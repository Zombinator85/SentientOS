from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CodexLandingSupervisorPolicy:
    require_pr_landing_gate: bool = True
    max_matrix_age_seconds: int = 7200


@dataclass(frozen=True)
class CodexLandingSupervisorLaneResult:
    lane: str
    status: str
    classification: str
    likely_affected_files: tuple[str, ...]
    rerun_commands: tuple[str, ...]


@dataclass(frozen=True)
class CodexLandingSupervisorRequest:
    title: str
    intended_commit_title: str
    matrix_json_text: str
    changed_files: tuple[str, ...] = ()
    baseline_summary: dict[str, Any] | None = None
    pr_landing_gate_result: dict[str, Any] | None = None
    now_utc: datetime | None = None


@dataclass(frozen=True)
class CodexLandingSupervisorDecision:
    status: str
    decision: str
    pr_metadata_allowed: bool
    final_report_allowed: bool


@dataclass(frozen=True)
class CodexLandingSupervisorReport:
    reasons: tuple[str, ...]
    failed_lanes: tuple[CodexLandingSupervisorLaneResult, ...]


@dataclass(frozen=True)
class CodexLandingSupervisorResult:
    policy: CodexLandingSupervisorPolicy
    decision: CodexLandingSupervisorDecision
    report: CodexLandingSupervisorReport

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data


def _parse_matrix(text: str) -> dict[str, Any]:
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("matrix_json must decode to an object")
    return parsed


def _matrix_stale(matrix: dict[str, Any], *, now_utc: datetime, max_age_seconds: int) -> bool:
    generated_at = matrix.get("generated_at")
    if not isinstance(generated_at, str):
        return True
    try:
        ts = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    return (now_utc - ts.astimezone(timezone.utc)).total_seconds() > max_age_seconds


def evaluate_landing_supervisor(request: CodexLandingSupervisorRequest, policy: CodexLandingSupervisorPolicy | None = None) -> CodexLandingSupervisorResult:
    pol = policy or CodexLandingSupervisorPolicy()
    reasons: list[str] = []
    failed: list[CodexLandingSupervisorLaneResult] = []

    if request.title != request.intended_commit_title:
        reasons.append("title_mismatch")

    try:
        matrix = _parse_matrix(request.matrix_json_text)
    except Exception:
        return CodexLandingSupervisorResult(
            policy=pol,
            decision=CodexLandingSupervisorDecision("do_not_finalize", "do_not_finalize", False, False),
            report=CodexLandingSupervisorReport(reasons=("matrix_malformed",), failed_lanes=()),
        )

    now_utc = request.now_utc or datetime.now(timezone.utc)
    if _matrix_stale(matrix, now_utc=now_utc, max_age_seconds=pol.max_matrix_age_seconds):
        reasons.append("matrix_stale_or_missing_timestamp")

    required_failures = int(matrix.get("required_failure_count", 0))
    if required_failures > 0:
        reasons.append("matrix_failed")
        for lane in matrix.get("required_failures", []):
            failed.append(CodexLandingSupervisorLaneResult(lane=str(lane), status="failed", classification="repair_required_task_caused", likely_affected_files=request.changed_files, rerun_commands=(f"python -m scripts.run_tests -q {lane}", "python scripts/run_work_item_review_packet_matrix.py --summary")))

    baseline = request.baseline_summary or {}
    if int(baseline.get("new_errors", 0)) > 0:
        reasons.append("mypy_baseline_new_errors")
        failed.append(CodexLandingSupervisorLaneResult(lane="mypy_baseline", status="failed", classification="repair_required_task_caused", likely_affected_files=request.changed_files, rerun_commands=("python scripts/check_mypy_baseline.py",)))

    if policy is None and request.pr_landing_gate_result is None and pol.require_pr_landing_gate:
        reasons.append("landing_gate_missing")
    if request.pr_landing_gate_result:
        if request.pr_landing_gate_result.get("decision") != "pr_metadata_allowed":
            reasons.append("landing_gate_failed")

    if reasons:
        decision = "repair_required_task_caused" if any(r in reasons for r in ("matrix_failed", "mypy_baseline_new_errors", "landing_gate_failed")) else "do_not_finalize"
        return CodexLandingSupervisorResult(
            policy=pol,
            decision=CodexLandingSupervisorDecision(status=decision, decision=decision, pr_metadata_allowed=False, final_report_allowed=False),
            report=CodexLandingSupervisorReport(reasons=tuple(reasons), failed_lanes=tuple(failed)),
        )

    return CodexLandingSupervisorResult(
        policy=pol,
        decision=CodexLandingSupervisorDecision(status="ready_for_pr_metadata", decision="ready_for_pr_metadata", pr_metadata_allowed=True, final_report_allowed=True),
        report=CodexLandingSupervisorReport(reasons=(), failed_lanes=()),
    )


def load_json_file(path: str) -> dict[str, Any]:
    parsed = json.loads(Path(path).read_text(encoding="utf-8"))
    return parsed if isinstance(parsed, dict) else {}
