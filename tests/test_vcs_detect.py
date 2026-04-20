from __future__ import annotations

from pathlib import Path

import pytest

from diff_tree_view.vcs.detect import DetectError, detect_backend, find_repo_root
from diff_tree_view.vcs.git import GitBackend
from diff_tree_view.vcs.jj import JjBackend


def test_detect_backend_picks_jj_when_only_jj_is_present(tmp_path: Path) -> None:
    (tmp_path / ".jj").mkdir()

    backend = detect_backend(tmp_path)

    assert isinstance(backend, JjBackend)
    assert backend.repo_root == tmp_path


def test_detect_backend_picks_git_when_only_git_is_present(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()

    backend = detect_backend(tmp_path)

    assert isinstance(backend, GitBackend)
    assert backend.repo_root == tmp_path


def test_detect_backend_prefers_jj_when_both_are_present(tmp_path: Path) -> None:
    (tmp_path / ".jj").mkdir()
    (tmp_path / ".git").mkdir()

    backend = detect_backend(tmp_path)

    assert isinstance(backend, JjBackend)


def test_detect_backend_respects_git_override(tmp_path: Path) -> None:
    (tmp_path / ".jj").mkdir()
    (tmp_path / ".git").mkdir()

    backend = detect_backend(tmp_path, preferred="git")

    assert isinstance(backend, GitBackend)


def test_detect_backend_raises_clear_error_when_no_repo_exists(tmp_path: Path) -> None:
    with pytest.raises(DetectError, match="No jj or git repo found"):
        detect_backend(tmp_path)


def test_find_repo_root_walks_up_parent_directories(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".git").mkdir()
    nested = root / "a" / "b"
    nested.mkdir(parents=True)

    assert find_repo_root(nested) == root
