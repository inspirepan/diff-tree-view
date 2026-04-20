from __future__ import annotations

from diff_tree_view import terminal
from diff_tree_view.terminal import (
    _luminance_is_light,
    _parse_osc_color_response,
    _parse_rgb_spec,
    _scale_hex_component,
    detect_tree_theme_name,
)
from diff_tree_view.theme import BuiltinTreeThemeName


def test_parse_rgb_spec_accepts_xterm_16bit_form() -> None:
    assert _parse_rgb_spec("rgb:ffff/ffff/ffff") == (255, 255, 255)
    assert _parse_rgb_spec("rgb:0000/0000/0000") == (0, 0, 0)
    # ~middle grey, scaled from 16-bit to 8-bit.
    r, g, b = _parse_rgb_spec("rgb:8080/8080/8080") or (0, 0, 0)
    assert abs(r - 128) <= 1
    assert abs(g - 128) <= 1
    assert abs(b - 128) <= 1


def test_parse_rgb_spec_accepts_hex_triplet() -> None:
    assert _parse_rgb_spec("#ff8040") == (255, 128, 64)


def test_parse_rgb_spec_rejects_garbage() -> None:
    assert _parse_rgb_spec("not-a-color") is None
    assert _parse_rgb_spec("#xyzxyz") is None
    assert _parse_rgb_spec("rgb:abc") is None


def test_scale_hex_component_handles_variable_widths() -> None:
    assert _scale_hex_component("f") == 255
    assert _scale_hex_component("ff") == 255
    assert _scale_hex_component("ffff") == 255
    assert _scale_hex_component("0") == 0


def test_parse_osc_color_response_extracts_rgb_from_bel_terminated_reply() -> None:
    payload = b"\x1b]11;rgb:fafa/fafa/fafa\x07"
    assert _parse_osc_color_response(payload) == (250, 250, 250)


def test_parse_osc_color_response_handles_st_terminator_and_hex_form() -> None:
    payload = b"\x1b]11;#101010\x1b\\"
    assert _parse_osc_color_response(payload) == (16, 16, 16)


def test_parse_osc_color_response_returns_none_for_unrelated_bytes() -> None:
    assert _parse_osc_color_response(b"random\x07") is None


def test_luminance_is_light_matches_codex_rs_threshold() -> None:
    # Pure white is obviously light.
    assert _luminance_is_light((255, 255, 255)) is True
    # Pure black is obviously dark.
    assert _luminance_is_light((0, 0, 0)) is False
    # Deep navy stays on the dark side of the threshold.
    assert _luminance_is_light((10, 20, 40)) is False
    # Pastel mint lands on the light side.
    assert _luminance_is_light((200, 240, 210)) is True


def test_detect_tree_theme_name_picks_light_when_background_is_bright(monkeypatch) -> None:
    monkeypatch.setattr(terminal, "_query_color_slot", lambda slot, timeout: (240, 240, 240))
    assert detect_tree_theme_name() is BuiltinTreeThemeName.LIGHT


def test_detect_tree_theme_name_picks_dark_when_background_is_dim(monkeypatch) -> None:
    monkeypatch.setattr(terminal, "_query_color_slot", lambda slot, timeout: (20, 20, 20))
    assert detect_tree_theme_name() is BuiltinTreeThemeName.DARK


def test_detect_tree_theme_name_returns_none_when_query_fails(monkeypatch) -> None:
    monkeypatch.setattr(terminal, "_query_color_slot", lambda slot, timeout: None)
    assert detect_tree_theme_name() is None
