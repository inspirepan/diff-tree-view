from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import typer

from diff_tree_view import __version__
from diff_tree_view.app import DiffTreeViewApp
from diff_tree_view.config import UISettings
from diff_tree_view.terminal import detect_tree_theme_name
from diff_tree_view.vcs import BackendError, DetectError, detect_backend

app = typer.Typer(
    name="dff",
    help="Terminal UI diff viewer for jujutsu and git.",
    no_args_is_help=False,
    add_completion=False,
)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-V", help="Show version and exit."),
    backend: str | None = typer.Option(None, "--backend", help="Override backend detection (jj or git)."),
    rev: str | None = typer.Option(None, "--rev", help="Override the backend revision selection."),
) -> None:
    if version:
        typer.echo(f"dff {__version__}")
        raise typer.Exit(0)
    if ctx.invoked_subcommand is None:
        try:
            selected_backend = detect_backend(Path.cwd(), preferred=backend)
            changes = selected_backend.list_changes(rev=rev)
        except (BackendError, DetectError) as exc:
            typer.echo(f"dff: {exc}", err=True)
            raise typer.Exit(1) from exc
        ui = UISettings()
        detected_theme = detect_tree_theme_name()
        if detected_theme is not None:
            ui = replace(ui, tree_theme_name=detected_theme)
        DiffTreeViewApp(changes, backend=selected_backend, rev=rev, ui=ui).run()
