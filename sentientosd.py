# mypy: disable-error-code="redundant-cast"
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import stat
import tempfile
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
from sentientos.governed_local_model_invocation import GovernedLocalModelInvoker, validate_receipt
from sentientos.installation_state import InstallationIdentity, InstallationStateError, InstallationStateRegistry
from sentientos.resident_cognitive_model_serving import (CONFIG_ENV as RESIDENT_SERVING_CONFIG_ENV, ResidentCognitiveModelServingController, ResidentCognitiveServingInvoker, ResidentCognitiveServingSlot, load_config as load_resident_serving_config)
from sentientos.resident_cognitive_model_transition_experiment import (QuiescedDevelopmentalCognitionOwner, ResidentCognitionQuiescenceGate, ResidentCognitiveModelTransitionController, TransitionError, TransitionJournal, developmental_history_boundary)
from sentientos.resident_cognitive_transition_operator import (JOURNAL_CUSTODY as RESIDENT_TRANSITION_JOURNAL_CUSTODY, LiveTransitionConfig, LiveTransitionOperatorRuntime, journal_identity as resident_transition_journal_identity, load_verified_protocol)
from sentientos.resident_cognitive_transition_runtime import ResidentCognitiveTransitionStageOperations
from sentientos.local_model_production_activation import verify_current_activation
from sentientos.codex_task_authority_admission import (RESIDENT_DEVELOPMENTAL_WRITEBACK,
    RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION, RESIDENT_EPISTEMIC_STATE_MUTATION,
    RESIDENT_EPISTEMIC_STATE_MUTATION_DEFINITION)
from sentientos.resident_developmental_cognition import CONFIG_ENV as RESIDENT_DEVELOPMENTAL_CONFIG_ENV, ResidentDevelopmentalCognitionOwner, load_config as load_resident_developmental_config
from sentientos.resident_developmental_writeback import ResidentDevelopmentalWritebackController
from sentientos.persistent_epistemic_state import PersistentEpistemicStateOwner
from sentientos.resident_epistemic_development import (CONFIG_ENV as EPISTEMIC_DEVELOPMENT_CONFIG_ENV,
    ResidentEpistemicDevelopmentRuntime, load_epistemic_development_config)
from sentientos.resident_epistemic_state_mutation import ResidentEpistemicStateMutationController
from sentientos.runtime_admission import AdmissionLedger, RuntimeAdmissionAuthority, RuntimeAdmissionVerifier
from sentientos.world_state_board import WorldStateSnapshot, WorldStateSourceKind, record_digest
from sentientos.causal_introspection import (CausalIntrospectionRuntime, CaptureContext,
    IntrospectionConfig, LiveOwnerMetadataProvider, ProviderRegistration,
    load_config as load_causal_introspection_config)
from sentientos.longitudinal_self_model import (LongitudinalSelfModelOwner,
    LongitudinalSelfModelRuntimeConfig, load_runtime_config as load_longitudinal_self_model_config)
from sentientos.genesis_model_advice import GenesisModelAdviceCoordinator
from sentientos.world_state_board import WorldStateBoardBuilder, to_dict
from sentientos.embodiment_self_observation import EmbodimentEvidenceOwner
from sentientos.embodiment_proposal_review import load_selected_review_world_state_records
from sentientos.embodiment_fulfillment import (load_selected_fulfillment_world_state_records,
    verify_embodied_fulfillment_receipt)
from sentientos.embodied_consequence import (ConsequenceStore,
    validate_world_state_projection_config)
from sentientos.developmental_model_replacement_experiment import ModelReplacementArtifactStore
from sentientos.maintenance_post_adoption_attribution_campaign import (
    MaintenancePostAdoptionAttributionCampaignOwner,
    validate_world_state_projection_config as validate_post_adoption_projection_config,
)
from sentientos.host_resource_runtime import (HostResourceRuntimeCoordinator,
    HostResourceRuntimeEvaluation, summary_for_evaluation, world_state_records,
    resource_consumption_world_state_records, resource_invocation_proposal_lineage_records)
from sentientos.governed_local_model_resource_allocation import GovernedLocalModelResourceLedger
from sentientos.production_chat_resource_observation import (
    ProductionChatResourceObservationError,
    ProductionChatResourceObservationOwner,
)
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
from sentientos.maintenance_initial_posix_resident_commissioning import STARTUP_GATE_ENV, await_initial_commissioning_gate
from sentientos.windows_handle_custody import WindowsHandleCustodyError, read_explicit_file, read_regular_files

LOGGER = logging.getLogger(__name__)
RESIDENT_COGNITIVE_TRANSITION_LIVE_CONFIG_ENV = "SENTIENTOS_RESIDENT_COGNITIVE_TRANSITION_LIVE_CONFIG"
RESOURCE_OBSERVATION_INSTALLATION_ENV = "SENTIENTOS_RESOURCE_OBSERVATION_INSTALLATION_IDENTITY"
RESOURCE_OBSERVATION_PROVISIONING_ENV = "SENTIENTOS_RESOURCE_OBSERVATION_PROVISIONING_ID"
LONGITUDINAL_SELF_MODEL_CONFIG_ENV = "SENTIENTOS_LONGITUDINAL_SELF_MODEL_CONFIG"
EPISTEMIC_STATE_CONFIG_ENV = "SENTIENTOS_EPISTEMIC_STATE_CONFIG"
EMBODIED_CONSEQUENCE_PROJECTION_CONFIG_ENV = "SENTIENTOS_EMBODIED_CONSEQUENCE_PROJECTION_CONFIG"
POST_ADOPTION_ATTRIBUTION_PROJECTION_CONFIG_ENV = "SENTIENTOS_POST_ADOPTION_ATTRIBUTION_PROJECTION_CONFIG"


def _load_embodied_consequence_projection(path: str | None) -> tuple[Any | None, tuple[str, ...], tuple[str, ...], Any | None, tuple[tuple[str, str], ...], tuple[Mapping[str, Any], ...], Path | None, tuple[str, ...], tuple[Mapping[str, Any], ...], Path | None, tuple[str, ...], dict[str, Any]]:
    """Load an explicit, bounded read-only view of selected durable experiments."""
    if path is None:
        return None, (), (), None, (), (), None, (), (), None, (), {"status": "disabled", "read_only": True, "effect_authority": False}
    if os.name not in {"posix", "nt"} or (os.name == "posix" and not hasattr(os, "O_NOFOLLOW")):
        return None, (), (), None, (), (), None, (), (), None, (), {"status": "unsupported", "reason_code": "secure_descriptor_reads_unavailable",
                          "read_only": True, "effect_authority": False}
    descriptor: int | None = None
    try:
        config_path = Path(path)
        if os.name == "nt":
            entries = read_regular_files(config_path.parent,
                max_entries=1, max_file_bytes=65_536, max_total_bytes=65_536,
                selected_names=(config_path.name,))
            if len(entries) != 1 or entries[0][0] != config_path.name:
                raise ValueError("projection_config_missing_or_ambiguous")
            raw = entries[0][1]
        else:
            descriptor = os.open(config_path, os.O_RDONLY | os.O_NOFOLLOW)
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 65_536:
                raise ValueError("projection_config_not_bounded_regular_file")
            chunks: list[bytes] = []
            remaining = 65_537
            while remaining:
                chunk = os.read(descriptor, min(16_384, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            if len(raw) > 65_536 or len(raw) != metadata.st_size:
                raise ValueError("projection_config_size_mismatch")
        config = validate_world_state_projection_config(json.loads(raw.decode("utf-8")))
        if not config["enabled"]:
            return None, (), (), None, (), (), None, (), (), None, (), {"status": "disabled", "read_only": True, "effect_authority": False}
        identities = tuple(config["experiment_result_ids"])
        chain_ids = tuple(config["consequence_chain_ids"])
        review_ids = tuple(config.get("proposal_review_receipt_ids", ()))
        review_path = Path(config["proposal_review_log_path"]) if review_ids else None
        review_records = tuple(load_selected_review_world_state_records(
            path=review_path, review_receipt_ids=review_ids)) if review_ids else ()
        fulfillment_ids = tuple(config.get("fulfillment_receipt_ids", ()))
        fulfillment_path = Path(config["fulfillment_receipt_log_path"]) if fulfillment_ids else None
        fulfillment_records = tuple(load_selected_fulfillment_world_state_records(
            path=fulfillment_path, fulfillment_receipt_ids=fulfillment_ids)) if fulfillment_ids else ()
        store = (ConsequenceStore(Path(config["store_root"]), create_root=False)
            if identities or chain_ids else None)
        # Verify selected artifacts at startup; the tick path re-verifies before
        # projection so replacement or corruption is reported at observation.
        if store is not None:
            store.world_state_records(experiment_result_ids=identities,
                consequence_chain_ids=chain_ids)
        model_runs = tuple((item["run_id"], item["run_digest"])
            for item in config["model_replacement_runs"])
        model_store = (ModelReplacementArtifactStore(Path(config["model_replacement_state_root"]),
            read_only=True) if model_runs else None)
        if model_store is not None:
            model_store.world_state_records(run_refs=model_runs)
        return store, identities, chain_ids, model_store, model_runs, review_records, review_path, review_ids, fulfillment_records, fulfillment_path, fulfillment_ids, {"status": "verified",
            "selected_strategy_result_count": len(identities),
            "selected_consequence_chain_count": len(chain_ids),
            "selected_model_replacement_run_count": len(model_runs),
            "selected_proposal_review_receipt_count": len(review_records),
            "selected_fulfillment_receipt_count": len(fulfillment_records),
            "config_digest": config["config_digest"], "read_only": True, "effect_authority": False}
    except FileNotFoundError:
        return None, (), (), None, (), (), None, (), (), None, (), {"status": "missing", "reason_code": "projection_config_or_store_missing",
                          "read_only": True, "effect_authority": False}
    except Exception as exc:
        reason = str(exc)
        status = ("unsupported" if reason.startswith("consequence_store_unsupported_platform") else
                  "missing" if any(token in reason for token in ("missing", "unavailable")) else "invalid")
        return None, (), (), None, (), (), None, (), (), None, (), {"status": status, "reason_code": reason[:128] or type(exc).__name__,
                          "read_only": True, "effect_authority": False}
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _valid_embodied_fulfillment_world_state_record(item: Mapping[str, Any]) -> bool:
    payload = item.get("payload")
    if not isinstance(payload, Mapping):
        return False
    receipt = {key: value for key, value in payload.items()
        if key not in {"event_time_posture", "observer_issuer_posture", "actual_effect_observed",
            "authority", "effect_proven"}}
    receipt_id = receipt.get("fulfillment_receipt_id")
    return (verify_embodied_fulfillment_receipt(receipt)
        and item.get("digest") == record_digest(item)
        and item.get("source_kind") == "embodiment"
        and item.get("schema_version") == "embodiment.fulfillment_receipt.v2"
        and item.get("source_id") == f"fulfillment-receipt:{receipt_id}"
        and item.get("subject_kind") == "embodied_proposal_fulfillment_receipt"
        and item.get("effect_claimed") is False and item.get("effect_proven") is False)


def _load_post_adoption_attribution_projection(path: str | None) -> tuple[Any | None, tuple[str, ...], dict[str, Any]]:
    """Load one explicit read-only campaign selection; ambient discovery is forbidden."""
    if path is None:
        return None, (), {"status": "disabled", "read_only": True, "effect_authority": False}
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        return None, (), {"status": "unsupported", "reason_code": "secure_descriptor_reads_unavailable",
            "read_only": True, "effect_authority": False}
    descriptor: int | None = None
    try:
        descriptor = os.open(Path(path), os.O_RDONLY | os.O_NOFOLLOW)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 65_536:
            raise ValueError("campaign_projection_config_not_bounded_regular_file")
        chunks: list[bytes] = []
        remaining = metadata.st_size
        while remaining:
            chunk = os.read(descriptor, min(16_384, remaining))
            if not chunk:
                raise ValueError("campaign_projection_config_truncated")
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) != metadata.st_size:
            raise ValueError("campaign_projection_config_size_mismatch")
        config = validate_post_adoption_projection_config(json.loads(raw.decode("utf-8")))
        if not config["enabled"]:
            return None, (), {"status": "disabled", "read_only": True, "effect_authority": False}
        owner = MaintenancePostAdoptionAttributionCampaignOwner(Path(config["store_root"]), read_only=True)
        identities = tuple(config["campaign_ids"])
        records = owner.world_state_records(campaign_ids=identities)
        if len(records) != len(identities):
            raise ValueError("campaign_projection_record_count_mismatch")
        return owner, identities, {"status": "verified", "selected_campaign_count": len(identities),
            "config_digest": config["config_digest"], "read_only": True, "effect_authority": False}
    except FileNotFoundError:
        return None, (), {"status": "missing", "reason_code": "campaign_projection_config_or_store_missing",
            "read_only": True, "effect_authority": False}
    except Exception as exc:
        reason = str(exc)
        status = "unsupported" if "unsupported_platform" in reason else "missing" if "missing" in reason.lower() else "invalid"
        return None, (), {"status": status, "reason_code": reason[:128] or type(exc).__name__,
            "read_only": True, "effect_authority": False}
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _load_epistemic_state_owner(config_path: str | None) -> tuple[PersistentEpistemicStateOwner | None, dict[str, Any]]:
    """Compose custody only from explicit configuration; never scan ambient logs."""
    if not config_path:
        return None, {"status": "disabled", "cognitive_consumption_enabled": False}
    payload = json.loads(read_explicit_file(Path(config_path), max_bytes=65_536).decode("utf-8"))
    expected = {"schema", "custody_root", "allowed_proposition_namespaces", "max_cognitive_projection_count", "cognitive_consumption_enabled"}
    if set(payload) != expected or payload["schema"] != "sentientos.epistemic_runtime_config:v1":
        raise ValueError("epistemic_runtime_configuration_invalid")
    namespaces = payload["allowed_proposition_namespaces"]; maximum = payload["max_cognitive_projection_count"]
    if (not isinstance(namespaces, list) or not namespaces or any(not isinstance(x, str) or not x for x in namespaces)
            or not isinstance(maximum, int) or not 1 <= maximum <= 128
            or not isinstance(payload["cognitive_consumption_enabled"], bool)):
        raise ValueError("epistemic_runtime_configuration_invalid")
    owner = PersistentEpistemicStateOwner(payload["custody_root"], allowed_namespaces=namespaces)
    return owner, {"status": "configured", "max_cognitive_projection_count": maximum,
                   "cognitive_consumption_enabled": payload["cognitive_consumption_enabled"]}


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

    def __init__(self, repo_root: Path, *, repository_mutation_handoff_root: Path | None = None, improvement_evidence_sources: list[dict[str, Any]] | None = None, runtime_state_root: Path | None = None, governed_local_invoker: GovernedLocalModelInvoker | None = None, governed_resource_ledger: GovernedLocalModelResourceLedger | None = None, governed_invocation_receipts: tuple[Mapping[str, Any], ...] = (), resource_observation_owner: ProductionChatResourceObservationOwner | None = None, resource_observation_configuration_status: Mapping[str, Any] | None = None, genesis_advice_source: GenesisModelAdviceCoordinator | None = None, longitudinal_self_model_owner: LongitudinalSelfModelOwner | None = None, epistemic_state_owner: PersistentEpistemicStateOwner | None = None, epistemic_state_config: dict[str, Any] | None = None, epistemic_state_configuration_error: str | None = None, epistemic_development_runtime: ResidentEpistemicDevelopmentRuntime | None = None, resident_developmental_owner: ResidentDevelopmentalCognitionOwner | None = None, resident_cognitive_invoker: Any | None = None, resident_cognition_gate: ResidentCognitionQuiescenceGate | None = None, resident_transition_runtime: Any | None = None, embodiment_evidence_owner: EmbodimentEvidenceOwner | None = None, embodied_consequence_store: Any | None = None, embodied_consequence_result_ids: tuple[str, ...] = (), embodied_consequence_chain_ids: tuple[str, ...] = (), model_replacement_artifact_store: Any | None = None, model_replacement_run_refs: tuple[tuple[str, str], ...] = (), embodied_proposal_review_records: tuple[Mapping[str, Any], ...] = (), embodied_proposal_review_log_path: Path | None = None, embodied_proposal_review_receipt_ids: tuple[str, ...] = (), embodied_fulfillment_records: tuple[Mapping[str, Any], ...] = (), embodied_fulfillment_log_path: Path | None = None, embodied_fulfillment_receipt_ids: tuple[str, ...] = (), embodied_consequence_projection_status: Mapping[str, Any] | None = None, post_adoption_attribution_owner: MaintenancePostAdoptionAttributionCampaignOwner | None = None, post_adoption_attribution_campaign_ids: tuple[str, ...] = (), post_adoption_attribution_projection_status: Mapping[str, Any] | None = None, causal_introspection_runtime: Any | None = None) -> None:
        self._repo_root = Path(repo_root)
        self._repository_mutation_handoff_root = repository_mutation_handoff_root
        self._improvement_evidence_sources = list(improvement_evidence_sources or [])
        self._runtime_state_root = runtime_state_root or Path(os.environ.get("SENTIENTOS_RUNTIME_STATE_ROOT", "/tmp/sentientos-runtime-state"))
        self._identify_admitted = False
        self._governed_local_invoker = governed_local_invoker
        self._governed_resource_ledger = governed_resource_ledger
        self._resource_observation_owner = resource_observation_owner
        self._resource_observation_health: dict[str, Any] = dict(resource_observation_configuration_status or {
            "status": "verified" if resource_observation_owner is not None else "disabled",
            "read_only": True, "effect_authority": False,
        })
        self._governed_invocation_receipts_path = self._runtime_state_root / "governed_local_model_invocation" / "registered_receipts.json"
        self._governed_invocation_receipts = self._recover_governed_invocation_receipts(governed_invocation_receipts)
        self._genesis_advice_source = genesis_advice_source
        self._world_state_snapshot_built_for_tick: str | None = None
        self._world_state_snapshot: WorldStateSnapshot | None = None
        self._embodiment_evidence_owner = embodiment_evidence_owner
        if (not isinstance(embodied_consequence_result_ids, tuple)
                or len(embodied_consequence_result_ids) > 32
                or any(not isinstance(identity, str) for identity in embodied_consequence_result_ids)
                or len(embodied_consequence_result_ids) != len(set(embodied_consequence_result_ids))
                or not isinstance(embodied_consequence_chain_ids, tuple)
                or len(embodied_consequence_chain_ids) > 32
                or any(not isinstance(identity, str) for identity in embodied_consequence_chain_ids)
                or len(embodied_consequence_chain_ids) != len(set(embodied_consequence_chain_ids))
                or ((embodied_consequence_result_ids or embodied_consequence_chain_ids)
                    and embodied_consequence_store is None)
                or not isinstance(model_replacement_run_refs, tuple)
                or len(model_replacement_run_refs) > 32
                or any(not isinstance(item, tuple) or len(item) != 2
                       or any(not isinstance(value, str) for value in item)
                       for item in model_replacement_run_refs)
                or len({item[0] for item in model_replacement_run_refs}) != len(model_replacement_run_refs)
                or (model_replacement_run_refs and model_replacement_artifact_store is None)
                or not isinstance(embodied_proposal_review_records, tuple)
                or len(embodied_proposal_review_records) > 32
                or any(not isinstance(item, Mapping) or item.get("digest") != record_digest(item)
                       or item.get("source_kind") != "embodiment"
                       or item.get("schema_version") != "embodiment.proposal.review_receipt.v2"
                       or item.get("subject_kind") != "embodied_strategy_proposal_review"
                       or item.get("stage") != "review"
                       or not isinstance(item.get("payload"), Mapping)
                       or item.get("source_id") != "proposal-review:" + str(item.get("payload", {}).get("review_receipt_id", ""))
                       or item.get("subject_id") != str(item.get("payload", {}).get("proposal_id", ""))
                       or item.get("payload", {}).get("review_binding_posture") not in {
                           "material_digest_bound", "legacy_id_reconstructed"}
                       for item in embodied_proposal_review_records)
                or len({str(item.get("source_id")) for item in embodied_proposal_review_records})
                    != len(embodied_proposal_review_records)
                or not isinstance(embodied_proposal_review_receipt_ids, tuple)
                or len(embodied_proposal_review_receipt_ids) > 32
                or any(not isinstance(item, str) or len(item) != 29 or not item.startswith("eprr_")
                       or any(character not in "0123456789abcdef" for character in item[5:])
                       for item in embodied_proposal_review_receipt_ids)
                or len(set(embodied_proposal_review_receipt_ids)) != len(embodied_proposal_review_receipt_ids)
                or ((embodied_proposal_review_log_path is None) != (not embodied_proposal_review_receipt_ids))
                or (embodied_proposal_review_log_path is not None
                    and (not isinstance(embodied_proposal_review_log_path, Path)
                         or not embodied_proposal_review_log_path.is_absolute()))
                or not isinstance(embodied_fulfillment_records, tuple)
                or len(embodied_fulfillment_records) > 32
                or any(not isinstance(item, Mapping)
                       or not _valid_embodied_fulfillment_world_state_record(item)
                       for item in embodied_fulfillment_records)
                or len({str(item.get("source_id")) for item in embodied_fulfillment_records})
                    != len(embodied_fulfillment_records)
                or not isinstance(embodied_fulfillment_receipt_ids, tuple)
                or len(embodied_fulfillment_receipt_ids) > 32
                or any(not isinstance(item, str) or len(item) != 28 or not item.startswith("efr_")
                       or any(character not in "0123456789abcdef" for character in item[4:])
                       for item in embodied_fulfillment_receipt_ids)
                or len(set(embodied_fulfillment_receipt_ids)) != len(embodied_fulfillment_receipt_ids)
                or ((embodied_fulfillment_log_path is None) != (not embodied_fulfillment_receipt_ids))
                or (embodied_fulfillment_log_path is not None
                    and (not isinstance(embodied_fulfillment_log_path, Path)
                         or not embodied_fulfillment_log_path.is_absolute()))
                or not isinstance(post_adoption_attribution_campaign_ids, tuple)
                or len(post_adoption_attribution_campaign_ids) > 32
                or any(not isinstance(identity, str) for identity in post_adoption_attribution_campaign_ids)
                or len(post_adoption_attribution_campaign_ids) != len(set(post_adoption_attribution_campaign_ids))
                or (post_adoption_attribution_campaign_ids and post_adoption_attribution_owner is None)
                or (post_adoption_attribution_campaign_ids
                    and getattr(post_adoption_attribution_owner, "read_only", False) is not True)):
            raise ValueError("embodied_consequence_projection_injection_invalid")
        self._embodied_consequence_store = embodied_consequence_store
        self._embodied_consequence_result_ids = embodied_consequence_result_ids
        self._embodied_consequence_chain_ids = embodied_consequence_chain_ids
        self._model_replacement_artifact_store = model_replacement_artifact_store
        self._model_replacement_run_refs = model_replacement_run_refs
        self._embodied_proposal_review_records = embodied_proposal_review_records
        self._embodied_proposal_review_log_path = embodied_proposal_review_log_path
        self._embodied_proposal_review_receipt_ids = embodied_proposal_review_receipt_ids
        self._embodied_proposal_review_projection_status = {
            "status": "verified" if embodied_proposal_review_records else "disabled",
            "selected_receipt_count": len(embodied_proposal_review_receipt_ids),
            "read_only": True, "effect_authority": False,
        }
        self._embodied_fulfillment_records = embodied_fulfillment_records
        self._embodied_fulfillment_log_path = embodied_fulfillment_log_path
        self._embodied_fulfillment_receipt_ids = embodied_fulfillment_receipt_ids
        self._embodied_fulfillment_projection_status = {
            "status": "verified" if embodied_fulfillment_records else "disabled",
            "selected_receipt_count": len(embodied_fulfillment_receipt_ids),
            "read_only": True, "effect_authority": False,
        }
        self._embodied_consequence_projection_status = dict(embodied_consequence_projection_status or {
            "status": "verified" if embodied_consequence_store is not None else "disabled",
            "read_only": True, "effect_authority": False})
        self._post_adoption_attribution_owner = post_adoption_attribution_owner
        self._post_adoption_attribution_campaign_ids = post_adoption_attribution_campaign_ids
        self._post_adoption_attribution_projection_status = dict(post_adoption_attribution_projection_status or {
            "status": "verified" if post_adoption_attribution_owner is not None else "disabled",
            "read_only": True, "effect_authority": False})
        self._causal_introspection_runtime = causal_introspection_runtime
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
        self._epistemic_state_owner = epistemic_state_owner
        self._epistemic_state_config = epistemic_state_config or {"status": "disabled", "cognitive_consumption_enabled": False}
        self._epistemic_state_configuration_error = epistemic_state_configuration_error
        self._epistemic_development_runtime = epistemic_development_runtime
        if epistemic_state_owner is None and epistemic_state_config is None and epistemic_state_configuration_error is None:
            try:
                self._epistemic_state_owner, self._epistemic_state_config = _load_epistemic_state_owner(
                    os.environ.get(EPISTEMIC_STATE_CONFIG_ENV))
            except Exception as exc:
                self._epistemic_state_configuration_error = f"{type(exc).__name__}:{exc}"
                self._epistemic_state_config = {"status": "degraded", "cognitive_consumption_enabled": False}
        if self._epistemic_development_runtime is None and os.environ.get(EPISTEMIC_DEVELOPMENT_CONFIG_ENV):
            try:
                if self._epistemic_state_owner is None:
                    raise ValueError("epistemic_state_owner_required")
                development_config = load_epistemic_development_config(
                    os.environ[EPISTEMIC_DEVELOPMENT_CONFIG_ENV])
                ledger = AdmissionLedger(self._runtime_state_root / "epistemic_development" / "runtime_admissions.json")
                definitions = {RESIDENT_EPISTEMIC_STATE_MUTATION: RESIDENT_EPISTEMIC_STATE_MUTATION_DEFINITION}
                def current_epistemic_admission_sequence() -> int:
                    admissions, revocations = ledger.load()
                    return max([item.issued_sequence for item in admissions]
                               + [item.sequence for item in revocations], default=1)
                controller = ResidentEpistemicStateMutationController(
                    owner=self._epistemic_state_owner,
                    admission_verifier=RuntimeAdmissionVerifier(definitions=definitions, ledger=ledger),
                    current_sequence=current_epistemic_admission_sequence,
                    receipt_root=self._runtime_state_root / "epistemic_development")
                self._epistemic_development_runtime = ResidentEpistemicDevelopmentRuntime(
                    config=development_config, owner=self._epistemic_state_owner,
                    mutation_controller=controller,
                    admission_authority=RuntimeAdmissionAuthority(definitions=definitions, ledger=ledger),
                    admission_ledger=ledger)
            except Exception as exc:
                self._epistemic_state_configuration_error = f"{type(exc).__name__}:{exc}"
        self._resident_developmental_owner: Any | None = resident_developmental_owner
        self._resident_cognition_gate = resident_cognition_gate
        self._resident_transition_runtime = resident_transition_runtime
        self._resident_transition_custody: tuple[Any, TransitionJournal] | None = None
        self._resident_transition_custody_error: str | None = None
        self._resident_software_transition_controller: MaintenanceResidentRuntimeAdoptionController | None = None
        self._resident_software_transition_config: Mapping[str, Any] | None = None
        self._resident_transition_configuration_error: str | None = None
        self._resident_developmental_configuration_error: str | None = None
        self._resident_developmental_configuration_status = (
            "explicitly_injected" if self._resident_developmental_owner is not None else "not_configured")
        resident_invoker: Any = resident_cognitive_invoker if resident_cognitive_invoker is not None else governed_local_invoker
        self._resident_cognitive_invoker = resident_invoker
        if self._resident_developmental_owner is None and os.environ.get(RESIDENT_DEVELOPMENTAL_CONFIG_ENV):
            try:
                config = load_resident_developmental_config(os.environ[RESIDENT_DEVELOPMENTAL_CONFIG_ENV])
                if config.enabled:
                    self._resident_developmental_configuration_status = "enabled"
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
                        self._resident_developmental_configuration_status = "blocked_invoker_unavailable"
                else:
                    self._resident_developmental_configuration_status = "disabled"
            except Exception as exc:
                self._resident_developmental_configuration_error = f"{type(exc).__name__}:{exc}"
                self._resident_developmental_configuration_status = "invalid"
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
        self._feedback["surfaces"]["embodied_consequence_projection"] = dict(
            self._embodied_consequence_projection_status)
        self._feedback["surfaces"]["post_adoption_attribution_projection"] = dict(
            self._post_adoption_attribution_projection_status)
        if self._governed_local_invoker is not None:
            self._governed_local_invoker.register_evidence_sink(self.register_governed_invocation_receipt)

    def register_governed_invocation_receipt(self, receipt: Mapping[str, Any]) -> None:
        """Admit an already-produced invocation receipt as bounded evidence.

        Registration is observational only: it validates the receipt identity,
        deduplicates by receipt ID, and never invokes a model or grants effect
        authority. The next World-State build carries the exact receipt fields.
        """
        if os.name != "posix":
            raise ValueError("registered_invocation_receipt_publication_unsupported_platform")
        valid, findings = validate_receipt(receipt)
        if not valid:
            raise ValueError("invalid_governed_invocation_receipt:" + ",".join(findings))
        receipt_id = str(receipt.get("receipt_id") or "")
        if not receipt_id:
            raise ValueError("missing_governed_invocation_receipt_id")
        for item in self._governed_invocation_receipts:
            if str(item.get("receipt_id") or "") == receipt_id:
                if dict(item) != dict(receipt):
                    raise ValueError("conflicting_governed_invocation_receipt")
                return
        if len(self._governed_invocation_receipts) >= 256:
            self._governed_invocation_receipts = self._governed_invocation_receipts[-255:]
        self._governed_invocation_receipts = (*self._governed_invocation_receipts, dict(receipt))
        self._persist_governed_invocation_receipts()

    def _recover_governed_invocation_receipts(self, supplied: tuple[Mapping[str, Any], ...]) -> tuple[dict[str, Any], ...]:
        """Recover evidence only; no model call, ledger mutation, or replay."""
        recovered: list[dict[str, Any]] = []
        try:
            raw_bytes = read_explicit_file(self._governed_invocation_receipts_path,
                max_bytes=16_777_216)
        except WindowsHandleCustodyError as exc:
            if str(exc) == "explicit_file_missing":
                raw_bytes = None
            else:
                raise ValueError("registered_invocation_receipts_artifact_invalid") from exc
        if raw_bytes is not None:
            try:
                raw = json.loads(raw_bytes.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise ValueError("registered_invocation_receipts_artifact_invalid") from exc
            if (not isinstance(raw, list) or len(raw) > 256
                    or any(not isinstance(item, Mapping) for item in raw)
                    or json.dumps(raw, sort_keys=True, separators=(",", ":")).encode("utf-8") != raw_bytes):
                raise ValueError("registered_invocation_receipts_artifact_invalid")
            recovered.extend(dict(item) for item in raw)
        if len(supplied) > 256:
            raise ValueError("registered_invocation_receipts_retention_limit_exceeded")
        for item in supplied:
            candidate = dict(item)
            receipt_id = str(candidate.get("receipt_id") or "")
            prior = next((existing for existing in recovered if str(existing.get("receipt_id") or "") == receipt_id), None)
            if prior is not None and prior != candidate:
                raise ValueError("conflicting_recovered_invocation_receipt")
            if prior is None:
                recovered.append(candidate)
        for item in recovered:
            valid, findings = validate_receipt(item)
            if not valid:
                raise ValueError("invalid_recovered_invocation_receipt:" + ",".join(findings))
        return tuple(recovered[-256:])

    def _persist_governed_invocation_receipts(self) -> None:
        if os.name != "posix":
            raise ValueError("registered_invocation_receipt_publication_unsupported_platform")
        path = self._governed_invocation_receipts_path
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(list(self._governed_invocation_receipts), sort_keys=True,
            separators=(",", ":")).encode("utf-8")
        if len(payload) > 16_777_216:
            raise ValueError("registered_invocation_receipts_size_limit_exceeded")
        descriptor, temporary = tempfile.mkstemp(prefix=".registered-invocation-receipts-",
            suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload); handle.flush(); os.fsync(handle.fileno())
            os.replace(temporary, path)
            directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            try: os.unlink(temporary)
            except FileNotFoundError: pass

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
        selected_embodied_source_ids: set[str] = set()
        selected_proposal_review_source_ids: set[str] = set()
        selected_fulfillment_source_ids: set[str] = set()
        selected_post_adoption_source_ids: set[str] = set()
        records.extend(self._resident_succession_world_state_records(tick_key))
        if self._causal_introspection_runtime is not None:
            # Generation, not a parsed tick string, enforces the temporal firewall.
            next_capture_generation = len(self._causal_introspection_runtime.reconstruct()) + 1
            records.extend(self._causal_introspection_runtime.world_state_records(
                before_generation=next_capture_generation))
        if self._embodiment_evidence_owner is not None:
            # Explicit injection only: no ambient discovery and no avatar daemon startup.
            records.extend(self._embodiment_evidence_owner.world_state_records())
        if self._embodied_proposal_review_log_path is not None:
            try:
                review_records = load_selected_review_world_state_records(
                    path=self._embodied_proposal_review_log_path,
                    review_receipt_ids=self._embodied_proposal_review_receipt_ids)
                records.extend(review_records)
                selected_proposal_review_source_ids.update(str(item["source_id"]) for item in review_records)
                self._embodied_proposal_review_projection_status = {
                    "status": "verified",
                    "selected_receipt_count": len(self._embodied_proposal_review_receipt_ids),
                    "read_only": True, "effect_authority": False,
                }
            except Exception as exc:
                self._embodied_proposal_review_projection_status = {
                    "status": "degraded", "reason_code": type(exc).__name__,
                    "selected_receipt_count": len(self._embodied_proposal_review_receipt_ids),
                    "read_only": True, "effect_authority": False,
                }
            records.append({
                "source_kind": "embodiment", "source_id": "proposal-review-projection:health",
                "subject_id": "configured_proposal_review_selection",
                "subject_kind": "proposal_review_projection_status", "stage": "observation",
                "disposition": self._embodied_proposal_review_projection_status["status"],
                "evidence_strength": "source_integrity_status", "effect_claimed": False,
                "effect_proven": False, "observed_at": tick_key,
                "payload": dict(self._embodied_proposal_review_projection_status),
            })
            self._feedback.setdefault("surfaces", {})["embodied_proposal_review_projection"] = dict(
                self._embodied_proposal_review_projection_status)
        elif self._embodied_proposal_review_records:
            records.extend(dict(item) for item in self._embodied_proposal_review_records)
        if self._embodied_fulfillment_log_path is not None:
            try:
                fulfillment_records = load_selected_fulfillment_world_state_records(
                    path=self._embodied_fulfillment_log_path,
                    fulfillment_receipt_ids=self._embodied_fulfillment_receipt_ids)
                records.extend(fulfillment_records)
                selected_fulfillment_source_ids.update(str(item["source_id"]) for item in fulfillment_records)
                self._embodied_fulfillment_projection_status = {
                    "status": "verified",
                    "selected_receipt_count": len(self._embodied_fulfillment_receipt_ids),
                    "read_only": True, "effect_authority": False,
                }
            except Exception as exc:
                self._embodied_fulfillment_projection_status = {
                    "status": "degraded", "reason_code": type(exc).__name__,
                    "selected_receipt_count": len(self._embodied_fulfillment_receipt_ids),
                    "read_only": True, "effect_authority": False,
                }
            records.append({
                "source_kind": "embodiment", "source_id": "fulfillment-receipt-projection:health",
                "subject_id": "configured_fulfillment_receipt_selection",
                "subject_kind": "fulfillment_receipt_projection_status", "stage": "observation",
                "disposition": self._embodied_fulfillment_projection_status["status"],
                "evidence_strength": "source_integrity_status", "effect_claimed": False,
                "effect_proven": False, "observed_at": tick_key,
                "payload": dict(self._embodied_fulfillment_projection_status),
            })
            self._feedback.setdefault("surfaces", {})["embodied_fulfillment_projection"] = dict(
                self._embodied_fulfillment_projection_status)
        elif self._embodied_fulfillment_records:
            records.extend(dict(item) for item in self._embodied_fulfillment_records)
        if self._embodied_consequence_store is not None and (self._embodied_consequence_result_ids
                or self._embodied_consequence_chain_ids):
            try:
                projected = self._embodied_consequence_store.world_state_records(
                    experiment_result_ids=self._embodied_consequence_result_ids,
                    consequence_chain_ids=self._embodied_consequence_chain_ids)
                records.extend(projected)
                selected_embodied_source_ids.update(str(item["source_id"]) for item in projected)
                self._embodied_consequence_projection_status = {
                    **self._embodied_consequence_projection_status, "status": "verified",
                    "read_only": True, "effect_authority": False}
            except Exception as exc:
                self._embodied_consequence_projection_status = {
                    **self._embodied_consequence_projection_status, "status": "degraded",
                    "reason_code": type(exc).__name__, "read_only": True, "effect_authority": False}
            self._feedback.setdefault("surfaces", {})["embodied_consequence_projection"] = dict(
                self._embodied_consequence_projection_status)
        if self._model_replacement_artifact_store is not None and self._model_replacement_run_refs:
            try:
                projected = self._model_replacement_artifact_store.world_state_records(
                    run_refs=self._model_replacement_run_refs)
                records.extend(projected)
                selected_embodied_source_ids.update(str(item["source_id"]) for item in projected)
            except Exception as exc:
                self._embodied_consequence_projection_status = {
                    **self._embodied_consequence_projection_status, "status": "degraded",
                    "reason_code": type(exc).__name__, "read_only": True, "effect_authority": False}
                self._feedback.setdefault("surfaces", {})["embodied_consequence_projection"] = dict(
                    self._embodied_consequence_projection_status)
        if self._post_adoption_attribution_owner is not None and self._post_adoption_attribution_campaign_ids:
            try:
                projected = self._post_adoption_attribution_owner.world_state_records(
                    campaign_ids=self._post_adoption_attribution_campaign_ids)
                records.extend(projected)
                selected_post_adoption_source_ids.update(str(item["source_id"]) for item in projected)
                self._post_adoption_attribution_projection_status = {
                    **self._post_adoption_attribution_projection_status, "status": "verified",
                    "read_only": True, "effect_authority": False}
            except Exception as exc:
                self._post_adoption_attribution_projection_status = {
                    **self._post_adoption_attribution_projection_status, "status": "degraded",
                    "reason_code": type(exc).__name__, "read_only": True, "effect_authority": False}
            self._feedback.setdefault("surfaces", {})["post_adoption_attribution_projection"] = dict(
                self._post_adoption_attribution_projection_status)
        signal = self._feedback.get("surfaces", {}).get("governed_improvement_signal_plane", {})
        if isinstance(signal, dict) and signal:
            records.append({"source_kind":"governed_improvement_signal_plane","source_id":"runtime:signal-plane","subject_id":"governed_improvement_signal_plane","subject_kind":"runtime_surface","stage":"proposal","disposition":"degraded" if signal.get("status") == "degraded" else "recorded","payload": {k:v for k,v in signal.items() if k != "runtime_artifacts"}, "observed_at": tick_key})
        host_eval = self._host_resource_evaluation
        if host_eval is not None:
            records.extend(world_state_records(host_eval))
        if self._governed_resource_ledger is not None:
            records.extend(resource_consumption_world_state_records(
                ledger=self._governed_resource_ledger,
                invocation_receipts=self._governed_invocation_receipts,
                observed_at=tick_key))
        if self._resource_observation_owner is not None:
            try:
                observation = self._resource_observation_owner.observe()
                resource_records = resource_consumption_world_state_records(
                    ledger=observation.ledger,
                    invocation_receipts=observation.invocation_receipts,
                    observed_at=tick_key,
                    source_identity={
                        "installation_identity": observation.installation_identity,
                        "provisioning_id": observation.provisioning_id,
                        "manifest_digest": observation.manifest_digest,
                    })
                records.extend(resource_records)
                degraded = (observation.invocation_receipt_posture != "verified"
                            or any(item.get("disposition") != "recorded" for item in resource_records))
                self._resource_observation_health = {
                    "status": "degraded" if degraded else "verified",
                    "installation_identity": observation.installation_identity,
                    "provisioning_id": observation.provisioning_id,
                    "ledger_digest": observation.ledger.observation_snapshot()["ledger_digest"],
                    "invocation_receipt_posture": observation.invocation_receipt_posture,
                    "read_only": True, "effect_authority": False,
                }
                records.append({
                    "source_kind": WorldStateSourceKind.RESOURCE_GOVERNOR.value,
                    "source_id": "production_chat_resource_observation:health",
                    "subject_kind": "read_only_resource_custody_source",
                    "subject_id": observation.provisioning_id,
                    "stage": "observation",
                    "disposition": self._resource_observation_health["status"],
                    "evidence_strength": "source_integrity_status",
                    "effect_claimed": False, "effect_proven": False,
                    "observed_at": tick_key,
                    "payload": dict(self._resource_observation_health),
                })
            except ProductionChatResourceObservationError as exc:
                status = exc.status
                self._resource_observation_health = {
                    "status": status, "reason_code": exc.code,
                    "read_only": True, "effect_authority": False,
                }
                records.append({
                    "source_kind": WorldStateSourceKind.RESOURCE_GOVERNOR.value,
                    "source_id": "production_chat_resource_observation:health",
                    "subject_kind": "read_only_resource_custody_source",
                    "subject_id": "configured_resource_provisioning",
                    "stage": "observation", "disposition": status,
                    "evidence_strength": "source_integrity_status",
                    "effect_claimed": False, "effect_proven": False,
                    "observed_at": tick_key,
                    "payload": dict(self._resource_observation_health),
                })
            except Exception as exc:
                self._resource_observation_health = {
                    "status": "invalid", "reason_code": type(exc).__name__,
                    "read_only": True, "effect_authority": False,
                }
                records.append({
                    "source_kind": WorldStateSourceKind.RESOURCE_GOVERNOR.value,
                    "source_id": "production_chat_resource_observation:health",
                    "subject_kind": "read_only_resource_custody_source",
                    "subject_id": "configured_resource_provisioning",
                    "stage": "observation", "disposition": "invalid",
                    "evidence_strength": "source_integrity_status",
                    "effect_claimed": False, "effect_proven": False,
                    "observed_at": tick_key,
                    "payload": dict(self._resource_observation_health),
                })
        elif self._resource_observation_health.get("status") != "disabled":
            records.append({
                "source_kind": WorldStateSourceKind.RESOURCE_GOVERNOR.value,
                "source_id": "production_chat_resource_observation:health",
                "subject_kind": "read_only_resource_custody_source",
                "subject_id": str(self._resource_observation_health.get("provisioning_id")
                                   or "configured_resource_provisioning"),
                "stage": "observation",
                "disposition": str(self._resource_observation_health.get("status", "invalid")),
                "evidence_strength": "source_integrity_status",
                "effect_claimed": False, "effect_proven": False,
                "observed_at": tick_key,
                "payload": dict(self._resource_observation_health),
            })
        # Reconcile while the proposal and resource sources are adjacent in
        # the bounded input. The World-State source-count cap keeps earlier
        # records; deferring this join until the end allowed unrelated later
        # surfaces to silently evict resource lineage before epistemic select.
        records.extend(resource_invocation_proposal_lineage_records(records))
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
        retained_source_ids = {source.source_id for source in snapshot.sources}
        omitted_fulfillment_sources = selected_fulfillment_source_ids - retained_source_ids
        if omitted_fulfillment_sources:
            self._embodied_fulfillment_projection_status = {
                **self._embodied_fulfillment_projection_status,
                "status": "degraded", "reason_code": "world_state_source_limit_omitted_selected_fulfillment",
                "omitted_source_count": len(omitted_fulfillment_sources),
                "read_only": True, "effect_authority": False,
            }
            self._feedback.setdefault("surfaces", {})["embodied_fulfillment_projection"] = dict(
                self._embodied_fulfillment_projection_status)
        omitted_review_sources = selected_proposal_review_source_ids - retained_source_ids
        if omitted_review_sources:
            self._embodied_proposal_review_projection_status = {
                **self._embodied_proposal_review_projection_status,
                "status": "degraded", "reason_code": "world_state_source_limit_omitted_selected_review",
                "omitted_source_count": len(omitted_review_sources),
                "read_only": True, "effect_authority": False,
            }
            self._feedback.setdefault("surfaces", {})["embodied_proposal_review_projection"] = dict(
                self._embodied_proposal_review_projection_status)
        omitted_embodied_sources = selected_embodied_source_ids - retained_source_ids
        if omitted_embodied_sources:
            self._embodied_consequence_projection_status = {
                **self._embodied_consequence_projection_status,
                "status": "degraded",
                "reason_code": "world_state_source_limit_omitted_selected_projection",
                "omitted_source_count": len(omitted_embodied_sources),
                "read_only": True, "effect_authority": False,
            }
            self._feedback["surfaces"]["embodied_consequence_projection"] = dict(
                self._embodied_consequence_projection_status)
        omitted_post_adoption_sources = selected_post_adoption_source_ids - retained_source_ids
        if omitted_post_adoption_sources:
            self._post_adoption_attribution_projection_status = {
                **self._post_adoption_attribution_projection_status,
                "status": "degraded",
                "reason_code": "world_state_source_limit_omitted_selected_projection",
                "omitted_source_count": len(omitted_post_adoption_sources),
                "read_only": True, "effect_authority": False,
            }
            self._feedback["surfaces"]["post_adoption_attribution_projection"] = dict(
                self._post_adoption_attribution_projection_status)
        self._world_state_snapshot = snapshot
        out_dir = self._runtime_state_root / "world_state_board"
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / "latest.json"
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(to_dict(snapshot), sort_keys=True, indent=2), encoding="utf-8")
        tmp.replace(target)
        feedback = {"status":"degraded" if snapshot.degraded or snapshot.contradicted else "ok", "snapshot_id": snapshot.snapshot_id, "snapshot_digest": snapshot.digest, "entity_count": len(snapshot.entities), "conflict_count": len(snapshot.conflicts), "stale": snapshot.stale, "contradicted": snapshot.contradicted, "artifact": target.as_posix(), "decision_authority": False, "admission_authority": False, "execution_authority": False, "adoption_authority": False, "repository_mutation_authority": False}
        self._feedback["surfaces"]["world_state_evidence_board"] = feedback
        self._feedback["surfaces"]["production_chat_resource_observation"] = dict(self._resource_observation_health)
        self._world_state_snapshot_built_for_tick = tick_key
        return feedback

    def _resident_model_provenance_bindings(self, protocol_value: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
        references = protocol_value.get("model_replacement_protocol_references")
        if not isinstance(references, Mapping) or not references:
            legacy: dict[str, dict[str, Any]] = {}
            for role in ("predecessor_a", "successor_b"):
                identity = protocol_value.get(role)
                reference = identity.get("model_development_provenance") if isinstance(identity, Mapping) else None
                reference_digest = identity.get("model_development_provenance_digest") if isinstance(identity, Mapping) else None
                if reference is not None or reference_digest is not None:
                    legacy[role] = {"posture": "referenced_unverified_legacy_binding",
                        "reference": {"manifest_digest": (reference_digest or
                            (reference.get("manifest_digest") if isinstance(reference, Mapping) else None)),
                            "reference_present": True}}
                else:
                    legacy[role] = {"posture": "unavailable_not_protocol_bound"}
            return legacy
        owner = self._resident_developmental_owner
        if isinstance(owner, QuiescedDevelopmentalCognitionOwner):
            owner = owner._owner
        if owner is None:
            posture = {
                "disabled": "unavailable_developmental_configuration_disabled",
                "invalid": "unavailable_invalid_developmental_configuration",
                "blocked_invoker_unavailable": "unavailable_developmental_invoker",
            }.get(self._resident_developmental_configuration_status,
                "unavailable_developmental_owner_not_composed")
            return {role: {"posture": posture} for role in references}
        config = getattr(owner, "config", None)
        artifact_root = getattr(config, "model_replacement_artifact_root", None)
        if artifact_root is None:
            return {role: {"posture": "unavailable_artifact_store_not_configured",
                "protocol_id": reference.get("protocol_id") if isinstance(reference, Mapping) else None,
                "protocol_digest": reference.get("protocol_digest") if isinstance(reference, Mapping) else None}
                for role, reference in references.items()}
        from sentientos.developmental_model_replacement_experiment import (
            DevelopmentalModelReplacementError, ModelReplacementArtifactStore)
        try:
            store = ModelReplacementArtifactStore(Path(artifact_root))
        except (TypeError, ValueError, OSError):
            return {role: {"posture": "contradictory_artifact_store_configuration"}
                    for role in references}
        bindings: dict[str, dict[str, Any]] = {}
        model_roles = {"predecessor_a": "predecessor_a", "successor_b": "successor_b"}
        for transition_role, reference in references.items():
            expected_identity = protocol_value.get(model_roles[transition_role])
            if not isinstance(reference, Mapping):
                bindings[transition_role] = {"posture": "contradictory_protocol_reference"}
                continue
            try:
                replacement, identity, manifest = store.load_verified_protocol_provenance(
                    str(reference.get("protocol_id", "")),
                    str(reference.get("protocol_digest", "")),
                    model_role=str(reference.get("model_role", "")))
                if dict(identity.active_model_identity) != dict(expected_identity or {}):
                    raise DevelopmentalModelReplacementError("provenance_subject_active_identity_mismatch")
            except Exception as exc:
                code = str(exc)
                posture = ("unavailable_protocol" if code == "preregistered_protocol_unavailable"
                           else "unavailable_manifest" if code == "provenance_manifest_unavailable"
                           else "contradictory_provenance_evidence")
                bindings[transition_role] = {"posture": posture, "finding": code,
                    "protocol_id": reference.get("protocol_id"),
                    "protocol_digest": reference.get("protocol_digest")}
                continue
            bindings[transition_role] = {
                "posture": ("verified_source_bound_claim_manifest" if manifest.claims
                    else "verified_manifest_with_unknown_claims"),
                "identity_binding_verified": True,
                "protocol_id": replacement.protocol_id,
                "protocol_digest": replacement.protocol_digest,
                "model_role": reference["model_role"],
                "model_identity_digest": identity.identity_digest,
                "active_model_identity_digest": identity.active_model_identity_digest,
                "provenance_manifest_digest": manifest.manifest_digest,
                "provenance_subject_identity_digest": manifest.subject_identity_digest,
                "provenance_availability": manifest.availability,
                "provenance_claim_count": len(manifest.claims),
            }
        return bindings

    def _resident_succession_world_state_records(self, observed_at: str) -> list[dict[str, Any]]:
        """Expose durable transition events without promoting proposals to observations."""
        records: list[dict[str, Any]] = []
        runtime = self._resident_transition_runtime
        controller = getattr(runtime, "controller", None) if runtime is not None else None
        protocol = getattr(controller, "protocol", None) if controller is not None else None
        journal = getattr(controller, "journal", None) if controller is not None else None
        if protocol is None or journal is None:
            custody = self._resident_transition_custody
            if custody is not None:
                protocol, journal = custody
        if protocol is not None and journal is not None:
                protocol_value = dict(getattr(protocol, "value", {}))
                transition_id = str(protocol_value.get("transition_id") or "unknown")
                predecessor, successor = protocol_value.get("predecessor_a"), protocol_value.get("successor_b")
                provenance_bindings = self._resident_model_provenance_bindings(protocol_value)
                health: dict[str, Any] = {}
                status: dict[str, Any] = {}
                try:
                    entries = journal.entries()[-16:]
                    if controller is not None:
                        health = dict(controller.health())
                    else:
                        unresolved = next((entry for entry in reversed(entries)
                            if entry.get("status") in {"attempted", "effected", "failed", "interrupted"}), None)
                        evidence = unresolved.get("evidence", {}) if isinstance(unresolved, Mapping) else {}
                        health = {"status": "runtime_composition_blocked",
                            "phase": "unknown", "outstanding_stage": (evidence.get("attempted_stage")
                                or evidence.get("failed_stage") or evidence.get("interrupted_stage")),
                            "replay_forbidden": unresolved is not None,
                            "journal_head": entries[-1].get("entry_digest") if entries else "GENESIS"}
                    if runtime is not None:
                        status = runtime.status()
                    else:
                        serving = getattr(self._resident_cognitive_invoker, "current_controller", None)
                        session = serving.current_session() if serving is not None else None
                        identity = session.binding.get("observed_loaded_model_identity") if session is not None else None
                        status = {"resident_model_identity": dict(identity) if isinstance(identity, Mapping) else identity,
                            "resident_serving_session_id": session.session_id if session is not None else None}
                except Exception as exc:
                    records.append({"source_kind": "runtime_supervisor", "source_id": f"resident_transition:{transition_id}:recovery",
                        "subject_id": transition_id, "subject_kind": "model_transition", "stage": "observation",
                        "disposition": "incomplete", "evidence_strength": "unavailable",
                        "payload": {"recovery_posture": "journal_reconstruction_failed", "error_class": type(exc).__name__},
                        "observed_at": None, "effect_claimed": False, "effect_proven": False})
                else:
                    for entry in entries[-128:]:
                        evidence = entry.get("evidence") if isinstance(entry.get("evidence"), Mapping) else {}
                        phase = str(entry.get("phase") or "")
                        disposition = {"completed": "completed", "attempted": "attempted", "effected": "effected",
                                       "failed": "failed", "interrupted": "interrupted"}.get(str(entry.get("status")), "unknown")
                        payload: dict[str, Any] = {"transition_id": transition_id, "transition_phase": phase,
                            "journal_sequence": entry.get("sequence"), "journal_entry_digest": entry.get("entry_digest"),
                            "journal_prior_digest": entry.get("prior_digest"), "journal_status": entry.get("status"),
                            "event_time": entry.get("event_time"),
                            "predecessor_model_identity": predecessor, "proposed_successor_model_identity": successor,
                            "transition_protocol_digest": protocol_value.get("protocol_digest"),
                            "developmental_history_boundary": (protocol_value.get("initial_history_boundary", {}).get("boundary_digest")
                                if isinstance(protocol_value.get("initial_history_boundary"), Mapping) else None),
                            "replay_forbidden": True}
                        successor_provenance = provenance_bindings.get("successor_b",
                            {"posture": "unavailable_not_protocol_bound"})
                        payload["proposed_successor_model_development_provenance"] = successor_provenance
                        payload["model_development_provenance_posture"] = successor_provenance["posture"]
                        predecessor_provenance = provenance_bindings.get("predecessor_a")
                        if predecessor_provenance is not None:
                            payload["predecessor_model_development_provenance"] = predecessor_provenance
                        activation = evidence.get("activation") if isinstance(evidence.get("activation"), Mapping) else None
                        if (activation is not None and entry.get("status") == "completed"
                                and phase in {"b_activation_committed", "a_restoration_activation_committed"}):
                            identity_key = "proposed_successor_model_identity" if phase == "b_activation_committed" else "predecessor_model_identity"
                            payload["activated_model_identity"] = successor if identity_key == "proposed_successor_model_identity" else protocol_value.get("restored_a")
                            payload["activation_receipt_id"] = activation.get("receipt_id")
                            payload["activation_receipt_digest"] = activation.get("receipt_semantic_digest")
                            payload["activation_state_digest"] = activation.get("state_semantic_digest")
                        binding = evidence.get("stage_binding") if isinstance(evidence.get("stage_binding"), Mapping) else None
                        if (binding is not None and entry.get("status") == "completed"
                                and phase in {"b_serving_bound", "restored_a_serving_bound"}):
                            payload["serving_binding_digest"] = binding.get("binding_digest")
                            payload["serving_activation_receipt_id"] = binding.get("activation_receipt_id")
                            payload["serving_activation_receipt_digest"] = binding.get("activation_receipt_digest")
                            payload["serving_expected_model_identity"] = binding.get("expected_model_identity")
                        provenance_identity = (successor_provenance.get("provenance_manifest_digest")
                            or successor_provenance.get("posture", "unknown"))
                        records.append({"source_kind": "runtime_supervisor",
                            "source_id": f"resident_transition:{transition_id}:{entry.get('entry_digest')}:{provenance_identity}",
                            "subject_id": transition_id, "subject_kind": "resident_model_transition",
                            "stage": "observation", "disposition": disposition,
                            "evidence_strength": "validated_transition_journal_entry", "payload": payload,
                            "observed_at": entry.get("event_time"), "effect_claimed": False, "effect_proven": False})
                session_identity = status.get("resident_model_identity")
                if session_identity is not None:
                    running_provenance = next((value for role, value in provenance_bindings.items()
                        if value.get("identity_binding_verified") is True
                        and isinstance(protocol_value.get(role), Mapping)
                        and dict(protocol_value[role]) == dict(session_identity)), None)
                    running_provenance_identity = ((running_provenance or {}).get("provenance_manifest_digest")
                        or (running_provenance or {}).get("posture", "unknown"))
                    records.append({"source_kind": "runtime_supervisor",
                        "source_id": f"resident_serving_session:{status.get('resident_serving_session_id')}:{running_provenance_identity}",
                        "subject_id": str(status.get("resident_serving_session_id") or "resident-serving-session"),
                        "subject_kind": "observed_running_model", "stage": "observation",
                        "disposition": "observed", "evidence_strength": "serving_session_observation",
                        "payload": {"running_model_identity_observed": session_identity,
                            "serving_session_id": status.get("resident_serving_session_id"),
                            "transition_id": transition_id,
                            "model_development_provenance": (running_provenance or
                                {"posture": "unavailable_no_exact_running_identity_binding"})},
                        "observed_at": observed_at, "effect_claimed": False, "effect_proven": False})
                head = health.get("journal_head")
                if head:
                    records.append({"source_kind": "runtime_supervisor",
                        "source_id": f"resident_transition_recovery:{transition_id}:{head}:{health.get('status', 'unknown')}",
                        "subject_id": transition_id, "subject_kind": "resident_model_transition_recovery",
                        "stage": "observation", "disposition": str(health.get("status", "unknown")),
                        "evidence_strength": "reconstructed_transition_journal_posture",
                        "payload": {"transition_id": transition_id, "journal_head": head,
                            "recovery_posture": health.get("status"), "outstanding_stage": health.get("outstanding_stage"),
                            "replay_forbidden": health.get("replay_forbidden", True)},
                        "observed_at": observed_at, "effect_claimed": False, "effect_proven": False})
        elif self._resident_transition_custody_error is not None:
            records.append({"source_kind": "runtime_supervisor", "source_id": "resident_transition:recovery-unavailable",
                "subject_id": "resident-model-transition", "subject_kind": "resident_model_transition_recovery",
                "stage": "observation", "disposition": "incomplete", "evidence_strength": "unavailable",
                "payload": {"recovery_posture": "transition_custody_unavailable",
                    "error_class": self._resident_transition_custody_error, "replay_forbidden": True},
                "observed_at": None, "effect_claimed": False, "effect_proven": False})

        software_controller = self._resident_software_transition_controller
        software_config = (software_controller.config if software_controller is not None
                           else self._resident_software_transition_config)
        if software_config is not None:
            try:
                from sentientos.maintenance_resident_runtime_adoption import (
                    inspect_transition_custody, read_transition_events)
                rows = read_transition_events(software_config, limit=16)
                custody = inspect_transition_custody(software_config)
                software_health = (software_controller.health() if software_controller is not None else
                    self._feedback.get("surfaces", {}).get("maintenance_resident_runtime_adoption", {}))
                baseline = getattr(software_controller, "_baseline", None) if software_controller is not None else None
            except Exception as exc:
                records.append({"source_kind": "runtime_supervisor", "source_id": "resident_software_transition:recovery",
                    "subject_id": "resident_software_transition", "subject_kind": "software_transition",
                    "stage": "observation", "disposition": "incomplete", "evidence_strength": "unavailable",
                    "payload": {"recovery_posture": "journal_reconstruction_failed", "error_class": type(exc).__name__},
                    "observed_at": None, "effect_claimed": False, "effect_proven": False})
            else:
                for row in rows:
                    phase = str(row.get("phase", ""))
                    disposition = "completed" if phase == "resident_adoption_completed" else "attempted"
                    payload = {"transition_id": row.get("transition_id"), "transition_phase": phase,
                        "journal_entry_digest": row.get("event_digest"), "journal_prior_digest": row.get("prior_event_digest"),
                        "event_time": row.get("event_time"),
                        "lineage_id": row.get("lineage_id"), "predecessor_generation_digest": row.get("predecessor_generation_digest"),
                        "successor_generation_digest": row.get("successor_generation_digest"),
                        "predecessor_ordinal": row.get("predecessor_ordinal"), "successor_ordinal": row.get("successor_ordinal"),
                        "continuity_receipt_digest": row.get("continuity_receipt_digest"),
                        "pending_handoff_event_digest": row.get("pending_handoff_event_digest"),
                        "successor_repository_commit": row.get("successor_repository_commit"),
                        "successor_repository_tree": row.get("successor_repository_tree"),
                        "successor_launch_provenance_digest": row.get("successor_launch_provenance_digest"),
                        "replay_forbidden": True}
                    if row.get("readiness_receipt_digest"):
                        payload["readiness_receipt_digest"] = row["readiness_receipt_digest"]
                    records.append({"source_kind": "runtime_supervisor",
                        "source_id": f"resident_software_transition:{row.get('event_digest')}",
                        "subject_id": str(row.get("transition_id") or "resident-software-transition"),
                        "subject_kind": "software_generation_transition", "stage": "observation",
                        "disposition": disposition, "evidence_strength": "validated_software_transition_journal_entry",
                        "payload": payload, "observed_at": row.get("event_time"), "effect_claimed": False, "effect_proven": False})
                if rows:
                    last = rows[-1]
                    transaction_rows = [item for item in rows if item.get("transition_id") == last.get("transition_id")]
                    complete = bool(transaction_rows and transaction_rows[-1].get("phase") == "resident_adoption_completed")
                    records.append({"source_kind": "runtime_supervisor",
                        "source_id": f"resident_software_recovery:{last.get('event_digest')}:{custody.get('status', 'unknown')}",
                        "subject_id": str(last.get("transition_id") or "resident-software-transition"),
                        "subject_kind": "software_generation_transition_recovery", "stage": "observation",
                        "disposition": "complete" if complete else "incomplete",
                        "evidence_strength": "reconstructed_software_transition_journal_posture",
                        "payload": {"journal_head": last.get("event_digest"), "recovery_posture": custody.get("status"),
                            "process_recovery_status": software_health.get("status"),
                            "transition_phase": last.get("phase"), "completed": complete, "replay_forbidden": True},
                        "observed_at": observed_at, "effect_claimed": False, "effect_proven": False})
                if isinstance(baseline, Mapping) and baseline.get("provenance_digest"):
                    records.append({"source_kind": "runtime_supervisor",
                        "source_id": f"resident_running_software:{baseline['provenance_digest']}",
                        "subject_id": str(baseline.get("process_instance_id") or "resident-process"),
                        "subject_kind": "observed_running_software_generation", "stage": "observation",
                        "disposition": "observed", "evidence_strength": "resident_launch_provenance",
                        "payload": {"running_software_generation_observed": baseline.get("represented_generation_digest"),
                            "software_generation": baseline.get("represented_generation_digest"),
                            "repository_commit": baseline.get("observed_commit_sha"),
                            "repository_tree": baseline.get("observed_tree_sha"),
                            "process_instance_id": baseline.get("process_instance_id"),
                            "provenance_digest": baseline.get("provenance_digest")},
                        "observed_at": baseline.get("startup_timestamp"), "effect_claimed": False, "effect_proven": False})
        return records

    def capture_causal_introspection(self, *, tick_id: str) -> dict[str, Any]:
        """Capture after all same-tick owner closures; never invoke a model or owner mutation."""
        if self._causal_introspection_runtime is None:
            return {"status": "disabled", "authority": False, "current_truth": False}
        snapshot = self._causal_introspection_runtime.capture(CaptureContext(
            tick_id=tick_id, capture_posture="unknown"))
        feedback = {"status": "degraded" if snapshot.completion_posture == "partial" else "ok",
            "snapshot_id": snapshot.snapshot_id, "snapshot_digest": snapshot.snapshot_digest,
            "generation": snapshot.generation, "projection_count": len(snapshot.projections),
            "conflict_count": len(snapshot.conflicts), "authority": False, "current_truth": False}
        self._feedback.setdefault("surfaces", {})["causal_introspection"] = feedback
        return feedback

    @property
    def current_world_state_snapshot(self) -> WorldStateSnapshot | None:
        """Return the exact validated in-memory snapshot; never reconstruct authority from JSON."""
        return self._world_state_snapshot

    def run_epistemic_development(self, *, tick_id: str) -> dict[str, Any]:
        """Run only after the cognition slot; its state is eligible next tick."""
        if self._epistemic_development_runtime is None:
            feedback = {"status": "disabled", "authority": False, "next_tick_only": True}
        elif self._world_state_snapshot is None or self._world_state_snapshot_built_for_tick != tick_id:
            feedback = {"status": "degraded", "reason": "same_tick_world_state_unavailable",
                        "authority": False, "next_tick_only": True}
        else:
            instant = datetime.fromisoformat(tick_id.replace("Z", "+00:00"))
            result = self._epistemic_development_runtime.process_snapshot(
                self._world_state_snapshot, tick=int(instant.timestamp()), recorded_at=instant.isoformat())
            feedback = asdict(result)
        self._feedback.setdefault("surfaces", {})["resident_epistemic_development"] = feedback
        self._refresh_feedback()
        return feedback

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
                prior_epistemic_state = None
                config = self._longitudinal_self_model_config
                if (config is not None and config.cognitive_consumption_enabled
                        and self._longitudinal_self_model_owner is not None):
                    prior_self_model = self._longitudinal_self_model_owner.cognitive_projection(
                        before_tick=tick_id, max_claims=config.max_projection_claims,
                        allowed_predicates=config.allowed_predicates)
                if self._epistemic_state_configuration_error is not None:
                    raise ValueError(self._epistemic_state_configuration_error)
                if (self._epistemic_state_owner is not None
                        and self._epistemic_state_config.get("cognitive_consumption_enabled") is True):
                    prior_epistemic_state = self._epistemic_state_owner.cognitive_projection(
                        max_states=int(self._epistemic_state_config["max_cognitive_projection_count"]))
                result = self._resident_developmental_owner.run_tick(
                    snapshot=self._world_state_snapshot, tick_id=tick_id,
                    prior_self_model=prior_self_model,
                    prior_epistemic_state=prior_epistemic_state)
                feedback = {**asdict(result), "snapshot_object_preserved": True,
                            "memory_posture": "historical_interpretation_not_current_truth",
                            "epistemic_composition": {
                                "status": ("composed" if prior_epistemic_state is not None else
                                    "configured-and-no-eligible-prior-state" if self._epistemic_state_owner is not None and self._epistemic_state_config.get("cognitive_consumption_enabled") else
                                    "configured-but-consumption-disabled" if self._epistemic_state_owner is not None else "disabled"),
                                "projection_present": prior_epistemic_state is not None,
                                "projection_id": prior_epistemic_state.projection_id if prior_epistemic_state else None,
                                "projection_digest": prior_epistemic_state.projection_digest if prior_epistemic_state else None,
                                "proposition_count": len(prior_epistemic_state.proposition_ids) if prior_epistemic_state else 0,
                                "cutoff_posture": "verified-custody-capture-before-inference",
                                "authority": False,
                            }}
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
        elif os.name != "posix":
            result = {"status": "blocked", "reason": "live_transition_processing_unsupported_platform",
                      "effect_performed": False, "interrupted": True}
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


def _load_resident_transition_custody(config_path: str, installation_handle: Any | None = None) -> tuple[Any, TransitionJournal]:
    """Resolve exact configured transition protocol and journal without composing an effector."""
    config = LiveTransitionConfig.load(Path(config_path))
    handle = installation_handle
    if handle is None:
        identity = InstallationIdentity.parse(config.installation_identity)
        registry = InstallationStateRegistry.system()
        handle = (registry.open_read_only(identity) if os.name == "nt"
                  else registry.open(identity))
    if handle.identity.value != config.installation_identity:
        raise TransitionError("transition_recovery_installation_binding_mismatch")
    protocol = load_verified_protocol(handle.root, protocol_id=config.protocol_id,
        protocol_digest=config.protocol_digest)
    if (protocol.value.get("installation_identity") != handle.identity.value
            or config.journal_identity != resident_transition_journal_identity(protocol)):
        raise TransitionError("transition_recovery_configuration_binding_mismatch")
    return protocol, TransitionJournal(handle.root / RESIDENT_TRANSITION_JOURNAL_CUSTODY)


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
        current_surface = "resident_epistemic_development"
        current_correlation_id = f"{tick_id}:resident_epistemic_development"
        develop_epistemics = getattr(runtime_surfaces, "run_epistemic_development", None)
        if callable(develop_epistemics):
            develop_epistemics(tick_id=tick_id)
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
        current_surface = "causal_introspection"
        current_correlation_id = f"{tick_id}:causal_introspection"
        capture_introspection = getattr(runtime_surfaces, "capture_causal_introspection", None)
        if callable(capture_introspection):
            capture_introspection(tick_id=tick_id)
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


def _compose_causal_introspection(
        runtime_surfaces: RuntimeMaintenanceSurfaces,
        *, resident_serving_controller: ResidentCognitiveModelServingController | None,
        config: IntrospectionConfig) -> CausalIntrospectionRuntime:
    """Bind only explicitly held live owners to read-only projection adapters."""
    registrations: list[ProviderRegistration] = []
    enabled = set(config.enabled_domains)
    if "runtime_supervision" in enabled:
        def inspect_runtime() -> dict[str, Any]:
            surfaces = runtime_surfaces.governance_feedback().get("surfaces", {})
            values = list(surfaces.values()) if isinstance(surfaces, dict) else []
            return {"surface_count": len(values),
                "degraded_surface_count": sum(1 for value in values
                    if isinstance(value, dict) and value.get("status") in {"blocked", "degraded"})}
        registrations.append(ProviderRegistration("sentientosd-runtime", "runtime_supervision",
            LiveOwnerMetadataProvider(provider_id="sentientosd-runtime-supervision-v1",
                owner_id="sentientosd-runtime", owner_kind="runtime_maintenance_surfaces",
                domain="runtime_supervision", inspect=inspect_runtime,
                observation_classes={"surface_count": "count", "degraded_surface_count": "count"})))
    epistemic_owner = runtime_surfaces._epistemic_state_owner
    if "persistent_epistemics" in enabled and epistemic_owner is not None:
        def inspect_epistemics() -> dict[str, Any]:
            counts = epistemic_owner.verify()
            return {"proposition_count": int(counts.get("propositions", 0)),
                "state_count": int(counts.get("states", 0)),
                "evidence_binding_count": int(counts.get("bindings", 0))}
        registrations.append(ProviderRegistration("persistent-epistemic-state", "persistent_epistemics",
            LiveOwnerMetadataProvider(provider_id="persistent-epistemic-state-v1",
                owner_id="persistent-epistemic-state", owner_kind="persistent_epistemic_state_owner",
                domain="persistent_epistemics", inspect=inspect_epistemics,
                observation_classes={"proposition_count": "count", "state_count": "count",
                    "evidence_binding_count": "count"})))
    resource_observer = runtime_surfaces._resource_observation_owner
    if "causal_resources" in enabled and resource_observer is not None:
        def inspect_causal_resources() -> dict[str, Any]:
            observation = resource_observer.observe()
            ledger_snapshot = observation.ledger.observation_snapshot()
            records = resource_consumption_world_state_records(
                ledger=observation.ledger,
                invocation_receipts=observation.invocation_receipts,
                source_identity={"installation_identity": observation.installation_identity,
                    "provisioning_id": observation.provisioning_id,
                    "manifest_digest": observation.manifest_digest})
            if len(records) != 1 or not isinstance(records[0].get("payload"), Mapping):
                raise ValueError("causal_resource_projection_shape_invalid")
            payload = records[0]["payload"]
            receipt_values = payload.get("consumption_receipts", ())
            latest_consumption_event_at = next((item.get("observed_at")
                for item in reversed(tuple(receipt_values))
                if isinstance(item, Mapping) and isinstance(item.get("observed_at"), str)), None)
            return {"installation_identity": observation.installation_identity,
                "provisioning_id": observation.provisioning_id,
                "manifest_digest": observation.manifest_digest,
                "ledger_digest": str(payload.get("ledger_digest", "")),
                "allocation_digests": tuple(str(item.get("allocation_digest", ""))
                    for item in ledger_snapshot["allocations"] if isinstance(item, Mapping)),
                "attempt_ids": tuple(str(item.get("attempt_id", ""))
                    for item in ledger_snapshot["attempts"][-64:] if isinstance(item, Mapping)),
                "retained_historical_consumption_receipt_digests": tuple(str(item.get("receipt_digest", ""))
                    for item in receipt_values[-64:] if isinstance(item, Mapping)),
                "retained_invocation_receipt_digests": tuple(str(item.get("receipt_digest", ""))
                    for item in observation.invocation_receipts[-64:]),
                "allocation_count": len(ledger_snapshot["allocations"]),
                "attempt_count": len(ledger_snapshot["attempts"]),
                "retained_historical_consumption_receipt_count": len(receipt_values),
                "latest_consumption_event_at": latest_consumption_event_at,
                "retained_invocation_receipt_count": len(observation.invocation_receipts),
                "incomplete_attempt_count": int(payload.get("incomplete_attempt_count",
                    len(payload.get("incomplete_attempt_ids", ())))),
                "lineage_finding_count": int(payload.get("lineage_finding_count",
                    len(payload.get("lineage_findings", ())))),
                "lineage_posture": str(payload.get("lineage_posture", "unknown")),
                "recovery_posture": str(payload.get("recovery_posture", "unknown")),
                "invocation_receipt_posture": observation.invocation_receipt_posture,
                "identity_retention_posture": ("complete" if len(ledger_snapshot["attempts"]) <= 64
                    and len(receipt_values) <= 64 and len(observation.invocation_receipts) <= 64
                    else "bounded_tail_incomplete"),
                "read_only": True, "effect_authority": False}
        registrations.append(ProviderRegistration("governed-resource-observer", "causal_resources",
            LiveOwnerMetadataProvider(provider_id="governed-resource-observer-v1",
                owner_id="governed-resource-observer", owner_kind="production_chat_resource_observation_owner",
                domain="causal_resources", inspect=inspect_causal_resources,
                observation_classes={"installation_identity": "identity", "provisioning_id": "identity",
                    "manifest_digest": "lineage", "ledger_digest": "lineage",
                    "allocation_digests": "resource_attribution", "attempt_ids": "resource_attribution",
                    "retained_historical_consumption_receipt_digests": "resource_attribution",
                    "retained_invocation_receipt_digests": "resource_attribution", "allocation_count": "count",
                    "attempt_count": "count", "retained_historical_consumption_receipt_count": "count",
                    "latest_consumption_event_at": "lifecycle",
                    "retained_invocation_receipt_count": "count", "incomplete_attempt_count": "count",
                    "lineage_finding_count": "count", "lineage_posture": "lineage",
                    "recovery_posture": "lifecycle", "invocation_receipt_posture": "health",
                    "identity_retention_posture": "lifecycle",
                    "read_only": "currentness", "effect_authority": "authority_evidence"})))
    longitudinal_owner = runtime_surfaces._longitudinal_self_model_owner
    if "longitudinal_self_model" in enabled and longitudinal_owner is not None:
        def inspect_longitudinal() -> dict[str, Any]:
            history = longitudinal_owner.history()
            latest = history[-1] if history else None
            return {"reconciliation_count": len(history),
                "latest_generation": latest.generation if latest is not None else 0,
                "latest_reconciliation_id": latest.reconciliation_id if latest is not None else None}
        registrations.append(ProviderRegistration("longitudinal-self-model", "longitudinal_self_model",
            LiveOwnerMetadataProvider(provider_id="longitudinal-self-model-v1",
                owner_id="longitudinal-self-model", owner_kind="longitudinal_self_model_owner",
                domain="longitudinal_self_model", inspect=inspect_longitudinal,
                observation_classes={"reconciliation_count": "count", "latest_generation": "lifecycle",
                    "latest_reconciliation_id": "identity"})))
    developmental_owner = runtime_surfaces._resident_developmental_owner
    if isinstance(developmental_owner, QuiescedDevelopmentalCognitionOwner):
        developmental_owner = developmental_owner._owner
    if "developmental_history" in enabled and developmental_owner is not None:
        def inspect_developmental_history() -> dict[str, Any]:
            records = developmental_owner.writeback.store.records()
            if not records:
                return {"record_count": 0, "latest_record_id": None,
                    "latest_record_digest": None, "latest_candidate_id": None,
                    "latest_model_id": None, "latest_model_artifact_digest": None,
                    "latest_snapshot_digest": None, "selected_fact_count": 0,
                    "verified_provenance_manifest_digests": []}
            def record_order(record: Any) -> tuple[float, str]:
                try:
                    created = datetime.fromisoformat(record.created_at.replace("Z", "+00:00"))
                    if created.tzinfo is None:
                        raise ValueError("naive")
                except (AttributeError, TypeError, ValueError) as exc:
                    raise ValueError("developmental_history_timestamp_invalid") from exc
                return created.astimezone(timezone.utc).timestamp(), record.record_id
            latest = max(records, key=record_order)
            candidate = latest.candidate
            selected_facts = candidate.get("selected_facts", ())
            provenance_digests: set[str] = set()
            for fact in selected_facts if isinstance(selected_facts, (list, tuple)) else ():
                if not isinstance(fact, Mapping) or not isinstance(fact.get("payload"), Mapping):
                    continue
                payload = fact["payload"]
                for key in ("proposed_successor_model_development_provenance",
                            "predecessor_model_development_provenance", "model_development_provenance"):
                    binding = payload.get(key)
                    if (isinstance(binding, Mapping)
                            and binding.get("posture") == "verified_source_bound_claim_manifest"
                            and isinstance(binding.get("provenance_manifest_digest"), str)):
                        provenance_digests.add(str(binding["provenance_manifest_digest"]))
            return {"record_count": len(records), "latest_record_id": latest.record_id,
                "latest_record_digest": latest.record_digest,
                "latest_candidate_id": candidate.get("candidate_id"),
                "latest_model_id": candidate.get("model_id"),
                "latest_model_artifact_digest": candidate.get("model_artifact_digest"),
                "latest_snapshot_digest": candidate.get("snapshot_digest"),
                "selected_fact_count": len(candidate.get("selected_fact_ids", ())),
                "verified_provenance_manifest_digests": sorted(provenance_digests)[:16]}
        registrations.append(ProviderRegistration("resident-developmental-history", "developmental_history",
            LiveOwnerMetadataProvider(provider_id="resident-developmental-history-v1",
                owner_id="resident-developmental-history", owner_kind="resident_developmental_history_store",
                domain="developmental_history", inspect=inspect_developmental_history,
                observation_classes={"record_count": "count", "latest_record_id": "identity",
                    "latest_record_digest": "lineage", "latest_candidate_id": "identity",
                    "latest_model_id": "identity", "latest_model_artifact_digest": "lineage",
                    "latest_snapshot_digest": "identity", "selected_fact_count": "count",
                    "verified_provenance_manifest_digests": "lineage"})))
    if "model_serving" in enabled and resident_serving_controller is not None:
        def inspect_serving() -> dict[str, Any]:
            health = resident_serving_controller.health()
            session = resident_serving_controller.current_session()
            return {"serving_status": str(health.get("status", "unknown")),
                "session_present": session is not None,
                "session_id": session.session_id if session is not None else None}
        registrations.append(ProviderRegistration("resident-cognitive-model-serving", "model_serving",
            LiveOwnerMetadataProvider(provider_id="resident-cognitive-model-serving-v1",
                owner_id="resident-cognitive-model-serving", owner_kind="resident_cognitive_model_serving_controller",
                domain="model_serving", inspect=inspect_serving,
                observation_classes={"serving_status": "health", "session_present": "currentness",
                    "session_id": "identity"})))
    transition_runtime = runtime_surfaces._resident_transition_runtime
    transition_controller = getattr(transition_runtime, "controller", None) if transition_runtime is not None else None
    transition_custody = runtime_surfaces._resident_transition_custody
    transition_protocol = (getattr(transition_controller, "protocol", None) if transition_controller is not None
                           else transition_custody[0] if transition_custody is not None else None)
    transition_journal = (getattr(transition_controller, "journal", None) if transition_controller is not None
                          else transition_custody[1] if transition_custody is not None else None)
    if "model_succession" in enabled and transition_protocol is not None and transition_journal is not None:
        def inspect_model_succession() -> dict[str, Any]:
            protocol = transition_protocol
            entries = transition_journal.entries()
            protocol_value = protocol.value
            if transition_controller is not None and transition_runtime is not None:
                health = transition_controller.health()
                status = transition_runtime.status()
            else:
                unresolved = next((entry for entry in reversed(entries)
                    if entry.get("status") in {"attempted", "effected", "failed", "interrupted"}), None)
                evidence = unresolved.get("evidence", {}) if isinstance(unresolved, Mapping) else {}
                health = {"status": "runtime_composition_blocked", "phase": "unknown",
                    "outstanding_stage": (evidence.get("attempted_stage") or evidence.get("failed_stage")
                        or evidence.get("interrupted_stage")), "replay_forbidden": unresolved is not None}
                serving = getattr(runtime_surfaces._resident_cognitive_invoker, "current_controller", None)
                session = serving.current_session() if serving is not None else None
                identity = session.binding.get("observed_loaded_model_identity") if session is not None else None
                status = {"resident_model_identity": dict(identity) if isinstance(identity, Mapping) else identity,
                    "resident_serving_session_id": session.session_id if session is not None else None}
            provenance = runtime_surfaces._resident_model_provenance_bindings(protocol_value)
            predecessor_provenance = provenance.get("predecessor_a", {})
            successor_provenance = provenance.get("successor_b", {})
            running_identity = status.get("resident_model_identity")
            running_provenance = next((value for role, value in provenance.items()
                if value.get("identity_binding_verified") is True
                and isinstance(protocol_value.get(role), Mapping)
                and isinstance(running_identity, Mapping)
                and dict(protocol_value[role]) == dict(running_identity)), {})
            return {"transition_id": protocol_value.get("transition_id"),
                "protocol_digest": protocol_value.get("protocol_digest"),
                "journal_head_digest": entries[-1].get("entry_digest") if entries else "GENESIS",
                "recovery_status": health.get("status"), "current_phase": health.get("phase"),
                "replay_forbidden": health.get("replay_forbidden", True),
                "predecessor_model_identity": protocol_value.get("predecessor_a"),
                "proposed_successor_model_identity": protocol_value.get("successor_b"),
                "predecessor_model_provenance_posture": predecessor_provenance.get("posture", "unknown"),
                "predecessor_model_provenance_manifest_digest": predecessor_provenance.get("provenance_manifest_digest"),
                "successor_model_provenance_posture": successor_provenance.get("posture", "unknown"),
                "successor_model_provenance_manifest_digest": successor_provenance.get("provenance_manifest_digest"),
                "running_model_provenance_posture": running_provenance.get("posture",
                    "unavailable_no_exact_running_identity_binding"),
                "running_model_provenance_manifest_digest": running_provenance.get("provenance_manifest_digest"),
                "running_model_identity_observed": status.get("resident_model_identity")}
        registrations.append(ProviderRegistration("resident-model-succession", "model_succession",
            LiveOwnerMetadataProvider(provider_id="resident-model-succession-v1",
                owner_id="resident-model-succession", owner_kind="resident_model_transition_controller",
                domain="model_succession", inspect=inspect_model_succession,
                observation_classes={"transition_id": "identity", "protocol_digest": "identity",
                    "journal_head_digest": "identity", "recovery_status": "health", "current_phase": "lifecycle",
                    "replay_forbidden": "currentness", "predecessor_model_identity": "identity",
                    "proposed_successor_model_identity": "identity",
                    "predecessor_model_provenance_posture": "lineage",
                    "predecessor_model_provenance_manifest_digest": "lineage",
                    "successor_model_provenance_posture": "lineage",
                    "successor_model_provenance_manifest_digest": "lineage",
                    "running_model_provenance_posture": "lineage",
                    "running_model_provenance_manifest_digest": "lineage",
                    "running_model_identity_observed": "identity"})))
    software_controller = runtime_surfaces._resident_software_transition_controller
    software_config = (software_controller.config if software_controller is not None
                       else runtime_surfaces._resident_software_transition_config)
    if "software_succession" in enabled and software_config is not None:
        def inspect_software_succession() -> dict[str, Any]:
            from sentientos.maintenance_resident_runtime_adoption import read_transition_events
            rows = read_transition_events(software_config, limit=1)
            health = (software_controller.health() if software_controller is not None else
                runtime_surfaces.governance_feedback().get("surfaces", {}).get("maintenance_resident_runtime_adoption", {}))
            baseline = getattr(software_controller, "_baseline", None) if software_controller is not None else None
            last = rows[-1] if rows else {}
            return {"transition_id": last.get("transition_id"),
                "journal_head_digest": last.get("event_digest", "GENESIS"),
                "transition_phase": last.get("phase", "none"),
                "recovery_status": health.get("status"),
                "predecessor_generation_digest": last.get("predecessor_generation_digest"),
                "successor_generation_digest": last.get("successor_generation_digest"),
                "running_software_generation_observed": (baseline.get("represented_generation_digest")
                    if isinstance(baseline, Mapping) else None)}
        registrations.append(ProviderRegistration("resident-software-succession", "software_succession",
            LiveOwnerMetadataProvider(provider_id="resident-software-succession-v1",
                owner_id="resident-software-succession", owner_kind="resident_software_generation_adoption_controller",
                domain="software_succession", inspect=inspect_software_succession,
                observation_classes={"transition_id": "identity", "journal_head_digest": "identity",
                    "transition_phase": "lifecycle", "recovery_status": "health",
                    "predecessor_generation_digest": "lineage",
                    "successor_generation_digest": "lineage",
                    "running_software_generation_observed": "lineage"})))
    runtime = CausalIntrospectionRuntime(config, registrations)
    runtime.reconstruct()  # fail closed on malformed or tampered predecessor custody
    return runtime


async def run_loop(shutdown_event: asyncio.Event, interval_seconds: int = 60) -> None:
    """Run the autonomous Codex maintenance loop."""

    # Resolve and gate an exact initial resident before boot ceremony output,
    # owner construction, or any maintenance-capable runtime initialization.
    adoption_path = os.environ.get("SENTIENTOS_MAINTENANCE_SCHEDULER_ADOPTION_CONFIG")
    wake_adoption_path = os.environ.get("SENTIENTOS_MAINTENANCE_WAKE_ADOPTION_CONFIG")
    successor_adoption_path = os.environ.get("SENTIENTOS_MAINTENANCE_SUCCESSOR_GENERATION_ADOPTION_CONFIG")
    auto_derivation_path = os.environ.get("SENTIENTOS_MAINTENANCE_AUTHORITY_CONTINUITY_AUTO_DERIVATION_CONFIG")
    resident_path = os.environ.get("SENTIENTOS_MAINTENANCE_RESIDENT_RUNTIME_ADOPTION_CONFIG")
    resident_config: dict[str, Any] | None = None
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
                initial_provenance = _prepare_resident_runtime_startup(resident_controller)
                await_initial_commissioning_gate(initial_provenance)
                resident_health = resident_controller.health()
        except Exception as exc:
            resident_health = {"status": "blocked", "reason": str(exc), "read_only": True}
    resident_blocked = bool(resident_path and resident_health["status"] == "blocked")
    if resident_blocked and os.environ.get(STARTUP_GATE_ENV):
        return

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
    resource_observation_owner = None
    resource_observation_configuration_status: dict[str, Any] = {
        "status": "disabled", "read_only": True, "effect_authority": False,
    }
    observation_installation = os.environ.get(RESOURCE_OBSERVATION_INSTALLATION_ENV)
    observation_provisioning = os.environ.get(RESOURCE_OBSERVATION_PROVISIONING_ENV)
    if observation_installation is not None or observation_provisioning is not None:
        if not observation_installation or not observation_provisioning:
            resource_observation_configuration_status = {
                "status": "invalid", "reason_code": "resource_observation_configuration_incomplete",
                "read_only": True, "effect_authority": False,
            }
        else:
            try:
                handle = InstallationStateRegistry.system().open_read_only(
                    InstallationIdentity.parse(observation_installation))
                resource_observation_owner = ProductionChatResourceObservationOwner(
                    handle, observation_provisioning)
                resource_observation_configuration_status = {
                    "status": "degraded", "reason_code": "source_not_yet_observed",
                    "installation_identity": handle.identity.value,
                    "provisioning_id": observation_provisioning,
                    "read_only": True, "effect_authority": False,
                }
            except InstallationStateError as exc:
                resource_observation_configuration_status = {
                    "status": "missing" if exc.code == "installation_state_root_missing" else "invalid",
                    "reason_code": exc.code,
                    "read_only": True, "effect_authority": False,
                }
            except Exception as exc:
                resource_observation_configuration_status = {
                    "status": "invalid", "reason_code": type(exc).__name__,
                    "read_only": True, "effect_authority": False,
                }
    resident_serving_controller = None
    resident_serving_slot = None
    resident_serving_config = None
    resident_serving_error = None
    resident_serving_path = os.environ.get(RESIDENT_SERVING_CONFIG_ENV)
    resident_transition_live_path = os.environ.get(RESIDENT_COGNITIVE_TRANSITION_LIVE_CONFIG_ENV)
    consequence_store, consequence_result_ids, consequence_chain_ids, model_replacement_store, model_replacement_run_refs, proposal_review_records, proposal_review_log_path, proposal_review_receipt_ids, fulfillment_records, fulfillment_log_path, fulfillment_receipt_ids, consequence_projection_status = (
        _load_embodied_consequence_projection(os.environ.get(EMBODIED_CONSEQUENCE_PROJECTION_CONFIG_ENV)))
    consequence_projection_kwargs = {
        "embodied_consequence_store": consequence_store,
        "embodied_consequence_result_ids": consequence_result_ids,
        "embodied_consequence_chain_ids": consequence_chain_ids,
        "model_replacement_artifact_store": model_replacement_store,
        "model_replacement_run_refs": model_replacement_run_refs,
        "embodied_proposal_review_records": proposal_review_records,
        "embodied_proposal_review_log_path": proposal_review_log_path,
        "embodied_proposal_review_receipt_ids": proposal_review_receipt_ids,
        "embodied_fulfillment_records": fulfillment_records,
        "embodied_fulfillment_log_path": fulfillment_log_path,
        "embodied_fulfillment_receipt_ids": fulfillment_receipt_ids,
        "embodied_consequence_projection_status": consequence_projection_status,
    }
    post_adoption_owner, post_adoption_campaign_ids, post_adoption_projection_status = (
        _load_post_adoption_attribution_projection(
            os.environ.get(POST_ADOPTION_ATTRIBUTION_PROJECTION_CONFIG_ENV)))
    post_adoption_projection_kwargs = {
        "post_adoption_attribution_owner": post_adoption_owner,
        "post_adoption_attribution_campaign_ids": post_adoption_campaign_ids,
        "post_adoption_attribution_projection_status": post_adoption_projection_status,
    }
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
        resource_observation_owner=resource_observation_owner,
        resource_observation_configuration_status=resource_observation_configuration_status,
        **consequence_projection_kwargs,
        **post_adoption_projection_kwargs,
    )
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
    if not resident_blocked and resident_serving_config is not None and resident_serving_config.enabled:
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
            candidate_surfaces: RuntimeMaintenanceSurfaces | None = None
            candidate_surfaces = RuntimeMaintenanceSurfaces(
                repo_root, improvement_evidence_sources=resolve_improvement_evidence_sources(repo_root),
                governed_local_invoker=governed_invoker, genesis_advice_source=genesis_advice,
                resource_observation_owner=resource_observation_owner,
                resource_observation_configuration_status=resource_observation_configuration_status,
                **consequence_projection_kwargs,
                **post_adoption_projection_kwargs,
                epistemic_state_owner=runtime_surfaces._epistemic_state_owner,
                epistemic_state_config=runtime_surfaces._epistemic_state_config,
                epistemic_state_configuration_error=runtime_surfaces._epistemic_state_configuration_error,
                epistemic_development_runtime=runtime_surfaces._epistemic_development_runtime,
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
                    try:
                        candidate_surfaces._resident_transition_custody = _load_resident_transition_custody(
                            resident_transition_live_path, handle)
                    except Exception as recovery_exc:
                        candidate_surfaces._resident_transition_custody_error = type(recovery_exc).__name__
                if (resident_transition_runtime is None
                        and candidate_surfaces._resident_transition_custody is None
                        and candidate_surfaces._resident_transition_custody_error is None):
                    try:
                        candidate_surfaces._resident_transition_custody = _load_resident_transition_custody(
                            resident_transition_live_path, handle)
                    except Exception as recovery_exc:
                        candidate_surfaces._resident_transition_custody_error = type(recovery_exc).__name__
            if resident_transition_runtime is not None:
                runtime_surfaces = RuntimeMaintenanceSurfaces(
                    repo_root, improvement_evidence_sources=resolve_improvement_evidence_sources(repo_root),
                    governed_local_invoker=governed_invoker, genesis_advice_source=genesis_advice,
                    resource_observation_owner=resource_observation_owner,
                    resource_observation_configuration_status=resource_observation_configuration_status,
                    **consequence_projection_kwargs,
                    **post_adoption_projection_kwargs,
                    epistemic_state_owner=candidate_surfaces._epistemic_state_owner,
                    epistemic_state_config=candidate_surfaces._epistemic_state_config,
                    epistemic_state_configuration_error=candidate_surfaces._epistemic_state_configuration_error,
                    epistemic_development_runtime=candidate_surfaces._epistemic_development_runtime,
                    resident_developmental_owner=_resident_developmental_owner(candidate_surfaces),
                    resident_cognitive_invoker=resident_serving_slot,
                    resident_cognition_gate=resident_cognition_gate,
                    resident_transition_runtime=resident_transition_runtime)
            else:
                runtime_surfaces = candidate_surfaces
            if resident_transition_runtime is not None:
                transition_controller = resident_transition_runtime.controller
                runtime_surfaces._resident_transition_custody = (
                    transition_controller.protocol, transition_controller.journal)
            runtime_surfaces._resident_transition_configuration_error = resident_transition_error
        except Exception as exc:
            resident_serving_error = f"{type(exc).__name__}:{exc}"
            if resident_serving_controller is not None:
                resident_serving_controller.close()
                resident_serving_controller = None
            # Enabled mode is deliberately unavailable; never reconstruct with legacy invoker.
            runtime_surfaces = RuntimeMaintenanceSurfaces(
                repo_root, improvement_evidence_sources=resolve_improvement_evidence_sources(repo_root),
                governed_local_invoker=None, genesis_advice_source=genesis_advice,
                resource_observation_owner=resource_observation_owner,
                resource_observation_configuration_status=resource_observation_configuration_status,
                **consequence_projection_kwargs,
                **post_adoption_projection_kwargs,
                epistemic_state_owner=runtime_surfaces._epistemic_state_owner,
                epistemic_state_config=runtime_surfaces._epistemic_state_config,
                epistemic_state_configuration_error=runtime_surfaces._epistemic_state_configuration_error,
                epistemic_development_runtime=runtime_surfaces._epistemic_development_runtime)
            if candidate_surfaces is not None:
                runtime_surfaces._resident_transition_custody = candidate_surfaces._resident_transition_custody
                runtime_surfaces._resident_transition_custody_error = candidate_surfaces._resident_transition_custody_error
    if (resident_transition_live_path
            and runtime_surfaces._resident_transition_custody is None
            and runtime_surfaces._resident_transition_custody_error is None):
        try:
            runtime_surfaces._resident_transition_custody = _load_resident_transition_custody(
                resident_transition_live_path)
        except Exception as recovery_exc:
            runtime_surfaces._resident_transition_custody_error = type(recovery_exc).__name__
    if resident_serving_error is not None:
        runtime_surfaces._resident_developmental_configuration_error = resident_serving_error
    if resident_transition_live_path and resident_serving_controller is None:
        runtime_surfaces._resident_transition_configuration_error = (
            runtime_surfaces._resident_transition_configuration_error
            or "hardened_resident_serving_required")
    # Explicit owner injection: World-State reads the already configured
    # software-transition journal and the startup provenance captured by this
    # controller. It does not discover generation custody from the filesystem.
    runtime_surfaces._resident_software_transition_controller = resident_controller
    runtime_surfaces._resident_software_transition_config = resident_config
    try:
        introspection_config = load_causal_introspection_config()
        if introspection_config is not None and introspection_config.enabled:
            runtime_surfaces._causal_introspection_runtime = _compose_causal_introspection(
                runtime_surfaces, resident_serving_controller=resident_serving_controller,
                config=introspection_config)
        elif introspection_config is not None:
            runtime_surfaces._feedback["surfaces"]["causal_introspection"] = {
                "status": "disabled", "authority": False, "current_truth": False}
    except Exception as exc:
        runtime_surfaces._causal_introspection_runtime = None
        runtime_surfaces._feedback["surfaces"]["causal_introspection"] = {
            "status": "blocked", "reason": f"{type(exc).__name__}:{exc}",
            "authority": False, "current_truth": False}
    LOGGER.info("SentientOS daemon initialised with %s", model.describe())

    try:
        while not shutdown_event.is_set():
            if resident_blocked:
                # Preserve a verified read-only recovery snapshot before this
                # image stops. No cognition, transition retry, or effector runs.
                with suppress(Exception):
                    runtime_surfaces.build_world_state_board(
                        tick_id=datetime.now(timezone.utc).isoformat())
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
