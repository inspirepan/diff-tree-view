from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from diff_tree_view.theme import BuiltinTreeThemeName, TreeThemeTokens, get_builtin_tree_theme


class TreeDisclosureStyle(StrEnum):
    BRACKETS = "brackets"
    TRIANGLES = "triangles"


@dataclass(frozen=True, slots=True)
class UISettings:
    transparent_background: bool = True
    collapse_single_child_directories: bool = True
    tree_disclosure_style: TreeDisclosureStyle = TreeDisclosureStyle.BRACKETS
    tree_theme_name: BuiltinTreeThemeName = BuiltinTreeThemeName.DARK
    tree_theme: TreeThemeTokens | None = None

    @property
    def resolved_tree_theme(self) -> TreeThemeTokens:
        if self.tree_theme is not None:
            return self.tree_theme
        return get_builtin_tree_theme(self.tree_theme_name)
