#!/usr/bin/env python3
"""Read-only comparison of a construction checkout with a freshly observed ref.

This helper never fetches, checks out, repairs, stages, commits, or publishes.
It distinguishes the branch's current commit from uncommitted working-tree
content and refuses to infer ancestry when the remote commit is absent locally.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Sequence

DEFAULT_REMOTE = "https://github.com/Zombinator85/SentientOS.git"
DEFAULT_BRANCH = "codex/construct-sentientos"
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class PreflightError(ValueError):
    pass


def _git(root: Path, *args: str, timeout: float = 8.0) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PreflightError("git_command_unavailable") from exc


def _required(root: Path, *args: str) -> str:
    result = _git(root, *args)
    if result.returncode:
        raise PreflightError("git_identity_unavailable")
    return result.stdout.strip()


def _names(root: Path, *args: str) -> list[str]:
    value = _required(root, *args)
    return sorted({line for line in value.splitlines() if line})


def _is_ancestor(root: Path, ancestor: str, descendant: str) -> bool | None:
    result = _git(root, "merge-base", "--is-ancestor", ancestor, descendant)
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    return None


def inspect_source(
    repository_root: str | Path,
    *,
    branch: str = DEFAULT_BRANCH,
    expected_remote_url: str = DEFAULT_REMOTE,
    expected_head: str | None = None,
) -> dict[str, object]:
    root = Path(repository_root).expanduser().resolve(strict=True)
    ref = f"refs/heads/{branch}"
    if not re.fullmatch(r"[A-Za-z0-9._/-]{1,180}", branch) or ".." in branch or branch.startswith("-"):
        raise PreflightError("branch_name_invalid")
    if expected_head is not None and not _SHA_RE.fullmatch(expected_head):
        raise PreflightError("expected_head_invalid")

    local_head = _required(root, "rev-parse", "--verify", "HEAD")
    local_tree = _required(root, "rev-parse", "--verify", "HEAD^{tree}")
    origin = _required(root, "remote", "get-url", "origin")
    staged = _names(root, "diff", "--cached", "--name-only")
    unstaged = _names(root, "diff", "--name-only")
    untracked = _names(root, "ls-files", "--others", "--exclude-standard")
    status_lines = [line for line in _required(root, "status", "--porcelain=v1", "--untracked-files=all").splitlines() if line]
    branch_name_result = _git(root, "symbolic-ref", "--short", "-q", "HEAD")
    local_branch = branch_name_result.stdout.strip() if branch_name_result.returncode == 0 else None
    dirty = bool(status_lines)

    report: dict[str, object] = {
        "schema_version": 1,
        "repository_root": str(root),
        "expected_remote_url": expected_remote_url,
        "observed_origin_url": origin,
        "branch": branch,
        "local_branch": local_branch,
        "local_head": local_head,
        "local_tree": local_tree,
        "remote_ref": ref,
        "expected_head": expected_head,
        "remote_head": None,
        "remote_tree": None,
        "staged_paths": staged,
        "unstaged_paths": unstaged,
        "untracked_paths": untracked,
        "dirty": dirty,
        "findings": [],
        "status": "remote_identity_unavailable",
    }

    if origin != expected_remote_url:
        report["reason_code"] = "origin_url_mismatch"
        return report
    try:
        remote = subprocess.run(
            ["git", "ls-remote", "--heads", "--", expected_remote_url, ref],
            capture_output=True,
            text=True,
            timeout=8.0,
            check=False,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"},
        )
    except (OSError, subprocess.TimeoutExpired):
        report["reason_code"] = "remote_read_failed"
        return report
    if remote.returncode:
        report["reason_code"] = "remote_read_failed"
        return report
    rows = [line.split() for line in remote.stdout.splitlines() if line.strip()]
    matches = [row for row in rows if len(row) == 2 and row[1] == ref and _SHA_RE.fullmatch(row[0])]
    if len(matches) != 1:
        report["reason_code"] = "remote_ref_missing_or_ambiguous"
        return report
    remote_head = matches[0][0]
    report["remote_head"] = remote_head

    if expected_head is not None and remote_head != expected_head:
        report["status"] = "branch_advanced_during_publication"
        report["reason_code"] = "expected_remote_head_changed"
        if dirty:
            report["findings"] = ["dirty_historical_checkout"]
        return report

    tree_result = _git(root, "rev-parse", "--verify", f"{remote_head}^{{tree}}")
    if tree_result.returncode:
        report["status"] = "remote_commit_object_unavailable"
        report["reason_code"] = "remote_head_not_present_in_local_object_database"
        report["findings"] = ["dirty_historical_checkout"] if dirty else []
        return report
    remote_tree = tree_result.stdout.strip()
    report["remote_tree"] = remote_tree

    if local_head == remote_head:
        report["status"] = "valid_unpublished_changes_on_correct_base" if dirty else "correct_remote_and_local_base"
    elif local_tree == remote_tree:
        report["status"] = "matching_tree_different_commit_identity"
    else:
        remote_is_ancestor = _is_ancestor(root, remote_head, local_head)
        local_is_ancestor = _is_ancestor(root, local_head, remote_head)
        if remote_is_ancestor is None or local_is_ancestor is None:
            report["status"] = "remote_identity_unavailable"
            report["reason_code"] = "ancestry_unavailable"
        elif local_is_ancestor:
            report["status"] = "stale_base"
        elif remote_is_ancestor:
            report["status"] = "unpublished_candidate_requires_reconciliation"
        else:
            report["status"] = "divergent_remote_history"

    findings: list[str] = []
    if dirty and local_head != remote_head:
        findings.append("dirty_historical_checkout")
    if report["status"] == "unpublished_candidate_requires_reconciliation":
        findings.append("local_commit_not_yet_published")
    report["findings"] = findings
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", type=Path)
    parser.add_argument("--branch", default=DEFAULT_BRANCH)
    parser.add_argument("--expected-remote-url", default=DEFAULT_REMOTE)
    parser.add_argument("--expected-head")
    args = parser.parse_args(argv)
    try:
        report = inspect_source(
            args.repository,
            branch=args.branch,
            expected_remote_url=args.expected_remote_url,
            expected_head=args.expected_head,
        )
    except PreflightError as exc:
        report = {"schema_version": 1, "status": "local_identity_unavailable", "reason_code": str(exc)}
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0 if report.get("status") in {"correct_remote_and_local_base", "valid_unpublished_changes_on_correct_base"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
