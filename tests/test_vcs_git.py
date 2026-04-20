from __future__ import annotations

import subprocess
from pathlib import Path

from diff_tree_view.models import FileChange, FileSides, HunkStats
from diff_tree_view.vcs.base import Backend
from diff_tree_view.vcs.git import GitBackend


def run(args: list[str], cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)


def git_repo_with_staged_and_unstaged_changes(tmp_path: Path) -> Path:
    run(["git", "init", "-q"], tmp_path)
    run(["git", "config", "user.name", "Test User"], tmp_path)
    run(["git", "config", "user.email", "test@example.com"], tmp_path)

    (tmp_path / "modified.txt").write_text("base\n")
    (tmp_path / "deleted.txt").write_text("delete\n")
    (tmp_path / "rename-me.txt").write_text("rename\n")
    (tmp_path / "worktree.txt").write_text("worktree\n")
    run(["git", "add", "modified.txt", "deleted.txt", "rename-me.txt", "worktree.txt"], tmp_path)
    run(["git", "commit", "-qm", "init"], tmp_path)

    (tmp_path / "modified.txt").write_text("base\nstaged\n")
    (tmp_path / "added.txt").write_text("added\n")
    run(["git", "rm", "-q", "deleted.txt"], tmp_path)
    run(["git", "mv", "rename-me.txt", "renamed.txt"], tmp_path)
    run(["git", "add", "modified.txt", "added.txt", "renamed.txt"], tmp_path)

    (tmp_path / "worktree.txt").write_text("worktree\nunstaged\n")
    return tmp_path


def test_git_backend_satisfies_backend_protocol(tmp_path: Path) -> None:
    root = git_repo_with_staged_and_unstaged_changes(tmp_path)

    backend = GitBackend(root)

    assert isinstance(backend, Backend)


def test_git_backend_lists_staged_and_unstaged_groups(tmp_path: Path) -> None:
    root = git_repo_with_staged_and_unstaged_changes(tmp_path)
    backend = GitBackend(root)

    changes = backend.list_changes()

    assert [change.description for change in changes] == ["Staged", "Unstaged"]

    staged_files = {file_change.path: file_change for file_change in changes[0].files}
    assert staged_files["added.txt"].status == "A"
    assert staged_files["added.txt"].stats == HunkStats(1, 0)
    assert staged_files["deleted.txt"].status == "D"
    assert staged_files["deleted.txt"].stats == HunkStats(0, 1)
    assert staged_files["modified.txt"].status == "M"
    assert staged_files["modified.txt"].stats == HunkStats(1, 0)
    assert staged_files["renamed.txt"].status == "R"
    assert staged_files["renamed.txt"].stats == HunkStats(0, 0)
    assert staged_files["renamed.txt"].is_rename

    unstaged_files = {file_change.path: file_change for file_change in changes[1].files}
    assert list(unstaged_files) == ["worktree.txt"]
    assert unstaged_files["worktree.txt"].status == "M"
    assert unstaged_files["worktree.txt"].stats == HunkStats(1, 0)


def test_git_backend_get_sides_returns_head_and_index_for_staged(tmp_path: Path) -> None:
    root = git_repo_with_staged_and_unstaged_changes(tmp_path)
    backend = GitBackend(root)
    changes = backend.list_changes()
    staged = changes[0]
    staged_files = {f.path: f for f in staged.files}

    modified = backend.get_sides(staged, staged_files["modified.txt"])
    assert modified.before == "base\n"
    assert modified.after == "base\nstaged\n"
    assert not modified.binary

    added = backend.get_sides(staged, staged_files["added.txt"])
    assert added.before == ""
    assert added.after == "added\n"

    deleted = backend.get_sides(staged, staged_files["deleted.txt"])
    assert deleted.before == "delete\n"
    assert deleted.after == ""

    renamed = backend.get_sides(staged, staged_files["renamed.txt"])
    assert renamed.before == "rename\n"
    assert renamed.after == "rename\n"


def test_git_backend_get_sides_returns_index_and_worktree_for_unstaged(tmp_path: Path) -> None:
    root = git_repo_with_staged_and_unstaged_changes(tmp_path)
    backend = GitBackend(root)
    unstaged = backend.list_changes()[1]
    sides = backend.get_sides(unstaged, unstaged.files[0])

    assert sides.before == "worktree\n"
    assert sides.after == "worktree\nunstaged\n"
    assert not sides.binary


def test_git_backend_get_sides_flags_binary_files(tmp_path: Path) -> None:
    run(["git", "init", "-q"], tmp_path)
    run(["git", "config", "user.name", "Test User"], tmp_path)
    run(["git", "config", "user.email", "test@example.com"], tmp_path)
    (tmp_path / "seed.txt").write_text("seed\n")
    run(["git", "add", "seed.txt"], tmp_path)
    run(["git", "commit", "-qm", "init"], tmp_path)
    (tmp_path / "blob.bin").write_bytes(b"\x00\x01\x02\x03")
    run(["git", "add", "blob.bin"], tmp_path)

    backend = GitBackend(tmp_path)
    staged = backend.list_changes()[0]
    blob = next(f for f in staged.files if f.path == "blob.bin")
    assert blob.is_binary

    sides = backend.get_sides(staged, blob)
    assert sides == FileSides(before="", after="", binary=True)


def test_git_backend_get_sides_detects_binary_worktree_file(tmp_path: Path) -> None:
    run(["git", "init", "-q"], tmp_path)
    run(["git", "config", "user.name", "Test User"], tmp_path)
    run(["git", "config", "user.email", "test@example.com"], tmp_path)
    (tmp_path / "blob.bin").write_bytes(b"seed\n")
    run(["git", "add", "blob.bin"], tmp_path)
    run(["git", "commit", "-qm", "init"], tmp_path)
    (tmp_path / "blob.bin").write_bytes(b"\x00\x01\x02\x03")

    backend = GitBackend(tmp_path)
    unstaged = backend.list_changes()[0]
    sides = backend.get_sides(unstaged, unstaged.files[0])

    assert sides.binary
    assert sides.before == ""
    assert sides.after == ""


def test_git_backend_get_sides_rejects_unknown_change(tmp_path: Path) -> None:
    root = git_repo_with_staged_and_unstaged_changes(tmp_path)
    backend = GitBackend(root)
    from diff_tree_view.models import Change

    stranger = Change(change_id="git-other", short_id="?", description="?")
    try:
        backend.get_sides(stranger, FileChange(path="modified.txt", status="M"))
    except ValueError:
        return
    raise AssertionError("expected ValueError for unknown change")


def test_git_backend_omits_empty_staged_group(tmp_path: Path) -> None:
    run(["git", "init", "-q"], tmp_path)
    run(["git", "config", "user.name", "Test User"], tmp_path)
    run(["git", "config", "user.email", "test@example.com"], tmp_path)
    (tmp_path / "tracked.txt").write_text("base\n")
    run(["git", "add", "tracked.txt"], tmp_path)
    run(["git", "commit", "-qm", "init"], tmp_path)
    (tmp_path / "tracked.txt").write_text("base\nchanged\n")

    changes = GitBackend(tmp_path).list_changes()

    assert [change.description for change in changes] == ["Unstaged"]
    assert changes[0].files[0].path == "tracked.txt"
