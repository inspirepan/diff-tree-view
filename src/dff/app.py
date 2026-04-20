from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical

from dff.config import UISettings
from dff.models import Change
from dff.vcs.base import Backend
from dff.vcs.watcher import DEFAULT_DEBOUNCE_MS, watch_repo
from dff.widgets import ChangeTree, StatusBar


class DffApp(App[None]):
    CSS_PATH = "app.tcss"
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("q", "quit", "Quit", show=False),
        Binding("r", "reload", "Reload", show=False),
    ]

    def __init__(
        self,
        changes: Sequence[Change],
        *,
        backend: Backend | None = None,
        rev: str | None = None,
        live_watch: bool = True,
        watch_debounce_ms: int = DEFAULT_DEBOUNCE_MS,
        ui: UISettings | None = None,
    ) -> None:
        super().__init__()
        self.changes = tuple(changes)
        self.backend = backend
        self.rev = rev
        self.live_watch = live_watch and backend is not None
        self.watch_debounce_ms = watch_debounce_ms
        self.ui = ui or UISettings()

    def compose(self) -> ComposeResult:
        with Vertical(id="app-shell"):
            yield ChangeTree(self.changes, ui=self.ui)
            yield StatusBar(id="status-bar", ui=self.ui)

    def on_mount(self) -> None:
        self.theme = "textual-ansi"
        self.add_class("-transparent" if self.ui.transparent_background else "-opaque")
        if self.live_watch and self.backend is not None:
            self.run_worker(self._watch_loop(), name="dff-watcher", exclusive=True)

    def action_reload(self) -> None:
        if self.backend is None:
            return
        self._refresh_changes()

    def _refresh_changes(self) -> None:
        if self.backend is None:
            return
        try:
            new_changes = self.backend.list_changes(rev=self.rev)
        except Exception:
            self.bell()
            return
        self.changes = tuple(new_changes)
        tree = self.query_one(ChangeTree)
        tree.reload_changes(self.changes)

    async def _watch_loop(self) -> None:
        assert self.backend is not None
        async for _ in watch_repo(self.backend.repo_root, debounce_ms=self.watch_debounce_ms):
            self._refresh_changes()
