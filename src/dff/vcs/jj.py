from __future__ import annotations

import subprocess
from pathlib import Path

from dff.models import Change, FileChange, FileSides, HunkStats
from dff.vcs.base import BackendError

DEFAULT_REVSET = "trunk()..@"


class JjBackend:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root

    def list_changes(self, *, rev: str | None = None) -> tuple[Change, ...]:
        revset = rev or DEFAULT_REVSET
        changes: list[Change] = []
        for index, line in enumerate(self._run_log(revset)):
            change_id, description = line.split("\x1f", maxsplit=1)
            files = self._list_files(change_id)
            if not files:
                continue
            changes.append(
                Change(
                    change_id=change_id,
                    short_id=change_id,
                    description=description or "(no description set)",
                    files=files,
                    graph="@" if index == 0 else "○",
                )
            )
        return tuple(changes)

    def _run_log(self, revset: str) -> list[str]:
        output = self._run(
            "log",
            "-r",
            revset,
            "--no-graph",
            "-T",
            'change_id.short() ++ "\u001f" ++ description.first_line() ++ "\n"',
        )
        return [line for line in output.splitlines() if line]

    def _list_files(self, change_id: str) -> tuple[FileChange, ...]:
        summary = self._run("diff", "-r", change_id, "--summary")
        stats = self._parse_patch_stats(self._run("diff", "-r", change_id, "--git"))
        files: list[FileChange] = []
        for raw_line in summary.splitlines():
            if not raw_line:
                continue
            status, raw_path = raw_line.split(" ", maxsplit=1)
            path, old_path = self._parse_summary_path(status, raw_path)
            files.append(
                FileChange(
                    path=path,
                    status=status,
                    old_path=old_path,
                    stats=stats.get(path, HunkStats()),
                )
            )
        return tuple(files)

    def _parse_summary_path(self, status: str, raw_path: str) -> tuple[str, str | None]:
        if status != "R":
            return raw_path, None
        before, after = raw_path.removeprefix("{").removesuffix("}").split(" => ", maxsplit=1)
        return after, before

    def _parse_patch_stats(self, output: str) -> dict[str, HunkStats]:
        stats: dict[str, HunkStats] = {}
        current_path: str | None = None
        added = 0
        removed = 0

        def flush() -> None:
            nonlocal current_path, added, removed
            if current_path is not None:
                stats[current_path] = HunkStats(added, removed)
            current_path = None
            added = 0
            removed = 0

        for line in output.splitlines():
            if line.startswith("diff --git "):
                flush()
                continue
            if line.startswith("rename to "):
                current_path = line.removeprefix("rename to ")
                continue
            if line.startswith("+++ b/"):
                current_path = line.removeprefix("+++ b/")
                continue
            if line.startswith("+") and not line.startswith("+++"):
                added += 1
                continue
            if line.startswith("-") and not line.startswith("---"):
                removed += 1
        flush()
        return stats

    def get_sides(self, change: Change, file: FileChange) -> FileSides:
        before = None if file.status == "A" else self._read_at(f"{change.change_id}-", file.old_path or file.path)
        after = None if file.status == "D" else self._read_at(change.change_id, file.path)

        if file.is_binary or _bytes_look_binary(before) or _bytes_look_binary(after):
            return FileSides(before="", after="", binary=True)
        return FileSides(before=_decode(before), after=_decode(after))

    def _read_at(self, revision: str, path: str) -> bytes | None:
        try:
            return self._run_bytes("file", "show", "-r", revision, path)
        except BackendError:
            return None

    def _run(self, *args: str) -> str:
        try:
            completed = subprocess.run(
                ["jj", "-R", str(self.repo_root), "--quiet", "--ignore-working-copy", *args],
                cwd=self.repo_root,
                check=True,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise BackendError("jj is not installed or not on PATH") from exc
        except subprocess.CalledProcessError as exc:
            raise BackendError(exc.stderr.strip() or exc.stdout.strip() or "jj command failed") from exc
        return completed.stdout

    def _run_bytes(self, *args: str) -> bytes:
        try:
            completed = subprocess.run(
                ["jj", "-R", str(self.repo_root), "--quiet", "--ignore-working-copy", *args],
                cwd=self.repo_root,
                check=True,
                capture_output=True,
                text=False,
            )
        except FileNotFoundError as exc:
            raise BackendError("jj is not installed or not on PATH") from exc
        except subprocess.CalledProcessError as exc:
            raise BackendError(
                exc.stderr.decode(errors="replace").strip()
                or exc.stdout.decode(errors="replace").strip()
                or "jj command failed"
            ) from exc
        return completed.stdout


def _bytes_look_binary(data: bytes | None) -> bool:
    if data is None:
        return False
    return b"\x00" in data[:8000]


def _decode(data: bytes | None) -> str:
    if data is None:
        return ""
    return data.decode(errors="replace")
