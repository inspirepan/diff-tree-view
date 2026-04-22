from __future__ import annotations

import difflib
from typing import Any

from pygments.token import Token
from rich.style import Style
from rich.text import Text
from textual import containers, events
from textual._loop import loop_last
from textual._segment_tools import line_pad
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.content import Content, Span
from textual.highlight import HighlightTheme
from textual.message import Message
from textual.reactive import reactive
from textual.strip import Strip
from textual.widgets import Static
from textual_diff_view import DiffView
from textual_diff_view._diff_view import (
    DiffCode,
    DiffScrollContainer,
    FoldedLineContent,
    LineAnnotations,
    LineContent,
    fill_lists,
)
from textual_diff_view._diff_view import (
    Ellipsis as DiffEllipsis,
)

from diff_tree_view.config import UISettings
from diff_tree_view.models import Change, FileChange, FileSides
from diff_tree_view.theme import TreeThemeTokens

Opcode = tuple[str, int, int, int, int]

# `HighlightTheme.STYLES` is overridden per-theme in
# `TransparentDiffView.__init__`. We also clear the default `underline` attr
# on function-name tokens at import time so they never render with a stray
# link/error underline even before the first DiffView is constructed.
HighlightTheme.STYLES[Token.Name.Function] = "$text-warning"
HighlightTheme.STYLES[Token.Name.Function.Magic] = "$text-warning"


class ExpandableEllipsis(Static):
    """Clickable `⋮` row that, when activated, expands the hidden equal lines.

    Upstream renders a non-selectable `Ellipsis` between grouped opcodes. We
    replace it with this widget so the user can click the marker and reveal
    the unchanged lines that `SequenceMatcher.get_grouped_opcodes` trimmed
    (default: lines more than 3 away from any change).
    """

    ALLOW_SELECT = False
    DEFAULT_CSS = """
    ExpandableEllipsis {
        text-align: center;
        width: 1fr;
        color: $foreground;
        text-style: bold;
    }
    ExpandableEllipsis:hover {
        color: $accent;
        text-style: bold;
    }
    """

    class Activated(Message):
        """Posted when the user clicks an `ExpandableEllipsis` to expand a gap."""

        def __init__(self, gap_index: int) -> None:
            super().__init__()
            self.gap_index = gap_index

    def __init__(self, gap_index: int, hidden_lines: int, *, background: str) -> None:
        label = f"⋮  (hidden {hidden_lines} line{'s' if hidden_lines != 1 else ''})"
        super().__init__(label)
        self.gap_index = gap_index
        # Themed muted-blue row that visually separates the "hidden" marker from
        # neighbouring hunks. We apply it inline rather than in DEFAULT_CSS so
        # each theme (dark / light) can ship its own hex via `TreeThemeTokens`.
        self.styles.background = background

    async def on_click(self, event: events.Click) -> None:
        event.stop()
        self.post_message(self.Activated(self.gap_index))


class _BlankFilledLineContent(LineContent):
    """LineContent that pads missing rows with blanks instead of `╲` hatches.

    Upstream's `LineContent.render_strips` renders each `None` entry in
    `code_lines` as `╲╲╲╲...` across the full width. That hatch reads as noise
    in a review tool — especially in split view where large insertion-only
    hunks leave an entire panel solid with diagonal strokes. Substituting the
    Nones before render makes the opposite side render as blank space.
    """

    def __init__(
        self,
        code_lines: list[Content | None],
        line_styles: list[str],
        width: int | None = None,
    ) -> None:
        cleaned: list[Content | None] = [Content("") if line is None else line for line in code_lines]
        super().__init__(cleaned, line_styles, width)


class _BlankFilledFoldedLineContent(FoldedLineContent):
    """Wrap-mode counterpart to `_BlankFilledLineContent`.

    `FoldedLineContent.render_strips` hatches `None` code lines with `╲` too
    (the wrap-view sibling of the bug above). Replace them with empty content
    before delegating, so the missing-line column renders blank in wrap mode.
    """

    def __init__(
        self,
        annotations: list[Content],
        continuations: list[Content],
        code_lines: list[Content | None],
        line_styles: list[str],
        code_lengths: list[int] | None = None,
    ) -> None:
        cleaned: list[Content | None] = [Content("") if line is None else line for line in code_lines]
        super().__init__(annotations, continuations, cleaned, line_styles, code_lengths)


class TransparentDiffView(DiffView):
    """DiffView subclass tuned for `textual-ansi` + a klaude-code-inspired palette.

    Three things it does differently from upstream:

    1. Anchors unchanged-row styles to `ansi_default` so Rich emits `[49m`
       instead of the `#000000` fallback that `rgba(0,0,0,0)` flattens to.
    2. Pulls muted diff hex colors from the active `TreeThemeTokens` so
       dark/light themes each get their own palette.
    3. Suppresses upstream's `📄 path (+N, -M)` title (DiffPanel renders its
       own header) and replaces the diagonal-hatched "missing line" markers
       in split view with blank space.
    """

    _expanded_gaps: reactive[frozenset[int]] = reactive(frozenset(), recompose=True)
    """Set of original gap indices the user has clicked to expand.

    A gap index `k` refers to the gap between `grouped_opcodes[k]` and
    `grouped_opcodes[k + 1]`. `recompose=True` so assigning a new frozenset
    remounts the full view with the hidden lines spliced back in.
    """

    def __init__(self, *args: Any, theme: TreeThemeTokens, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Apply the theme's full syntax palette. Textual's default
        # `HighlightTheme` routes every pygments token through generic
        # theme variables (`$text-primary`, `$text-success`, ...), which
        # under the `textual-ansi` app theme flatten to a muted 50%-sat
        # ANSI palette that reads as low-contrast on the diff-add/remove
        # backgrounds. Overwriting STYLES here replaces those variables
        # with explicit hex values from the active `SyntaxPalette`.
        # `HighlightTheme.STYLES` is global state; only one TreeTheme is
        # active at a time so the overwrite is safe.
        syntax = theme.syntax
        HighlightTheme.STYLES[Token.Name] = syntax.identifier
        HighlightTheme.STYLES[Token.Name.Variable] = syntax.variable
        HighlightTheme.STYLES[Token.Name.Function] = syntax.function
        HighlightTheme.STYLES[Token.Name.Function.Magic] = syntax.function
        HighlightTheme.STYLES[Token.Name.Class] = f"{syntax.class_name} bold"
        HighlightTheme.STYLES[Token.Name.Builtin] = syntax.builtin
        HighlightTheme.STYLES[Token.Name.Builtin.Pseudo] = f"{syntax.builtin} italic"
        HighlightTheme.STYLES[Token.Name.Decorator] = f"{syntax.decorator} bold"
        HighlightTheme.STYLES[Token.Name.Tag] = syntax.tag
        HighlightTheme.STYLES[Token.Name.Attribute] = syntax.attribute
        HighlightTheme.STYLES[Token.Name.Constant] = syntax.constant
        HighlightTheme.STYLES[Token.Keyword] = syntax.keyword
        HighlightTheme.STYLES[Token.Keyword.Namespace] = syntax.keyword_namespace
        HighlightTheme.STYLES[Token.Keyword.Constant] = f"bold {syntax.keyword_constant}"
        HighlightTheme.STYLES[Token.Keyword.Type] = f"{syntax.keyword} bold"
        HighlightTheme.STYLES[Token.Literal.String] = syntax.string
        HighlightTheme.STYLES[Token.Literal.String.Double] = syntax.string
        HighlightTheme.STYLES[Token.Literal.String.Single] = syntax.string
        HighlightTheme.STYLES[Token.Literal.String.Doc] = f"{syntax.comment} italic"
        HighlightTheme.STYLES[Token.Literal.String.Backtick] = syntax.string
        HighlightTheme.STYLES[Token.Literal.Number] = syntax.number
        HighlightTheme.STYLES[Token.Comment] = f"{syntax.comment} italic"
        HighlightTheme.STYLES[Token.Operator] = syntax.operator
        HighlightTheme.STYLES[Token.Operator.Word] = f"bold {syntax.operator_word}"
        self._diff_add_char_bg = theme.diff_add_char_bg
        self._diff_remove_char_bg = theme.diff_remove_char_bg
        # Reuse the same muted blue that ChangeTree uses for change-group rows,
        # so the "hidden N lines" marker reads as a row separator rather than
        # as styled content.
        self._ellipsis_bg = theme.change_row_bg
        # Shadow upstream's class-level dicts with theme-derived instance dicts.
        # The unchanged-row gutter uses the tree's `guides` color explicitly —
        # under `textual-ansi`, `$foreground 30%` / `$foreground 10%` flatten
        # to near-black, which reads as a hard line in light themes.
        self.NUMBER_STYLES = {
            "+": f"{theme.diff_add_text} on {theme.diff_add_char_bg}",
            "-": f"{theme.diff_remove_text} on {theme.diff_remove_char_bg}",
            " ": f"{theme.guides} on ansi_default",
        }
        self.EDGE_STYLES = {
            "+": f"{theme.diff_add_text} on {theme.diff_add_char_bg}",
            "-": f"{theme.diff_remove_text} on {theme.diff_remove_char_bg}",
            " ": f"{theme.guides} on ansi_default",
        }
        self.LINE_STYLES = {
            "+": f"on {theme.diff_add_bg}",
            "-": f"on {theme.diff_remove_bg}",
            " ": "on ansi_default",
            "/": "on ansi_default",
        }

    def compose(self) -> ComposeResult:
        # Skip upstream's `Static(self.get_title(), classes="title")` — the
        # surrounding DiffPanel already renders a richer header row, so the
        # built-in "📄 path (+N, -M)" would just duplicate it.
        if self.split:
            yield from self._compose_split_clean()
        else:
            yield from self._compose_unified_clean()

    async def on_mount(self) -> None:
        # Upstream's on_mount just checks auto-split; keep that, then link
        # every hunk's horizontal scroll container into one cycle so
        # horizontal scroll moves every hunk together (otherwise each
        # DiffScrollContainer scrolls independently and the file appears to
        # "tear" between hunks when the user scrolls right).
        self._check_auto_split(self.size.width)
        self.call_after_refresh(self._link_horizontal_scroll)

    def watch_split(self, old: bool, new: bool) -> None:
        # `split` is `recompose=True`, so toggling it remounts every child.
        # The newly mounted containers need to rejoin the scroll cycle.
        self.call_after_refresh(self._link_horizontal_scroll)

    def watch_wrap(self, old: bool, new: bool) -> None:
        self.call_after_refresh(self._link_horizontal_scroll)

    def watch__expanded_gaps(self, old: frozenset[int], new: frozenset[int]) -> None:
        # `_expanded_gaps` has `recompose=True`, so assigning triggers a full
        # remount. Re-link the scroll cycle once the new containers exist.
        self.call_after_refresh(self._link_horizontal_scroll)

    def on_expandable_ellipsis_activated(self, message: ExpandableEllipsis.Activated) -> None:
        message.stop()
        self._expanded_gaps = self._expanded_gaps | {message.gap_index}

    def _effective_groups(
        self,
    ) -> tuple[
        list[list[Opcode]],
        tuple[int, int] | None,
        list[tuple[int, int]],
        tuple[int, int] | None,
    ]:
        """Merge `grouped_opcodes` at every expanded gap and report hidden regions.

        Returns:
            `(groups, leading_gap, middle_gaps, trailing_gap)` where each gap
            value is `(gap_index, hidden_line_count)`.

            `gap_index` semantics:
            - `-1`: hidden region before the first emitted hunk
            - `0..N-2`: hidden regions between grouped hunks (same as before)
            - `N-1`: hidden region after the last emitted hunk
        """
        base = self.grouped_opcodes
        expanded = self._expanded_gaps
        if not base:
            return [], None, [], None

        lines_a, lines_b = self.highlighted_code_lines
        leading_gap: tuple[int, int] | None = None
        trailing_gap: tuple[int, int] | None = None

        groups: list[list[Opcode]] = [list(base[0])]
        middle_gaps: list[tuple[int, int]] = []

        first_head = base[0][0]
        leading_hidden = max(first_head[1], first_head[3])
        if leading_hidden > 0:
            leading_index = -1
            if leading_index in expanded:
                leading_opcode: Opcode = ("equal", 0, first_head[1], 0, first_head[3])
                groups[0].insert(0, leading_opcode)
            else:
                leading_gap = (leading_index, leading_hidden)

        for idx in range(1, len(base)):
            prev_tail = groups[-1][-1]
            next_head = base[idx][0]
            # The hidden equal region between the two hunks. `get_grouped_opcodes`
            # never emits touching groups, so (i2 < i1') and (j2 < j1') both hold.
            i_start, i_end = prev_tail[2], next_head[1]
            j_start, j_end = prev_tail[4], next_head[3]
            hidden = max(i_end - i_start, j_end - j_start)
            if (idx - 1) in expanded:
                gap_opcode: Opcode = ("equal", i_start, i_end, j_start, j_end)
                groups[-1].append(gap_opcode)
                groups[-1].extend(base[idx])
            else:
                middle_gaps.append((idx - 1, hidden))
                groups.append(list(base[idx]))

        last_tail = base[-1][-1]
        trailing_hidden = max(len(lines_a) - last_tail[2], len(lines_b) - last_tail[4])
        if trailing_hidden > 0:
            trailing_index = len(base) - 1
            if trailing_index in expanded:
                trailing_opcode: Opcode = (
                    "equal",
                    last_tail[2],
                    len(lines_a),
                    last_tail[4],
                    len(lines_b),
                )
                groups[-1].append(trailing_opcode)
            else:
                trailing_gap = (trailing_index, trailing_hidden)

        return groups, leading_gap, middle_gaps, trailing_gap

    def _link_horizontal_scroll(self) -> None:
        containers = list(self.query(DiffScrollContainer))
        if len(containers) < 2:
            # Single container (or none): nothing to sync; also clear any
            # stale link so the view doesn't reference a removed peer.
            for container in containers:
                container.scroll_link = None
            return
        # Chain A→B→C→…→A. When any one scrolls, Textual's reactive
        # change-detection drops the cycle the moment values converge.
        rotated = [*containers[1:], containers[0]]
        for current, nxt in zip(containers, rotated, strict=True):
            current.scroll_link = nxt

    def _highlight_diff_lines(
        self, lines_a: list[Content], lines_b: list[Content]
    ) -> tuple[list[Content], list[Content]]:
        # Shadows upstream's classmethod with an instance method so we can pull
        # char-level highlight colors from the theme attached in __init__.
        code_a = Content("\n").join(content for content in lines_a)
        code_b = Content("\n").join(content for content in lines_b)
        sequence_matcher = difflib.SequenceMatcher(
            lambda character: character in {" ", "\t"},
            code_a.plain,
            code_b.plain,
            autojunk=True,
        )
        spans_a: list[Span] = []
        spans_b: list[Span] = []
        for tag, i1, i2, j1, j2 in sequence_matcher.get_opcodes():
            if tag in {"delete", "replace"}:
                spans_a.append(Span(i1, i2, f"on {self._diff_remove_char_bg}"))
            if tag in {"insert", "replace"}:
                spans_b.append(Span(j1, j2, f"on {self._diff_add_char_bg}"))
        diffed_lines_a = code_a.add_spans(spans_a).split("\n")
        diffed_lines_b = code_b.add_spans(spans_b).split("\n")
        return diffed_lines_a, diffed_lines_b

    def _compose_split_clean(self) -> ComposeResult:
        # Mirror of upstream `_compose_split` (no-wrap branch) with four edits:
        # blank rather than `╲` hatches, `_BlankFilledLineContent` for missing
        # rows, no manual per-group `scroll_link` (cycle-linked in on_mount),
        # and a **file-wide** `line_width` — upstream computes it per hunk,
        # which gives each hunk its own max scroll_x, so short hunks stop
        # tracking the cursor when the user scrolls a long hunk past their
        # own content. Sharing one width across the whole file keeps every
        # hunk's horizontal offset aligned.
        # Wrapping mode is handled by `_compose_split_wrap_clean`, which is
        # our hatch-free mirror of upstream's `_compose_split_wrap`.
        if self.wrap:
            yield from self._compose_split_wrap_clean()
            return

        lines_a, lines_b = self.highlighted_code_lines

        all_lines = [line for line in lines_a + lines_b if line is not None]
        global_line_width = max((line.cell_length for line in all_lines), default=1)
        # Unify line-number column width across hunks too — otherwise a hunk
        # whose max line number is 3 digits (e.g. 100–109) gives its gutter
        # more columns than a hunk with single-digit numbers, which in turn
        # leaves that hunk's DiffScrollContainer with a narrower viewport and
        # a different `max_scroll_x`. When scroll propagates through the
        # cycle, short-gutter hunks clamp at a smaller offset and drag the
        # whole file back to their limit.
        max_line_no = max(len(lines_a), len(lines_b))
        global_line_number_width = len(str(max_line_no)) if max_line_no else 1

        annotation_hatch = Content(" " * 3)
        annotation_blank = Content(" " * 3)

        def make_annotation(annotation: str, highlight_annotation: str) -> Content:
            if not self.annotations:
                return Content(" ").stylize(self.LINE_STYLES[annotation])
            if annotation == highlight_annotation:
                return (
                    Content(f" {annotation} ")
                    .stylize(self.LINE_STYLES[annotation])
                    .stylize(self.ANNOTATION_STYLES.get(annotation, ""))
                )
            if annotation == "/":
                return annotation_hatch
            return annotation_blank

        groups, leading_gap, gaps, trailing_gap = self._effective_groups()
        if leading_gap is not None:
            gap_index, hidden = leading_gap
            with containers.HorizontalGroup():
                yield ExpandableEllipsis(gap_index, hidden, background=self._ellipsis_bg)
                yield ExpandableEllipsis(gap_index, hidden, background=self._ellipsis_bg)

        for group_index, (last, group) in enumerate(loop_last(groups)):
            line_numbers_a: list[int | None] = []
            line_numbers_b: list[int | None] = []
            annotations_a: list[str] = []
            annotations_b: list[str] = []
            code_lines_a: list[Content | None] = []
            code_lines_b: list[Content | None] = []
            for tag, i1, i2, j1, j2 in group:
                if tag == "equal":
                    for line_offset, line in enumerate(lines_a[i1:i2], 1):
                        annotations_a.append(" ")
                        annotations_b.append(" ")
                        line_numbers_a.append(i1 + line_offset)
                        line_numbers_b.append(j1 + line_offset)
                        code_lines_a.append(line)
                        code_lines_b.append(line)
                else:
                    if tag in {"delete", "replace"}:
                        for line_number, line in enumerate(lines_a[i1:i2], i1 + 1):
                            annotations_a.append("-")
                            line_numbers_a.append(line_number)
                            code_lines_a.append(line)
                    if tag in {"insert", "replace"}:
                        for line_number, line in enumerate(lines_b[j1:j2], j1 + 1):
                            annotations_b.append("+")
                            line_numbers_b.append(line_number)
                            code_lines_b.append(line)
                    fill_lists(code_lines_a, code_lines_b, None)
                    fill_lists(annotations_a, annotations_b, "/")
                    fill_lists(line_numbers_a, line_numbers_b, None)

            line_number_width = global_line_number_width

            hatch = Content(" " * (2 + line_number_width))

            def format_number(
                line_no: int | None,
                annotation: str,
                _width: int = line_number_width,
                _hatch: Content = hatch,
            ) -> Content:
                return (
                    _hatch
                    if line_no is None
                    else Content(f"▎{line_no:>{_width}} ")
                    .stylize(self.NUMBER_STYLES[annotation], 1)
                    .stylize(self.EDGE_STYLES[annotation], 0, 1)
                )

            with containers.HorizontalGroup(classes="diff-group"):
                yield LineAnnotations(map(format_number, line_numbers_a, annotations_a))
                yield LineAnnotations([make_annotation(annotation, "-") for annotation in annotations_a])

                code_line_styles = [self.LINE_STYLES[annotation] for annotation in annotations_a]
                with DiffScrollContainer():
                    yield DiffCode(_BlankFilledLineContent(code_lines_a, code_line_styles, width=global_line_width))

                yield LineAnnotations(map(format_number, line_numbers_b, annotations_b))
                yield LineAnnotations([make_annotation(annotation, "+") for annotation in annotations_b])

                code_line_styles = [self.LINE_STYLES[annotation] for annotation in annotations_b]
                with DiffScrollContainer():
                    yield DiffCode(_BlankFilledLineContent(code_lines_b, code_line_styles, width=global_line_width))
                # scroll_link intentionally left as default (None) — the
                # TransparentDiffView cycles all containers in on_mount.

            if not last:
                gap_index, hidden = gaps[group_index]
                with containers.HorizontalGroup():
                    yield ExpandableEllipsis(gap_index, hidden, background=self._ellipsis_bg)
                    yield ExpandableEllipsis(gap_index, hidden, background=self._ellipsis_bg)

        if trailing_gap is not None:
            gap_index, hidden = trailing_gap
            with containers.HorizontalGroup():
                yield ExpandableEllipsis(gap_index, hidden, background=self._ellipsis_bg)
                yield ExpandableEllipsis(gap_index, hidden, background=self._ellipsis_bg)

    def _compose_split_wrap_clean(self) -> ComposeResult:
        # Mirror of upstream `_compose_split_wrap` that swaps the two `╲`
        # hatches (annotation column + line-number gutter) for blanks and
        # replaces `FoldedLineContent` with `_BlankFilledFoldedLineContent`
        # so missing code rows also render blank. Everything else follows
        # upstream verbatim.
        lines_a, lines_b = self.highlighted_code_lines

        annotation_hatch = Content(" " * 3)
        annotation_blank = Content(" " * 3)

        def make_annotation(annotation: str, highlight_annotation: str) -> Content:
            if not self.annotations:
                return (
                    Content.blank(1)
                    .stylize(self.LINE_STYLES[annotation])
                    .stylize(self.ANNOTATION_STYLES.get(annotation, ""))
                )
            if annotation == highlight_annotation:
                return (
                    Content(f" {annotation} ")
                    .stylize(self.LINE_STYLES[annotation])
                    .stylize(self.ANNOTATION_STYLES.get(annotation, ""))
                )
            if annotation == "/":
                return annotation_hatch
            return annotation_blank

        for last, group in loop_last(self.grouped_opcodes):
            line_numbers_a: list[int | None] = []
            line_numbers_b: list[int | None] = []
            annotations_a: list[str] = []
            annotations_b: list[str] = []
            code_lines_a: list[Content | None] = []
            code_lines_b: list[Content | None] = []
            for tag, i1, i2, j1, j2 in group:
                if tag == "equal":
                    for line_offset, line in enumerate(lines_a[i1:i2], 1):
                        annotations_a.append(" ")
                        annotations_b.append(" ")
                        line_numbers_a.append(i1 + line_offset)
                        line_numbers_b.append(j1 + line_offset)
                        code_lines_a.append(line)
                        code_lines_b.append(line)
                else:
                    if tag in {"delete", "replace"}:
                        for line_number, line in enumerate(lines_a[i1:i2], i1 + 1):
                            annotations_a.append("-")
                            line_numbers_a.append(line_number)
                            code_lines_a.append(line)
                    if tag in {"insert", "replace"}:
                        for line_number, line in enumerate(lines_b[j1:j2], j1 + 1):
                            annotations_b.append("+")
                            line_numbers_b.append(line_number)
                            code_lines_b.append(line)
                    fill_lists(code_lines_a, code_lines_b, None)
                    fill_lists(annotations_a, annotations_b, "/")
                    fill_lists(line_numbers_a, line_numbers_b, None)

            if line_numbers_a or line_numbers_b:
                line_number_width = max(
                    0 if line_no is None else len(str(line_no)) for line_no in (line_numbers_a + line_numbers_b)
                )
            else:
                line_number_width = 1

            hatch = Content(" " * (2 + line_number_width))

            def format_number(
                line_no: int | None,
                annotation: str,
                _width: int = line_number_width,
                _hatch: Content = hatch,
            ) -> Content:
                return (
                    _hatch
                    if line_no is None
                    else Content(f"▎{line_no:>{_width}} ")
                    .stylize(self.NUMBER_STYLES[annotation], 1)
                    .stylize(self.EDGE_STYLES[annotation], 0, 1)
                )

            code_lengths = [
                max(
                    0 if line_a is None else line_a.cell_length,
                    0 if line_b is None else line_b.cell_length,
                )
                for line_a, line_b in zip(code_lines_a, code_lines_b, strict=True)
            ]

            with containers.HorizontalGroup(classes="diff-group"):
                annotations = [
                    Content.assemble(
                        format_number(line_number, annotation),
                        make_annotation(annotation, "-"),
                    )
                    for line_number, annotation in zip(line_numbers_a, annotations_a, strict=True)
                ]
                continuations = self._make_continuations(line_number_width + 2)
                code_line_styles = [self.LINE_STYLES[annotation] for annotation in annotations_a]

                with DiffScrollContainer():
                    yield DiffCode(
                        _BlankFilledFoldedLineContent(
                            annotations,
                            [continuations[annotate] for annotate in annotations_a],
                            code_lines_a,
                            code_line_styles,
                            code_lengths=code_lengths,
                        )
                    )

                annotations = [
                    Content.assemble(
                        format_number(line_number, annotation),
                        make_annotation(annotation, "+"),
                    )
                    for line_number, annotation in zip(line_numbers_b, annotations_b, strict=True)
                ]
                code_line_styles = [self.LINE_STYLES[annotation] for annotation in annotations_b]

                with DiffScrollContainer():
                    yield DiffCode(
                        _BlankFilledFoldedLineContent(
                            annotations,
                            [continuations[annotate] for annotate in annotations_b],
                            code_lines_b,
                            code_line_styles,
                            code_lengths=code_lengths,
                        )
                    )

            if not last:
                with containers.HorizontalGroup():
                    yield DiffEllipsis("⋮")
                    yield DiffEllipsis("⋮")

    def _compose_unified_clean(self) -> ComposeResult:
        # Mirror of upstream `_compose_unified` (no-wrap) using the same
        # file-wide `line_width` and `line_number_width` we use in split, so
        # every hunk's `DiffScrollContainer` has identical viewport width
        # and `max_scroll_x`. Without this the narrow-mode (unified) view
        # still has the per-hunk clamp bug the user hit.
        if self.wrap:
            yield from self._compose_unified_wrap()
            return

        lines_a, lines_b = self.highlighted_code_lines
        all_lines = [line for line in lines_a + lines_b if line is not None]
        global_line_width = max((line.cell_length for line in all_lines), default=1)
        max_line_no = max(len(lines_a), len(lines_b))
        line_number_width = len(str(max_line_no)) if max_line_no else 1

        groups, leading_gap, gaps, trailing_gap = self._effective_groups()
        if leading_gap is not None:
            gap_index, hidden = leading_gap
            yield ExpandableEllipsis(gap_index, hidden, background=self._ellipsis_bg)

        for group_index, (last, group) in enumerate(loop_last(groups)):
            line_numbers_a: list[int | None] = []
            line_numbers_b: list[int | None] = []
            annotations: list[str] = []
            code_lines: list[Content | None] = []
            for tag, i1, i2, j1, j2 in group:
                if tag == "equal":
                    for line_offset, line in enumerate(lines_a[i1:i2], 1):
                        annotations.append(" ")
                        line_numbers_a.append(i1 + line_offset)
                        line_numbers_b.append(j1 + line_offset)
                        code_lines.append(line)
                    continue
                if tag in {"delete", "replace"}:
                    for line_offset, line in enumerate(lines_a[i1:i2], 1):
                        annotations.append("-")
                        line_numbers_a.append(i1 + line_offset)
                        line_numbers_b.append(None)
                        code_lines.append(line)
                if tag in {"insert", "replace"}:
                    for line_offset, line in enumerate(lines_b[j1:j2], 1):
                        annotations.append("+")
                        line_numbers_a.append(None)
                        line_numbers_b.append(j1 + line_offset)
                        code_lines.append(line)

            with containers.HorizontalGroup(classes="diff-group"):
                yield LineAnnotations(
                    [
                        (
                            Content(f"▎{' ' * line_number_width} ")
                            if line_no is None
                            else Content(f"▎{line_no:>{line_number_width}} ")
                        )
                        .stylize(self.NUMBER_STYLES[annotation], 1)
                        .stylize(self.EDGE_STYLES[annotation], 0, 1)
                        for line_no, annotation in zip(line_numbers_a, annotations, strict=True)
                    ]
                )
                yield LineAnnotations(
                    [
                        (
                            Content(f" {' ' * line_number_width} ")
                            if line_no is None
                            else Content(f" {line_no:>{line_number_width}} ")
                        ).stylize(self.NUMBER_STYLES[annotation])
                        for line_no, annotation in zip(line_numbers_b, annotations, strict=True)
                    ]
                )

                if self.annotations:
                    yield LineAnnotations(
                        [
                            Content(f" {annotation} ")
                            .stylize(self.LINE_STYLES[annotation])
                            .stylize(self.ANNOTATION_STYLES[annotation])
                            for annotation in annotations
                        ]
                    )
                else:
                    blank = Content.blank(1)
                    yield LineAnnotations(
                        [
                            blank.stylize(self.LINE_STYLES[annotation]).stylize(self.ANNOTATION_STYLES[annotation])
                            for annotation in annotations
                        ]
                    )

                code_line_styles = [self.LINE_STYLES[annotation] for annotation in annotations]
                with DiffScrollContainer():
                    yield DiffCode(_BlankFilledLineContent(code_lines, code_line_styles, width=global_line_width))

            if not last:
                gap_index, hidden = gaps[group_index]
                yield ExpandableEllipsis(gap_index, hidden, background=self._ellipsis_bg)

        if trailing_gap is not None:
            gap_index, hidden = trailing_gap
            yield ExpandableEllipsis(gap_index, hidden, background=self._ellipsis_bg)


class DiffHeader(Static):
    def __init__(self, *, ui: UISettings, id: str | None = None) -> None:
        super().__init__(id=id)
        self._ui = ui
        self._text: Text = Text()

    def set_text(self, text: Text) -> None:
        self._text = text
        self.refresh()

    def render(self) -> Text:
        return self._text

    def render_line(self, y: int) -> Strip:
        if y != 0:
            return Strip.blank(self.size.width, Style())
        segments = list(self._text.render(self.app.console))
        segments = line_pad(segments, 0, max(0, self.size.width - self._text.cell_len), Style())
        return Strip(segments)


NARROW_PANEL_WIDTH = 80
"""When the diff panel is narrower than this, force unified view regardless of
the user's toggle preference — a split view gets unusable below ~80 columns
(each half has <40 columns of actual code and wraps into a mess)."""


class DiffPanel(Vertical):
    """Display the diff for the file currently selected in the tree."""

    def __init__(self, *, ui: UISettings | None = None, id: str | None = None) -> None:
        super().__init__(id=id)
        self._ui = ui or UISettings()
        self._current_key: tuple[str, str] | None = None
        # `_user_split` is what the `m` toggle flips. Effective split view is
        # `_user_split AND viewport-wide-enough`; that way narrow windows auto-
        # unify but a later resize restores the user's preference.
        self._user_split = True
        self._wrap = False
        self._header: DiffHeader | None = None
        self._body: VerticalScroll | None = None

    @property
    def _effective_split(self) -> bool:
        return self._user_split and self.size.width >= NARROW_PANEL_WIDTH

    def compose(self):
        self._header = DiffHeader(ui=self._ui, id="diff-header")
        self._body = VerticalScroll(id="diff-body")
        yield self._header
        yield self._body

    def on_mount(self) -> None:
        assert self._body is not None
        scrollbar_color = self._ui.resolved_tree_theme.directory
        self._body.styles.scrollbar_color = scrollbar_color
        self._body.styles.scrollbar_color_hover = scrollbar_color
        self._body.styles.scrollbar_color_active = scrollbar_color
        # Tint the rounded panel frame with the theme's faint `panel_border`.
        # See ChangeTree.on_mount for why we set this inline instead of in CSS.
        border_color = self._ui.resolved_tree_theme.panel_border
        for edge in ("border_top", "border_right", "border_bottom", "border_left"):
            setattr(self.styles, edge, ("round", border_color))
        self._body.mount(Static("Select a file to view its diff", classes="diff-placeholder diff-empty"))

    def on_resize(self) -> None:
        # Re-evaluate split/unified whenever the panel resizes across the 80-col
        # threshold. Avoid unnecessary reactive thrash by only assigning when
        # the value would actually change.
        effective = self._effective_split
        for view in self.query(DiffView):
            if view.split != effective:
                view.split = effective

    async def show_file(self, change: Change, file: FileChange, sides: FileSides) -> None:
        assert self._header is not None
        assert self._body is not None
        key = (change.change_id, file.path)
        self._header.set_text(self._format_header(change, file))
        if sides.binary:
            widget = Static("[binary file — not shown]", classes="diff-placeholder")
        else:
            widget = TransparentDiffView(
                path_original=file.old_path or file.path,
                path_modified=file.path,
                code_original=sides.before,
                code_modified=sides.after,
                split=self._effective_split,
                wrap=self._wrap,
                theme=self._ui.resolved_tree_theme,
            )
        await self._replace_body_content(widget)
        self._current_key = key

    async def clear_file(self) -> None:
        assert self._header is not None
        assert self._body is not None
        self._header.set_text(Text())
        await self._replace_body_content(
            Static("Select a file to view its diff", classes="diff-placeholder diff-empty")
        )
        self._current_key = None

    async def _replace_body_content(self, widget: Static | TransparentDiffView) -> None:
        assert self._body is not None
        old_children = list(self._body.children)
        await self._body.mount(widget)
        for child in old_children:
            await child.remove()

    def toggle_split(self) -> None:
        self._user_split = not self._user_split
        effective = self._effective_split
        for view in self.query(DiffView):
            view.split = effective

    def toggle_wrap(self) -> None:
        self._wrap = not self._wrap
        for view in self.query(DiffView):
            view.wrap = self._wrap

    def _format_header(self, change: Change, file: FileChange) -> Text:
        theme = self._ui.resolved_tree_theme
        text = Text()
        text.append(" ", style=theme.guides)
        text.append(file.path, style=theme.file)
        text.append("  ")
        text.append(file.status, style=self._status_style(file.status))
        stats = file.stats
        if stats.added or stats.removed:
            text.append("  ")
            text.append("(", style=theme.guides)
            if stats.added:
                text.append(f"+{stats.added}", style=theme.diff_add)
            if stats.added and stats.removed:
                text.append(",", style=theme.guides)
            if stats.removed:
                text.append(f"-{stats.removed}", style=theme.diff_remove)
            text.append(")", style=theme.guides)
        if change.short_id:
            text.append("   ")
            text.append(change.short_id, style=theme.change_id)
        return text

    def _status_style(self, status: str) -> str:
        theme = self._ui.resolved_tree_theme
        return {
            "A": theme.status_added,
            "D": theme.status_deleted,
            "R": theme.status_renamed,
            "M": theme.status_modified,
        }.get(status, "default")
