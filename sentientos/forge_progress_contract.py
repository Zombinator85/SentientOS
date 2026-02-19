"""Contract-native Forge progress baseline emission helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from typing import Any

from sentientos.forge_outcomes import OutcomeSummary, summarize_report


@dataclass(slots=True)
class ForgeProgressRun:
    run_id: str
    created_at: str
    goal_id: str | None
    campaign_id: str | None
    before_failed: int | None
    after_failed: int | None
    progress_delta_percent: float | None
    improved: bool
    notes_truncated: list[str]


@dataclass(slots=True)
class ForgeProgressContract:
    schema_version: int
    generated_at: str
    git_sha: str
    window_size: int = 10
    last_runs: list[ForgeProgressRun] | None = None
    stagnation_alert: bool = False
    stagnation_reason: str | None = None
    last_improving_run_id: str | None = None
    last_stagnant_run_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "git_sha": self.git_sha,
            "window_size": self.window_size,
            "last_runs": [asdict(item) for item in (self.last_runs or [])],
            "stagnation_alert": self.stagnation_alert,
            "stagnation_reason": self.stagnation_reason,
            "last_improving_run_id": self.last_improving_run_id,
            "last_stagnant_run_id": self.last_stagnant_run_id,
        }


def emit_forge_progress_contract(repo_root: Path, *, window_size: int = 10) -> ForgeProgressContract:
    root = repo_root.resolve()
    reports = sorted((root / "glow/forge").glob("report_*.json"), key=lambda item: item.name)

    rows: list[ForgeProgressRun] = []
    for path in reports:
        payload = _load_json(path)
        if not payload:
            continue
        summary = summarize_report(payload)
        rows.append(_row_from_summary(summary))

    bounded_rows = rows[-max(1, window_size) :]
    stagnation_alert = len(bounded_rows) >= 3 and all(not item.improved for item in bounded_rows[-3:])
    stagnation_reason = "3 consecutive non-improving runs" if stagnation_alert else None

    last_improving_run_id = next((item.run_id for item in reversed(bounded_rows) if item.improved), None)
    last_stagnant_run_id = next((item.run_id for item in reversed(bounded_rows) if not item.improved), None)

    return ForgeProgressContract(
        schema_version=1,
        generated_at=_iso_now(),
        git_sha=_git_sha(root),
        window_size=max(1, window_size),
        last_runs=bounded_rows,
        stagnation_alert=stagnation_alert,
        stagnation_reason=stagnation_reason,
        last_improving_run_id=last_improving_run_id,
        last_stagnant_run_id=last_stagnant_run_id,
    )


def _row_from_summary(summary: OutcomeSummary) -> ForgeProgressRun:
    improved = (
        summary.last_progress_improved
        or (
            summary.ci_before_failed_count is not None
            and summary.ci_after_failed_count is not None
            and summary.ci_after_failed_count < summary.ci_before_failed_count
        )
        or (summary.progress_delta_percent is not None and summary.progress_delta_percent > 0)
    )
    return ForgeProgressRun(
        run_id=summary.run_id,
        created_at=summary.created_at,
        goal_id=summary.goal_id,
        campaign_id=summary.campaign_id,
        before_failed=summary.ci_before_failed_count,
        after_failed=summary.ci_after_failed_count,
        progress_delta_percent=summary.progress_delta_percent,
        improved=improved,
        notes_truncated=[item[:120] for item in summary.last_progress_notes[:4]],
    )


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _git_sha(repo_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--verify", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""
    return completed.stdout.strip()
