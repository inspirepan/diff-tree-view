from __future__ import annotations

import subprocess
from pathlib import Path

from diff_tree_view.models import FileSides, HunkStats
from diff_tree_view.vcs.base import Backend
from diff_tree_view.vcs.jj import JjBackend


def run(args: list[str], cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)


def jj_repo_with_feature_change(tmp_path: Path) -> Path:
    run(["jj", "git", "init", "."], tmp_path)
    (tmp_path / "base.txt").write_text("base\n")
    run(["jj", "file", "track", "base.txt"], tmp_path)
    run(["jj", "describe", "-m", "base"], tmp_path)
    run(["jj", "bookmark", "create", "trunk", "-r", "@"], tmp_path)
    run(["jj", "new", "trunk"], tmp_path)
    (tmp_path / "added.txt").write_text("added\n")
    run(["jj", "file", "track", "added.txt"], tmp_path)
    (tmp_path / "base.txt").write_text("base\nfeature\n")
    run(["jj", "describe", "-m", "feature"], tmp_path)
    return tmp_path


def test_jj_backend_satisfies_backend_protocol(tmp_path: Path) -> None:
    root = jj_repo_with_feature_change(tmp_path)

    backend = JjBackend(root)

    assert isinstance(backend, Backend)


def test_jj_backend_lists_requested_revset_for_tree(tmp_path: Path) -> None:
    root = jj_repo_with_feature_change(tmp_path)
    backend = JjBackend(root)

    changes = backend.list_changes(rev="@")

    assert [change.description for change in changes] == ["feature"]

    files = {file_change.path: file_change for file_change in changes[0].files}
    assert files["base.txt"].status == "M"
    assert files["base.txt"].stats == HunkStats(1, 0)
    assert files["added.txt"].status == "A"
    assert files["added.txt"].stats == HunkStats(1, 0)


def test_jj_backend_defaults_to_current_revset(tmp_path: Path) -> None:
    root = jj_repo_with_feature_change(tmp_path)

    changes = JjBackend(root).list_changes()

    assert changes
    assert changes[0].files


def test_jj_backend_get_sides_returns_parent_and_current(tmp_path: Path) -> None:
    root = jj_repo_with_feature_change(tmp_path)
    backend = JjBackend(root)
    changes = backend.list_changes(rev="@")
    feature = changes[0]
    files = {f.path: f for f in feature.files}

    modified = backend.get_sides(feature, files["base.txt"])
    assert modified.before == "base\n"
    assert modified.after == "base\nfeature\n"
    assert not modified.binary

    added = backend.get_sides(feature, files["added.txt"])
    assert added.before == ""
    assert added.after == "added\n"
    assert not added.binary


def test_jj_backend_get_sides_flags_binary(tmp_path: Path) -> None:
    run(["jj", "git", "init", "."], tmp_path)
    (tmp_path / "seed.txt").write_text("seed\n")
    run(["jj", "file", "track", "seed.txt"], tmp_path)
    run(["jj", "describe", "-m", "base"], tmp_path)
    run(["jj", "bookmark", "create", "trunk", "-r", "@"], tmp_path)
    run(["jj", "new", "trunk"], tmp_path)
    (tmp_path / "blob.bin").write_bytes(b"\x00\x01\x02\x03")
    run(["jj", "file", "track", "blob.bin"], tmp_path)
    run(["jj", "describe", "-m", "binary"], tmp_path)

    backend = JjBackend(tmp_path)
    changes = backend.list_changes(rev="@")
    feature = changes[0]
    blob = next(f for f in feature.files if f.path == "blob.bin")

    sides = backend.get_sides(feature, blob)
    assert sides == FileSides(before="", after="", binary=True)
