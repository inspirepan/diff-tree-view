"""Terminal background detection via OSC 11.

Ported from `klaude-code`'s implementation. The goal is to pick a sensible
light/dark default for `BuiltinTreeThemeName` when the user has not
explicitly configured one, by asking the terminal for its background color
using the `ESC ] 11 ; ? BEL` OSC query.
"""

from __future__ import annotations

import contextlib
import os
import re
import select
import sys
import termios
import time
import tty
from typing import BinaryIO, Final

from dff.theme import BuiltinTreeThemeName

ST: Final[bytes] = b"\x1b\\"
BEL: Final[int] = 7

_OSC_BG_REGEX = re.compile(r"\x1b\]11;([^\x07\x1b\\]*)")


def detect_tree_theme_name(timeout: float = 0.3) -> BuiltinTreeThemeName | None:
    """Return the builtin tree theme matching the detected terminal background.

    Returns `None` when detection is not possible (non-TTY, Windows, dumb
    terminal, or the terminal does not respond within `timeout` seconds).
    """

    is_light = _is_light_terminal_background(timeout=timeout)
    if is_light is None:
        return None
    return BuiltinTreeThemeName.LIGHT if is_light else BuiltinTreeThemeName.DARK


def _is_light_terminal_background(timeout: float) -> bool | None:
    rgb = _query_color_slot(slot=11, timeout=timeout)
    if rgb is None:
        return None
    return _luminance_is_light(rgb)


def _luminance_is_light(rgb: tuple[int, int, int]) -> bool:
    r, g, b = rgb
    y = 0.299 * float(r) + 0.587 * float(g) + 0.114 * float(b)
    return y > 128.0


def _query_color_slot(slot: int, timeout: float) -> tuple[int, int, int] | None:
    if sys.platform == "win32":
        return None

    term = os.getenv("TERM", "").lower()
    if term in {"", "dumb"}:
        return None

    try:
        with open("/dev/tty", "r+b", buffering=0) as tty_fp:
            fd = tty_fp.fileno()
            if not os.isatty(fd):
                return None

            try:
                old_attrs = termios.tcgetattr(fd)
            except (termios.error, OSError):
                old_attrs = None

            try:
                if old_attrs is not None:
                    tty.setcbreak(fd)

                _send_osc_query(tty_fp, slot)
                raw = _read_osc_response(fd, timeout=timeout)
            finally:
                if old_attrs is not None:
                    with contextlib.suppress(termios.error, OSError):
                        termios.tcsetattr(fd, termios.TCSADRAIN, old_attrs)
    except OSError:
        return None

    if raw is None or not raw:
        return None

    return _parse_osc_color_response(raw)


def _send_osc_query(tty_fp: BinaryIO, slot: int) -> None:
    seq = f"\x1b]{slot};?\x1b\\".encode("ascii", errors="ignore")
    try:
        tty_fp.write(seq)
        tty_fp.flush()
    except OSError:
        pass


def _read_osc_response(fd: int, timeout: float) -> bytes | None:
    deadline = time.monotonic() + max(timeout, 0.0)
    buf = bytearray()

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break

        readable, _, _ = select.select([fd], [], [], remaining)
        if not readable:
            continue

        try:
            chunk = os.read(fd, 1024)
        except OSError:
            break

        if not chunk:
            break

        buf.extend(chunk)

        if BEL in buf:
            idx = buf.index(BEL)
            return bytes(buf[: idx + 1])

        st_index = buf.find(ST)
        if st_index != -1:
            return bytes(buf[: st_index + len(ST)])

    return bytes(buf) if buf else None


def _parse_osc_color_response(data: bytes) -> tuple[int, int, int] | None:
    text = data.decode("ascii", errors="ignore")

    match = _OSC_BG_REGEX.search(text)
    if not match:
        return None

    payload = match.group(1).strip().split(";", 1)[0].strip()
    return _parse_rgb_spec(payload)


def _parse_rgb_spec(spec: str) -> tuple[int, int, int] | None:
    spec = spec.strip()

    if spec.lower().startswith("rgb:"):
        parts = spec[4:].split("/")
        if len(parts) != 3:
            return None
        try:
            return (
                _scale_hex_component(parts[0]),
                _scale_hex_component(parts[1]),
                _scale_hex_component(parts[2]),
            )
        except ValueError:
            return None

    if spec.startswith("#") and len(spec) == 7:
        try:
            return (
                int(spec[1:3], 16),
                int(spec[3:5], 16),
                int(spec[5:7], 16),
            )
        except ValueError:
            return None

    return None


def _scale_hex_component(component: str) -> int:
    if not component or len(component) > 4:
        raise ValueError("invalid component width")

    value = int(component, 16)
    max_value = (16 ** len(component)) - 1
    scaled = round((value / float(max_value)) * 255.0)
    return max(0, min(255, int(scaled)))
