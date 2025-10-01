from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Iterable, Sequence

LOGGER = logging.getLogger(__name__)


def git_commit_push(message: str, *, paths: Iterable[str] | None = None, repo_path: str | os.PathLike[str] | None = None) -> bool:
    """Commit staged changes and push them to the upstream remote.

    The helper uses the ``git`` executable to avoid introducing an additional
    dependency on GitPython. It returns ``True`` when a new commit was created
    and pushed successfully. When there are no changes to commit the function
    logs the outcome and returns ``False``.
    """

    cwd = Path(repo_path) if repo_path else Path.cwd()
    git_args: Sequence[str]

    try:
        if paths is None:
            git_args = ("git", "add", "--all")
        else:
            git_args = ("git", "add", *paths)
        subprocess.run(git_args, cwd=cwd, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:  # pragma: no cover - surface via log
        LOGGER.error("git add failed: %s", exc.stderr.decode("utf-8", errors="ignore"))
        return False

    try:
        commit = subprocess.run(
            ("git", "commit", "-m", message),
            cwd=cwd,
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError as exc:  # pragma: no cover - environment specific
        LOGGER.error("Unable to invoke git commit: %s", exc)
        return False

    if commit.returncode != 0:
        stderr = commit.stderr or ""
        if "nothing to commit" in stderr.lower():
            LOGGER.info("No changes detected for commit.")
        else:  # pragma: no cover - surfaced through logs
            LOGGER.error("git commit failed: %s", stderr.strip())
        return False

    LOGGER.info("Created commit: %s", commit.stdout.strip())

    try:
        push = subprocess.run(("git", "push"), cwd=cwd, capture_output=True, text=True, check=False)
    except OSError as exc:  # pragma: no cover - environment specific
        LOGGER.error("Unable to invoke git push: %s", exc)
        return False

    if push.returncode != 0:
        LOGGER.error("git push failed: %s", (push.stderr or push.stdout).strip())
        return False

    LOGGER.info("Changes pushed to remote.")
    return True
