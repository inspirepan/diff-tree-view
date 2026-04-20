from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from rich.color import Color
from rich.style import Style
from rich.text import Text
from textual.app import App, ComposeResult
from textual.widgets._tree import TreeNode

from dff.app import DffApp
from dff.config import TreeDisclosureStyle, UISettings
from dff.models import Change, FileChange, HunkStats
from dff.theme import TreeThemeTokens
from dff.widgets import ChangeTree


class TreeApp(App[None]):
    def __init__(
        self,
        changes: list[Change],
        *,
        collapse_single_child_dirs: bool | None = None,
        ui: UISettings | None = None,
    ) -> None:
        super().__init__()
        self._changes = changes
        self._collapse_single_child_dirs = collapse_single_child_dirs
        self._ui = ui or UISettings()

    def compose(self) -> ComposeResult:
        yield ChangeTree(self._changes, collapse_single_child_dirs=self._collapse_single_child_dirs, ui=self._ui)


def walk(node: TreeNode[Any]) -> Iterator[TreeNode[Any]]:
    yield node
    for child in node.children:
        yield from walk(child)


def plain_label(node: TreeNode[Any]) -> str:
    label = node.label
    return label if isinstance(label, str) else label.plain


def rich_label(node: TreeNode[Any]) -> Text:
    label = node.label
    return Text(label) if isinstance(label, str) else label


def sample_changes() -> list[Change]:
    return [
        Change(
            change_id="change-1",
            short_id="xmzynnxm",
            description="tidy logs",
            graph="@",
            files=(
                FileChange("src/app.py", "M", HunkStats(12, 3)),
                FileChange("src/cli.py", "M", HunkStats(5, 2)),
                FileChange("tests/test_app.py", "A", HunkStats(25, 0)),
            ),
        ),
        Change(
            change_id="change-2",
            short_id="4f2c6a",
            description="refactor parser",
            graph="○",
            files=(
                FileChange("src/parser.py", "M", HunkStats(18, 7), is_conflict=True),
                FileChange("dist/bundle.js", "M", HunkStats(240, 90), ignored=True),
            ),
        ),
    ]


async def test_change_tree_renders_groups_directories_and_stats() -> None:
    app = TreeApp(sample_changes())

    async with app.run_test() as pilot:
        await pilot.pause()
        tree = app.query_one(ChangeTree)

        # `root.children` now also includes blank spacer rows between change
        # groups. Filter them out to assert on the real change labels.
        group_labels = [
            plain_label(node) for node in tree.root.children if node.data is not None and not node.data.is_spacer
        ]
        assert group_labels == [
            "@  xmzynnxm  tidy logs  (+42,-5)",
            "○  4f2c6a  refactor parser  (+258,-97)",
        ]

        first_group = tree.root.children[0]
        assert [plain_label(node) for node in first_group.children] == ["src/", "tests/"]
        assert [plain_label(node) for node in first_group.children[0].children] == [
            "app.py  (+12,-3)  M",
            "cli.py  (+5,-2)  M",
        ]


async def test_change_tree_collapses_single_child_directories_when_enabled() -> None:
    changes = [
        Change(
            change_id="change-1",
            short_id="xmzynnxm",
            description="tidy logs",
            graph="@",
            files=(FileChange("src/dff/widgets/change_tree.py", "M", HunkStats(12, 3)),),
        )
    ]
    app = TreeApp(changes, collapse_single_child_dirs=True)

    async with app.run_test() as pilot:
        await pilot.pause()
        tree = app.query_one(ChangeTree)

        first_group = tree.root.children[0]
        assert [plain_label(node) for node in first_group.children] == ["src/dff/widgets/"]
        assert [plain_label(node) for node in first_group.children[0].children] == ["change_tree.py  (+12,-3)  M"]


async def test_change_tree_collapses_single_child_directories_by_default() -> None:
    changes = [
        Change(
            change_id="change-1",
            short_id="xmzynnxm",
            description="tidy logs",
            graph="@",
            files=(FileChange("src/dff/widgets/change_tree.py", "M", HunkStats(12, 3)),),
        )
    ]
    app = TreeApp(changes)

    async with app.run_test() as pilot:
        await pilot.pause()
        tree = app.query_one(ChangeTree)

        first_group = tree.root.children[0]
        assert [plain_label(node) for node in first_group.children] == ["src/dff/widgets/"]


async def test_change_tree_dims_ignored_files_and_marks_conflicts() -> None:
    app = TreeApp(sample_changes())

    async with app.run_test() as pilot:
        await pilot.pause()
        tree = app.query_one(ChangeTree)

        labels = {plain_label(node): rich_label(node) for node in walk(tree.root)}
        parser_label = labels["parser.py  (+18,-7)  !  M"]
        assert parser_label.style != "dim"
        assert any(span.style == "#d75f5f" for span in parser_label.spans)
        assert any(span.style == "dim" for span in labels["bundle.js  (+240,-90)  M"].spans)


async def test_change_tree_styles_all_file_status_badges() -> None:
    changes = [
        Change(
            change_id="change-1",
            short_id="xmzynnxm",
            description="status sweep",
            graph="@",
            files=(
                FileChange("modified.py", "M", HunkStats(1, 1)),
                FileChange("added.py", "A", HunkStats(1, 0)),
                FileChange("deleted.py", "D", HunkStats(0, 1)),
                FileChange("renamed.py", "R", HunkStats(4, 4)),
            ),
        )
    ]
    app = TreeApp(changes)

    async with app.run_test() as pilot:
        await pilot.pause()
        tree = app.query_one(ChangeTree)

        labels = {plain_label(node): rich_label(node) for node in walk(tree.root)}
        assert any(span.style == "#4db8b8" for span in labels["modified.py  (+1,-1)  M"].spans)
        assert any(span.style == "#4fb06c" for span in labels["added.py  (+1)  A"].spans)
        assert any(span.style == "#d75f5f" for span in labels["deleted.py  (-1)  D"].spans)
        assert any(span.style == "#e8b040" for span in labels["renamed.py  (+4,-4)  R"].spans)


async def test_change_tree_j_k_navigation_and_space_toggle_directory() -> None:
    app = TreeApp(sample_changes())

    async with app.run_test() as pilot:
        tree = app.query_one(ChangeTree)
        await pilot.pause()

        assert tree.cursor_node is not None
        assert plain_label(tree.cursor_node) == "@  xmzynnxm  tidy logs  (+42,-5)"

        await pilot.press("j")
        await pilot.pause()
        assert tree.cursor_node is not None
        assert plain_label(tree.cursor_node) == "src/"

        await pilot.press("space")
        await pilot.pause()
        assert tree.cursor_node is not None
        assert not tree.cursor_node.is_expanded

        await pilot.press("enter")
        await pilot.pause()
        assert tree.cursor_node is not None
        assert tree.cursor_node.is_expanded

        await pilot.press("k")
        await pilot.pause()
        assert tree.cursor_node is not None
        assert plain_label(tree.cursor_node) == "@  xmzynnxm  tidy logs  (+42,-5)"


async def test_change_tree_uses_compact_guides() -> None:
    app = TreeApp(sample_changes())

    async with app.run_test() as pilot:
        await pilot.pause()
        tree = app.query_one(ChangeTree)

        assert tree.guide_depth == 4
        assert tree.render_line(1).text.startswith(" ├─ [-] src/")
        assert tree.render_line(3).text.startswith(" │   └─ cli.py")
        assert tree.render_line(4).text.startswith(" └─ [-] tests/")


async def test_change_tree_right_aligns_status_and_stats() -> None:
    app = TreeApp(sample_changes())

    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        tree = app.query_one(ChangeTree)

        # render_line returns a Strip; its .text covers the tree's content width.
        row = tree.render_line(2).text
        assert "app.py" in row
        # Status letter sits two columns before the scrollbar / vkey border so
        # it doesn't collide with either.
        assert row.rstrip().endswith("M")
        assert row.endswith("M  ")
        assert "(+12,-3)  M  " in row


async def test_change_tree_has_no_right_border() -> None:
    app = DffApp(sample_changes())

    async with app.run_test() as pilot:
        await pilot.pause()
        tree = app.query_one(ChangeTree)

        # Right border removed — the blue scrollbar provides the separator now.
        assert tree.styles.border_right[0] == ""


async def test_change_tree_uses_bracket_disclosure_markers() -> None:
    app = TreeApp(sample_changes())

    async with app.run_test() as pilot:
        await pilot.pause()
        tree = app.query_one(ChangeTree)

        assert tree.render_line(0).text.startswith("[-] @")
        assert tree.render_line(1).text.startswith(" ├─ [-] src/")

        await pilot.press("j", "space")
        await pilot.pause()

        assert tree.render_line(1).text.startswith(" ├─ [+] src/")


async def test_change_tree_applies_custom_tokens_and_non_compact_guides() -> None:
    custom_tokens = TreeThemeTokens(
        disclosure="magenta",
        directory="yellow",
        file="white",
        diff_add="bright_green",
        diff_remove="bright_red",
        status_added="green",
        status_modified="blue",
        status_deleted="red",
        status_renamed="cyan",
        conflict="magenta",
        guides="yellow",
        change_graph_current="magenta",
        change_graph_default="blue",
        change_id="cyan",
        change_description="yellow",
        cursor_background="#222222",
        diff_add_bg="#2b4938",
        diff_add_char_bg="#3d7b52",
        diff_add_text="#c8e6c9",
        diff_remove_bg="#4d2f33",
        diff_remove_char_bg="#8a4a52",
        diff_remove_text="#ffcdd2",
        change_row_bg="#2c3846",
    )
    app = TreeApp(
        sample_changes(),
        ui=UISettings(
            compact_tree_guides=False,
            tree_disclosure_style=TreeDisclosureStyle.TRIANGLES,
            tree_theme=custom_tokens,
        ),
    )

    async with app.run_test() as pilot:
        await pilot.pause()
        tree = app.query_one(ChangeTree)

        assert tree.guide_depth == 4
        assert tree.render_line(0).text.startswith("▼ @")
        assert tree.render_line(1).text.startswith("├── ▼ src/")

        assert tree.get_component_rich_style("tree--guides", partial=False).color == Style.parse("yellow").color

        change_label = rich_label(tree.root.children[0])
        assert change_label.spans[0].style == "magenta"
        assert change_label.spans[1].style == "cyan"
        assert change_label.spans[2].style == "yellow"

        directory_label = rich_label(tree.root.children[0].children[0])
        assert directory_label.style == "yellow"

        file_label = rich_label(tree.root.children[0].children[0].children[0])
        # File name is now colored by status. src/app.py is "M" → change_graph_current.
        assert file_label.style == "magenta"
        span_styles = {span.style for span in file_label.spans}
        assert "blue" in span_styles
        assert "bright_green" in span_styles
        assert "bright_red" in span_styles


async def test_change_tree_ignores_mouse_hover() -> None:
    app = TreeApp(sample_changes())

    async with app.run_test() as pilot:
        await pilot.pause()
        tree = app.query_one(ChangeTree)

        await pilot.hover(tree, offset=(1, 1))
        await pilot.pause()

        assert tree.hover_line == -1
        assert not any(node._hover for node in walk(tree.root))


async def test_change_tree_cursor_row_uses_background_without_overriding_token_colors() -> None:
    app = DffApp(sample_changes())

    async with app.run_test(size=(180, 40)) as pilot:
        await pilot.pause()
        tree = app.query_one(ChangeTree)
        strip = tree.render_line(0)

        rich_cursor_style = tree.get_component_rich_style("tree--cursor", partial=False)
        assert rich_cursor_style.bgcolor == Color.parse("#343a44")
        assert rich_cursor_style.color in {None, Color.default()}
        assert rich_cursor_style.bold in {None, False}

        colored_segments = [
            (segment.text, segment.style)
            for segment in strip._segments
            if segment.text.strip() and segment.style is not None
        ]
        assert any(style.bgcolor == Color.parse("#343a44") for _, style in colored_segments)
        assert any(style.color == Color.parse("#e8b040") for text, style in colored_segments if "@" in text)
        assert any(style.color == Color.parse("#4fb06c") for text, style in colored_segments if "+42" in text)


async def test_change_tree_shift_groups_with_uppercase_j_and_k() -> None:
    app = TreeApp(sample_changes())

    async with app.run_test() as pilot:
        tree = app.query_one(ChangeTree)
        await pilot.pause()

        await pilot.press("j", "j")
        await pilot.pause()
        assert tree.cursor_node is not None
        assert plain_label(tree.cursor_node) == "app.py  (+12,-3)  M"

        await pilot.press("J")
        await pilot.pause()
        assert tree.cursor_node is not None
        assert plain_label(tree.cursor_node) == "○  4f2c6a  refactor parser  (+258,-97)"

        await pilot.press("K")
        await pilot.pause()
        assert tree.cursor_node is not None
        assert plain_label(tree.cursor_node) == "@  xmzynnxm  tidy logs  (+42,-5)"
