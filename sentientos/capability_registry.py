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
        "host_resource_policy",
        "host_resource_proposal_receipts",
        "privilege_broker",
        "control_plane_admission",
        "actuation_fulfillment",
        "execution_proof",
        "authorization_review",
        "controlled_authorization",
        "host_embodiment_trace",
        "reviewer_proof_bundle",
        "host_actuation_safety",
        "live_grant_readiness",
        "local_authorization_grant",
        "fulfillment_authorization",
        "fulfillment_executor_contract",
        "dry_run_execution_harness",
        "dry_run_audit_closure",
        "real_effect_admission",
        "local_diagnostic_effect",
        "local_effect_transaction_ledger",
        "workspace_file_effect",
        "workspace_file_transaction_ledger",
        "host_steward_boundary",
        "delegated_runner_boundary",
        "runtime_supervision",
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
        "eligibility_only",
        "rehearsal_only",
        "proof_only",
        "readiness_only",
        "review_only",
        "schema_only",
        "contract_only",
        "ledger_only",
        "demo_proof_only",
        "metadata_proof_only",
        "allowlist_only",
        "declaration_only",
        "policy_only",
        "scope_only",
        "safety_gate_only",
        "packet_only",
        "preflight_only",
        "denial_deferral_only",
        "local_authorization_record_only",
        "authorization_ledger_only",
        "revocation_record_only",
        "expiry_evaluation_only",
        "verification_only",
        "request_only",
        "assessment_only",
        "consumption_receipt_only",
        "denial_receipt_only",
        "precondition_only",
        "plan_only",
        "readiness_receipt_only",
        "simulated_only",
        "dry_run_receipt_only",
        "dry_run_verification_only",
        "dry_run_postcondition_only",
        "dry_run_rollback_only",
        "dry_run_audit_only",
        "dry_run_closure_only",
        "admission_planning_only",
        "local_diagnostic_effect_only",
        "real_effect_receipt_only",
        "real_postcondition_check_only",
        "production_audit_only",
        "exact_artifact_rollback_only",
        "exact_artifact_postcondition_only",
        "exact_artifact_rollback_audit_only",
        "bounded_in_process_runner",
        "builtin_runner_action_only",
        "bounded-orchestrator",
        "bounded diagnostic write orchestration",
        "bounded write/exact-rollback orchestration",
        "explicit ledger build",
        "runner_execution_receipt_only",
        "local_effect_transaction_ledger_only",
        "local_effect_lifecycle_report_only",
        "metadata_ledger_only",
        "report_only",
        "explicit-local-artifact-only",
        "explicit_local_artifact_only",
        "authority_profile_only",
        "boundary_profile_only",
        "containment_profile_only",
        "grant_scaffold_only",
        "violation_receipt_only",
        "candidate_only",
        "plan_scaffold_only",
        "block_receipt_only",
        "telemetry_readiness_only",
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
    schema_version: str = "host-embodiment-execution-proof-wing.v1"
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
    """Return the deterministic host embodiment capability map."""

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
        _record("host_resource_telemetry", "host_resource_telemetry", "partial", "proposal_only", source_paths=("sentientos/host_resource_governor.py",), proof_tests=("tests/test_host_resource_governor.py",), proof_commands=("python -m scripts.run_tests -q tests/test_host_resource_governor.py",), implemented_surfaces=("read-only pressure classification from supplied telemetry",), deferred_surfaces=("cooling action", "process killing", "service restart", "power profile changes"), forbidden_implications=("telemetry is actuation")),
        _record("host_resource_policy", "host_resource_policy", "implemented", "proposal_only", source_paths=("sentientos/host_resource_policy.py", "sentientos/host_resource_governor.py"), proof_tests=("tests/test_host_resource_policy.py",), proof_commands=("python -m scripts.run_tests -q tests/test_host_resource_policy.py",), implemented_surfaces=("deterministic metadata-only policy decisions from pressure reports",), deferred_surfaces=("Privilege Broker authorization", "Actuation Fulfillment Layer effects", "cooling action", "service restart", "power profile changes"), forbidden_implications=("policy decision is authorization", "pressure report executes host action"), requires_control_plane_admission=True, requires_operator_approval=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("host_resource_proposal_receipts", "host_resource_proposal_receipts", "implemented", "proposal_only", source_paths=("sentientos/host_resource_policy.py",), proof_tests=("tests/test_host_resource_policy.py",), proof_commands=("python -m scripts.run_tests -q tests/test_host_resource_policy.py",), implemented_surfaces=("deterministic proposal-only resource policy receipts",), deferred_surfaces=("Privilege Broker", "Actuation Fulfillment Layer", "host mutation fulfillment", "fan/PWM writes", "thermal actuation"), forbidden_implications=("proposal receipts are effects", "proposal receipt grants privileged host action"), requires_control_plane_admission=True, requires_operator_approval=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("direct_fan_pwm_thermal_control", "host_resource_telemetry", "blocked", "none", source_paths=("sentientos/host_resource_governor.py", "sentientos/host_inventory.py", "sentientos/host_resource_policy.py"), proof_tests=("tests/test_host_resource_governor.py", "tests/test_host_inventory.py", "tests/test_host_resource_policy.py"), deferred_surfaces=("fan/PWM writes", "direct thermal actuation"), forbidden_implications=("fan/PWM/thermal control is implemented"), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("blanket_hardware_control", "hardware_driver_awareness", "blocked", "none", deferred_surfaces=("stem-to-stern host actuation",), forbidden_implications=("blanket hardware control exists"), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("control_plane_admission", "control_plane_admission", "implemented", "proposal_only", source_paths=("sentientos/control_plane_kernel.py", "control_plane/", "sentientos/runtime_governor.py"), proof_tests=("tests/test_control_plane_kernel.py", "tests/test_sentientosd_runtime_closure.py"), implemented_surfaces=("admission receipts and runtime gating",), forbidden_implications=("admission alone performs effects",)),
        _record("privilege_broker", "privilege_broker", "implemented", "eligibility_only", source_paths=("sentientos/privilege_broker.py", "sentientos/host_resource_policy.py"), proof_tests=("tests/test_privilege_broker.py",), proof_commands=("python -m scripts.run_tests -q tests/test_privilege_broker.py tests/test_host_resource_policy.py tests/test_capability_registry.py",), implemented_surfaces=("eligibility-only classification of proposal receipts", "deterministic broker review receipts"), deferred_surfaces=("authorization", "Actuation Fulfillment Layer", "cooling fulfillment", "service restart fulfillment", "cleanup fulfillment", "power policy mutation"), forbidden_implications=("privilege broker eligibility is authorization", "broker review receipt is fulfillment", "privilege broker performs host action"), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("actuation_fulfillment", "actuation_fulfillment", "implemented", "rehearsal_only", source_paths=("sentientos/actuation_fulfillment.py", "sentientos/privilege_broker.py"), proof_tests=("tests/test_actuation_fulfillment.py",), proof_commands=("python -m scripts.run_tests -q tests/test_actuation_fulfillment.py tests/test_privilege_broker.py tests/test_capability_registry.py",), implemented_surfaces=("dry-run fulfillment rehearsal plans", "non-effect fulfillment rehearsal receipts"), deferred_surfaces=("real actuation fulfillment", "rollback execution", "host mutation effects", "fan/PWM writes", "thermal actuation", "service restart", "power profile mutation", "cleanup mutation"), forbidden_implications=("rehearsal plan is authorization", "rehearsal receipt is effect receipt", "privilege broker receipt is fulfillment"), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("real_actuation_fulfillment", "actuation_fulfillment", "deferred", "none", deferred_surfaces=("candidate-to-effect fulfillment", "privileged host mutation", "fan/PWM writes", "thermal actuation", "service restart", "power profile mutation", "cleanup mutation"), forbidden_implications=("Phase 5 implements real actuation", "rehearsal receipt is effect receipt"), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("effect_receipt_contract", "execution_proof", "implemented", "proof_only", source_paths=("sentientos/effect_proof.py",), proof_tests=("tests/test_effect_proof.py",), proof_commands=("python -m scripts.run_tests -q tests/test_effect_proof.py",), implemented_surfaces=("metadata-only effect receipt contract schema", "proof gates for future effects"), deferred_surfaces=("real effect receipt issuance", "real host action execution"), forbidden_implications=("effect receipt contract is a real effect receipt", "contract grants authorization"), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("postcondition_checks", "execution_proof", "implemented", "proof_only", source_paths=("sentientos/effect_proof.py",), proof_tests=("tests/test_effect_proof.py",), implemented_surfaces=("metadata-only postcondition plan and rehearsal receipt schemas",), deferred_surfaces=("postcondition checks against real effects",), forbidden_implications=("postcondition schema proves an effect occurred",), requires_audit_receipt=True),
        _record("rollback_planning", "execution_proof", "implemented", "proof_only", source_paths=("sentientos/effect_proof.py",), proof_tests=("tests/test_effect_proof.py",), implemented_surfaces=("metadata-only rollback plans and rollback receipt schemas",), deferred_surfaces=("real rollback execution",), forbidden_implications=("rollback plan executes rollback",), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("runtime_supervisor", "runtime_supervision", "implemented", "telemetry_readiness_only", source_paths=("sentientos/runtime_supervisor.py",), proof_tests=("tests/test_runtime_supervisor.py",), proof_commands=("python -m scripts.run_tests -q tests/test_runtime_supervisor.py",), implemented_surfaces=("supplied service telemetry snapshots", "runtime supervisor readiness reports"), deferred_surfaces=("service restart", "process kill", "service manager mutation"), forbidden_implications=("runtime supervisor restarts or kills services",), requires_audit_receipt=True),
        _record("execution_readiness_manifest", "execution_proof", "implemented", "readiness_only", source_paths=("sentientos/effect_proof.py", "sentientos/runtime_supervisor.py"), proof_tests=("tests/test_effect_proof.py", "tests/test_runtime_supervisor.py"), implemented_surfaces=("metadata-only execution readiness manifest",), deferred_surfaces=("authorization", "fulfillment", "real actuation"), forbidden_implications=("execution readiness is authorization", "readiness manifest performs effects"), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("authorization_review", "authorization_review", "implemented", "review_only", source_paths=("sentientos/authorization_review.py",), proof_tests=("tests/test_authorization_review.py",), proof_commands=("python -m scripts.run_tests -q tests/test_authorization_review.py",), implemented_surfaces=("metadata-only authorization review packets", "authorization review decisions", "authorization review receipts"), deferred_surfaces=("real authorization grants", "real effect execution", "real rollback execution"), forbidden_implications=("authorization review is authorization", "authorization review receipt is fulfillment"), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("future_authorization_grant_schema", "authorization_review", "implemented", "schema_only", source_paths=("sentientos/authorization_review.py",), proof_tests=("tests/test_authorization_review.py",), implemented_surfaces=("future authorization grant schema placeholder",), deferred_surfaces=("real authorization grant issuance", "host mutation fulfillment"), forbidden_implications=("future authorization grant schema is a real grant", "schema grants fulfillment"), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("controlled_authorization_contract", "controlled_authorization", "implemented", "contract_only", source_paths=("sentientos/controlled_authorization.py",), proof_tests=("tests/test_controlled_authorization.py",), implemented_surfaces=("controlled authorization grant contract metadata",), deferred_surfaces=("live authorization grant", "real fulfillment", "real actuation"), forbidden_implications=("controlled authorization contract is a live grant", "contract authorizes fulfillment"), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("controlled_authorization_grant_record", "controlled_authorization", "implemented", "schema_only", source_paths=("sentientos/controlled_authorization.py",), proof_tests=("tests/test_controlled_authorization.py",), implemented_surfaces=("schema-only future-use grant record",), deferred_surfaces=("live authorization grant",), forbidden_implications=("grant record grants live authority",)),
        _record("controlled_authorization_ledger", "controlled_authorization", "implemented", "ledger_only", source_paths=("sentientos/controlled_authorization.py",), proof_tests=("tests/test_controlled_authorization.py",), implemented_surfaces=("metadata-only authorization ledger scaffold",), deferred_surfaces=("runtime authority token",), forbidden_implications=("ledger grants authorization",)),
        _record("host_embodiment_trace", "host_embodiment_trace", "implemented", "demo_proof_only", source_paths=("sentientos/host_embodiment_trace.py",), proof_tests=("tests/test_host_embodiment_trace.py",), implemented_surfaces=("reviewer-facing non-mutating demo trace",), deferred_surfaces=("live authorization", "real effects", "real rollback"), forbidden_implications=("demo trace executes host actions", "trace grants authority")),
        _record("host_embodiment_trace_export", "host_embodiment_trace", "implemented", "demo_proof_only", source_paths=("sentientos/host_embodiment_trace_export.py",), proof_tests=("tests/test_host_embodiment_trace_export.py",), proof_commands=("python scripts/build_host_embodiment_trace.py --format json", "python scripts/build_host_embodiment_trace.py --format markdown", "python scripts/build_host_embodiment_trace.py --validate-only"), implemented_surfaces=("deterministic sorted-key JSON trace export", "reviewer Markdown trace summary", "explicit-path artifact writing"), deferred_surfaces=("live host collection", "live authorization", "real effects"), forbidden_implications=("trace export collects live host data", "trace export grants authority", "trace export performs effects")),
        _record("reviewer_demo_trace", "host_embodiment_trace", "implemented", "demo_proof_only", source_paths=("scripts/build_host_embodiment_trace.py", "tests/fixtures/host_embodiment_trace_thermal_pwm_demo.json"), proof_tests=("tests/test_build_host_embodiment_trace_script.py",), proof_commands=("python scripts/build_host_embodiment_trace.py --format json", "python scripts/build_host_embodiment_trace.py --summary"), implemented_surfaces=("deterministic fake/sample thermal+PWM reviewer demo",), deferred_surfaces=("live host collection", "host mutation", "runtime authority token"), forbidden_implications=("reviewer demo performs live collection by default", "reviewer demo authorizes host actions")),
        _record("reviewer_proof_bundle", "reviewer_proof_bundle", "implemented", "demo_proof_only", source_paths=("sentientos/reviewer_proof_bundle.py",), proof_tests=("tests/test_reviewer_proof_bundle.py",), proof_commands=("python scripts/build_reviewer_proof_bundle.py --output-dir /tmp/sentientos-reviewer-proof --force",), implemented_surfaces=("metadata-only first-run reviewer proof bundle", "deterministic local packaging of demo trace, capability posture, deferred actions, and proof commands"), deferred_surfaces=("live host trace collection", "live authorization", "real effects", "host mutation"), forbidden_implications=("reviewer proof bundle collects live host data", "reviewer proof bundle grants authority", "reviewer proof bundle performs effects")),
        _record("reviewer_proof_bundle_cli", "reviewer_proof_bundle", "implemented", "demo_proof_only", source_paths=("scripts/build_reviewer_proof_bundle.py",), proof_tests=("tests/test_build_reviewer_proof_bundle_script.py",), proof_commands=("python scripts/build_reviewer_proof_bundle.py --output-dir /tmp/sentientos-reviewer-proof --force",), implemented_surfaces=("one-command local proof bundle writer",), deferred_surfaces=("verification command execution by default", "live host collection", "host mutation"), forbidden_implications=("CLI performs live verification by default", "CLI mutates host state beyond explicit bundle files")),
        _record("proof_command_manifest", "reviewer_proof_bundle", "implemented", "proof_only", source_paths=("sentientos/reviewer_proof_bundle.py",), proof_tests=("tests/test_reviewer_proof_bundle.py",), implemented_surfaces=("bounded local proof command inventory",), deferred_surfaces=("default proof command execution", "network commands", "provider invocation"), forbidden_implications=("listed proof commands have run", "proof command manifest grants runtime authority")),
        _record("host_actuation_safety_gates", "host_actuation_safety", "implemented", "metadata_proof_only", source_paths=("sentientos/host_actuation_safety.py",), proof_tests=("tests/test_host_actuation_safety.py",), implemented_surfaces=("metadata-only safety gate prerequisite assessment",), deferred_surfaces=("live authorization grant", "real actuation", "host mutation"), forbidden_implications=("safety gates are authorization", "safety gates perform effects"), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("hardware_allowlist_manifest", "host_actuation_safety", "implemented", "allowlist_only", source_paths=("sentientos/host_actuation_safety.py",), proof_tests=("tests/test_host_actuation_safety.py",), implemented_surfaces=("metadata-only hardware allowlist manifests",), deferred_surfaces=("hardware control authority", "host mutation"), forbidden_implications=("hardware allowlist grants control",)),
        _record("os_backend_declaration", "host_actuation_safety", "implemented", "declaration_only", source_paths=("sentientos/host_actuation_safety.py",), proof_tests=("tests/test_host_actuation_safety.py",), implemented_surfaces=("declaration-only OS backend records",), deferred_surfaces=("backend loading", "backend invocation", "host mutation"), forbidden_implications=("OS backend declaration loads or invokes backend",)),
        _record("bounds_policy", "host_actuation_safety", "implemented", "policy_only", source_paths=("sentientos/host_actuation_safety.py",), proof_tests=("tests/test_host_actuation_safety.py",), implemented_surfaces=("metadata-only bounds policy records",), deferred_surfaces=("live bounds enforcement", "host mutation"), forbidden_implications=("bounds policy enforces live action",)),
        _record("cooldown_policy", "host_actuation_safety", "implemented", "policy_only", source_paths=("sentientos/host_actuation_safety.py",), proof_tests=("tests/test_host_actuation_safety.py",), implemented_surfaces=("metadata-only cooldown policy records",), deferred_surfaces=("live cooldown enforcement", "host mutation"), forbidden_implications=("cooldown policy waits or enforces live action",)),
        _record("panic_stop_contract", "host_actuation_safety", "implemented", "contract_only", source_paths=("sentientos/host_actuation_safety.py",), proof_tests=("tests/test_host_actuation_safety.py",), implemented_surfaces=("metadata-only panic stop contracts",), deferred_surfaces=("panic stop execution", "host mutation"), forbidden_implications=("panic stop contract executes stop",)),
        _record("host_action_scope_manifest", "host_actuation_safety", "implemented", "scope_only", source_paths=("sentientos/host_actuation_safety.py",), proof_tests=("tests/test_host_actuation_safety.py",), implemented_surfaces=("metadata-only host action scope manifests",), deferred_surfaces=("action authorization", "host mutation"), forbidden_implications=("scope manifest authorizes action",)),
        _record("safety_gate_satisfaction_manifest", "host_actuation_safety", "implemented", "safety_gate_only", source_paths=("sentientos/host_actuation_safety.py",), proof_tests=("tests/test_host_actuation_safety.py",), implemented_surfaces=("metadata-only safety gate satisfaction manifests",), deferred_surfaces=("live authorization", "fulfillment", "real effects"), forbidden_implications=("safety satisfaction manifest is authorization or fulfillment",)),
        _record("live_grant_readiness", "live_grant_readiness", "implemented", "readiness_only", source_paths=("sentientos/live_grant_readiness.py",), proof_tests=("tests/test_live_grant_readiness.py",), implemented_surfaces=("metadata-only live-grant readiness assessment",), deferred_surfaces=("live authorization grant", "real fulfillment", "host mutation"), forbidden_implications=("live-grant readiness is a live grant", "readiness authorizes fulfillment"), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("live_grant_prerequisite_matrix", "live_grant_readiness", "implemented", "metadata_proof_only", source_paths=("sentientos/live_grant_readiness.py",), proof_tests=("tests/test_live_grant_readiness.py",), implemented_surfaces=("metadata-only prerequisite matrix",), deferred_surfaces=("authorization approval", "live grant issuance"), forbidden_implications=("prerequisite matrix grants authority",)),
        _record("operator_policy_approval_packet", "live_grant_readiness", "implemented", "packet_only", source_paths=("sentientos/live_grant_readiness.py",), proof_tests=("tests/test_live_grant_readiness.py",), implemented_surfaces=("operator/policy approval packet scaffold",), deferred_surfaces=("operator approval", "policy approval", "live authorization grant"), forbidden_implications=("approval packet is approval",)),
        _record("grant_issue_preflight_receipt", "live_grant_readiness", "implemented", "preflight_only", source_paths=("sentientos/live_grant_readiness.py",), proof_tests=("tests/test_live_grant_readiness.py",), implemented_surfaces=("grant issue preflight receipt",), deferred_surfaces=("grant issuance", "fulfillment", "effect receipt"), forbidden_implications=("preflight receipt issues a grant",)),
        _record("grant_denial_deferral_receipt", "live_grant_readiness", "implemented", "denial_deferral_only", source_paths=("sentientos/live_grant_readiness.py",), proof_tests=("tests/test_live_grant_readiness.py",), implemented_surfaces=("grant denial/deferral receipt",), deferred_surfaces=("grant issuance", "host mutation"), forbidden_implications=("denial/deferral receipt mutates host state",)),
        _record("local_authorization_grant", "local_authorization_grant", "implemented", "local_authorization_record_only", source_paths=("sentientos/local_authorization_grant.py",), proof_tests=("tests/test_local_authorization_grant.py",), proof_commands=("python -m scripts.run_tests -q tests/test_local_authorization_grant.py",), implemented_surfaces=("bounded local authorization record lifecycle",), deferred_surfaces=("fulfillment authorization consumption", "real effect execution", "host mutation"), forbidden_implications=("local authorization grant is fulfillment", "local authorization grant executes host action"), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("local_authorization_grant_ledger", "local_authorization_grant", "implemented", "authorization_ledger_only", source_paths=("sentientos/local_authorization_grant.py",), proof_tests=("tests/test_local_authorization_grant.py",), implemented_surfaces=("metadata-only local authorization grant ledger",), deferred_surfaces=("host action fulfillment",), forbidden_implications=("ledger mutates host state",)),
        _record("local_authorization_revocation_receipt", "local_authorization_grant", "implemented", "revocation_record_only", source_paths=("sentientos/local_authorization_grant.py",), proof_tests=("tests/test_local_authorization_grant.py",), implemented_surfaces=("local authorization revocation metadata receipt",), deferred_surfaces=("revocation effect execution",), forbidden_implications=("revocation receipt executes host action",)),
        _record("local_authorization_expiry_evaluation", "local_authorization_grant", "implemented", "expiry_evaluation_only", source_paths=("sentientos/local_authorization_grant.py",), proof_tests=("tests/test_local_authorization_grant.py",), implemented_surfaces=("metadata-only grant expiry evaluation",), deferred_surfaces=("scheduler or host action execution",), forbidden_implications=("expiry evaluation executes host action",)),
        _record("local_authorization_verification", "local_authorization_grant", "implemented", "verification_only", source_paths=("sentientos/local_authorization_grant.py",), proof_tests=("tests/test_local_authorization_grant.py",), implemented_surfaces=("grant lookup and verification metadata",), deferred_surfaces=("fulfillment authorization consumption",), forbidden_implications=("verification authorizes fulfillment",)),
        _record("fulfillment_authorization_consumption", "fulfillment_authorization", "implemented", "consumption_receipt_only", source_paths=("sentientos/fulfillment_authorization.py",), proof_tests=("tests/test_fulfillment_authorization.py",), proof_commands=("python -m scripts.run_tests -q tests/test_fulfillment_authorization.py",), implemented_surfaces=("metadata-only fulfillment authorization consumption receipts",), deferred_surfaces=("fulfillment execution", "real effect execution", "host mutation"), forbidden_implications=("authorization consumption is fulfillment", "consumption receipt executes host action"), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("fulfillment_authorization_request", "fulfillment_authorization", "implemented", "request_only", source_paths=("sentientos/fulfillment_authorization.py",), proof_tests=("tests/test_fulfillment_authorization.py",), implemented_surfaces=("metadata-only future fulfillment authorization requests",), deferred_surfaces=("fulfillment execution", "host mutation"), forbidden_implications=("fulfillment authorization request grants fulfillment",)),
        _record("grant_consumption_verification", "fulfillment_authorization", "implemented", "verification_only", source_paths=("sentientos/fulfillment_authorization.py",), proof_tests=("tests/test_fulfillment_authorization.py",), implemented_surfaces=("non-authorizing grant consumption verification metadata",), deferred_surfaces=("fulfillment authorization grant", "effect execution"), forbidden_implications=("grant consumption verification authorizes fulfillment",)),
        _record("fulfillment_scope_match_assessment", "fulfillment_authorization", "implemented", "assessment_only", source_paths=("sentientos/fulfillment_authorization.py",), proof_tests=("tests/test_fulfillment_authorization.py",), implemented_surfaces=("metadata-only requested scope versus granted scope assessment",), deferred_surfaces=("execution", "host mutation"), forbidden_implications=("scope match is execution",)),
        _record("fulfillment_authorization_consumption_receipt", "fulfillment_authorization", "implemented", "consumption_receipt_only", source_paths=("sentientos/fulfillment_authorization.py",), proof_tests=("tests/test_fulfillment_authorization.py",), implemented_surfaces=("metadata-only consumption receipt for future fulfillment",), deferred_surfaces=("fulfillment execution", "real effects", "postcondition checks against real effects"), forbidden_implications=("consumption receipt performs effect",)),
        _record("fulfillment_authorization_denial_receipt", "fulfillment_authorization", "implemented", "denial_receipt_only", source_paths=("sentientos/fulfillment_authorization.py",), proof_tests=("tests/test_fulfillment_authorization.py",), implemented_surfaces=("metadata-only denial receipt for out-of-scope or non-active grants",), deferred_surfaces=("fulfillment execution",), forbidden_implications=("denial receipt executes host action",)),
        _record("fulfillment_executor_contract", "fulfillment_executor_contract", "implemented", "contract_only", source_paths=("sentientos/fulfillment_executor_contract.py",), proof_tests=("tests/test_fulfillment_executor_contract.py",), proof_commands=("python -m scripts.run_tests -q tests/test_fulfillment_executor_contract.py",), implemented_surfaces=("metadata-only future executor contract records",), deferred_surfaces=("executor implementation", "backend invocation", "control-plane admission for fulfillment", "fulfillment execution"), forbidden_implications=("executor contract is an executor", "contract grants fulfillment"), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("executor_backend_declaration", "fulfillment_executor_contract", "implemented", "declaration_only", source_paths=("sentientos/fulfillment_executor_contract.py",), proof_tests=("tests/test_fulfillment_executor_contract.py",), implemented_surfaces=("backend declaration metadata",), deferred_surfaces=("backend loading", "backend invocation"), forbidden_implications=("backend declaration loads a backend", "backend declaration invokes a backend")),
        _record("executor_precondition_manifest", "fulfillment_executor_contract", "implemented", "precondition_only", source_paths=("sentientos/fulfillment_executor_contract.py",), proof_tests=("tests/test_fulfillment_executor_contract.py",), implemented_surfaces=("executor precondition manifest metadata",), deferred_surfaces=("precondition enforcement by a real executor",), forbidden_implications=("precondition manifest performs an effect",)),
        _record("executor_dry_run_plan", "fulfillment_executor_contract", "implemented", "plan_only", source_paths=("sentientos/fulfillment_executor_contract.py",), proof_tests=("tests/test_fulfillment_executor_contract.py",), implemented_surfaces=("dry-run plan metadata",), deferred_surfaces=("dry-run execution",), forbidden_implications=("dry-run plan executes a dry run",)),
        _record("executor_admission_packet", "fulfillment_executor_contract", "implemented", "packet_only", source_paths=("sentientos/fulfillment_executor_contract.py",), proof_tests=("tests/test_fulfillment_executor_contract.py",), implemented_surfaces=("control-plane admission packet metadata",), deferred_surfaces=("control-plane admission", "fulfillment execution"), forbidden_implications=("admission packet is control-plane admission",)),
        _record("executor_contract_readiness_receipt", "fulfillment_executor_contract", "implemented", "readiness_receipt_only", source_paths=("sentientos/fulfillment_executor_contract.py",), proof_tests=("tests/test_fulfillment_executor_contract.py",), implemented_surfaces=("executor contract readiness receipt metadata",), deferred_surfaces=("executor implementation", "backend invocation", "real effects"), forbidden_implications=("readiness receipt implements executor", "readiness receipt performs effects")),
        _record("executor_implementation", "fulfillment_executor_contract", "deferred", "none", source_paths=("sentientos/fulfillment_executor_contract.py",), deferred_surfaces=("future executor implementation", "host mutation", "real fulfillment"), forbidden_implications=("executor contract wing implements executor"), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("backend_invocation", "fulfillment_executor_contract", "deferred", "none", deferred_surfaces=("backend loading", "backend invocation"), forbidden_implications=("backend declaration invokes backend"), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("control_plane_admission_for_fulfillment", "fulfillment_executor_contract", "deferred", "none", deferred_surfaces=("future control-plane admission for fulfillment",), forbidden_implications=("executor admission packet grants admission"), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("dry_run_execution_harness", "dry_run_execution_harness", "implemented", "simulated_only", source_paths=("sentientos/dry_run_execution_harness.py",), proof_tests=("tests/test_dry_run_execution_harness.py",), proof_commands=("python -m scripts.run_tests -q tests/test_dry_run_execution_harness.py",), implemented_surfaces=("deterministic in-process simulated dry-run harness",), deferred_surfaces=("real backend invocation", "real fulfillment execution", "real effect execution", "host mutation"), forbidden_implications=("dry-run harness is real fulfillment", "dry-run harness performs host mutation"), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("simulated_backend_registry", "dry_run_execution_harness", "implemented", "simulated_only", source_paths=("sentientos/dry_run_execution_harness.py",), proof_tests=("tests/test_dry_run_execution_harness.py",), implemented_surfaces=("inert simulated backend registry metadata",), deferred_surfaces=("real backend loading", "real backend invocation"), forbidden_implications=("simulated backend registry loads real backends",)),
        _record("dry_run_execution_request", "dry_run_execution_harness", "implemented", "request_only", source_paths=("sentientos/dry_run_execution_harness.py",), proof_tests=("tests/test_dry_run_execution_harness.py",), implemented_surfaces=("dry-run request records",), deferred_surfaces=("real backend execution",), forbidden_implications=("dry-run request executes a backend",)),
        _record("dry_run_execution_result", "dry_run_execution_harness", "implemented", "simulated_only", source_paths=("sentientos/dry_run_execution_harness.py",), proof_tests=("tests/test_dry_run_execution_harness.py",), implemented_surfaces=("simulation-only dry-run results",), deferred_surfaces=("effect receipt", "host mutation", "real fulfillment"), forbidden_implications=("dry-run result is effect receipt",)),
        _record("dry_run_execution_receipt", "dry_run_execution_harness", "implemented", "dry_run_receipt_only", source_paths=("sentientos/dry_run_execution_harness.py",), proof_tests=("tests/test_dry_run_execution_harness.py",), implemented_surfaces=("dry-run-only execution receipts",), deferred_surfaces=("proof of host mutation", "real effect receipt"), forbidden_implications=("dry-run receipt proves host mutation",)),
        _record("dry_run_effect_verification", "dry_run_audit_closure", "implemented", "dry_run_verification_only", source_paths=("sentientos/dry_run_audit_closure.py",), proof_tests=("tests/test_dry_run_audit_closure.py",), implemented_surfaces=("metadata-only dry-run effect verification records",), deferred_surfaces=("real effect receipt creation", "real effect execution"), forbidden_implications=("dry-run effect verification is a real effect receipt",)),
        _record("dry_run_postcondition_verification", "dry_run_audit_closure", "implemented", "dry_run_postcondition_only", source_paths=("sentientos/dry_run_audit_closure.py",), proof_tests=("tests/test_dry_run_audit_closure.py",), implemented_surfaces=("metadata-only simulated postcondition verification records",), deferred_surfaces=("real host postcondition checks",), forbidden_implications=("dry-run postcondition verification checks real host state",)),
        _record("dry_run_rollback_rehearsal", "dry_run_audit_closure", "implemented", "dry_run_rollback_only", source_paths=("sentientos/dry_run_audit_closure.py",), proof_tests=("tests/test_dry_run_audit_closure.py",), implemented_surfaces=("metadata-only rollback rehearsal records",), deferred_surfaces=("real rollback execution",), forbidden_implications=("dry-run rollback rehearsal executes rollback",)),
        _record("dry_run_audit_closure_receipt", "dry_run_audit_closure", "implemented", "dry_run_audit_only", source_paths=("sentientos/dry_run_audit_closure.py",), proof_tests=("tests/test_dry_run_audit_closure.py",), implemented_surfaces=("metadata-only dry-run audit closure receipts",), deferred_surfaces=("production audit receipt for host effects",), forbidden_implications=("dry-run audit closure is a production audit receipt",)),
        _record("dry_run_closure_bundle", "dry_run_audit_closure", "implemented", "dry_run_closure_only", source_paths=("sentientos/dry_run_audit_closure.py",), proof_tests=("tests/test_dry_run_audit_closure.py",), implemented_surfaces=("metadata-only dry-run closure bundles",), deferred_surfaces=("real fulfillment", "real effect receipt", "real postcondition check", "real rollback"), forbidden_implications=("dry-run closure bundle fulfills host actions",)),
        _record("real_effect_capability_admission", "real_effect_admission", "implemented", "admission_planning_only", source_paths=("sentientos/real_effect_admission.py",), proof_tests=("tests/test_real_effect_admission.py",), implemented_surfaces=("metadata-only real effect capability admission decisions",), deferred_surfaces=("real backend implementation", "real fulfillment execution", "real effect execution", "host mutation"), forbidden_implications=("real effect admission is implementation", "admission authorizes execution")),
        _record("real_effect_capability_candidate", "real_effect_admission", "implemented", "candidate_only", source_paths=("sentientos/real_effect_admission.py",), proof_tests=("tests/test_real_effect_admission.py",), implemented_surfaces=("metadata-only capability candidate records",), deferred_surfaces=("implementation start", "backend loading"), forbidden_implications=("candidate record implements backend",)),
        _record("real_effect_implementation_plan_scaffold", "real_effect_admission", "implemented", "plan_scaffold_only", source_paths=("sentientos/real_effect_admission.py",), proof_tests=("tests/test_real_effect_admission.py",), implemented_surfaces=("implementation plan scaffolds only",), deferred_surfaces=("real backend implementation", "backend invocation", "effect receipt creation"), forbidden_implications=("plan scaffold starts implementation",)),
        _record("real_effect_capability_block_receipt", "real_effect_admission", "implemented", "block_receipt_only", source_paths=("sentientos/real_effect_admission.py",), proof_tests=("tests/test_real_effect_admission.py",), implemented_surfaces=("real effect capability block and deferral receipts",), deferred_surfaces=("blocked host action", "host mutation"), forbidden_implications=("block receipt mutates host state",)),
        _record("local_diagnostic_effect", "local_diagnostic_effect", "implemented", "local_diagnostic_effect_only", source_paths=("sentientos/local_diagnostic_effect.py", "scripts/run_local_diagnostic_effect.py"), proof_tests=("tests/test_local_diagnostic_effect.py", "tests/test_run_local_diagnostic_effect_script.py"), proof_commands=("python -m scripts.run_tests -q tests/test_local_diagnostic_effect.py tests/test_run_local_diagnostic_effect_script.py", "python scripts/run_local_diagnostic_effect.py --output-dir /tmp/sentientos-local-effect --summary"), implemented_surfaces=("explicit optional low-risk local diagnostic file write", "single caller-supplied output directory artifact"), deferred_surfaces=("general host effects", "hardware control", "service control", "cleanup outside exact artifact rollback"), forbidden_implications=("local diagnostic effect is general host backend", "diagnostic artifact write grants hardware control"), requires_operator_approval=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("local_diagnostic_effect_receipt", "local_diagnostic_effect", "implemented", "real_effect_receipt_only", source_paths=("sentientos/local_diagnostic_effect.py",), proof_tests=("tests/test_local_diagnostic_effect.py",), implemented_surfaces=("real effect receipt for diagnostic artifact write only",), deferred_surfaces=("general real effect receipt creation", "privileged host action receipts"), forbidden_implications=("diagnostic receipt covers fan/PWM, thermal, power, service, cleanup, provider, network, prompt, subprocess, shell, or control-plane execution"), requires_audit_receipt=True),
        _record("local_diagnostic_postcondition_check", "local_diagnostic_effect", "implemented", "real_postcondition_check_only", source_paths=("sentientos/local_diagnostic_effect.py",), proof_tests=("tests/test_local_diagnostic_effect.py",), implemented_surfaces=("readback postcondition check for the exact diagnostic artifact only",), deferred_surfaces=("general host postcondition checks",), forbidden_implications=("postcondition readback scans broad filesystem")),
        _record("local_diagnostic_production_audit_receipt", "local_diagnostic_effect", "implemented", "production_audit_only", source_paths=("sentientos/local_diagnostic_effect.py",), proof_tests=("tests/test_local_diagnostic_effect.py",), implemented_surfaces=("production audit receipt for local diagnostic artifact effect only",), deferred_surfaces=("production audits for general host effects",), forbidden_implications=("diagnostic audit authorizes broader effects")),
        _record("local_diagnostic_rollback_plan", "local_diagnostic_effect", "implemented", "plan_only", source_paths=("sentientos/local_diagnostic_effect.py",), proof_tests=("tests/test_local_diagnostic_effect.py",), implemented_surfaces=("rollback plan and non-executed rollback receipt scaffold",), deferred_surfaces=("automatic exact-artifact rollback execution"), forbidden_implications=("rollback plan deletes files"), requires_rollback_receipt=True),
        _record("local_diagnostic_exact_rollback", "local_diagnostic_effect", "implemented", "exact_artifact_rollback_only", source_paths=("sentientos/local_diagnostic_effect.py", "scripts/run_local_diagnostic_rollback.py"), proof_tests=("tests/test_local_diagnostic_exact_rollback.py", "tests/test_run_local_diagnostic_rollback_script.py"), proof_commands=("python -m scripts.run_tests -q tests/test_local_diagnostic_exact_rollback.py tests/test_run_local_diagnostic_rollback_script.py", "python scripts/run_local_diagnostic_rollback.py --effect-receipt <receipt.json> --rollback-plan <rollback-plan.json> --output-dir-scope /tmp/sentientos-local-effect --summary"), implemented_surfaces=("explicit exact-artifact rollback for local diagnostic artifact only", "path, digest, plan, receipt, and scope gated single Path.unlink"), deferred_surfaces=("general cleanup", "recursive delete", "wildcard delete", "unrelated file delete", "hardware control", "service control"), forbidden_implications=("exact diagnostic rollback is general cleanup", "exact diagnostic rollback deletes directories, siblings, wildcard matches, or unrelated files"), requires_operator_approval=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("local_diagnostic_rollback_postcondition_check", "local_diagnostic_effect", "implemented", "exact_artifact_postcondition_only", source_paths=("sentientos/local_diagnostic_effect.py",), proof_tests=("tests/test_local_diagnostic_exact_rollback.py",), implemented_surfaces=("postcondition check verifies exact artifact path absence only",), deferred_surfaces=("broad filesystem checks",), forbidden_implications=("rollback postcondition scans broad filesystem")),
        _record("local_diagnostic_rollback_audit_receipt", "local_diagnostic_effect", "implemented", "exact_artifact_rollback_audit_only", source_paths=("sentientos/local_diagnostic_effect.py",), proof_tests=("tests/test_local_diagnostic_exact_rollback.py",), implemented_surfaces=("audit receipt for exact local diagnostic artifact rollback only",), deferred_surfaces=("general rollback audits",), forbidden_implications=("rollback audit authorizes cleanup or unrelated deletion")),
        _record("local_effect_transaction_ledger", "local_effect_transaction_ledger", "implemented", "local_effect_transaction_ledger_only", source_paths=("sentientos/local_effect_transaction_ledger.py", "scripts/build_local_effect_transaction_ledger.py"), proof_tests=("tests/test_local_effect_transaction_ledger.py", "tests/test_build_local_effect_transaction_ledger_script.py"), proof_commands=("python -m scripts.run_tests -q tests/test_local_effect_transaction_ledger.py tests/test_build_local_effect_transaction_ledger_script.py", "python scripts/build_local_effect_transaction_ledger.py --effect-receipt <effect_receipt.json> --postcondition-check <postcondition.json> --production-audit <audit.json> --rollback-plan <rollback_plan.json> --summary"), implemented_surfaces=("metadata-only transaction ledger for local diagnostic effect and exact rollback records", "digest-chain validation", "open/orphan/incomplete/contradicted/closed lifecycle classification"), deferred_surfaces=("broader effect transaction ledger", "general cleanup", "broader host control"), forbidden_implications=("transaction ledger performs host effects", "ledger authorizes cleanup or rollback"), requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("local_effect_lifecycle_report", "local_effect_transaction_ledger", "implemented", "local_effect_lifecycle_report_only", source_paths=("sentientos/local_effect_transaction_ledger.py",), proof_tests=("tests/test_local_effect_transaction_ledger.py",), implemented_surfaces=("metadata-only lifecycle status report for local diagnostic transactions",), deferred_surfaces=("general lifecycle enforcement",), forbidden_implications=("lifecycle report performs host mutation")),
        _record("local_effect_transaction_ledger_artifact", "local_effect_transaction_ledger", "implemented", "explicit_local_artifact_only", source_paths=("sentientos/local_effect_transaction_ledger.py", "scripts/build_local_effect_transaction_ledger.py"), proof_tests=("tests/test_local_effect_transaction_ledger.py", "tests/test_build_local_effect_transaction_ledger_script.py"), implemented_surfaces=("optional explicit caller-supplied local JSON ledger artifact write",), deferred_surfaces=("default proof bundle execution", "implicit artifact writes"), forbidden_implications=("ledger artifact write runs effect or rollback")),
        _record("workspace_scoped_file_effect", "workspace_file_effect", "implemented", "explicit_local_artifact_only", source_paths=("sentientos/workspace_file_effect.py", "scripts/run_workspace_file_effect.py"), proof_tests=("tests/test_workspace_file_effect.py", "tests/test_run_workspace_file_effect_script.py"), proof_commands=("python -m scripts.run_tests -q tests/test_workspace_file_effect.py tests/test_run_workspace_file_effect_script.py", "python scripts/run_workspace_file_effect.py --workspace-root /tmp/sentientos-workspace-file-effect --target demo.txt --payload hello --summary"), implemented_surfaces=("explicit single-file create/update inside caller-supplied workspace root", "relative normalized scope-checked target path", "atomic same-directory replace where reasonable"), deferred_surfaces=("general filesystem access", "directory cleanup", "recursive delete", "wildcard delete", "unrelated file delete"), forbidden_implications=("workspace file effect is general filesystem authority", "workspace file effect grants cleanup, hardware, service, network, provider, prompt, subprocess, shell, or control-plane authority"), requires_operator_approval=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("workspace_file_preimage_capture", "workspace_file_effect", "implemented", "explicit_local_artifact_only", source_paths=("sentientos/workspace_file_effect.py",), proof_tests=("tests/test_workspace_file_effect.py",), implemented_surfaces=("exact-target preimage capture before replacement", "in-record base64 preimage for exact rollback"), deferred_surfaces=("broad filesystem snapshot",), forbidden_implications=("preimage capture scans unrelated files")),
        _record("workspace_file_postcondition_check", "workspace_file_effect", "implemented", "real_postcondition_check_only", source_paths=("sentientos/workspace_file_effect.py",), proof_tests=("tests/test_workspace_file_effect.py",), implemented_surfaces=("exact-target digest and byte-count postcondition check",), deferred_surfaces=("broad filesystem postcondition checks",), forbidden_implications=("postcondition check scans sibling directories")),
        _record("workspace_file_exact_rollback", "workspace_file_effect", "implemented", "exact_artifact_rollback_only", source_paths=("sentientos/workspace_file_effect.py", "scripts/run_workspace_file_effect.py"), proof_tests=("tests/test_workspace_file_effect.py", "tests/test_run_workspace_file_effect_script.py"), proof_commands=("python scripts/run_workspace_file_effect.py --workspace-root /tmp/sentientos-workspace-file-effect --target demo.txt --payload hello --rollback --summary",), implemented_surfaces=("exact-target rollback removes only a created target after digest check", "exact-target rollback restores captured preimage after digest check"), deferred_surfaces=("general cleanup", "recursive delete", "wildcard delete", "unrelated file delete"), forbidden_implications=("workspace rollback deletes directories, siblings, wildcard matches, or unrelated files"), requires_operator_approval=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("workspace_file_production_audit", "workspace_file_effect", "implemented", "production_audit_only", source_paths=("sentientos/workspace_file_effect.py",), proof_tests=("tests/test_workspace_file_effect.py",), implemented_surfaces=("production audit receipt for workspace file effect only",), deferred_surfaces=("production audits for general host effects",), forbidden_implications=("workspace audit authorizes broader host effects")),
        _record("general_filesystem_access", "workspace_file_effect", "blocked", "none", deferred_surfaces=("general filesystem access", "multi-file mutation", "directory traversal"), forbidden_implications=("workspace single-file pilot grants general filesystem authority"), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("wildcard_delete", "execution_proof", "blocked", "none", deferred_surfaces=("wildcard delete",), forbidden_implications=("exact rollback uses wildcard deletion"), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("host_steward_authority_profile", "host_steward_boundary", "implemented", "authority_profile_only", source_paths=("sentientos/host_steward_boundary.py",), proof_tests=("tests/test_host_steward_boundary.py",), implemented_surfaces=("metadata-only host steward authority profile", "top-level operator-delegated broad local authority model"), deferred_surfaces=("delegated runner execution",), forbidden_implications=("authority profile grants live runner authority",)),
        _record("delegated_runner_boundary_profile", "delegated_runner_boundary", "implemented", "boundary_profile_only", source_paths=("sentientos/host_steward_boundary.py",), proof_tests=("tests/test_host_steward_boundary.py",), implemented_surfaces=("metadata-only delegated runner boundary profile", "ambient authority inheritance denial"), deferred_surfaces=("live runner implementation",), forbidden_implications=("boundary profile executes runner",)),
        _record("execution_containment_profile", "delegated_runner_boundary", "implemented", "containment_profile_only", source_paths=("sentientos/host_steward_boundary.py",), proof_tests=("tests/test_host_steward_boundary.py",), implemented_surfaces=("metadata-only containment declaration",), deferred_surfaces=("live sandbox enforcement",), forbidden_implications=("containment declaration is live sandbox execution",)),
        _record("backend_adapter_authority_declaration", "delegated_runner_boundary", "implemented", "declaration_only", source_paths=("sentientos/host_steward_boundary.py",), proof_tests=("tests/test_host_steward_boundary.py",), implemented_surfaces=("metadata-only backend adapter authority declaration",), deferred_surfaces=("backend loading", "backend invocation"), forbidden_implications=("declaration invokes backend",)),
        _record("runner_capability_grant_scaffold", "delegated_runner_boundary", "implemented", "grant_scaffold_only", source_paths=("sentientos/host_steward_boundary.py",), proof_tests=("tests/test_host_steward_boundary.py",), implemented_surfaces=("metadata-only scoped revocable auditable grant scaffold",), deferred_surfaces=("live runner grant issuance",), forbidden_implications=("grant scaffold issues live runner grant",)),
        _record("runner_boundary_assessment", "delegated_runner_boundary", "implemented", "assessment_only", source_paths=("sentientos/host_steward_boundary.py",), proof_tests=("tests/test_host_steward_boundary.py",), implemented_surfaces=("metadata-only runner boundary assessment",), deferred_surfaces=("execution authorization",), forbidden_implications=("boundary assessment authorizes execution",)),
        _record("runner_boundary_violation_receipt", "delegated_runner_boundary", "implemented", "violation_receipt_only", source_paths=("sentientos/host_steward_boundary.py",), proof_tests=("tests/test_host_steward_boundary.py",), implemented_surfaces=("metadata-only runner boundary violation receipt",), deferred_surfaces=("runner execution", "host mutation"), forbidden_implications=("violation receipt authorizes execution",)),
        _record("builtin_local_effect_runner", "delegated_runner_boundary", "implemented", "bounded_in_process_runner", source_paths=("sentientos/builtin_local_effect_runner.py", "scripts/run_builtin_local_effect_runner.py"), proof_tests=("tests/test_builtin_local_effect_runner.py", "tests/test_run_builtin_local_effect_runner_script.py"), proof_commands=("python -m scripts.run_tests -q tests/test_builtin_local_effect_runner.py tests/test_run_builtin_local_effect_runner_script.py", "python scripts/run_builtin_local_effect_runner.py --action local_diagnostic_artifact_write --output-dir /tmp/sentientos-local-effect-runner --summary"), implemented_surfaces=("bounded built-in in-process delegated runner", "local diagnostic artifact write, exact-artifact rollback, workspace-scoped file update, and workspace exact rollback"), deferred_surfaces=("general runner framework", "generated-code runners", "plugin runners", "federation import runners", "external tool runners"), forbidden_implications=("built-in runner is general runner framework", "built-in runner grants ambient delegated authority", "built-in runner uses subprocess shell network provider prompt hardware service power or cleanup authority"), requires_operator_approval=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("builtin_runner_local_diagnostic_artifact_write", "delegated_runner_boundary", "implemented", "builtin_runner_action_only", source_paths=("sentientos/builtin_local_effect_runner.py", "sentientos/local_diagnostic_effect.py"), proof_tests=("tests/test_builtin_local_effect_runner.py",), implemented_surfaces=("in-process invocation of existing local diagnostic artifact write path",), deferred_surfaces=("broader local effects",), forbidden_implications=("diagnostic runner action is general host mutation",), requires_operator_approval=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("builtin_runner_exact_artifact_rollback", "delegated_runner_boundary", "implemented", "builtin_runner_action_only", source_paths=("sentientos/builtin_local_effect_runner.py", "sentientos/local_diagnostic_effect.py"), proof_tests=("tests/test_builtin_local_effect_runner.py",), implemented_surfaces=("in-process invocation of existing exact artifact rollback path",), deferred_surfaces=("general cleanup", "directory cleanup", "recursive delete", "unrelated file deletion"), forbidden_implications=("exact rollback runner action is general cleanup",), requires_operator_approval=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("builtin_runner_workspace_scoped_file_update", "delegated_runner_boundary", "implemented", "builtin_runner_action_only", source_paths=("sentientos/builtin_local_effect_runner.py", "sentientos/workspace_file_effect.py"), proof_tests=("tests/test_builtin_local_effect_runner.py", "tests/test_run_builtin_local_effect_runner_script.py"), implemented_surfaces=("in-process invocation of existing workspace-scoped single-file update path", "one explicit relative target inside one explicit workspace root"), deferred_surfaces=("general filesystem runner", "multi-file mutation", "directory operations"), forbidden_implications=("workspace runner update is general filesystem access",), requires_operator_approval=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("builtin_runner_workspace_file_exact_rollback", "delegated_runner_boundary", "implemented", "builtin_runner_action_only", source_paths=("sentientos/builtin_local_effect_runner.py", "sentientos/workspace_file_effect.py"), proof_tests=("tests/test_builtin_local_effect_runner.py", "tests/test_run_builtin_local_effect_runner_script.py"), implemented_surfaces=("in-process invocation of existing workspace exact-target rollback path", "rollback only for produced explicit target after existing digest/scope checks"), deferred_surfaces=("general cleanup", "recursive delete", "wildcard delete", "unrelated file deletion"), forbidden_implications=("workspace runner rollback deletes siblings or performs cleanup",), requires_operator_approval=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("workspace_file_transaction_ledger", "workspace_file_transaction_ledger", "implemented", "metadata_ledger_only", source_paths=("sentientos/workspace_file_transaction_ledger.py", "scripts/build_workspace_file_transaction_ledger.py"), proof_tests=("tests/test_workspace_file_transaction_ledger.py", "tests/test_build_workspace_file_transaction_ledger_script.py"), proof_commands=("python -m scripts.run_tests -q tests/test_workspace_file_transaction_ledger.py tests/test_build_workspace_file_transaction_ledger_script.py",), implemented_surfaces=("metadata-only digest-chained ledger over supplied workspace file records",), deferred_surfaces=("effect execution", "rollback execution"), forbidden_implications=("workspace file transaction ledger mutates target files",)),
        _record("workspace_file_lifecycle_report", "workspace_file_transaction_ledger", "implemented", "report_only", source_paths=("sentientos/workspace_file_transaction_ledger.py",), proof_tests=("tests/test_workspace_file_transaction_ledger.py",), implemented_surfaces=("metadata-only lifecycle classification for workspace file transactions",), deferred_surfaces=("effect execution",), forbidden_implications=("lifecycle report grants filesystem authority",)),
        _record("workspace_file_transaction_ledger_artifact", "workspace_file_transaction_ledger", "implemented", "explicit-local-artifact-only", source_paths=("sentientos/workspace_file_transaction_ledger.py", "scripts/build_workspace_file_transaction_ledger.py"), proof_tests=("tests/test_workspace_file_transaction_ledger.py", "tests/test_build_workspace_file_transaction_ledger_script.py"), implemented_surfaces=("optional explicit caller-supplied local ledger artifact write only",), deferred_surfaces=("target file mutation", "cleanup"), forbidden_implications=("ledger artifact write is workspace file effect",)),
        _record("workspace_file_transaction_orchestration", "delegated_runner_boundary", "deferred", "none", deferred_surfaces=("workspace file update/rollback orchestration",), forbidden_implications=("diagnostic orchestrator implies workspace file orchestration",), requires_operator_approval=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("general_filesystem_runner", "delegated_runner_boundary", "blocked", "none", deferred_surfaces=("general filesystem runner",), forbidden_implications=("workspace runner actions grant general filesystem runner authority",), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("builtin_runner_transaction_orchestrator", "delegated_runner_boundary", "implemented", "bounded-orchestrator", source_paths=("sentientos/builtin_runner_transaction_orchestrator.py", "scripts/run_builtin_runner_transaction.py"), proof_tests=("tests/test_builtin_runner_transaction_orchestrator.py", "tests/test_run_builtin_runner_transaction_script.py"), proof_commands=("python -m scripts.run_tests -q tests/test_builtin_runner_transaction_orchestrator.py tests/test_run_builtin_runner_transaction_script.py", "python scripts/run_builtin_runner_transaction.py --output-dir /tmp/sentientos-builtin-runner-transaction --mode diagnostic_write_rollback_with_ledger --ledger-output /tmp/sentientos-builtin-runner-transaction/transaction_ledger.json --summary"), implemented_surfaces=("bounded transaction orchestration of built-in diagnostic write and exact rollback",), deferred_surfaces=("general runner orchestration",), forbidden_implications=("transaction orchestrator is general runner framework", "transaction orchestrator widens delegated authority"), requires_operator_approval=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("builtin_runner_transaction_write_only", "delegated_runner_boundary", "implemented", "bounded diagnostic write orchestration", source_paths=("sentientos/builtin_runner_transaction_orchestrator.py",), proof_tests=("tests/test_builtin_runner_transaction_orchestrator.py",), implemented_surfaces=("orchestrates existing bounded local diagnostic artifact write",), forbidden_implications=("write-only orchestration is new effect class",), requires_operator_approval=True, requires_audit_receipt=True),
        _record("builtin_runner_transaction_write_with_rollback", "delegated_runner_boundary", "implemented", "bounded write/exact-rollback orchestration", source_paths=("sentientos/builtin_runner_transaction_orchestrator.py",), proof_tests=("tests/test_builtin_runner_transaction_orchestrator.py",), implemented_surfaces=("orchestrates existing bounded diagnostic write and exact-artifact rollback",), forbidden_implications=("write-with-rollback orchestration is general cleanup",), requires_operator_approval=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("builtin_runner_transaction_ledger_build", "delegated_runner_boundary", "implemented", "explicit ledger build", source_paths=("sentientos/builtin_runner_transaction_orchestrator.py", "sentientos/local_effect_transaction_ledger.py"), proof_tests=("tests/test_builtin_runner_transaction_orchestrator.py",), implemented_surfaces=("explicit local effect transaction ledger build from produced records",), forbidden_implications=("ledger build performs additional host effects",), requires_audit_receipt=True),
        _record("live_runner_execution", "delegated_runner_boundary", "deferred", "none", deferred_surfaces=("live delegated runner execution",), forbidden_implications=("host steward boundary wing implements runner execution",), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True),
        _record("real_subprocess_runner", "delegated_runner_boundary", "blocked", "none", deferred_surfaces=("subprocess runner",), forbidden_implications=("delegated runner subprocess execution",), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True),
        _record("shell_runner", "delegated_runner_boundary", "blocked", "none", deferred_surfaces=("shell runner",), forbidden_implications=("delegated runner shell execution",), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True),
        _record("network_runner", "delegated_runner_boundary", "blocked", "none", deferred_surfaces=("network runner",), forbidden_implications=("delegated runner network egress",), network_required=False),
        _record("provider_runner", "delegated_runner_boundary", "blocked", "none", deferred_surfaces=("provider runner",), forbidden_implications=("delegated runner provider invocation",), provider_required=False),
        _record("prompt_assembly_runner", "delegated_runner_boundary", "blocked", "none", deferred_surfaces=("prompt assembly runner",), forbidden_implications=("delegated runner prompt assembly",), prompt_assembly_required=False),
        _record("hardware_control_runner", "delegated_runner_boundary", "blocked", "none", deferred_surfaces=("hardware control runner",), forbidden_implications=("delegated runner hardware control",), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True),
        _record("service_control_runner", "delegated_runner_boundary", "blocked", "none", deferred_surfaces=("service control runner",), forbidden_implications=("delegated runner service control",), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True),
        _record("power_control_runner", "delegated_runner_boundary", "blocked", "none", deferred_surfaces=("power control runner",), forbidden_implications=("delegated runner power control",), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True),
        _record("cleanup_runner", "delegated_runner_boundary", "blocked", "none", deferred_surfaces=("cleanup runner",), forbidden_implications=("delegated runner cleanup",), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("general_effect_transaction_ledger", "local_effect_transaction_ledger", "deferred", "none", deferred_surfaces=("transaction ledgers for broader host effects",), forbidden_implications=("local diagnostic transaction ledger covers arbitrary host effects"), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("general_cleanup", "execution_proof", "blocked", "none", deferred_surfaces=("general cleanup", "directory cleanup", "wildcard cleanup"), forbidden_implications=("exact artifact rollback is general cleanup"), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("recursive_delete", "execution_proof", "blocked", "none", deferred_surfaces=("recursive delete",), forbidden_implications=("rollback uses recursive deletion"), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("unrelated_file_delete", "execution_proof", "blocked", "none", deferred_surfaces=("unrelated file deletion",), forbidden_implications=("exact artifact rollback deletes siblings"), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("package_install", "install_bootstrap", "blocked", "none", deferred_surfaces=("package installation",), forbidden_implications=("proof bundle or local effect installs packages"), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("driver_install", "hardware_driver_awareness", "blocked", "none", deferred_surfaces=("driver installation",), forbidden_implications=("driver awareness installs drivers"), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("network_egress", "local_model_chat", "blocked", "none", deferred_surfaces=("network egress",), forbidden_implications=("local ledgers open network connections")),
        _record("prompt_assembly", "local_model_chat", "blocked", "none", deferred_surfaces=("prompt assembly", "prompt export"), forbidden_implications=("reviewer proof or local ledgers assemble prompts")),
        _record("remote_execution", "federation_evidence", "blocked", "none", deferred_surfaces=("remote execution",), forbidden_implications=("federation evidence executes remotely"), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("local_diagnostic_rollback_execution", "local_diagnostic_effect", "deferred", "none", source_paths=("sentientos/local_diagnostic_effect.py",), proof_tests=("tests/test_local_diagnostic_effect.py",), deferred_surfaces=("general rollback execution outside exact local diagnostic artifact"), forbidden_implications=("rollback scaffold performs deletion")),
        _record("real_backend_implementation", "real_effect_admission", "deferred", "none", deferred_surfaces=("real backend implementation", "OS backend implementation"), forbidden_implications=("real effect admission implements backends",), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("real_effect_receipt_creation", "dry_run_audit_closure", "deferred", "none", deferred_surfaces=("real effect receipt creation",), forbidden_implications=("dry-run audit closure creates real effect receipts",), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("real_postcondition_check", "dry_run_audit_closure", "deferred", "none", deferred_surfaces=("real host postcondition checking",), forbidden_implications=("dry-run audit closure checks real host postconditions",), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("production_audit_receipt_for_host_effect", "dry_run_audit_closure", "deferred", "none", deferred_surfaces=("production audit receipts for real host effects",), forbidden_implications=("dry-run audit closure emits production audit receipts",), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("general_runner_orchestration", "delegated_runner_boundary", "deferred", "none", deferred_surfaces=("general delegated runner orchestration",), forbidden_implications=("bounded transaction orchestrator is general runner orchestration",), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("general_runner_framework", "delegated_runner_boundary", "deferred", "none", deferred_surfaces=("general delegated runner framework",), forbidden_implications=("bounded built-in runner is a general runner",), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("generated_code_runner", "delegated_runner_boundary", "blocked", "none", deferred_surfaces=("generated-code execution",), forbidden_implications=("bounded built-in runner executes generated code",), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True),
        _record("plugin_runner", "delegated_runner_boundary", "blocked", "none", deferred_surfaces=("plugin execution",), forbidden_implications=("bounded built-in runner loads plugins",), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True),
        _record("federation_import_runner", "delegated_runner_boundary", "blocked", "none", deferred_surfaces=("federation import execution",), forbidden_implications=("bounded built-in runner executes federation imports",), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True),
        _record("subprocess_runner", "delegated_runner_boundary", "blocked", "none", deferred_surfaces=("subprocess execution",), forbidden_implications=("bounded built-in runner spawns subprocesses",), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True),
        _record("real_backend_invocation", "real_effect_admission", "deferred", "none", deferred_surfaces=("real backend invocation", "OS backend invocation", "control-plane execution"), forbidden_implications=("real effect admission invokes real backends",), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("fulfillment_execution", "fulfillment_authorization", "deferred", "none", deferred_surfaces=("future fulfillment executor", "host mutation", "effect receipt from real action"), forbidden_implications=("fulfillment authorization wing implements execution",), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("live_host_trace_collection", "host_embodiment_trace", "deferred", "none", deferred_surfaces=("live host trace collection", "privileged probing"), forbidden_implications=("reviewer demo default collects live host data",)),
        _record("live_authorization_grant", "controlled_authorization", "deferred", "none", deferred_surfaces=("live controlled authorization grant", "runtime authority token"), forbidden_implications=("controlled authorization wing implements live grants",), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("real_authorization_grant", "authorization_review", "deferred", "none", deferred_surfaces=("operator/policy authorization grant issuance",), forbidden_implications=("authorization review wing grants authorization",), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("real_effect_execution", "execution_proof", "deferred", "none", deferred_surfaces=("authorized effect fulfillment", "host mutation", "effect receipt from real action"), forbidden_implications=("execution proof wing implements real effects",), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("real_rollback_execution", "execution_proof", "deferred", "none", deferred_surfaces=("rollback execution", "host mutation rollback",), forbidden_implications=("rollback receipt schema executes rollback",), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("real_service_restart", "runtime_supervision", "blocked", "none", deferred_surfaces=("service restart", "service stop", "process kill"), forbidden_implications=("runtime supervisor grants restart authority",), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("real_fan_pwm_control", "execution_proof", "blocked", "none", deferred_surfaces=("fan/PWM writes", "thermal actuation"), forbidden_implications=("execution proof wing grants fan/PWM control",), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("real_power_profile_mutation", "execution_proof", "blocked", "none", deferred_surfaces=("power profile mutation",), forbidden_implications=("execution proof wing grants power mutation",), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("real_thermal_actuation", "execution_proof", "blocked", "none", deferred_surfaces=("thermal actuation",), forbidden_implications=("safety gate wing grants thermal actuation",), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("real_file_cleanup", "execution_proof", "blocked", "none", deferred_surfaces=("file cleanup", "file delete",), forbidden_implications=("execution proof wing grants cleanup authority",), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("audit_immutability", "audit_immutability", "implemented", "observation", source_paths=("scripts/audit_immutability_verifier.py", "scripts/verify_audits.py", "vow/immutable_manifest.json"), proof_commands=("python scripts/verify_audits.py --strict", "python scripts/audit_immutability_verifier.py --manifest vow/immutable_manifest.json"), implemented_surfaces=("audit verification",)),
        _record("self_amendment", "self_amendment", "partial", "self_amendment", source_paths=("sentientos/autonomy/runtime.py", "sentientos/autonomy/rehearsal.py"), implemented_surfaces=("rehearsal/governed composition surfaces",), deferred_surfaces=("unapproved self-modification",), forbidden_implications=("runtime authority expansion",), requires_control_plane_admission=True, requires_operator_approval=True, requires_panic_stop=True, requires_audit_receipt=True, requires_rollback_receipt=True),
        _record("federation_evidence_custody", "federation_evidence", "implemented", "federation_evidence", source_paths=("sentientos/federation/",), proof_tests=("tests/test_federated_improvement_candidate.py", "tests/test_federated_improvement_intake_receipt.py", "tests/test_federated_improvement_custody_runway.py"), implemented_surfaces=("federated evidence/receipt custody",), deferred_surfaces=("transport", "sync", "adoption", "merge", "apply", "install", "execution"), forbidden_implications=("federation receipts transport or adopt changes")),
        _record("federation_transport_sync_adoption", "federation_evidence", "blocked", "none", source_paths=("sentientos/federation/",), deferred_surfaces=("transport", "sync", "adoption", "merge", "apply", "install", "remote execution"), forbidden_implications=("evidence custody is adoption")),
        _record("provider_invocation", "local_model_chat", "blocked", "none", source_paths=("docs/architecture/reviewer_release_readiness_index.md",), proof_commands=("python scripts/verify_context_hygiene_prompt_boundaries.py",), deferred_surfaces=("provider invocation", "provider SDK", "network egress", "prompt export"), forbidden_implications=("provider runtime authority exists")),
        _record("docs_proof", "docs_proof", "implemented", "observation", source_paths=("docs/architecture/host_embodiment_substrate_phase1.md", "docs/architecture/host_embodiment_substrate_phase2_read_only_discovery.md", "docs/architecture/host_embodiment_substrate_phase3_policy_receipts.md", "docs/architecture/host_embodiment_substrate_phase4_privilege_broker.md", "docs/architecture/host_embodiment_substrate_phase5_actuation_fulfillment_scaffold.md", "docs/architecture/host_embodiment_execution_proof_wing.md", "docs/architecture/host_embodiment_authorization_review_wing.md", "docs/architecture/host_embodiment_controlled_authorization_and_trace_wing.md", "docs/architecture/host_local_authorization_grant_wing.md", "docs/architecture/host_fulfillment_authorization_consumption_wing.md", "docs/architecture/host_fulfillment_executor_contract_wing.md", "docs/architecture/host_real_effect_capability_admission_wing.md", "docs/architecture/sentientos_trajectory_and_missing_organs.md", "docs/architecture/public_technical_overview.md", "docs/architecture/reviewer_release_readiness_index.md"), proof_tests=("tests/test_reviewer_release_readiness_index.py",), proof_commands=("python scripts/build_docs.py --check-deps", "python scripts/build_docs.py"), implemented_surfaces=("public proof maps and docs build",)),
    )
    return CapabilityRegistry(registry_id="sentientos-host-real-effect-capability-admission-wing", schema_version="host-real-effect-capability-admission-wing.v1", records=records)



def update_registry_from_reviewer_proof_bundle(registry: CapabilityRegistry, manifest: Any) -> CapabilityRegistry:
    """Reflect reviewer proof bundle packaging without claiming live authority."""

    has_manifest = bool(getattr(manifest, "manifest_id", "")) or (isinstance(manifest, Mapping) and bool(manifest.get("manifest_id")))
    records: list[CapabilityRecord] = []
    for record in registry.records:
        if record.capability_id in {"reviewer_proof_bundle", "reviewer_proof_bundle_cli", "proof_command_manifest"}:
            records.append(
                replace(
                    record,
                    status="implemented" if has_manifest else record.status,
                    authority_level="demo_proof_only" if record.capability_id != "proof_command_manifest" else "proof_only",
                    host_actuation_performed=False,
                    metadata_only=True,
                )
            )
        elif record.capability_id == "live_host_trace_collection":
            records.append(replace(record, status="deferred", authority_level="none", host_actuation_performed=False))
        elif record.capability_id in {"live_authorization_grant", "real_effect_execution", "real_rollback_execution"}:
            records.append(replace(record, status="deferred", authority_level="none", host_actuation_performed=False))
        elif record.capability_id in {"real_fan_pwm_control", "real_power_profile_mutation", "real_service_restart", "real_file_cleanup", "direct_fan_pwm_thermal_control"}:
            records.append(replace(record, status="blocked", authority_level="none", host_actuation_performed=False))
        else:
            records.append(record)
    return replace(registry, records=tuple(records), schema_version="reviewer-first-run-proof-bundle.v1")


def update_registry_from_host_inventory(registry: CapabilityRegistry, manifest: Any) -> CapabilityRegistry:
    """Reflect collector-backed hardware inventory without granting control."""

    records: list[CapabilityRecord] = []
    source_paths = ("sentientos/host_collectors.py", "sentientos/host_inventory.py")
    has_collector_source = any(str(label).startswith("collector:") for label in getattr(manifest, "source_labels", ()))
    sensor_count = len(getattr(manifest, "sensors", ()) or ())
    device_count = len(getattr(manifest, "devices", ()) or ())
    status = "implemented" if has_collector_source and (sensor_count or device_count) else "partial"
    for record in registry.records:
        if record.capability_id == "hardware_sensor_inventory":
            records.append(
                replace(
                    record,
                    status=status,
                    authority_level="observation",
                    source_paths=tuple(sorted(set(record.source_paths + source_paths))),
                    proof_tests=tuple(sorted(set(record.proof_tests + ("tests/test_host_collectors.py", "tests/test_host_inventory.py")))),
                    proof_commands=tuple(sorted(set(record.proof_commands + ("python -m scripts.run_tests -q tests/test_host_collectors.py tests/test_host_inventory.py",)))),
                    implemented_surfaces=tuple(sorted(set(record.implemented_surfaces + ("collector-backed read-only local host inventory",)))),
                    deferred_surfaces=tuple(sorted(set(record.deferred_surfaces + ("direct fan/PWM control", "direct thermal actuation",)))),
                    forbidden_implications=tuple(sorted(set(record.forbidden_implications + ("pwm presence is control authority", "inventory grants host actuation",)))),
                    host_actuation_performed=False,
                    metadata_only=True,
                )
            )
        elif record.capability_id == "direct_fan_pwm_thermal_control":
            records.append(replace(record, status="blocked", authority_level="none", host_actuation_performed=False))
        else:
            records.append(record)
    return replace(registry, records=tuple(records), schema_version="host-embodiment-substrate-phase2.v1")


def update_registry_from_host_resource_report(registry: CapabilityRegistry, report: Any) -> CapabilityRegistry:
    """Reflect collector-backed host resource telemetry as observe/model/propose only."""

    records: list[CapabilityRecord] = []
    has_labels = bool(getattr(report, "pressure_labels", ()) or getattr(report, "findings", ()))
    status = "implemented" if has_labels else "partial"
    source_paths = ("sentientos/host_collectors.py", "sentientos/host_resource_governor.py")
    for record in registry.records:
        if record.capability_id == "host_resource_telemetry":
            records.append(
                replace(
                    record,
                    status=status,
                    authority_level="proposal_only",
                    source_paths=tuple(sorted(set(record.source_paths + source_paths))),
                    proof_tests=tuple(sorted(set(record.proof_tests + ("tests/test_host_collectors.py", "tests/test_host_resource_governor.py")))),
                    proof_commands=tuple(sorted(set(record.proof_commands + ("python -m scripts.run_tests -q tests/test_host_collectors.py tests/test_host_resource_governor.py",)))),
                    implemented_surfaces=tuple(sorted(set(record.implemented_surfaces + ("collector-backed read-only resource pressure telemetry",)))),
                    deferred_surfaces=tuple(sorted(set(record.deferred_surfaces + ("cooling fulfillment", "process killing", "service restart", "power profile mutation",)))),
                    forbidden_implications=tuple(sorted(set(record.forbidden_implications + ("telemetry candidates execute host actions",)))),
                    host_actuation_performed=False,
                    metadata_only=True,
                )
            )
        elif record.capability_id == "direct_fan_pwm_thermal_control":
            records.append(replace(record, status="blocked", authority_level="none", host_actuation_performed=False))
        else:
            records.append(record)
    return replace(registry, records=tuple(records), schema_version="host-embodiment-substrate-phase2.v1")


def update_registry_from_host_resource_policy(registry: CapabilityRegistry, decision: Any, receipts: Sequence[Any] = ()) -> CapabilityRegistry:
    """Reflect Phase 3 host resource policy receipts without granting effects."""

    records: list[CapabilityRecord] = []
    has_decision = bool(getattr(decision, "decision_id", ""))
    has_receipts = bool(receipts)
    source_paths = ("sentientos/host_resource_policy.py", "sentientos/host_resource_governor.py")
    for record in registry.records:
        if record.capability_id == "host_resource_policy":
            records.append(
                replace(
                    record,
                    status="implemented" if has_decision else "partial",
                    authority_level="proposal_only",
                    source_paths=tuple(sorted(set(record.source_paths + source_paths))),
                    proof_tests=tuple(sorted(set(record.proof_tests + ("tests/test_host_resource_policy.py",)))),
                    proof_commands=tuple(sorted(set(record.proof_commands + ("python -m scripts.run_tests -q tests/test_host_resource_policy.py",)))),
                    implemented_surfaces=tuple(sorted(set(record.implemented_surfaces + ("pressure-to-policy proposal decision receipts",)))),
                    deferred_surfaces=tuple(sorted(set(record.deferred_surfaces + ("Privilege Broker", "Actuation Fulfillment Layer", "host mutation",)))),
                    forbidden_implications=tuple(sorted(set(record.forbidden_implications + ("policy decision is authorization", "policy receipt performs effects",)))),
                    host_actuation_performed=False,
                    metadata_only=True,
                )
            )
        elif record.capability_id == "host_resource_proposal_receipts":
            records.append(
                replace(
                    record,
                    status="implemented" if has_receipts else "scaffolded",
                    authority_level="proposal_only",
                    source_paths=tuple(sorted(set(record.source_paths + ("sentientos/host_resource_policy.py",)))),
                    proof_tests=tuple(sorted(set(record.proof_tests + ("tests/test_host_resource_policy.py",)))),
                    implemented_surfaces=tuple(sorted(set(record.implemented_surfaces + ("deterministic proposal receipts from policy decisions",)))),
                    forbidden_implications=tuple(sorted(set(record.forbidden_implications + ("proposal receipts are effects", "proposal receipt authorizes fulfillment",)))),
                    host_actuation_performed=False,
                    metadata_only=True,
                )
            )
        elif record.capability_id in {"direct_fan_pwm_thermal_control"}:
            records.append(replace(record, status="blocked", authority_level="none", host_actuation_performed=False))
        elif record.capability_id == "privilege_broker":
            records.append(record)
        elif record.capability_id == "actuation_fulfillment":
            records.append(replace(record, status="implemented", authority_level="rehearsal_only", host_actuation_performed=False))
        else:
            records.append(record)
    return replace(registry, records=tuple(records), schema_version="host-embodiment-substrate-phase5.v1")


def update_registry_from_builtin_runner_execution_receipt(registry: CapabilityRegistry, receipt: Any) -> CapabilityRegistry:
    """Reflect bounded built-in runner execution without widening runner authority."""

    payload = receipt.to_dict() if hasattr(receipt, "to_dict") else dict(receipt)
    action = payload.get("action_kind")
    records: list[CapabilityRecord] = []
    for record in registry.records:
        if record.capability_id == "builtin_local_effect_runner":
            records.append(replace(record, status="implemented", authority_level="bounded_in_process_runner", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id == "builtin_runner_local_diagnostic_artifact_write" and action == "local_diagnostic_artifact_write":
            records.append(replace(record, status="implemented", authority_level="builtin_runner_action_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id == "builtin_runner_exact_artifact_rollback" and action == "local_diagnostic_exact_rollback":
            records.append(replace(record, status="implemented", authority_level="builtin_runner_action_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id == "builtin_runner_workspace_scoped_file_update" and action == "workspace_scoped_file_update":
            records.append(replace(record, status="implemented", authority_level="builtin_runner_action_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id == "builtin_runner_workspace_file_exact_rollback" and action == "workspace_scoped_file_exact_rollback":
            records.append(replace(record, status="implemented", authority_level="builtin_runner_action_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id in {"general_runner_framework", "general_filesystem_runner", "generated_code_runner", "plugin_runner", "federation_import_runner", "subprocess_runner", "shell_runner", "network_runner", "provider_runner", "prompt_assembly_runner", "hardware_control_runner", "service_control_runner", "power_control_runner", "cleanup_runner"}:
            records.append(replace(record, status="deferred" if record.capability_id == "general_runner_framework" else "blocked", authority_level="none", host_actuation_performed=False, metadata_only=True))
        else:
            records.append(record)
    return replace(registry, records=tuple(records), schema_version="host-builtin-local-effect-runner-pilot-wing.v1")



def update_registry_from_builtin_runner_transaction_receipt(registry: CapabilityRegistry, receipt: Any) -> CapabilityRegistry:
    """Reflect bounded runner transaction orchestration without widening authority."""

    payload = receipt.to_dict() if hasattr(receipt, "to_dict") else dict(receipt)
    mode = payload.get("transaction_mode")
    records: list[CapabilityRecord] = []
    blocked_ids = {"general_runner_orchestration", "general_runner_framework", "generated_code_runner", "plugin_runner", "federation_import_runner", "subprocess_runner", "shell_runner", "network_runner", "provider_runner", "prompt_assembly_runner", "hardware_control_runner", "service_control_runner", "power_control_runner", "cleanup_runner"}
    for record in registry.records:
        if record.capability_id == "builtin_runner_transaction_orchestrator":
            records.append(replace(record, status="implemented", authority_level="bounded-orchestrator", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id == "builtin_runner_transaction_write_only" and mode in {"diagnostic_write_only", "diagnostic_write_with_ledger", "diagnostic_write_with_rollback", "diagnostic_write_rollback_with_ledger"}:
            records.append(replace(record, status="implemented", authority_level="bounded diagnostic write orchestration", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id == "builtin_runner_transaction_write_with_rollback" and mode in {"diagnostic_write_with_rollback", "diagnostic_write_rollback_with_ledger"}:
            records.append(replace(record, status="implemented", authority_level="bounded write/exact-rollback orchestration", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id == "builtin_runner_transaction_ledger_build" and payload.get("ledger_id"):
            records.append(replace(record, status="implemented", authority_level="explicit ledger build", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id in blocked_ids:
            records.append(replace(record, status="deferred" if record.capability_id in {"general_runner_orchestration", "general_runner_framework", "network_runner", "provider_runner", "prompt_assembly_runner", "hardware_control_runner", "service_control_runner", "power_control_runner", "cleanup_runner"} else "blocked", authority_level="none", host_actuation_performed=False, metadata_only=True))
        else:
            records.append(record)
    return replace(registry, records=tuple(records), schema_version="host-builtin-runner-transaction-orchestrator-wing.v1")

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



def update_registry_from_dry_run_execution_receipt(registry: CapabilityRegistry, receipt: Any) -> CapabilityRegistry:
    """Reflect a simulation-only dry-run receipt without claiming real effects."""

    records: list[CapabilityRecord] = []
    has_receipt = bool(getattr(receipt, "receipt_id", "")) or bool(isinstance(receipt, Mapping) and receipt.get("receipt_id"))
    for record in registry.records:
        if record.capability_id in {"dry_run_execution_harness", "dry_run_execution_result", "dry_run_execution_receipt"}:
            records.append(
                replace(
                    record,
                    status="implemented" if has_receipt else record.status,
                    authority_level="dry_run_receipt_only" if record.capability_id == "dry_run_execution_receipt" else "simulated_only",
                    source_paths=tuple(sorted(set(record.source_paths + ("sentientos/dry_run_execution_harness.py",)))),
                    proof_tests=tuple(sorted(set(record.proof_tests + ("tests/test_dry_run_execution_harness.py",)))),
                    implemented_surfaces=tuple(sorted(set(record.implemented_surfaces + ("simulation-only dry-run receipt posture",)))),
                    deferred_surfaces=tuple(sorted(set(record.deferred_surfaces + ("real backend invocation", "real fulfillment execution", "real effect execution", "host mutation")))),
                    forbidden_implications=tuple(sorted(set(record.forbidden_implications + ("dry-run receipt is real fulfillment", "dry-run receipt is proof of host mutation")))),
                    host_actuation_performed=False,
                    metadata_only=True,
                )
            )
        elif record.capability_id in {"real_backend_invocation", "fulfillment_execution", "real_effect_execution", "real_rollback_execution", "real_actuation_fulfillment"}:
            records.append(replace(record, status="deferred", authority_level="none", host_actuation_performed=False))
        elif record.capability_id in {"real_service_restart", "real_fan_pwm_control", "real_power_profile_mutation", "real_thermal_actuation", "real_file_cleanup", "direct_fan_pwm_thermal_control"}:
            records.append(replace(record, status="blocked", authority_level="none", host_actuation_performed=False))
        else:
            records.append(record)
    return replace(registry, records=tuple(records), schema_version="host-dry-run-execution-harness-wing.v1")



def update_registry_from_dry_run_audit_closure(registry: CapabilityRegistry, closure_wing: Any) -> CapabilityRegistry:
    """Reflect dry-run audit closure records without claiming real effects."""

    has_effect = bool(getattr(getattr(closure_wing, "effect_verification", None), "verification_id", "")) or bool(getattr(closure_wing, "verification_id", ""))
    has_post = bool(getattr(getattr(closure_wing, "postcondition_verification", None), "verification_id", "")) or bool(getattr(closure_wing, "postcondition_verification_id", ""))
    has_rollback = bool(getattr(getattr(closure_wing, "rollback_rehearsal", None), "rehearsal_id", "")) or bool(getattr(closure_wing, "rollback_rehearsal_id", ""))
    has_audit = bool(getattr(getattr(closure_wing, "audit_closure_receipt", None), "receipt_id", "")) or bool(getattr(closure_wing, "audit_closure_receipt_id", ""))
    has_bundle = bool(getattr(getattr(closure_wing, "closure_bundle", None), "bundle_id", "")) or bool(getattr(closure_wing, "bundle_id", ""))
    records: list[CapabilityRecord] = []
    for record in registry.records:
        if record.capability_id == "dry_run_effect_verification":
            records.append(replace(record, status="implemented" if has_effect else record.status, authority_level="dry_run_verification_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id == "dry_run_postcondition_verification":
            records.append(replace(record, status="implemented" if has_post else record.status, authority_level="dry_run_postcondition_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id == "dry_run_rollback_rehearsal":
            records.append(replace(record, status="implemented" if has_rollback else record.status, authority_level="dry_run_rollback_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id == "dry_run_audit_closure_receipt":
            records.append(replace(record, status="implemented" if has_audit else record.status, authority_level="dry_run_audit_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id == "dry_run_closure_bundle":
            records.append(replace(record, status="implemented" if has_bundle else record.status, authority_level="dry_run_closure_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id in {"real_effect_receipt_creation", "real_postcondition_check", "real_rollback_execution", "production_audit_receipt_for_host_effect", "fulfillment_execution", "real_effect_execution", "real_actuation_fulfillment"}:
            records.append(replace(record, status="deferred", authority_level="none", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id in {"real_fan_pwm_control", "real_thermal_actuation", "real_power_profile_mutation", "real_service_restart", "real_file_cleanup", "direct_fan_pwm_thermal_control"}:
            records.append(replace(record, status="blocked", authority_level="none", host_actuation_performed=False, metadata_only=True))
        else:
            records.append(record)
    return replace(registry, records=tuple(records), schema_version="host-dry-run-audit-closure-wing.v1")


def update_registry_from_local_diagnostic_effect_receipt(registry: CapabilityRegistry, receipt: Any) -> CapabilityRegistry:
    """Reflect the explicit Tier-1 local diagnostic effect without broadening host authority."""

    has_receipt = bool(getattr(receipt, "receipt_id", "")) or bool(isinstance(receipt, Mapping) and receipt.get("receipt_id"))
    records: list[CapabilityRecord] = []
    for record in registry.records:
        if record.capability_id in {"local_diagnostic_effect", "local_diagnostic_effect_receipt", "local_diagnostic_postcondition_check", "local_diagnostic_production_audit_receipt", "local_diagnostic_rollback_plan"}:
            records.append(
                replace(
                    record,
                    status="implemented" if has_receipt else record.status,
                    source_paths=tuple(sorted(set(record.source_paths + ("sentientos/local_diagnostic_effect.py", "scripts/run_local_diagnostic_effect.py")))),
                    proof_tests=tuple(sorted(set(record.proof_tests + ("tests/test_local_diagnostic_effect.py", "tests/test_run_local_diagnostic_effect_script.py")))),
                    implemented_surfaces=tuple(sorted(set(record.implemented_surfaces + ("Tier-1 explicit local diagnostic artifact effect",)))),
                    forbidden_implications=tuple(sorted(set(record.forbidden_implications + ("local diagnostic effect grants general host control",)))),
                    host_actuation_performed=False,
                    metadata_only=True,
                )
            )
        elif record.capability_id == "local_diagnostic_rollback_execution":
            records.append(replace(record, status="deferred", authority_level="none", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id in {"real_backend_implementation", "real_backend_invocation", "fulfillment_execution", "real_effect_execution", "real_fulfillment_execution"}:
            records.append(replace(record, status="deferred", authority_level="none", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id in {"real_fan_pwm_control", "real_thermal_actuation", "real_power_profile_mutation", "real_service_restart", "real_file_cleanup"}:
            records.append(replace(record, status="blocked", authority_level="none", host_actuation_performed=False, metadata_only=True))
        else:
            records.append(record)
    return replace(registry, records=tuple(records), schema_version="host-local-diagnostic-effect-pilot-wing.v1")

def update_registry_from_real_effect_admission(registry: CapabilityRegistry, admission_wing: Any) -> CapabilityRegistry:
    """Reflect real-effect admission planning without claiming implementation."""

    has_candidate = bool(getattr(getattr(admission_wing, "candidate", None), "candidate_id", "")) or bool(getattr(admission_wing, "candidate_id", ""))
    has_decision = bool(getattr(getattr(admission_wing, "decision", None), "decision_id", "")) or bool(getattr(admission_wing, "decision_id", ""))
    plan_or_block = getattr(admission_wing, "plan_or_block_receipt", None)
    has_plan = bool(getattr(plan_or_block, "plan_id", "")) or bool(getattr(admission_wing, "plan_id", ""))
    has_block = bool(getattr(plan_or_block, "receipt_id", "")) or bool(getattr(admission_wing, "block_receipt_id", ""))
    records: list[CapabilityRecord] = []
    for record in registry.records:
        if record.capability_id == "real_effect_capability_admission":
            records.append(replace(record, status="implemented" if has_decision else record.status, authority_level="admission_planning_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id == "real_effect_capability_candidate":
            records.append(replace(record, status="implemented" if has_candidate else record.status, authority_level="candidate_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id == "real_effect_implementation_plan_scaffold":
            records.append(replace(record, status="implemented" if has_plan else record.status, authority_level="plan_scaffold_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id == "real_effect_capability_block_receipt":
            records.append(replace(record, status="implemented" if has_block else record.status, authority_level="block_receipt_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id in {"real_backend_implementation", "real_backend_invocation", "fulfillment_execution", "real_effect_execution", "real_effect_receipt_creation", "real_postcondition_check", "real_rollback_execution", "production_audit_receipt_for_host_effect", "real_actuation_fulfillment"}:
            records.append(replace(record, status="deferred", authority_level="none", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id in {"real_fan_pwm_control", "real_thermal_actuation", "real_power_profile_mutation", "real_service_restart", "real_file_cleanup", "direct_fan_pwm_thermal_control"}:
            records.append(replace(record, status="blocked", authority_level="none", host_actuation_performed=False, metadata_only=True))
        else:
            records.append(record)
    return replace(registry, records=tuple(records), schema_version="host-real-effect-capability-admission-wing.v1")

def update_registry_from_actuation_fulfillment_plan(registry: CapabilityRegistry, plan: Any) -> CapabilityRegistry:
    """Reflect a Phase 5 rehearsal plan without claiming real fulfillment."""

    records: list[CapabilityRecord] = []
    has_plan = bool(getattr(plan, "plan_id", ""))
    for record in registry.records:
        if record.capability_id == "actuation_fulfillment":
            records.append(
                replace(
                    record,
                    status="implemented" if has_plan else "scaffolded",
                    authority_level="rehearsal_only",
                    source_paths=tuple(sorted(set(record.source_paths + ("sentientos/actuation_fulfillment.py", "sentientos/privilege_broker.py")))),
                    proof_tests=tuple(sorted(set(record.proof_tests + ("tests/test_actuation_fulfillment.py",)))),
                    implemented_surfaces=tuple(sorted(set(record.implemented_surfaces + ("dry-run fulfillment rehearsal planning",)))),
                    deferred_surfaces=tuple(sorted(set(record.deferred_surfaces + ("real actuation fulfillment", "host mutation", "effect receipt issuance", "fan/PWM writes", "thermal actuation", "service restart", "cleanup mutation", "power profile mutation")))),
                    forbidden_implications=tuple(sorted(set(record.forbidden_implications + ("fulfillment rehearsal is real fulfillment", "plan is authorization")))),
                    host_actuation_performed=False,
                    metadata_only=True,
                )
            )
        elif record.capability_id == "real_actuation_fulfillment":
            records.append(replace(record, status="deferred", authority_level="none", host_actuation_performed=False))
        elif record.capability_id == "direct_fan_pwm_thermal_control":
            records.append(replace(record, status="blocked", authority_level="none", host_actuation_performed=False))
        else:
            records.append(record)
    return replace(registry, records=tuple(records), schema_version="host-embodiment-substrate-phase5.v1")


def update_registry_from_actuation_rehearsal_receipt(registry: CapabilityRegistry, receipt: Any) -> CapabilityRegistry:
    """Reflect a Phase 5 rehearsal receipt while keeping real host actuation deferred."""

    updated = update_registry_from_actuation_fulfillment_plan(registry, receipt)
    records: list[CapabilityRecord] = []
    has_receipt = bool(getattr(receipt, "receipt_id", ""))
    for record in updated.records:
        if record.capability_id == "actuation_fulfillment":
            records.append(
                replace(
                    record,
                    status="implemented" if has_receipt else record.status,
                    authority_level="rehearsal_only",
                    implemented_surfaces=tuple(sorted(set(record.implemented_surfaces + ("non-effect fulfillment rehearsal receipts",)))),
                    forbidden_implications=tuple(sorted(set(record.forbidden_implications + ("rehearsal receipt is effect receipt",)))),
                    host_actuation_performed=False,
                    metadata_only=True,
                )
            )
        else:
            records.append(record)
    return replace(updated, records=tuple(records), schema_version="host-embodiment-substrate-phase5.v1")

def update_registry_from_privilege_broker_decision(registry: CapabilityRegistry, decision: Any, review_receipts: Sequence[Any] = ()) -> CapabilityRegistry:
    """Reflect Phase 4 broker eligibility without claiming fulfillment."""

    records: list[CapabilityRecord] = []
    has_decision = bool(getattr(decision, "decision_id", ""))
    has_receipts = bool(review_receipts)
    for record in registry.records:
        if record.capability_id == "privilege_broker":
            records.append(
                replace(
                    record,
                    status="implemented" if has_decision else "scaffolded",
                    authority_level="eligibility_only",
                    source_paths=tuple(sorted(set(record.source_paths + ("sentientos/privilege_broker.py", "sentientos/host_resource_policy.py")))),
                    proof_tests=tuple(sorted(set(record.proof_tests + ("tests/test_privilege_broker.py",)))),
                    implemented_surfaces=tuple(sorted(set(record.implemented_surfaces + ("proposal receipt eligibility classification", "non-effect broker review receipts" if has_receipts else "broker eligibility scaffold")))),
                    deferred_surfaces=tuple(sorted(set(record.deferred_surfaces + ("Actuation Fulfillment Layer", "authorization", "host mutation", "fan/PWM writes", "thermal actuation", "service restart", "cleanup mutation", "power profile mutation")))),
                    forbidden_implications=tuple(sorted(set(record.forbidden_implications + ("eligibility decision is authorization", "broker receipt is fulfillment")))),
                    host_actuation_performed=False,
                    metadata_only=True,
                )
            )
        elif record.capability_id == "actuation_fulfillment":
            records.append(replace(record, status="implemented", authority_level="rehearsal_only", host_actuation_performed=False))
        elif record.capability_id == "direct_fan_pwm_thermal_control":
            records.append(replace(record, status="blocked", authority_level="none", host_actuation_performed=False))
        else:
            records.append(record)
    return replace(registry, records=tuple(records), schema_version="host-embodiment-substrate-phase5.v1")


def update_registry_from_execution_readiness_manifest(registry: CapabilityRegistry, manifest: Any) -> CapabilityRegistry:
    """Reflect execution proof readiness without claiming authorization or effects."""

    records: list[CapabilityRecord] = []
    has_manifest = bool(getattr(manifest, "manifest_id", ""))
    for record in registry.records:
        if record.capability_id in {"effect_receipt_contract", "postcondition_checks", "rollback_planning"}:
            records.append(
                replace(
                    record,
                    status="implemented" if has_manifest else record.status,
                    authority_level="proof_only",
                    source_paths=tuple(sorted(set(record.source_paths + ("sentientos/effect_proof.py",)))),
                    proof_tests=tuple(sorted(set(record.proof_tests + ("tests/test_effect_proof.py",)))),
                    host_actuation_performed=False,
                    metadata_only=True,
                )
            )
        elif record.capability_id == "execution_readiness_manifest":
            records.append(
                replace(
                    record,
                    status="implemented" if has_manifest else "scaffolded",
                    authority_level="readiness_only",
                    source_paths=tuple(sorted(set(record.source_paths + ("sentientos/effect_proof.py",)))),
                    proof_tests=tuple(sorted(set(record.proof_tests + ("tests/test_effect_proof.py",)))),
                    implemented_surfaces=tuple(sorted(set(record.implemented_surfaces + ("execution readiness manifests are not authorization",)))),
                    deferred_surfaces=tuple(sorted(set(record.deferred_surfaces + ("real effect execution", "real rollback execution")))),
                    forbidden_implications=tuple(sorted(set(record.forbidden_implications + ("readiness manifest grants fulfillment",)))) ,
                    host_actuation_performed=False,
                    metadata_only=True,
                )
            )
        elif record.capability_id in {"real_effect_execution", "real_rollback_execution", "real_service_restart", "real_fan_pwm_control", "real_power_profile_mutation", "real_file_cleanup", "direct_fan_pwm_thermal_control", "real_actuation_fulfillment"}:
            records.append(replace(record, status="blocked" if record.capability_id not in {"real_effect_execution", "real_rollback_execution", "real_actuation_fulfillment"} else "deferred", authority_level="none", host_actuation_performed=False))
        else:
            records.append(record)
    return replace(registry, records=tuple(records), schema_version="host-embodiment-execution-proof-wing.v1")


def update_registry_from_authorization_review_decision(registry: CapabilityRegistry, decision: Any) -> CapabilityRegistry:
    """Reflect authorization review eligibility without granting authorization."""

    records: list[CapabilityRecord] = []
    has_decision = bool(getattr(decision, "decision_id", ""))
    for record in registry.records:
        if record.capability_id == "authorization_review":
            records.append(
                replace(
                    record,
                    status="implemented" if has_decision else "scaffolded",
                    authority_level="review_only",
                    source_paths=tuple(sorted(set(record.source_paths + ("sentientos/authorization_review.py",)))),
                    proof_tests=tuple(sorted(set(record.proof_tests + ("tests/test_authorization_review.py",)))),
                    implemented_surfaces=tuple(sorted(set(record.implemented_surfaces + ("authorization review decision is not authorization",)))),
                    deferred_surfaces=tuple(sorted(set(record.deferred_surfaces + ("real authorization grant", "real effect execution", "real rollback execution")))),
                    forbidden_implications=tuple(sorted(set(record.forbidden_implications + ("authorization review decision grants authorization",)))),
                    host_actuation_performed=False,
                    metadata_only=True,
                )
            )
        elif record.capability_id in {"real_authorization_grant", "real_effect_execution", "real_rollback_execution", "real_actuation_fulfillment"}:
            records.append(replace(record, status="deferred", authority_level="none", host_actuation_performed=False))
        elif record.capability_id in {"real_service_restart", "real_fan_pwm_control", "real_power_profile_mutation", "real_file_cleanup", "direct_fan_pwm_thermal_control"}:
            records.append(replace(record, status="blocked", authority_level="none", host_actuation_performed=False))
        else:
            records.append(record)
    return replace(registry, records=tuple(records), schema_version="host-embodiment-authorization-review-wing.v1")


def update_registry_from_future_authorization_schema(registry: CapabilityRegistry, schema: Any) -> CapabilityRegistry:
    """Reflect the future grant schema placeholder without creating a grant."""

    updated = registry
    records: list[CapabilityRecord] = []
    has_schema = bool(getattr(schema, "schema_id", ""))
    for record in updated.records:
        if record.capability_id == "future_authorization_grant_schema":
            records.append(
                replace(
                    record,
                    status="implemented" if has_schema else "scaffolded",
                    authority_level="schema_only",
                    source_paths=tuple(sorted(set(record.source_paths + ("sentientos/authorization_review.py",)))),
                    proof_tests=tuple(sorted(set(record.proof_tests + ("tests/test_authorization_review.py",)))),
                    implemented_surfaces=tuple(sorted(set(record.implemented_surfaces + ("schema-only future authorization grant placeholder",)))),
                    forbidden_implications=tuple(sorted(set(record.forbidden_implications + ("future authorization grant schema is a real grant",)))),
                    host_actuation_performed=False,
                    metadata_only=True,
                )
            )
        else:
            records.append(record)
    return replace(updated, records=tuple(records), schema_version="host-embodiment-authorization-review-wing.v1")


def update_registry_from_runtime_supervisor_report(registry: CapabilityRegistry, report: Any) -> CapabilityRegistry:
    """Reflect runtime supervisor readiness without restart/kill authority."""

    records: list[CapabilityRecord] = []
    has_report = bool(getattr(report, "report_id", ""))
    for record in registry.records:
        if record.capability_id == "runtime_supervisor":
            records.append(
                replace(
                    record,
                    status="implemented" if has_report else "scaffolded",
                    authority_level="telemetry_readiness_only",
                    source_paths=tuple(sorted(set(record.source_paths + ("sentientos/runtime_supervisor.py",)))),
                    proof_tests=tuple(sorted(set(record.proof_tests + ("tests/test_runtime_supervisor.py",)))),
                    implemented_surfaces=tuple(sorted(set(record.implemented_surfaces + ("runtime supervisor readiness reports do not restart or kill services",)))) ,
                    deferred_surfaces=tuple(sorted(set(record.deferred_surfaces + ("real service restart", "real process kill")))),
                    host_actuation_performed=False,
                    metadata_only=True,
                )
            )
        elif record.capability_id == "real_service_restart":
            records.append(replace(record, status="blocked", authority_level="none", host_actuation_performed=False))
        else:
            records.append(record)
    return replace(registry, records=tuple(records), schema_version="host-embodiment-execution-proof-wing.v1")


def update_registry_from_controlled_authorization_ledger(registry: CapabilityRegistry, ledger: Any) -> CapabilityRegistry:
    """Reflect controlled authorization records without creating live authority."""

    records: list[CapabilityRecord] = []
    has_ledger = bool(getattr(ledger, "ledger_id", "") or getattr(ledger, "source_id", ""))
    for record in registry.records:
        if record.capability_id == "controlled_authorization_contract":
            records.append(replace(record, status="implemented", authority_level="contract_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id == "controlled_authorization_grant_record":
            records.append(replace(record, status="implemented", authority_level="schema_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id == "controlled_authorization_ledger":
            records.append(
                replace(
                    record,
                    status="implemented" if has_ledger else "scaffolded",
                    authority_level="ledger_only",
                    source_paths=tuple(sorted(set(record.source_paths + ("sentientos/controlled_authorization.py",)))),
                    proof_tests=tuple(sorted(set(record.proof_tests + ("tests/test_controlled_authorization.py",)))),
                    implemented_surfaces=tuple(sorted(set(record.implemented_surfaces + ("metadata-only controlled authorization ledger",)))),
                    forbidden_implications=tuple(sorted(set(record.forbidden_implications + ("controlled authorization ledger grants live authority",)))),
                    host_actuation_performed=False,
                    metadata_only=True,
                )
            )
        elif record.capability_id in {"live_authorization_grant", "real_authorization_grant", "real_effect_execution", "real_rollback_execution", "real_actuation_fulfillment"}:
            records.append(replace(record, status="deferred", authority_level="none", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id in {"real_service_restart", "real_fan_pwm_control", "real_power_profile_mutation", "real_file_cleanup", "direct_fan_pwm_thermal_control"}:
            records.append(replace(record, status="blocked", authority_level="none", host_actuation_performed=False, metadata_only=True))
        else:
            records.append(record)
    return replace(registry, records=tuple(records), schema_version="host-embodiment-controlled-authorization-and-trace-wing.v1")


def update_registry_from_host_embodiment_trace(registry: CapabilityRegistry, trace: Any) -> CapabilityRegistry:
    """Reflect reviewer demo trace proof without granting authorization or effects."""

    records: list[CapabilityRecord] = []
    has_trace = bool(getattr(trace, "trace_id", ""))
    for record in registry.records:
        if record.capability_id == "host_embodiment_trace":
            records.append(
                replace(
                    record,
                    status="implemented" if has_trace else "scaffolded",
                    authority_level="demo_proof_only",
                    source_paths=tuple(sorted(set(record.source_paths + ("sentientos/host_embodiment_trace.py",)))),
                    proof_tests=tuple(sorted(set(record.proof_tests + ("tests/test_host_embodiment_trace.py",)))),
                    implemented_surfaces=tuple(sorted(set(record.implemented_surfaces + ("full non-mutating reviewer trace artifact",)))),
                    deferred_surfaces=tuple(sorted(set(record.deferred_surfaces + ("live authorization grant", "real effect execution", "real rollback execution")))),
                    forbidden_implications=tuple(sorted(set(record.forbidden_implications + ("host embodiment trace grants live authorization", "trace performs effects")))),
                    host_actuation_performed=False,
                    metadata_only=True,
                )
            )
        elif record.capability_id in {"live_authorization_grant", "real_authorization_grant", "real_effect_execution", "real_rollback_execution", "real_actuation_fulfillment"}:
            records.append(replace(record, status="deferred", authority_level="none", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id in {"real_service_restart", "real_fan_pwm_control", "real_power_profile_mutation", "real_file_cleanup", "direct_fan_pwm_thermal_control"}:
            records.append(replace(record, status="blocked", authority_level="none", host_actuation_performed=False, metadata_only=True))
        else:
            records.append(record)
    return replace(registry, records=tuple(records), schema_version="host-embodiment-controlled-authorization-and-trace-wing.v1")


def update_registry_from_trace_export(registry: CapabilityRegistry, trace: Any) -> CapabilityRegistry:
    """Reflect trace export/demo proof without live collection or authority."""

    records: list[CapabilityRecord] = []
    has_trace = bool(getattr(trace, "trace_id", ""))
    for record in registry.records:
        if record.capability_id == "host_embodiment_trace_export":
            records.append(
                replace(
                    record,
                    status="implemented" if has_trace else "scaffolded",
                    authority_level="demo_proof_only",
                    source_paths=tuple(sorted(set(record.source_paths + ("sentientos/host_embodiment_trace_export.py",)))),
                    proof_tests=tuple(sorted(set(record.proof_tests + ("tests/test_host_embodiment_trace_export.py",)))),
                    implemented_surfaces=tuple(sorted(set(record.implemented_surfaces + ("deterministic reviewer trace export",)))),
                    forbidden_implications=tuple(sorted(set(record.forbidden_implications + ("trace export grants live authorization", "trace export performs host mutation")))),
                    host_actuation_performed=False,
                    metadata_only=True,
                )
            )
        elif record.capability_id == "reviewer_demo_trace":
            records.append(replace(record, status="implemented" if has_trace else "scaffolded", authority_level="demo_proof_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id == "live_host_trace_collection":
            records.append(replace(record, status="deferred", authority_level="none", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id in {"live_authorization_grant", "real_authorization_grant", "real_effect_execution", "real_rollback_execution", "real_actuation_fulfillment"}:
            records.append(replace(record, status="deferred", authority_level="none", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id in {"real_service_restart", "real_fan_pwm_control", "real_power_profile_mutation", "real_file_cleanup", "direct_fan_pwm_thermal_control"}:
            records.append(replace(record, status="blocked", authority_level="none", host_actuation_performed=False, metadata_only=True))
        else:
            records.append(record)
    return replace(registry, records=tuple(records), schema_version="host-embodiment-reviewer-demo-trace.v1")


def update_registry_from_safety_gate_manifest(registry: CapabilityRegistry, manifest: Any) -> CapabilityRegistry:
    """Reflect metadata-only safety gate posture without claiming authorization."""

    has_manifest = bool(getattr(manifest, "manifest_id", ""))
    records: list[CapabilityRecord] = []
    for record in registry.records:
        if record.capability_id == "host_actuation_safety_gates":
            records.append(replace(record, status="implemented" if has_manifest else record.status, authority_level="metadata_proof_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id in {"live_authorization_grant", "real_effect_execution"}:
            records.append(replace(record, status="deferred", authority_level="none", host_actuation_performed=False))
        elif record.capability_id in {"real_fan_pwm_control", "real_thermal_actuation", "real_power_profile_mutation", "real_service_restart", "real_file_cleanup"}:
            records.append(replace(record, status="blocked", authority_level="none", host_actuation_performed=False))
        else:
            records.append(record)
    return replace(registry, records=tuple(records), schema_version="host-actuation-safety-gate-wing.v1")


def update_registry_from_live_grant_readiness(registry: CapabilityRegistry, readiness_wing: Any) -> CapabilityRegistry:
    """Reflect live-grant readiness/preflight records without granting authority."""

    has_matrix = bool(getattr(getattr(readiness_wing, "prerequisite_matrix", None), "matrix_id", ""))
    records: list[CapabilityRecord] = []
    for record in registry.records:
        if record.capability_id == "live_grant_readiness":
            records.append(replace(record, status="implemented" if has_matrix else record.status, authority_level="readiness_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id == "live_grant_prerequisite_matrix":
            records.append(replace(record, status="implemented" if has_matrix else record.status, authority_level="metadata_proof_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id == "operator_policy_approval_packet":
            records.append(replace(record, status="implemented", authority_level="packet_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id == "grant_issue_preflight_receipt":
            records.append(replace(record, status="implemented", authority_level="preflight_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id == "grant_denial_deferral_receipt":
            records.append(replace(record, status="implemented", authority_level="denial_deferral_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id in {"live_authorization_grant", "real_authorization_grant", "real_effect_execution", "real_actuation_fulfillment"}:
            records.append(replace(record, status="deferred", authority_level="none", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id in {"real_fan_pwm_control", "real_thermal_actuation", "real_power_profile_mutation", "real_service_restart", "real_file_cleanup", "direct_fan_pwm_thermal_control"}:
            records.append(replace(record, status="blocked", authority_level="none", host_actuation_performed=False, metadata_only=True))
        else:
            records.append(record)
    return replace(registry, records=tuple(records), schema_version="host-live-grant-readiness-wing.v1")



def update_registry_from_fulfillment_authorization_consumption(registry: CapabilityRegistry, wing: Any) -> CapabilityRegistry:
    """Reflect metadata-only fulfillment authorization consumption without execution."""

    has_request = bool(getattr(getattr(wing, "request", None), "request_id", "")) or bool(getattr(wing, "request_id", ""))
    has_verification = bool(getattr(getattr(wing, "grant_consumption_verification", None), "verification_id", "")) or bool(getattr(wing, "verification_id", ""))
    has_assessment = bool(getattr(getattr(wing, "scope_match_assessment", None), "assessment_id", "")) or bool(getattr(wing, "assessment_id", ""))
    has_consumption = bool(getattr(getattr(wing, "consumption_receipt", None), "receipt_id", "")) or bool(getattr(wing, "receipt_id", ""))
    has_denial = bool(getattr(getattr(wing, "denial_receipt", None), "receipt_id", ""))
    records: list[CapabilityRecord] = []
    for record in registry.records:
        if record.capability_id == "fulfillment_authorization_request":
            records.append(replace(record, status="implemented" if has_request else record.status, authority_level="request_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id == "grant_consumption_verification":
            records.append(replace(record, status="implemented" if has_verification else record.status, authority_level="verification_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id == "fulfillment_scope_match_assessment":
            records.append(replace(record, status="implemented" if has_assessment else record.status, authority_level="assessment_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id in {"fulfillment_authorization_consumption", "fulfillment_authorization_consumption_receipt"}:
            records.append(replace(record, status="implemented" if has_consumption else record.status, authority_level="consumption_receipt_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id == "fulfillment_authorization_denial_receipt":
            records.append(replace(record, status="implemented" if (has_denial or not has_consumption) else record.status, authority_level="denial_receipt_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id in {"fulfillment_execution", "real_effect_execution", "real_actuation_fulfillment"}:
            records.append(replace(record, status="deferred", authority_level="none", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id in {"real_fan_pwm_control", "real_thermal_actuation", "real_power_profile_mutation", "real_service_restart", "real_file_cleanup", "direct_fan_pwm_thermal_control"}:
            records.append(replace(record, status="blocked", authority_level="none", host_actuation_performed=False, metadata_only=True))
        else:
            records.append(record)
    return replace(registry, records=tuple(records), schema_version="host-fulfillment-authorization-consumption-wing.v1")

def update_registry_from_local_authorization_ledger(registry: CapabilityRegistry, ledger: Any) -> CapabilityRegistry:
    """Reflect local authorization grant records without claiming fulfillment."""

    has_ledger = bool(getattr(ledger, "ledger_id", "")) or (isinstance(ledger, Mapping) and bool(ledger.get("ledger_id")))
    records: list[CapabilityRecord] = []
    for record in registry.records:
        if record.capability_id == "local_authorization_grant":
            records.append(replace(record, status="implemented" if has_ledger else record.status, authority_level="local_authorization_record_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id == "local_authorization_grant_ledger":
            records.append(replace(record, status="implemented" if has_ledger else record.status, authority_level="authorization_ledger_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id == "local_authorization_revocation_receipt":
            records.append(replace(record, status="implemented", authority_level="revocation_record_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id == "local_authorization_expiry_evaluation":
            records.append(replace(record, status="implemented", authority_level="expiry_evaluation_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id == "local_authorization_verification":
            records.append(replace(record, status="implemented", authority_level="verification_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id in {"fulfillment_authorization_consumption", "fulfillment_authorization_request", "grant_consumption_verification", "fulfillment_scope_match_assessment", "fulfillment_authorization_consumption_receipt", "fulfillment_authorization_denial_receipt"}:
            records.append(replace(record, status="implemented", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id in {"fulfillment_execution", "real_authorization_grant", "real_effect_execution", "real_actuation_fulfillment"}:
            records.append(replace(record, status="deferred", authority_level="none", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id in {"real_fan_pwm_control", "real_thermal_actuation", "real_power_profile_mutation", "real_service_restart", "real_file_cleanup", "direct_fan_pwm_thermal_control"}:
            records.append(replace(record, status="blocked", authority_level="none", host_actuation_performed=False, metadata_only=True))
        else:
            records.append(record)
    return replace(registry, records=tuple(records), schema_version="host-local-authorization-grant-wing.v1")


def update_registry_from_executor_contract_readiness(registry: CapabilityRegistry, readiness_wing: Any) -> CapabilityRegistry:
    """Reflect executor contract readiness without implementing execution."""

    has_contract = bool(getattr(getattr(readiness_wing, "contract", None), "contract_id", "")) or bool(getattr(readiness_wing, "contract_id", ""))
    has_backend = bool(getattr(getattr(readiness_wing, "backend_declaration", None), "declaration_id", "")) or bool(getattr(readiness_wing, "backend_declaration_id", ""))
    has_manifest = bool(getattr(getattr(readiness_wing, "precondition_manifest", None), "manifest_id", "")) or bool(getattr(readiness_wing, "precondition_manifest_id", ""))
    has_plan = bool(getattr(getattr(readiness_wing, "dry_run_plan", None), "plan_id", "")) or bool(getattr(readiness_wing, "dry_run_plan_id", ""))
    has_packet = bool(getattr(getattr(readiness_wing, "admission_packet", None), "packet_id", "")) or bool(getattr(readiness_wing, "admission_packet_id", ""))
    has_receipt = bool(getattr(getattr(readiness_wing, "readiness_receipt", None), "receipt_id", "")) or bool(getattr(readiness_wing, "receipt_id", ""))
    records: list[CapabilityRecord] = []
    for record in registry.records:
        if record.capability_id == "fulfillment_executor_contract":
            records.append(replace(record, status="implemented" if has_contract else record.status, authority_level="contract_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id == "executor_backend_declaration":
            records.append(replace(record, status="implemented" if has_backend else record.status, authority_level="declaration_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id == "executor_precondition_manifest":
            records.append(replace(record, status="implemented" if has_manifest else record.status, authority_level="precondition_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id == "executor_dry_run_plan":
            records.append(replace(record, status="implemented" if has_plan else record.status, authority_level="plan_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id == "executor_admission_packet":
            records.append(replace(record, status="implemented" if has_packet else record.status, authority_level="packet_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id == "executor_contract_readiness_receipt":
            records.append(replace(record, status="implemented" if has_receipt else record.status, authority_level="readiness_receipt_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id in {"executor_implementation", "backend_invocation", "control_plane_admission_for_fulfillment", "fulfillment_execution", "real_effect_execution", "real_actuation_fulfillment"}:
            records.append(replace(record, status="deferred", authority_level="none", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id in {"real_fan_pwm_control", "real_thermal_actuation", "real_power_profile_mutation", "real_service_restart", "real_file_cleanup", "direct_fan_pwm_thermal_control"}:
            records.append(replace(record, status="blocked", authority_level="none", host_actuation_performed=False, metadata_only=True))
        else:
            records.append(record)
    return replace(registry, records=tuple(records), schema_version="host-fulfillment-executor-contract-wing.v1")


def update_registry_from_local_diagnostic_rollback_receipt(registry: CapabilityRegistry, receipt: Any) -> CapabilityRegistry:
    """Reflect exact local diagnostic artifact rollback without widening cleanup authority."""

    payload = receipt.to_dict() if hasattr(receipt, "to_dict") else dict(receipt)
    performed = bool(payload.get("real_rollback_performed")) and bool(payload.get("exact_artifact_only"))
    records: list[CapabilityRecord] = []
    for record in registry.records:
        if record.capability_id == "local_diagnostic_exact_rollback":
            records.append(replace(record, status="implemented", authority_level="exact_artifact_rollback_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id == "local_diagnostic_rollback_postcondition_check":
            records.append(replace(record, status="implemented", authority_level="exact_artifact_postcondition_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id == "local_diagnostic_rollback_audit_receipt":
            records.append(replace(record, status="implemented", authority_level="exact_artifact_rollback_audit_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id in {"real_file_cleanup", "real_fan_pwm_control", "real_thermal_actuation", "real_power_profile_mutation", "real_service_restart", "provider_invocation", "federation_transport_sync_adoption"}:
            records.append(replace(record, status="blocked", authority_level="none", host_actuation_performed=False))
        else:
            records.append(record)
    return replace(registry, records=tuple(records), schema_version="host-local-diagnostic-exact-rollback-wing.v1")


def update_registry_from_local_effect_transaction_ledger(registry: CapabilityRegistry, ledger: Any) -> CapabilityRegistry:
    """Reflect the metadata-only local effect transaction ledger without widening host authority."""

    payload = ledger.to_dict() if hasattr(ledger, "to_dict") else dict(ledger)
    has_ledger = bool(payload.get("ledger_id"))
    records: list[CapabilityRecord] = []
    for record in registry.records:
        if record.capability_id == "local_effect_transaction_ledger":
            records.append(replace(record, status="implemented" if has_ledger else record.status, authority_level="local_effect_transaction_ledger_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id == "local_effect_lifecycle_report":
            records.append(replace(record, status="implemented", authority_level="local_effect_lifecycle_report_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id == "local_effect_transaction_ledger_artifact":
            records.append(replace(record, status="implemented", authority_level="explicit_local_artifact_only", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id == "general_effect_transaction_ledger":
            records.append(replace(record, status="deferred", authority_level="none", host_actuation_performed=False, metadata_only=True))
        elif record.capability_id in {"general_cleanup", "recursive_delete", "unrelated_file_delete", "real_file_cleanup", "real_fan_pwm_control", "real_thermal_actuation", "real_power_profile_mutation", "real_service_restart", "package_install", "driver_install", "network_egress", "provider_invocation", "prompt_assembly", "federation_transport_sync_adoption", "remote_execution"}:
            records.append(replace(record, status="blocked", authority_level="none", host_actuation_performed=False, metadata_only=True))
        else:
            records.append(record)
    return replace(registry, records=tuple(records), schema_version="host-local-effect-transaction-ledger-wing.v1")


def update_registry_from_workspace_file_effect_receipt(registry: CapabilityRegistry, receipt: Any) -> CapabilityRegistry:
    """Reflect the explicit workspace-scoped file effect without broadening filesystem authority."""

    payload = receipt.to_dict() if hasattr(receipt, "to_dict") else dict(receipt)
    has_receipt = bool(payload.get("receipt_id")) and bool(payload.get("workspace_scoped")) and bool(payload.get("single_target_only"))
    records: list[CapabilityRecord] = []
    implemented_ids = {"workspace_scoped_file_effect", "workspace_file_preimage_capture", "workspace_file_postcondition_check", "workspace_file_exact_rollback", "workspace_file_production_audit"}
    blocked_ids = {"general_filesystem_access", "general_cleanup", "recursive_delete", "wildcard_delete", "unrelated_file_delete", "real_file_cleanup", "real_fan_pwm_control", "real_thermal_actuation", "real_power_profile_mutation", "real_service_restart", "package_install", "driver_install", "network_egress", "provider_invocation", "prompt_assembly", "federation_transport_sync_adoption", "remote_execution", "subprocess_runner", "shell_runner", "real_subprocess_runner"}
    for record in registry.records:
        if record.capability_id in implemented_ids:
            records.append(replace(record, status="implemented" if has_receipt else record.status, host_actuation_performed=False, metadata_only=True))
        elif record.capability_id in blocked_ids:
            records.append(replace(record, status="blocked", authority_level="none", host_actuation_performed=False, metadata_only=True))
        else:
            records.append(record)
    return replace(registry, records=tuple(records), schema_version="host-workspace-file-effect-pilot-wing.v1")

def update_registry_from_workspace_file_transaction_ledger(registry: CapabilityRegistry, ledger: Any) -> CapabilityRegistry:
    """Reflect metadata-only workspace file transaction ledgers without widening file authority."""

    payload = ledger.to_dict() if hasattr(ledger, "to_dict") else dict(ledger)
    has_ledger = bool(payload.get("ledger_id"))
    implemented_ids = {"workspace_file_transaction_ledger", "workspace_file_lifecycle_report", "workspace_file_transaction_ledger_artifact"}
    blocked_ids = {"general_filesystem_runner", "general_filesystem_access", "general_cleanup", "recursive_delete", "wildcard_delete", "unrelated_file_delete", "network_egress", "provider_invocation", "prompt_assembly", "subprocess_runner", "shell_runner"}
    records: list[CapabilityRecord] = []
    for record in registry.records:
        if record.capability_id in implemented_ids:
            records.append(replace(record, status="implemented" if has_ledger else record.status, host_actuation_performed=False, metadata_only=True))
        elif record.capability_id in blocked_ids:
            records.append(replace(record, status="blocked", authority_level="none", host_actuation_performed=False, metadata_only=True))
        else:
            records.append(record)
    return replace(registry, records=tuple(records), schema_version="host-workspace-file-runner-transaction-wing.v1")

def update_registry_from_host_steward_boundary(registry: CapabilityRegistry, wing: Any) -> CapabilityRegistry:
    """Reflect metadata-only host steward boundary records without adding runner execution."""

    payload = wing.to_dict() if hasattr(wing, "to_dict") else dict(wing)
    has_profile = bool(payload.get("host_steward_profile"))
    boundary_ids = {
        "host_steward_authority_profile",
        "delegated_runner_boundary_profile",
        "execution_containment_profile",
        "backend_adapter_authority_declaration",
        "runner_capability_grant_scaffold",
        "runner_boundary_assessment",
        "runner_boundary_violation_receipt",
    }
    blocked_runner_ids = {
        "live_runner_execution",
        "real_subprocess_runner",
        "shell_runner",
        "network_runner",
        "provider_runner",
        "prompt_assembly_runner",
        "hardware_control_runner",
        "service_control_runner",
        "power_control_runner",
        "cleanup_runner",
        "real_fan_pwm_control",
        "real_thermal_actuation",
    }
    records: list[CapabilityRecord] = []
    for record in registry.records:
        if record.capability_id in boundary_ids:
            records.append(replace(record, status="implemented" if has_profile else record.status, host_actuation_performed=False, metadata_only=True))
        elif record.capability_id in blocked_runner_ids:
            records.append(replace(record, status="deferred" if record.capability_id == "live_runner_execution" else "blocked", authority_level="none", host_actuation_performed=False, metadata_only=True))
        else:
            records.append(record)
    return replace(registry, records=tuple(records), schema_version="host-steward-delegated-runner-boundary-wing.v1")
