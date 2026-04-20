from __future__ import annotations

from rich.style import Style
from rich.text import Text
from textual._segment_tools import line_pad
from textual.strip import Strip
from textual.widgets import Static

from dff.config import UISettings
from dff.theme import BuiltinTreeThemeName


def _hint_palette(ui: UISettings) -> tuple[str, str, str]:
    if ui.tree_theme_name is BuiltinTreeThemeName.LIGHT:
        return ("#5f5fb7", "#667e90", "#93a4b1")
    return ("#9090cc", "#99aabb", "#778899")


class StatusBar(Static):
    def __init__(self, *, ui: UISettings | None = None, id: str | None = None) -> None:
        super().__init__(id=id)
        self._ui = ui or UISettings()

    def render(self) -> Text:
        text = Text()
        key_style, label_style, separator_style = _hint_palette(self._ui)
        hints = [
            ("↑/k", key_style, " up", label_style),
            ("↓/j", key_style, " down", label_style),
            ("enter/space", key_style, " toggle", label_style),
            ("q", key_style, " quit", label_style),
        ]
        text.append(" ")
        for index, (keys, key_style, label, label_style) in enumerate(hints):
            text.append(keys, style=key_style)
            text.append(label, style=label_style)
            if index < len(hints) - 1:
                text.append(" • ", style=separator_style)
        return text

    def render_line(self, y: int) -> Strip:
        if y != 0:
            return Strip.blank(self.size.width, Style())

        text = self.render()
        segments = list(text.render(self.app.console))
        segments = line_pad(segments, 0, max(0, self.size.width - text.cell_len), Style())
        return Strip(segments)
