"""Read-only, local Git orientation for a fresh coding conversation."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Callable, Sequence


SCHEMA_VERSION = "sentientos.codex_fresh_chat_orientation:v1"


class OrientationError(RuntimeError):
    """Raised when a trustworthy, internally consistent snapshot is unavailable."""


GitRunner = Callable[[Path, Sequence[str]], bytes]


def _run_git(cwd: Path, arguments: Sequence[str]) -> bytes:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", "replace").strip()
        raise OrientationError(f"git_observation_failed:{arguments[0]}:{detail or completed.returncode}")
    return completed.stdout


def _text(value: bytes, primitive: str) -> str:
    try:
        return value.decode("utf-8").rstrip("\n")
    except UnicodeDecodeError as exc:
        raise OrientationError(f"git_output_not_utf8:{primitive}") from exc


def _identity(cwd: Path, run_git: GitRunner) -> tuple[str, str | None, bool]:
    head = _text(run_git(cwd, ("rev-parse", "--verify", "HEAD")), "head")
    symbolic = subprocess.run(
        ["git", "symbolic-ref", "--quiet", "--short", "HEAD"],
        cwd=cwd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ) if run_git is _run_git else None
    if symbolic is not None:
        if symbolic.returncode not in (0, 1):
            raise OrientationError("git_observation_failed:symbolic-ref")
        branch = _text(symbolic.stdout, "branch") if symbolic.returncode == 0 else None
    else:
        try:
            branch = _text(run_git(cwd, ("symbolic-ref", "--quiet", "--short", "HEAD")), "branch")
        except OrientationError:
            branch = None
    return head, branch, branch is None


def _decode_path(value: bytes) -> str:
    return _text(value, "status_path")


def _parse_status(raw: bytes) -> dict[str, Any]:
    records = raw.split(b"\0")
    staged: list[dict[str, str]] = []
    unstaged: list[dict[str, str]] = []
    untracked: list[str] = []
    conflicted: list[dict[str, str]] = []
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record or record.startswith(b"# "):
            continue
        kind = record[:1]
        if kind == b"?":
            untracked.append(_decode_path(record[2:]))
            continue
        if kind == b"!":
            continue
        field_limits = {b"1": 8, b"2": 9, b"u": 10}
        fields = record.split(b" ", field_limits.get(kind, 1))
        if kind == b"1" and len(fields) >= 9:
            xy, path = fields[1].decode("ascii"), _decode_path(fields[8])
        elif kind == b"2" and len(fields) >= 10:
            xy, path = fields[1].decode("ascii"), _decode_path(fields[9])
            if index >= len(records):
                raise OrientationError("malformed_git_status:missing_rename_source")
            source = _decode_path(records[index])
            index += 1
            path = f"{source} -> {path}"
        elif kind == b"u" and len(fields) >= 11:
            xy, path = fields[1].decode("ascii"), _decode_path(fields[10])
            conflicted.append({"path": path, "status": xy})
            continue
        else:
            raise OrientationError("malformed_git_status:unknown_record")
        if xy[0] != ".":
            staged.append({"path": path, "status": xy[0]})
        if xy[1] != ".":
            unstaged.append({"path": path, "status": xy[1]})
    key = lambda item: (item["path"], item["status"])
    staged.sort(key=key)
    unstaged.sort(key=key)
    conflicted.sort(key=key)
    untracked.sort()
    return {
        "clean": not (staged or unstaged or untracked or conflicted),
        "staged": staged,
        "unstaged": unstaged,
        "untracked": untracked,
        "conflicted": conflicted,
    }


def _tracked_agents(root: Path, run_git: GitRunner) -> list[str]:
    paths = [_decode_path(item) for item in run_git(root, ("ls-files", "-z", "--", "*AGENTS.md")).split(b"\0") if item]
    return sorted(path for path in paths if Path(path).name == "AGENTS.md" and (root / path).is_file())


def observe_orientation(cwd: str | os.PathLike[str] = ".", *, run_git: GitRunner = _run_git) -> dict[str, Any]:
    """Return a deterministic snapshot, or fail if two observations disagree."""

    start = Path(cwd)
    root = Path(_text(run_git(start, ("rev-parse", "--show-toplevel")), "repository_root")).resolve()
    before_identity = _identity(root, run_git)
    before_status = run_git(root, ("status", "--porcelain=v2", "-z", "--untracked-files=all"))
    worktree = _parse_status(before_status)
    tracked_agents = _tracked_agents(root, run_git)
    after_status = run_git(root, ("status", "--porcelain=v2", "-z", "--untracked-files=all"))
    after_identity = _identity(root, run_git)
    if before_identity != after_identity or before_status != after_status:
        raise OrientationError("unstable_repository_observation")
    untracked_agents = sorted(path for path in worktree["untracked"] if Path(path).name == "AGENTS.md")
    head, branch, detached = before_identity
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "orientation_observed",
        "repository": {"root": str(root), "head_sha": head, "branch": branch, "detached_head": detached},
        "worktree": worktree,
        "instruction_surfaces": {
            "tracked_agents": tracked_agents,
            "untracked_agents_candidates": untracked_agents,
            "task_specific_applicability_selected": False,
        },
        "observability": {
            "observed": ["local_checkout_identity", "local_git_worktree_state", "local_agents_instruction_candidates"],
            "not_observed": ["github_pr_existence", "hosted_pr_title_or_body", "hosted_pr_head_sha", "remote_checks", "reviews_or_comments", "merge_state", "current_hosted_main"],
            "scope": "local_checkout_only",
        },
        "authority": {
            "implementation": False,
            "runtime_or_effect": False,
            "commit": False,
            "publication": False,
            "hosted_state_verification": False,
        },
        "task_state": {
            name: False for name in (
                "task_classification_selected", "preset_selected", "scaffold_selected",
                "allowed_paths_selected", "behavioral_acceptance_selected",
                "validation_profile_selected", "implementation_bootstrapped", "landing_authority_granted",
            )
        },
    }
