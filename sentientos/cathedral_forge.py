"""CathedralForge orchestrates repo-wide structural refactors with strict gates."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


SCHEMA_VERSION = 1
FORGE_DIR = Path("glow/forge")
CONTRACT_STATUS_PATH = Path("glow/contracts/contract_status.json")
MAX_REPORT_OUTPUT_CHARS = 4000


@dataclass(slots=True)
class ForgePhase:
    summary: str
    touched_paths_globs: list[str]
    commands_to_run: list[str]
    expected_contract_impact: str


@dataclass(slots=True)
class ForgePlan:
    schema_version: int
    generated_at: str
    goal: str
    phases: list[ForgePhase]
    risk_notes: list[str]
    rollback_notes: list[str]


@dataclass(slots=True)
class GoalProfile:
    name: str
    test_command: list[str]
    test_command_display: str


@dataclass(slots=True)
class ForgeCheckResult:
    status: str
    summary: str


@dataclass(slots=True)
class ForgeTestResult:
    status: str
    command: str
    summary: str


@dataclass(slots=True)
class ForgePreflight:
    contract_drift: ForgeCheckResult
    contract_status_path: str
    contract_status_embedded: dict[str, Any]


@dataclass(slots=True)
class ForgeReport:
    schema_version: int
    generated_at: str
    goal: str
    goal_profile: str
    git_sha: str
    plan_path: str
    preflight: ForgePreflight
    tests: ForgeTestResult
    ci_commands_run: list[str]
    command_results: list[ForgeTestResult]
    artifacts_written: list[str]
    outcome: str
    failure_reasons: list[str]
    notes: list[str]


class CathedralForge:
    """Repo-wide forge for coherent, contract-validated structural transformations."""

    def __init__(self, *, repo_root: Path | None = None, forge_dir: Path = FORGE_DIR) -> None:
        self.repo_root = (repo_root or Path.cwd()).resolve()
        self.forge_dir = forge_dir

    def plan(self, goal: str) -> ForgePlan:
        generated_at = _iso_now()
        goal_profile = resolve_goal_profile(goal)
        plan = ForgePlan(
            schema_version=SCHEMA_VERSION,
            generated_at=generated_at,
            goal=goal,
            phases=[
                ForgePhase(
                    summary="Scope and stage a coherent multi-file transformation plan.",
                    touched_paths_globs=["sentientos/**/*.py", "scripts/**/*.py", "tests/**/*.py"],
                    commands_to_run=[
                        "python -m scripts.contract_drift",
                        "python -m scripts.emit_contract_status",
                        goal_profile.test_command_display,
                    ],
                    expected_contract_impact="No unmanaged contract drift; all drift is explicit and reviewed.",
                ),
                ForgePhase(
                    summary="Apply repo-wide changes and run full contract + test gates.",
                    touched_paths_globs=["**/*.py", "**/*.json", ".github/workflows/*.yml"],
                    commands_to_run=[
                        "python -m scripts.contract_drift",
                        "python -m scripts.emit_contract_status",
                        goal_profile.test_command_display,
                    ],
                    expected_contract_impact="Contract status rollup captures new baseline compatibility.",
                ),
            ],
            risk_notes=[
                "Large refactors can increase coupling risk if not staged by domain.",
                "Any detected drift blocks completion until explicitly reconciled.",
            ],
            rollback_notes=[
                "Revert the forge commit and restore previous contract artifacts.",
                "Re-run contract drift + status + tests before retrying.",
            ],
        )
        path = self._plan_path(generated_at)
        _write_json(path, _dataclass_to_dict(plan))
        return plan

    def run(self, goal: str) -> ForgeReport:
        generated_at = _iso_now()
        goal_profile = resolve_goal_profile(goal)
        plan = self.plan(goal)
        plan_path = self._plan_path(plan.generated_at)

        ci_commands_run: list[str] = []
        command_results: list[ForgeTestResult] = []
        artifacts_written: list[str] = [str(plan_path)]
        failure_reasons: list[str] = []
        notes: list[str] = []

        contract_drift_command = "python -m scripts.contract_drift"
        ci_commands_run.append(contract_drift_command)
        drift_result = self._run_command([sys.executable, "-m", "scripts.contract_drift"])
        command_results.append(_result_from_completed("contract_drift", contract_drift_command, drift_result))
        drift_failed = drift_result.returncode != 0
        drift_summary = _summarize_command("contract_drift", drift_result)
        contract_drift_status = "fail" if drift_failed else "pass"
        if drift_failed:
            failure_reasons.append("contract_drift_failed")

        contract_status_command = "python -m scripts.emit_contract_status"
        ci_commands_run.append(contract_status_command)
        status_result = self._run_command([sys.executable, "-m", "scripts.emit_contract_status"])
        command_results.append(_result_from_completed("contract_status", contract_status_command, status_result))
        status_payload = self._load_json(self.repo_root / CONTRACT_STATUS_PATH)
        artifacts_written.append(str(CONTRACT_STATUS_PATH))
        if status_result.returncode != 0:
            failure_reasons.append("contract_status_emit_failed")
            notes.append(_summarize_command("contract_status", status_result))

        test_command = goal_profile.test_command_display
        tests_result = ForgeTestResult(status="fail", command=test_command, summary="skipped: preflight failed")

        preflight = ForgePreflight(
            contract_drift=ForgeCheckResult(status=contract_drift_status, summary=drift_summary),
            contract_status_path=str(CONTRACT_STATUS_PATH),
            contract_status_embedded=status_payload,
        )

        if not failure_reasons:
            ci_commands_run.append(test_command)
            test_run = self._run_command(goal_profile.test_command)
            command_results.append(_result_from_completed("tests", test_command, test_run))
            tests_result = ForgeTestResult(
                status="pass" if test_run.returncode == 0 else "fail",
                command=test_command,
                summary=_summarize_command("tests", test_run),
            )
            if test_run.returncode != 0:
                failure_reasons.append("tests_failed")

        outcome = "failed" if failure_reasons else "success"
        report = ForgeReport(
            schema_version=SCHEMA_VERSION,
            generated_at=generated_at,
            goal=goal,
            goal_profile=goal_profile.name,
            git_sha=self._git_sha(),
            plan_path=str(plan_path),
            preflight=preflight,
            tests=tests_result,
            ci_commands_run=ci_commands_run,
            command_results=command_results,
            artifacts_written=artifacts_written,
            outcome=outcome,
            failure_reasons=failure_reasons,
            notes=notes,
        )
        report_path = self._report_path(generated_at)
        _write_json(report_path, _dataclass_to_dict(report))
        return report

    def _plan_path(self, generated_at: str) -> Path:
        return self.forge_dir / f"plan_{_safe_timestamp(generated_at)}.json"

    def _report_path(self, generated_at: str) -> Path:
        return self.forge_dir / f"report_{_safe_timestamp(generated_at)}.json"

    def _run_command(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(command, cwd=self.repo_root, check=False, capture_output=True, text=True)

    def _git_sha(self) -> str:
        result = self._run_command(["git", "rev-parse", "--verify", "HEAD"])
        return result.stdout.strip() if result.returncode == 0 else ""

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_timestamp(iso_timestamp: str) -> str:
    return iso_timestamp.replace(":", "-")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _summarize_command(name: str, completed: subprocess.CompletedProcess[str]) -> str:
    message = completed.stdout.strip() or completed.stderr.strip()
    if not message:
        return f"{name} returncode={completed.returncode}"
    return f"{name} returncode={completed.returncode}: {message}"


def resolve_goal_profile(goal: str) -> GoalProfile:
    if goal == "forge_smoke_noop" or goal.startswith("forge_smoke_"):
        return GoalProfile(
            name="smoke_noop",
            test_command=[sys.executable, "-m", "scripts.run_tests", "-q", "tests/test_cathedral_forge.py"],
            test_command_display="python -m scripts.run_tests -q tests/test_cathedral_forge.py",
        )
    return GoalProfile(
        name="default",
        test_command=[sys.executable, "-m", "scripts.run_tests", "-q"],
        test_command_display="python -m scripts.run_tests -q",
    )


def _truncate_output(value: str) -> str:
    if len(value) <= MAX_REPORT_OUTPUT_CHARS:
        return value
    return value[:MAX_REPORT_OUTPUT_CHARS] + "\n...[truncated]"


def _result_from_completed(step: str, command: str, completed: subprocess.CompletedProcess[str]) -> ForgeTestResult:
    stdout = _truncate_output(completed.stdout or "")
    stderr = _truncate_output(completed.stderr or "")
    summary = json.dumps(
        {
            "step": step,
            "exit_code": completed.returncode,
            "stdout": stdout,
            "stderr": stderr,
        },
        sort_keys=True,
    )
    return ForgeTestResult(
        status="pass" if completed.returncode == 0 else "fail",
        command=command,
        summary=summary,
    )


def _dataclass_to_dict(value: Any) -> dict[str, Any]:
    payload = asdict(value)
    if not isinstance(payload, dict):
        raise TypeError("Expected dataclass object to serialize to dict")
    return payload
