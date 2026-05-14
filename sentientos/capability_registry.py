"""Metadata-only capability registry for SentientOS host embodiment.

The registry describes current and deferred capability surfaces. It never probes
hardware, opens network connections, assembles prompts, invokes providers, or
changes runtime authority.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Mapping, Sequence

CAPABILITY_CATEGORIES = frozenset(
    {
        "install_bootstrap",
        "first_boot_configuration",
        "local_model_chat",
        "memory_context_reflection",
        "perception_audio",
        "perception_screen",
        "perception_vision",
        "embodiment_fusion",
        "embodiment_governance",
        "avatar_state",
        "gui_host_interaction",
        "browser_host_interaction",
        "hardware_driver_awareness",
        "hardware_sensor_inventory",
        "host_resource_telemetry",
        "control_plane_admission",
        "audit_immutability",
        "self_amendment",
        "federation_evidence",
        "docs_proof",
    }
)
CAPABILITY_STATUSES = frozenset({"implemented", "partial", "scaffolded", "deferred", "blocked", "unknown"})
AUTHORITY_LEVELS = frozenset(
    {
        "none",
        "observation",
        "proposal_only",
        "gated_host_interaction",
        "privileged_host_action",
        "federation_evidence",
        "self_amendment",
    }
)
_SAFE_PROVIDER_NETWORK_STATUSES = frozenset({"blocked", "deferred"})

# Backward-compatible session-scoped disablement registry used by diagnostics.
# This legacy API is intentionally local in-memory metadata; it does not grant,
# execute, or expand host authority.
_DISABLED_CAPABILITIES: dict[str, str] = {}


def disable_capability(capability: str, *, reason: str) -> bool:
    if capability in _DISABLED_CAPABILITIES:
        return False
    _DISABLED_CAPABILITIES[capability] = reason
    return True


def is_capability_disabled(capability: str) -> bool:
    return capability in _DISABLED_CAPABILITIES


def disabled_capability_reason(capability: str) -> str | None:
    return _DISABLED_CAPABILITIES.get(capability)


def disabled_capabilities() -> Mapping[str, str]:
    return dict(_DISABLED_CAPABILITIES)


def reset_capability_registry() -> None:
    _DISABLED_CAPABILITIES.clear()


def capability_snapshot_hash() -> str:
    payload = json.dumps(
        {"disabled": _DISABLED_CAPABILITIES},
        separators=(",", ":"),
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CapabilityRecord:
    capability_id: str
    category: str
    status: str
    authority_level: str = "none"
    source_paths: tuple[str, ...] = ()
    proof_tests: tuple[str, ...] = ()
    proof_commands: tuple[str, ...] = ()
    implemented_surfaces: tuple[str, ...] = ()
    deferred_surfaces: tuple[str, ...] = ()
    forbidden_implications: tuple[str, ...] = ()
    requires_control_plane_admission: bool = False
    requires_operator_approval: bool = False
    requires_panic_stop: bool = False
    requires_audit_receipt: bool = False
    requires_rollback_receipt: bool = False
    network_required: bool = False
    provider_required: bool = False
    prompt_assembly_required: bool = False
    host_actuation_performed: bool = False
    metadata_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CapabilityRegistry:
    registry_id: str
    schema_version: str = "host-embodiment-substrate-phase1.v1"
    records: tuple[CapabilityRecord, ...] = ()
    metadata_only: bool = True
    no_runtime_authority_expansion: bool = True

    def by_id(self) -> dict[str, CapabilityRecord]:
        return {record.capability_id: record for record in self.records}

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CapabilityValidationResult:
    ok: bool
    findings: tuple[str, ...] = ()


def _tuple(value: Sequence[str] | None) -> tuple[str, ...]:
    return tuple(str(item) for item in (value or ()))


def _record(
    capability_id: str,
    category: str,
    status: str,
    authority_level: str = "none",
    *,
    source_paths: Sequence[str] = (),
    proof_tests: Sequence[str] = (),
    proof_commands: Sequence[str] = (),
    implemented_surfaces: Sequence[str] = (),
    deferred_surfaces: Sequence[str] = (),
    forbidden_implications: Sequence[str] = (),
    requires_control_plane_admission: bool = False,
    requires_operator_approval: bool = False,
    requires_panic_stop: bool = False,
    requires_audit_receipt: bool = False,
    requires_rollback_receipt: bool = False,
    network_required: bool = False,
    provider_required: bool = False,
    prompt_assembly_required: bool = False,
    host_actuation_performed: bool = False,
) -> CapabilityRecord:
    return CapabilityRecord(
        capability_id=capability_id,
        category=category,
        status=status,
        authority_level=authority_level,
        source_paths=_tuple(source_paths),
        proof_tests=_tuple(proof_tests),
        proof_commands=_tuple(proof_commands),
        implemented_surfaces=_tuple(implemented_surfaces),
        deferred_surfaces=_tuple(deferred_surfaces),
        forbidden_implications=_tuple(forbidden_implications),
        requires_control_plane_admission=requires_control_plane_admission,
        requires_operator_approval=requires_operator_approval,
        requires_panic_stop=requires_panic_stop,
        requires_audit_receipt=requires_audit_receipt,
        requires_rollback_receipt=requires_rollback_receipt,
        network_required=network_required,
        provider_required=provider_required,
        prompt_assembly_required=prompt_assembly_required,
        host_actuation_performed=host_actuation_performed,
        metadata_only=True,
    )


def build_default_capability_registry() -> CapabilityRegistry:
    """Return the deterministic Phase 1 capability map."""

    records = (
        _record("install_bootstrap", "install_bootstrap", "implemented", "observation", source_paths=("installer/setup_installer.py", "installer/dry_run.py", "scripts/package_launcher.py"), implemented_surfaces=("offline/dry-run setup metadata",), forbidden_implications=("package installation without operator action",)),
        _record("first_boot_configuration", "first_boot_configuration", "implemented", "observation", source_paths=("sentientos/first_boot.py",), proof_tests=("tests/test_first_boot.py",), implemented_surfaces=("operator approvals and first-boot ledger rows",)),
        _record("local_model_chat", "local_model_chat", "partial", "observation", source_paths=("sentientos/local_model.py", "sentientos/chat_service.py", "model_bridge.py"), proof_tests=("tests/test_local_model.py", "tests/test_chat_service_lazy_loading.py"), implemented_surfaces=("local-file/echo/null model paths",), deferred_surfaces=("provider invocation",), forbidden_implications=("runtime provider authority",)),
        _record("memory_context_reflection", "memory_context_reflection", "implemented", "observation", source_paths=("memory_manager.py", "memory_governor.py", "sentientos/memory/", "sentientos/meta/reflection_loop.py"), implemented_surfaces=("memory/reflection storage and pressure summaries",), forbidden_implications=("host mutation",)),
        _record("perception_audio", "perception_audio", "partial", "observation", source_paths=("mic_bridge.py", "tts_bridge.py", "tts_service.py"), implemented_surfaces=("audio ingress/egress adapters",), forbidden_implications=("privileged device control",)),
        _record("perception_screen", "perception_screen", "partial", "observation", source_paths=("ocr_pipeline.py", "ocr_utils.py", "scripts/perception/screen_adapter.py"), implemented_surfaces=("screen OCR and normalized screen observations",), forbidden_implications=("desktop control",)),
        _record("perception_vision", "perception_vision", "partial", "observation", source_paths=("sentientos/perception_api.py",), implemented_surfaces=("vision/perception telemetry APIs",), forbidden_implications=("camera authority expansion",)),
        _record("embodiment_fusion", "embodiment_fusion", "implemented", "proposal_only", source_paths=("sentientos/embodiment_fusion.py", "sentientos/embodiment_ingress.py", "sentientos/embodiment_proposals.py"), implemented_surfaces=("event fusion, ingress receipts, proposal handoffs",), forbidden_implications=("proposal is not effect",)),
        _record("embodiment_governance", "embodiment_governance", "implemented", "proposal_only", source_paths=("sentientos/embodiment_governance_bridge.py", "sentientos/embodiment_fulfillment.py"), implemented_surfaces=("governance bridge and non-authoritative fulfillment candidates",), forbidden_implications=("fulfillment candidate is not side-effect proof",)),
        _record("avatar_state", "avatar_state", "implemented", "observation", source_paths=("avatar_state.py", "sentientos/embodiment/avatar_state.py"), implemented_surfaces=("avatar state metadata",)),
        _record("gui_host_interaction", "gui_host_interaction", "implemented", "gated_host_interaction", source_paths=("sentientos/actuators/gui_control.py", "ui_controller.py", "input_controller.py", "sentientos/innervation.py"), implemented_surfaces=("permission/panic/policy gated UI shims",), forbidden_implications=("blanket host control",), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True),
        _record("browser_host_interaction", "browser_host_interaction", "implemented", "gated_host_interaction", source_paths=("sentientos/agents/browser_automator.py", "sentientos/oracle_relay.py", "browser_voice.py"), implemented_surfaces=("enable flags, allowlists, budgets, audit logging",), forbidden_implications=("network egress authority beyond configured browser automation",), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True),
        _record("hardware_driver_awareness", "hardware_driver_awareness", "partial", "proposal_only", source_paths=("sentientos/daemons/driver_manager.py", "config/hardware_profile.json"), proof_tests=("tests/test_first_boot.py",), implemented_surfaces=("device reports, driver recommendations, veil-pending requests",), deferred_surfaces=("driver installation",), forbidden_implications=("package or driver install",), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("hardware_sensor_inventory", "hardware_sensor_inventory", "scaffolded", "observation", source_paths=("sentientos/host_inventory.py",), proof_tests=("tests/test_host_inventory.py",), proof_commands=("python -m scripts.run_tests -q tests/test_host_inventory.py",), implemented_surfaces=("metadata manifest from supplied observations",), deferred_surfaces=("privileged sensor probing", "fan/PWM control"), forbidden_implications=("inventory grants authority")),
        _record("host_resource_telemetry", "host_resource_telemetry", "scaffolded", "proposal_only", source_paths=("sentientos/host_resource_governor.py",), proof_tests=("tests/test_host_resource_governor.py",), proof_commands=("python -m scripts.run_tests -q tests/test_host_resource_governor.py",), implemented_surfaces=("read-only pressure classification from supplied telemetry",), deferred_surfaces=("cooling action", "process killing", "service restart", "power profile changes"), forbidden_implications=("telemetry is actuation")),
        _record("direct_fan_pwm_thermal_control", "host_resource_telemetry", "blocked", "none", source_paths=("sentientos/host_resource_governor.py", "sentientos/host_inventory.py"), proof_tests=("tests/test_host_resource_governor.py", "tests/test_host_inventory.py"), deferred_surfaces=("fan/PWM writes", "direct thermal actuation"), forbidden_implications=("fan/PWM/thermal control is implemented"), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("blanket_hardware_control", "hardware_driver_awareness", "blocked", "none", deferred_surfaces=("stem-to-stern host actuation",), forbidden_implications=("blanket hardware control exists"), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("control_plane_admission", "control_plane_admission", "implemented", "proposal_only", source_paths=("sentientos/control_plane_kernel.py", "control_plane/", "sentientos/runtime_governor.py"), proof_tests=("tests/test_control_plane_kernel.py", "tests/test_sentientosd_runtime_closure.py"), implemented_surfaces=("admission receipts and runtime gating",), forbidden_implications=("admission alone performs effects",)),
        _record("audit_immutability", "audit_immutability", "implemented", "observation", source_paths=("scripts/audit_immutability_verifier.py", "scripts/verify_audits.py", "vow/immutable_manifest.json"), proof_commands=("python scripts/verify_audits.py --strict", "python scripts/audit_immutability_verifier.py --manifest vow/immutable_manifest.json"), implemented_surfaces=("audit verification",)),
        _record("self_amendment", "self_amendment", "partial", "self_amendment", source_paths=("sentientos/autonomy/runtime.py", "sentientos/autonomy/rehearsal.py"), implemented_surfaces=("rehearsal/governed composition surfaces",), deferred_surfaces=("unapproved self-modification",), forbidden_implications=("runtime authority expansion",), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("federation_evidence_custody", "federation_evidence", "implemented", "federation_evidence", source_paths=("sentientos/federation/",), proof_tests=("tests/test_federated_improvement_candidate.py", "tests/test_federated_improvement_intake_receipt.py", "tests/test_federated_improvement_custody_runway.py"), implemented_surfaces=("federated evidence/receipt custody",), deferred_surfaces=("transport", "sync", "adoption", "merge", "apply", "install", "execution"), forbidden_implications=("federation receipts transport or adopt changes")),
        _record("federation_transport_sync_adoption", "federation_evidence", "blocked", "none", source_paths=("sentientos/federation/",), deferred_surfaces=("transport", "sync", "adoption", "merge", "apply", "install", "remote execution"), forbidden_implications=("evidence custody is adoption")),
        _record("provider_invocation", "local_model_chat", "blocked", "none", source_paths=("docs/architecture/reviewer_release_readiness_index.md",), proof_commands=("python scripts/verify_context_hygiene_prompt_boundaries.py",), deferred_surfaces=("provider invocation", "provider SDK", "network egress", "prompt export"), forbidden_implications=("provider runtime authority exists")),
        _record("docs_proof", "docs_proof", "implemented", "observation", source_paths=("docs/architecture/host_embodiment_substrate_phase1.md", "docs/architecture/sentientos_trajectory_and_missing_organs.md", "docs/architecture/public_technical_overview.md", "docs/architecture/reviewer_release_readiness_index.md"), proof_tests=("tests/test_reviewer_release_readiness_index.py",), proof_commands=("python scripts/build_docs.py --check-deps", "python scripts/build_docs.py"), implemented_surfaces=("public proof maps and docs build",)),
    )
    return CapabilityRegistry(registry_id="sentientos-host-embodiment-phase1", records=records)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def capability_registry_digest(registry: CapabilityRegistry) -> str:
    return hashlib.sha256(_canonical_json(registry.to_dict()).encode("utf-8")).hexdigest()


def summarize_capability_registry(registry: CapabilityRegistry) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    by_authority: dict[str, int] = {}
    for record in registry.records:
        by_status[record.status] = by_status.get(record.status, 0) + 1
        by_authority[record.authority_level] = by_authority.get(record.authority_level, 0) + 1
    return {
        "registry_id": registry.registry_id,
        "schema_version": registry.schema_version,
        "record_count": len(registry.records),
        "records_by_status": dict(sorted(by_status.items())),
        "records_by_authority_level": dict(sorted(by_authority.items())),
        "capability_ids": tuple(sorted(record.capability_id for record in registry.records)),
        "metadata_only": registry.metadata_only,
        "no_runtime_authority_expansion": registry.no_runtime_authority_expansion,
        "digest": capability_registry_digest(registry),
    }


def validate_capability_registry(registry: CapabilityRegistry) -> CapabilityValidationResult:
    findings: list[str] = []
    if not registry.registry_id:
        findings.append("missing_registry_id")
    if not registry.metadata_only:
        findings.append("registry_not_metadata_only")
    seen: set[str] = set()
    for record in registry.records:
        prefix = f"capability:{record.capability_id or '<missing>'}:"
        if not record.capability_id:
            findings.append(prefix + "missing_id")
        if record.capability_id in seen:
            findings.append(prefix + "duplicate_id")
        seen.add(record.capability_id)
        if not record.category:
            findings.append(prefix + "missing_category")
        elif record.category not in CAPABILITY_CATEGORIES:
            findings.append(prefix + "unknown_category")
        if not record.status:
            findings.append(prefix + "missing_status")
        elif record.status not in CAPABILITY_STATUSES:
            findings.append(prefix + "unknown_status")
        if record.authority_level not in AUTHORITY_LEVELS:
            findings.append(prefix + "unknown_authority_level")
        if not record.metadata_only:
            findings.append(prefix + "not_metadata_only")
        forbidden_text = " ".join(record.forbidden_implications).lower()
        if record.status == "implemented" and forbidden_text and any(term in forbidden_text for term in ("implemented", "exists", "authority")) and record.host_actuation_performed:
            findings.append(prefix + "implemented_claims_forbidden_implication")
        if (record.provider_required or record.network_required or record.prompt_assembly_required) and record.status not in _SAFE_PROVIDER_NETWORK_STATUSES:
            findings.append(prefix + "provider_network_prompt_authority_not_blocked_or_deferred")
        record_text = _canonical_json(record.to_dict()).lower()
        fan_pwm = "fan" in record_text or "pwm" in record_text or "thermal" in record_text
        if record.status == "implemented" and fan_pwm and record.host_actuation_performed:
            if not record.source_paths or not record.proof_tests:
                findings.append(prefix + "implemented_fan_pwm_actuation_missing_source_or_proof")
        if record.host_actuation_performed:
            if record.authority_level != "privileged_host_action":
                findings.append(prefix + "host_actuation_without_privileged_authority_level")
            required = (
                record.requires_control_plane_admission,
                record.requires_operator_approval,
                record.requires_panic_stop,
                record.requires_audit_receipt,
                record.requires_rollback_receipt,
            )
            if not all(required):
                findings.append(prefix + "host_actuation_missing_admission_operator_panic_audit_or_rollback")
        if record.category == "federation_evidence" and record.status == "implemented":
            implemented_text = " ".join(record.implemented_surfaces).lower()
            if any(term in implemented_text for term in ("transport", "sync", "adoption", "adopt", "merge", "apply", "install", "execution", "execute")):
                findings.append(prefix + "federation_evidence_claims_transport_or_adoption")
    return CapabilityValidationResult(ok=not findings, findings=tuple(findings))


def replace_capability_record(registry: CapabilityRegistry, capability_id: str, **changes: Any) -> CapabilityRegistry:
    """Test helper for deterministic mutations without changing metadata behavior."""

    records = tuple(replace(record, **changes) if record.capability_id == capability_id else record for record in registry.records)
    return replace(registry, records=records)
