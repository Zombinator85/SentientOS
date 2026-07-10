from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Iterable

LOGGER = logging.getLogger(__name__)


def _validate_git_path(path: str) -> None:
    p = Path(path)
    if not path or path in {".", "./"}:
        raise ValueError("repository-root scope is not allowed")
    if p.is_absolute() or any(part == ".." for part in p.parts) or any(part == ".git" for part in p.parts):
        raise ValueError(f"unsafe git path: {path}")
    if any("*" in part or "?" in part or "[" in part or "]" in part for part in p.parts):
        raise ValueError(f"wildcard git path is not allowed: {path}")


def git_commit_push(
    message: str,
    *,
    paths: Iterable[str],
    repo_path: str | os.PathLike[str] | None = None,
    push: bool = False,
    remote: str | None = None,
    branch: str | None = None,
) -> bool:
    """Explicit-operator-only Git helper with exact paths and push opt-in.

    This compatibility helper is not used by ``sentientosd``. It fails closed:
    no ``paths=None`` / ``git add --all`` behavior, no inferred push remote, and
    no pushes from ``main`` or ``master``.
    """

    exact_paths = tuple(str(path).strip() for path in paths if str(path).strip())
    if not exact_paths:
        LOGGER.error("git_commit_push requires explicit non-empty paths")
        return False
    try:
        for path in exact_paths:
            _validate_git_path(path)
    except ValueError as exc:
        LOGGER.error("git path validation failed: %s", exc)
        return False

    cwd = Path(repo_path) if repo_path else Path.cwd()
    try:
        subprocess.run(("git", "add", "--", *exact_paths), cwd=cwd, check=True, capture_output=True)
        commit = subprocess.run(("git", "commit", "-m", message), cwd=cwd, capture_output=True, check=False, text=True)
    except (subprocess.CalledProcessError, OSError) as exc:
        LOGGER.error("git commit helper failed before commit completion: %s", exc)
        return False
    if commit.returncode != 0:
        LOGGER.error("git commit failed: %s", (commit.stderr or commit.stdout).strip())
        return False
    if not push:
        return True
    if not remote or not branch:
        LOGGER.error("explicit remote and branch are required for push")
        return False
    if branch in {"main", "master"}:
        LOGGER.error("refusing to push from protected branch: %s", branch)
        return False
    push_result = subprocess.run(("git", "push", remote, f"HEAD:{branch}"), cwd=cwd, capture_output=True, text=True, check=False)
    if push_result.returncode != 0:
        LOGGER.error("git push failed: %s", (push_result.stderr or push_result.stdout).strip())
        return False
    return True
