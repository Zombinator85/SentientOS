"""CathedralForge orchestrates repo-wide structural refactors with strict gates."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any

from sentientos.forge_goals import GoalSpec, resolve_goal
from sentientos.forge_model import (
    ApplyResult,
    CommandResult,
    CommandSpec,
    ForgeCheckResult,
    ForgePhase,
    ForgePreflight,
    ForgeSession,
    ForgeTestResult,
    GoalProfile,
    merge_env,
)


SCHEMA_VERSION = 2
FORGE_DIR = Path("glow/forge")
CONTRACT_STATUS_PATH = Path("glow/contracts/contract_status.json")
MAX_REPORT_OUTPUT_CHARS = 4000


@dataclass(slots=True)
class ForgePlan:
    schema_version: int
    generated_at: str
    goal: str
    goal_id: str
    phases: list[ForgePhase]
    risk_notes: list[str]
    rollback_notes: list[str]


@dataclass(slots=True)
class ForgeReport:
    schema_version: int
    generated_at: str
    goal: str
    goal_id: str
    goal_profile: str
    git_sha: str
    plan_path: str
    preflight: ForgePreflight
    tests: ForgeTestResult
    ci_commands_run: list[str]
    session: ForgeSession
    step_results: list[CommandResult]
    artifacts_written: list[str]
    outcome: str
    failure_reasons: list[str]
    notes: list[str]
    test_failures_before: int | None
    test_failures_after: int | None
    docket_path: str | None


class CathedralForge:
    """Repo-wide forge for coherent, contract-validated structural transformations."""

    def __init__(self, *, repo_root: Path | None = None, forge_dir: Path = FORGE_DIR) -> None:
        self.repo_root = (repo_root or Path.cwd()).resolve()
        self.forge_dir = forge_dir

    def plan(self, goal: str) -> ForgePlan:
        generated_at = _iso_now()
        goal_spec = resolve_goal(goal)
        plan = ForgePlan(
            schema_version=SCHEMA_VERSION,
            generated_at=generated_at,
            goal=goal,
            goal_id=goal_spec.goal_id,
            phases=goal_spec.phases,
            risk_notes=goal_spec.risk_notes,
            rollback_notes=goal_spec.rollback_notes,
        )
        _write_json(self._plan_path(generated_at), _dataclass_to_dict(plan))
        return plan

    def run(self, goal: str) -> ForgeReport:
        generated_at = _iso_now()
        goal_spec = resolve_goal(goal)
        goal_profile = resolve_goal_profile(goal_spec)
        plan = self.plan(goal)
        plan_path = self._plan_path(plan.generated_at)
        session = self._create_session(generated_at)

        ci_commands_run: list[str] = []
        step_results: list[CommandResult] = []
        artifacts_written: list[str] = [str(plan_path)]
        failure_reasons: list[str] = []
        notes: list[str] = []
        docket_path: str | None = None
        test_failures_before: int | None = None
        test_failures_after: int | None = None

        try:
            drift_result = self._run_step(
                CommandSpec(step="contract_drift", argv=[sys.executable, "-m", "scripts.contract_drift"]),
                Path(session.root_path),
            )
            step_results.append(drift_result)
            ci_commands_run.append("python -m scripts.contract_drift")
            drift_failed = drift_result.returncode != 0
            if drift_failed:
                failure_reasons.append("contract_drift_failed")

            status_result = self._run_step(
                CommandSpec(step="contract_status", argv=[sys.executable, "-m", "scripts.emit_contract_status"]),
                Path(session.root_path),
            )
            step_results.append(status_result)
            ci_commands_run.append("python -m scripts.emit_contract_status")

            status_payload = self._load_json(Path(session.root_path) / CONTRACT_STATUS_PATH)
            artifacts_written.append(str(CONTRACT_STATUS_PATH))
            if status_result.returncode != 0:
                failure_reasons.append("contract_status_emit_failed")

            preflight = ForgePreflight(
                contract_drift=ForgeCheckResult(
                    status="fail" if drift_failed else "pass",
                    summary=_summarize_result("contract_drift", drift_result),
                ),
                contract_status_path=str(CONTRACT_STATUS_PATH),
                contract_status_embedded=status_payload,
            )

            apply_result = ApplyResult(status="skipped", step_results=[], summary="skipped: preflight failed")
            if not failure_reasons:
                apply_result = self.apply(goal_spec, session)
                step_results.extend(apply_result.step_results)
                if apply_result.status != "success":
                    failure_reasons.append("apply_failed")

                if goal_spec.goal_id == "baseline_reclamation":
                    test_failures_before = self._count_failures(step_results, "inventory_failures")
                    test_failures_after = self._count_failures(step_results, "baseline_gate")
                    choice_points = self._extract_choice_points(step_results)
                    if choice_points:
                        docket = {
                            "generated_at": generated_at,
                            "goal": goal,
                            "goal_id": goal_spec.goal_id,
                            "choices": choice_points,
                            "auto_choice_policy": "least_invasive",
                        }
                        docket_path = str(self._docket_path(generated_at))
                        _write_json(Path(docket_path), docket)
                        artifacts_written.append(docket_path)

            tests_result = ForgeTestResult(status="fail", command=goal_profile.test_command_display, summary="skipped: preflight/apply failed")
            if not failure_reasons:
                tests_step = self._run_step(CommandSpec(step="tests", argv=goal_profile.test_command), Path(session.root_path))
                step_results.append(tests_step)
                ci_commands_run.append(goal_profile.test_command_display)
                tests_result = ForgeTestResult(
                    status="pass" if tests_step.returncode == 0 else "fail",
                    command=goal_profile.test_command_display,
                    summary=_summarize_result("tests", tests_step),
                )
                if tests_step.returncode != 0:
                    failure_reasons.append("tests_failed")

            publish_notes = self._maybe_publish(goal_spec, session)
            notes.extend(publish_notes)

            outcome = "failed" if failure_reasons else "success"
            session.preserved_on_failure = bool(failure_reasons)
            git_sha = self._git_sha(Path(session.root_path))
            if not failure_reasons:
                self._cleanup_session(session)
            report = ForgeReport(
                schema_version=SCHEMA_VERSION,
                generated_at=generated_at,
                goal=goal,
                goal_id=goal_spec.goal_id,
                goal_profile=goal_profile.name,
                git_sha=git_sha,
                plan_path=str(plan_path),
                preflight=preflight,
                tests=tests_result,
                ci_commands_run=ci_commands_run,
                session=session,
                step_results=step_results,
                artifacts_written=artifacts_written,
                outcome=outcome,
                failure_reasons=failure_reasons,
                notes=notes,
                test_failures_before=test_failures_before,
                test_failures_after=test_failures_after,
                docket_path=docket_path,
            )
            _write_json(self._report_path(generated_at), _dataclass_to_dict(report))
            return report
        except Exception:
            session.preserved_on_failure = True
            raise

    def apply(self, goal: GoalSpec, session: ForgeSession) -> ApplyResult:
        if not goal.apply_commands:
            return ApplyResult(status="success", step_results=[], summary="no apply commands for this goal")
        results: list[CommandResult] = []
        for command in goal.apply_commands:
            result = self._run_step(command, Path(session.root_path))
            results.append(result)
            if result.returncode != 0:
                return ApplyResult(status="failed", step_results=results, summary=f"failed at step {command.step}")
        return ApplyResult(status="success", step_results=results, summary="all apply commands passed")

    def _create_session(self, generated_at: str) -> ForgeSession:
        session_id = _safe_timestamp(generated_at)
        worktree_root = self.repo_root / ".forge" / "worktrees"
        worktree_path = worktree_root / session_id
        branch_name = f"forge/{session_id}"
        git_dir = self.repo_root / ".git"
        if git_dir.exists():
            worktree_root.mkdir(parents=True, exist_ok=True)
            add_cmd = ["git", "worktree", "add", "--detach", str(worktree_path)]
            completed = subprocess.run(add_cmd, cwd=self.repo_root, capture_output=True, text=True, check=False)
            if completed.returncode == 0:
                return ForgeSession(session_id=session_id, root_path=str(worktree_path), strategy="git_worktree", branch_name=branch_name)
        temp_path = Path(tempfile.mkdtemp(prefix=f"forge-{session_id}-"))
        shutil.copytree(self.repo_root, temp_path / self.repo_root.name, dirs_exist_ok=True)
        session_root = temp_path / self.repo_root.name
        return ForgeSession(session_id=session_id, root_path=str(session_root), strategy="copy", branch_name=branch_name)

    def _cleanup_session(self, session: ForgeSession) -> None:
        root = Path(session.root_path)
        if session.strategy == "git_worktree" and root.exists():
            subprocess.run(["git", "worktree", "remove", "--force", str(root)], cwd=self.repo_root, check=False, capture_output=True, text=True)
            session.cleanup_performed = True
            return
        if session.strategy == "copy" and root.exists():
            shutil.rmtree(root.parent, ignore_errors=True)
            session.cleanup_performed = True

    def _run_step(self, command: CommandSpec, cwd: Path) -> CommandResult:
        env = merge_env(os.environ, command.env)
        try:
            completed = subprocess.run(
                command.argv,
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=command.timeout_seconds,
            )
            return CommandResult(
                step=command.step,
                argv=command.argv,
                cwd=str(cwd),
                env_overlay=command.env,
                timeout_seconds=command.timeout_seconds,
                returncode=completed.returncode,
                stdout=_truncate_output(completed.stdout or ""),
                stderr=_truncate_output(completed.stderr or ""),
            )
        except subprocess.TimeoutExpired as exc:
            return CommandResult(
                step=command.step,
                argv=command.argv,
                cwd=str(cwd),
                env_overlay=command.env,
                timeout_seconds=command.timeout_seconds,
                returncode=124,
                stdout=_truncate_output((exc.stdout or "") if isinstance(exc.stdout, str) else ""),
                stderr=_truncate_output((exc.stderr or "") if isinstance(exc.stderr, str) else ""),
                timed_out=True,
            )

    def _maybe_publish(self, goal: GoalSpec, session: ForgeSession) -> list[str]:
        notes: list[str] = []
        root = Path(session.root_path)
        if os.getenv("SENTIENTOS_FORGE_AUTOCOMMIT") == "1":
            message = f"[forge:{goal.goal_id}] automated forge session"
            subprocess.run(["git", "add", "-A"], cwd=root, check=False, capture_output=True, text=True)
            subprocess.run(["git", "commit", "-m", message], cwd=root, check=False, capture_output=True, text=True)
            notes.append("autocommit_enabled")
        if os.getenv("SENTIENTOS_FORGE_AUTOPR") == "1":
            payload = {
                "title": f"[forge:{goal.goal_id}] automated forge proposal",
                "body": "Generated by CathedralForge autopr path.",
                "session_root": str(root),
            }
            path = self._pr_path(_iso_now())
            _write_json(path, payload)
            notes.append(f"autopr_metadata:{path}")
        return notes

    def _count_failures(self, results: list[CommandResult], step_name: str) -> int | None:
        for result in results:
            if result.step == step_name:
                return _parse_failure_count(result.stdout + "\n" + result.stderr)
        return None

    def _extract_choice_points(self, results: list[CommandResult]) -> list[dict[str, object]]:
        choices: list[dict[str, object]] = []
        for result in results:
            text = f"{result.stdout}\n{result.stderr}"
            if "CHOICE_POINT" in text or "requires manual choice" in text:
                choices.append(
                    {
                        "step": result.step,
                        "failure_location": "unknown",
                        "suspected_cause": "ambiguous remediation path",
                        "candidate_fixes": [
                            "Fix the nearest failing assertion with deterministic expectation.",
                            "Patch fixture or import path without changing runtime semantics.",
                            "Introduce minimal compatibility shim and schedule follow-up cleanup.",
                        ],
                        "chosen_fix": "Fix the nearest failing assertion with deterministic expectation.",
                    }
                )
        return choices

    def _plan_path(self, generated_at: str) -> Path:
        return self.forge_dir / f"plan_{_safe_timestamp(generated_at)}.json"

    def _report_path(self, generated_at: str) -> Path:
        return self.forge_dir / f"report_{_safe_timestamp(generated_at)}.json"

    def _docket_path(self, generated_at: str) -> Path:
        return self.forge_dir / f"docket_{_safe_timestamp(generated_at)}.json"

    def _pr_path(self, generated_at: str) -> Path:
        return self.forge_dir / f"pr_{_safe_timestamp(generated_at)}.json"

    def _git_sha(self, cwd: Path) -> str:
        result = subprocess.run(["git", "rev-parse", "--verify", "HEAD"], cwd=cwd, capture_output=True, text=True, check=False)
        return result.stdout.strip() if result.returncode == 0 else ""

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}


def _parse_failure_count(output: str) -> int:
    for line in output.splitlines():
        compact = line.strip()
        if " failed" in compact and "=" in compact:
            tokens = compact.replace("=", " ").split()
            for idx, token in enumerate(tokens):
                if token == "failed" and idx > 0 and tokens[idx - 1].isdigit():
                    return int(tokens[idx - 1])
    return 0


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_timestamp(iso_timestamp: str) -> str:
    return iso_timestamp.replace(":", "-")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _summarize_result(name: str, result: CommandResult) -> str:
    message = result.stdout.strip() or result.stderr.strip()
    if not message:
        return f"{name} returncode={result.returncode}"
    return f"{name} returncode={result.returncode}: {message}"


def resolve_goal_profile(goal_spec: GoalSpec) -> GoalProfile:
    if goal_spec.gate_profile == "smoke_noop":
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


def _dataclass_to_dict(value: Any) -> dict[str, Any]:
    payload = asdict(value)
    if not isinstance(payload, dict):
        raise TypeError("Expected dataclass object to serialize to dict")
    return payload
