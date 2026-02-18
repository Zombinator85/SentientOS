"""GitHub merge/rebase operations for Forge merge train."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import TYPE_CHECKING
from urllib import error, request

if TYPE_CHECKING:
    from sentientos.forge_merge_train import TrainEntry


@dataclass(slots=True)
class RebaseResult:
    ok: bool
    conflict: bool
    message: str | None
    new_head_sha: str | None
    suspect_files: list[str]


@dataclass(slots=True)
class MergeResult:
    ok: bool
    conflict: bool
    message: str | None


class GitHubMergeOps:
    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = (repo_root or Path.cwd()).resolve()

    def is_branch_behind_base(self, *, entry: TrainEntry, base_branch: str) -> bool:
        branch = entry.branch
        if not branch:
            return False
        fetch = self._run(["git", "fetch", "origin", base_branch, branch])
        if fetch.returncode != 0:
            return False
        rev = self._run(["git", "rev-list", "--left-right", "--count", f"origin/{base_branch}...origin/{branch}"])
        if rev.returncode != 0:
            return False
        parts = rev.stdout.strip().split()
        if len(parts) != 2:
            return False
        behind = int(parts[0]) if parts[0].isdigit() else 0
        return behind > 0

    def rebase_branch(self, *, entry: TrainEntry, base_branch: str) -> RebaseResult:
        if entry.pr_number is None:
            return RebaseResult(ok=False, conflict=False, message="missing_pr_number", new_head_sha=None, suspect_files=[])
        if shutil.which("gh"):
            return self._rebase_with_gh(entry.pr_number, base_branch)
        return self._rebase_with_api(entry.pr_number)

    def merge_pull_request(self, *, entry: TrainEntry, strategy: str) -> MergeResult:
        if entry.pr_number is None:
            return MergeResult(ok=False, conflict=False, message="missing_pr_number")
        if shutil.which("gh"):
            return self._merge_with_gh(entry.pr_number, strategy)
        return self._merge_with_api(entry.pr_number, strategy)

    def _rebase_with_gh(self, pr_number: int, base_branch: str) -> RebaseResult:
        checkout = self._run(["gh", "pr", "checkout", str(pr_number)])
        if checkout.returncode != 0:
            return RebaseResult(ok=False, conflict=False, message=checkout.stderr.strip() or "checkout_failed", new_head_sha=None, suspect_files=[])
        fetch = self._run(["git", "fetch", "origin", base_branch])
        if fetch.returncode != 0:
            return RebaseResult(ok=False, conflict=False, message=fetch.stderr.strip() or "fetch_failed", new_head_sha=None, suspect_files=[])
        rebase = self._run(["git", "rebase", f"origin/{base_branch}"])
        if rebase.returncode != 0:
            files = self._conflict_files()
            self._run(["git", "rebase", "--abort"])
            return RebaseResult(ok=False, conflict=bool(files), message=rebase.stderr.strip() or "rebase_failed", new_head_sha=None, suspect_files=files)
        push = self._run(["git", "push", "--force-with-lease"])
        if push.returncode != 0:
            return RebaseResult(ok=False, conflict=False, message=push.stderr.strip() or "push_failed", new_head_sha=None, suspect_files=[])
        head = self._run(["git", "rev-parse", "HEAD"])
        return RebaseResult(ok=True, conflict=False, message="rebased", new_head_sha=head.stdout.strip() if head.returncode == 0 else None, suspect_files=[])

    def _rebase_with_api(self, pr_number: int) -> RebaseResult:
        repo = os.getenv("GITHUB_REPOSITORY", "")
        token = os.getenv("GITHUB_TOKEN", "")
        if not repo or not token:
            return RebaseResult(ok=False, conflict=False, message="missing_github_token", new_head_sha=None, suspect_files=[])
        url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/update-branch"
        req = request.Request(url, data=b"{}", method="PUT")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        try:
            with request.urlopen(req, timeout=20):
                return RebaseResult(ok=True, conflict=False, message="updated_via_api", new_head_sha=None, suspect_files=[])
        except error.HTTPError as exc:
            conflict = exc.code == 422
            return RebaseResult(ok=False, conflict=conflict, message=f"update_branch_http_{exc.code}", new_head_sha=None, suspect_files=[])
        except (error.URLError, TimeoutError):
            return RebaseResult(ok=False, conflict=False, message="update_branch_failed", new_head_sha=None, suspect_files=[])

    def _merge_with_gh(self, pr_number: int, strategy: str) -> MergeResult:
        flag = {"squash": "--squash", "merge": "--merge", "rebase": "--rebase"}.get(strategy, "--squash")
        cmd = ["gh", "pr", "merge", str(pr_number), flag, "--delete-branch", "--auto"]
        proc = self._run(cmd)
        if proc.returncode == 0:
            return MergeResult(ok=True, conflict=False, message="merged")
        stderr = (proc.stderr or "").lower()
        return MergeResult(ok=False, conflict="conflict" in stderr, message=proc.stderr.strip() or "merge_failed")

    def _merge_with_api(self, pr_number: int, strategy: str) -> MergeResult:
        repo = os.getenv("GITHUB_REPOSITORY", "")
        token = os.getenv("GITHUB_TOKEN", "")
        if not repo or not token:
            return MergeResult(ok=False, conflict=False, message="missing_github_token")
        method = {"squash": "squash", "merge": "merge", "rebase": "rebase"}.get(strategy, "squash")
        body = json.dumps({"merge_method": method}).encode("utf-8")
        req = request.Request(f"https://api.github.com/repos/{repo}/pulls/{pr_number}/merge", data=body, method="PUT")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        try:
            with request.urlopen(req, timeout=20) as resp:
                ok = 200 <= resp.status < 300
                return MergeResult(ok=ok, conflict=False, message="merged" if ok else "merge_failed")
        except error.HTTPError as exc:
            return MergeResult(ok=False, conflict=exc.code == 409, message=f"merge_http_{exc.code}")
        except (error.URLError, TimeoutError):
            return MergeResult(ok=False, conflict=False, message="merge_failed")

    def _conflict_files(self) -> list[str]:
        proc = self._run(["git", "diff", "--name-only", "--diff-filter=U"])
        if proc.returncode != 0:
            return []
        return [line.strip() for line in proc.stdout.splitlines() if line.strip()]

    def _run(self, cmd: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(cmd, cwd=self.repo_root, capture_output=True, text=True, check=False)
