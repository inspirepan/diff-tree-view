from __future__ import annotations

from rich.color import Color

from dff.app import DffApp
from dff.config import UISettings
from dff.models import Change, FileChange, HunkStats
from dff.widgets import ChangeTree, StatusBar


async def test_dff_app_uses_textual_ansi_and_transparent_backgrounds() -> None:
    app = DffApp(
        [
            Change(
                change_id="demo",
                short_id="demo",
                description="Demo",
                files=(FileChange("demo.py", "M", HunkStats(1, 0)),),
            )
        ]
    )

    async with app.run_test() as pilot:
        await pilot.pause()
        tree = app.query_one(ChangeTree)

        assert app.theme == "textual-ansi"
        assert app.ansi_color is True
        assert app.styles.background.a == 0
        assert app.screen.styles.background.a == 0
        assert tree.styles.background.a == 0
        assert tree.region.width < app.screen.region.width
        assert tree.region.height < app.screen.region.height
        for name in [
            "tree--label",
            "tree--guides",
            "tree--guides-hover",
            "tree--guides-selected",
            "tree--highlight",
            "tree--highlight-line",
        ]:
            bgcolor = tree.get_component_rich_style(name, partial=False).bgcolor
            assert bgcolor is None or bgcolor.is_default

        cursor_style = tree.get_component_rich_style("tree--cursor", partial=False)
        assert cursor_style.bgcolor == Color.parse("#343a44")
        assert cursor_style.color in {None, Color.default()}


async def test_dff_app_renders_status_bar_hints() -> None:
    app = DffApp(
        [
            Change(
                change_id="demo",
                short_id="demo",
                description="Demo",
                files=(FileChange("demo.py", "M", HunkStats(1, 0)),),
            )
        ]
    )

    async with app.run_test() as pilot:
        await pilot.pause()
        status_bar = app.query_one(StatusBar)
        status_text = status_bar.render()

        assert "↑/k up" in status_text.plain
        assert "z wrap" in status_text.plain
        assert "q quit" in status_text.plain
        assert " • " in status_text.plain
        # Default run_test gives an 80x24 screen — DiffPanel is narrower than
        # NARROW_PANEL_WIDTH so split is auto-unified and `m` hint is hidden.
        assert "m split" not in status_text.plain


async def test_dff_app_global_q_binding_quits() -> None:
    app = DffApp(
        [
            Change(
                change_id="demo",
                short_id="demo",
                description="Demo",
                files=(FileChange("demo.py", "M", HunkStats(1, 0)),),
            )
        ]
    )

    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.is_running is True

        await pilot.press("q")
        await pilot.pause()

        assert app.is_running is False


async def test_dff_app_applies_opaque_mode_from_ui_settings() -> None:
    app = DffApp(
        [
            Change(
                change_id="demo",
                short_id="demo",
                description="Demo",
                files=(FileChange("demo.py", "M", HunkStats(1, 0)),),
            )
        ],
        ui=UISettings(transparent_background=False),
    )

    async with app.run_test() as pilot:
        await pilot.pause()
        tree = app.query_one(ChangeTree)

        assert app.styles.background.a != 0
        assert app.screen.styles.background.a != 0
        assert tree.styles.background.a != 0
