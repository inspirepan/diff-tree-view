from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class SyntaxPalette:
    """Per-theme pygments highlight palette.

    Textual's default `HighlightTheme` resolves every token through its
    generic theme variables (`$text-primary`, `$text-success`, ...). Under
    the `textual-ansi` app theme those variables flatten to a muted 50%-
    saturation ANSI palette that reads as low-contrast against both the
    diff-add (green) and diff-remove (red) row tints. Each `TreeThemeTokens`
    ships an explicit palette so dark/light panels can each pick colors
    that read well on their own backgrounds.

    Fields map 1:1 to pygments tokens applied in
    `TransparentDiffView.__init__`. Add more fields here if a token type
    needs per-theme control.
    """

    identifier: str  # Token.Name — plain identifiers
    keyword: str  # Token.Keyword — `if`, `class`, `def`, ...
    keyword_namespace: str  # Token.Keyword.Namespace — `import`, `from`
    keyword_constant: str  # Token.Keyword.Constant — `True`, `False`, `None`
    string: str  # Token.Literal.String (+ Double/Single/Doc subclasses)
    number: str  # Token.Literal.Number
    comment: str  # Token.Comment
    function: str  # Token.Name.Function (+ .Magic)
    class_name: str  # Token.Name.Class
    builtin: str  # Token.Name.Builtin
    decorator: str  # Token.Name.Decorator
    variable: str  # Token.Name.Variable
    tag: str  # Token.Name.Tag — CSS selectors, HTML/XML tags
    attribute: str  # Token.Name.Attribute — XML attrs, CSS properties
    operator: str  # Token.Operator
    operator_word: str  # Token.Operator.Word — `and`, `or`, `not`, `in`
    constant: str  # Token.Name.Constant


@dataclass(frozen=True, slots=True)
class TreeThemeTokens:
    disclosure: str
    directory: str
    file: str
    diff_add: str
    diff_remove: str
    status_added: str
    status_modified: str
    status_deleted: str
    status_renamed: str
    conflict: str
    guides: str
    change_graph_current: str
    change_graph_default: str
    change_id: str
    change_description: str
    cursor_background: str
    # Subtle background tint for the disclosure marker character (`+` / `-`)
    # in the change tree. Kept faint so the marker reads as a soft pill
    # rather than a reversed/inverted block.
    disclosure_bg: str
    # Diff-body palette (klaude-code dark/light). fg is the text color on the
    # corresponding bg; char_bg is the stronger shade used for line-number
    # gutters and intra-line char highlights.
    diff_add_bg: str
    diff_add_char_bg: str
    diff_add_text: str
    diff_remove_bg: str
    diff_remove_char_bg: str
    diff_remove_text: str
    # Background highlight for the change-group rows in ChangeTree. Borrowed
    # from klaude-code's `blue_sub_background` — faint blue that distinguishes
    # group headers from the file rows beneath them.
    change_row_bg: str
    # Color of the rounded panel borders wrapping ChangeTree and DiffPanel.
    # Kept much fainter than `guides` so the frame reads as a subtle outline
    # rather than a hard divider.
    panel_border: str
    # Full syntax-highlight palette applied to the diff body.
    syntax: SyntaxPalette


class BuiltinTreeThemeName(StrEnum):
    DARK = "dark"
    LIGHT = "light"


# One Dark / Atom-inspired palette. Balanced on the dark red/green diff tints.
DARK_SYNTAX = SyntaxPalette(
    identifier="#d4d4d4",
    keyword="#c678dd",
    keyword_namespace="#c678dd",
    keyword_constant="#4169e1",
    string="#98c379",
    number="#d19a66",
    comment="#7f848e",
    function="#61afef",
    class_name="#e5c07b",
    builtin="#56b6c2",
    decorator="#e5c07b",
    variable="#e06c75",
    tag="#56b6c2",
    attribute="#d19a66",
    operator="#56b6c2",
    operator_word="#c678dd",
    constant="#d19a66",
)


# One Light-inspired palette. Reads well on the faint pink/green diff tints.
LIGHT_SYNTAX = SyntaxPalette(
    identifier="#383a42",
    keyword="#a626a4",
    keyword_namespace="#a626a4",
    keyword_constant="#1d4ed8",
    string="#50a14f",
    number="#986801",
    comment="#a0a1a7",
    function="#4078f2",
    class_name="#c18401",
    builtin="#0184bc",
    decorator="#c18401",
    variable="#e45649",
    tag="#0184bc",
    attribute="#986801",
    operator="#0184bc",
    operator_word="#a626a4",
    constant="#986801",
)


DARK_TREE_TOKENS = TreeThemeTokens(
    disclosure="#99aabb",
    directory="#5b9fd4",
    file="#ffffff",
    diff_add="#4fb06c",
    diff_remove="#d75f5f",
    status_added="#4fb06c",
    status_modified="#4db8b8",
    status_deleted="#d75f5f",
    status_renamed="#e8b040",
    conflict="#d75f5f",
    guides="#778899",
    change_graph_current="#e8b040",
    change_graph_default="#778899",
    change_id="#ffffff",
    change_description="#99aabb",
    cursor_background="#545c6c",
    disclosure_bg="#6a7384",
    diff_add_bg="#2b4938",
    diff_add_char_bg="#3d7b52",
    diff_add_text="#c8e6c9",
    diff_remove_bg="#4d2f33",
    diff_remove_char_bg="#8a4a52",
    diff_remove_text="#ffcdd2",
    change_row_bg="#2c3846",
    panel_border="#3a4250",
    syntax=DARK_SYNTAX,
)


LIGHT_TREE_TOKENS = TreeThemeTokens(
    disclosure="#667e90",
    directory="#2d6ba8",
    file="#101827",
    diff_add="#00875f",
    diff_remove="#b83838",
    status_added="#00875f",
    status_modified="#2a9090",
    status_deleted="#b83838",
    status_renamed="#a17208",
    conflict="#b83838",
    guides="#93a4b1",
    change_graph_current="#a17208",
    change_graph_default="#93a4b1",
    change_id="#101827",
    change_description="#667e90",
    cursor_background="#c4ced4",
    disclosure_bg="#aeb8c2",
    diff_add_bg="#dafbe1",
    diff_add_char_bg="#aceebb",
    diff_add_text="#2e5a32",
    diff_remove_bg="#ffecec",
    diff_remove_char_bg="#ffcfcf",
    diff_remove_text="#82071e",
    change_row_bg="#ecf1f9",
    panel_border="#dde3ea",
    syntax=LIGHT_SYNTAX,
)


def get_builtin_tree_theme(name: BuiltinTreeThemeName) -> TreeThemeTokens:
    if name is BuiltinTreeThemeName.LIGHT:
        return LIGHT_TREE_TOKENS
    return DARK_TREE_TOKENS
