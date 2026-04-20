from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from dff import __version__
from dff.app import DffApp
from dff.cli import app
from dff.config import UISettings
from dff.models import Change, FileChange, HunkStats
from dff.theme import BuiltinTreeThemeName


class FakeBackend:
    def __init__(self) -> None:
        self.preferred: str | None = None
        self.rev: str | None = None

    def list_changes(self, *, rev: str | None = None) -> tuple[Change, ...]:
        self.rev = rev
        return (
            Change(
                change_id="demo",
                short_id="demo",
                description="Demo",
                files=(FileChange("demo.py", "M", HunkStats(1, 0)),),
            ),
        )


def test_version_flag_prints_version() -> None:
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_no_args_launches_tree_app(monkeypatch) -> None:
    backend = FakeBackend()
    launched: dict[str, object] = {}

    def fake_detect_backend(cwd: Path, preferred: str | None = None) -> FakeBackend:
        launched["cwd"] = cwd
        backend.preferred = preferred
        return backend

    def fake_run(self: DffApp) -> None:
        launched["changes"] = self.changes

    monkeypatch.setattr("dff.cli.detect_backend", fake_detect_backend)
    monkeypatch.setattr(DffApp, "run", fake_run)

    result = CliRunner().invoke(app, [])

    assert result.exit_code == 0
    assert launched["cwd"] == Path.cwd()
    assert backend.preferred is None
    assert launched["changes"] == backend.list_changes()


def test_cli_applies_detected_light_theme(monkeypatch) -> None:
    backend = FakeBackend()
    captured: dict[str, object] = {}

    def fake_detect_backend(cwd: Path, preferred: str | None = None) -> FakeBackend:
        return backend

    def fake_detect_theme() -> BuiltinTreeThemeName:
        return BuiltinTreeThemeName.LIGHT

    original_init = DffApp.__init__

    def capturing_init(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        captured["ui"] = kwargs.get("ui")
        original_init(self, *args, **kwargs)

    monkeypatch.setattr("dff.cli.detect_backend", fake_detect_backend)
    monkeypatch.setattr("dff.cli.detect_tree_theme_name", fake_detect_theme)
    monkeypatch.setattr(DffApp, "__init__", capturing_init)
    monkeypatch.setattr(DffApp, "run", lambda self: None)

    result = CliRunner().invoke(app, [])

    assert result.exit_code == 0
    ui = captured["ui"]
    assert isinstance(ui, UISettings)
    assert ui.tree_theme_name is BuiltinTreeThemeName.LIGHT


def test_cli_leaves_default_theme_when_detection_fails(monkeypatch) -> None:
    backend = FakeBackend()
    captured: dict[str, object] = {}

    monkeypatch.setattr("dff.cli.detect_backend", lambda cwd, preferred=None: backend)
    monkeypatch.setattr("dff.cli.detect_tree_theme_name", lambda: None)

    original_init = DffApp.__init__

    def capturing_init(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        captured["ui"] = kwargs.get("ui")
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(DffApp, "__init__", capturing_init)
    monkeypatch.setattr(DffApp, "run", lambda self: None)

    result = CliRunner().invoke(app, [])

    assert result.exit_code == 0
    ui = captured["ui"]
    assert isinstance(ui, UISettings)
    assert ui.tree_theme_name is BuiltinTreeThemeName.DARK


def test_cli_forwards_backend_override_and_rev(monkeypatch) -> None:
    backend = FakeBackend()

    def fake_detect_backend(cwd: Path, preferred: str | None = None) -> FakeBackend:
        backend.preferred = preferred
        return backend

    monkeypatch.setattr("dff.cli.detect_backend", fake_detect_backend)
    monkeypatch.setattr(DffApp, "run", lambda self: None)

    result = CliRunner().invoke(app, ["--backend", "git", "--rev", "@"])

    assert result.exit_code == 0
    assert backend.preferred == "git"
    assert backend.rev == "@"
