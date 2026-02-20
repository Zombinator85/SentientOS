"""CathedralForge orchestrates repo-wide structural refactors with strict gates."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any
import uuid

from sentientos.ci_baseline import CI_BASELINE_PATH, emit_ci_baseline
from sentientos.doctrine_identity import expected_bundle_sha256_from_receipts, local_doctrine_identity
from sentientos.event_stream import record_forge_event
from sentientos.federation_integrity import federation_integrity_gate
from sentientos.forge_budget import BudgetConfig
from sentientos.forge_env import ForgeEnv, bootstrap_env
from sentientos.integrity_incident import build_base_context, build_incident
from sentientos.integrity_quarantine import load_state as load_quarantine_state, maybe_activate_quarantine
from sentientos.forge_failures import FailureCluster, HarvestResult, harvest_failures
from sentientos.forge_fixers import FixResult, apply_fix_candidate, generate_fix_candidates
from sentientos.forge_campaigns import resolve_campaign
from sentientos.forge_goals import GoalSpec, resolve_goal
from sentientos.forge_progress import ProgressSnapshot, delta as progress_delta_from, snapshot_from_harvest
from sentientos.forge_pr_notes import build_pr_notes
from sentientos.forge_provenance import ForgeProvenance
from sentientos.github_artifacts import download_contract_bundle, find_contract_artifact_for_sha
from sentientos.receipt_anchors import maybe_verify_receipt_anchors
from sentientos.github_checks import PRChecks, PRRef, detect_capabilities, wait_for_pr_checks
from sentientos.receipt_chain import maybe_verify_receipt_chain
from sentientos.forge_transaction import (
    ForgeGitOps,
    TransactionPolicy,
    capture_snapshot,
    compare_snapshots,
    quarantine,
    rollback_session,
)
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


SCHEMA_VERSION = 3
FORGE_DIR = Path("glow/forge")
CONTRACT_STATUS_PATH = Path("glow/contracts/contract_status.json")
MAX_REPORT_OUTPUT_CHARS = 4000
MAX_BASELINE_PROGRESS_ENTRIES = 60
MAX_BASELINE_PROGRESS_NODEIDS = 10


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
    baseline_progress: list[dict[str, object]] | None = None
    ci_baseline_before: dict[str, object] | None = None
    ci_baseline_after: dict[str, object] | None = None
    progress_delta: dict[str, float | int] | None = None
    transaction_status: str = "aborted"
    regression_reasons: list[str] | None = None
    quarantine_ref: str | None = None
    rollback_performed: bool = False
    transaction_improvement_summary: str | None = None
    campaign_subreports: list[dict[str, object]] | None = None
    provenance_run_id: str | None = None
    provenance_path: str | None = None
    publish_remote: dict[str, object] | None = None
    doctrine_identity: dict[str, object] | None = None
    doctrine_source: str | None = None
    doctrine_gate_reason: str | None = None


class CathedralForge:
    """Repo-wide forge for coherent, contract-validated structural transformations."""

    def __init__(self, *, repo_root: Path | None = None, forge_dir: Path = FORGE_DIR) -> None:
        self.repo_root = (repo_root or Path.cwd()).resolve()
        self.forge_dir = forge_dir
        self.git_ops = ForgeGitOps()
        self._active_provenance: ForgeProvenance | None = None

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

    def run(self, goal: str, *, initiator: str = "manual", request_id: str | None = None, metadata: dict[str, object] | None = None) -> ForgeReport:
        if goal.startswith("campaign:"):
            return self._run_campaign(goal, initiator=initiator, request_id=request_id, metadata=metadata)
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
        session.env_cache_key = forge_env.cache_key

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
        baseline_progress: list[dict[str, object]] = []
        ci_baseline_before: dict[str, object] | None = None
        ci_baseline_after: dict[str, object] | None = None
        progress_delta: dict[str, float | int] | None = None
        transaction_status = "aborted"
        regression_reasons: list[str] = []
        quarantine_ref: str | None = None
        rollback_performed = False
        transaction_improvement_summary: str | None = None
        transaction_policy = TransactionPolicy()
        before_snapshot = None
        after_snapshot = None
        run_started_at = generated_at
        provenance = ForgeProvenance(self.repo_root, run_id=str(uuid.uuid4()))
        self._active_provenance = provenance

        try:
            if goal_profile.name != "smoke_noop" and transaction_policy.enabled:
                before_snapshot = capture_snapshot(self.repo_root, Path(session.root_path), git_ops=self.git_ops)
                ci_baseline_before = dict(before_snapshot.ci_baseline)
                provenance.add_step(
                    provenance.make_step(
                        step_id="snapshot_before",
                        kind="snapshot",
                        command={"action": "capture_snapshot", "phase": "before"},
                        cwd=str(session.root_path),
                        env_fingerprint=_env_fingerprint(),
                        started_at=_iso_now(),
                        finished_at=_iso_now(),
                        exit_code=0,
                        stdout="",
                        stderr="",
                        artifacts_written=[],
                        notes="transaction before snapshot",
                    )
                )

            drift_result = self._run_step(
                CommandSpec(
                    step="contract_drift",
                    argv=[forge_env.python, "-m", "scripts.contract_drift"],
                    timeout_seconds=self._preflight_timeout_seconds(goal_profile),
                ),
                Path(session.root_path),
            )
            step_results.append(drift_result)
            ci_commands_run.append(f"{forge_env.python} -m scripts.contract_drift")
            drift_failed = drift_result.returncode != 0
            if drift_failed:
                failure_reasons.append("contract_drift_failed")

            status_result = self._run_step(
                CommandSpec(
                    step="contract_status",
                    argv=[forge_env.python, "-m", "scripts.emit_contract_status"],
                    timeout_seconds=self._preflight_timeout_seconds(goal_profile),
                ),
                Path(session.root_path),
            )
            step_results.append(status_result)
            ci_commands_run.append(f"{forge_env.python} -m scripts.emit_contract_status")

            status_payload = self._load_json(Path(session.root_path) / CONTRACT_STATUS_PATH)
            artifacts_written.append(str(CONTRACT_STATUS_PATH))
            if status_result.returncode != 0:
                failure_reasons.append("contract_status_emit_failed")

            should_run_env_import = goal_profile.name == "smoke_noop" or os.getenv("SENTIENTOS_FORGE_REQUIRE_ENV_IMPORT", "0") == "1"
            if should_run_env_import:
                env_import = self._run_step(
                    CommandSpec(
                        step="env_import_sentientos",
                        argv=[forge_env.python, "-c", "import sentientos"],
                        timeout_seconds=self._preflight_timeout_seconds(goal_profile),
                    ),
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
                before_ci_snapshot = emit_ci_baseline(
                    output_path=Path(session.root_path) / CI_BASELINE_PATH,
                    run_command=True,
                )
                ci_baseline_before = _dataclass_to_dict(before_ci_snapshot)
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
                        baseline_progress,
                    ) = self._run_baseline_engine(goal, goal_spec, session, generated_at, forge_env)
                    baseline_progress = _cap_baseline_progress(baseline_progress)
                    if docket_path:
                        artifacts_written.append(docket_path)
                else:
                    apply_result = self.apply(goal_spec, session)

                step_results.extend(apply_result.step_results)
                if apply_result.status != "success":
                    if apply_result.summary == "no progress":
                        failure_reasons.append("no progress")
                    failure_reasons.append("apply_failed")

            tests_result = ForgeTestResult(status="fail", command=goal_profile.test_command_display, summary="skipped: preflight/apply failed")
            if not failure_reasons:
                tests_step = self._run_step(
                    CommandSpec(
                        step="tests",
                        argv=goal_profile.test_command(forge_env.python),
                        timeout_seconds=self._tests_timeout_seconds(goal_profile),
                    ),
                    Path(session.root_path),
                )
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
                before_raw = (ci_baseline_before or {}).get("failed_count", test_failures_before or 0)
                after_raw = (ci_baseline_after or {}).get("failed_count", test_failures_after or 0)
                before_failed = before_raw if isinstance(before_raw, int) else (test_failures_before or 0)
                after_failed = after_raw if isinstance(after_raw, int) else (test_failures_after or 0)
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

            if goal_profile.name != "smoke_noop" and transaction_policy.enabled:
                after_snapshot = capture_snapshot(self.repo_root, Path(session.root_path), git_ops=self.git_ops)
                ci_baseline_after = dict(after_snapshot.ci_baseline)
                provenance.add_step(
                    provenance.make_step(
                        step_id="snapshot_after",
                        kind="snapshot",
                        command={"action": "capture_snapshot", "phase": "after"},
                        cwd=str(session.root_path),
                        env_fingerprint=_env_fingerprint(),
                        started_at=_iso_now(),
                        finished_at=_iso_now(),
                        exit_code=0,
                        stdout="",
                        stderr="",
                        artifacts_written=[],
                        notes="transaction after snapshot",
                    )
                )
                regressed, regression_reasons, improved, improvement_summary = compare_snapshots(
                    before_snapshot,
                    after_snapshot,
                    policy=transaction_policy,
                )
                transaction_improvement_summary = improvement_summary
                gates_failed = bool(failure_reasons)
                if regressed or gates_failed:
                    failure_reasons.extend([reason for reason in regression_reasons if reason not in failure_reasons])
                    notes_path = self.forge_dir / f"quarantine_{_safe_timestamp(_iso_now())}.json"
                    if transaction_policy.quarantine_on_failure:
                        quarantine_ref = quarantine(
                            Path(session.root_path),
                            transaction_policy.quarantine_branch_prefix,
                            notes_path,
                            git_ops=self.git_ops,
                        )
                        if quarantine_ref:
                            artifacts_written.append(str(notes_path))
                            provenance.add_step(
                                provenance.make_step(
                                    step_id="quarantine",
                                    kind="quarantine",
                                    command={"action": "quarantine", "notes_path": str(notes_path)},
                                    cwd=str(session.root_path),
                                    env_fingerprint=_env_fingerprint(),
                                    started_at=_iso_now(),
                                    finished_at=_iso_now(),
                                    exit_code=0,
                                    stdout="",
                                    stderr="",
                                    artifacts_written=[str(notes_path)],
                                )
                            )
                    rollback_performed = rollback_session(Path(session.root_path), git_ops=self.git_ops)
                    if rollback_performed:
                        provenance.add_step(
                            provenance.make_step(
                                step_id="rollback",
                                kind="rollback",
                                command={"action": "rollback_session"},
                                cwd=str(session.root_path),
                                env_fingerprint=_env_fingerprint(),
                                started_at=_iso_now(),
                                finished_at=_iso_now(),
                                exit_code=0,
                                stdout="",
                                stderr="",
                                artifacts_written=[],
                            )
                        )
                    transaction_status = "quarantined" if quarantine_ref else "rolled_back"
                elif improved:
                    transaction_status = "committed"
                else:
                    transaction_status = "aborted"
            else:
                transaction_status = "aborted"

            publish_notes: list[str] = []
            publish_remote: dict[str, object] | None = None
            doctrine_identity: dict[str, object] | None = None
            doctrine_source: str | None = None
            doctrine_gate_reason: str | None = None
            eligible_for_publish = not failure_reasons and transaction_status == "committed"
            if eligible_for_publish:
                publish_notes, publish_remote = self._maybe_publish(
                    goal_spec,
                    session,
                    improvement_summary=transaction_improvement_summary,
                    ci_baseline_before=ci_baseline_before,
                    ci_baseline_after=ci_baseline_after,
                    metadata=metadata,
                )
                doctrine_identity_raw = publish_remote.get("doctrine_identity") if isinstance(publish_remote, dict) else None
                doctrine_identity = doctrine_identity_raw if isinstance(doctrine_identity_raw, dict) else None
                doctrine_source = str(publish_remote.get("doctrine_source")) if isinstance(publish_remote, dict) and publish_remote.get("doctrine_source") is not None else None
                doctrine_gate_reason = str(publish_remote.get("doctrine_gate_reason")) if isinstance(publish_remote, dict) and publish_remote.get("doctrine_gate_reason") is not None else None
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
                baseline_progress=baseline_progress or None,
                ci_baseline_before=ci_baseline_before,
                ci_baseline_after=ci_baseline_after,
                progress_delta=progress_delta,
                transaction_status=transaction_status,
                regression_reasons=regression_reasons or None,
                quarantine_ref=quarantine_ref,
                rollback_performed=rollback_performed,
                transaction_improvement_summary=transaction_improvement_summary,
                publish_remote=publish_remote,
                doctrine_identity=doctrine_identity,
                doctrine_source=doctrine_source,
                doctrine_gate_reason=doctrine_gate_reason,
            )
            run_finished_at = _iso_now()
            header = provenance.build_header(
                started_at=run_started_at,
                finished_at=run_finished_at,
                initiator=initiator,
                request_id=request_id,
                goal=goal,
                goal_id=goal_spec.goal_id,
                campaign_id=(goal.split(":", 1)[1] if goal.startswith("campaign:") else None),
                transaction_status=transaction_status,
                quarantine_ref=quarantine_ref,
            )
            provenance_path, _bundle, _chain = provenance.finalize(
                header=header,
                env_cache_key=session.env_cache_key,
                before_snapshot=before_snapshot,
                after_snapshot=after_snapshot,
                artifacts=[*artifacts_written, str(self._report_path(generated_at))],
            )
            report.provenance_run_id = provenance.run_id
            report.provenance_path = str(provenance_path)
            _write_json(self._report_path(generated_at), _dataclass_to_dict(report))
            self._active_provenance = None
            return report
        except Exception:
            session.preserved_on_failure = True
            self._active_provenance = None
            raise

    def _run_campaign(self, goal: str, *, initiator: str = "manual", request_id: str | None = None, metadata: dict[str, object] | None = None) -> ForgeReport:
        campaign_id = goal.split(":", 1)[1] if ":" in goal else ""
        campaign = resolve_campaign(campaign_id)
        if campaign is None:
            return self.run("forge_smoke_noop")

        notes: list[str] = [f"campaign_id:{campaign.campaign_id}"]
        failure_reasons: list[str] = []
        artifacts: list[str] = []
        step_results: list[CommandResult] = []
        subreports: list[dict[str, object]] = []
        last_report: ForgeReport | None = None
        transaction_policy = TransactionPolicy()
        before = capture_snapshot(self.repo_root, self.repo_root, git_ops=self.git_ops)

        for campaign_goal in campaign.goals:
            report = self.run(campaign_goal, initiator=initiator, request_id=request_id, metadata=metadata)
            last_report = report
            subreports.append({"goal": campaign_goal, "outcome": report.outcome, "report_generated_at": report.generated_at})
            notes.append(f"campaign_goal:{campaign_goal}:{report.outcome}")
            artifacts.append(report.plan_path)
            if report.docket_path:
                artifacts.append(report.docket_path)
            if report.outcome != "success":
                failure_reasons.append(f"campaign_goal_failed:{campaign_goal}")
                if report.docket_path and "no progress" in report.failure_reasons:
                    notes.append(f"campaign_goal:{campaign_goal}:no_progress:{report.docket_path}")
                if "no progress" in report.failure_reasons:
                    summary = _summarize_baseline_progress(report.baseline_progress)
                    if summary:
                        notes.append(f"campaign_goal:{campaign_goal}:no_progress_detail:{summary}")
                if campaign.stop_on_failure:
                    break

        generated_at = _iso_now()
        if last_report is None:
            return self.run("forge_smoke_noop")

        after = capture_snapshot(self.repo_root, self.repo_root, git_ops=self.git_ops)
        regressed, regression_reasons, improved, improvement_summary = compare_snapshots(before, after, policy=transaction_policy)
        quarantine_ref: str | None = None
        rollback_performed = False
        transaction_status = "aborted"
        if regressed or failure_reasons:
            failure_reasons.extend([reason for reason in regression_reasons if reason not in failure_reasons])
            notes_path = self.forge_dir / f"quarantine_{_safe_timestamp(generated_at)}.json"
            if transaction_policy.quarantine_on_failure:
                quarantine_ref = quarantine(self.repo_root, transaction_policy.quarantine_branch_prefix, notes_path, git_ops=self.git_ops)
                if quarantine_ref:
                    artifacts.append(str(notes_path))
            rollback_performed = rollback_session(self.repo_root, git_ops=self.git_ops)
            transaction_status = "quarantined" if quarantine_ref else "rolled_back"
        elif improved:
            transaction_status = "committed"

        campaign_provenance = ForgeProvenance(self.repo_root, run_id=str(uuid.uuid4()))
        campaign_header = campaign_provenance.build_header(
            started_at=before.timestamp,
            finished_at=generated_at,
            initiator=initiator,
            request_id=request_id,
            goal=goal,
            goal_id=goal,
            campaign_id=campaign_id,
            transaction_status=transaction_status,
            quarantine_ref=quarantine_ref,
        )
        campaign_step = campaign_provenance.make_step(
            step_id="campaign_summary",
            kind="apply",
            command={"action": "campaign", "goals": list(campaign.goals)},
            cwd=str(self.repo_root),
            env_fingerprint=_env_fingerprint(),
            started_at=before.timestamp,
            finished_at=generated_at,
            exit_code=0 if not failure_reasons else 1,
            stdout=json.dumps(subreports, sort_keys=True),
            stderr="",
            artifacts_written=artifacts,
            notes="campaign aggregate",
        )
        campaign_provenance.add_step(campaign_step, stdout=json.dumps(subreports, sort_keys=True), stderr="")
        campaign_prov_path, _campaign_bundle, _campaign_chain = campaign_provenance.finalize(
            header=campaign_header,
            env_cache_key=last_report.session.env_cache_key,
            before_snapshot=before,
            after_snapshot=after,
            artifacts=artifacts,
        )

        return ForgeReport(
            schema_version=SCHEMA_VERSION,
            generated_at=generated_at,
            goal=goal,
            goal_id=goal,
            goal_profile="campaign",
            git_sha=last_report.git_sha,
            plan_path=last_report.plan_path,
            preflight=last_report.preflight,
            tests=last_report.tests,
            ci_commands_run=last_report.ci_commands_run,
            session=last_report.session,
            step_results=step_results,
            artifacts_written=artifacts,
            outcome="failed" if failure_reasons else "success",
            failure_reasons=failure_reasons,
            notes=notes,
            test_failures_before=before.ci_baseline.get("failed_count") if isinstance(before.ci_baseline.get("failed_count"), int) else None,
            test_failures_after=after.ci_baseline.get("failed_count") if isinstance(after.ci_baseline.get("failed_count"), int) else None,
            docket_path=last_report.docket_path,
            baseline_harvests=last_report.baseline_harvests,
            baseline_fixes=last_report.baseline_fixes,
            baseline_budget=last_report.baseline_budget,
            baseline_progress=last_report.baseline_progress,
            ci_baseline_before=before.ci_baseline,
            ci_baseline_after=after.ci_baseline,
            progress_delta=last_report.progress_delta,
            transaction_status=transaction_status,
            regression_reasons=regression_reasons or None,
            quarantine_ref=quarantine_ref,
            rollback_performed=rollback_performed,
            transaction_improvement_summary=improvement_summary,
            campaign_subreports=subreports,
            provenance_run_id=campaign_provenance.run_id,
            provenance_path=str(campaign_prov_path),
        )

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
        started_at = _iso_now()
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
            result = CommandResult(
                step=command.step,
                argv=command.argv,
                cwd=str(cwd),
                env_overlay=command.env,
                timeout_seconds=command.timeout_seconds,
                returncode=completed.returncode,
                stdout=_truncate_output(completed.stdout or ""),
                stderr=_truncate_output(completed.stderr or ""),
            )
            self._record_provenance_step(command=command, cwd=cwd, env=env, started_at=started_at, finished_at=_iso_now(), result=result)
            return result
        except subprocess.TimeoutExpired as exc:
            result = CommandResult(
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
            self._record_provenance_step(command=command, cwd=cwd, env=env, started_at=started_at, finished_at=_iso_now(), result=result)
            return result

    def _record_provenance_step(
        self,
        *,
        command: CommandSpec,
        cwd: Path,
        env: dict[str, str],
        started_at: str,
        finished_at: str,
        result: CommandResult,
    ) -> None:
        if self._active_provenance is None:
            return
        kind = _step_kind(command.step)
        step = self._active_provenance.make_step(
            step_id=command.step,
            kind=kind,
            command={"argv": command.argv, "step": command.step},
            cwd=str(cwd),
            env_fingerprint=_env_fingerprint(env),
            started_at=started_at,
            finished_at=finished_at,
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            artifacts_written=[],
            notes="timeout" if result.timed_out else "",
        )
        self._active_provenance.add_step(step, stdout=result.stdout, stderr=result.stderr)



    def _preflight_timeout_seconds(self, goal_profile: GoalProfile) -> int:
        if goal_profile.name == "smoke_noop":
            return max(1, int(os.getenv("SENTIENTOS_FORGE_SMOKE_TIMEOUT_SECONDS", "30")))
        return 600

    def _tests_timeout_seconds(self, goal_profile: GoalProfile) -> int:
        if goal_profile.name == "smoke_noop":
            return max(1, int(os.getenv("SENTIENTOS_FORGE_SMOKE_TIMEOUT_SECONDS", "30")))
        return 600

    def _maybe_publish(
        self,
        goal: GoalSpec,
        session: ForgeSession,
        *,
        improvement_summary: str | None,
        ci_baseline_before: dict[str, object] | None,
        ci_baseline_after: dict[str, object] | None,
        metadata: dict[str, object] | None,
    ) -> tuple[list[str], dict[str, object]]:
        notes: list[str] = []
        remote: dict[str, object] = {
            "pr_url": None,
            "pr_number": None,
            "head_sha": None,
            "checks_overall": "unknown",
            "checks_summary": [],
            "automerge_attempted": False,
            "automerge_result": "not_attempted",
            "canary_timeout": False,
            "doctrine_identity": {},
            "doctrine_source": "local",
            "doctrine_gate_reason": "not_checked",
        }
        root = Path(session.root_path)
        quarantine = load_quarantine_state(root)
        if quarantine.active and not quarantine.allow_publish:
            notes.append("quarantine_active")
            remote["automerge_result"] = "quarantine_active"
            remote["quarantine_active"] = True
            return notes, remote
        doctrine = self._load_json(root / "glow/contracts/stability_doctrine.json")
        audit_failures = _audit_integrity_failures(doctrine)
        if audit_failures:
            docket_path = self.forge_dir / f"publish_audit_block_{_safe_timestamp(_iso_now())}.json"
            docket_payload = {
                "kind": "publish_blocked_audit_integrity",
                "goal_id": goal.goal_id,
                "failing_fields": audit_failures,
                "recommended_repair": "campaign:stability_recovery_full",
            }
            _write_json(docket_path, docket_payload)
            notes.append("publish_blocked_audit_integrity")
            notes.append(f"publish_audit_docket:{docket_path}")
            if self._active_provenance is not None:
                payload = json.dumps(docket_payload, sort_keys=True)
                step = self._active_provenance.make_step(
                    step_id="publish_blocked_audit_integrity",
                    kind="publish",
                    command={"action": "publish_blocked_audit_integrity"},
                    cwd=str(root),
                    env_fingerprint=_env_fingerprint(),
                    started_at=_iso_now(),
                    finished_at=_iso_now(),
                    exit_code=1,
                    stdout=payload,
                    stderr="",
                    artifacts_written=[str(docket_path)],
                )
                self._active_provenance.add_step(step, stdout=payload, stderr="")
            return notes, remote
        if os.getenv("SENTIENTOS_FORGE_ALLOW_AUTOPUBLISH", "0") != "1":
            return notes, remote
        sentinel_triggered = os.getenv("SENTIENTOS_FORGE_SENTINEL_TRIGGERED", "0") == "1"
        if sentinel_triggered:
            if os.getenv("SENTIENTOS_FORGE_SENTINEL_ALLOW_AUTOPUBLISH", "0") != "1":
                return notes, remote
            if os.getenv("SENTIENTOS_FORGE_SENTINEL_ALLOW_AUTOMERGE", "0") != "1":
                notes.append("sentinel_automerge_disallowed")
        if os.getenv("SENTIENTOS_FORGE_AUTOCOMMIT") == "1":
            delta_before = ci_baseline_before.get("failed_count") if isinstance(ci_baseline_before, dict) else None
            delta_after = ci_baseline_after.get("failed_count") if isinstance(ci_baseline_after, dict) else None
            message = f"[forge:{goal.goal_id}] transaction {improvement_summary or 'improved'} ci_delta={delta_before}->{delta_after}"
            subprocess.run(["git", "add", "-A"], cwd=root, check=False, capture_output=True, text=True)
            subprocess.run(["git", "commit", "-m", message], cwd=root, check=False, capture_output=True, text=True)
            notes.append("autocommit_enabled")

        pr_ref = PRRef(number=None, url="", head_sha=self._git_sha(root), branch=session.branch_name, created_at=_iso_now())
        if os.getenv("SENTIENTOS_FORGE_AUTOPR") == "1":
            metadata_payload = self._build_pr_metadata(goal, root, improvement_summary=improvement_summary, ci_baseline_before=ci_baseline_before, ci_baseline_after=ci_baseline_after)
            metadata_path = self._pr_path(_iso_now())
            _write_json(metadata_path, metadata_payload)
            make_probe = subprocess.run(["make", "-n", "make_pr"], cwd=root, capture_output=True, text=True, check=False)
            if make_probe.returncode == 0:
                subprocess.run(["make", "make_pr"], cwd=root, capture_output=True, text=True, check=False)
                notes.append("autopr_make_pr_invoked")
            notes.append(f"autopr_metadata:{metadata_path}")
            pr_ref = _extract_pr_ref(metadata_payload, default=pr_ref)
            remote["pr_url"] = pr_ref.url or None
            remote["pr_number"] = pr_ref.number
            remote["head_sha"] = pr_ref.head_sha or None
            if self._active_provenance is not None:
                payload = json.dumps({"pr": _dataclass_to_dict(pr_ref), "metadata_path": str(metadata_path)}, sort_keys=True)
                step = self._active_provenance.make_step(
                    step_id="publish_pr_created",
                    kind="publish",
                    command={"action": "create_pr"},
                    cwd=str(root),
                    env_fingerprint=_env_fingerprint(),
                    started_at=_iso_now(),
                    finished_at=_iso_now(),
                    exit_code=0,
                    stdout=payload,
                    stderr="",
                    artifacts_written=[str(metadata_path)],
                )
                self._active_provenance.add_step(step, stdout=payload, stderr="")

        canary_enabled = os.getenv("SENTIENTOS_FORGE_CANARY_PUBLISH", "0") == "1"
        timeout_seconds = max(1, int(os.getenv("SENTIENTOS_FORGE_GH_TIMEOUT_SECONDS", "1800")))
        poll_seconds = max(1, int(os.getenv("SENTIENTOS_FORGE_GH_POLL_SECONDS", "20")))
        auto_merge = os.getenv("SENTIENTOS_FORGE_AUTOMERGE", "0") == "1"
        if sentinel_triggered and os.getenv("SENTIENTOS_FORGE_SENTINEL_ALLOW_AUTOMERGE", "0") != "1":
            auto_merge = False

        if canary_enabled:
            caps = detect_capabilities()
            if not any(caps.values()):
                notes.append("remote_checks_unavailable")
                remote["checks_overall"] = "remote_checks_unavailable"
            else:
                checks, timing = wait_for_pr_checks(pr_ref, timeout_seconds=timeout_seconds, poll_interval_seconds=poll_seconds)
                remote["checks_overall"] = checks.overall
                remote["checks_summary"] = _checks_summary(checks)
                remote["canary_timeout"] = bool(timing.get("timed_out"))
                if self._active_provenance is not None:
                    payload = json.dumps({"checks": _checks_to_dict(checks), "timing": timing}, sort_keys=True)
                    step = self._active_provenance.make_step(
                        step_id="publish_checks_polled",
                        kind="publish",
                        command={"action": "wait_for_pr_checks", "timeout_seconds": timeout_seconds, "poll_interval_seconds": poll_seconds},
                        cwd=str(root),
                        env_fingerprint=_env_fingerprint(),
                        started_at=_iso_now(),
                        finished_at=_iso_now(),
                        exit_code=0,
                        stdout=payload,
                        stderr="",
                        artifacts_written=[],
                    )
                    self._active_provenance.add_step(step, stdout=payload, stderr="")

                if timing.get("timed_out") or checks.overall == "failure":
                    notes.append("held_failed_checks")
                    quarantine_path = self.forge_dir / f"quarantine_{_safe_timestamp(_iso_now())}.json"
                    quarantine_payload = {
                        "kind": "publish_checks",
                        "pr_url": checks.pr.url,
                        "pr_number": checks.pr.number,
                        "overall": checks.overall,
                        "timed_out": bool(timing.get("timed_out")),
                        "checks": [_dataclass_to_dict(item) for item in checks.checks],
                    }
                    _write_json(quarantine_path, quarantine_payload)
                    notes.append(f"publish_quarantine:{quarantine_path}")
                    if metadata and metadata.get("sentinel_triggered"):
                        notes.append("sentinel_cooldown_extension_requested")
                elif checks.overall == "success":
                    remote_gate_ok = True
                    require_remote = os.getenv("SENTIENTOS_FORGE_REQUIRE_REMOTE_DOCTRINE", "0") == "1"
                    artifact = find_contract_artifact_for_sha(checks.pr.number, checks.pr.head_sha)
                    if artifact is None:
                        notes.append("publish_contract_artifact_missing")
                        remote["doctrine_source"] = "local"
                        local_identity = local_doctrine_identity(root, fallback_head_sha=checks.pr.head_sha)
                        expected_bundle = expected_bundle_sha256_from_receipts(root)
                        enforce_identity = os.getenv("SENTIENTOS_DOCTRINE_IDENTITY_ENFORCE", "0") == "1"
                        gate_reason = "remote_missing_fallback"
                        if expected_bundle and local_identity.bundle_sha256 and expected_bundle != local_identity.bundle_sha256:
                            gate_reason = "local_doctrine_identity_mismatch"
                            notes.append("local_doctrine_identity_mismatch")
                            if enforce_identity:
                                remote_gate_ok = False
                                notes.append("publish_remote_doctrine_gated")
                        remote["doctrine_gate_reason"] = gate_reason
                        remote["doctrine_identity"] = local_identity.to_dict()
                        if self._active_provenance is not None:
                            step = self._active_provenance.make_step(
                                step_id="publish_contract_artifact_missing",
                                kind="publish",
                                command={"action": "find_contract_artifact", "sha": checks.pr.head_sha},
                                cwd=str(root),
                                env_fingerprint=_env_fingerprint(),
                                started_at=_iso_now(),
                                finished_at=_iso_now(),
                                exit_code=1,
                                stdout="",
                                stderr="artifact_not_found",
                                artifacts_written=[],
                            )
                            self._active_provenance.add_step(step, stdout="", stderr="artifact_not_found")
                        if require_remote:
                            remote_gate_ok = False
                            notes.append("remote_doctrine_required_missing")
                    else:
                        notes.append("publish_contract_artifact_found")
                        bundle = download_contract_bundle(artifact, root / "glow/contracts/remote")
                        notes.append("publish_contract_bundle_downloaded")
                        artifact_details: dict[str, object] = {
                            "name": artifact.name,
                            "run_id": artifact.run_id,
                            "created_at": artifact.created_at,
                            "sha": artifact.sha,
                            "selected_via": artifact.selected_via,
                        }
                        remote["contract_artifact"] = artifact_details
                        remote["doctrine_source"] = "remote"
                        doctrine = bundle.parsed.get("stability_doctrine.json", {})
                        remote_doctrine_failures = _audit_integrity_failures(doctrine)
                        bundle_corrupt = _bundle_corruption_errors(bundle)
                        metadata_mismatch = _bundle_metadata_mismatch(bundle)
                        manifest_missing = _bundle_manifest_missing(bundle)
                        manifest_mismatch = _bundle_manifest_mismatch(bundle)
                        remote["bundle_errors"] = bundle.errors[:8]
                        metadata_sha = None
                        if bundle.metadata:
                            raw_metadata_sha = bundle.metadata.get("sha") or bundle.metadata.get("git_sha")
                            if isinstance(raw_metadata_sha, str):
                                metadata_sha = raw_metadata_sha
                        remote["metadata_sha"] = metadata_sha
                        remote["metadata_ok"] = bundle.metadata_ok
                        remote["manifest_ok"] = bool(getattr(bundle, "manifest_ok", False))
                        remote["bundle_sha256"] = str(getattr(bundle, "bundle_sha256", ""))
                        raw_failing_paths = getattr(bundle, "failing_hash_paths", [])
                        remote["failing_hash_paths"] = [str(item) for item in raw_failing_paths[:8]] if isinstance(raw_failing_paths, list) else []
                        remote["mirror_used"] = bool(getattr(bundle, "mirror_used", False))
                        remote["doctrine_identity"] = {
                            "head_sha": checks.pr.head_sha,
                            "bundle_sha256": remote["bundle_sha256"],
                            "artifact_name": artifact.name,
                            "run_id": artifact.run_id,
                            "selected_via": artifact.selected_via,
                            "mirror_used": remote["mirror_used"],
                            "metadata_ok": remote["metadata_ok"],
                            "manifest_ok": remote["manifest_ok"],
                        }
                        if bundle_corrupt:
                            remote_gate_ok = False
                            remote["doctrine_gate_reason"] = "remote_doctrine_corrupt_bundle"
                            notes.append("publish_remote_doctrine_gated")
                            notes.append("remote_doctrine_corrupt_bundle")
                        elif manifest_missing:
                            remote_gate_ok = False
                            remote["doctrine_gate_reason"] = "remote_doctrine_manifest_missing"
                            notes.append("publish_remote_doctrine_gated")
                            notes.append("remote_doctrine_manifest_missing")
                        elif manifest_mismatch:
                            remote_gate_ok = False
                            remote["doctrine_gate_reason"] = "remote_doctrine_manifest_mismatch"
                            notes.append("publish_remote_doctrine_gated")
                            notes.append("remote_doctrine_manifest_mismatch")
                        elif metadata_mismatch:
                            remote_gate_ok = False
                            remote["doctrine_gate_reason"] = "remote_doctrine_metadata_mismatch"
                            notes.append("publish_remote_doctrine_gated")
                            notes.append("remote_doctrine_metadata_mismatch")
                        elif remote_doctrine_failures:
                            remote_gate_ok = False
                            remote["doctrine_gate_reason"] = "remote_doctrine_failed"
                            notes.append("publish_remote_doctrine_gated")
                            notes.append("remote_doctrine_failed")
                        else:
                            remote["doctrine_gate_reason"] = "remote_doctrine_passed"
                        if self._active_provenance is not None:
                            payload = json.dumps({"artifact": remote["contract_artifact"], "bundle_errors": bundle.errors, "doctrine_failures": remote_doctrine_failures}, sort_keys=True)
                            step = self._active_provenance.make_step(
                                step_id="publish_contract_bundle_downloaded",
                                kind="publish",
                                command={"action": "download_contract_bundle", "sha": checks.pr.head_sha},
                                cwd=str(root),
                                env_fingerprint=_env_fingerprint(),
                                started_at=_iso_now(),
                                finished_at=_iso_now(),
                                exit_code=0 if not bundle.errors else 1,
                                stdout=payload,
                                stderr="",
                                artifacts_written=list(bundle.paths.values()),
                            )
                            self._active_provenance.add_step(step, stdout=payload, stderr="")
                    if not remote_gate_ok:
                        auto_merge = False
                        notes.append("held_remote_doctrine")
                    chain_check, chain_enforced, chain_warned = maybe_verify_receipt_chain(root, context="canary_publish")
                    if chain_check is not None and not chain_check.ok:
                        remote["receipt_chain"] = chain_check.to_dict()
                        if chain_enforced:
                            auto_merge = False
                            remote["automerge_result"] = "receipt_chain_broken"
                            notes.append("receipt_chain_broken")
                            record_forge_event({"event": "canary_receipt_chain_blocked", "level": "warning", "chain": chain_check.to_dict()})
                            self._record_integrity_incident(
                                root,
                                triggers=["receipt_chain_broken"],
                                enforcement_mode="enforce",
                                severity="enforced",
                                context={"receipt_chain": chain_check.to_dict()},
                                evidence_paths=["glow/forge/receipts/receipts_index.jsonl"],
                            )
                        elif chain_warned:
                            notes.append("receipt_chain_warning")
                            record_forge_event({"event": "canary_receipt_chain_warning", "level": "warning", "chain": chain_check.to_dict()})
                    federation_gate = federation_integrity_gate(root, context="canary_publish")
                    remote["federation_integrity"] = federation_gate
                    if bool(federation_gate.get("blocked")):
                        auto_merge = False
                        remote["automerge_result"] = "federation_integrity_diverged"
                        notes.append("federation_integrity_diverged")
                        record_forge_event({"event": "canary_federation_integrity_blocked", "level": "warning", "integrity": federation_gate})
                        self._record_integrity_incident(
                            root,
                            triggers=["federation_integrity_diverged"],
                            enforcement_mode="enforce",
                            severity="enforced",
                            context={"federation_integrity": federation_gate},
                            evidence_paths=["glow/federation/integrity_snapshot.json", "glow/federation/peer_integrity"],
                        )

                    anchor_check, anchor_enforced, anchor_warned = maybe_verify_receipt_anchors(root, context="canary_publish")
                    if anchor_check is not None and not anchor_check.ok:
                        remote["receipt_anchors"] = anchor_check.to_dict()
                        anchor_reason = "receipt_anchor_missing" if anchor_check.status == "missing" else "receipt_anchor_invalid"
                        if anchor_enforced:
                            auto_merge = False
                            remote["automerge_result"] = anchor_reason
                            notes.append(anchor_reason)
                            record_forge_event({"event": "canary_receipt_anchor_blocked", "level": "warning", "anchors": anchor_check.to_dict()})
                            self._record_integrity_incident(
                                root,
                                triggers=[anchor_reason],
                                enforcement_mode="enforce",
                                severity="enforced",
                                context={"receipt_anchors": anchor_check.to_dict()},
                                evidence_paths=["glow/forge/receipts/anchors/anchors_index.jsonl"],
                            )
                        elif anchor_warned:
                            notes.append("receipt_anchor_warning")
                            record_forge_event({"event": "canary_receipt_anchor_warning", "level": "warning", "anchors": anchor_check.to_dict()})
                    if auto_merge:
                        remote["automerge_attempted"] = True
                        merged = self._merge_pr(checks.pr)
                        remote["automerge_result"] = "merged" if merged else "merge_failed"
                        notes.append("automerge_merged" if merged else "automerge_failed")
                    elif remote_gate_ok:
                        notes.append("ready_to_merge")

        if self._active_provenance is not None:
            outcome_payload = json.dumps({"remote": remote, "notes": notes}, sort_keys=True)
            step = self._active_provenance.make_step(
                step_id="publish_outcome",
                kind="publish",
                command={"action": "publish_outcome"},
                cwd=str(root),
                env_fingerprint=_env_fingerprint(),
                started_at=_iso_now(),
                finished_at=_iso_now(),
                exit_code=0,
                stdout=outcome_payload,
                stderr="",
                artifacts_written=[],
            )
            self._active_provenance.add_step(step, stdout=outcome_payload, stderr="")

        return notes, remote

    def _record_integrity_incident(
        self,
        repo_root: Path,
        *,
        triggers: list[str],
        enforcement_mode: str,
        severity: str,
        context: dict[str, object],
        evidence_paths: list[str],
    ) -> None:
        incident = build_incident(
            triggers=triggers,
            enforcement_mode=enforcement_mode,
            severity=severity,
            context={**build_base_context(repo_root), **context},
            evidence_paths=evidence_paths,
            suggested_actions=[
                "python scripts/quarantine_status.py",
                "python scripts/quarantine_ack.py --note acknowledged",
                "python scripts/quarantine_clear.py --note recovered",
            ],
        )
        maybe_activate_quarantine(repo_root, triggers, incident)

    def _build_pr_metadata(
        self,
        goal: GoalSpec,
        root: Path,
        *,
        improvement_summary: str | None,
        ci_baseline_before: dict[str, object] | None,
        ci_baseline_after: dict[str, object] | None,
    ) -> dict[str, Any]:
        changed_paths = _git_changed_paths(root)
        body = build_pr_notes(
            diff_stats=_git_diff_stats(root),
            touched_paths=changed_paths,
            key_actions=[phase.summary for phase in goal.phases],
            tests_run=["contract_drift", "emit_contract_status", goal.gate_profile],
            risks=[*goal.risk_notes, *goal.rollback_notes, f"goal_id={goal.goal_id}"],
        )
        transaction_section = "\n\n## Transaction\n" + "\n".join([
            f"- status: committed",
            f"- improvement: {improvement_summary or 'n/a'}",
            f"- ci_baseline_before: {ci_baseline_before}",
            f"- ci_baseline_after: {ci_baseline_after}",
            "- contract_status_before: embedded in report",
            "- contract_status_after: embedded in report",
        ])
        body = body + transaction_section
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


    def _merge_pr(self, pr: PRRef) -> bool:
        if not pr.number and not pr.url:
            return False
        if shutil.which("gh") is None:
            return False
        target = str(pr.number) if pr.number is not None else pr.url
        result = subprocess.run(["gh", "pr", "merge", target, "--merge", "--delete-branch", "--auto"], cwd=self.repo_root, capture_output=True, text=True, check=False)
        if self._active_provenance is not None:
            payload = json.dumps({"target": target, "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}, sort_keys=True)
            step = self._active_provenance.make_step(
                step_id="publish_merge_attempted",
                kind="publish",
                command={"action": "merge_pr", "target": target},
                cwd=str(self.repo_root),
                env_fingerprint=_env_fingerprint(),
                started_at=_iso_now(),
                finished_at=_iso_now(),
                exit_code=result.returncode,
                stdout=payload,
                stderr=result.stderr,
                artifacts_written=[],
            )
            self._active_provenance.add_step(step, stdout=payload, stderr=result.stderr)
        return result.returncode == 0

    def _run_baseline_engine(
        self,
        goal: str,
        goal_spec: GoalSpec,
        session: ForgeSession,
        generated_at: str,
        forge_env: ForgeEnv,
    ) -> tuple[
        ApplyResult,
        int | None,
        int | None,
        str | None,
        list[HarvestResult],
        list[FixResult],
        dict[str, int],
        list[dict[str, object]],
    ]:
        cwd = Path(session.root_path)
        budget = BudgetConfig.from_env()
        step_results: list[CommandResult] = []
        harvests: list[HarvestResult] = []
        fixes: list[FixResult] = []
        prev_snapshot: ProgressSnapshot | None = None
        consecutive_no_improvement = 0
        no_improvement_limit = max(1, int(os.getenv("SENTIENTOS_FORGE_NO_IMPROVEMENT_LIMIT", "2")))
        baseline_progress: list[dict[str, object]] = []
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
            snapshot = snapshot_from_harvest(harvest)

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
                        baseline_progress,
                    )
                return (
                    ApplyResult(status="success", step_results=step_results, summary="baseline engine converged"),
                    test_failures_before,
                    test_failures_after,
                    docket_path,
                    harvests,
                    fixes,
                    _budget_payload(budget, iteration, len(touched_files_total)),
                    baseline_progress,
                )

            candidates = _prioritize_root_cause_candidates(generate_fix_candidates(harvest.clusters, cwd), harvest.clusters)
            selected = candidates[: budget.max_fixes_per_iteration]
            iteration_changed: set[str] = set()
            applied_fix = False

            for candidate in selected:
                result = apply_fix_candidate(candidate, cwd)
                fixes.append(result)
                touched_files_total.update(result.files_changed)
                iteration_changed.update(result.files_changed)
                if result.applied:
                    applied_fix = True

            if iteration_changed and goal_spec.gate_profile != "smoke_noop":
                self._run_optional_formatters(cwd, sorted(iteration_changed), step_results, goal_spec)
                if os.getenv("SENTIENTOS_FORGE_AUTOCOMMIT") == "1":
                    self._autocommit_iteration(cwd, goal_spec.goal_id, iteration)

            rerun_every = max(1, int(os.getenv("SENTIENTOS_FORGE_FULL_RERUN_EVERY", "2")))
            if applied_fix:
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
                    baseline_progress,
                )

            progress_notes: list[str] = []
            if applied_fix:
                progress_notes.append("fix_candidate_applied")
            if prev_snapshot is None:
                progress_notes.append("initial_snapshot")
                baseline_progress.append(
                    _compact_progress_record(
                        iteration=iteration,
                        snapshot=snapshot,
                        delta=None,
                        notes=progress_notes,
                    )
                )
                prev_snapshot = snapshot
                continue

            change = progress_delta_from(prev_snapshot, snapshot)
            progress_notes.extend(change.notes)
            baseline_progress.append(
                _compact_progress_record(
                    iteration=iteration,
                    snapshot=snapshot,
                    delta=change,
                    notes=progress_notes,
                )
            )
            if change.improved:
                consecutive_no_improvement = 0
            else:
                consecutive_no_improvement += 1

            if consecutive_no_improvement >= no_improvement_limit:
                confirm_step = self._run_step(
                    CommandSpec(step=f"baseline_full_rerun_confirm_{iteration}", argv=self._baseline_harvest_argv(forge_env.python, goal_spec.goal_id)),
                    cwd,
                )
                step_results.append(confirm_step)
                confirm_harvest = harvest_failures(confirm_step.stdout, confirm_step.stderr)
                harvests.append(confirm_harvest)
                test_failures_after = confirm_harvest.total_failed
                confirm_snapshot = snapshot_from_harvest(confirm_harvest)
                confirm_delta = progress_delta_from(snapshot, confirm_snapshot)
                confirm_notes = ["confirm_full_rerun"] + confirm_delta.notes
                baseline_progress.append(
                    _compact_progress_record(
                        iteration=iteration,
                        snapshot=confirm_snapshot,
                        delta=confirm_delta,
                        notes=confirm_notes,
                    )
                )
                if confirm_delta.improved:
                    consecutive_no_improvement = 0
                    prev_snapshot = confirm_snapshot
                    if confirm_harvest.total_failed == 0:
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
                                baseline_progress,
                            )
                        return (
                            ApplyResult(status="success", step_results=step_results, summary="baseline engine converged"),
                            test_failures_before,
                            test_failures_after,
                            docket_path,
                            harvests,
                            fixes,
                            _budget_payload(budget, iteration, len(touched_files_total)),
                            baseline_progress,
                        )
                    continue
                docket_path = self._emit_docket(goal, goal_spec.goal_id, generated_at, harvest.clusters, selected, "no progress in two consecutive iterations")
                return (
                    ApplyResult(status="failed", step_results=step_results, summary="no progress"),
                    test_failures_before,
                    test_failures_after,
                    docket_path,
                    harvests,
                    fixes,
                    _budget_payload(budget, iteration, len(touched_files_total)),
                    baseline_progress,
                )
            prev_snapshot = snapshot

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
            baseline_progress,
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




def _extract_pr_ref(metadata_payload: dict[str, Any], *, default: PRRef) -> PRRef:
    raw = metadata_payload.get("pr")
    if not isinstance(raw, dict):
        return default
    number_raw = raw.get("number")
    number = number_raw if isinstance(number_raw, int) else None
    return PRRef(
        number=number,
        url=str(raw.get("url", default.url)),
        head_sha=str(raw.get("head_sha", default.head_sha)),
        branch=str(raw.get("branch", default.branch)),
        created_at=str(raw.get("created_at", default.created_at)),
    )


def _checks_summary(checks: PRChecks) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in checks.checks:
        if item.conclusion not in {"", "success"}:
            rows.append({"name": item.name, "conclusion": item.conclusion, "details_url": item.details_url})
    return rows[:10]


def _checks_to_dict(checks: PRChecks) -> dict[str, object]:
    return {
        "pr": _dataclass_to_dict(checks.pr),
        "overall": checks.overall,
        "checks": [_dataclass_to_dict(item) for item in checks.checks],
    }

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


def _truncate_list(values: list[str], *, limit: int) -> list[str]:
    if len(values) <= limit:
        return values
    return values[:limit]


def _compact_progress_record(
    *,
    iteration: int,
    snapshot: ProgressSnapshot,
    delta: Any,
    notes: list[str],
) -> dict[str, object]:
    record: dict[str, object] = {
        "iteration": iteration,
        "snapshot": {
            "failed_count": snapshot.failed_count,
            "cluster_digest": snapshot.cluster_digest,
            "nodeid_sample": _truncate_list(list(snapshot.nodeid_sample), limit=MAX_BASELINE_PROGRESS_NODEIDS),
            "captured_at": snapshot.captured_at,
        },
        "notes": _truncate_list([_truncate_output(note) for note in notes], limit=8),
    }
    if delta is not None:
        record["delta"] = {
            "failed_count_delta": int(delta.failed_count_delta),
            "cluster_digest_changed": bool(delta.cluster_digest_changed),
            "improved": bool(delta.improved),
            "notes": _truncate_list([_truncate_output(note) for note in delta.notes], limit=8),
        }
    return record


def _summarize_baseline_progress(progress: list[dict[str, object]] | None) -> str | None:
    if not progress:
        return None
    last = progress[-1]
    snapshot = last.get("snapshot") if isinstance(last, dict) else None
    delta = last.get("delta") if isinstance(last, dict) else None
    notes = last.get("notes") if isinstance(last, dict) else []
    if not isinstance(snapshot, dict):
        return None
    failed = snapshot.get("failed_count")
    digest = snapshot.get("cluster_digest")
    delta_notes = delta.get("notes") if isinstance(delta, dict) else []
    note_summary = ",".join(str(item) for item in list(delta_notes)[:3]) if isinstance(delta_notes, list) else ""
    iter_value = last.get("iteration") if isinstance(last, dict) else "?"
    suffix = f" notes={note_summary}" if note_summary else ""
    return f"iter={iter_value} failed={failed} digest={digest} extra={notes}{suffix}"


def _cap_baseline_progress(progress: list[dict[str, object]]) -> list[dict[str, object]]:
    if len(progress) <= MAX_BASELINE_PROGRESS_ENTRIES:
        return progress
    return progress[-MAX_BASELINE_PROGRESS_ENTRIES:]


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


def _step_kind(step: str) -> str:
    lowered = step.lower()
    if "drift" in lowered or "status" in lowered or "env_import" in lowered:
        return "preflight"
    if lowered.startswith("baseline_") or lowered.startswith("apply"):
        return "apply"
    if "test" in lowered:
        return "tests"
    return "apply"



def _audit_integrity_failures(doctrine: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if not doctrine:
        return ["stability_doctrine_missing"]
    if doctrine.get("baseline_integrity_ok") is False:
        failures.append("baseline_integrity_ok")
    if doctrine.get("runtime_integrity_ok") is False:
        failures.append("runtime_integrity_ok")
    if doctrine.get("baseline_unexpected_change_detected") is True:
        failures.append("baseline_unexpected_change_detected")
    return failures


def _bundle_corruption_errors(bundle: Any) -> list[str]:
    errors = bundle.errors if isinstance(getattr(bundle, "errors", None), list) else []
    prefixes = (
        "bundle_missing_required:",
        "invalid_json:",
        "invalid_shape:",
        "zip_extract_failed:",
        "gh_download_failed:",
        "token_download_failed",
    )
    return [
        str(err)
        for err in errors
        if isinstance(err, str) and any(err.startswith(prefix) for prefix in prefixes) and err != "bundle_missing_required:contract_manifest.json"
    ]


def _bundle_metadata_mismatch(bundle: Any) -> bool:
    errors = bundle.errors if isinstance(getattr(bundle, "errors", None), list) else []
    return any(isinstance(err, str) and err.startswith("metadata_mismatch:") for err in errors)


def _bundle_manifest_missing(bundle: Any) -> bool:
    errors = bundle.errors if isinstance(getattr(bundle, "errors", None), list) else []
    return any(isinstance(err, str) and err == "bundle_missing_required:contract_manifest.json" for err in errors)


def _bundle_manifest_mismatch(bundle: Any) -> bool:
    errors = bundle.errors if isinstance(getattr(bundle, "errors", None), list) else []
    return any(isinstance(err, str) and err == "manifest_mismatch" for err in errors)


def _env_fingerprint(env: dict[str, str] | None = None) -> str:
    source = env if env is not None else dict(os.environ)
    keys = ["PATH", "PYTHONPATH", "VIRTUAL_ENV", "SENTIENTOS_FORGE_ALLOW_AUTOPUBLISH", "SENTIENTOS_FORGE_SENTINEL_TRIGGERED"]
    payload = {key: source.get(key, "") for key in keys}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
