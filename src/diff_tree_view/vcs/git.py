from __future__ import annotations

import subprocess
from pathlib import Path

from diff_tree_view.models import Change, FileChange, FileSides, HunkStats
from diff_tree_view.vcs.base import BackendError

STAGED_CHANGE_ID = "git-staged"
UNSTAGED_CHANGE_ID = "git-unstaged"


class GitBackend:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root

    def list_changes(self, *, rev: str | None = None) -> tuple[Change, ...]:
        staged = self._collect_change(
            description="Staged",
            change_id=STAGED_CHANGE_ID,
            graph="●",
            name_status_args=["diff", "--cached", "--name-status", "-z", "-M"],
            numstat_args=["diff", "--cached", "--numstat", "-z", "-M"],
        )
        unstaged = self._collect_change(
            description="Unstaged",
            change_id=UNSTAGED_CHANGE_ID,
            graph="○",
            name_status_args=["diff", "--name-status", "-z", "-M"],
            numstat_args=["diff", "--numstat", "-z", "-M"],
        )
        return tuple(change for change in (staged, unstaged) if change is not None)

    def get_sides(self, change: Change, file: FileChange) -> FileSides:
        if change.change_id == STAGED_CHANGE_ID:
            before_source = self._read_head(file.old_path or file.path) if file.status != "A" else None
            after_source = self._read_index(file.path) if file.status != "D" else None
        elif change.change_id == UNSTAGED_CHANGE_ID:
            before_source = self._read_index(file.path) if file.status != "A" else None
            after_source = self._read_worktree(file.path) if file.status != "D" else None
        else:
            raise ValueError(f"Unknown git change id: {change.change_id!r}")

        if file.is_binary or _bytes_look_binary(before_source) or _bytes_look_binary(after_source):
            return FileSides(before="", after="", binary=True)
        return FileSides(before=_decode(before_source), after=_decode(after_source))

    def _read_head(self, path: str) -> bytes | None:
        try:
            return self._run_bytes("show", f"HEAD:{path}")
        except BackendError:
            return None

    def _read_index(self, path: str) -> bytes | None:
        try:
            return self._run_bytes("show", f":{path}")
        except BackendError:
            return None

    def _read_worktree(self, path: str) -> bytes | None:
        target = self.repo_root / path
        if not target.exists():
            return None
        return target.read_bytes()

    def _run_bytes(self, *args: str) -> bytes:
        try:
            completed = subprocess.run(
                ["git", *args],
                cwd=self.repo_root,
                check=True,
                capture_output=True,
                text=False,
            )
        except FileNotFoundError as exc:
            raise BackendError("git is not installed or not on PATH") from exc
        except subprocess.CalledProcessError as exc:
            raise BackendError(
                exc.stderr.decode(errors="replace").strip()
                or exc.stdout.decode(errors="replace").strip()
                or "git command failed"
            ) from exc
        return completed.stdout

    def _collect_change(
        self,
        *,
        description: str,
        change_id: str,
        graph: str,
        name_status_args: list[str],
        numstat_args: list[str],
    ) -> Change | None:
        statuses = self._parse_name_status(self._run(*name_status_args))
        if not statuses:
            return None
        stats, binary_paths = self._parse_numstat(self._run(*numstat_args))
        files = tuple(
            FileChange(
                path=path,
                status=entry["status"],
                old_path=entry.get("old_path"),
                stats=stats.get(path, HunkStats()),
                is_binary=path in binary_paths,
            )
            for path, entry in statuses.items()
        )
        return Change(change_id=change_id, short_id=description, description=description, files=files, graph=graph)

    def _run(self, *args: str) -> str:
        try:
            completed = subprocess.run(
                ["git", *args],
                cwd=self.repo_root,
                check=True,
                capture_output=True,
                text=False,
            )
        except FileNotFoundError as exc:
            raise BackendError("git is not installed or not on PATH") from exc
        except subprocess.CalledProcessError as exc:
            raise BackendError(
                exc.stderr.decode().strip() or exc.stdout.decode().strip() or "git command failed"
            ) from exc
        return completed.stdout.decode()

    def _parse_name_status(self, output: str) -> dict[str, dict[str, str]]:
        parts = [part for part in output.split("\0") if part]
        statuses: dict[str, dict[str, str]] = {}
        index = 0
        while index < len(parts):
            token = parts[index]
            status = token[0]
            if status == "R":
                old_path = parts[index + 1]
                new_path = parts[index + 2]
                statuses[new_path] = {"status": "R", "old_path": old_path}
                index += 3
                continue
            path = parts[index + 1]
            statuses[path] = {"status": status}
            index += 2
        return statuses

    def _parse_numstat(self, output: str) -> tuple[dict[str, HunkStats], set[str]]:
        parts = [part for part in output.split("\0") if part]
        stats: dict[str, HunkStats] = {}
        binary_paths: set[str] = set()
        index = 0
        while index < len(parts):
            fields = parts[index].split("\t")
            added_text = fields[0]
            removed_text = fields[1]
            if len(fields) == 3 and fields[2]:
                path = fields[2]
                index += 1
            else:
                path = parts[index + 2]
                index += 3
            if added_text == "-" and removed_text == "-":
                binary_paths.add(path)
                continue
            stats[path] = HunkStats(int(added_text), int(removed_text))
        return stats, binary_paths


def _bytes_look_binary(data: bytes | None) -> bool:
    if data is None:
        return False
    return b"\x00" in data[:8000]


def _decode(data: bytes | None) -> str:
    if data is None:
        return ""
    return data.decode(errors="replace")
