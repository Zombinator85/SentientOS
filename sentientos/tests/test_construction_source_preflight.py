from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from scripts.construction_source_preflight import inspect_source


BRANCH = "codex/construct-sentientos"


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def _source_pair(tmp_path: Path) -> tuple[Path, Path]:
    bare = tmp_path / "remote.git"
    checkout = tmp_path / "checkout"
    subprocess.run(["git", "init", "--bare", "--initial-branch", BRANCH, str(bare)], check=True, capture_output=True)
    subprocess.run(["git", "init", "--initial-branch", BRANCH, str(checkout)], check=True, capture_output=True)
    _git(checkout, "config", "user.name", "Preflight Fixture")
    _git(checkout, "config", "user.email", "preflight@example.invalid")
    (checkout / "source.txt").write_text("base\n", encoding="utf-8")
    _git(checkout, "add", "source.txt")
    _git(checkout, "commit", "-m", "base")
    _git(checkout, "remote", "add", "origin", str(bare))
    _git(checkout, "push", "-u", "origin", BRANCH)
    return checkout, bare


def _advance_remote(tmp_path: Path, bare: Path) -> str:
    other = tmp_path / "other"
    subprocess.run(["git", "clone", str(bare), str(other)], check=True, capture_output=True)
    _git(other, "checkout", BRANCH)
    _git(other, "config", "user.name", "Preflight Fixture")
    _git(other, "config", "user.email", "preflight@example.invalid")
    (other / "remote.txt").write_text("remote advance\n", encoding="utf-8")
    _git(other, "add", "remote.txt")
    _git(other, "commit", "-m", "remote advance")
    _git(other, "push", "origin", BRANCH)
    return _git(other, "rev-parse", "HEAD")


def test_exact_clean_remote_base_is_distinguished(tmp_path: Path) -> None:
    checkout, bare = _source_pair(tmp_path)
    report = inspect_source(checkout, branch=BRANCH, expected_remote_url=str(bare))
    assert report["status"] == "correct_remote_and_local_base"
    assert report["local_head"] == report["remote_head"]
    assert report["dirty"] is False


def test_unpublished_work_on_exact_base_is_separately_reported(tmp_path: Path) -> None:
    checkout, bare = _source_pair(tmp_path)
    (checkout / "source.txt").write_text("staged\n", encoding="utf-8")
    _git(checkout, "add", "source.txt")
    (checkout / "source.txt").write_text("unstaged\n", encoding="utf-8")
    (checkout / "new.txt").write_text("untracked\n", encoding="utf-8")
    report = inspect_source(checkout, branch=BRANCH, expected_remote_url=str(bare))
    assert report["status"] == "valid_unpublished_changes_on_correct_base"
    assert report["staged_paths"] == ["source.txt"]
    assert report["unstaged_paths"] == ["source.txt"]
    assert report["untracked_paths"] == ["new.txt"]


def test_unpublished_commit_is_candidate_and_not_remote_base(tmp_path: Path) -> None:
    checkout, bare = _source_pair(tmp_path)
    (checkout / "candidate.txt").write_text("candidate\n", encoding="utf-8")
    _git(checkout, "add", "candidate.txt")
    _git(checkout, "commit", "-m", "candidate")
    report = inspect_source(checkout, branch=BRANCH, expected_remote_url=str(bare))
    assert report["status"] == "unpublished_candidate_requires_reconciliation"
    assert "local_commit_not_yet_published" in report["findings"]


def test_stale_and_dirty_historical_checkout_are_both_visible(tmp_path: Path) -> None:
    checkout, bare = _source_pair(tmp_path)
    remote_head = _advance_remote(tmp_path, bare)
    _git(checkout, "fetch", "origin", BRANCH)
    (checkout / "source.txt").write_text("local dirty\n", encoding="utf-8")
    report = inspect_source(checkout, branch=BRANCH, expected_remote_url=str(bare))
    assert report["status"] == "stale_base"
    assert "dirty_historical_checkout" in report["findings"]
    assert report["remote_head"] == remote_head


def test_divergence_and_expected_head_race_are_not_accepted(tmp_path: Path) -> None:
    checkout, bare = _source_pair(tmp_path)
    old_remote = _git(checkout, "rev-parse", "HEAD")
    (checkout / "local.txt").write_text("local branch\n", encoding="utf-8")
    _git(checkout, "add", "local.txt")
    _git(checkout, "commit", "-m", "local advance")
    _advance_remote(tmp_path, bare)
    _git(checkout, "fetch", "origin", BRANCH)
    report = inspect_source(checkout, branch=BRANCH, expected_remote_url=str(bare))
    assert report["status"] == "divergent_remote_history"
    raced = inspect_source(checkout, branch=BRANCH, expected_remote_url=str(bare), expected_head=old_remote)
    assert raced["status"] == "branch_advanced_during_publication"


def test_equal_tree_with_rewritten_commit_is_not_exact_identity(tmp_path: Path) -> None:
    checkout, bare = _source_pair(tmp_path)
    base = _git(checkout, "rev-parse", "HEAD")
    tree = _git(checkout, "rev-parse", "HEAD^{tree}")
    replacement = _git(checkout, "commit-tree", tree, "-p", base, "-m", "same tree, new commit")
    _git(checkout, "push", "origin", replacement + ":refs/heads/" + BRANCH)
    report = inspect_source(checkout, branch=BRANCH, expected_remote_url=str(bare))
    assert report["status"] == "matching_tree_different_commit_identity"
    assert report["local_tree"] == report["remote_tree"]
    assert report["local_head"] != report["remote_head"]


def test_remote_identity_mismatch_fails_closed(tmp_path: Path) -> None:
    checkout, bare = _source_pair(tmp_path)
    report = inspect_source(checkout, branch=BRANCH, expected_remote_url=str(tmp_path / "wrong.git"))
    assert report["status"] == "remote_identity_unavailable"
    assert report["reason_code"] == "origin_url_mismatch"


def test_unreachable_expected_remote_is_explicitly_unavailable(tmp_path: Path) -> None:
    checkout, bare = _source_pair(tmp_path)
    shutil.rmtree(bare)
    report = inspect_source(checkout, branch=BRANCH, expected_remote_url=str(bare))
    assert report["status"] == "remote_identity_unavailable"
    assert report["reason_code"] == "remote_read_failed"


def test_remote_advance_without_fetch_never_accepts_stale_checkout(tmp_path: Path) -> None:
    checkout, bare = _source_pair(tmp_path)
    stale_head = _git(checkout, "rev-parse", "HEAD")
    remote_head = _advance_remote(tmp_path, bare)

    report = inspect_source(checkout, branch=BRANCH, expected_remote_url=str(bare))

    assert report["status"] == "remote_commit_object_unavailable"
    assert report["reason_code"] == "remote_head_not_present_in_local_object_database"
    assert report["local_head"] == stale_head
    assert report["remote_head"] == remote_head
    assert report["dirty"] is False

    raced = inspect_source(
        checkout, branch=BRANCH, expected_remote_url=str(bare), expected_head=stale_head)
    assert raced["status"] == "branch_advanced_during_publication"
    assert raced["remote_head"] == remote_head
