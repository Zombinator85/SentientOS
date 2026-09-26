# mypy: disable-error-code="redundant-cast"
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import time
from contextlib import suppress
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, cast

from sentientos.boot_ceremony import (
    BootAnnouncer,
    BootCeremonyError,
    CeremonialScript,
    EventEmitter,
    FirstContact,
)
from sentientos.boot_chronicler import build_boot_ceremony_link
from sentientos.contract_sentinel import ContractSentinel
from sentientos.control_plane_kernel import (
    AuthorityClass,
    ControlActionRequest,
    LifecyclePhase,
    get_control_plane_kernel,
)
from sentientos.forge_daemon import ForgeDaemon
from sentientos.forge_merge_train import ForgeMergeTrain
from sentientos.local_model import LocalModel
from sentientos.local_model_authority import build_local_model_authority_map
from sentientos.governed_local_model_invocation import GovernedLocalModelInvoker
from sentientos.installation_state import InstallationIdentity, InstallationStateRegistry
from sentientos.resident_cognitive_model_serving import (CONFIG_ENV as RESIDENT_SERVING_CONFIG_ENV, ResidentCognitiveModelServingController, ResidentCognitiveServingInvoker, ResidentCognitiveServingSlot, load_config as load_resident_serving_config)
from sentientos.resident_cognitive_model_transition_experiment import (QuiescedDevelopmentalCognitionOwner, ResidentCognitionQuiescenceGate, ResidentCognitiveModelTransitionController, TransitionError, TransitionJournal, developmental_history_boundary)
from sentientos.resident_cognitive_transition_operator import (JOURNAL_CUSTODY as RESIDENT_TRANSITION_JOURNAL_CUSTODY, LiveTransitionConfig, LiveTransitionOperatorRuntime, journal_identity as resident_transition_journal_identity, load_verified_protocol)
from sentientos.resident_cognitive_transition_runtime import ResidentCognitiveTransitionStageOperations
from sentientos.local_model_production_activation import verify_current_activation
from sentientos.codex_task_authority_admission import RESIDENT_DEVELOPMENTAL_WRITEBACK, RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION
from sentientos.resident_developmental_cognition import CONFIG_ENV as RESIDENT_DEVELOPMENTAL_CONFIG_ENV, ResidentDevelopmentalCognitionOwner, load_config as load_resident_developmental_config
from sentientos.resident_developmental_writeback import ResidentDevelopmentalWritebackController
from sentientos.runtime_admission import AdmissionLedger, RuntimeAdmissionAuthority, RuntimeAdmissionVerifier
from sentientos.world_state_board import WorldStateSnapshot
from sentientos.longitudinal_self_model import (LongitudinalSelfModelOwner,
    LongitudinalSelfModelRuntimeConfig, load_runtime_config as load_longitudinal_self_model_config)
from sentientos.genesis_model_advice import GenesisModelAdviceCoordinator
from sentientos.world_state_board import WorldStateBoardBuilder, to_dict
from sentientos.embodiment_self_observation import EmbodimentEvidenceOwner
from sentientos.host_resource_runtime import HostResourceRuntimeCoordinator, HostResourceRuntimeEvaluation, summary_for_evaluation, world_state_records
from sentientos.host_privilege_review_runtime import HostPrivilegeReviewRuntimeCoordinator, HostPrivilegeReviewEvaluation, summary_for_evaluation as privilege_review_summary, world_state_records as privilege_review_world_state_records
from sentientos.host_execution_readiness_runtime import HostExecutionReadinessRuntimeCoordinator, HostExecutionReadinessEvaluation, summary_for_evaluation as execution_readiness_summary, world_state_records as execution_readiness_world_state_records
from sentientos.host_controlled_authorization_runtime import HostControlledAuthorizationRuntimeCoordinator, HostControlledAuthorizationEvaluation, summary_for_evaluation as controlled_authorization_summary, world_state_records as controlled_authorization_world_state_records
from sentientos.host_live_grant_readiness_runtime import HostLiveGrantReadinessRuntimeCoordinator, HostLiveGrantReadinessEvaluation, summary_for_evaluation as live_grant_readiness_summary, world_state_records as live_grant_readiness_world_state_records
from sentientos.host_dry_run_audit_closure_runtime import load_latest_evaluation as load_latest_host_dry_run_audit_closure_evaluation, world_state_records as host_dry_run_audit_closure_world_state_records
from codex.amendments import (
    RepositoryMutationHandoffPlan,
    runtime_cycle as runtime_spec_cycle,
    runtime_next_repository_mutation_handoff,
)
from codex.integrity_daemon import runtime_guard as runtime_integrity_guard
from sentientos.codex_healer import runtime_monitor as runtime_healer_monitor
from sentientos.genesis_forge import CovenantVow, TelemetryStream, runtime_expand as runtime_genesis_expand
from sentientos.governed_improvement_signal_plane import SignalPlaneEvaluation, collect_repository_evidence, evaluate_signal_plane, persist_runtime_artifacts
from sentientos.repository_mutation_handoff import (
    build_repository_mutation_handoff,
    resolve_observed_source_revision,
    resolve_runtime_handoff_root,
    write_handoff_json,
)
from sentientos.maintenance_scheduler_daemon import MaintenanceSchedulerOwner, load_adoption
from sentientos.maintenance_wake_daemon_adoption import MaintenanceWakeOwner, load_adoption as load_wake_adoption
from sentientos.maintenance_successor_generation_adoption import MaintenanceSuccessorGenerationOwner, load_config as load_successor_adoption
from sentientos.maintenance_authority_continuity_auto_derivation import MaintenanceAuthorityContinuityAutoDerivationOwner, load_config as load_continuity_auto_derivation
from sentientos.maintenance_resident_runtime_adoption import MaintenanceResidentRuntimeAdoptionController, load_config as load_resident_adoption
from sentientos.maintenance_resident_runtime_adoption import TRANSITION_ENV as RESIDENT_TRANSITION_ENV
from sentientos.maintenance_resident_runtime_adoption import inspect_transition_custody as inspect_resident_transition_custody

LOGGER = logging.getLogger(__name__)
RESIDENT_COGNITIVE_TRANSITION_LIVE_CONFIG_ENV = "SENTIENTOS_RESIDENT_COGNITIVE_TRANSITION_LIVE_CONFIG"
LONGITUDINAL_SELF_MODEL_CONFIG_ENV = "SENTIENTOS_LONGITUDINAL_SELF_MODEL_CONFIG"


def _prepare_resident_runtime_startup(controller: MaintenanceResidentRuntimeAdoptionController) -> dict[str, Any]:
    """Prove this image before any maintenance owner is allowed to start."""
    marker = os.environ.get(RESIDENT_TRANSITION_ENV)
    if marker:
        return cast(dict[str, Any], controller.complete_post_exec(marker=marker))
    return cast(dict[str, Any], controller.capture_baseline())


def _drive_resident_runtime_transition(
    controller: MaintenanceResidentRuntimeAdoptionController,
    successor_owner: MaintenanceSuccessorGenerationOwner,
    auto_derivation_owner: MaintenanceAuthorityContinuityAutoDerivationOwner | None,
) -> dict[str, Any] | None:
    """Drive only the canonical resident barrier; never owns successor wake."""
    if successor_owner.health().get("status") != "waiting_for_resident_runtime_readiness":
        return None

    def quiesce(timeout: float) -> bool:
        started = time.monotonic()
        if auto_derivation_owner is not None and not auto_derivation_owner.stop():
            return False
        if not successor_owner.stop():
            return False
        return time.monotonic() - started <= timeout

    return cast(dict[str, Any] | None, controller.request_replacement(quiesce=quiesce))


def _start_maintenance_daemon_owners(
    scheduler_adoption_path: str | None, wake_adoption_path: str | None,
    successor_adoption_path: str | None = None,
    resident_controller: MaintenanceResidentRuntimeAdoptionController | None = None,
) -> tuple[MaintenanceSchedulerOwner | None, MaintenanceWakeOwner | None, MaintenanceSuccessorGenerationOwner | None, bool]:
    """Start at most one explicitly selected maintenance cadence owner."""
    scheduler_adoption = load_adoption(scheduler_adoption_path) if scheduler_adoption_path else None
    wake_adoption = load_wake_adoption(wake_adoption_path) if wake_adoption_path else None
    successor_adoption = load_successor_adoption(successor_adoption_path) if successor_adoption_path else None
    enabled = sum(bool(item and item["enabled"]) for item in (scheduler_adoption, wake_adoption, successor_adoption))
    overlapping = enabled > 1
    scheduler_owner = None; wake_owner = None; successor_owner = None
    if not overlapping and scheduler_adoption:
        scheduler_owner = MaintenanceSchedulerOwner(scheduler_adoption); scheduler_owner.start()
    if not overlapping and wake_adoption:
        wake_owner = MaintenanceWakeOwner(wake_adoption); wake_owner.start()
    if not overlapping and successor_adoption:
        successor_owner = (MaintenanceSuccessorGenerationOwner(successor_adoption,
            successor_start_readiness_guard=resident_controller.readiness_guard)
            if resident_controller else MaintenanceSuccessorGenerationOwner(successor_adoption))
        setattr(successor_owner, "_sentientos_started", bool(successor_owner.start()))
    return scheduler_owner, wake_owner, successor_owner, overlapping


def _start_maintenance_daemon_owners_after_resident_decision(
    scheduler_adoption_path: str | None, wake_adoption_path: str | None,
    successor_adoption_path: str | None,
    resident_controller: MaintenanceResidentRuntimeAdoptionController | None,
    *, resident_blocked: bool,
) -> tuple[MaintenanceSchedulerOwner | None, MaintenanceWakeOwner | None, MaintenanceSuccessorGenerationOwner | None, bool]:
    """Make blocked resident posture a pre-construction, zero-owner decision."""
    if resident_blocked:
        return None, None, None, False
    return _start_maintenance_daemon_owners(
        scheduler_adoption_path, wake_adoption_path, successor_adoption_path, resident_controller)


def _start_maintenance_continuity_auto_derivation(
    config_path: str | None, selected_successor_path: str | None,
    successor_owner: MaintenanceSuccessorGenerationOwner | None, overlapping: bool,
) -> tuple[MaintenanceAuthorityContinuityAutoDerivationOwner | None, dict[str, Any]]:
    """Start the complementary derivation owner only beside its exact handoff owner."""
    if not config_path:
        return None, {"status": "disabled", "read_only": True}
    try:
        config = load_continuity_auto_derivation(config_path)
        if (overlapping or successor_owner is None or not getattr(successor_owner, "_sentientos_started", False) or not selected_successor_path or
                Path(config["successor_adoption_config_path"]).resolve() != Path(selected_successor_path).resolve()):
            return None, {"status": "blocked", "reason": "exact_successor_adoption_owner_not_running", "read_only": True}
        owner = MaintenanceAuthorityContinuityAutoDerivationOwner(config)
        if not owner.start():
            return None, owner.health()
        return owner, owner.health()
    except Exception as exc:
        return None, {"status": "blocked", "reason": str(exc), "read_only": True}


def resolve_improvement_evidence_sources(
    repo_root: Path,
    *,
    manifest_path: Path | None = None,
    max_sources: int = 16,
) -> list[dict[str, Any]]:
    """Resolve bounded read-only repository evidence sources for maintenance ticks."""

    root = repo_root.resolve()
    candidates: list[dict[str, Any]] = []
    configured = manifest_path or (
        Path(os.environ["SENTIENTOS_IMPROVEMENT_EVIDENCE_MANIFEST"])
        if os.environ.get("SENTIENTOS_IMPROVEMENT_EVIDENCE_MANIFEST")
        else None
    )
    if configured is not None and configured.exists():
        payload = json.loads(configured.read_text(encoding="utf-8"))
        rows = payload.get("sources", payload) if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise ValueError("malformed_improvement_evidence_manifest")
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("malformed_improvement_evidence_source")
            candidates.append(dict(row))
    else:
        defaults = [
            ("run_tests", root / "glow" / "test_runs" / "test_run_provenance.json"),
            ("coverage", root / "coverage.json"),
            ("mypy", root / "glow" / "mypy" / "mypy_output.txt"),
            ("covenant", root / "glow" / "integrity" / "findings.json"),
            ("capability_gap", root / "glow" / "capabilities" / "observations.json"),
        ]
        candidates.extend(
            {"source_kind": kind, "path": path.as_posix()}
            for kind, path in defaults
            if path.exists()
        )
    out: list[dict[str, Any]] = []
    for row in candidates:
        path = Path(str(row.get("path", "")))
        resolved = path if path.is_absolute() else root / path
        resolved = resolved.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"improvement_evidence_source_outside_repo:{resolved}") from exc
        if not resolved.exists():
            continue
        out.append({**row, "path": resolved.as_posix()})
        if len(out) > max_sources:
            raise ValueError("too_many_improvement_evidence_sources")
    return sorted(out, key=lambda item: (str(item.get("source_kind")), str(item.get("path"))))


class RuntimeMaintenanceSurfaces:
    """Runtime facade that closes sentientosd loop calls onto real subsystem methods."""

    def __init__(self, repo_root: Path, *, repository_mutation_handoff_root: Path | None = None, improvement_evidence_sources: list[dict[str, Any]] | None = None, runtime_state_root: Path | None = None, governed_local_invoker: GovernedLocalModelInvoker | None = None, genesis_advice_source: GenesisModelAdviceCoordinator | None = None, longitudinal_self_model_owner: LongitudinalSelfModelOwner | None = None, resident_developmental_owner: ResidentDevelopmentalCognitionOwner | None = None, resident_cognitive_invoker: Any | None = None, resident_cognition_gate: ResidentCognitionQuiescenceGate | None = None, resident_transition_runtime: Any | None = None, embodiment_evidence_owner: EmbodimentEvidenceOwner | None = None) -> None:
        self._repo_root = Path(repo_root)
        self._repository_mutation_handoff_root = repository_mutation_handoff_root
        self._improvement_evidence_sources = list(improvement_evidence_sources or [])
        self._runtime_state_root = runtime_state_root or Path(os.environ.get("SENTIENTOS_RUNTIME_STATE_ROOT", "/tmp/sentientos-runtime-state"))
        self._identify_admitted = False
        self._governed_local_invoker = governed_local_invoker
        self._genesis_advice_source = genesis_advice_source
        self._world_state_snapshot_built_for_tick: str | None = None
        self._world_state_snapshot: WorldStateSnapshot | None = None
        self._embodiment_evidence_owner = embodiment_evidence_owner
        self._longitudinal_self_model_owner = longitudinal_self_model_owner
        self._longitudinal_self_model_config: LongitudinalSelfModelRuntimeConfig | None = None
        self._longitudinal_self_model_configuration_error: str | None = None
        if self._longitudinal_self_model_owner is None and os.environ.get(LONGITUDINAL_SELF_MODEL_CONFIG_ENV):
            try:
                self._longitudinal_self_model_config = load_longitudinal_self_model_config(
                    os.environ[LONGITUDINAL_SELF_MODEL_CONFIG_ENV])
                if self._longitudinal_self_model_config.enabled:
                    self._longitudinal_self_model_owner = LongitudinalSelfModelOwner(
                        self._longitudinal_self_model_config.custody_root)
                    self._longitudinal_self_model_owner.history()  # verify the complete durable chain now
            except Exception as exc:
                self._longitudinal_self_model_configuration_error = f"{type(exc).__name__}:{exc}"
        self._resident_developmental_owner: Any | None = resident_developmental_owner
        self._resident_cognition_gate = resident_cognition_gate
        self._resident_transition_runtime = resident_transition_runtime
        self._resident_transition_configuration_error: str | None = None
        self._resident_developmental_configuration_error: str | None = None
        resident_invoker = resident_cognitive_invoker if resident_cognitive_invoker is not None else governed_local_invoker
        if self._resident_developmental_owner is None and os.environ.get(RESIDENT_DEVELOPMENTAL_CONFIG_ENV):
            try:
                config = load_resident_developmental_config(os.environ[RESIDENT_DEVELOPMENTAL_CONFIG_ENV])
                if config.enabled:
                    ledger = AdmissionLedger(config.state_root / "runtime_admissions.json")
                    definitions = {RESIDENT_DEVELOPMENTAL_WRITEBACK: RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION}
                    def current_admission_sequence() -> int:
                        admissions, _ = ledger.load()
                        return max((item.issued_sequence for item in admissions), default=1)
                    def next_admission_sequence() -> int:
                        admissions, revocations = ledger.load()
                        return max([item.issued_sequence for item in admissions] + [item.sequence for item in revocations], default=0) + 1
                    writeback = ResidentDevelopmentalWritebackController(
                        history_root=config.history_root,
                        admission_verifier=RuntimeAdmissionVerifier(definitions=definitions, ledger=ledger),
                        current_sequence=current_admission_sequence,
                    )
                    self._resident_developmental_owner = ResidentDevelopmentalCognitionOwner(
                        config=config, writeback=writeback,
                        admission_authority=RuntimeAdmissionAuthority(definitions=definitions, ledger=ledger),
                        invoker=resident_invoker, current_sequence=next_admission_sequence,
                    ) if resident_invoker is not None else None
                    if resident_invoker is None:
                        self._resident_developmental_configuration_error = "governed_local_invoker_unavailable"
            except Exception as exc:
                self._resident_developmental_configuration_error = f"{type(exc).__name__}:{exc}"
        if self._resident_developmental_owner is not None and self._resident_cognition_gate is not None:
            self._resident_developmental_owner = QuiescedDevelopmentalCognitionOwner(
                self._resident_developmental_owner, self._resident_cognition_gate)
        self._host_resource_runtime = HostResourceRuntimeCoordinator(runtime_state_root=self._runtime_state_root)
        self._host_privilege_review_runtime = HostPrivilegeReviewRuntimeCoordinator(runtime_state_root=self._runtime_state_root)
        self._host_execution_readiness_runtime = HostExecutionReadinessRuntimeCoordinator(runtime_state_root=self._runtime_state_root)
        self._host_controlled_authorization_runtime = HostControlledAuthorizationRuntimeCoordinator(runtime_state_root=self._runtime_state_root)
        self._host_live_grant_readiness_runtime = HostLiveGrantReadinessRuntimeCoordinator(runtime_state_root=self._runtime_state_root)
        self._host_resource_evaluation: HostResourceRuntimeEvaluation | None = None
        self._host_privilege_review_evaluation: HostPrivilegeReviewEvaluation | None = None
        self._host_execution_readiness_evaluation: HostExecutionReadinessEvaluation | None = None
        self._host_controlled_authorization_evaluation: HostControlledAuthorizationEvaluation | None = None
        self._host_live_grant_readiness_evaluation: HostLiveGrantReadinessEvaluation | None = None
        self._feedback: dict[str, Any] = {
            "schema": "runtime_maintenance_feedback:v1",
            "degraded": False,
            "surfaces": {},
        }

    def identify_improvement_signals(self) -> SignalPlaneEvaluation:
        records = collect_repository_evidence(repo_root=self._repo_root, artifacts=self._improvement_evidence_sources)
        evaluation = evaluate_signal_plane(records, repo_root=self._repo_root)
        artifacts = persist_runtime_artifacts(self._runtime_state_root, evaluation, tick_id=datetime.now(timezone.utc).isoformat())
        self._identify_admitted = True
        self._feedback["surfaces"]["governed_improvement_signal_plane"] = {
            "status": "degraded" if evaluation.summary.get("degraded") else "ok",
            "batch_id": evaluation.batch.batch_id,
            "batch_digest": evaluation.batch.batch_digest,
            "input_counts_by_source": dict(evaluation.summary.get("input_counts_by_source", {})),
            "routed_counts_by_disposition": dict(evaluation.summary.get("routed_counts_by_disposition", {})),
            "proposal_count": evaluation.summary.get("proposal_count", 0),
            "blocked_invalid_count": evaluation.summary.get("blocked_invalid_count", 0),
            "adoption_performed": False,
            "repository_mutation_performed": False,
            "provider_network_git_operation_performed": False,
            "runtime_artifacts": artifacts,
        }
        self._current_signal_evaluation = evaluation
        self._refresh_feedback()
        return evaluation


    def run_host_resource_observation_runtime(self, *, tick_id: str) -> dict[str, Any]:
        """Run at most one admitted host-resource observation epoch per tick."""
        correlation_id = f"{tick_id}:host_resource_observation_runtime"
        evaluation = self._host_resource_runtime.run_cycle(correlation_id=correlation_id)
        if evaluation is None:
            feedback = {"status": "not_allowed", "collector_calls": self._host_resource_runtime.collector_call_count, "no_effect_authority": True}
            self._feedback.setdefault("surfaces", {})["host_resource_observation_runtime"] = feedback
            return feedback
        receipt = self._host_resource_runtime.persist_bundle(evaluation, tick_id=tick_id)
        feedback = {**summary_for_evaluation(evaluation), "bundle_digest": receipt.bundle_digest, "artifact_root": receipt.artifact_root}
        self._host_resource_evaluation = evaluation
        self._feedback.setdefault("surfaces", {})["host_resource_observation_runtime"] = feedback
        return feedback

    def run_host_privilege_review_rehearsal_runtime(self, *, tick_id: str) -> dict[str, Any]:
        """Link same-tick host proposal receipts through broker/rehearsal evidence."""
        evaluation = self._host_privilege_review_runtime.run_cycle(tick_id=tick_id, source_evaluation=self._host_resource_evaluation)
        if evaluation is None:
            feedback = {"status": "not_available", "builder_calls": self._host_privilege_review_runtime.builder_call_count, "read_only": True, "rehearsal_only": True, "host_mutation_performed": False}
            self._feedback.setdefault("surfaces", {})["host_privilege_review_rehearsal_runtime"] = feedback
            return feedback
        self._host_privilege_review_evaluation = evaluation
        feedback = {**privilege_review_summary(evaluation), "builder_calls": self._host_privilege_review_runtime.builder_call_count}
        self._feedback.setdefault("surfaces", {})["host_privilege_review_rehearsal_runtime"] = feedback
        return feedback


    def run_host_execution_readiness_authorization_review_runtime(self, *, tick_id: str) -> dict[str, Any]:
        """Close same-tick rehearsal evidence into read-only proof/review records."""
        evaluation = self._host_execution_readiness_runtime.run_cycle(tick_id=tick_id, source_evaluation=self._host_privilege_review_evaluation)
        if evaluation is None:
            feedback = {"status": "not_available", "builder_calls": self._host_execution_readiness_runtime.builder_call_count, "read_only": True, "review_only": True, "authorization_granted": False, "execution_triggered": False, "host_mutation_performed": False}
            self._feedback.setdefault("surfaces", {})["host_execution_readiness_authorization_review_runtime"] = feedback
            return feedback
        self._host_execution_readiness_evaluation = evaluation
        feedback = {**execution_readiness_summary(evaluation), "builder_calls": self._host_execution_readiness_runtime.builder_call_count}
        self._feedback.setdefault("surfaces", {})["host_execution_readiness_authorization_review_runtime"] = feedback
        return feedback


    def run_host_controlled_authorization_safety_runtime(self, *, tick_id: str) -> dict[str, Any]:
        """Close same-tick execution-readiness review into metadata-only authorization/safety records."""
        evaluation = self._host_controlled_authorization_runtime.run_cycle(tick_id=tick_id, source_evaluation=self._host_execution_readiness_evaluation)
        if evaluation is None:
            feedback = {"status": "not_available", "builder_calls": self._host_controlled_authorization_runtime.builder_call_count, "read_only": True, "review_only": True, "live_authorization_granted": False, "fulfillment_granted": False, "execution_triggered": False, "host_mutation_performed": False}
            self._feedback.setdefault("surfaces", {})["host_controlled_authorization_safety_runtime"] = feedback
            return feedback
        self._host_controlled_authorization_evaluation = evaluation
        feedback = {**controlled_authorization_summary(evaluation), "builder_calls": self._host_controlled_authorization_runtime.builder_call_count}
        self._feedback.setdefault("surfaces", {})["host_controlled_authorization_safety_runtime"] = feedback
        return feedback


    def run_host_live_grant_readiness_runtime(self, *, tick_id: str) -> dict[str, Any]:
        """Close same-tick controlled authorization/safety evidence into readiness review records."""
        evaluation = self._host_live_grant_readiness_runtime.run_cycle(tick_id=tick_id, source_evaluation=self._host_controlled_authorization_evaluation)
        if evaluation is None:
            feedback = {"status": "not_available", "builder_calls": self._host_live_grant_readiness_runtime.builder_call_count, "read_only": True, "review_only": True, "approval_packet_only": True, "operator_approval_granted": False, "policy_approval_granted": False, "local_grant_issued": False, "fulfillment_granted": False, "execution_triggered": False, "host_mutation_performed": False}
            self._feedback.setdefault("surfaces", {})["host_live_grant_readiness_runtime"] = feedback
            return feedback
        self._host_live_grant_readiness_evaluation = evaluation
        feedback = {**live_grant_readiness_summary(evaluation), "builder_calls": self._host_live_grant_readiness_runtime.builder_call_count}
        self._feedback.setdefault("surfaces", {})["host_live_grant_readiness_runtime"] = feedback
        return feedback

    def build_world_state_board(self, *, tick_id: str | None = None) -> dict[str, Any]:
        """Persist one terminal read-only world-state snapshot per maintenance tick."""
        tick_key = tick_id or datetime.now(timezone.utc).isoformat()
        if self._world_state_snapshot_built_for_tick == tick_key:
            return dict(self._feedback.get("surfaces", {}).get("world_state_evidence_board", {}))
        records: list[dict[str, Any]] = []
        if self._embodiment_evidence_owner is not None:
            # Explicit injection only: no ambient discovery and no avatar daemon startup.
            records.extend(self._embodiment_evidence_owner.world_state_records())
        signal = self._feedback.get("surfaces", {}).get("governed_improvement_signal_plane", {})
        if isinstance(signal, dict) and signal:
            records.append({"source_kind":"governed_improvement_signal_plane","source_id":"runtime:signal-plane","subject_id":"governed_improvement_signal_plane","subject_kind":"runtime_surface","stage":"proposal","disposition":"degraded" if signal.get("status") == "degraded" else "recorded","payload": {k:v for k,v in signal.items() if k != "runtime_artifacts"}, "observed_at": tick_key})
        host_eval = self._host_resource_evaluation
        if host_eval is not None:
            records.extend(world_state_records(host_eval))
        privilege_eval = self._host_privilege_review_evaluation
        if privilege_eval is not None:
            records.extend(privilege_review_world_state_records(privilege_eval))
        execution_eval = self._host_execution_readiness_evaluation
        if execution_eval is not None:
            records.extend(execution_readiness_world_state_records(execution_eval))
        controlled_eval = self._host_controlled_authorization_evaluation
        if controlled_eval is not None:
            records.extend(controlled_authorization_world_state_records(controlled_eval))
        live_grant_eval = self._host_live_grant_readiness_evaluation
        if live_grant_eval is not None:
            records.extend(live_grant_readiness_world_state_records(live_grant_eval))
        closure_root = Path(os.environ.get("SENTIENTOS_HOST_DRY_RUN_AUDIT_CLOSURE_ROOT", str(self._runtime_state_root / "host_dry_run_audit_closure_runtime")))
        with suppress(Exception):
            closure_eval = load_latest_host_dry_run_audit_closure_evaluation(closure_root)
            if closure_eval is not None:
                records.extend(host_dry_run_audit_closure_world_state_records(closure_eval))
        genesis = self._feedback.get("surfaces", {}).get("genesis_forge", {})
        if isinstance(genesis, dict) and genesis:
            records.append({"source_kind":"genesis_advice","source_id":"runtime:genesis","subject_id":"genesis_forge","subject_kind":"self_amendment","stage":"proposal","disposition":"degraded" if genesis.get("status") == "degraded" else "recorded","payload": genesis, "observed_at": tick_key})
        snapshot = WorldStateBoardBuilder(allowed_roots=(self._runtime_state_root,), max_source_count=128, clock=lambda: datetime.fromisoformat(tick_key.replace("Z", "+00:00"))).build(records)
        self._world_state_snapshot = snapshot
        out_dir = self._runtime_state_root / "world_state_board"
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / "latest.json"
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(to_dict(snapshot), sort_keys=True, indent=2), encoding="utf-8")
        tmp.replace(target)
        feedback = {"status":"degraded" if snapshot.degraded or snapshot.contradicted else "ok", "snapshot_id": snapshot.snapshot_id, "snapshot_digest": snapshot.digest, "entity_count": len(snapshot.entities), "conflict_count": len(snapshot.conflicts), "stale": snapshot.stale, "contradicted": snapshot.contradicted, "artifact": target.as_posix(), "decision_authority": False, "admission_authority": False, "execution_authority": False, "adoption_authority": False, "repository_mutation_authority": False}
        self._feedback["surfaces"]["world_state_evidence_board"] = feedback
        self._world_state_snapshot_built_for_tick = tick_key
        return feedback

    @property
    def current_world_state_snapshot(self) -> WorldStateSnapshot | None:
        """Return the exact validated in-memory snapshot; never reconstruct authority from JSON."""
        return self._world_state_snapshot

    def reconcile_longitudinal_self_model(self, *, tick_id: str) -> dict[str, Any]:
        """Project the same-tick board when an operator explicitly supplies an owner."""
        if self._longitudinal_self_model_configuration_error is not None:
            feedback = {"status": "degraded", "reason": self._longitudinal_self_model_configuration_error,
                        "authority": False}
        elif self._longitudinal_self_model_owner is None:
            feedback = {"status": "disabled", "reason": "owner_not_explicitly_composed", "authority": False}
        elif self._world_state_snapshot is None or self._world_state_snapshot_built_for_tick != tick_id:
            feedback = {"status": "degraded", "reason": "same_tick_world_state_unavailable", "authority": False}
        else:
            try:
                result = self._longitudinal_self_model_owner.reconcile(self._world_state_snapshot, tick_id=tick_id)
                feedback = {"status": "ok", "reconciliation_id": result.reconciliation_id,
                            "reconciliation_digest": result.reconciliation_digest,
                            "generation": result.generation, "snapshot_id": result.snapshot_id,
                            "claim_count": len(result.claims), "authority": False}
            except Exception as exc:
                feedback = {"status": "degraded", "reason": f"{type(exc).__name__}:{exc}", "authority": False}
        self._feedback.setdefault("surfaces", {})["longitudinal_self_model"] = feedback
        self._refresh_feedback()
        return feedback

    def run_resident_developmental_cognition(self, *, tick_id: str) -> dict[str, Any]:
        """Run one configured cycle after the same-tick World-State snapshot exists."""
        if self._resident_developmental_configuration_error is not None:
            feedback = {"status": "degraded", "reason": self._resident_developmental_configuration_error,
                        "write_performed": False, "model_invoked": False, "admission_issued": False}
        elif self._resident_developmental_owner is None:
            feedback = {"status": "disabled", "reason": "configuration_absent_or_disabled",
                        "write_performed": False, "model_invoked": False, "admission_issued": False}
        elif self._world_state_snapshot is None or self._world_state_snapshot_built_for_tick != tick_id:
            feedback = {"status": "degraded", "reason": "same_tick_world_state_unavailable",
                        "write_performed": False, "model_invoked": False, "admission_issued": False}
        else:
            try:
                prior_self_model = None
                config = self._longitudinal_self_model_config
                if (config is not None and config.cognitive_consumption_enabled
                        and self._longitudinal_self_model_owner is not None):
                    prior_self_model = self._longitudinal_self_model_owner.cognitive_projection(
                        before_tick=tick_id, max_claims=config.max_projection_claims,
                        allowed_predicates=config.allowed_predicates)
                if prior_self_model is None:
                    result = self._resident_developmental_owner.run_tick(
                        snapshot=self._world_state_snapshot, tick_id=tick_id)
                else:
                    result = self._resident_developmental_owner.run_tick(
                        snapshot=self._world_state_snapshot, tick_id=tick_id,
                        prior_self_model=prior_self_model)
                feedback = {**asdict(result), "snapshot_object_preserved": True,
                            "memory_posture": "historical_interpretation_not_current_truth"}
            except Exception as exc:
                if getattr(exc, "code", "") == "resident_cognition_quiesced":
                    feedback = {"status": "quiesced", "reason": "intentional_transition_quiescence",
                                "write_performed": False, "model_invoked": False,
                                "admission_issued": False}
                    self._feedback.setdefault("surfaces", {})["resident_developmental_cognition"] = feedback
                    self._refresh_feedback()
                    return feedback
                feedback = {"status": "degraded", "reason": f"{type(exc).__name__}:{exc}",
                            "write_performed": False}
        self._feedback.setdefault("surfaces", {})["resident_developmental_cognition"] = feedback
        self._refresh_feedback()
        return feedback

    def process_resident_cognitive_transition_request(self, *, tick_id: str) -> dict[str, Any]:
        """Process at most one operator packet, after ordinary cognition."""
        if self._resident_transition_configuration_error is not None:
            result = {"status": "blocked", "reason": self._resident_transition_configuration_error,
                      "effect_performed": False, "interrupted": True}
        elif self._resident_transition_runtime is None:
            result = {"status": "disabled", "effect_performed": False}
        else:
            result = self._resident_transition_runtime.process_one()
            result["live_status"] = self._resident_transition_runtime.status()
        self._feedback.setdefault("surfaces", {})["resident_cognitive_transition_operator"] = result
        return result

    def expand(self) -> list[Any]:
        evaluation = getattr(self, "_current_signal_evaluation", evaluate_signal_plane((), repo_root=self._repo_root))
        genesis_inputs = evaluation.genesis_inputs
        telemetry_streams = [
            TelemetryStream(
                name=str(item.get("name")),
                capability=str(item.get("capability")),
                description=str(item.get("description")),
                sample_payload=dict(item.get("sample_payload") or {}),
            )
            for item in genesis_inputs.get("telemetry_streams", [])
            if isinstance(item, dict)
        ]
        vows = [
            CovenantVow(capability=str(item.get("capability")), description=str(item.get("description")))
            for item in genesis_inputs.get("vows", [])
            if isinstance(item, dict)
        ]
        if not self._identify_admitted:
            outcomes = []
        else:
            try:
                outcomes = runtime_genesis_expand(
                    self._repo_root,
                    telemetry_streams=telemetry_streams,
                    vows=vows,
                    proposal_only=True,
                    advice_source=self._genesis_advice_source,
                )
            except TypeError as exc:
                if "advice_source" not in str(exc):
                    raise
                outcomes = runtime_genesis_expand(
                    self._repo_root,
                    telemetry_streams=telemetry_streams,
                    vows=vows,
                    proposal_only=True,
                )
        failed = sum(1 for item in outcomes if str(getattr(item, "status", "")).lower() in {"failed", "deferred_degraded_audit_trust"})
        advice_feedback = dict(getattr(self._genesis_advice_source, "feedback", {}) or {})
        self._feedback["surfaces"]["genesis_forge"] = {
            "status": "degraded" if failed else "ok",
            "failed_or_deferred": failed,
            "outcome_count": len(outcomes),
            "governed_genesis_model_advice": {
                "authority_map_id": getattr(getattr(self._governed_local_invoker, "authority_map", None), "map_id", None),
                "authority_map_digest": getattr(getattr(self._governed_local_invoker, "authority_map", None), "map_digest", None),
                "eligible_model_count": int(getattr(getattr(self._governed_local_invoker, "authority_map", None), "summary", {}).get("eligible_count", 0)) if self._governed_local_invoker else 0,
                "advice_enabled": self._genesis_advice_source is not None,
                **advice_feedback,
                "forbidden_downstream_effects": {"approved": False, "adopted": False, "lineage_integrated": False, "repository_mutation_performed": False},
            },
        }
        self._refresh_feedback()
        return cast(list[Any], outcomes)

    def cycle(self) -> dict[str, Any]:
        evaluation = getattr(self, "_current_signal_evaluation", evaluate_signal_plane((), repo_root=self._repo_root))
        if not self._identify_admitted:
            state = {"panel": "Spec Amendments", "pending": [], "approved": [], "runtime_signal_count": 0, "blocked_by_identify_stage": True}
        else:
            state = cast(dict[str, Any], runtime_spec_cycle(self._repo_root / "integration", signals=evaluation.amendment_inputs))
        pending_items = state.get("pending", [])
        approved_items = state.get("approved", [])
        pending = len(pending_items) if isinstance(pending_items, list) else 0
        self._feedback["surfaces"]["spec_amender"] = {
            "status": "ok",
            "pending": pending,
            "approved": len(approved_items) if isinstance(approved_items, list) else 0,
        }
        self._refresh_feedback()
        return state

    def guard(self) -> dict[str, Any]:
        health = runtime_integrity_guard(self._repo_root / "integration")
        status = str(health.get("status", "unknown")).lower()
        quarantined = int(health.get("quarantined", 0) or 0)
        degraded = status in {"alert", "quarantined"} or quarantined > 0
        self._feedback["surfaces"]["integrity_daemon"] = {
            "status": "degraded" if degraded else "ok",
            "health_status": status,
            "quarantined": quarantined,
            "passed": int(health.get("passed", 0) or 0),
        }
        self._refresh_feedback()
        typed_health: dict[str, Any] = health
        return typed_health

    def monitor(self) -> list[dict[str, Any]]:
        events = runtime_healer_monitor(self._repo_root / "integration")
        quarantined = sum(1 for event in events if bool(event.get("quarantined")))
        statuses = sorted({str(event.get("status", "unknown")) for event in events})
        self._feedback["surfaces"]["codex_healer"] = {
            "status": "degraded" if quarantined else "ok",
            "events": len(events),
            "quarantined_events": quarantined,
            "statuses": statuses,
        }
        self._refresh_feedback()
        return cast(list[dict[str, Any]], events)

    def next_repository_mutation_handoff(self) -> RepositoryMutationHandoffPlan | None:
        return runtime_next_repository_mutation_handoff(self._repo_root / "integration", approved_only=True)

    def emit_repository_mutation_handoff(self, plan: RepositoryMutationHandoffPlan) -> dict[str, Any]:
        observed_revision, _warnings = resolve_observed_source_revision(self._repo_root)
        handoff = build_repository_mutation_handoff(
            plan.proposal,
            repo_root=self._repo_root,
            source_revision=observed_revision,
        )
        output_dir = resolve_runtime_handoff_root(self._repo_root, self._repository_mutation_handoff_root)
        write_handoff_json(handoff, output_dir / f"{handoff['handoff_id'].replace(':', '_')}.json")
        self._feedback["surfaces"]["repository_mutation_handoff"] = {
            "status": "ok",
            "handoff_status": handoff.get("handoff_status"),
            "proposal_id": handoff.get("proposal_id"),
            "metadata_only": True,
        }
        self._refresh_feedback()
        return cast(dict[str, Any], handoff)

    def governance_feedback(self) -> dict[str, Any]:
        return dict(self._feedback)

    def _refresh_feedback(self) -> None:
        surfaces = self._feedback.get("surfaces", {})
        degraded = any(
            isinstance(surface, dict) and str(surface.get("status", "ok")) == "degraded"
            for surface in surfaces.values()
        )
        self._feedback["degraded"] = degraded


def _maintenance_degradation_signal(
    *,
    tick_id: str,
    surface: str,
    correlation_id: str,
    phase_before: Any,
    phase_at_failure: Any,
    exc: BaseException,
) -> dict[str, Any]:
    return {
        "event_type": "runtime_maintenance_degradation",
        "schema": "runtime_maintenance_degradation:v1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tick_id": tick_id,
        "correlation_id": correlation_id,
        "phase": LifecyclePhase.MAINTENANCE.value,
        "phase_before": getattr(phase_before, "value", str(phase_before)),
        "phase_at_failure": getattr(phase_at_failure, "value", str(phase_at_failure)),
        "surface": surface,
        "actor": "sentientosd",
        "severity": "blocking",
        "disposition": "fail_stop_degraded",
        "stopped_active_cycle": True,
        "retry_attempted": False,
        "follow_up_enqueued": False,
        "reinterpreted_as_goal": False,
        "failure_type": type(exc).__name__,
        "failure_message": str(exc),
    }


def _record_maintenance_degradation(*, kernel: Any, signal: dict[str, Any]) -> None:
    logging.getLogger("sentientos.degradation").error(json.dumps(signal, sort_keys=True))
    append = getattr(kernel, "_append", None)
    if callable(append):
        try:
            append(signal)
        except Exception:
            LOGGER.warning(
                "Failed to append runtime maintenance degradation signal",
                extra={"correlation_id": signal.get("correlation_id"), "surface": signal.get("surface")},
                exc_info=True,
            )


def _resident_developmental_owner(surfaces: RuntimeMaintenanceSurfaces) -> ResidentDevelopmentalCognitionOwner:
    owner = surfaces._resident_developmental_owner
    if isinstance(owner, QuiescedDevelopmentalCognitionOwner):
        owner = owner._owner
    if not isinstance(owner, ResidentDevelopmentalCognitionOwner):
        raise TransitionError("resident_developmental_history_owner_required")
    return owner


def _compose_live_resident_transition(*, config_path: str, installation_handle: Any,
        kernel: Any, slot: ResidentCognitiveServingSlot, gate: ResidentCognitionQuiescenceGate,
        developmental_owner: ResidentDevelopmentalCognitionOwner | None = None,
        runtime_surfaces: RuntimeMaintenanceSurfaces | None = None,
        allow_synthetic_evidence_for_tests: bool = False,
        serving_controller_factory: Any = ResidentCognitiveModelServingController,
        clock: Any = lambda: datetime.now(timezone.utc)) -> LiveTransitionOperatorRuntime | None:
    """Compose the live ingress from the exact already-established resident objects."""
    config = LiveTransitionConfig.load(Path(config_path))
    if not config.enabled:
        return None
    if developmental_owner is None:
        if runtime_surfaces is None:
            raise TransitionError("resident_developmental_history_owner_required")
        developmental_owner = _resident_developmental_owner(runtime_surfaces)
    if config.installation_identity != installation_handle.identity.value:
        raise TransitionError("live_transition_installation_identity_mismatch")
    protocol = load_verified_protocol(installation_handle.root,
        protocol_id=config.protocol_id, protocol_digest=config.protocol_digest)
    if protocol.value.get("installation_identity") != installation_handle.identity.value:
        raise TransitionError("transition_protocol_installation_identity_mismatch")
    if config.journal_identity != resident_transition_journal_identity(protocol):
        raise TransitionError("transition_journal_custody_identity_mismatch")
    current = verify_current_activation(installation_handle,
        allow_synthetic_evidence_for_tests=allow_synthetic_evidence_for_tests)
    session = slot.current_controller.current_session()
    if session is None:
        raise TransitionError("hardened_resident_serving_required")
    observed_identity = session.binding.get("observed_loaded_model_identity")
    if observed_identity != protocol.value.get("predecessor_a"):
        raise TransitionError("transition_protocol_predecessor_identity_mismatch")
    initial = protocol.value.get("initial_activation", {})
    active = current["active_state"]
    if (initial.get("state_semantic_digest") != active.get("state_semantic_digest")
            or initial.get("generation") != active.get("generation")):
        raise TransitionError("transition_protocol_initial_activation_mismatch")

    def boundary() -> Mapping[str, Any]:
        verified = verify_current_activation(installation_handle,
            allow_synthetic_evidence_for_tests=allow_synthetic_evidence_for_tests)
        current_session = slot.current_controller.current_session()
        activation = {**dict(verified["active_state"]),
            "receipt_id": verified["activation_receipt"]["receipt_id"],
            "receipt_semantic_digest": verified["activation_receipt"]["receipt_semantic_digest"]}
        return cast(Mapping[str, Any], developmental_history_boundary(store=developmental_owner.writeback.store,
            composition_state_path=developmental_owner.state_path,
            activation=activation, session=current_session.to_dict() if current_session is not None else None))

    journal = TransitionJournal(installation_handle.root / RESIDENT_TRANSITION_JOURNAL_CUSTODY)
    if not journal.entries() and dict(boundary()) != dict(protocol.value.get("initial_history_boundary", {})):
        raise TransitionError("transition_protocol_initial_history_boundary_mismatch")
    operations = ResidentCognitiveTransitionStageOperations(
        installation_handle=installation_handle, control_plane_kernel=kernel,
        protocol=protocol, journal=journal, gate=gate, slot=slot,
        serving_controller_factory=serving_controller_factory, clock=clock,
        allow_synthetic_evidence_for_tests=allow_synthetic_evidence_for_tests)
    controller = ResidentCognitiveModelTransitionController(protocol=protocol, journal=journal,
        gate=gate, slot=slot, history_snapshot=boundary, operations=operations,
        allow_synthetic_approval_for_tests=allow_synthetic_evidence_for_tests, clock=clock)
    # Construction reconstructs journal and proves that any durable quiescence token is
    # still the exact process-local token. A restarted quiesced experiment is blocked.
    if controller.health()["status"] == "interrupted":
        raise TransitionError("transition_journal_interrupted_or_unreconstructable")
    return LiveTransitionOperatorRuntime(config=config,
        installation_root=installation_handle.root, controller=controller, slot=slot, gate=gate,
        clock=clock)


def _run_maintenance_tick(
    *,
    kernel: Any,
    runtime_surfaces: RuntimeMaintenanceSurfaces,
    contract_sentinel: ContractSentinel,
    forge_daemon: ForgeDaemon,
    merge_train: ForgeMergeTrain,
) -> None:
    LOGGER.debug("SentientOS daemon tick")
    phase_before = getattr(kernel, "phase", LifecyclePhase.RUNTIME)
    tick_id = datetime.now(timezone.utc).isoformat()
    current_surface = "maintenance_start"
    current_correlation_id = f"{tick_id}:{current_surface}"

    try:
        kernel.set_phase(LifecyclePhase.MAINTENANCE, actor="sentientosd")
        feedback = runtime_surfaces.governance_feedback()
        current_surface = "identify_improvement_signals"
        current_correlation_id = f"{tick_id}:identify_improvement_signals"
        identify = getattr(runtime_surfaces, "identify_improvement_signals", None)
        identify_allowed = True
        if callable(identify):
            decision, _identify_result = kernel.admit_and_execute(
                ControlActionRequest(
                    action_kind="identify_improvement_signals",
                    authority_class=AuthorityClass.PROPOSAL_EVALUATION,
                    actor="sentientosd",
                    target_subsystem="governed_improvement_signal_plane",
                    requested_phase=LifecyclePhase.MAINTENANCE,
                    metadata={"correlation_id": current_correlation_id},
                ),
                execute=identify,
            )
            identify_allowed = bool(getattr(decision, "allowed", False))
        if not identify_allowed:
            runtime_surfaces._identify_admitted = False
            runtime_surfaces._feedback["surfaces"]["governed_improvement_signal_plane"] = {"status": "degraded", "blocked_by_admission": True}
            _record_maintenance_degradation(
                kernel=kernel,
                signal={
                    "event": "runtime_maintenance_degradation",
                    "tick_id": tick_id,
                    "surface": current_surface,
                    "correlation_id": current_correlation_id,
                    "reason": "identify_improvement_signals_not_admitted",
                    "phase_before": str(getattr(phase_before, "value", phase_before)),
                },
            )
            safe_phase = phase_before if isinstance(phase_before, LifecyclePhase) else LifecyclePhase.RUNTIME
            if safe_phase == LifecyclePhase.MAINTENANCE:
                safe_phase = LifecyclePhase.RUNTIME
            kernel.set_phase(safe_phase, actor="sentientosd")
            return
        if identify_allowed:
            feedback = runtime_surfaces.governance_feedback()
            current_surface = "expand"
            current_correlation_id = f"{tick_id}:expand"
            kernel.admit_and_execute(
                ControlActionRequest(
                    action_kind="expand",
                    authority_class=AuthorityClass.PROPOSAL_EVALUATION,
                    actor="sentientosd",
                    target_subsystem="genesis_forge",
                    requested_phase=LifecyclePhase.MAINTENANCE,
                    startup_symbol="GenesisForge",
                    metadata={"runtime_feedback": feedback, "correlation_id": current_correlation_id},
                ),
                execute=runtime_surfaces.expand,
            )
            feedback = runtime_surfaces.governance_feedback()
            current_surface = "cycle"
            current_correlation_id = f"{tick_id}:cycle"
            kernel.admit_and_execute(
                ControlActionRequest(
                    action_kind="cycle",
                    authority_class=AuthorityClass.SPEC_AMENDMENT,
                    actor="sentientosd",
                    target_subsystem="spec_amender",
                    requested_phase=LifecyclePhase.MAINTENANCE,
                    startup_symbol="SpecAmender",
                    metadata={"runtime_feedback": feedback, "correlation_id": current_correlation_id},
                ),
                execute=runtime_surfaces.cycle,
            )
            feedback = runtime_surfaces.governance_feedback()
            current_surface = "guard"
            current_correlation_id = f"{tick_id}:guard"
            kernel.admit_and_execute(
                ControlActionRequest(
                    action_kind="guard",
                    authority_class=AuthorityClass.PROPOSAL_EVALUATION,
                    actor="sentientosd",
                    target_subsystem="integrity_daemon",
                    requested_phase=LifecyclePhase.MAINTENANCE,
                    startup_symbol="IntegrityDaemon",
                    metadata={"runtime_feedback": feedback, "correlation_id": current_correlation_id},
                ),
                execute=runtime_surfaces.guard,
            )
        feedback = runtime_surfaces.governance_feedback()
        current_surface = "monitor"
        current_correlation_id = f"{tick_id}:monitor"
        kernel.admit_and_execute(
            ControlActionRequest(
                action_kind="monitor",
                authority_class=AuthorityClass.REPAIR,
                actor="sentientosd",
                target_subsystem="codex_healer",
                requested_phase=LifecyclePhase.MAINTENANCE,
                startup_symbol="CodexHealer",
                metadata={"runtime_feedback": feedback, "correlation_id": current_correlation_id},
            ),
            execute=runtime_surfaces.monitor,
        )
        # Sentinel runs after integrity guard so contract artifacts are trustworthy, before forge daemon so queued repairs execute same tick.
        if os.getenv("SENTIENTOS_SENTINEL_ENABLED", "0") == "1":
            current_surface = "sentinel_tick"
            current_correlation_id = f"{tick_id}:sentinel_tick"
            contract_sentinel.tick()
        feedback = runtime_surfaces.governance_feedback()
        current_surface = "forge_tick"
        current_correlation_id = f"{tick_id}:forge_tick"
        kernel.admit_and_execute(
            ControlActionRequest(
                action_kind="forge_tick",
                authority_class=AuthorityClass.REPAIR,
                actor="sentientosd",
                target_subsystem="forge_daemon",
                requested_phase=LifecyclePhase.MAINTENANCE,
                metadata={"runtime_feedback": feedback, "correlation_id": current_correlation_id},
            ),
            execute=forge_daemon.run_tick,
        )
        feedback = runtime_surfaces.governance_feedback()
        current_surface = "merge_tick"
        current_correlation_id = f"{tick_id}:merge_tick"
        kernel.admit_and_execute(
            ControlActionRequest(
                action_kind="merge_tick",
                authority_class=AuthorityClass.REPAIR,
                actor="sentientosd",
                target_subsystem="forge_merge_train",
                requested_phase=LifecyclePhase.MAINTENANCE,
                metadata={"runtime_feedback": feedback, "correlation_id": current_correlation_id},
            ),
            execute=merge_train.tick,
        )
        current_surface = "host_resource_observation_runtime"
        current_correlation_id = f"{tick_id}:host_resource_observation_runtime"
        run_host_resource = getattr(runtime_surfaces, "run_host_resource_observation_runtime", None)
        if callable(run_host_resource):
            run_host_resource(tick_id=tick_id)
        current_surface = "host_privilege_review_rehearsal_runtime"
        current_correlation_id = f"{tick_id}:host_privilege_review_rehearsal_runtime"
        run_privilege_review = getattr(runtime_surfaces, "run_host_privilege_review_rehearsal_runtime", None)
        if callable(run_privilege_review):
            run_privilege_review(tick_id=tick_id)
        current_surface = "host_execution_readiness_authorization_review_runtime"
        current_correlation_id = f"{tick_id}:host_execution_readiness_authorization_review_runtime"
        run_execution_readiness = getattr(runtime_surfaces, "run_host_execution_readiness_authorization_review_runtime", None)
        if callable(run_execution_readiness):
            run_execution_readiness(tick_id=tick_id)
        current_surface = "host_controlled_authorization_safety_runtime"
        current_correlation_id = f"{tick_id}:host_controlled_authorization_safety_runtime"
        run_controlled_authorization = getattr(runtime_surfaces, "run_host_controlled_authorization_safety_runtime", None)
        if callable(run_controlled_authorization):
            run_controlled_authorization(tick_id=tick_id)
        current_surface = "host_live_grant_readiness_runtime"
        current_correlation_id = f"{tick_id}:host_live_grant_readiness_runtime"
        run_live_grant_readiness = getattr(runtime_surfaces, "run_host_live_grant_readiness_runtime", None)
        if callable(run_live_grant_readiness):
            run_live_grant_readiness(tick_id=tick_id)
        current_surface = "world_state_evidence_board"
        current_correlation_id = f"{tick_id}:world_state_evidence_board"
        build_board = getattr(runtime_surfaces, "build_world_state_board", None)
        if callable(build_board):
            build_board(tick_id=tick_id)
        current_surface = "resident_developmental_cognition_then_transition_operator"
        current_correlation_id = f"{tick_id}:resident_developmental_cognition_then_transition_operator"
        _run_resident_cognition_and_transition(runtime_surfaces, tick_id=tick_id)
        # Temporal firewall: cognition can inspect only custody that existed before
        # this tick.  Current World-State reconciliation is deliberately later.
        current_surface = "longitudinal_self_model"
        current_correlation_id = f"{tick_id}:longitudinal_self_model"
        reconcile_self_model = getattr(runtime_surfaces, "reconcile_longitudinal_self_model", None)
        if callable(reconcile_self_model):
            reconcile_self_model(tick_id=tick_id)
        kernel.set_phase(LifecyclePhase.RUNTIME, actor="sentientosd")

        current_surface = "repository_mutation_handoff"
        current_correlation_id = f"{tick_id}:repository_mutation_handoff"
        plan = runtime_surfaces.next_repository_mutation_handoff() if identify_allowed else None
        if plan:
            LOGGER.info("Codex amendment ready for repository mutation handoff review: %s", plan.message)
            runtime_surfaces.emit_repository_mutation_handoff(plan)
    except Exception as exc:
        signal = _maintenance_degradation_signal(
            tick_id=tick_id,
            surface=current_surface,
            correlation_id=current_correlation_id,
            phase_before=phase_before,
            phase_at_failure=getattr(kernel, "phase", "unknown"),
            exc=exc,
        )
        _record_maintenance_degradation(kernel=kernel, signal=signal)
        safe_phase = phase_before if isinstance(phase_before, LifecyclePhase) else LifecyclePhase.RUNTIME
        if safe_phase == LifecyclePhase.MAINTENANCE:
            safe_phase = LifecyclePhase.RUNTIME
        try:
            kernel.set_phase(safe_phase, actor="sentientosd")
        except Exception:
            LOGGER.warning(
                "Failed to restore runtime phase after maintenance degradation",
                extra={"correlation_id": current_correlation_id, "surface": current_surface},
                exc_info=True,
            )
        return


def _run_resident_cognition_and_transition(runtime_surfaces: RuntimeMaintenanceSurfaces,
        *, tick_id: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Preserve the daemon tail order: cognition, then at most one operator request."""
    run_cognition = getattr(runtime_surfaces, "run_resident_developmental_cognition", None)
    cognition = run_cognition(tick_id=tick_id) if callable(run_cognition) else None
    process_transition = getattr(runtime_surfaces, "process_resident_cognitive_transition_request", None)
    transition = process_transition(tick_id=tick_id) if callable(process_transition) else None
    return cognition, transition


async def run_loop(shutdown_event: asyncio.Event, interval_seconds: int = 60) -> None:
    """Run the autonomous Codex maintenance loop."""

    emitter = EventEmitter(LOGGER)
    announcer = BootAnnouncer(emitter)
    ceremony = CeremonialScript(announcer)
    try:
        ceremony.perform()
    except BootCeremonyError:
        LOGGER.critical("Boot ceremony failed. Aborting startup.")
        raise
    first_contact = FirstContact(emitter)
    first_contact.affirm_integrity()
    first_contact.invite_conversation()
    build_boot_ceremony_link(emitter).narrate()
    model = LocalModel.autoload()
    forge_daemon = ForgeDaemon()
    merge_train = ForgeMergeTrain(repo_root=forge_daemon.repo_root)
    contract_sentinel = ContractSentinel()
    kernel = get_control_plane_kernel()
    repo_root = Path.cwd()
    authority_map = build_local_model_authority_map()
    governed_invoker = GovernedLocalModelInvoker(model=model, authority_map=authority_map, runtime_root=repo_root / "sentientos_data" / "runtime")
    genesis_advice = GenesisModelAdviceCoordinator(invoker=governed_invoker, runtime_root=repo_root / "sentientos_data" / "runtime")
    resident_serving_controller = None
    resident_serving_slot = None
    resident_serving_config = None
    resident_serving_error = None
    resident_serving_path = os.environ.get(RESIDENT_SERVING_CONFIG_ENV)
    resident_transition_live_path = os.environ.get(RESIDENT_COGNITIVE_TRANSITION_LIVE_CONFIG_ENV)
    if resident_serving_path:
        try:
            resident_serving_config = load_resident_serving_config(resident_serving_path)
        except Exception as exc:
            resident_serving_error = f"{type(exc).__name__}:{exc}"
    runtime_surfaces = RuntimeMaintenanceSurfaces(
        repo_root,
        improvement_evidence_sources=resolve_improvement_evidence_sources(repo_root),
        governed_local_invoker=governed_invoker,
        genesis_advice_source=genesis_advice,
    )
    adoption_path = os.environ.get("SENTIENTOS_MAINTENANCE_SCHEDULER_ADOPTION_CONFIG")
    wake_adoption_path = os.environ.get("SENTIENTOS_MAINTENANCE_WAKE_ADOPTION_CONFIG")
    successor_adoption_path = os.environ.get("SENTIENTOS_MAINTENANCE_SUCCESSOR_GENERATION_ADOPTION_CONFIG")
    auto_derivation_path = os.environ.get("SENTIENTOS_MAINTENANCE_AUTHORITY_CONTINUITY_AUTO_DERIVATION_CONFIG")
    resident_path = os.environ.get("SENTIENTOS_MAINTENANCE_RESIDENT_RUNTIME_ADOPTION_CONFIG")
    resident_controller = None
    resident_health: dict[str, Any] = {"status": "disabled", "read_only": True}
    if resident_path:
        try:
            resident_config = load_resident_adoption(resident_path)
            if not resident_config["enabled"]:
                if os.environ.get(RESIDENT_TRANSITION_ENV):
                    raise ValueError("disabled_resident_posture_transition_marker_present")
                custody = inspect_resident_transition_custody(resident_config)
                if custody["status"] == "incomplete_resident_transaction":
                    raise ValueError("disabled_resident_posture_incomplete_transition")
                if custody["status"] == "corrupt_or_ambiguous":
                    raise ValueError("disabled_resident_posture_custody_corrupt_or_ambiguous")
                resident_health = {"status": "disabled", "custody_status": custody["status"], "read_only": True}
            else:
                if (not successor_adoption_path or
                        Path(resident_config["successor_adoption_config_path"]).resolve() != Path(successor_adoption_path).resolve() or
                        (resident_config["automatic_continuity_config_path"] and
                         (not auto_derivation_path or Path(resident_config["automatic_continuity_config_path"]).resolve() != Path(auto_derivation_path).resolve()))):
                    raise ValueError("resident_runtime_configuration_binding_mismatch")
                resident_controller = MaintenanceResidentRuntimeAdoptionController(resident_config)
                _prepare_resident_runtime_startup(resident_controller)
                resident_health = resident_controller.health()
        except Exception as exc:
            resident_health = {"status": "blocked", "reason": str(exc), "read_only": True}
            resident_controller = None
    resident_blocked = bool(resident_path and resident_health["status"] == "blocked")
    scheduler_owner, wake_owner, successor_owner, overlapping = _start_maintenance_daemon_owners_after_resident_decision(
        adoption_path, wake_adoption_path, successor_adoption_path,
        resident_controller if resident_path and not resident_blocked else None, resident_blocked=resident_blocked)
    auto_derivation_owner, auto_derivation_health = _start_maintenance_continuity_auto_derivation(
        None if resident_blocked else auto_derivation_path, successor_adoption_path, successor_owner, overlapping
    )
    runtime_surfaces._feedback["surfaces"]["maintenance_scheduler_daemon_adoption"] = (
        scheduler_owner.health() if scheduler_owner is not None else {"status": "disabled", "read_only": True}
    )
    runtime_surfaces._feedback["surfaces"]["maintenance_wake_daemon_adoption"] = (
        {"status": "blocked", "reason": "overlapping_maintenance_daemon_adoptions", "read_only": True}
        if overlapping else wake_owner.health() if wake_owner is not None else {"status": "disabled", "read_only": True}
    )
    runtime_surfaces._feedback["surfaces"]["maintenance_successor_generation_adoption"] = (
        {"status": "blocked", "reason": "overlapping_maintenance_daemon_adoptions", "read_only": True}
        if overlapping else ({"status": "blocked", "reason": "resident_runtime_startup_blocked", "read_only": True}
            if resident_blocked else successor_owner.health() if successor_owner is not None else {"status": "disabled", "read_only": True})
    )
    runtime_surfaces._feedback["surfaces"]["maintenance_authority_continuity_auto_derivation"] = auto_derivation_health
    runtime_surfaces._feedback["surfaces"]["maintenance_resident_runtime_adoption"] = resident_health
    kernel.set_phase(LifecyclePhase.RUNTIME, actor="sentientosd")
    if resident_serving_config is not None and resident_serving_config.enabled:
        try:
            assert resident_serving_config.installation_identity is not None
            handle = InstallationStateRegistry.system().open(
                InstallationIdentity.parse(resident_serving_config.installation_identity))
            resident_serving_controller = ResidentCognitiveModelServingController(handle, kernel, config_digest=resident_serving_config.config_digest)
            resident_serving_controller.establish(
                operation_id=str(resident_serving_config.serving_operation_id),
                expected_activation_state_digest=resident_serving_config.expected_activation_state_digest)
            resident_serving_slot = ResidentCognitiveServingSlot(resident_serving_controller)
            resident_cognition_gate = ResidentCognitionQuiescenceGate()
            candidate_surfaces = RuntimeMaintenanceSurfaces(
                repo_root, improvement_evidence_sources=resolve_improvement_evidence_sources(repo_root),
                governed_local_invoker=governed_invoker, genesis_advice_source=genesis_advice,
                resident_cognitive_invoker=resident_serving_slot,
                resident_cognition_gate=resident_cognition_gate)
            resident_transition_runtime = None
            resident_transition_error = None
            if resident_transition_live_path:
                try:
                    resident_transition_runtime = _compose_live_resident_transition(
                        config_path=resident_transition_live_path, installation_handle=handle,
                        kernel=kernel, slot=resident_serving_slot, gate=resident_cognition_gate,
                        runtime_surfaces=candidate_surfaces)
                except Exception as exc:
                    resident_transition_error = f"{type(exc).__name__}:{exc}"
            if resident_transition_runtime is not None:
                runtime_surfaces = RuntimeMaintenanceSurfaces(
                    repo_root, improvement_evidence_sources=resolve_improvement_evidence_sources(repo_root),
                    governed_local_invoker=governed_invoker, genesis_advice_source=genesis_advice,
                    resident_developmental_owner=_resident_developmental_owner(candidate_surfaces),
                    resident_cognitive_invoker=resident_serving_slot,
                    resident_cognition_gate=resident_cognition_gate,
                    resident_transition_runtime=resident_transition_runtime)
            else:
                runtime_surfaces = candidate_surfaces
            runtime_surfaces._resident_transition_configuration_error = resident_transition_error
        except Exception as exc:
            resident_serving_error = f"{type(exc).__name__}:{exc}"
            if resident_serving_controller is not None:
                resident_serving_controller.close()
                resident_serving_controller = None
            # Enabled mode is deliberately unavailable; never reconstruct with legacy invoker.
            runtime_surfaces = RuntimeMaintenanceSurfaces(
                repo_root, improvement_evidence_sources=resolve_improvement_evidence_sources(repo_root),
                governed_local_invoker=None, genesis_advice_source=genesis_advice)
    if resident_serving_error is not None:
        runtime_surfaces._resident_developmental_configuration_error = resident_serving_error
    if resident_transition_live_path and resident_serving_controller is None:
        runtime_surfaces._resident_transition_configuration_error = (
            runtime_surfaces._resident_transition_configuration_error
            or "hardened_resident_serving_required")
    LOGGER.info("SentientOS daemon initialised with %s", model.describe())

    try:
        while not shutdown_event.is_set():
            if resident_blocked:
                # Blocked resident posture is terminal for this image.
                # Health has already been projected; no maintenance effector may run.
                shutdown_event.set()
                continue
            if scheduler_owner is not None:
                runtime_surfaces._feedback["surfaces"]["maintenance_scheduler_daemon_adoption"] = scheduler_owner.health()
            if wake_owner is not None:
                runtime_surfaces._feedback["surfaces"]["maintenance_wake_daemon_adoption"] = wake_owner.health()
            if successor_owner is not None:
                runtime_surfaces._feedback["surfaces"]["maintenance_successor_generation_adoption"] = successor_owner.health()
            if auto_derivation_owner is not None:
                runtime_surfaces._feedback["surfaces"]["maintenance_authority_continuity_auto_derivation"] = auto_derivation_owner.health()
            if resident_controller is not None and successor_owner is not None:
                try:
                    transition = _drive_resident_runtime_transition(
                        resident_controller, successor_owner, auto_derivation_owner
                    )
                    if transition is not None:
                        # A real execve cannot return.  Returning is permitted only
                        # for the narrow injected boundary used by behavioral proof.
                        resident_health = resident_controller.health()
                        runtime_surfaces._feedback["surfaces"]["maintenance_resident_runtime_adoption"] = resident_health
                        continue
                except Exception as exc:
                    resident_health = {"status": "blocked", "reason": str(exc), "terminal": True, "read_only": True}
                    runtime_surfaces._feedback["surfaces"]["maintenance_resident_runtime_adoption"] = resident_health
                    shutdown_event.set()
                    continue
            _run_maintenance_tick(
                kernel=kernel,
                runtime_surfaces=runtime_surfaces,
                contract_sentinel=contract_sentinel,
                forge_daemon=forge_daemon,
                merge_train=merge_train,
            )

            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=interval_seconds)
            except asyncio.TimeoutError:
                continue
    finally:
        if resident_serving_slot is not None:
            resident_serving_slot.close_current()
        elif resident_serving_controller is not None:
            resident_serving_controller.close()
        if auto_derivation_owner is not None:
            auto_derivation_owner.stop()
        if scheduler_owner is not None:
            scheduler_owner.stop()
        if wake_owner is not None:
            wake_owner.stop()
        if successor_owner is not None:
            successor_owner.stop()

    kernel.set_phase(LifecyclePhase.SHUTDOWN, actor="sentientosd")
    LOGGER.info("SentientOS daemon shutting down")


def _install_signal_handlers(loop: asyncio.AbstractEventLoop, shutdown_event: asyncio.Event) -> None:
    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, shutdown_event.set)


def main(interval_seconds: int = 60) -> None:
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s - %(message)s")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    shutdown_event = asyncio.Event()
    _install_signal_handlers(loop, shutdown_event)
    try:
        loop.run_until_complete(run_loop(shutdown_event, interval_seconds=interval_seconds))
    finally:
        with suppress(RuntimeError):
            loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


if __name__ == "__main__":
    main()
