from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


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


class BuiltinTreeThemeName(StrEnum):
    DARK = "dark"
    LIGHT = "light"


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
    cursor_background="#343a44",
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
    status_renamed="#b8860b",
    conflict="#b83838",
    guides="#93a4b1",
    change_graph_current="#b8860b",
    change_graph_default="#93a4b1",
    change_id="#101827",
    change_description="#667e90",
    cursor_background="#f0f1f7",
)


def get_builtin_tree_theme(name: BuiltinTreeThemeName) -> TreeThemeTokens:
    if name is BuiltinTreeThemeName.LIGHT:
        return LIGHT_TREE_TOKENS
    return DARK_TREE_TOKENS
