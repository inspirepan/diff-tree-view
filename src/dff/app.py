from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical

from dff.config import UISettings
from dff.models import Change, FileChange, FileSides
from dff.vcs.base import Backend
from dff.vcs.watcher import DEFAULT_DEBOUNCE_MS, watch_repo
from dff.widgets import ChangeTree, DiffPanel, NodeMeta, StatusBar


class DffApp(App[None]):
    CSS_PATH = "app.tcss"
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("q", "quit", "Quit", show=False),
        Binding("r", "reload", "Reload", show=False),
        Binding("m", "toggle_split", "Split", show=False),
        # Both `w` and `z` toggle word-wrap on the diff. `z` matches vim's
        # `zw`/`zl` wrap muscle memory; `w` is the historical default.
        Binding("w", "toggle_wrap", "Wrap", show=False),
        Binding("z", "toggle_wrap", "Wrap", show=False),
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
            with Horizontal(id="panes"):
                yield ChangeTree(self.changes, ui=self.ui)
                yield DiffPanel(ui=self.ui, id="diff-panel")
            yield StatusBar(id="status-bar", ui=self.ui)

    def on_mount(self) -> None:
        self.theme = "textual-ansi"
        self.add_class("-transparent" if self.ui.transparent_background else "-opaque")
        if self.live_watch and self.backend is not None:
            self.run_worker(self._watch_loop(), name="dff-watcher", exclusive=True)
        self.call_after_refresh(self._sync_diff_to_cursor)

    def action_reload(self) -> None:
        if self.backend is None:
            return
        self._refresh_changes()

    def action_toggle_split(self) -> None:
        self.query_one(DiffPanel).toggle_split()

    def action_toggle_wrap(self) -> None:
        self.query_one(DiffPanel).toggle_wrap()

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
        self._sync_diff_to_cursor()

    async def _watch_loop(self) -> None:
        assert self.backend is not None
        async for _ in watch_repo(self.backend.repo_root, debounce_ms=self.watch_debounce_ms):
            self._refresh_changes()

    def on_tree_node_highlighted(self, event: ChangeTree.NodeHighlighted[NodeMeta]) -> None:
        self._route_node(event.node.data)

    def on_tree_node_selected(self, event: ChangeTree.NodeSelected[NodeMeta]) -> None:
        self._route_node(event.node.data)

    def _sync_diff_to_cursor(self) -> None:
        tree = self.query_one(ChangeTree)
        node = tree.cursor_node
        if node is None:
            return
        self._route_node(node.data)

    def _route_node(self, data: NodeMeta | None) -> None:
        if data is None or data.file is None or data.change is None:
            return
        self._load_file_diff(data.change, data.file)

    def _load_file_diff(self, change: Change, file: FileChange) -> None:
        panel = self.query_one(DiffPanel)
        sides = self._resolve_sides(change, file)
        self.run_worker(panel.show_file(change, file, sides), exclusive=True, name="dff-diff-load")

    def _resolve_sides(self, change: Change, file: FileChange) -> FileSides:
        if file.is_binary:
            return FileSides(before="", after="", binary=True)
        if self.backend is None:
            return FileSides(before="", after="")
        try:
            return self.backend.get_sides(change, file)
        except Exception:
            return FileSides(before="", after="")
