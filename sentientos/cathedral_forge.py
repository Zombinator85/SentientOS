"""CathedralForge orchestrates repo-wide structural refactors with strict gates."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any

from sentientos.ci_baseline import CI_BASELINE_PATH, emit_ci_baseline
from sentientos.forge_budget import BudgetConfig
from sentientos.forge_env import ForgeEnv, bootstrap_env
from sentientos.forge_failures import FailureCluster, HarvestResult, harvest_failures
from sentientos.forge_fixers import FixResult, apply_fix_candidate, generate_fix_candidates
from sentientos.forge_goals import GoalSpec, resolve_goal
from sentientos.forge_pr_notes import build_pr_notes
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
    baseline_harvests: list[HarvestResult] | None = None
    baseline_fixes: list[FixResult] | None = None
    baseline_budget: dict[str, int] | None = None
    ci_baseline_before: dict[str, object] | None = None
    ci_baseline_after: dict[str, object] | None = None
    progress_delta: dict[str, float | int] | None = None


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
        forge_env = bootstrap_env(Path(session.root_path))
        session.env_python_path = forge_env.python
        session.env_venv_path = forge_env.venv_path
        session.env_reused = not forge_env.created
        session.env_install_summary = forge_env.install_summary

        ci_commands_run: list[str] = []
        step_results: list[CommandResult] = []
        artifacts_written: list[str] = [str(plan_path)]
        failure_reasons: list[str] = []
        notes: list[str] = []
        docket_path: str | None = None
        test_failures_before: int | None = None
        test_failures_after: int | None = None
        baseline_harvests: list[HarvestResult] = []
        baseline_fixes: list[FixResult] = []
        baseline_budget: dict[str, int] | None = None
        ci_baseline_before: dict[str, object] | None = None
        ci_baseline_after: dict[str, object] | None = None
        progress_delta: dict[str, float | int] | None = None

        try:
            drift_result = self._run_step(
                CommandSpec(step="contract_drift", argv=[forge_env.python, "-m", "scripts.contract_drift"]),
                Path(session.root_path),
            )
            step_results.append(drift_result)
            ci_commands_run.append(f"{forge_env.python} -m scripts.contract_drift")
            drift_failed = drift_result.returncode != 0
            if drift_failed:
                failure_reasons.append("contract_drift_failed")

            status_result = self._run_step(
                CommandSpec(step="contract_status", argv=[forge_env.python, "-m", "scripts.emit_contract_status"]),
                Path(session.root_path),
            )
            step_results.append(status_result)
            ci_commands_run.append(f"{forge_env.python} -m scripts.emit_contract_status")

            status_payload = self._load_json(Path(session.root_path) / CONTRACT_STATUS_PATH)
            artifacts_written.append(str(CONTRACT_STATUS_PATH))
            if status_result.returncode != 0:
                failure_reasons.append("contract_status_emit_failed")

            env_import = self._run_step(
                CommandSpec(step="env_import_sentientos", argv=[forge_env.python, "-c", "import sentientos"]),
                Path(session.root_path),
            )
            step_results.append(env_import)
            if env_import.returncode != 0:
                failure_reasons.append("forge_env_import_failed")

            preflight = ForgePreflight(
                contract_drift=ForgeCheckResult(
                    status="fail" if drift_failed else "pass",
                    summary=_summarize_result("contract_drift", drift_result),
                ),
                contract_status_path=str(CONTRACT_STATUS_PATH),
                contract_status_embedded=status_payload,
            )

            if goal_spec.goal_id == "repo_green_storm":
                before_snapshot = emit_ci_baseline(
                    output_path=Path(session.root_path) / CI_BASELINE_PATH,
                    run_command=True,
                )
                ci_baseline_before = _dataclass_to_dict(before_snapshot)
                artifacts_written.append(str(CI_BASELINE_PATH))

            apply_result = ApplyResult(status="skipped", step_results=[], summary="skipped: preflight failed")
            if not failure_reasons:
                if goal_spec.goal_id in {"baseline_reclamation", "repo_green_storm"}:
                    (
                        apply_result,
                        test_failures_before,
                        test_failures_after,
                        docket_path,
                        baseline_harvests,
                        baseline_fixes,
                        baseline_budget,
                    ) = self._run_baseline_engine(goal, goal_spec, session, generated_at, forge_env)
                    if docket_path:
                        artifacts_written.append(docket_path)
                else:
                    apply_result = self.apply(goal_spec, session)

                step_results.extend(apply_result.step_results)
                if apply_result.status != "success":
                    failure_reasons.append("apply_failed")

            tests_result = ForgeTestResult(status="fail", command=goal_profile.test_command_display, summary="skipped: preflight/apply failed")
            if not failure_reasons:
                tests_step = self._run_step(CommandSpec(step="tests", argv=goal_profile.test_command(forge_env.python)), Path(session.root_path))
                step_results.append(tests_step)
                ci_commands_run.append(goal_profile.test_command_display)
                tests_result = ForgeTestResult(
                    status="pass" if tests_step.returncode == 0 else "fail",
                    command=goal_profile.test_command_display,
                    summary=_summarize_result("tests", tests_step),
                )
                if tests_step.returncode != 0:
                    failure_reasons.append("tests_failed")

            if goal_spec.goal_id == "repo_green_storm":
                after_snapshot = emit_ci_baseline(output_path=Path(session.root_path) / CI_BASELINE_PATH, run_command=True)
                ci_baseline_after = _dataclass_to_dict(after_snapshot)
                artifacts_written.append(str(CI_BASELINE_PATH))
                before_failed = int((ci_baseline_before or {}).get("failed_count", test_failures_before or 0))
                after_failed = int((ci_baseline_after or {}).get("failed_count", test_failures_after or 0))
                if before_failed > 0:
                    reduction_pct = ((before_failed - after_failed) / before_failed) * 100
                else:
                    reduction_pct = 0.0
                progress_delta = {
                    "failed_count_before": before_failed,
                    "failed_count_after": after_failed,
                    "reduction_pct": round(reduction_pct, 2),
                }
                if after_failed > 0 and reduction_pct >= float(os.getenv("SENTIENTOS_FORGE_PROGRESS_MIN_PCT", "30")):
                    notes.append(f"repo_green_storm_progress:{reduction_pct:.2f}%")
                if after_failed > 0:
                    failure_reasons.append("repo_green_storm_not_green")

            publish_notes = self._maybe_publish(goal_spec, session)
            notes.extend(publish_notes)
            if baseline_budget:
                notes.append(
                    f"baseline_budget:iters={baseline_budget['iterations_used']}/{baseline_budget['max_iterations']},"
                    f"fixes_per_iter={baseline_budget['max_fixes_per_iteration']},"
                    f"total_files={baseline_budget['total_files_changed']}/{baseline_budget['max_total_files_changed']}"
                )

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
                baseline_harvests=baseline_harvests or None,
                baseline_fixes=baseline_fixes or None,
                baseline_budget=baseline_budget,
                ci_baseline_before=ci_baseline_before,
                ci_baseline_after=ci_baseline_after,
                progress_delta=progress_delta,
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
            metadata = self._build_pr_metadata(goal, root)
            metadata_path = self._pr_path(_iso_now())
            _write_json(metadata_path, metadata)
            make_probe = subprocess.run(["make", "-n", "make_pr"], cwd=root, capture_output=True, text=True, check=False)
            if make_probe.returncode == 0:
                subprocess.run(["make", "make_pr"], cwd=root, capture_output=True, text=True, check=False)
                notes.append("autopr_make_pr_invoked")
            notes.append(f"autopr_metadata:{metadata_path}")
        return notes

    def _build_pr_metadata(self, goal: GoalSpec, root: Path) -> dict[str, Any]:
        changed_paths = _git_changed_paths(root)
        body = build_pr_notes(
            diff_stats=_git_diff_stats(root),
            touched_paths=changed_paths,
            key_actions=[phase.summary for phase in goal.phases],
            tests_run=["contract_drift", "emit_contract_status", goal.gate_profile],
            risks=[*goal.risk_notes, *goal.rollback_notes, f"goal_id={goal.goal_id}"],
        )
        return {
            "title": f"[forge:{goal.goal_id}] automated forge proposal",
            "body": body,
            "summary": body.splitlines()[0] if body else f"forge goal {goal.goal_id}",
            "goal_id": goal.goal_id,
            "session_root": str(root),
            "artifacts": {
                "report": str(self._report_path(_iso_now())),
                "docket": str(self._docket_path(_iso_now())),
            },
        }

    def _run_baseline_engine(
        self,
        goal: str,
        goal_spec: GoalSpec,
        session: ForgeSession,
        generated_at: str,
        forge_env: ForgeEnv,
    ) -> tuple[ApplyResult, int | None, int | None, str | None, list[HarvestResult], list[FixResult], dict[str, int]]:
        cwd = Path(session.root_path)
        budget = BudgetConfig.from_env()
        step_results: list[CommandResult] = []
        harvests: list[HarvestResult] = []
        fixes: list[FixResult] = []
        no_progress = 0
        test_failures_before: int | None = None
        test_failures_after: int | None = None
        docket_path: str | None = None
        touched_files_total: set[str] = set()

        for iteration in range(1, budget.max_iterations + 1):
            harvest_step = self._run_step(
                CommandSpec(
                    step=f"baseline_harvest_{iteration}",
                    argv=self._baseline_harvest_argv(forge_env.python, goal_spec.goal_id),
                ),
                cwd,
            )
            step_results.append(harvest_step)
            harvest = harvest_failures(harvest_step.stdout, harvest_step.stderr)
            harvests.append(harvest)

            if test_failures_before is None:
                test_failures_before = harvest.total_failed
            test_failures_after = harvest.total_failed

            if harvest.total_failed == 0:
                end_drift = self._run_step(CommandSpec(step="contract_drift_end", argv=[forge_env.python, "-m", "scripts.contract_drift"]), cwd)
                step_results.append(end_drift)
                if end_drift.returncode != 0:
                    return (
                        ApplyResult(status="failed", step_results=step_results, summary="contract drift detected after remediation"),
                        test_failures_before,
                        test_failures_after,
                        docket_path,
                        harvests,
                        fixes,
                        _budget_payload(budget, iteration, len(touched_files_total)),
                    )
                return (
                    ApplyResult(status="success", step_results=step_results, summary="baseline engine converged"),
                    test_failures_before,
                    test_failures_after,
                    docket_path,
                    harvests,
                    fixes,
                    _budget_payload(budget, iteration, len(touched_files_total)),
                )

            candidates = _prioritize_root_cause_candidates(generate_fix_candidates(harvest.clusters, cwd), harvest.clusters)
            selected = candidates[: budget.max_fixes_per_iteration]
            iteration_changed: set[str] = set()
            progress = False

            for candidate in selected:
                result = apply_fix_candidate(candidate, cwd)
                fixes.append(result)
                touched_files_total.update(result.files_changed)
                iteration_changed.update(result.files_changed)
                if result.applied:
                    progress = True

            if iteration_changed:
                self._run_optional_formatters(cwd, sorted(iteration_changed), step_results, goal_spec)
                if os.getenv("SENTIENTOS_FORGE_AUTOCOMMIT") == "1":
                    self._autocommit_iteration(cwd, goal_spec.goal_id, iteration)

            rerun_every = max(1, int(os.getenv("SENTIENTOS_FORGE_FULL_RERUN_EVERY", "2")))
            if progress:
                nodeids = [cluster.signature.nodeid for cluster in harvest.clusters if cluster.signature.nodeid and cluster.signature.nodeid != "unknown"]
                if nodeids:
                    targeted_step = self._run_step(
                        CommandSpec(
                            step=f"baseline_targeted_rerun_{iteration}",
                            argv=[forge_env.python, "-m", "scripts.run_tests", "-q", *nodeids[:20]],
                        ),
                        cwd,
                    )
                    step_results.append(targeted_step)
                    if targeted_step.returncode != 0 and iteration % rerun_every != 0:
                        continue
                if iteration % rerun_every == 0:
                    cadence_step = self._run_step(
                        CommandSpec(step=f"baseline_full_rerun_{iteration}", argv=self._baseline_harvest_argv(forge_env.python, goal_spec.goal_id)),
                        cwd,
                    )
                    step_results.append(cadence_step)

            if len(iteration_changed) > budget.max_files_changed_per_iteration or len(touched_files_total) > budget.max_total_files_changed:
                docket_path = self._emit_docket(goal, goal_spec.goal_id, generated_at, harvest.clusters, selected, "budget limits reached")
                return (
                    ApplyResult(status="failed", step_results=step_results, summary="budget exhausted by file-change caps"),
                    test_failures_before,
                    test_failures_after,
                    docket_path,
                    harvests,
                    fixes,
                    _budget_payload(budget, iteration, len(touched_files_total)),
                )

            if not progress:
                no_progress += 1
            else:
                no_progress = 0
            if no_progress >= 2:
                docket_path = self._emit_docket(goal, goal_spec.goal_id, generated_at, harvest.clusters, selected, "no progress in two consecutive iterations")
                return (
                    ApplyResult(status="failed", step_results=step_results, summary="no progress"),
                    test_failures_before,
                    test_failures_after,
                    docket_path,
                    harvests,
                    fixes,
                    _budget_payload(budget, iteration, len(touched_files_total)),
                )

        latest = harvests[-1] if harvests else HarvestResult(total_failed=0, clusters=[], raw_excerpt_truncated="")
        docket_path = self._emit_docket(goal, goal_spec.goal_id, generated_at, latest.clusters, [], "iteration budget exhausted")
        return (
            ApplyResult(status="failed", step_results=step_results, summary="iteration budget exhausted"),
            test_failures_before,
            test_failures_after,
            docket_path,
            harvests,
            fixes,
            _budget_payload(budget, budget.max_iterations, len(touched_files_total)),
        )

    def _baseline_harvest_argv(self, python_bin: str, goal_id: str = "baseline_reclamation") -> list[str]:
        default_runner = "run_tests" if goal_id == "repo_green_storm" else "pytest"
        runner = os.getenv("SENTIENTOS_FORGE_HARVEST_RUNNER", default_runner).strip().lower()
        if runner == "run_tests":
            return [python_bin, "-m", "scripts.run_tests", "-q", "--maxfail=50"]
        return [python_bin, "-m", "pytest", "-q", "--maxfail=50", "--disable-warnings"]

    def _run_optional_formatters(self, cwd: Path, files: list[str], step_results: list[CommandResult], goal_spec: GoalSpec) -> None:
        probe = subprocess.run(["ruff", "--version"], cwd=cwd, capture_output=True, text=True, check=False)
        if probe.returncode != 0:
            return
        step_results.append(self._run_step(CommandSpec(step="format_touched", argv=["ruff", "format", *files]), cwd))
        step_results.append(self._run_step(CommandSpec(step="sort_imports_touched", argv=["ruff", "check", "--select", "I", "--fix", *files]), cwd))

    def _autocommit_iteration(self, cwd: Path, goal_id: str, iteration: int) -> None:
        message = f"[forge:{goal_id}] baseline iteration {iteration}"
        subprocess.run(["git", "add", "-A"], cwd=cwd, check=False, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", message], cwd=cwd, check=False, capture_output=True, text=True)

    def _emit_docket(
        self,
        goal: str,
        goal_id: str,
        generated_at: str,
        clusters: list[FailureCluster],
        candidates: list[Any],
        why: str,
    ) -> str:
        choices: list[dict[str, object]] = []
        for cluster in clusters[:10]:
            sig = cluster.signature
            choices.append(
                {
                    "step": "baseline_reclamation",
                    "failure_location": {"file": sig.file, "line": sig.line},
                    "test_nodeid": sig.nodeid,
                    "exception_summary": f"{sig.error_type}:{sig.message_digest}",
                    "why_ambiguous": why,
                    "candidate_fixes": [candidate.description for candidate in candidates][:5],
                    "chosen_action": "deferred_for_manual_review",
                }
            )
        docket = {
            "generated_at": generated_at,
            "goal": goal,
            "goal_id": goal_id,
            "choices": choices,
            "auto_choice_policy": "least_invasive",
        }
        docket_path = self._docket_path(generated_at)
        _write_json(docket_path, docket)
        return str(docket_path)

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



def _git_changed_paths(cwd: Path) -> list[str]:
    result = subprocess.run(["git", "status", "--porcelain"], cwd=cwd, capture_output=True, text=True, check=False)
    paths: list[str] = []
    for line in result.stdout.splitlines():
        if len(line) > 3:
            paths.append(line[3:].strip())
    return paths


def _git_diff_stats(cwd: Path) -> dict[str, int]:
    result = subprocess.run(["git", "diff", "--name-status"], cwd=cwd, capture_output=True, text=True, check=False)
    stats = {"files_added": 0, "files_modified": 0, "files_removed": 0}
    for line in result.stdout.splitlines():
        if not line:
            continue
        status = line.split("	", 1)[0]
        if status.startswith("A"):
            stats["files_added"] += 1
        elif status.startswith("D"):
            stats["files_removed"] += 1
        else:
            stats["files_modified"] += 1
    return stats

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
            test_command=lambda python_bin: [python_bin, "-m", "scripts.run_tests", "-q", "tests/test_cathedral_forge.py"],
            test_command_display="python -m scripts.run_tests -q tests/test_cathedral_forge.py",
        )
    return GoalProfile(
        name="default",
        test_command=lambda python_bin: [python_bin, "-m", "scripts.run_tests", "-q"],
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


def _budget_payload(config: BudgetConfig, iterations_used: int, total_files_changed: int) -> dict[str, int]:
    return {
        "max_iterations": config.max_iterations,
        "max_fixes_per_iteration": config.max_fixes_per_iteration,
        "max_files_changed_per_iteration": config.max_files_changed_per_iteration,
        "max_total_files_changed": config.max_total_files_changed,
        "iterations_used": iterations_used,
        "total_files_changed": total_files_changed,
    }


def _prioritize_root_cause_candidates(candidates: list[Any], clusters: list[FailureCluster]) -> list[Any]:
    has_import_cluster = any(cluster.signature.error_type in {"ImportError", "ModuleNotFoundError"} for cluster in clusters)
    if not has_import_cluster:
        return candidates

    def _score(candidate: Any) -> tuple[int, str]:
        description = getattr(candidate, "description", "")
        if not isinstance(description, str):
            description = ""
        priority = 0 if "import" in description.lower() or "module" in description.lower() else 1
        return (priority, description)

    return sorted(candidates, key=_score)
