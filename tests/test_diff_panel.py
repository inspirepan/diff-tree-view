from __future__ import annotations

from pathlib import Path

from textual_diff_view import DiffView

from dff.app import DffApp
from dff.models import Change, FileChange, FileSides, HunkStats
from dff.widgets import ChangeTree, DiffPanel


def make_change() -> Change:
    return Change(
        change_id="c-demo",
        short_id="demo",
        description="demo",
        files=(
            FileChange("src/a.py", "M", HunkStats(1, 0)),
            FileChange("src/b.bin", "M", HunkStats(0, 0), is_binary=True),
        ),
    )


class StubBackend:
    def __init__(self, repo_root: Path, sides_by_path: dict[str, FileSides]) -> None:
        self.repo_root = repo_root
        self._sides_by_path = sides_by_path
        self._change = make_change()

    def list_changes(self, *, rev: str | None = None) -> tuple[Change, ...]:
        return (self._change,)

    def get_sides(self, change: Change, file: FileChange) -> FileSides:
        return self._sides_by_path[file.path]


async def test_diff_panel_shows_file_and_updates_header(tmp_path: Path) -> None:
    sides = {
        "src/a.py": FileSides(before="old\n", after="new\n"),
        "src/b.bin": FileSides(before="", after="", binary=True),
    }
    backend = StubBackend(tmp_path, sides)
    app = DffApp(backend.list_changes(), backend=backend, live_watch=False)

    async with app.run_test(size=(180, 40)) as pilot:
        await pilot.pause()
        panel = app.query_one(DiffPanel)
        tree = app.query_one(ChangeTree)

        # Move cursor down until we land on src/a.py
        for _ in range(6):
            await pilot.press("j")
            await pilot.pause()
            node = tree.cursor_node
            if node is not None and node.data is not None and node.data.file is not None:
                if node.data.file.path == "src/a.py":
                    break

        await pilot.pause()
        diff_views = list(panel.query(DiffView))
        assert len(diff_views) == 1
        assert diff_views[0].code_original == "old\n"
        assert diff_views[0].code_modified == "new\n"


async def test_diff_panel_renders_placeholder_for_binary(tmp_path: Path) -> None:
    sides = {
        "src/a.py": FileSides(before="a\n", after="a\n"),
        "src/b.bin": FileSides(before="", after="", binary=True),
    }
    backend = StubBackend(tmp_path, sides)
    app = DffApp(backend.list_changes(), backend=backend, live_watch=False)

    async with app.run_test(size=(180, 40)) as pilot:
        await pilot.pause()
        tree = app.query_one(ChangeTree)
        panel = app.query_one(DiffPanel)

        # Walk all file nodes to find src/b.bin
        for _ in range(10):
            await pilot.press("j")
            await pilot.pause()
            node = tree.cursor_node
            if node is not None and node.data is not None and node.data.file is not None:
                if node.data.file.path == "src/b.bin":
                    break

        await pilot.pause()
        assert list(panel.query(DiffView)) == []
        placeholders = list(panel.query(".diff-placeholder"))
        assert placeholders
        rendered = placeholders[0].render()
        plain = getattr(rendered, "plain", None)
        text = plain if isinstance(plain, str) else str(rendered)
        assert "binary" in text


async def test_diff_panel_backgrounds_are_transparent_under_transparent_mode(tmp_path: Path) -> None:
    sides = {
        "src/a.py": FileSides(before="old one\nsame\n", after="new one\nsame\n"),
        "src/b.bin": FileSides(before="", after="", binary=True),
    }
    backend = StubBackend(tmp_path, sides)
    app = DffApp(backend.list_changes(), backend=backend, live_watch=False)

    async with app.run_test(size=(180, 40)) as pilot:
        await pilot.pause()
        panel = app.query_one(DiffPanel)
        tree = app.query_one(ChangeTree)

        for _ in range(6):
            await pilot.press("j")
            await pilot.pause()
            node = tree.cursor_node
            if node is not None and node.data is not None and node.data.file is not None:
                if node.data.file.path == "src/a.py":
                    break
        await pilot.pause()

        # Real invariant: no literal RGB(0,0,0) background in any rendered segment.
        # `ansi_default` resolves to Color(0, 0, 0, ansi=-1) which renders as
        # terminal-default (ESC[49m); a pure RGB black would appear as an
        # explicit ESC[48;2;0;0;0m and break transparency.
        view = panel.query_one(DiffView)
        from textual_diff_view._diff_view import DiffCode, LineAnnotations

        def assert_no_black_rgb_bg(strip) -> None:
            for seg in strip._segments:
                if seg.style is None or seg.style.bgcolor is None:
                    continue
                bg = seg.style.bgcolor
                is_rgb_black = bg.triplet is not None and bg.triplet == (0, 0, 0)
                assert not is_rgb_black, f"segment {seg.text!r} has explicit RGB black bg"

        for la in view.query(LineAnnotations):
            for y in range(len(la.numbers)):
                assert_no_black_rgb_bg(la.render_line(y))
        for dc in view.query(DiffCode):
            for y in range(dc.size.height):
                assert_no_black_rgb_bg(dc.render_line(y))


async def test_diff_panel_toggle_split_flips_diff_view_reactive(tmp_path: Path) -> None:
    sides = {
        "src/a.py": FileSides(before="old\n", after="new\n"),
        "src/b.bin": FileSides(before="", after="", binary=True),
    }
    backend = StubBackend(tmp_path, sides)
    app = DffApp(backend.list_changes(), backend=backend, live_watch=False)

    async with app.run_test(size=(180, 40)) as pilot:
        await pilot.pause()
        tree = app.query_one(ChangeTree)
        panel = app.query_one(DiffPanel)

        for _ in range(6):
            await pilot.press("j")
            await pilot.pause()
            node = tree.cursor_node
            if node is not None and node.data is not None and node.data.file is not None:
                if node.data.file.path == "src/a.py":
                    break
        await pilot.pause()

        views = list(panel.query(DiffView))
        assert views
        initial_split = views[0].split

        await pilot.press("m")
        await pilot.pause()
        views_after = list(panel.query(DiffView))
        assert views_after[0].split is not initial_split
