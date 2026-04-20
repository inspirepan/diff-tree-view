from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import ClassVar, cast

from rich.color import Color
from rich.style import Style
from rich.text import Text
from textual import events
from textual._segment_tools import line_pad
from textual.binding import Binding
from textual.strip import Strip
from textual.widgets import Tree
from textual.widgets._tree import TreeNode

from dff.config import TreeDisclosureStyle, UISettings
from dff.models import Change, FileChange, HunkStats


@dataclass(slots=True)
class DirectoryEntry:
    directories: dict[str, DirectoryEntry] = field(default_factory=dict)
    files: list[FileChange] = field(default_factory=list)


@dataclass(slots=True)
class NodeMeta:
    left: Text
    right: Text | None = None


class ChangeTree(Tree[NodeMeta]):
    BINDINGS: ClassVar[list[Binding | tuple[str, str] | tuple[str, str, str]]] = [
        *Tree.BINDINGS,
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("J", "next_group", "Next group", show=False),
        Binding("K", "previous_group", "Previous group", show=False),
    ]

    def __init__(
        self,
        changes: Sequence[Change],
        *,
        collapse_single_child_dirs: bool | None = None,
        ui: UISettings | None = None,
    ) -> None:
        super().__init__("root")
        self._changes = tuple(changes)
        self._ui = ui or UISettings()
        self._collapse_single_child_dirs = (
            self._ui.collapse_single_child_directories
            if collapse_single_child_dirs is None
            else collapse_single_child_dirs
        )
        self._tree_theme = self._ui.resolved_tree_theme
        self.ICON_NODE, self.ICON_NODE_EXPANDED = self._disclosure_icons()
        self.guide_depth = 4
        self.show_root = False
        self.root.expand()
        self._build_tree()

    def on_mount(self) -> None:
        guides_color = self._tree_theme.guides
        self.styles.border_right = ("vkey", guides_color)
        self.styles.scrollbar_color = guides_color
        self.styles.scrollbar_color_hover = guides_color
        self.styles.scrollbar_color_active = guides_color
        if self.root.children:
            self.move_cursor(self.root.children[0])

    def action_select_cursor(self) -> None:
        node = self.cursor_node
        if node is None:
            return
        if node.allow_expand:
            node.toggle()
            return
        self.select_node(node)

    def action_next_group(self) -> None:
        group_node = self._current_group_node()
        if group_node is None:
            return
        group_index = self.root.children.index(group_node)
        if group_index < len(self.root.children) - 1:
            self.move_cursor(self.root.children[group_index + 1])

    def action_previous_group(self) -> None:
        group_node = self._current_group_node()
        if group_node is None:
            return
        group_index = self.root.children.index(group_node)
        if group_index > 0:
            self.move_cursor(self.root.children[group_index - 1])

    def _on_mouse_move(self, event: events.MouseMove) -> None:
        event.stop()
        self.hover_line = -1

    def _on_leave(self, _: events.Leave) -> None:
        self.hover_line = -1

    def watch_hover_line(self, previous_hover_line: int, hover_line: int) -> None:
        super().watch_hover_line(previous_hover_line, hover_line)
        if hover_line != -1:
            self.hover_line = -1

    def get_component_rich_style(self, *names: str, partial: bool = False, default: Style | None = None) -> Style:
        if len(names) == 1 and names[0] in {
            "tree--guides",
            "tree--guides-hover",
            "tree--guides-selected",
        }:
            return super().get_component_rich_style(*names, partial=partial, default=default) + Style.parse(
                self._tree_theme.guides
            )
        if len(names) == 1 and names[0] == "tree--cursor":
            return Style(bgcolor=Color.parse(self._tree_theme.cursor_background))
        return super().get_component_rich_style(*names, partial=partial, default=default)

    def render_label(self, node: TreeNode[NodeMeta], base_style: Style, style: Style) -> Text:
        left = self._node_left(node).copy()
        left.stylize(style)

        if node.allow_expand:
            disclosure_style = base_style + Style.parse(self._tree_theme.disclosure)
            if style.bgcolor is not None:
                disclosure_style += Style(bgcolor=style.bgcolor)
            prefix: tuple[str, Style] = (
                self.ICON_NODE_EXPANDED if node.is_expanded else self.ICON_NODE,
                disclosure_style,
            )
        else:
            prefix = ("", base_style)

        return Text.assemble(prefix, left)

    def _render_line(self, y: int, x1: int, x2: int, base_style: Style) -> Strip:
        tree_lines = self._tree_lines
        width = self.size.width

        if y >= len(tree_lines):
            return Strip.blank(width, base_style)

        line = tree_lines[y]
        is_hover = self.hover_line >= 0 and any(node._hover for node in line.path)

        base_hidden = self.get_component_styles("tree--guides").color.a == 0
        hover_hidden = self.get_component_styles("tree--guides-hover").color.a == 0
        selected_hidden = self.get_component_styles("tree--guides-selected").color.a == 0

        base_guide_style = self.get_component_rich_style("tree--guides", partial=True)
        guide_hover_style = base_guide_style + self.get_component_rich_style("tree--guides-hover", partial=True)
        guide_selected_style = base_guide_style + self.get_component_rich_style("tree--guides-selected", partial=True)

        hover = line.path[0]._hover
        selected = line.path[0]._selected and self.has_focus

        line_style = self.get_component_rich_style("tree--highlight-line") if is_hover else base_style
        line_style += Style(meta={"line": y})

        guides = Text(style=line_style)
        guide_style = base_guide_style
        hidden = True

        for node in line.path[1:]:
            hidden = base_hidden
            if hover:
                guide_style = guide_hover_style
                hidden = hover_hidden
            if selected:
                guide_style = guide_selected_style
                hidden = selected_hidden

            space, vertical, _, _ = self._guide_chars(guide_style, hidden)
            guide = space if node.is_last else vertical
            if node != line.path[-1]:
                guides.append(guide, style=guide_style)
            hover = hover or node._hover
            selected = (selected or node._selected) and self.has_focus

        if len(line.path) > 1:
            _, _, terminator, cross = self._guide_chars(guide_style, hidden)
            guides.append(terminator if line.last else cross, style=guide_style)

        label_style = self.get_component_rich_style("tree--label", partial=True)
        if self.hover_line == y:
            label_style += self.get_component_rich_style("tree--highlight", partial=True)
        if self.cursor_line == y:
            label_style += self.get_component_rich_style("tree--cursor", partial=False)

        node = line.path[-1]
        label = self.render_label(node, line_style, label_style).copy()
        label.stylize(Style(meta={"node": node._id}))

        left_text = Text(style=line_style)
        left_text.append(guides)
        left_text.append(label)

        right_text: Text | None = None
        right_source = self._node_right(node)
        if right_source is not None and right_source.plain:
            right_text = right_source.copy()
            right_text.stylize(label_style)
            right_text.stylize(Style(meta={"node": node._id}))

        if right_text is not None:
            left_w = left_text.cell_len
            right_w = right_text.cell_len
            # Reserve two trailing columns before the scrollbar / vkey border
            # so the right content doesn't sit flush against the scrollbar.
            trailing = 2
            gap = max(width - left_w - right_w - trailing, 2)
            composite = Text(style=line_style)
            composite.append(left_text)
            composite.append(" " * gap, style=line_style)
            composite.append(right_text)
            composite.append(" " * trailing, style=line_style)
        else:
            composite = left_text

        segments = list(composite.render(self.app.console))
        pad_width = max(self.virtual_size.width, width)
        trailing = pad_width - composite.cell_len
        if trailing > 0:
            segments = line_pad(segments, 0, trailing, line_style)
        strip = Strip(segments)

        return strip.crop(x1, x2)

    def _current_group_node(self) -> TreeNode[NodeMeta] | None:
        node = self.cursor_node
        if node is None:
            return None
        while node.parent is not None and node.parent != self.root:
            node = node.parent
        if node.parent == self.root:
            return node
        return None

    def _build_tree(self) -> None:
        for change in self._changes:
            left, right = self._format_change_node(change)
            label = self._combine_label(left, right)
            group_node = self.root.add(label, data=NodeMeta(left=left, right=right), expand=True)
            directory_root = self._build_directory_tree(change.files)
            self._add_directory_children(group_node, directory_root)

    def reload_changes(self, changes: Sequence[Change]) -> None:
        """Rebuild the tree from a fresh set of changes, preserving cursor path."""
        cursor_path = self._cursor_label_path()
        self._changes = tuple(changes)
        self.clear()
        self.root.expand()
        self._build_tree()
        self._build()
        if cursor_path:
            self._restore_cursor(cursor_path)
        elif self.root.children:
            self.move_cursor(self.root.children[0])

    def _cursor_label_path(self) -> list[str]:
        node = self.cursor_node
        if node is None or node is self.root:
            return []
        path: list[str] = []
        while node is not None and node is not self.root:
            path.append(self._node_identity(node))
            node = node.parent
        path.reverse()
        return path

    def _restore_cursor(self, path: Sequence[str]) -> None:
        node: TreeNode[NodeMeta] = self.root
        for identity in path:
            match = next(
                (child for child in node.children if self._node_identity(child) == identity),
                None,
            )
            if match is None:
                break
            node = match
        if node is self.root:
            if self.root.children:
                self.move_cursor(self.root.children[0])
            return
        self.move_cursor(node)

    def _node_identity(self, node: TreeNode[NodeMeta]) -> str:
        data = node.data
        if isinstance(data, NodeMeta):
            return data.left.plain
        label = node.label
        return label if isinstance(label, str) else label.plain

    def _disclosure_icons(self) -> tuple[str, str]:
        if self._ui.tree_disclosure_style is TreeDisclosureStyle.TRIANGLES:
            return "▶ ", "▼ "
        return "[+] ", "[-] "

    def _uses_aligned_compact_guides(self) -> bool:
        return self._ui.compact_tree_guides and self._ui.tree_disclosure_style is TreeDisclosureStyle.BRACKETS

    def _guide_chars(self, style: Style, hidden: bool) -> tuple[str, str, str, str]:
        lines: tuple[str, str, str, str]
        if not self.show_guides or hidden:
            lines = ("    ", "    ", "    ", "    ")
        elif self._uses_aligned_compact_guides():
            if style.bold:
                lines = ("    ", " ┃  ", " ┗━ ", " ┣━ ")
            elif style.underline2:
                lines = ("    ", " ║  ", " ╚═ ", " ╠═ ")
            else:
                lines = ("    ", " │  ", " └─ ", " ├─ ")
        else:
            if style.bold:
                lines = ("    ", "┃   ", "┗━━ ", "┣━━ ")
            elif style.underline2:
                lines = ("    ", "║   ", "╚══ ", "╠══ ")
            else:
                lines = ("    ", "│   ", "└── ", "├── ")
        return cast("tuple[str, str, str, str]", lines)

    def _build_directory_tree(self, files: Sequence[FileChange]) -> DirectoryEntry:
        root = DirectoryEntry()
        for file_change in sorted(files, key=lambda item: item.path):
            path = PurePosixPath(file_change.path)
            current = root
            for part in path.parts[:-1]:
                current = current.directories.setdefault(part, DirectoryEntry())
            current.files.append(file_change)
        return root

    def _add_directory_children(self, parent: TreeNode[NodeMeta], entry: DirectoryEntry) -> None:
        for directory_name in sorted(entry.directories):
            directory_entry = entry.directories[directory_name]
            name, collapsed_entry = self._collapse_directory(directory_name, directory_entry)
            left, right = self._format_directory_node(name)
            label = self._combine_label(left, right)
            directory_node = parent.add(label, data=NodeMeta(left=left, right=right), expand=True)
            self._add_directory_children(directory_node, collapsed_entry)
        for file_change in sorted(entry.files, key=lambda item: PurePosixPath(item.path).name):
            left, right = self._format_file_node(file_change)
            label = self._combine_label(left, right)
            parent.add_leaf(label, data=NodeMeta(left=left, right=right))

    def _collapse_directory(self, name: str, entry: DirectoryEntry) -> tuple[str, DirectoryEntry]:
        if not self._collapse_single_child_dirs:
            return name, entry

        current_name = name
        current_entry = entry
        while not current_entry.files and len(current_entry.directories) == 1:
            child_name, child_entry = next(iter(current_entry.directories.items()))
            current_name = f"{current_name}/{child_name}"
            current_entry = child_entry
        return current_name, current_entry

    def _format_change_node(self, change: Change) -> tuple[Text, Text | None]:
        left = Text()
        graph_style = (
            self._tree_theme.change_graph_current if change.graph == "@" else self._tree_theme.change_graph_default
        )
        left.append(change.graph, style=graph_style)
        left.append(f"  {change.short_id}", style=self._tree_theme.change_id)
        if change.description:
            left.append(f"  {change.description}", style=self._tree_theme.change_description)
        right = self._format_stats(change.stats())
        return left, right if right.plain else None

    def _format_directory_node(self, label: str) -> tuple[Text, Text | None]:
        return Text(f"{label}/", style=self._tree_theme.directory), None

    def _format_file_node(self, file_change: FileChange) -> tuple[Text, Text | None]:
        left = Text(PurePosixPath(file_change.path).name, style=self._tree_theme.file)
        if file_change.ignored:
            left.stylize("dim")

        right = Text()
        stats = self._format_stats(file_change.stats)
        if stats.plain:
            right.append_text(stats)
            right.append("  ")
        if file_change.is_conflict:
            right.append("!", style=self._tree_theme.conflict)
            right.append("  ")
        right.append(file_change.status, style=self._status_style(file_change.status))
        if file_change.ignored:
            right.stylize("dim")
        return left, right if right.plain else None

    def _combine_label(self, left: Text, right: Text | None) -> Text:
        if right is None or not right.plain:
            return left.copy()
        combined = left.copy()
        combined.append("  ")
        combined.append_text(right)
        return combined

    def _node_left(self, node: TreeNode[NodeMeta]) -> Text:
        data = node.data
        if isinstance(data, NodeMeta):
            return data.left
        label = node.label
        return Text(label) if isinstance(label, str) else label

    def _node_right(self, node: TreeNode[NodeMeta]) -> Text | None:
        data = node.data
        if isinstance(data, NodeMeta):
            return data.right
        return None

    def _format_stats(self, stats: HunkStats) -> Text:
        text = Text()
        if not stats.added and not stats.removed:
            return text
        decoration_style = self._tree_theme.guides
        text.append("(", style=decoration_style)
        if stats.added:
            text.append(f"+{stats.added}", style=self._tree_theme.diff_add)
        if stats.added and stats.removed:
            text.append(",", style=decoration_style)
        if stats.removed:
            text.append(f"-{stats.removed}", style=self._tree_theme.diff_remove)
        text.append(")", style=decoration_style)
        return text

    def _status_style(self, status: str) -> str:
        return {
            "A": self._tree_theme.status_added,
            "D": self._tree_theme.status_deleted,
            "R": self._tree_theme.status_renamed,
            "M": self._tree_theme.status_modified,
        }.get(status, "default")
