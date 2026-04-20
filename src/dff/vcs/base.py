from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from dff.models import Change, FileChange, FileSides


class BackendError(RuntimeError):
    pass


@runtime_checkable
class Backend(Protocol):
    repo_root: Path

    def list_changes(self, *, rev: str | None = None) -> tuple[Change, ...]: ...

    def get_sides(self, change: Change, file: FileChange) -> FileSides: ...
