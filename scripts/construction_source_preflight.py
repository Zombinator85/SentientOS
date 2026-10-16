#!/usr/bin/env python3
"""Read-only comparison of a construction checkout with a freshly observed ref.

This helper never fetches, checks out, repairs, stages, commits, or publishes.
It distinguishes the branch's current commit from uncommitted working-tree
content and refuses to infer ancestry when the remote commit is absent locally.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from scripts.verify_construction_continuation_custody import verify_continuation_reader

DEFAULT_REMOTE = "https://github.com/Zombinator85/SentientOS.git"
DEFAULT_BRANCH = "codex/construct-sentientos"
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
MAX_CANDIDATE_FILES = 128
MAX_CANDIDATE_FILE_BYTES = 2 * 1024 * 1024
MAX_CANDIDATE_TOTAL_BYTES = 16 * 1024 * 1024


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


def _tree_blob(root: Path, tree: str, path: str, limit: int) -> tuple[str, bytes]:
    relative = PurePosixPath(path)
    if (relative.is_absolute() or str(relative) != path or not relative.parts
            or any(part in {".", ".."} for part in relative.parts)
            or "\x00" in path or "\n" in path or "\t" in path):
        raise PreflightError("candidate_path_invalid")
    row = _required(root, "ls-tree", tree, "--", path)
    header, separator, actual_path = row.partition("\t")
    fields = header.split()
    if (not separator or actual_path != path or len(fields) != 3
            or fields[0] not in {"100644", "100755"} or fields[1] != "blob"):
        raise PreflightError("candidate_regular_blob_required")
    blob = fields[2]
    size = int(_required(root, "cat-file", "-s", blob))
    if size > limit:
        raise PreflightError("candidate_file_unbounded")
    result = subprocess.run(["git", "-C", str(root), "cat-file", "blob", blob],
        capture_output=True, timeout=8, check=False)
    if result.returncode or len(result.stdout) != size:
        raise PreflightError("candidate_blob_read_failed")
    return blob, result.stdout


def candidate_manifest(root: Path, tree: str, expected_head: str) -> dict[str, Any]:
    """Bind tested working bytes to every changed candidate-tree member."""
    if not _SHA_RE.fullmatch(tree) or not _SHA_RE.fullmatch(expected_head):
        raise PreflightError("candidate_identity_invalid")
    paths = _names(root, "diff", "--name-only", expected_head, tree)
    if len(paths) > MAX_CANDIDATE_FILES:
        raise PreflightError("candidate_files_unbounded")
    files = []
    for path in paths:
        blob, data = _tree_blob(root, tree, path, MAX_CANDIDATE_FILE_BYTES)
        local = root / path
        if local.is_symlink() or local.read_bytes() != data:
            raise PreflightError("candidate_tested_worktree_mismatch:" + path)
        files.append({"path": path, "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(), "git_blob_sha": blob})
    return {"schema_version": 1, "expected_head": expected_head,
        "candidate_tree": tree, "files": files}


def verify_candidate_publication(root: Path, manifest: Mapping[str, Any], *,
        observed_blobs: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Read-only guard for exact source bytes, frozen custody and remote blobs.

    An observed blob map must come from actual remote blob readback. This
    function compares that observation; it does not issue attestations or
    update the branch. CAS remains the publisher's separate final operation.
    """
    failures: list[str] = []
    if not isinstance(manifest, Mapping) or (
            observed_blobs is not None and not isinstance(observed_blobs, Mapping)):
        return {"status": "invalid", "failures": ["candidate_manifest_or_observation_shape_invalid"],
            "remote_ref_updated": False}
    try:
        tree, parent = manifest["candidate_tree"], manifest["expected_head"]
        if (manifest.get("schema_version") != 1 or not isinstance(tree, str)
                or not _SHA_RE.fullmatch(tree) or not isinstance(parent, str)
                or not _SHA_RE.fullmatch(parent)):
            raise PreflightError("candidate_manifest_identity_invalid")
        if (_required(root, "cat-file", "-t", tree) != "tree"
                or _required(root, "cat-file", "-t", parent) != "commit"):
            raise PreflightError("candidate_git_object_kind_invalid")
        files = manifest["files"]
        if not isinstance(files, list) or not files or len(files) > MAX_CANDIDATE_FILES:
            raise PreflightError("candidate_manifest_files_invalid")
        raw_listed = [item.get("path") if isinstance(item, dict) else None for item in files]
        if any(not isinstance(path, str) for path in raw_listed):
            raise PreflightError("candidate_tree_membership_mismatch")
        listed = [str(path) for path in raw_listed]
        changed = _names(root, "diff", "--name-only", parent, tree)
        if len(set(listed)) != len(listed) or sorted(listed) != changed:
            raise PreflightError("candidate_tree_membership_mismatch")
        total = 0
        for item in files:
            path = item["path"]
            blob, data = _tree_blob(root, tree, path, MAX_CANDIDATE_FILE_BYTES)
            total += len(data)
            if (type(item.get("bytes")) is not int or item["bytes"] != len(data)
                    or item.get("sha256") != hashlib.sha256(data).hexdigest()
                    or item.get("git_blob_sha") != blob):
                failures.append("candidate_bytes_mismatch:" + path)
            if observed_blobs is not None and observed_blobs.get(path) != blob:
                failures.append("remote_blob_mismatch_or_missing:" + path)
            if path.endswith((".py", ".md", ".json", ".xml", ".toml", ".yml", ".yaml")):
                try:
                    source = data.decode("utf-8")
                    if path.endswith(".py"):
                        compile(source, path, "exec")
                except (UnicodeError, SyntaxError, ValueError):
                    failures.append("candidate_source_invalid:" + path)
        if total > MAX_CANDIDATE_TOTAL_BYTES:
            failures.append("candidate_total_bytes_unbounded")
        def read(path: str, limit: int) -> bytes:
            return _tree_blob(root, tree, path, limit)[1]
        custody = verify_continuation_reader(read)
        failures.extend("custody:" + error for error in custody["failures"])
        old_index = json.loads(_tree_blob(root, parent,
            "work/construction/index.json", MAX_CANDIDATE_FILE_BYTES)[1])
        new_index = json.loads(read("work/construction/index.json", MAX_CANDIDATE_FILE_BYTES))
        if old_index.get("legacy_journal") != new_index.get("legacy_journal"):
            failures.append("frozen_journal_definition_changed")
        for path in {item["path"] for item in old_index.get("segments", [])
                if isinstance(item, dict) and isinstance(item.get("path"), str)}:
            old_blob, _ = _tree_blob(root, parent, path, MAX_CANDIDATE_FILE_BYTES)
            if _tree_blob(root, tree, path, MAX_CANDIDATE_FILE_BYTES)[0] != old_blob:
                failures.append("historical_segment_changed:" + path)
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        failures.append("candidate_unreadable:" + str(exc))
    return {"schema_version": 1, "candidate_tree": manifest.get("candidate_tree"),
        "expected_head": manifest.get("expected_head"), "failures": failures,
        "status": "invalid" if failures else (
            "candidate_integrity_ready_for_ref_update" if observed_blobs is not None
            else "candidate_integrity_ready_for_blob_upload"),
        "remote_ref_updated": False}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", type=Path)
    parser.add_argument("--branch", default=DEFAULT_BRANCH)
    parser.add_argument("--expected-remote-url", default=DEFAULT_REMOTE)
    parser.add_argument("--expected-head")
    parser.add_argument("--candidate-manifest", type=Path)
    parser.add_argument("--observed-blobs", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.candidate_manifest is not None:
            manifest = json.loads(args.candidate_manifest.read_bytes())
            observed = (json.loads(args.observed_blobs.read_bytes())
                if args.observed_blobs is not None else None)
            candidate_report = verify_candidate_publication(args.repository, manifest,
                observed_blobs=observed)
            print(json.dumps(candidate_report, sort_keys=True, indent=2))
            return 0 if not candidate_report["failures"] else 2
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
