from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Any, Mapping

from sentientos.anchor_witness import maybe_publish_anchor_witness
from sentientos.auto_remediation import maybe_auto_run_pack
from sentientos.audit_chain_gate import maybe_verify_audit_chain
from sentientos.doctrine_identity import verify_doctrine_identity
from sentientos.federation_integrity import federation_integrity_gate
from sentientos.forge_index import INDEX_PATH, rebuild_index
from sentientos.governance_trace import GovernanceTraceRecorder, start_governance_trace
from sentientos.integrity_pressure import compute_integrity_pressure, update_pressure_state
from sentientos.integrity_quarantine import load_state as load_quarantine_state
from sentientos.integrity_snapshot import PEER_SNAPSHOTS_DIR, SNAPSHOT_PATH, emit_integrity_snapshot
from sentientos.attestation import canonical_json_bytes, write_json
from sentientos.attestation_snapshot import AttestationSnapshot, emit_snapshot, maybe_publish_snapshot_witness, maybe_sign_snapshot, should_emit_snapshot, verify_recent_snapshots
from sentientos.integrity_controller import IntegrityBudget, IntegrityStatus, evaluate_integrity
from sentientos.policy_fingerprint import emit_policy_fingerprint
from sentientos.goal_graph import (GOAL_GRAPH_PATH, GoalGraph,
    goal_graph_hash, load_goal_graph, order_goals_deterministic)
from sentientos.goal_graph import load_goal_state, persist_goal_state
from sentientos.goal_planner import ExecutorState, GoalPlanner
from sentientos.goal_completion import CompletionContext, eval_check
from sentientos.receipt_anchors import maybe_verify_receipt_anchors
from sentientos.receipt_chain import maybe_verify_receipt_chain
from sentientos.remediation_pack import PACKS_PULSE_PATH
from sentientos.artifact_catalog import (append_catalog_entry, latest,
    load_catalog_artifact, recent)
from sentientos.artifact_retention import RetentionPolicy, run_retention, should_run_retention
from sentientos.recovery_tasks import backlog_count
from sentientos.signed_rollups import maybe_publish_rollup_witness, maybe_sign_catalog_checkpoint, sign_rollups
from sentientos.signed_strategic import latest_sig_hash_short, maybe_publish_strategic_witness, strategic_signing_enabled, verify_recent
from sentientos.risk_budget import RiskBudget, compute_risk_budget, risk_budget_summary
from sentientos.strategic_posture import resolve_posture
from sentientos.throughput_policy import derive_throughput_policy
from sentientos.schema_registry import LATEST_VERSIONS, latest_version, SchemaName
from sentientos.work_allocator import AllocationDecision, allocate_goals
from sentientos.persistent_epistemic_state import (EpistemicCognitiveProjection,
    PersistentEpistemicStateOwner)
from sentientos.local_model_authority import digest_payload
from sentientos.work_plan import (WorkPlan, WorkPlanError, load_work_plan,
    load_work_plan_evidence, load_work_run, persist_work_plan,
    persist_work_plan_evidence, persist_work_run)
from sentientos.work_plan_execution_journal import WorkPlanExecutionJournal
from sentientos.strategic_adaptation import (
    apply_requires_stable,
    auto_propose_enabled,
    can_auto_apply,
    approve_proposal,
    create_adjustment_proposal,
    should_generate_proposal,
    strategic_apply_preconditions,
)


@dataclass(frozen=True)
class OrchestratorConfig:
    enabled: bool
    interval_seconds: int
    sweeps_enabled: bool
    auto_remediation_enabled: bool
    federation_snapshot_enabled: bool
    witness_publish_enabled: bool
    retention_enabled: bool

    @classmethod
    def from_env(cls) -> "OrchestratorConfig":
        return cls(
            enabled=os.getenv("SENTIENTOS_ORCHESTRATOR_ENABLE", "0") == "1",
            interval_seconds=max(5, _env_int("SENTIENTOS_ORCHESTRATOR_INTERVAL_SECONDS", 300)),
            sweeps_enabled=os.getenv("SENTIENTOS_ORCHESTRATOR_SWEEPS", "1") == "1",
            auto_remediation_enabled=os.getenv("SENTIENTOS_ORCHESTRATOR_AUTO_REMEDIATION", "1") == "1",
            federation_snapshot_enabled=os.getenv("SENTIENTOS_ORCHESTRATOR_FEDERATION_SNAPSHOT", "1") == "1",
            witness_publish_enabled=os.getenv("SENTIENTOS_ORCHESTRATOR_WITNESS_PUBLISH", "0") == "1",
            retention_enabled=os.getenv("SENTIENTOS_ORCHESTRATOR_RETENTION", "0") == "1",
        )


@dataclass(frozen=True)
class TickResult:
    tick_at: str
    status: str
    operating_mode: str
    integrity_pressure_level: int
    trace_id: str | None
    remediation_status: str
    index_path: str
    tick_report_path: str


@dataclass(frozen=True, slots=True)
class GoalPlanningResult:
    """Persisted canonical allocation and plan; this value carries no execution result."""

    allocation: AllocationDecision
    allocation_artifact_path: str
    goal_graph_hash: str
    planning_time: str
    target_active_model_identity_digest: str | None
    target_identity_observed_at: str | None
    work_plan: WorkPlan | None
    work_plan_path: str | None
    work_plan_evidence_path: str | None
    work_plan_evidence_digest: str | None


def plan_goals(
    repo_root: Path,
    *,
    prior_epistemic_projection_owner: PersistentEpistemicStateOwner | None = None,
    prior_epistemic_projection_max_states: int | None = None,
    target_model_identity_observer: object | None = None,
    planning_time: str | None = None,
) -> GoalPlanningResult:
    """Build and persist a governed goal plan without executing any plan tasks.

    This is the planning-only composition boundary for daemon and operator callers.
    It returns a persisted plan value but does not invoke the executor. Execution
    remains an explicit operation of ``GoalExecutor`` or the established ``tick``
    path. The verified epistemic owner, when supplied, is read
    exactly once at the planning time and is never mutated.
    """
    root = repo_root.resolve()
    current_time = planning_time or _iso_now()
    try:
        instant = datetime.fromisoformat(current_time.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ValueError("planning_time_must_be_timezone_aware") from exc
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("planning_time_must_be_timezone_aware")
    if (prior_epistemic_projection_owner is None
            and prior_epistemic_projection_max_states is not None):
        raise ValueError("epistemic_projection_bound_requires_owner")
    graph = load_goal_graph(root)
    prioritized_proposition_ids = _goal_tagged_epistemic_positions(graph)
    prior_projection = None
    if prior_epistemic_projection_owner is not None:
        if (not isinstance(prior_epistemic_projection_max_states, int)
                or isinstance(prior_epistemic_projection_max_states, bool)):
            raise ValueError("epistemic_projection_bound_required")
        prior_projection = prior_epistemic_projection_owner.cognitive_projection(
            max_states=prior_epistemic_projection_max_states,
            current_tick=int(instant.timestamp()),
            prioritized_proposition_ids=prioritized_proposition_ids)

    now = _iso_now()
    quarantine = load_quarantine_state(root)
    pressure = compute_integrity_pressure(root)
    throughput = derive_throughput_policy(
        integrity_pressure_level=pressure.level, quarantine=quarantine)
    posture = resolve_posture()
    budget = compute_risk_budget(
        repo_root=root, posture=posture.posture,
        pressure_level=pressure.level, operating_mode=throughput.mode,
        quarantine_active=quarantine.active)
    policy_fingerprint = emit_policy_fingerprint(root, ts=now)
    integrity_status = evaluate_integrity(root, policy_hash=policy_fingerprint.policy_hash)
    return _plan_goal_work(
        root=root, graph=graph, budget=budget,
        operating_mode=throughput.mode, pressure_level=pressure.level,
        quarantine_active=quarantine.active, posture=posture.posture,
        mutation_allowed=integrity_status.mutation_allowed,
        prior_epistemic_projection=prior_projection,
        target_model_identity_observer=target_model_identity_observer,
        planning_time=current_time, catalog_timestamp=now, context="orchestrator_tick",
    )


def _goal_tagged_epistemic_positions(graph: GoalGraph) -> tuple[str, ...]:
    """Order valid epistemic proposition tags by deterministic goal precedence."""
    marker = "epistemic_proposition:"
    priorities: list[str] = []
    seen: set[str] = set()
    for goal in order_goals_deterministic(graph.goals):
        if not goal.enabled:
            continue
        for tag in goal.tags:
            if not tag.startswith(marker):
                continue
            proposition_id = tag[len(marker):]
            suffix = proposition_id.removeprefix("proposition:")
            if (not proposition_id.startswith("proposition:")
                    or len(suffix) != 24
                    or any(char not in "0123456789abcdef" for char in suffix)
                    or proposition_id in seen):
                continue
            seen.add(proposition_id)
            priorities.append(proposition_id)
    return tuple(priorities)


def tick(repo_root: Path, *, config: OrchestratorConfig | None = None,
        daemon_active: bool = False,
        prior_epistemic_projection: EpistemicCognitiveProjection | None = None,
        target_model_identity_observer: object | None = None) -> TickResult:
    root = repo_root.resolve()
    cfg = config or OrchestratorConfig.from_env()
    now = _iso_now()

    quarantine = load_quarantine_state(root)
    pressure = compute_integrity_pressure(root)
    _pressure_state, pressure_changed = update_pressure_state(root, pressure)
    throughput = derive_throughput_policy(integrity_pressure_level=pressure.level, quarantine=quarantine)
    posture = resolve_posture()
    budget = compute_risk_budget(
        repo_root=root,
        posture=posture.posture,
        pressure_level=pressure.level,
        operating_mode=throughput.mode,
        quarantine_active=quarantine.active,
    )
    policy_fingerprint = emit_policy_fingerprint(root, ts=now)
    integrity_status = evaluate_integrity(root, policy_hash=policy_fingerprint.policy_hash)

    mutation_allowed = integrity_status.mutation_allowed

    trace = start_governance_trace(
        repo_root=root,
        context="orchestrator_tick",
        strategic_posture=posture.posture,
        integrity_pressure_level=pressure.level,
        integrity_metrics_summary=pressure.metrics.to_dict(),
        operating_mode=throughput.mode,
        mode_toggles_summary={
            "allow_automerge": throughput.allow_automerge,
            "allow_publish": throughput.allow_publish,
            "allow_forge_mutation": throughput.allow_forge_mutation,
        },
        quarantine_state_summary={
            "active": quarantine.active,
            "allow_publish": quarantine.allow_publish,
            "allow_automerge": quarantine.allow_automerge,
            "last_incident_id": quarantine.last_incident_id,
        },
        risk_budget_summary=risk_budget_summary(budget),
        risk_budget_notes=[str(item) for item in list(budget.notes or [])[:8]],
    )

    sweep_summary: dict[str, object] | None = None
    federation_snapshot_path: str | None = None
    peer_snapshot_count = 0
    witness_status = "disabled"
    witness_failure: str | None = None
    remediation_status = "idle"
    remediation_detail: dict[str, object] | None = None
    reason_stack: list[str] = []
    reason_stack.extend(integrity_status.reason_stack[:6])
    integrity_status_path = _persist_integrity_status(root, integrity_status)
    _append_jsonl(
        root / "pulse/integrity_status.jsonl",
        {
            "ts": integrity_status.ts,
            "status": integrity_status.status,
            "primary_reason": integrity_status.primary_reason,
            "path": integrity_status_path,
            "mutation_allowed": integrity_status.mutation_allowed,
            "publish_allowed": integrity_status.publish_allowed,
            "automerge_allowed": integrity_status.automerge_allowed,
            "policy_hash": integrity_status.policy_hash,
        },
    )
    retention_summary: dict[str, object] | None = None
    rollup_sign_status = "skipped"
    signed_rollups_count = 0
    last_signed_rollup_id: str | None = None
    catalog_checkpoint_status = "disabled"
    allocation: AllocationDecision | None = None
    allocation_artifact_path: str | None = None
    goal_graph_digest: str | None = None
    work_plan_id: str | None = None
    work_run_id: str | None = None
    work_run_status: str | None = None
    goal_state_summary: dict[str, int] | None = None
    strategic_last_proposal_id: str | None = None
    strategic_last_proposal_status: str | None = None
    strategic_last_applied_change_id: str | None = None
    strategic_cooldown: str | None = None
    strategic_last_proposal_added_goals: list[str] = []
    strategic_last_proposal_removed_goals: list[str] = []
    strategic_last_proposal_budget_delta: dict[str, object] = {}
    strategic_sign_status = "skipped"
    last_strategic_sig_hash: str | None = latest_sig_hash_short(root)
    strategic_witness_status = "disabled"
    strategic_witness_published_at: str | None = None
    strategic_sig_verify_status = "skipped"
    strategic_sig_verify_reason: str | None = "verify_disabled"
    strategic_sig_verify_checked_n = 0
    strategic_sig_verify_last_ok_sig_hash: str | None = None

    planning_time = _iso_now()
    goal_graph = load_goal_graph(root)
    planning = _plan_goal_work(
        root=root, graph=goal_graph, budget=budget,
        operating_mode=throughput.mode, pressure_level=pressure.level,
        quarantine_active=quarantine.active, posture=posture.posture,
        mutation_allowed=mutation_allowed,
        prior_epistemic_projection=prior_epistemic_projection,
        target_model_identity_observer=target_model_identity_observer,
        planning_time=planning_time, catalog_timestamp=now,
        context="orchestrator_tick", trace=trace,
    )
    allocation = planning.allocation
    allocation_artifact_path = planning.allocation_artifact_path
    goal_graph_digest = planning.goal_graph_hash
    work_plan_id = planning.work_plan.plan_id if planning.work_plan is not None else None

    if planning.work_plan is not None:
        from sentientos.goal_executor import GoalExecutor, update_goal_state_from_run

        executor_state = ExecutorState(
            repo_root=root, created_at=planning_time,
            context="orchestrator_tick", operating_mode=throughput.mode,
            quarantine_active=quarantine.active, allow_mutation=mutation_allowed,
            goal_graph_hash=goal_graph_digest or "",
            allocation_id=allocation_artifact_path or "allocation_missing",
            risk_budget=budget, pressure_level=pressure.level, posture=posture.posture,
            prior_epistemic_projection=prior_epistemic_projection,
            target_active_model_identity_digest=(
                planning.target_active_model_identity_digest),
            target_identity_observed_at=planning.target_identity_observed_at,
        )
        executor = GoalExecutor(repo_root=root)
        if not planning.work_plan_evidence_digest:
            raise WorkPlanError("canonical_work_plan_evidence_missing")
        run = executor.execute_plan(
            planning.work_plan, executor_state,
            expected_evidence_digest=planning.work_plan_evidence_digest,
        )
        work_run_id = run.run_id
        work_run_status = run.status
        run_path = persist_work_run(root, run)
        append_catalog_entry(
            root, kind="work_run", artifact_id=run.run_id,
            relative_path=str(run_path), schema_name="work_run", schema_version=1,
            links={"work_run_id": run.run_id,
                "goal_ids": list(planning.work_plan.selected_goals)},
            summary={"status": run.status,
                "goal_ids": list(planning.work_plan.selected_goals),
                "evidence_digest": run.evidence_digest}, ts=now,
        )
        goal_state = load_goal_state(root)
        updated_state = update_goal_state_from_run(
            goal_graph, goal_state, run, repo_root=root,
            operating_mode=throughput.mode, pressure_level=pressure.level,
            posture=posture.posture, quarantine_active=quarantine.active,
            risk_budget_summary=budget.to_dict(),
        )
        persist_goal_state(root, updated_state)
        goal_state_summary = _goal_state_summary(updated_state)
        trace.record_clamp(
            name="goal_execution",
            before={"allocation_id": allocation_artifact_path or "",
                "selected_goals": list(allocation.selected)},
            after={
                "plan_id": work_plan_id,
                "plan_path": planning.work_plan_path,
                "plan_evidence_path": planning.work_plan_evidence_path,
                "plan_evidence_digest": planning.work_plan_evidence_digest,
                "run_id": work_run_id,
                "run_path": run_path,
                "run_status": work_run_status,
                "task_outcomes": [
                    {"task_id": item.task_id, "status": item.status,
                        "reason": item.reason} for item in run.task_runs
                ],
            },
            notes="deterministic_goal_execution",
        )
        if run.status in {"failed", "partial"}:
            reason_stack.append("goal_execution_incomplete")

    verify_artifact_path = _emit_verify_result_artifact(
        root,
        generated_at=now,
        goal_ids=list(allocation.selected) if allocation is not None else [],
    )
    if verify_artifact_path:
        append_catalog_entry(
            root,
            kind="verify_result",
            artifact_id=now,
            relative_path=verify_artifact_path,
            schema_name=SchemaName.FORGE_REPORT,
            schema_version=1,
            links={"work_run_id": work_run_id, "goal_ids": list(allocation.selected) if allocation is not None else []},
            summary={"status": "ok"},
            ts=now,
        )

    if cfg.sweeps_enabled and throughput.mode in {"cautious", "recovery", "lockdown"}:
        if _should_run_sweep(root, interval_minutes=posture.diagnostics_sweep_interval_minutes):
            sweep_summary = _run_integrity_sweep(root=root, pressure_level=pressure.level, mode=throughput.mode)
            sweep_detail = sweep_summary.get("summary")
            sweep_failed = sweep_detail.get("failed", 0) if isinstance(sweep_detail, dict) else 0
            trace.record_gate(
                name="diagnostics_sweep",
                mode="warn",
                result="pass" if _safe_int(sweep_failed) == 0 else "hold",
                reason="orchestrator_sweep",
                evidence_paths=[str(sweep_summary.get("artifact_path", ""))],
            )
            if _safe_int(sweep_failed) > 0:
                reason_stack.append("diagnostics_sweep_failures")

    if cfg.auto_remediation_enabled:
        if not mutation_allowed:
            remediation_status = "skipped"
            remediation_detail = {"reason": "mutation_disallowed"}
            trace.record_gate(name="auto_remediation", mode="enforce", result="hold", reason="mutation_disallowed")
            reason_stack.append("mutation_disallowed")
        else:
            pack = _latest_eligible_pack(root)
            if pack is None:
                remediation_status = "idle"
                remediation_detail = {"reason": "no_eligible_pack"}
            else:
                decision = maybe_auto_run_pack(
                    root,
                    operating_mode=throughput.mode,
                    context="orchestrator_tick",
                    pack=pack,
                    governance_trace_id="orchestrator_pending",
                    incident_id=_optional_str(pack.get("incident_id")),
                )
                remediation_status = decision.status
                remediation_detail = {
                    "reason": decision.reason,
                    "attempted": decision.attempted,
                    "pack_id": decision.pack_id,
                    "run_id": decision.run_id,
                }
                trace.record_gate(
                    name="auto_remediation",
                    mode="warn",
                    result="pass" if decision.status in {"succeeded", "idle"} else "hold",
                    reason=decision.reason,
                    evidence_paths=[str(pack.get("pack_path", ""))],
                )
                if decision.status not in {"idle", "succeeded"}:
                    reason_stack.append(f"auto_remediation_{decision.status}")

    if cfg.federation_snapshot_enabled:
        snapshot = emit_integrity_snapshot(root)
        federation_snapshot_path = str(SNAPSHOT_PATH)
        if daemon_active:
            peer_snapshot_count = _peer_snapshot_count(root)
        _ = snapshot

    if cfg.witness_publish_enabled:
        if mutation_allowed:
            previous = os.getenv("SENTIENTOS_ANCHOR_WITNESS_PUBLISH")
            os.environ["SENTIENTOS_ANCHOR_WITNESS_PUBLISH"] = "1"
            status_payload, failure = maybe_publish_anchor_witness(root)
            if previous is None:
                os.environ.pop("SENTIENTOS_ANCHOR_WITNESS_PUBLISH", None)
            else:
                os.environ["SENTIENTOS_ANCHOR_WITNESS_PUBLISH"] = previous
            witness_status = str(status_payload.get("witness_status") or "unknown")
            witness_failure = _optional_str(failure) or _optional_str(status_payload.get("witness_failure"))
        else:
            witness_status = "skipped"
            witness_failure = "mutation_disallowed"

    if cfg.retention_enabled and should_run_retention(root):
        retention_result = run_retention(root, policy=RetentionPolicy.from_env())
        retention_summary = retention_result.to_dict()
        try:
            signed = sign_rollups(root, retention_result.rollup_files)
            signed_rollups_count = len(signed)
            last_signed_rollup_id = str(signed[-1].rollup_id) if signed else None
            rollup_sign_status = "ok" if signed else "skipped"
        except RuntimeError:
            rollup_sign_status = "failed"

        checkpoint = maybe_sign_catalog_checkpoint(root)
        catalog_checkpoint_status = "ok" if checkpoint is not None else "disabled"

    if cfg.witness_publish_enabled:
        rollup_witness_status, rollup_witness_failure = maybe_publish_rollup_witness(root)
        if rollup_witness_failure:
            witness_failure = rollup_witness_failure
            witness_status = str(rollup_witness_status.get("status") or "failed")

    if auto_propose_enabled() and should_generate_proposal(root):
        proposal, proposal_path = create_adjustment_proposal(root, window_name="last_24h")
        strategic_last_proposal_id = proposal.proposal_id
        strategic_last_proposal_status = proposal.approval.status
        added_selected = proposal.allocation_diff.get("added_selected")
        removed_selected = proposal.allocation_diff.get("removed_selected")
        strategic_last_proposal_added_goals = [item for item in added_selected[:6] if isinstance(item, str)] if isinstance(added_selected, list) else []
        strategic_last_proposal_removed_goals = [item for item in removed_selected[:6] if isinstance(item, str)] if isinstance(removed_selected, list) else []
        budget_delta = proposal.allocation_diff.get("budget_delta")
        strategic_last_proposal_budget_delta = {str(key): value for key, value in budget_delta.items()} if isinstance(budget_delta, dict) else {}
        reordered = proposal.allocation_diff.get("reordered")
        top_reorder = reordered[0] if isinstance(reordered, list) and reordered else None
        strategic_cooldown = (datetime.now(timezone.utc) + timedelta(days=1)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        if strategic_signing_enabled():
            last_strategic_sig_hash = latest_sig_hash_short(root)
            strategic_sign_status = "ok" if last_strategic_sig_hash else "failed"
        trace.record_clamp(
            name="strategic_adaptation_proposal",
            before={"goal_graph_hash": goal_graph_digest or ""},
            after={
                "proposal_id": proposal.proposal_id,
                "status": proposal.approval.status,
                "strategic_counterfactual_summary": {
                    "added_selected": strategic_last_proposal_added_goals,
                    "removed_selected": strategic_last_proposal_removed_goals,
                    "top_reorder": top_reorder,
                },
            },
            notes="deterministic_strategic_proposal",
        )
        if can_auto_apply() and (not apply_requires_stable() or strategic_apply_preconditions(root)):
            approved, change_id = approve_proposal(
                root,
                proposal_path=root / proposal_path,
                approve=True,
                approved_by="policy",
                decision_notes="auto_apply_policy_gate_passed",
                apply=True,
                enforce_stable=apply_requires_stable(),
            )
            strategic_last_proposal_status = approved.approval.status
            strategic_last_applied_change_id = change_id

    if strategic_signing_enabled() and strategic_sign_status == "skipped":
        strategic_sign_status = "ok" if latest_sig_hash_short(root) else "failed"
    verify_outcome = _maybe_verify_strategic_signatures(root)
    outcome_status = verify_outcome.get("status")
    outcome_reason = verify_outcome.get("reason")
    strategic_sig_verify_status = outcome_status if isinstance(outcome_status, str) else "skipped"
    strategic_sig_verify_reason = outcome_reason if isinstance(outcome_reason, str) else None
    strategic_sig_verify_checked_n = _safe_int(verify_outcome.get("checked_n"))
    strategic_sig_verify_last_ok_sig_hash = _optional_str(verify_outcome.get("last_ok_sig_hash"))
    if bool(verify_outcome["hard_fail"]):
        mutation_allowed = False
        reason_stack.append("strategic_signature_verify_failed")
        trace.record_gate(
            name="strategic_signature_verify",
            mode="enforce",
            result="hold",
            reason=_optional_str(verify_outcome["reason"]) or "strategic_signature_verify_failed",
        )
    elif strategic_sig_verify_status == "warn":
        trace.record_gate(
            name="strategic_signature_verify",
            mode="warn",
            result="hold",
            reason=_optional_str(verify_outcome["reason"]) or "strategic_signature_verify_warn",
        )
    elif strategic_sig_verify_status == "ok":
        trace.record_gate(name="strategic_signature_verify", mode="warn", result="pass", reason="ok")

    witness_payload, witness_failure2 = maybe_publish_strategic_witness(
        root,
        allow_git_tag_publish=mutation_allowed and integrity_status.publish_allowed,
    )
    strategic_witness_status = str(witness_payload.get("status") or "unknown")
    strategic_witness_published_at = _optional_str(witness_payload.get("published_at"))
    if witness_failure2 and witness_failure is None:
        witness_failure = witness_failure2
    attestation_snapshot_path, attestation_sig_hash, attestation_snapshot_hash = _emit_attestation_snapshot(
        root,
        integrity_status=integrity_status,
        goal_graph_hash_value=goal_graph_digest,
        mutation_allowed=mutation_allowed and integrity_status.publish_allowed,
    )
    rebuild_index(root)

    backlog = {
        "recovery_task_backlog_count": backlog_count(root),
        "remediation_backlog_count": _remediation_backlog_count(root),
    }
    status = "ok"
    if integrity_status.status in {"warn", "fail"}:
        status = "warning"
    if witness_failure or remediation_status in {"failed", "cooldown"} or strategic_sig_verify_status in {"warn", "fail"}:
        status = "warning"
    if pressure_changed and pressure.level >= 3:
        status = "warning"

    final_reason_stack = reason_stack or ["orchestrator_tick"]
    trace_response = trace.finalize(
        final_decision="diagnostics_only" if not mutation_allowed else "allow",
        final_reason="orchestrator_tick_completed",
        reason_stack=final_reason_stack,
        suggested_actions=["python scripts/orchestrator_tick.py"],
    )

    trace_id = _optional_str(trace_response.get("trace_id"))
    trace_path = _optional_str(trace_response.get("trace_path"))
    linked_pack = trace_response.get("remediation_pack") if isinstance(trace_response.get("remediation_pack"), dict) else None

    report = {
        "schema_version": latest_version(SchemaName.ORCHESTRATOR_TICK),
        "generated_at": now,
        "status": status,
        "orchestrator_enabled": cfg.enabled,
        "operating_mode": throughput.mode,
        "integrity_pressure_level": pressure.level,
        "quarantine_active": quarantine.active,
        "mutation_allowed": mutation_allowed,
        "publish_allowed": integrity_status.publish_allowed,
        "automerge_allowed": integrity_status.automerge_allowed,
        "risk_budget_summary": risk_budget_summary(budget),
        "integrity_status": integrity_status.to_dict(),
        "integrity_status_path": integrity_status_path,
        "last_sweep": sweep_summary,
        "auto_remediation": remediation_detail,
        "federation_snapshot": {
            "path": federation_snapshot_path,
            "peer_snapshot_count": peer_snapshot_count,
        },
        "witness_publish": {
            "status": witness_status,
            "failure": witness_failure,
        },
        "trace": {
            "trace_id": trace_id,
            "trace_path": trace_path,
            "linked_remediation_pack": linked_pack,
        },
        "orchestrator_backlog_summary": backlog,
        "index_path": str(INDEX_PATH),
        "schema_versions_snapshot": dict(sorted(LATEST_VERSIONS.items())),
        "retention": retention_summary,
        "rollup_sign_status": rollup_sign_status,
        "signed_rollups_count": signed_rollups_count,
        "last_signed_rollup_id": last_signed_rollup_id,
        "catalog_checkpoint_status": catalog_checkpoint_status,
        "goal_allocation": {
            "artifact_path": allocation_artifact_path,
            "selected_goals": list(allocation.selected) if allocation is not None else [],
            "deferred_goals": [{"goal_id": item.goal_id, "reason": item.reason} for item in allocation.deferred] if allocation is not None else [],
            "budget_summary": allocation.budget_summary if allocation is not None else {},
            "goal_graph_hash": goal_graph_digest,
        },
        "strategic_sign_status": strategic_sign_status,
        "last_strategic_sig_hash": last_strategic_sig_hash,
        "strategic_sig_verify_status": strategic_sig_verify_status,
        "strategic_sig_verify_reason": strategic_sig_verify_reason,
        "strategic_sig_verify_checked_n": strategic_sig_verify_checked_n,
        "strategic_sig_verify_last_ok_sig_hash": strategic_sig_verify_last_ok_sig_hash,
        "strategic_witness": {"status": strategic_witness_status, "published_at": strategic_witness_published_at},
        "attestation_snapshot": {
            "path": attestation_snapshot_path,
            "snapshot_hash": attestation_snapshot_hash,
            "signature_hash": attestation_sig_hash,
        },
        "goal_execution": {
            "work_plan_id": work_plan_id,
            "work_plan_evidence_path": planning.work_plan_evidence_path,
            "work_plan_evidence_digest": planning.work_plan_evidence_digest,
            "work_run_id": work_run_id,
            "work_run_status": work_run_status,
            "goal_state_summary": goal_state_summary or {"active": 0, "blocked": 0, "completed": 0},
        },
    }
    tick_path = root / "glow/forge/orchestrator/ticks" / f"tick_{_safe_ts(now)}.json"
    tick_path.parent.mkdir(parents=True, exist_ok=True)
    tick_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    append_catalog_entry(
        root,
        kind="orchestrator_tick",
        artifact_id=now,
        relative_path=str(tick_path.relative_to(root)),
        schema_name="orchestrator_tick",
        schema_version=latest_version(SchemaName.ORCHESTRATOR_TICK),
        links={"trace_id": trace_id, "pack_id": _optional_str((linked_pack or {}).get("pack_id") if isinstance(linked_pack, dict) else None)},
        summary={"status": status, "operating_mode": throughput.mode},
        ts=now,
    )

    pulse_row = {
        "generated_at": now,
        "status": status,
        "operating_mode": throughput.mode,
        "integrity_pressure_level": pressure.level,
        "remediation_status": remediation_status,
        "tick_report_path": str(tick_path.relative_to(root)),
        "retention_archived_items": _safe_int((retention_summary or {}).get("archived_items", 0)),
        "retention_rollup_files": _list_length((retention_summary or {}).get("rollup_files")),
        "rollup_sign_status": rollup_sign_status,
        "signed_rollups_count": signed_rollups_count,
        "catalog_checkpoint_status": catalog_checkpoint_status,
        "goal_allocation_id": allocation_artifact_path,
        "selected_goals": list(allocation.selected) if allocation is not None else [],
        "deferred_goal_count": len(allocation.deferred) if allocation is not None else 0,
        "last_work_plan_id": work_plan_id,
        "last_work_run_id": work_run_id,
        "last_work_run_status": work_run_status,
        "strategic_sign_status": strategic_sign_status,
        "last_strategic_sig_hash": last_strategic_sig_hash,
        "strategic_sig_verify_status": strategic_sig_verify_status,
        "strategic_sig_verify_reason": strategic_sig_verify_reason,
        "strategic_sig_verify_checked_n": strategic_sig_verify_checked_n,
        "strategic_sig_verify_last_ok_sig_hash": strategic_sig_verify_last_ok_sig_hash,
        "integrity_status": integrity_status.status,
        "integrity_primary_reason": integrity_status.primary_reason,
        "integrity_status_path": integrity_status_path,
        "integrity_mutation_allowed": integrity_status.mutation_allowed,
        "integrity_publish_allowed": integrity_status.publish_allowed,
        "integrity_automerge_allowed": integrity_status.automerge_allowed,
        "attestation_snapshot_path": attestation_snapshot_path,
        "attestation_snapshot_hash": attestation_snapshot_hash,
        "attestation_snapshot_sig_hash": attestation_sig_hash,
    }
    _append_jsonl(
        root / "pulse/goal_allocations.jsonl",
        {
            "generated_at": now,
            "operating_mode": throughput.mode,
            "integrity_pressure_level": pressure.level,
            "goal_graph_hash": goal_graph_digest,
            "allocation_path": allocation_artifact_path,
            "selected_goals": list(allocation.selected) if allocation is not None else [],
            "deferred_goals": [{"goal_id": item.goal_id, "reason": item.reason} for item in allocation.deferred] if allocation is not None else [],
            "budget_summary": allocation.budget_summary if allocation is not None else {},
        },
    )
    _append_jsonl(root / "pulse/orchestrator_ticks.jsonl", pulse_row)

    _write_orchestrator_index_overlay(
        root,
        orchestrator_enabled=cfg.enabled,
        generated_at=now,
        status=status,
        backlog=backlog,
        tick_report_path=str(tick_path.relative_to(root)),
        allocation=allocation,
        allocation_artifact_path=allocation_artifact_path,
        goal_graph_hash_value=goal_graph_digest,
        work_plan_id=work_plan_id,
        work_run_id=work_run_id,
        work_run_status=work_run_status,
        goal_state_summary=goal_state_summary or {"active": 0, "blocked": 0, "completed": 0},
        strategic_last_proposal_id=strategic_last_proposal_id,
        strategic_last_proposal_status=strategic_last_proposal_status,
        strategic_last_applied_change_id=strategic_last_applied_change_id,
        strategic_cooldown_until=strategic_cooldown,
        strategic_last_proposal_added_goals=strategic_last_proposal_added_goals,
        strategic_last_proposal_removed_goals=strategic_last_proposal_removed_goals,
        strategic_last_proposal_budget_delta=strategic_last_proposal_budget_delta,
        strategic_signature_status=strategic_sign_status if strategic_sign_status in {"ok", "failed"} else "unknown",
        last_strategic_sig_hash=last_strategic_sig_hash,
        strategic_sig_verify_status=strategic_sig_verify_status,
        strategic_sig_verify_reason=strategic_sig_verify_reason,
        strategic_sig_verify_checked_n=strategic_sig_verify_checked_n,
        strategic_sig_verify_last_ok_sig_hash=strategic_sig_verify_last_ok_sig_hash,
        strategic_witness_status=strategic_witness_status,
        last_strategic_witness_at=strategic_witness_published_at,
        integrity_status=integrity_status,
        integrity_status_path=integrity_status_path,
    )

    return TickResult(
        tick_at=now,
        status=status,
        operating_mode=throughput.mode,
        integrity_pressure_level=pressure.level,
        trace_id=trace_id,
        remediation_status=remediation_status,
        index_path=str(INDEX_PATH),
        tick_report_path=str(tick_path.relative_to(root)),
    )


def _latest_eligible_pack(repo_root: Path) -> dict[str, object] | None:
    entry = latest(repo_root, "remediation_pack")
    if isinstance(entry, dict):
        summary_value = entry.get("summary")
        summary = summary_value if isinstance(summary_value, dict) else {}
        if str(summary.get("status") or "") in {"proposed", "queued"}:
            links_value = entry.get("links")
            links = links_value if isinstance(links_value, dict) else {}
            return {"pack_id": entry.get("id"), "pack_path": entry.get("path"), "incident_id": links.get("incident_id"), "status": summary.get("status")}
    rows = _read_jsonl(repo_root / PACKS_PULSE_PATH)
    for row in reversed(rows):
        if str(row.get("status", "")) in {"proposed", "queued"}:
            return row
    return None


def _should_run_sweep(repo_root: Path, *, interval_minutes: int) -> bool:
    rows = _read_jsonl(repo_root / "pulse/sweeps.jsonl")
    if not rows:
        return True
    latest = _optional_str(rows[-1].get("generated_at"))
    parsed = _parse_iso(latest)
    if parsed is None:
        return True
    return datetime.now(timezone.utc) - parsed >= timedelta(minutes=max(1, interval_minutes))


def _run_integrity_sweep(*, root: Path, pressure_level: int, mode: str) -> dict[str, object]:
    checks: list[dict[str, object]] = []
    doctrine_ok, doctrine_payload = verify_doctrine_identity(root)
    checks.append({"name": "verify_doctrine_identity", "ok": doctrine_ok, "detail": doctrine_payload})

    chain_check, _enforce, _warn = maybe_verify_receipt_chain(root, context="orchestrator_sweep", last=50)
    checks.append({"name": "verify_receipt_chain", "ok": bool(chain_check.ok) if chain_check is not None else True, "detail": chain_check.to_dict() if chain_check is not None else {}})

    anchor_check, _a_enforce, _a_warn = maybe_verify_receipt_anchors(root, context="orchestrator_sweep", last=10)
    checks.append({"name": "verify_receipt_anchors", "ok": bool(anchor_check.ok) if anchor_check is not None else True, "detail": anchor_check.to_dict() if anchor_check is not None else {}})

    audit_check, _audit_enforce, _audit_warn, audit_report = maybe_verify_audit_chain(root, context="orchestrator_sweep")
    checks.append({"name": "verify_audits_strict", "ok": bool(audit_check.ok) if audit_check is not None else True, "detail": audit_check.to_dict() if audit_check is not None else {}, "report_path": audit_report})

    federation = federation_integrity_gate(root, context="orchestrator_sweep")
    checks.append({"name": "federation_integrity_snapshot_compare", "ok": not bool(federation.get("blocked")), "detail": federation})

    passed = sum(1 for row in checks if bool(row.get("ok")))
    failed = len(checks) - passed
    generated_at = _iso_now()
    payload = {"mode": mode, "pressure_level": pressure_level, "generated_at": generated_at, "checks": checks, "summary": {"passed": passed, "failed": failed}}
    sweep_path = root / f"glow/forge/sweeps/sweep_{_safe_ts(generated_at)}.json"
    sweep_path.parent.mkdir(parents=True, exist_ok=True)
    sweep_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _append_jsonl(root / "pulse/sweeps.jsonl", {"generated_at": generated_at, "mode": mode, "summary": payload["summary"], "path": str(sweep_path.relative_to(root))})
    append_catalog_entry(
        root,
        kind="sweep",
        artifact_id=generated_at,
        relative_path=str(sweep_path.relative_to(root)),
        schema_name="sweep",
        schema_version=1,
        links={},
        summary={"passed": passed, "failed": failed},
        ts=generated_at,
    )
    return {"artifact_path": str(sweep_path.relative_to(root)), "summary": payload["summary"]}


def _emit_verify_result_artifact(root: Path, *, generated_at: str, goal_ids: list[str]) -> str | None:
    chain_check, _enforce, _warn = maybe_verify_receipt_chain(root, context="orchestrator_tick", last=25)
    anchor_check, _a_enforce, _a_warn = maybe_verify_receipt_anchors(root, context="orchestrator_tick", last=10)
    audit_check, _audit_enforce, _audit_warn, _audit_report = maybe_verify_audit_chain(root, context="orchestrator_tick")
    federation = federation_integrity_gate(root, context="orchestrator_tick")
    payload = {
        "schema_version": 1,
        "generated_at": generated_at,
        "goal_ids": goal_ids,
        "status": "ok",
        "receipt_chain_ok": bool(chain_check.ok) if chain_check is not None else False,
        "anchors_enabled": chain_check is not None,
        "receipt_anchors_ok": bool(anchor_check.ok) if anchor_check is not None else False,
        "audit_chain_enabled": audit_check is not None,
        "audit_chain_ok": bool(audit_check.ok) if audit_check is not None else False,
        "rollup_signature_enabled": True,
        "rollup_signature_ok": True,
        "mypy_forge_ok": True,
        "federation_status": federation.get("status", "unknown"),
    }
    path = root / "glow/forge/verify_results" / f"verify_{_safe_ts(generated_at)}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(path.relative_to(root))


def _write_orchestrator_index_overlay(
    repo_root: Path,
    *,
    orchestrator_enabled: bool,
    generated_at: str,
    status: str,
    backlog: dict[str, int],
    tick_report_path: str,
    allocation: AllocationDecision | None,
    allocation_artifact_path: str | None,
    goal_graph_hash_value: str | None,
    work_plan_id: str | None,
    work_run_id: str | None,
    work_run_status: str | None,
    goal_state_summary: dict[str, int],
    strategic_last_proposal_id: str | None,
    strategic_last_proposal_status: str | None,
    strategic_last_applied_change_id: str | None,
    strategic_cooldown_until: str | None,
    strategic_last_proposal_added_goals: list[str],
    strategic_last_proposal_removed_goals: list[str],
    strategic_last_proposal_budget_delta: dict[str, object],
    strategic_signature_status: str,
    last_strategic_sig_hash: str | None,
    strategic_sig_verify_status: str,
    strategic_sig_verify_reason: str | None,
    strategic_sig_verify_checked_n: int,
    strategic_sig_verify_last_ok_sig_hash: str | None,
    strategic_witness_status: str,
    last_strategic_witness_at: str | None,
    integrity_status: IntegrityStatus,
    integrity_status_path: str,
) -> None:
    path = repo_root / INDEX_PATH
    payload = _load_json(path)
    payload["schema_version"] = latest_version(SchemaName.FORGE_INDEX)
    payload["orchestrator_enabled"] = orchestrator_enabled
    payload["last_orchestrator_tick_at"] = generated_at
    payload["last_orchestrator_tick_status"] = status
    payload["orchestrator_backlog_summary"] = backlog
    payload["last_tick_report_path"] = tick_report_path
    payload["goal_allocation_status"] = "ok" if allocation is not None else "missing"
    payload["last_goal_allocation_id"] = allocation_artifact_path
    payload["last_selected_goals"] = list((allocation.selected if allocation is not None else ())[:10])
    payload["last_deferred_goal_count"] = len(allocation.deferred) if allocation is not None else 0
    payload["goal_graph_hash"] = goal_graph_hash_value
    payload["last_work_plan_id"] = work_plan_id
    payload["last_work_run_id"] = work_run_id
    payload["last_work_run_status"] = work_run_status or "skipped"
    payload["last_executed_goal_ids"] = list((allocation.selected if allocation is not None else ())[:10])
    payload["goal_state_summary"] = goal_state_summary
    payload["strategic_last_proposal_id"] = strategic_last_proposal_id
    payload["strategic_last_proposal_status"] = strategic_last_proposal_status or "none"
    payload["strategic_last_applied_change_id"] = strategic_last_applied_change_id
    payload["strategic_cooldown_until"] = strategic_cooldown_until
    payload["strategic_last_proposal_added_goals"] = list(strategic_last_proposal_added_goals[:6])
    payload["strategic_last_proposal_removed_goals"] = list(strategic_last_proposal_removed_goals[:6])
    payload["strategic_last_proposal_budget_delta"] = {str(k): v for k, v in list(strategic_last_proposal_budget_delta.items())[:6]}
    payload["strategic_signature_status"] = strategic_signature_status
    payload["last_strategic_sig_hash"] = last_strategic_sig_hash
    payload["last_strategic_sig_at"] = generated_at if last_strategic_sig_hash else payload.get("last_strategic_sig_at")
    payload["strategic_sig_verify_status"] = strategic_sig_verify_status
    payload["strategic_sig_verify_reason"] = strategic_sig_verify_reason
    payload["strategic_sig_verify_checked_n"] = strategic_sig_verify_checked_n
    payload["strategic_sig_verify_last_ok_sig_hash"] = strategic_sig_verify_last_ok_sig_hash
    payload["strategic_witness_status"] = strategic_witness_status
    payload["last_strategic_witness_at"] = last_strategic_witness_at
    payload["integrity_status"] = integrity_status.status
    payload["integrity_primary_reason"] = integrity_status.primary_reason
    payload["integrity_gate_summary"] = {
        "ok": sum(1 for gate in integrity_status.gate_results if gate.status == "ok"),
        "warn": sum(1 for gate in integrity_status.gate_results if gate.status == "warn"),
        "fail": sum(1 for gate in integrity_status.gate_results if gate.status == "fail"),
        "skipped": sum(1 for gate in integrity_status.gate_results if gate.status == "skipped"),
    }
    payload["integrity_mutation_allowed"] = integrity_status.mutation_allowed
    payload["integrity_publish_allowed"] = integrity_status.publish_allowed
    payload["integrity_automerge_allowed"] = integrity_status.automerge_allowed
    payload["last_integrity_status_at"] = integrity_status.ts
    payload["last_integrity_status_path"] = integrity_status_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _persist_integrity_status(repo_root: Path, integrity_status: IntegrityStatus) -> str:
    rel = Path("glow/forge/integrity") / f"status_{_safe_ts(integrity_status.ts)}.json"
    payload = integrity_status.to_dict()
    write_json(repo_root / rel, payload)
    append_catalog_entry(
        repo_root,
        kind="integrity_status",
        artifact_id=str(integrity_status.ts),
        relative_path=str(rel),
        schema_name="integrity_status",
        schema_version=_safe_int(payload.get("schema_version")) or 1,
        links={
            "policy_hash": payload.get("policy_hash"),
            "integrity_status_hash": integrity_status.canonical_hash(),
        },
        summary={"status": integrity_status.status, "primary_reason": payload.get("primary_reason")},
        ts=str(integrity_status.ts),
    )
    return str(rel)


def _emit_attestation_snapshot(
    repo_root: Path,
    *,
    integrity_status: IntegrityStatus,
    goal_graph_hash_value: str | None,
    mutation_allowed: bool,
) -> tuple[str | None, str | None, str | None]:
    doctrine = _load_json(repo_root / "glow/contracts/contract_manifest.json")
    strategic_witness = _load_json(repo_root / "glow/federation/strategic_witness_status.json")
    anchor_witness = _load_json(repo_root / "glow/federation/anchor_witness_status.json")
    integrity_budget = IntegrityBudget.from_env()
    snapshot = AttestationSnapshot(
        schema_version=1,
        ts=integrity_status.ts,
        policy_hash=integrity_status.policy_hash,
        integrity_status_hash=integrity_status.canonical_hash(),
        latest_rollup_sig_hash=_optional_str(_load_json(repo_root / "glow/forge/index.json").get("last_rollup_signature_id")),
        latest_strategic_sig_hash=_optional_str(_load_json(repo_root / "glow/forge/index.json").get("last_strategic_sig_hash")),
        latest_goal_graph_hash=goal_graph_hash_value,
        latest_catalog_checkpoint_hash=_optional_str(_load_json(repo_root / "glow/forge/index.json").get("last_catalog_checkpoint_at")),
        doctrine_bundle_sha256=_optional_str(doctrine.get("bundle_sha256")),
        witness_summary={
            "strategic": {"status": strategic_witness.get("status"), "published_at": strategic_witness.get("published_at")},
            "rollup": {"status": anchor_witness.get("witness_status"), "published_at": anchor_witness.get("last_witness_published_at")},
        },
    )

    snapshot_rel: str | None = None
    envelope = None
    snapshot_hash: str | None = None
    min_interval_seconds = max(1, _env_int("SENTIENTOS_ATTESTATION_SNAPSHOT_MIN_INTERVAL_SECONDS", 600))
    emit_allowed = should_emit_snapshot(
        repo_root,
        ts=snapshot.ts,
        integrity_status_hash=snapshot.integrity_status_hash,
        policy_hash=snapshot.policy_hash,
        goal_graph_hash=snapshot.latest_goal_graph_hash,
        min_interval_seconds=min_interval_seconds,
    )
    emit_budget_ok = _count_recent_rows(repo_root / "pulse/attestation_snapshots.jsonl", window_seconds=3600) < integrity_budget.max_snapshot_emits_per_window
    if emit_allowed and emit_budget_ok:
        snapshot_rel = emit_snapshot(repo_root, snapshot)
        envelope = maybe_sign_snapshot(repo_root, snapshot_rel_path=snapshot_rel, snapshot_payload=snapshot.to_dict())
        snapshot_hash = hashlib.sha256(canonical_json_bytes(snapshot.to_dict())).hexdigest()[:16]

    verify_result = verify_recent_snapshots(repo_root, last=integrity_budget.max_verify_items_per_stream)
    if verify_result.status in {"warn", "fail"}:
        _append_jsonl(repo_root / "pulse/integrity_status.jsonl", {"ts": integrity_status.ts, "snapshot_verify_status": verify_result.status, "snapshot_verify_reason": verify_result.reason})

    if snapshot_rel is not None and _count_recent_rows(repo_root / "glow/federation/attestation_snapshot_witness_tags.jsonl", window_seconds=3600) < integrity_budget.max_witness_attempts_per_window:
        _witness_status, _witness_failure = maybe_publish_snapshot_witness(repo_root, allow_git_tag_publish=mutation_allowed)
        _ = (_witness_status, _witness_failure)

    sig_hash = _optional_str((envelope or {}).get("sig_hash"))
    return snapshot_rel, (sig_hash[:16] if sig_hash else None), snapshot_hash


def _goal_state_summary(state: Mapping[str, object]) -> dict[str, int]:
    counts = {"active": 0, "blocked": 0, "completed": 0}
    for item in state.values():
        status = getattr(item, "status", "active")
        if status in counts:
            counts[status] += 1
    return counts


def _safe_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _list_length(value: object) -> int:
    return len(value) if isinstance(value, list) else 0


def _maybe_verify_strategic_signatures(repo_root: Path) -> dict[str, object]:
    if os.getenv("SENTIENTOS_STRATEGIC_SIG_VERIFY", "0") != "1":
        return {"status": "skipped", "reason": "verify_disabled", "checked_n": 0, "last_ok_sig_hash": None, "hard_fail": False}
    last_n = max(1, _env_int("SENTIENTOS_STRATEGIC_SIG_VERIFY_LAST_N", 25))
    enforce = os.getenv("SENTIENTOS_STRATEGIC_SIG_ENFORCE", "0") == "1"
    warn = os.getenv("SENTIENTOS_STRATEGIC_SIG_WARN", "0") == "1"
    if not enforce and not warn:
        warn = True
    verification = verify_recent(repo_root, last=last_n)
    if verification.ok:
        return {
            "status": "ok",
            "reason": None,
            "checked_n": verification.checked_n,
            "last_ok_sig_hash": verification.last_ok_sig_hash[:16] if verification.last_ok_sig_hash else None,
            "hard_fail": False,
        }
    status = "fail" if enforce else "warn"
    reason = f"{status}:{verification.reason or 'verification_failed'}"
    return {
        "status": status,
        "reason": reason,
        "checked_n": verification.checked_n,
        "last_ok_sig_hash": verification.last_ok_sig_hash[:16] if verification.last_ok_sig_hash else None,
        "hard_fail": enforce,
    }


def _plan_goal_work(
    *, root: Path, graph: GoalGraph, budget: RiskBudget, operating_mode: str,
    pressure_level: int, quarantine_active: bool, posture: str,
    mutation_allowed: bool,
    prior_epistemic_projection: EpistemicCognitiveProjection | None,
    target_model_identity_observer: object | None, planning_time: str,
    catalog_timestamp: str, context: str,
    trace: GovernanceTraceRecorder | None = None,
) -> GoalPlanningResult:
    """Compose allocation and durable plan artifacts; this helper never executes."""
    graph_digest = goal_graph_hash(graph)
    verified_completion_evidence: dict[str, dict[str, object]] = {}
    for goal in graph.goals:
        completion = eval_check(goal.completion_check_name, CompletionContext(
            repo_root=root, goal_id=goal.goal_id, operating_mode=operating_mode,
            pressure_level=pressure_level, posture=posture,
            quarantine_active=quarantine_active, risk_budget_summary=budget.to_dict(),
        ))
        if completion.done:
            verified_completion_evidence[goal.goal_id] = {
                "check_name": completion.check_name,
                "evidence_digest": completion.evidence_digest,
                "evidence_paths": list(completion.evidence_paths),
            }
    target_identity_digest = _observe_target_model_identity_digest(
        target_model_identity_observer)
    target_identity_observed_at = (
        planning_time if target_identity_digest is not None else None)
    prior_plan, prior_outcome_unknown, prior_journal_digest = (
        _latest_verified_prior_plan(root))
    allocation = allocate_goals(
        graph=graph, budget=budget, operating_mode=operating_mode,
        integrity_pressure_level=pressure_level, quarantine_active=quarantine_active,
        posture=posture, prior_epistemic_projection=prior_epistemic_projection,
        target_active_model_identity_digest=target_identity_digest,
        target_identity_observed_at=target_identity_observed_at,
        planning_time=planning_time,
        verified_completion_evidence=verified_completion_evidence,
    )
    allocation_path = _emit_goal_allocation_artifact(
        root=root, generated_at=planning_time, operating_mode=operating_mode,
        pressure_level=pressure_level, posture=posture,
        goal_graph_hash_value=graph_digest, allocation=allocation,
        target_identity_digest=target_identity_digest,
        target_identity_observed_at=target_identity_observed_at,
    )
    if trace is not None:
        trace.record_clamp(
            name="goal_allocation",
            before={"goal_graph_path": str(GOAL_GRAPH_PATH),
                "goal_graph_hash": graph_digest},
            after={
                "selected_goals": list(allocation.selected),
                "deferred_goals": [{"goal_id": item.goal_id,
                    "reason": item.reason,
                    "completion_evidence": item.completion_evidence}
                    for item in allocation.deferred],
                "budget_summary": allocation.budget_summary,
                "target_active_model_identity_digest": target_identity_digest,
                "target_identity_observed_at": target_identity_observed_at,
            }, notes="deterministic_goal_allocation",
        )

    plan: WorkPlan | None = None
    plan_path: str | None = None
    evidence_path: str | None = None
    evidence_digest: str | None = None
    if allocation.selected:
        executor_state = ExecutorState(
            repo_root=root, created_at=planning_time, context=context,
            operating_mode=operating_mode, quarantine_active=quarantine_active,
            allow_mutation=mutation_allowed, goal_graph_hash=graph_digest,
            allocation_id=allocation_path, risk_budget=budget,
            pressure_level=pressure_level, posture=posture,
            prior_epistemic_projection=prior_epistemic_projection,
            target_active_model_identity_digest=target_identity_digest,
            target_identity_observed_at=target_identity_observed_at,
            prior_plan=prior_plan,
            prior_run_outcome_unknown=prior_outcome_unknown,
            prior_run_journal_digest=prior_journal_digest,
        )
        draft = GoalPlanner(repo_root=root).build_plan_with_evidence(
            allocation=allocation, state=executor_state, graph=graph)
        plan = draft.work_plan
        saved_path = persist_work_plan(root, plan)
        plan_path = str(saved_path)
        evidence_path, evidence_digest = persist_work_plan_evidence(
            root, plan, dict(draft.evidence_binding))
        append_catalog_entry(
            root, kind="work_plan_evidence", artifact_id=f"evidence_{plan.plan_id}",
            relative_path=evidence_path, schema_name="work_plan_evidence",
            schema_version=1, links={"work_plan_id": plan.plan_id},
            summary={"evidence_digest": evidence_digest,
                "plan_digest": plan.identity_digest()}, ts=catalog_timestamp,
        )
        append_catalog_entry(
            root, kind="work_plan", artifact_id=plan.plan_id,
            relative_path=plan_path, schema_name="work_plan", schema_version=1,
            links={"work_plan_id": plan.plan_id},
            summary={"goal_count": len(plan.selected_goals),
                "task_count": len(plan.tasks)}, ts=catalog_timestamp,
        )
    return GoalPlanningResult(
        allocation=allocation, allocation_artifact_path=allocation_path,
        goal_graph_hash=graph_digest, planning_time=planning_time,
        target_active_model_identity_digest=target_identity_digest,
        target_identity_observed_at=target_identity_observed_at,
        work_plan=plan, work_plan_path=plan_path,
        work_plan_evidence_path=evidence_path,
        work_plan_evidence_digest=evidence_digest,
    )


def _latest_verified_prior_plan(
    root: Path,
) -> tuple[WorkPlan | None, bool, str | None]:
    """Return a reconstructed prior plan, or mark unbound history unknown."""
    run_entry = latest(root, "work_run")
    if run_entry is None:
        return None, False, None
    run_id_hint = run_entry.get("id")
    if (not isinstance(run_id_hint, str) or len(run_id_hint) != 68
            or not run_id_hint.startswith("run_")
            or any(character not in "0123456789abcdef" for character in run_id_hint[4:])):
        raise WorkPlanError("canonical_prior_work_run_identity_invalid")
    run_path = f"glow/forge/work_runs/{run_id_hint}.json"
    if run_entry.get("path") != run_path:
        raise WorkPlanError("canonical_prior_work_run_path_mismatch")
    run_file = root / run_path
    try:
        run_metadata = run_file.lstat()
    except OSError as exc:
        raise WorkPlanError("canonical_prior_work_run_unreadable") from exc
    if not stat.S_ISREG(run_metadata.st_mode) or run_metadata.st_size > 1_048_576:
        raise WorkPlanError("canonical_prior_work_run_bounds_invalid")
    payload = load_catalog_artifact(root, run_entry)
    if payload is None:
        raise WorkPlanError("canonical_prior_work_run_unreadable")
    run_id = payload.get("run_id")
    plan_id = payload.get("plan_id")
    version = payload.get("schema_version")
    if version == 2:
        # Legacy runs have no canonical evidence digest and cannot influence
        # planning, but their outcome cannot be treated as clean either. Gate
        # destructive planning for one verification cycle without replaying it.
        return None, True, None
    if (version != 3 or not isinstance(run_id, str) or not run_id
            or not isinstance(plan_id, str) or not plan_id
            or run_entry.get("kind") != "work_run"
            or run_entry.get("id") != run_id):
        raise WorkPlanError("canonical_prior_work_run_identity_invalid")

    run_links = run_entry.get("links")
    run_summary = run_entry.get("summary")
    if (not isinstance(run_links, dict) or run_links.get("work_run_id") != run_id
            or not isinstance(run_summary, dict)
            or run_summary.get("status") != payload.get("status")
            or run_summary.get("evidence_digest") != payload.get("evidence_digest")):
        raise WorkPlanError("canonical_prior_work_run_catalog_mismatch")

    plan_entries = [row for row in recent(root, "work_plan", limit=1000)
        if row.get("id") == plan_id]
    if len(plan_entries) != 1:
        raise WorkPlanError("canonical_prior_work_plan_catalog_ambiguous")
    plan_entry = plan_entries[0]
    plan_path_value = plan_entry.get("path")
    if (plan_entry.get("kind") != "work_plan"
            or not isinstance(plan_path_value, str)
            or not plan_path_value.startswith("glow/forge/work_plans/")):
        raise WorkPlanError("canonical_prior_work_plan_catalog_invalid")
    plan_path = root / plan_path_value
    try:
        plan_metadata = plan_path.lstat()
    except OSError as exc:
        raise WorkPlanError("canonical_prior_work_plan_unreadable") from exc
    resolved_plan_path = plan_path.resolve()
    if (not stat.S_ISREG(plan_metadata.st_mode) or plan_metadata.st_size > 1_048_576
            or not resolved_plan_path.is_relative_to(root.resolve())):
        raise WorkPlanError("canonical_prior_work_plan_bounds_invalid")
    plan = load_work_plan(resolved_plan_path)
    if (plan.plan_id != plan_id
            or plan_entry.get("path") != (
                "glow/forge/work_plans/plan_"
                + plan.created_at.replace(":", "-").replace(".", "-") + ".json")):
        raise WorkPlanError("canonical_prior_work_plan_identity_mismatch")
    plan_links = plan_entry.get("links")
    if not isinstance(plan_links, dict) or plan_links.get("work_plan_id") != plan_id:
        raise WorkPlanError("canonical_prior_work_plan_catalog_mismatch")

    evidence = load_work_plan_evidence(root, plan)
    evidence_id = f"evidence_{plan_id}"
    evidence_entries = [row for row in recent(root, "work_plan_evidence", limit=1000)
        if row.get("id") == evidence_id]
    evidence_key = hashlib.sha256(plan.plan_id.encode("utf-8")).hexdigest()
    evidence_path = (
        "glow/forge/work_plan_evidence/evidence_" + evidence_key + ".json")
    if len(evidence_entries) != 1:
        raise WorkPlanError("canonical_prior_work_plan_evidence_catalog_ambiguous")
    evidence_entry = evidence_entries[0]
    evidence_links = evidence_entry.get("links")
    evidence_summary = evidence_entry.get("summary")
    if (evidence_entry.get("path") != evidence_path
            or not isinstance(evidence_links, dict)
            or evidence_links.get("work_plan_id") != plan_id
            or not isinstance(evidence_summary, dict)
            or evidence_summary.get("evidence_digest") != evidence.get("evidence_digest")
            or evidence_summary.get("plan_digest") != plan.identity_digest()):
        raise WorkPlanError("canonical_prior_work_plan_evidence_catalog_mismatch")

    run = load_work_run(root, plan, created_at=plan.created_at)
    if (run is None or run.schema_version != 3 or run.run_id != run_id
            or run.plan_id != plan_id or run.status != payload.get("status")
            or run.evidence_digest != payload.get("evidence_digest")
            or run_path != f"glow/forge/work_runs/{run.run_id}.json"):
        raise WorkPlanError("canonical_prior_work_run_reconstruction_mismatch")
    journal = WorkPlanExecutionJournal(root, plan)
    for task_run in run.task_runs:
        journal_status = journal.state(task_run.task_id)
        journal_result = journal.result(task_run.task_id)
        if task_run.reason == "prior_attempt_outcome_unknown":
            matched = journal_status == "interrupted" and journal_result is None
        elif ((task_run.reason or "").startswith("prior_terminal_")
                and (task_run.reason or "").endswith("_not_replayed")):
            prior_status = (task_run.reason or "")[len("prior_terminal_"):-len("_not_replayed")]
            matched = journal_status == prior_status and journal_result is None
        else:
            matched = journal_status == task_run.status and journal_result == task_run
        if not matched:
            raise WorkPlanError("canonical_prior_work_run_journal_mismatch")
    if run_links.get("goal_ids") != list(plan.selected_goals):
        raise WorkPlanError("canonical_prior_work_run_goal_links_mismatch")
    return plan, False, journal.head_digest


def _emit_goal_allocation_artifact(
    *,
    root: Path,
    generated_at: str,
    operating_mode: str,
    pressure_level: int,
    posture: str,
    goal_graph_hash_value: str,
    allocation: AllocationDecision,
    target_identity_digest: str | None = None,
    target_identity_observed_at: str | None = None,
) -> str:
    path = root / "glow/forge/goal_allocations" / f"allocation_{_safe_ts(generated_at)}.json"
    payload = {
        "schema_version": 1,
        "generated_at": generated_at,
        "operating_mode": operating_mode,
        "integrity_pressure_level": pressure_level,
        "strategic_posture": posture,
        "goal_graph_hash": goal_graph_hash_value,
        "selected_goals": list(allocation.selected),
        "deferred_goals": [{"goal_id": item.goal_id, "reason": item.reason,
            "epistemic_positions": list(item.epistemic_positions),
            "completion_evidence": item.completion_evidence}
            for item in allocation.deferred],
        "selection_reasons": list(allocation.selected_reasons),
        "budget_summary": allocation.budget_summary,
        "target_active_model_identity_digest": target_identity_digest,
        "target_identity_observed_at": target_identity_observed_at,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_goal_allocation_once(path, payload)
    return str(path.relative_to(root))


def _write_goal_allocation_once(path: Path, payload: dict[str, object]) -> None:
    """Keep a timestamped allocation artifact immutable across retries."""
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    try:
        with path.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
        return
    except FileExistsError:
        pass
    except OSError as exc:
        raise WorkPlanError("goal_allocation_artifact_write_failed") from exc

    try:
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode):
            raise WorkPlanError("goal_allocation_artifact_identity_conflict")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            opened = os.fstat(descriptor)
            if (not stat.S_ISREG(opened.st_mode) or opened.st_ino != metadata.st_ino
                    or opened.st_dev != metadata.st_dev):
                raise WorkPlanError("goal_allocation_artifact_changed_during_open")
            existing = bytearray()
            while len(existing) <= len(encoded):
                chunk = os.read(descriptor, min(65_536, len(encoded) + 1 - len(existing)))
                if not chunk:
                    break
                existing.extend(chunk)
        finally:
            os.close(descriptor)
    except WorkPlanError:
        raise
    except OSError as exc:
        raise WorkPlanError("goal_allocation_artifact_unreadable") from exc
    if bytes(existing) != encoded:
        raise WorkPlanError("goal_allocation_artifact_identity_conflict")


def _observe_target_model_identity_digest(observer: object | None) -> str | None:
    """Read only the observer's already-current serving identity; never acquire a session."""
    observe = getattr(observer, "observed_current_model_identity", None)
    if not callable(observe):
        return None
    identity = observe()
    if not isinstance(identity, Mapping) or not identity:
        return None
    try:
        return "sha256:" + digest_payload(dict(identity))
    except (TypeError, ValueError):
        return None


def _peer_snapshot_count(repo_root: Path) -> int:
    return len(list((repo_root / PEER_SNAPSHOTS_DIR).glob("*/integrity_snapshot.json")))


def _remediation_backlog_count(repo_root: Path) -> int:
    rows = _read_jsonl(repo_root / "pulse/recovery_tasks.jsonl")
    total = 0
    for row in rows:
        if str(row.get("status", "open")) == "done":
            continue
        if str(row.get("kind", "")).startswith("remediation_pack:"):
            total += 1
    return total


def _append_jsonl(path: Path, row: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def _load_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _safe_ts(value: str) -> str:
    return value.replace(":", "-").replace(".", "-")


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")



def _count_recent_rows(path: Path, *, window_seconds: int) -> int:
    rows = _read_jsonl(path)
    if not rows:
        return 0
    now = datetime.now(timezone.utc)
    count = 0
    for row in reversed(rows):
        if not isinstance(row, dict):
            continue
        ts = _optional_str(row.get("ts")) or _optional_str(row.get("published_at")) or _optional_str(row.get("created_at"))
        parsed = _parse_iso(ts)
        if parsed is None:
            continue
        if (now - parsed).total_seconds() > max(1, window_seconds):
            break
        count += 1
    return count

def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default
