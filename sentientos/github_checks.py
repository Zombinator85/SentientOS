"""GitHub PR checks integration with gh/api/fallback modes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from typing import Any
from urllib import error, parse, request


@dataclass(slots=True)
class PRRef:
    number: int | None
    url: str
    head_sha: str
    branch: str
    created_at: str


@dataclass(slots=True)
class CheckRun:
    name: str
    status: str
    conclusion: str
    details_url: str


@dataclass(slots=True)
class PRChecks:
    pr: PRRef
    checks: list[CheckRun]
    overall: str


def detect_capabilities() -> dict[str, bool]:
    return {"gh": shutil.which("gh") is not None, "token": bool(os.getenv("GITHUB_TOKEN"))}


def fetch_pr_checks(
    pr_number: int | None = None,
    pr_url: str | None = None,
    head_sha: str | None = None,
) -> PRChecks:
    caps = detect_capabilities()
    if caps["gh"]:
        return _fetch_with_gh(pr_number=pr_number, pr_url=pr_url, head_sha=head_sha)
    if caps["token"]:
        return _fetch_with_api(pr_number=pr_number, pr_url=pr_url, head_sha=head_sha)
    ref = _infer_ref(pr_number=pr_number, pr_url=pr_url, head_sha=head_sha)
    return PRChecks(pr=ref, checks=[], overall="unknown")


def wait_for_pr_checks(
    pr_ref: PRRef,
    timeout_seconds: int,
    poll_interval_seconds: int,
) -> tuple[PRChecks, dict[str, object]]:
    started = time.monotonic()
    polls = 0
    while True:
        polls += 1
        checks = fetch_pr_checks(pr_number=pr_ref.number, pr_url=pr_ref.url, head_sha=pr_ref.head_sha)
        if checks.overall in {"success", "failure", "unknown"}:
            elapsed = time.monotonic() - started
            return checks, {
                "timed_out": False,
                "elapsed_seconds": round(elapsed, 2),
                "polls": polls,
            }
        if time.monotonic() - started >= timeout_seconds:
            elapsed = time.monotonic() - started
            return checks, {
                "timed_out": True,
                "elapsed_seconds": round(elapsed, 2),
                "polls": polls,
            }
        time.sleep(max(1, poll_interval_seconds))


def _fetch_with_gh(pr_number: int | None, pr_url: str | None, head_sha: str | None) -> PRChecks:
    pr_arg = _pr_arg(pr_number=pr_number, pr_url=pr_url, head_sha=head_sha)
    view_cmd = ["gh", "pr", "view", pr_arg, "--json", "number,url,headRefOid,headRefName,createdAt"]
    view_payload = _run_json_cmd(view_cmd)
    view_raw = view_payload if isinstance(view_payload, dict) else {}
    pr = PRRef(
        number=_as_int(view_raw.get("number")),
        url=str(view_raw.get("url", pr_url or "")),
        head_sha=str(view_raw.get("headRefOid", head_sha or "")),
        branch=str(view_raw.get("headRefName", "")),
        created_at=str(view_raw.get("createdAt", _iso_now())),
    )
    checks_cmd = ["gh", "pr", "checks", str(pr.number or pr_arg), "--json", "name,state,link"]
    checks_raw = _run_json_cmd(checks_cmd)
    rows = checks_raw if isinstance(checks_raw, list) else []
    checks = [_normalize_gh_check(row) for row in rows if isinstance(row, dict)]
    return PRChecks(pr=pr, checks=checks, overall=_overall(checks))


def _fetch_with_api(pr_number: int | None, pr_url: str | None, head_sha: str | None) -> PRChecks:
    repo = os.getenv("GITHUB_REPOSITORY", "")
    token = os.getenv("GITHUB_TOKEN", "")
    if not repo or not token:
        return PRChecks(pr=_infer_ref(pr_number=pr_number, pr_url=pr_url, head_sha=head_sha), checks=[], overall="unknown")
    number = pr_number or _parse_pr_number(pr_url or "")
    pr = _infer_ref(pr_number=number, pr_url=pr_url, head_sha=head_sha)
    if number is not None:
        pr_payload = _http_json(f"https://api.github.com/repos/{repo}/pulls/{number}", token)
        if isinstance(pr_payload, dict):
            head_payload_raw = pr_payload.get("head")
            head_payload = head_payload_raw if isinstance(head_payload_raw, dict) else {}
            pr = PRRef(
                number=number,
                url=str(pr_payload.get("html_url", pr.url)),
                head_sha=str(head_payload.get("sha", pr.head_sha)),
                branch=str(head_payload.get("ref", pr.branch)),
                created_at=str(pr_payload.get("created_at", pr.created_at)),
            )
    if not pr.head_sha:
        return PRChecks(pr=pr, checks=[], overall="unknown")
    checks_payload = _http_json(
        f"https://api.github.com/repos/{repo}/commits/{pr.head_sha}/check-runs",
        token,
    )
    checks_rows_raw = checks_payload.get("check_runs", []) if isinstance(checks_payload, dict) else []
    checks_rows = checks_rows_raw if isinstance(checks_rows_raw, list) else []
    checks = [_normalize_api_check(row) for row in checks_rows if isinstance(row, dict)]
    return PRChecks(pr=pr, checks=checks, overall=_overall(checks))


def _http_json(url: str, token: str) -> dict[str, object] | list[object]:
    req = request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    try:
        with request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (error.URLError, TimeoutError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, (dict, list)) else {}


def _run_json_cmd(argv: list[str]) -> dict[str, object] | list[object]:
    proc = subprocess.run(argv, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return {}
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, (dict, list)) else {}


def _infer_ref(pr_number: int | None, pr_url: str | None, head_sha: str | None) -> PRRef:
    return PRRef(
        number=pr_number,
        url=pr_url or "",
        head_sha=head_sha or "",
        branch="",
        created_at=_iso_now(),
    )


def _pr_arg(pr_number: int | None, pr_url: str | None, head_sha: str | None) -> str:
    if pr_number is not None:
        return str(pr_number)
    if pr_url:
        return pr_url
    if head_sha:
        return head_sha
    return ""


def _normalize_gh_check(payload: dict[str, object]) -> CheckRun:
    state = str(payload.get("state", ""))
    status, conclusion = _map_state(state)
    return CheckRun(
        name=str(payload.get("name", "unnamed")),
        status=status,
        conclusion=conclusion,
        details_url=str(payload.get("link", "")),
    )


def _normalize_api_check(payload: dict[str, object]) -> CheckRun:
    return CheckRun(
        name=str(payload.get("name", "unnamed")),
        status=str(payload.get("status", "unknown")),
        conclusion=str(payload.get("conclusion") or ""),
        details_url=str(payload.get("html_url", "")),
    )


def _map_state(state: str) -> tuple[str, str]:
    lowered = state.lower()
    if lowered in {"pass", "success", "completed"}:
        return ("completed", "success")
    if lowered in {"fail", "failure", "error", "cancelled", "timed_out"}:
        return ("completed", "failure")
    if lowered in {"pending", "queued", "in_progress", "running", "waiting"}:
        return ("in_progress", "")
    return ("unknown", "")


def _overall(checks: list[CheckRun]) -> str:
    if not checks:
        return "unknown"
    if any(item.conclusion in {"failure", "timed_out", "cancelled", "startup_failure"} for item in checks):
        return "failure"
    if all(item.conclusion == "success" for item in checks):
        return "success"
    if any(item.status in {"queued", "in_progress", "requested", "waiting", "pending"} for item in checks):
        return "pending"
    return "pending"


def _parse_pr_number(pr_url: str) -> int | None:
    match = re.search(r"/pull/(\d+)", pr_url)
    if not match:
        return None
    return _as_int(match.group(1))


def _as_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
