from __future__ import annotations

from diff_tree_view.config import TreeDisclosureStyle, UISettings
from diff_tree_view.theme import DARK_TREE_TOKENS, BuiltinTreeThemeName


def test_ui_settings_defaults_use_dark_tree_tokens_and_bracket_disclosure() -> None:
    ui = UISettings()

    assert ui.transparent_background is True
    assert ui.tree_disclosure_style is TreeDisclosureStyle.BRACKETS
    assert ui.tree_theme_name is BuiltinTreeThemeName.DARK
    assert ui.resolved_tree_theme == DARK_TREE_TOKENS
