from __future__ import annotations

import asyncio
from pathlib import Path

from dff.app import DffApp
from dff.models import Change, FileChange, FileSides, HunkStats
from dff.vcs.base import Backend
from dff.vcs.watcher import watch_repo
from dff.widgets import ChangeTree


def node_label_plain(node) -> str:  # type: ignore[no-untyped-def]
    label = node.label
    return label if isinstance(label, str) else label.plain


def make_change(path: str, status: str = "M", stats: HunkStats | None = None) -> Change:
    return Change(
        change_id="c",
        short_id="c",
        description="demo",
        files=(FileChange(path, status, stats or HunkStats(1, 0)),),
    )


class StubBackend:
    def __init__(self, repo_root: Path, batches: list[tuple[Change, ...]]) -> None:
        self.repo_root = repo_root
        self._batches = batches
        self.calls = 0

    def list_changes(self, *, rev: str | None = None) -> tuple[Change, ...]:
        index = min(self.calls, len(self._batches) - 1)
        self.calls += 1
        return self._batches[index]

    def get_sides(self, change: Change, file: FileChange) -> FileSides:
        return FileSides(before="", after="")


async def test_watch_repo_debounces_bursts(tmp_path: Path) -> None:
    stop = asyncio.Event()

    async def produce_writes() -> None:
        # Wait a tick for awatch to settle, then write several files in a burst.
        await asyncio.sleep(0.05)
        for i in range(5):
            (tmp_path / f"f{i}.txt").write_text(str(i))
        await asyncio.sleep(0.4)
        stop.set()

    writer = asyncio.create_task(produce_writes())
    batches = 0
    async for _ in watch_repo(tmp_path, stop_event=stop, debounce_ms=50):
        batches += 1
    await writer

    assert batches >= 1
    # 5 rapid writes should coalesce to one or two notifications, not five.
    assert batches <= 2


def test_change_tree_reload_swaps_content_and_preserves_cursor_path() -> None:
    async def scenario() -> None:
        backend = StubBackend(
            repo_root=Path("."),
            batches=[
                (make_change("a.py"),),
                (make_change("a.py", stats=HunkStats(9, 0)),),
            ],
        )
        app = DffApp(backend.list_changes(), backend=backend, live_watch=False)

        async with app.run_test() as pilot:
            await pilot.pause()
            tree = app.query_one(ChangeTree)
            await pilot.press("j")
            await pilot.pause()
            cursor = tree.cursor_node
            assert cursor is not None
            assert node_label_plain(cursor).startswith("a.py")

            tree.reload_changes(backend.list_changes())
            await pilot.pause()

            cursor = tree.cursor_node
            assert cursor is not None
            assert node_label_plain(cursor).startswith("a.py")
            assert "(+9)" in node_label_plain(cursor)

    asyncio.run(scenario())


def test_change_tree_reload_preserves_collapsed_group_and_directory() -> None:
    async def scenario() -> None:
        change = Change(
            change_id="c",
            short_id="c",
            description="demo",
            files=(
                FileChange("src/a.py", "M", HunkStats(1, 0)),
                FileChange("src/b.py", "M", HunkStats(2, 0)),
            ),
        )
        backend = StubBackend(repo_root=Path("."), batches=[(change,), (change,)])
        app = DffApp(backend.list_changes(), backend=backend, live_watch=False)

        async with app.run_test() as pilot:
            await pilot.pause()
            tree = app.query_one(ChangeTree)

            group = tree.root.children[0]
            src_dir = group.children[0]
            assert src_dir.is_expanded
            src_dir.collapse()
            group.collapse()
            assert not src_dir.is_expanded
            assert not group.is_expanded

            tree.reload_changes(backend.list_changes())
            await pilot.pause()

            group = tree.root.children[0]
            assert not group.is_expanded, "reload must not re-expand a collapsed change group"
            group.expand()
            src_dir = group.children[0]
            assert not src_dir.is_expanded, "reload must not re-expand a collapsed directory"

    asyncio.run(scenario())


async def test_dff_app_schedules_watcher_when_backend_is_provided(tmp_path: Path) -> None:
    backend = StubBackend(repo_root=tmp_path, batches=[(make_change("demo.py"),)])
    app = DffApp(backend.list_changes(), backend=backend, live_watch=True)

    async with app.run_test() as pilot:
        await pilot.pause()
        running_workers = {worker.name for worker in app.workers}
        assert "dff-watcher" in running_workers


async def test_dff_app_does_not_start_watcher_without_backend() -> None:
    app = DffApp([make_change("demo.py")])

    async with app.run_test() as pilot:
        await pilot.pause()
        running_workers = {worker.name for worker in app.workers}
        assert "dff-watcher" not in running_workers


async def test_backend_protocol_matches_stub(tmp_path: Path) -> None:
    backend: Backend = StubBackend(repo_root=tmp_path, batches=[()])
    assert isinstance(backend, Backend)


async def test_dff_app_reload_action_refreshes_tree_from_backend(tmp_path: Path) -> None:
    backend = StubBackend(
        repo_root=tmp_path,
        batches=[
            (make_change("a.py", stats=HunkStats(1, 0)),),
            (make_change("a.py", stats=HunkStats(42, 0)),),
        ],
    )
    app = DffApp(backend.list_changes(), backend=backend, live_watch=False)

    async with app.run_test() as pilot:
        await pilot.pause()
        tree = app.query_one(ChangeTree)
        await pilot.press("r")
        await pilot.pause()

        found = []

        def collect(node):  # type: ignore[no-untyped-def]
            found.append(node_label_plain(node))
            for child in node.children:
                collect(child)

        collect(tree.root)
        assert any("(+42)" in label for label in found)
