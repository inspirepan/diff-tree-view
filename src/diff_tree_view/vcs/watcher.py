from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable
from pathlib import Path

from watchfiles import Change as WatchChange
from watchfiles import DefaultFilter, awatch

DEFAULT_DEBOUNCE_MS = 150
DEFAULT_IGNORE_DIRS: frozenset[str] = frozenset(
    {
        "__pycache__",
        ".ruff_cache",
        ".pytest_cache",
        ".mypy_cache",
        ".venv",
        "node_modules",
        "dist",
        "build",
        ".tox",
    }
)


class RepoFilter(DefaultFilter):
    def __init__(self, ignore_dirs: Iterable[str]) -> None:
        super().__init__()
        self._ignore_dirs = set(ignore_dirs)

    def __call__(self, change: WatchChange, path: str) -> bool:
        if any(segment in self._ignore_dirs for segment in Path(path).parts):
            return False
        return super().__call__(change, path)


async def watch_repo(
    root: Path,
    *,
    stop_event: asyncio.Event | None = None,
    debounce_ms: int = DEFAULT_DEBOUNCE_MS,
    ignore_dirs: Iterable[str] = DEFAULT_IGNORE_DIRS,
) -> AsyncIterator[None]:
    """Yield once per coalesced batch of filesystem events under `root`."""

    async for _ in awatch(
        root,
        stop_event=stop_event,
        debounce=debounce_ms,
        step=max(debounce_ms // 3, 20),
        watch_filter=RepoFilter(ignore_dirs),
        recursive=True,
    ):
        yield None
