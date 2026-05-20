"""Reviewer first-run proof bundle for non-mutating host embodiment.

This module builds deterministic, metadata-only bundle payloads from existing
reviewer proof surfaces. It does not collect live host data by default, open
network egress, invoke providers, assemble prompts, grant authorization, execute
host actions, or mutate host state except for writing explicit caller-requested
bundle files.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from sentientos.capability_registry import build_default_capability_registry, summarize_capability_registry
from sentientos.host_embodiment_trace import build_host_embodiment_demo_trace, summarize_host_embodiment_trace
from sentientos.host_actuation_safety import build_safety_gates_for_domain, summarize_safety_gate_satisfaction_manifest
from sentientos.live_grant_readiness import (
    build_live_grant_readiness_wing,
    summarize_grant_denial_deferral_receipt,
    summarize_grant_issue_preflight_receipt,
    summarize_live_grant_prerequisite_matrix,
    summarize_operator_policy_approval_packet,
)
from sentientos.fulfillment_authorization import (
    build_fulfillment_authorization_wing,
    summarize_fulfillment_authorization_consumption_receipt,
    summarize_fulfillment_authorization_denial_receipt,
    summarize_fulfillment_authorization_request,
    summarize_fulfillment_scope_match_assessment,
    summarize_grant_consumption_verification,
)
from sentientos.fulfillment_executor_contract import (
    build_fulfillment_executor_contract_wing,
    summarize_executor_admission_packet,
    summarize_executor_backend_declaration,
    summarize_executor_contract_readiness_receipt,
    summarize_executor_dry_run_plan,
    summarize_executor_precondition_manifest,
    summarize_fulfillment_executor_contract,
)
from sentientos.dry_run_execution_harness import (
    build_dry_run_execution_harness_wing,
    summarize_dry_run_execution_block_receipt,
    summarize_dry_run_execution_receipt,
    summarize_dry_run_execution_request,
    summarize_dry_run_execution_result,
    summarize_simulated_backend_registry,
)

from sentientos.dry_run_audit_closure import (
    build_dry_run_audit_closure_wing,
    summarize_dry_run_audit_closure_receipt,
    summarize_dry_run_closure_bundle,
    summarize_dry_run_effect_verification,
    summarize_dry_run_postcondition_verification,
    summarize_dry_run_rollback_rehearsal,
)
from sentientos.real_effect_admission import (
    build_real_effect_admission_wing,
    summarize_real_effect_admission_bundle,
    summarize_real_effect_capability_admission_decision,
    summarize_real_effect_capability_block_receipt,
    summarize_real_effect_capability_candidate,
    summarize_real_effect_implementation_plan_scaffold,
)

from sentientos.local_authorization_grant import (
    build_local_authorization_grant_wing,
    build_operator_approval_evidence,
    build_policy_approval_evidence,
    summarize_local_authorization_grant,
    summarize_local_authorization_grant_expiry_evaluation,
    summarize_local_authorization_grant_ledger,
    summarize_local_authorization_grant_revocation_receipt,
    summarize_local_authorization_grant_verification,
    summarize_operator_approval_evidence,
    summarize_policy_approval_evidence,
)
from sentientos.host_steward_boundary import (
    build_host_steward_boundary_wing,
    summarize_host_steward_boundary_wing,
)
from sentientos.host_embodiment_trace_export import (
    serialize_host_embodiment_trace_json,
    serialize_host_embodiment_trace_markdown,
    validate_trace_export_payload,
)

REVIEWER_PROOF_BUNDLE_STATUSES = frozenset(
    {
        "reviewer_proof_bundle_ready",
        "reviewer_proof_bundle_ready_with_warnings",
        "reviewer_proof_bundle_blocked",
        "reviewer_proof_bundle_incomplete",
        "reviewer_proof_bundle_contradicted",
    }
)
REVIEWER_PROOF_ARTIFACT_KINDS = frozenset(
    {
        "trace_json",
        "trace_markdown",
        "trace_summary",
        "capability_registry_summary",
        "deferred_action_inventory",
        "proof_command_manifest",
        "reviewer_readme",
        "bundle_manifest",
        "safety_gate_posture",
        "live_grant_readiness_posture",
        "local_authorization_posture",
        "fulfillment_authorization_posture",
        "executor_contract_posture",
        "dry_run_execution_posture",
        "dry_run_audit_closure_posture",
        "real_effect_admission_posture",
        "local_diagnostic_effect_capability",
        "local_diagnostic_rollback_capability",
        "local_effect_transaction_ledger_capability",
        "host_steward_boundary_posture",
        "builtin_local_effect_runner_capability",
        "builtin_runner_transaction_orchestrator_capability",
        "workspace_file_effect_capability",
        "workspace_file_runner_transaction_capability",
        "workspace_file_transaction_orchestrator_capability",
        "workspace_change_set_admission_capability",
        "workspace_change_set_preflight_capability",
        "workspace_change_set_execution_capability",
        "workspace_change_set_execution_verification_capability",
        "workspace_change_set_lifecycle_closure_capability",
        "workspace_change_set_lifecycle_orchestration_capability",
        "work_item_lifecycle_dry_run_adapter_capability",
        "work_item_promotion_gate_capability",
        "work_item_operator_admission_review_capability",
    }
)
REVIEWER_PROOF_COMMAND_STATUSES = frozenset(
    {
        "proof_command_listed",
        "proof_command_verified",
        "proof_command_skipped",
        "proof_command_failed",
        "proof_command_not_run",
    }
)
BUNDLE_FILE_NAMES = {
    "trace_json": "trace.json",
    "trace_markdown": "trace.md",
    "trace_summary": "trace.summary.txt",
    "capability_registry_summary": "capability_registry_summary.json",
    "deferred_action_inventory": "deferred_actions.json",
    "proof_command_manifest": "proof_commands.json",
    "reviewer_readme": "README.md",
    "bundle_manifest": "bundle_manifest.json",
    "safety_gate_posture": "safety_gates.json",
    "live_grant_readiness_posture": "live_grant_readiness.json",
    "local_authorization_posture": "local_authorization.json",
    "fulfillment_authorization_posture": "fulfillment_authorization.json",
    "executor_contract_posture": "executor_contract.json",
    "dry_run_execution_posture": "dry_run_execution.json",
    "dry_run_audit_closure_posture": "dry_run_audit_closure.json",
    "real_effect_admission_posture": "real_effect_admission.json",
    "local_diagnostic_effect_capability": "local_diagnostic_effect_capability.json",
    "local_diagnostic_rollback_capability": "local_diagnostic_rollback_capability.json",
    "local_effect_transaction_ledger_capability": "local_effect_transaction_ledger_capability.json",
    "host_steward_boundary_posture": "host_steward_boundary.json",
    "builtin_local_effect_runner_capability": "builtin_local_effect_runner_capability.json",
    "builtin_runner_transaction_orchestrator_capability": "builtin_runner_transaction_orchestrator_capability.json",
    "workspace_file_effect_capability": "workspace_file_effect_capability.json",
    "workspace_file_runner_transaction_capability": "workspace_file_runner_transaction_capability.json",
    "workspace_file_transaction_orchestrator_capability": "workspace_file_transaction_orchestrator_capability.json",
    "workspace_change_set_admission_capability": "workspace_change_set_admission_capability.json",
    "workspace_change_set_preflight_capability": "workspace_change_set_preflight_capability.json",
    "workspace_change_set_execution_capability": "workspace_change_set_execution_capability.json",
    "workspace_change_set_execution_verification_capability": "workspace_change_set_execution_verification_capability.json",
    "workspace_change_set_lifecycle_closure_capability": "workspace_change_set_lifecycle_closure_capability.json",
    "workspace_change_set_lifecycle_orchestration_capability": "workspace_change_set_lifecycle_orchestration_capability.json",
    "work_item_lifecycle_dry_run_adapter_capability": "work_item_lifecycle_dry_run_adapter_capability.json",
    "work_item_promotion_gate_capability": "work_item_promotion_gate_capability.json",
    "work_item_operator_admission_review_capability": "work_item_operator_admission_review_capability.json",
}
FORBIDDEN_MANIFEST_FLAGS = (
    "live_host_collection_performed",
    "live_authorization_granted",
    "effect_performed",
    "host_mutation_performed",
    "network_performed",
    "provider_invocation_performed",
    "prompt_assembly_performed",
)
DEFERRED_ACTION_LABELS = (
    "live_authorization_grant",
    "executor_implementation",
    "backend_invocation",
    "control_plane_admission_for_fulfillment",
    "fulfillment_execution",
    "dry_run_execution_harness",
    "simulated_backend_registry",
    "dry_run_execution_request",
    "dry_run_execution_result",
    "dry_run_execution_receipt",
    "dry_run_effect_verification",
    "dry_run_postcondition_verification",
    "dry_run_rollback_rehearsal",
    "dry_run_audit_closure_receipt",
    "dry_run_closure_bundle",
    "real_effect_capability_admission",
    "real_effect_capability_candidate",
    "real_effect_implementation_plan_scaffold",
    "real_effect_capability_block_receipt",
    "real_backend_implementation",
    "real_backend_invocation",
    "real_effect_execution",
    "real_rollback_execution",
    "real_fan_pwm_control",
    "real_thermal_actuation",
    "real_power_profile_mutation",
    "real_service_restart",
    "real_file_cleanup",
    "provider_invocation",
    "network_egress",
    "prompt_assembly_export",
    "federation_transport_sync_adoption",
    "remote_execution",
    "local_diagnostic_effect_pilot_explicit_only",
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
    "builtin_local_effect_runner_explicit_only",
    "builtin_runner_transaction_orchestrator_explicit_only",
    "workspace_file_effect_pilot_explicit_only",
)
BLOCKED_ACTION_LABELS = (
    "fan_pwm_write",
    "thermal_write",
    "power_profile_mutation",
    "service_restart",
    "file_cleanup_or_delete",
    "provider_invocation",
    "network_egress",
    "prompt_assembly_export",
    "federation_transport_sync_adoption",
    "remote_execution",
    "local_diagnostic_effect_pilot_explicit_only",
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
    "builtin_local_effect_runner_explicit_only",
    "builtin_runner_transaction_orchestrator_explicit_only",
    "workspace_file_effect_pilot_explicit_only",
)


@dataclass(frozen=True)
class ReviewerProofBundleArtifact:
    artifact_id: str
    artifact_kind: str
    relative_path: str
    media_type: str
    digest: str
    byte_count: int
    metadata_only: bool = True
    contains_live_host_data: bool = False
    contains_prompt_text: bool = False
    contains_secret_material: bool = False
    contains_provider_material: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReviewerProofCommandRecord:
    command_id: str
    command: tuple[str, ...]
    purpose: str
    expected_posture: str
    status: str
    exit_code: int | None = None
    output_digest: str | None = None
    warning_codes: tuple[str, ...] = ()
    risk_codes: tuple[str, ...] = ()
    executed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReviewerProofBundleManifest:
    manifest_id: str
    scenario_id: str
    scenario_label: str
    bundle_status: str
    created_at: str
    trace_id: str
    trace_digest: str
    artifact_records: tuple[ReviewerProofBundleArtifact, ...]
    proof_command_records: tuple[ReviewerProofCommandRecord, ...]
    blocked_action_labels: tuple[str, ...]
    deferred_capability_labels: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    digest: str
    metadata_only: bool = True
    reviewer_proof_only: bool = True
    live_host_collection_performed: bool = False
    live_authorization_granted: bool = False
    effect_performed: bool = False
    host_mutation_performed: bool = False
    network_performed: bool = False
    provider_invocation_performed: bool = False
    prompt_assembly_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReviewerProofBundleValidationResult:
    ok: bool
    findings: tuple[str, ...] = ()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def _pretty_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True, default=str) + "\n"


def _digest_text(prefix: str, content: str, length: int = 24) -> str:
    return prefix + hashlib.sha256(content.encode("utf-8")).hexdigest()[:length]


def reviewer_proof_artifact_digest(content: str | bytes) -> str:
    data = content if isinstance(content, bytes) else content.encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def reviewer_proof_bundle_manifest_digest(manifest_or_payload: ReviewerProofBundleManifest | Mapping[str, Any]) -> str:
    payload = manifest_or_payload.to_dict() if isinstance(manifest_or_payload, ReviewerProofBundleManifest) else dict(manifest_or_payload)
    payload["digest"] = ""
    return _digest_text("reviewer-proof-bundle-manifest-", _canonical_json(payload))


def build_default_reviewer_proof_commands() -> tuple[ReviewerProofCommandRecord, ...]:
    commands = (
        (("python", "scripts/build_host_embodiment_trace.py", "--validate-only"), "Validate the deterministic host embodiment demo trace."),
        (("python", "scripts/build_host_embodiment_trace.py", "--format", "json"), "Print deterministic trace JSON."),
        (("python", "scripts/build_host_embodiment_trace.py", "--format", "markdown"), "Print deterministic trace Markdown."),
        (("python", "-m", "scripts.run_tests", "-q", "tests/test_host_embodiment_trace.py", "tests/test_host_embodiment_trace_export.py", "tests/test_build_host_embodiment_trace_script.py"), "Run trace and trace export tests."),
        (("python", "-m", "scripts.run_tests", "-q", "tests/test_controlled_authorization.py", "tests/test_authorization_review.py", "tests/test_effect_proof.py", "tests/test_runtime_supervisor.py"), "Run authorization review, proof, and runtime readiness tests."),
        (("python", "-m", "scripts.run_tests", "-q", "tests/test_actuation_fulfillment.py", "tests/test_privilege_broker.py", "tests/test_host_resource_policy.py", "tests/test_host_resource_governor.py", "tests/test_host_inventory.py", "tests/test_host_collectors.py"), "Run non-mutating host resource ladder tests."),
        (("python", "-m", "scripts.run_tests", "-q", "tests/test_capability_registry.py", "tests/test_reviewer_release_readiness_index.py"), "Run capability registry and reviewer documentation proof tests."),
        (("python", "scripts/build_docs.py", "--check-deps"), "Check documentation build dependencies."),
        (("python", "scripts/build_docs.py"), "Build documentation locally."),
        (("python", "scripts/verify_context_hygiene_prompt_boundaries.py"), "Verify prompt/provider boundary hygiene."),
        (("python", "scripts/run_local_diagnostic_effect.py", "--output-dir", "/tmp/sentientos-local-effect", "--summary"), "Optional explicit Tier-1 local diagnostic effect pilot; listed for reviewer awareness and not run by proof bundle generation."),
        (("python", "scripts/run_local_diagnostic_rollback.py", "--effect-receipt", "<receipt.json>", "--rollback-plan", "<rollback-plan.json>", "--output-dir-scope", "/tmp/sentientos-local-effect", "--summary"), "Optional explicit exact-artifact rollback pilot; listed for reviewer awareness and not run by proof bundle generation."),
        (("python", "scripts/run_builtin_local_effect_runner.py", "--action", "local_diagnostic_artifact_write", "--output-dir", "/tmp/sentientos-local-effect-runner", "--summary"), "Optional explicit bounded built-in local effect runner diagnostic write; listed for reviewer awareness and not run by proof bundle generation."),
        (("python", "scripts/run_builtin_local_effect_runner.py", "--action", "local_diagnostic_exact_rollback", "--effect-receipt", "<effect_receipt.json>", "--rollback-plan", "<rollback_plan.json>", "--output-dir-scope", "/tmp/sentientos-local-effect-runner", "--summary"), "Optional explicit bounded built-in local effect runner exact rollback; listed for reviewer awareness and not run by proof bundle generation."),
        (("python", "scripts/build_local_effect_transaction_ledger.py", "--effect-receipt", "<effect_receipt.json>", "--postcondition-check", "<postcondition.json>", "--production-audit", "<audit.json>", "--rollback-plan", "<rollback_plan.json>", "--summary"), "Optional metadata-only local effect transaction ledger; listed for reviewer awareness and not run by proof bundle generation."),
        (("python", "scripts/run_builtin_runner_transaction.py", "--output-dir", "/tmp/sentientos-builtin-runner-transaction", "--mode", "diagnostic_write_rollback_with_ledger", "--ledger-output", "/tmp/sentientos-builtin-runner-transaction/transaction_ledger.json", "--summary"), "Optional explicit bounded runner transaction orchestrator; listed for reviewer awareness and not run by proof bundle generation."),
        (("python", "scripts/run_workspace_file_effect.py", "--workspace-root", "/tmp/sentientos-workspace-file-effect", "--target", "demo.txt", "--payload", "hello", "--summary"), "Optional explicit workspace-scoped single-file update pilot; listed for reviewer awareness and not run by proof bundle generation."),
        (("python", "scripts/run_workspace_file_effect.py", "--workspace-root", "/tmp/sentientos-workspace-file-effect", "--target", "demo.txt", "--payload", "hello", "--rollback", "--summary"), "Optional explicit workspace-scoped exact rollback pilot; listed for reviewer awareness and not run by proof bundle generation."),
        (("python", "scripts/run_builtin_local_effect_runner.py", "--action", "workspace_scoped_file_update", "--workspace-root", "/tmp/sentientos-workspace-runner", "--target", "demo.txt", "--payload", "hello", "--summary"), "Optional explicit built-in runner workspace-scoped file update; listed for reviewer awareness and not run by proof bundle generation."),
        (("python", "scripts/run_builtin_local_effect_runner.py", "--action", "workspace_scoped_file_exact_rollback", "--workspace-effect-receipt", "<workspace_effect_receipt.json>", "--workspace-rollback-plan", "<workspace_rollback_plan.json>", "--workspace-root-scope", "/tmp/sentientos-workspace-runner", "--summary"), "Optional explicit built-in runner workspace exact rollback; listed for reviewer awareness and not run by proof bundle generation."),
        (("python", "scripts/build_workspace_file_transaction_ledger.py", "--effect-receipt", "<workspace_effect_receipt.json>", "--preimage", "<workspace_preimage.json>", "--postcondition-check", "<workspace_postcondition_check.json>", "--production-audit", "<workspace_production_audit.json>", "--rollback-plan", "<workspace_rollback_plan.json>", "--summary"), "Optional explicit workspace file transaction ledger build; listed for reviewer awareness and not run by proof bundle generation."),
        (("python", "scripts/run_builtin_runner_transaction.py", "--mode", "workspace_file_update_rollback_with_ledger", "--workspace-root", "/tmp/sentientos-workspace-transaction", "--target", "demo.txt", "--payload", "hello", "--ledger-output", "/tmp/sentientos-workspace-transaction/workspace_transaction_ledger.json", "--summary"), "Optional explicit workspace file transaction orchestrator; listed for reviewer awareness and not run by proof bundle generation."),
        (("python", "scripts/admit_workspace_change_set.py", "--proposal", "<workspace_change_set_proposal_metadata.json>", "--summary"), "Optional metadata-only workspace change-set admission review; listed for reviewer awareness and not run by proof bundle generation."),
        (("python", "scripts/preflight_workspace_change_set.py", "--workspace-root", "/tmp/sentientos-workspace-change-set", "--target", "demo.txt=hello", "--summary"), "Optional explicit workspace change-set preflight/planning command; listed for reviewer awareness and not run by proof bundle generation."),
        (("python", "scripts/run_workspace_change_set_transaction.py", "--workspace-root", "/tmp/sentientos-workspace-change-set", "--target", "demo.txt=hello", "--target", "docs-demo.txt=docs", "--summary"), "Optional explicit bounded workspace change-set execution command; listed for reviewer awareness and not run by proof bundle generation."),
        (("python", "scripts/verify_workspace_change_set_execution.py", "--evidence", "<workspace_change_set_execution_evidence.json>", "--summary"), "Optional read-only workspace change-set execution verification/replay-audit command; listed for reviewer awareness and not run by proof bundle generation."),
        (("python", "scripts/build_workspace_change_set_lifecycle_closure.py", "--evidence", "<workspace_change_set_lifecycle_evidence.json>", "--summary"), "Optional metadata-only workspace change-set lifecycle closure manifest command; listed for reviewer awareness and not run by proof bundle generation."),
        (("python", "scripts/run_workspace_change_set_lifecycle.py", "--proposal", "<workspace_change_set_proposal.json>", "--workspace-root", "<path>", "--mode", "admit_preflight_execute_verify_close", "--summary"), "Optional bounded workspace change-set lifecycle orchestration command; listed for reviewer awareness and not run by proof bundle generation."),
    )
    return tuple(
        ReviewerProofCommandRecord(
            command_id=f"proof-command-{index:02d}",
            command=command,
            purpose=purpose,
            expected_posture="bounded local reviewer check; no live authorization, no effects, no host mutation",
            status="proof_command_not_run",
        )
        for index, (command, purpose) in enumerate(commands, start=1)
    )


def _trace_summary_text(trace: Any) -> str:
    summary = summarize_host_embodiment_trace(trace)
    return "\n".join(
        [
            "SentientOS Reviewer First-Run Proof Bundle Trace Summary",
            f"scenario: {summary['scenario_id']}",
            f"status: {summary['trace_status']}",
            f"steps: {summary['step_count']}",
            "reviewer proof only: true",
            "metadata only: true",
            "fake/sample telemetry by default: true",
            "live host collection performed: false",
            "live authorization granted: false",
            "effect performed: false",
            "host mutation performed: false",
            "network performed: false",
            "provider invocation performed: false",
            "prompt assembly performed: false",
            "PWM presence is not control authority: true",
            f"digest: {summary['digest']}",
            "",
        ]
    )


def _deferred_action_inventory() -> dict[str, Any]:
    return {
        "inventory_id": "reviewer-proof-bundle-deferred-actions-v1",
        "metadata_only": True,
        "reviewer_proof_only": True,
        "deferred_action_labels": DEFERRED_ACTION_LABELS,
        "blocked_action_labels": BLOCKED_ACTION_LABELS,
        "proof_statement": "All listed actions remain deferred or blocked; the bundle is an export-only inspection artifact.",
        "no_live_authorization": True,
        "no_effects": True,
        "no_host_mutation": True,
        "no_network": True,
        "no_provider": True,
        "no_prompt_assembly": True,
    }


def _readme_text(manifest_id: str, trace_digest: str) -> str:
    return "\n".join(
        [
            "# SentientOS Reviewer First-Run Proof Bundle",
            "",
            "This local bundle packages the deterministic non-mutating host-embodiment reviewer demo trace.",
            "It uses fake/sample thermal+PWM telemetry by default and does not collect live host data.",
            "",
            "## Inspect first",
            "",
            "1. `trace.md` — reviewer-readable trace ladder.",
            "2. `bundle_manifest.json` — artifact digests and safety flags.",
            "3. `deferred_actions.json` — deferred/blocked action inventory.",
            "4. `safety_gates.json` — metadata-only host actuation safety gate posture.",
            "5. `live_grant_readiness.json` — readiness/preflight-only future live-grant posture; it is not a grant.",
            "6. `local_authorization.json` — bounded local authorization-record posture; it is not fulfillment.",
            "7. `fulfillment_authorization.json` — metadata-only authorization consumption posture; consuming authorization is not fulfillment.",
            "8. `executor_contract.json` — metadata-only executor contract posture; it is not an executor.",
            "9. `dry_run_execution.json` — simulation-only dry-run harness posture; it is not fulfillment or an effect receipt.",
            "10. `dry_run_audit_closure.json` — dry-run verification/audit closure posture; it is not a real effect receipt, real postcondition check, real rollback, or production audit receipt.",
            "11. `real_effect_admission.json` — metadata-only real-effect capability admission posture; admission is not implementation or execution.",
            "12. `proof_commands.json` — bounded local proof commands listed but not run by default.",
            "13. `capability_registry_summary.json` — metadata-only capability posture.",
            "",
            "## Safety posture",
            "",
            "- Reviewer proof only: true",
            "- Metadata only: true",
            "- Live host collection performed: false",
            "- Live authorization granted: false",
            "- Effect performed: false",
            "- Host mutation performed: false",
            "- Network/provider/prompt assembly performed: false",
            "- Safety gates are not authorization and do not grant fulfillment or control authority.",
            "- Live-grant readiness is not a live grant; the approval packet is not approval; preflight does not issue a grant.",
            "- Local authorization grant records are authority metadata only; verification does not authorize fulfillment.",
            "- Executor contract records are readiness metadata only; they do not load backends, execute dry runs, grant control-plane admission, fulfill actions, or perform effects.",
            "- Dry-run execution runs only inert simulated in-process backends; dry_run_executed=true is simulation only, not fulfillment, not an effect receipt, and not host mutation proof.",
            "- Dry-run audit closure verifies dry-run evidence only; it is not a real effect receipt, real host postcondition check, real rollback, or production audit receipt.",
            "- Fan/PWM writes, thermal writes, power mutation, service restart, cleanup, federation transport, and remote execution remain deferred or blocked.",
            "",
            f"Manifest ID: `{manifest_id}`",
            f"Trace digest: `{trace_digest}`",
            "",
        ]
    )


def _artifact(kind: str, content: str) -> ReviewerProofBundleArtifact:
    media_type = "application/json" if BUNDLE_FILE_NAMES[kind].endswith(".json") else ("text/markdown" if BUNDLE_FILE_NAMES[kind].endswith(".md") else "text/plain")
    return ReviewerProofBundleArtifact(
        artifact_id=f"reviewer-proof-{kind.replace('_', '-')}",
        artifact_kind=kind,
        relative_path=BUNDLE_FILE_NAMES[kind],
        media_type=media_type,
        digest=reviewer_proof_artifact_digest(content),
        byte_count=len(content.encode("utf-8")),
    )


def build_reviewer_proof_bundle_payload(
    *,
    scenario: str = "thermal_pwm_demo",
    created_at: str = "1970-01-01T00:00:00+00:00",
    proof_command_records: Sequence[ReviewerProofCommandRecord] | None = None,
) -> dict[str, Any]:
    if scenario != "thermal_pwm_demo":
        raise ValueError(f"unsupported scenario: {scenario}")
    trace = build_host_embodiment_demo_trace(created_at=created_at)
    trace_validation = validate_trace_export_payload(trace)
    if not trace_validation.ok:
        raise ValueError("invalid trace export payload: " + ", ".join(trace_validation.findings))

    registry = build_default_capability_registry()
    manifest_id = "reviewer-proof-bundle-thermal-pwm-demo"
    safety_gates = build_safety_gates_for_domain("cooling_control_future", created_at=created_at)
    controlled_ledger = {
        "ledger_id": "sample-controlled-authorization-ledger-for-reviewer-proof",
        "grant_records": ({"grant_record_id": "sample-controlled-grant-schema"},),
        "revocation_records": ({"revocation_id": "sample-revocation-schema"},),
        "metadata_only": True,
        "ledger_only": True,
        "host_mutation_performed": False,
    }
    proof_manifest_stub = {"manifest_id": manifest_id, "metadata_only": True, "reviewer_proof_only": True}
    live_grant_readiness = build_live_grant_readiness_wing(
        controlled_ledger,
        safety_gates.safety_gate_satisfaction_manifest,
        proof_manifest_stub,
        readiness_domain="future_cooling_live_grant_review",
        created_at=created_at,
    )
    operator_evidence = build_operator_approval_evidence(
        approval_time_bounds=("not_before:1970-01-01T00:00:00+00:00", "not_after:2999-01-01T00:00:00+00:00"),
        approval_expiry_label="expires:2999-01-01T00:00:00+00:00",
        created_at=created_at,
    )
    policy_evidence = build_policy_approval_evidence(
        policy_time_bounds=("not_before:1970-01-01T00:00:00+00:00", "not_after:2999-01-01T00:00:00+00:00"),
        policy_expiry_label="expires:2999-01-01T00:00:00+00:00",
        created_at=created_at,
    )
    local_authorization = build_local_authorization_grant_wing(
        live_grant_readiness.preflight_receipt,
        live_grant_readiness.prerequisite_matrix,
        operator_evidence,
        policy_evidence,
        created_at=created_at,
    )
    fulfillment_authorization = build_fulfillment_authorization_wing(
        local_authorization.grant,
        local_authorization.verification,
        requested_fulfillment_domain="future_cooling_fulfillment_authorization",
        requested_backend_class="future_metadata_only_cooling_fulfillment_executor",
        requested_scope_labels=("future_cooling_scope",),
        requested_time_label=created_at,
        created_at=created_at,
    )
    if fulfillment_authorization.consumption_receipt is None:
        raise ValueError("reviewer proof scenario expected consumed authorization receipt")
    executor_contract = build_fulfillment_executor_contract_wing(fulfillment_authorization.consumption_receipt, created_at=created_at)
    dry_run_execution = build_dry_run_execution_harness_wing(
        executor_contract.readiness_receipt,
        requested_dry_run_domain="future_cooling_dry_run",
        requested_simulated_backend_class="cooling_backend_simulated",
        created_at=created_at,
    )
    dry_run_audit_closure = build_dry_run_audit_closure_wing(dry_run_execution.receipt, created_at=created_at)
    real_effect_admission = build_real_effect_admission_wing(dry_run_audit_closure.closure_bundle, created_at=created_at)
    host_steward_boundary = build_host_steward_boundary_wing(created_at=created_at)
    commands = tuple(proof_command_records) if proof_command_records is not None else build_default_reviewer_proof_commands()
    contents: dict[str, str] = {
        "trace_json": serialize_host_embodiment_trace_json(trace),
        "trace_markdown": serialize_host_embodiment_trace_markdown(trace),
        "trace_summary": _trace_summary_text(trace),
        "capability_registry_summary": _pretty_json({"summary": summarize_capability_registry(registry), "records": [record.to_dict() for record in registry.records], "metadata_only": True, "reviewer_proof_only": True}),
        "deferred_action_inventory": _pretty_json(_deferred_action_inventory()),
        "safety_gate_posture": _pretty_json({"metadata_only": True, "reviewer_proof_only": True, "safety_gate_only": True, "proof_statement": "Safety gates declare prerequisites only; they are not authorization or fulfillment.", "summary": summarize_safety_gate_satisfaction_manifest(safety_gates.safety_gate_satisfaction_manifest), "records": safety_gates.to_dict()}),
        "live_grant_readiness_posture": _pretty_json({
            "metadata_only": True,
            "reviewer_proof_only": True,
            "readiness_preflight_only": True,
            "proof_statement": "Live-grant readiness is not a live grant; approval packets are not approval; preflight receipts do not issue grants.",
            "matrix_summary": summarize_live_grant_prerequisite_matrix(live_grant_readiness.prerequisite_matrix),
            "approval_packet_summary": summarize_operator_policy_approval_packet(live_grant_readiness.approval_packet),
            "preflight_summary": summarize_grant_issue_preflight_receipt(live_grant_readiness.preflight_receipt),
            "denial_deferral_summary": summarize_grant_denial_deferral_receipt(live_grant_readiness.denial_deferral_receipt),
            "records": {
                "prerequisite_matrix": live_grant_readiness.prerequisite_matrix.to_dict(),
                "approval_packet": live_grant_readiness.approval_packet.to_dict(),
                "preflight_receipt": live_grant_readiness.preflight_receipt.to_dict(),
                "denial_deferral_receipt": live_grant_readiness.denial_deferral_receipt.to_dict(),
            },
        }),
        "local_authorization_posture": _pretty_json({
            "metadata_only": True,
            "reviewer_proof_only": True,
            "authorization_record_only": True,
            "proof_statement": "A local authorization grant is authority metadata, not fulfillment; verification does not authorize fulfillment and no effect or host mutation is performed.",
            "operator_approval_evidence_summary": summarize_operator_approval_evidence(operator_evidence),
            "policy_approval_evidence_summary": summarize_policy_approval_evidence(policy_evidence),
            "grant_summary": summarize_local_authorization_grant(local_authorization.grant),
            "expiry_evaluation_summary": summarize_local_authorization_grant_expiry_evaluation(local_authorization.expiry_evaluation),
            "verification_summary": summarize_local_authorization_grant_verification(local_authorization.verification),
            "revocation_receipt_summary": summarize_local_authorization_grant_revocation_receipt(local_authorization.revocation_receipt),
            "ledger_summary": summarize_local_authorization_grant_ledger(local_authorization.ledger),
            "fulfillment_granted": False,
            "effect_performed": False,
            "host_mutation_performed": False,
            "real_actuation_deferred": True,
            "records": {
                "operator_approval_evidence": operator_evidence.to_dict(),
                "policy_approval_evidence": policy_evidence.to_dict(),
                "grant": local_authorization.grant.to_dict(),
                "expiry_evaluation": local_authorization.expiry_evaluation.to_dict(),
                "verification": local_authorization.verification.to_dict(),
                "revocation_receipt_schema_example": local_authorization.revocation_receipt.to_dict(),
                "ledger": local_authorization.ledger.to_dict(),
            },
        }),
        "fulfillment_authorization_posture": _pretty_json({
            "metadata_only": True,
            "reviewer_proof_only": True,
            "consumption_pre_fulfillment_only": True,
            "proof_statement": "Fulfillment authorization consumption checks grant scope for a future executor; consuming authorization is not fulfillment, scope match is not execution, and no effect or host mutation is performed.",
            "request_summary": summarize_fulfillment_authorization_request(fulfillment_authorization.request),
            "grant_consumption_verification_summary": summarize_grant_consumption_verification(fulfillment_authorization.grant_consumption_verification),
            "scope_match_assessment_summary": summarize_fulfillment_scope_match_assessment(fulfillment_authorization.scope_match_assessment),
            "consumption_receipt_summary": summarize_fulfillment_authorization_consumption_receipt(fulfillment_authorization.consumption_receipt) if fulfillment_authorization.consumption_receipt else None,
            "denial_receipt_summary": summarize_fulfillment_authorization_denial_receipt(fulfillment_authorization.denial_receipt) if fulfillment_authorization.denial_receipt else None,
            "authorization_consumed_for_future_fulfillment": bool(fulfillment_authorization.consumption_receipt and fulfillment_authorization.consumption_receipt.authorization_consumed_for_future_fulfillment),
            "fulfillment_granted": False,
            "effect_performed": False,
            "host_mutation_performed": False,
            "real_actuation_deferred": True,
            "records": {
                "request": fulfillment_authorization.request.to_dict(),
                "grant_consumption_verification": fulfillment_authorization.grant_consumption_verification.to_dict(),
                "scope_match_assessment": fulfillment_authorization.scope_match_assessment.to_dict(),
                "consumption_receipt": fulfillment_authorization.consumption_receipt.to_dict() if fulfillment_authorization.consumption_receipt else None,
                "denial_receipt": fulfillment_authorization.denial_receipt.to_dict() if fulfillment_authorization.denial_receipt else None,
            },
        }),
        "executor_contract_posture": _pretty_json({
            "metadata_only": True,
            "reviewer_proof_only": True,
            "executor_contract_readiness_only": True,
            "proof_statement": "Executor contract records define prerequisites for a future executor only; the contract is not an executor, backend declarations are not loaded or invoked, dry-run plans are not executed, admission packets are not control-plane admission, and readiness receipts perform no effects.",
            "contract_summary": summarize_fulfillment_executor_contract(executor_contract.contract),
            "backend_declaration_summary": summarize_executor_backend_declaration(executor_contract.backend_declaration),
            "precondition_manifest_summary": summarize_executor_precondition_manifest(executor_contract.precondition_manifest),
            "dry_run_plan_summary": summarize_executor_dry_run_plan(executor_contract.dry_run_plan),
            "admission_packet_summary": summarize_executor_admission_packet(executor_contract.admission_packet),
            "readiness_receipt_summary": summarize_executor_contract_readiness_receipt(executor_contract.readiness_receipt),
            "executor_implemented": False,
            "backend_loaded": False,
            "backend_invoked": False,
            "dry_run_executed": False,
            "control_plane_admission_granted": False,
            "fulfillment_granted": False,
            "effect_performed": False,
            "host_mutation_performed": False,
            "real_actuation_deferred": True,
            "records": {
                "contract": executor_contract.contract.to_dict(),
                "backend_declaration": executor_contract.backend_declaration.to_dict(),
                "precondition_manifest": executor_contract.precondition_manifest.to_dict(),
                "dry_run_plan": executor_contract.dry_run_plan.to_dict(),
                "admission_packet": executor_contract.admission_packet.to_dict(),
                "readiness_receipt": executor_contract.readiness_receipt.to_dict(),
            },
        }),
        "dry_run_execution_posture": _pretty_json({
            "metadata_only": True,
            "reviewer_proof_only": True,
            "dry_run_execution_harness_only": True,
            "simulation_only": True,
            "proof_statement": "Dry-run execution runs only inert simulated in-process backend mappings against executor contract records; it is not real fulfillment, not an effect receipt, and not proof of host mutation.",
            "registry_summary": summarize_simulated_backend_registry(dry_run_execution.registry),
            "request_summary": summarize_dry_run_execution_request(dry_run_execution.request),
            "result_summary": summarize_dry_run_execution_result(dry_run_execution.result_or_block_receipt) if dry_run_execution.receipt else None,
            "block_receipt_summary": summarize_dry_run_execution_block_receipt(dry_run_execution.result_or_block_receipt) if dry_run_execution.receipt is None else None,
            "receipt_summary": summarize_dry_run_execution_receipt(dry_run_execution.receipt) if dry_run_execution.receipt else None,
            "dry_run_executed": bool(dry_run_execution.receipt and dry_run_execution.receipt.dry_run_executed),
            "real_backend_invoked": False,
            "real_fulfillment_performed": False,
            "real_effect_performed": False,
            "effect_performed": False,
            "host_mutation_performed": False,
            "fan_pwm_write_performed": False,
            "thermal_actuation_performed": False,
            "power_profile_mutation_performed": False,
            "service_restart_performed": False,
            "file_cleanup_performed": False,
            "network_performed": False,
            "provider_invocation_performed": False,
            "prompt_assembly_performed": False,
            "real_actuation_deferred": True,
            "records": {
                "registry": dry_run_execution.registry.to_dict(),
                "request": dry_run_execution.request.to_dict(),
                "result_or_block_receipt": dry_run_execution.result_or_block_receipt.to_dict(),
                "receipt": dry_run_execution.receipt.to_dict() if dry_run_execution.receipt else None,
            },
        }),
        "dry_run_audit_closure_posture": _pretty_json({
            "metadata_only": True,
            "reviewer_proof_only": True,
            "dry_run_audit_closure_only": True,
            "proof_statement": "Dry-run audit closure verifies dry-run evidence only; it is not a real effect receipt, not a real host postcondition check, not real rollback, and not a production audit receipt.",
            "effect_verification_summary": summarize_dry_run_effect_verification(dry_run_audit_closure.effect_verification),
            "postcondition_verification_summary": summarize_dry_run_postcondition_verification(dry_run_audit_closure.postcondition_verification),
            "rollback_rehearsal_summary": summarize_dry_run_rollback_rehearsal(dry_run_audit_closure.rollback_rehearsal),
            "audit_closure_receipt_summary": summarize_dry_run_audit_closure_receipt(dry_run_audit_closure.audit_closure_receipt),
            "closure_bundle_summary": summarize_dry_run_closure_bundle(dry_run_audit_closure.closure_bundle),
            "real_effect_receipt_created": False,
            "real_postcondition_check_performed": False,
            "real_rollback_performed": False,
            "production_audit_receipt_created": False,
            "real_fulfillment_performed": False,
            "real_effect_performed": False,
            "host_mutation_performed": False,
            "fan_pwm_write_performed": False,
            "thermal_actuation_performed": False,
            "power_profile_mutation_performed": False,
            "service_restart_performed": False,
            "file_cleanup_performed": False,
            "network_performed": False,
            "provider_invocation_performed": False,
            "prompt_assembly_performed": False,
            "real_actuation_deferred": True,
            "records": {
                "effect_verification": dry_run_audit_closure.effect_verification.to_dict(),
                "postcondition_verification": dry_run_audit_closure.postcondition_verification.to_dict(),
                "rollback_rehearsal": dry_run_audit_closure.rollback_rehearsal.to_dict(),
                "audit_closure_receipt": dry_run_audit_closure.audit_closure_receipt.to_dict(),
                "closure_bundle": dry_run_audit_closure.closure_bundle.to_dict(),
            },
        }),
        "real_effect_admission_posture": _pretty_json({
            "metadata_only": True,
            "reviewer_proof_only": True,
            "real_effect_admission_only": True,
            "proof_statement": "Dry-run audit closure does not automatically permit real effects; real-effect admission is implementation planning metadata only, not implementation, backend loading, execution, fulfillment, effect receipt creation, postcondition checking, rollback, production audit, or host mutation.",
            "candidate_summary": summarize_real_effect_capability_candidate(real_effect_admission.candidate),
            "decision_summary": summarize_real_effect_capability_admission_decision(real_effect_admission.decision),
            "plan_scaffold_summary": summarize_real_effect_implementation_plan_scaffold(real_effect_admission.plan_or_block_receipt) if hasattr(real_effect_admission.plan_or_block_receipt, "plan_id") else None,
            "block_receipt_summary": summarize_real_effect_capability_block_receipt(real_effect_admission.plan_or_block_receipt) if hasattr(real_effect_admission.plan_or_block_receipt, "receipt_id") else None,
            "admission_bundle_summary": summarize_real_effect_admission_bundle(real_effect_admission.admission_bundle),
            "authorizes_implementation": False,
            "authorizes_execution": False,
            "implementation_not_started": True,
            "backend_loaded": False,
            "backend_invoked": False,
            "real_backend_implemented": False,
            "real_fulfillment_performed": False,
            "real_effect_performed": False,
            "real_effect_receipt_created": False,
            "real_postcondition_check_performed": False,
            "real_rollback_performed": False,
            "production_audit_receipt_created": False,
            "host_mutation_performed": False,
            "fan_pwm_write_performed": False,
            "thermal_actuation_performed": False,
            "power_profile_mutation_performed": False,
            "service_restart_performed": False,
            "file_cleanup_performed": False,
            "network_performed": False,
            "provider_invocation_performed": False,
            "prompt_assembly_performed": False,
            "blocked_actions": real_effect_admission.admission_bundle.blocked_actions,
            "records": {
                "candidate": real_effect_admission.candidate.to_dict(),
                "decision": real_effect_admission.decision.to_dict(),
                "plan_or_block_receipt": real_effect_admission.plan_or_block_receipt.to_dict(),
                "admission_bundle": real_effect_admission.admission_bundle.to_dict(),
            },
        }),
        "workspace_change_set_admission_capability": _pretty_json({
            "metadata_only": True,
            "reviewer_proof_only": True,
            "capability_available": True,
            "change_set_admission_exists": True,
            "admission_review_only": True,
            "inspects_supplied_proposal_metadata_only": True,
            "validates_declared_target_count": True,
            "validates_relative_paths_syntactically": True,
            "validates_declared_payload_metadata_only": True,
            "target_payload_bodies_included": False,
            "workspace_target_files_read": False,
            "filesystem_existence_checked": False,
            "filesystem_digests_computed": False,
            "preflight_performed": False,
            "transaction_plan_built": False,
            "execution_performed": False,
            "rollback_performed": False,
            "verification_replay_performed": False,
            "lifecycle_closure_built": False,
            "cleanup_performed": False,
            "optional_admission_artifact_only_when_caller_supplies_path": True,
            "run_by_reviewer_proof_bundle_default": False,
            "proof_bundle_admission_run": False,
            "proof_command_status": "proof_command_not_run",
            "proof_command": "python scripts/admit_workspace_change_set.py --proposal <workspace_change_set_proposal_metadata.json> --summary",
            "general_filesystem_access_remains_blocked": True,
            "cleanup_remains_blocked": True,
            "recursive_wildcard_unrelated_delete_remain_blocked": True,
            "no_subprocess_shell_network_provider_prompt_control_plane_execution": True,
            "hardware_service_power_fan_thermal_remain_blocked_deferred": True,
        }),
        "workspace_change_set_preflight_capability": _pretty_json({
            "metadata_only": True,
            "reviewer_proof_only": True,
            "capability_available": True,
            "change_set_preflight_exists": True,
            "preflight_planning_only": True,
            "reads_only_explicitly_declared_targets": True,
            "target_count_bound": 8,
            "payload_bound_per_target_bytes": 65536,
            "total_payload_bound_bytes": 262144,
            "target_writes_occur": False,
            "rollback_occurs": False,
            "runner_orchestrator_invocation_occurs": False,
            "run_by_reviewer_proof_bundle_default": False,
            "proof_command_status": "proof_command_not_run",
            "proof_command": "python scripts/preflight_workspace_change_set.py --workspace-root /tmp/sentientos-workspace-change-set --target demo.txt=\"hello\" --summary",
            "general_filesystem_access_remains_blocked": True,
            "cleanup_remains_blocked": True,
            "recursive_delete_remains_blocked": True,
            "wildcard_delete_remains_blocked": True,
            "unrelated_file_delete_remains_blocked": True,
            "subprocess_shell_network_provider_prompt_control_plane_execution": False,
            "hardware_service_power_fan_thermal_blocked_deferred": True,
            "future_change_set_execution_deferred": False,
        }),
        "workspace_change_set_execution_capability": _pretty_json({
            "metadata_only": True,
            "reviewer_proof_only": True,
            "capability_available": True,
            "bounded_change_set_execution_exists": True,
            "consumes_passed_preflight_and_transaction_plans": True,
            "executes_explicit_targets_only": True,
            "uses_single_target_workspace_file_effect_helpers": True,
            "rollback_is_reverse_order_exact_target_only": True,
            "partial_state_is_visible": True,
            "run_by_reviewer_proof_bundle_default": False,
            "proof_bundle_execution_performed": False,
            "proof_bundle_rollback_performed": False,
            "proof_bundle_ledger_built_by_default": False,
            "proof_bundle_host_mutation_performed": False,
            "general_filesystem_access_remains_blocked": True,
            "cleanup_remains_blocked": True,
            "recursive_wildcard_unrelated_delete_remain_blocked": True,
            "no_subprocess_shell_network_provider_prompt_control_plane_execution": True,
            "hardware_service_power_fan_thermal_remain_blocked_deferred": True,
            "proof_command_status": "proof_command_not_run",
            "proof_command": "python scripts/run_workspace_change_set_transaction.py --workspace-root /tmp/sentientos-workspace-change-set --target demo.txt=hello --target docs-demo.txt=docs --summary",
        }),
        "workspace_change_set_execution_verification_capability": _pretty_json({
            "metadata_only": True,
            "reviewer_proof_only": True,
            "capability_available": True,
            "read_only_verification_exists": True,
            "verifies_completed_change_set_execution_evidence": True,
            "reads_only_explicitly_declared_targets": True,
            "recomputes_declared_target_digests_only": True,
            "checks_receipt_ledger_closure_consistency": True,
            "checks_optional_rollback_preimage_or_absence": True,
            "partial_state_replay_audit_visible": True,
            "optional_audit_artifact_only_when_caller_supplies_path": True,
            "run_by_reviewer_proof_bundle_default": False,
            "proof_bundle_verification_run": False,
            "proof_bundle_execution_performed": False,
            "proof_bundle_rollback_performed": False,
            "proof_bundle_cleanup_performed": False,
            "general_filesystem_access_remains_blocked": True,
            "cleanup_remains_blocked": True,
            "recursive_wildcard_unrelated_delete_remain_blocked": True,
            "no_subprocess_shell_network_provider_prompt_control_plane_execution": True,
            "hardware_service_power_fan_thermal_remain_blocked_deferred": True,
            "proof_command_status": "proof_command_not_run",
            "proof_command": "python scripts/verify_workspace_change_set_execution.py --evidence <workspace_change_set_execution_evidence.json> --summary",
        }),

        "workspace_change_set_lifecycle_closure_capability": _pretty_json({
            "metadata_only": True,
            "reviewer_proof_only": True,
            "capability_available": True,
            "lifecycle_closure_manifest_exists": True,
            "consumes_supplied_evidence_json_only": True,
            "requires_verification_evidence": True,
            "does_not_verify_replay": True,
            "does_not_read_target_files": True,
            "does_not_recompute_target_digests": True,
            "does_not_execute": True,
            "does_not_rollback": True,
            "does_not_cleanup": True,
            "does_not_schedule": True,
            "optional_closure_artifact_only_when_caller_supplies_path": True,
            "run_by_reviewer_proof_bundle_default": False,
            "proof_bundle_closure_run": False,
            "proof_bundle_execution_performed": False,
            "proof_bundle_rollback_performed": False,
            "proof_bundle_verification_replay_performed": False,
            "proof_bundle_cleanup_performed": False,
            "general_filesystem_access_remains_blocked": True,
            "cleanup_remains_blocked": True,
            "recursive_wildcard_unrelated_delete_remain_blocked": True,
            "no_subprocess_shell_network_provider_prompt_control_plane_execution": True,
            "hardware_service_power_fan_thermal_remain_blocked_deferred": True,
            "proof_command_status": "proof_command_not_run",
            "proof_command": "python scripts/build_workspace_change_set_lifecycle_closure.py --evidence <workspace_change_set_lifecycle_evidence.json> --summary",
        }),
        "workspace_change_set_lifecycle_orchestration_capability": _pretty_json({
            "metadata_only": True,
            "reviewer_proof_only": True,
            "capability_available": True,
            "lifecycle_orchestration_exists": True,
            "coordinates_existing_workspace_change_set_wings_only": True,
            "supported_modes": ["admit_only", "admit_and_preflight", "admit_preflight_execute", "admit_preflight_execute_verify", "admit_preflight_execute_verify_close", "dry_run_full_lifecycle"],
            "does_not_add_file_effect_primitive": True,
            "does_not_add_executor": True,
            "does_not_add_verifier": True,
            "does_not_add_closure_system": True,
            "does_not_read_target_files_directly": True,
            "does_not_recompute_target_digests": True,
            "does_not_cleanup": True,
            "does_not_schedule": True,
            "dry_run_does_not_execute_or_verify": True,
            "optional_stage_artifacts_only_when_caller_supplies_paths": True,
            "run_by_reviewer_proof_bundle_default": False,
            "proof_bundle_lifecycle_orchestration_run": False,
            "proof_bundle_execution_performed": False,
            "proof_bundle_rollback_performed": False,
            "proof_bundle_cleanup_performed": False,
            "general_filesystem_access_remains_blocked": True,
            "cleanup_remains_blocked": True,
            "recursive_wildcard_unrelated_delete_remain_blocked": True,
            "no_subprocess_shell_network_provider_prompt_control_plane_execution": True,
            "hardware_service_power_fan_thermal_remain_blocked_deferred": True,
            "proof_command_status": "proof_command_not_run",
            "proof_command": "python scripts/run_workspace_change_set_lifecycle.py --proposal <workspace_change_set_proposal.json> --workspace-root <path> --mode admit_preflight_execute_verify_close --summary",
        }),
        "work_item_lifecycle_dry_run_adapter_capability": _pretty_json({
            "metadata_only": True,
            "reviewer_proof_only": True,
            "capability_available": True,
            "dry_run_adapter_exists": True,
            "requires_normalized_packet_and_handoff_plan": True,
            "invokes_lifecycle_orchestrator_mode": "dry_run_full_lifecycle_only",
            "full_lifecycle_execution_modes_not_invoked": True,
            "workspace_execution_not_invoked": True,
            "agent_execution_not_invoked": True,
            "run_by_reviewer_proof_bundle_default": False,
            "proof_bundle_dry_run_adapter_run": False,
            "proof_command_status": "proof_command_not_run",
            "proof_command": "python scripts/run_work_item_dry_run.py --packet <normalized_work_item_packet.json> --handoff <work_item_handoff_plan.json> --workspace-root <path> --summary",
        }),
        "work_item_promotion_gate_capability": _pretty_json({
            "metadata_only": True,
            "reviewer_proof_only": True,
            "capability_id": "work_item_promotion_gate",
            "capability_category": "task_work_item_promotion_gate",
            "status": "implemented",
            "authority_level": "packet_only",
            "promotion_gate_exists": True,
            "execution_readiness_metadata_only": True,
            "proof_command_status": "proof_command_not_run",
            "proof_command": "python scripts/evaluate_work_item_promotion.py --review-packet <review_packet.json> --summary",
            "run_by_reviewer_proof_bundle_default": False,
            "cli_entry": "scripts/evaluate_work_item_promotion.py",
            "matrix_runner_coverage": "scripts/run_work_item_review_packet_matrix.py:promotion_gate_tests",
            "docs_reference": "docs/architecture/task_work_item_promotion_gate_wing.md",
            "non_authority_boundary_summary": "Promotion output is readiness metadata only; it does not authorize or invoke execution paths.",
            "blocked_or_deferred_surfaces": [
                "execution",
                "workspace mutation",
                "lifecycle orchestration invocation",
                "admission/preflight/execution/verification/closure helper invocation",
                "scheduler",
                "live tracker integration",
                "agent execution",
                "branch/PR/issue mutation",
                "network/provider/prompt/subprocess/shell",
            ],
            "does_not_execute": True,
            "does_not_mutate_workspace": True,
            "does_not_invoke_lifecycle_orchestration": True,
            "does_not_invoke_change_set_helpers": True,
            "does_not_schedule": True,
            "does_not_integrate_live_tracker": True,
            "does_not_execute_agents": True,
            "does_not_mutate_branch_pr_issue": True,
            "does_not_invoke_network_provider_prompt_subprocess_shell": True,
        }),
        "work_item_operator_admission_review_capability": _pretty_json({
            "metadata_only": True,
            "reviewer_proof_only": True,
            "capability_id": "work_item_operator_admission_review",
            "capability_category": "task_work_item_operator_admission_review",
            "status": "implemented",
            "authority_level": "metadata-admission-only",
            "proof_command_status": "proof_command_not_run",
            "proof_command": "python scripts/build_operator_admission_review.py --promotion-dossier <promotion.json> --summary",
            "cli_entry": "scripts/build_operator_admission_review.py",
            "matrix_runner_coverage": "scripts/run_work_item_review_packet_matrix.py:operator_admission_review_tests",
            "docs_reference": "docs/architecture/task_work_item_operator_admission_review_wing.md",
            "blocked_or_deferred_surfaces": ["workspace admission invocation", "preflight", "execution", "verification", "lifecycle closure"],
            "non_authority_boundary_summary": "Operator admission review packet is metadata-only and never authorization."
        }),
        "proof_command_manifest": _pretty_json({"metadata_only": True, "reviewer_proof_only": True, "default_execution": "not_run", "commands": [record.to_dict() for record in commands]}),
        "local_diagnostic_effect_capability": _pretty_json({
            "metadata_only": True,
            "reviewer_proof_only": True,
            "capability_available": True,
            "explicit_command_required": True,
            "run_by_reviewer_proof_bundle_default": False,
            "proof_bundle_effect_performed": False,
            "proof_bundle_host_mutation_performed": False,
            "first_intentionally_real_effect_pilot": True,
            "only_real_effect_when_explicitly_run": "write one deterministic diagnostic artifact to caller-supplied local output directory",
            "command": "python scripts/run_local_diagnostic_effect.py --output-dir /tmp/sentientos-local-effect --summary",
            "no_fan_pwm_thermal_power_service_cleanup": True,
            "no_network_provider_prompt_subprocess_shell_control_plane": True,
            "rollback_execution_deferred_by_default": False,
            "matching_exact_artifact_rollback_available_by_explicit_command_only": True,
        }),
        "local_diagnostic_rollback_capability": _pretty_json({
            "metadata_only": True,
            "reviewer_proof_only": True,
            "capability_available": True,
            "explicit_command_required": True,
            "run_by_reviewer_proof_bundle_default": False,
            "proof_bundle_rollback_performed": False,
            "proof_bundle_host_mutation_performed": False,
            "first_intentionally_real_rollback_pilot": True,
            "only_real_rollback_when_explicitly_run": "delete the exact diagnostic artifact proven by receipt, rollback plan, scope, and digest",
            "command": "python scripts/run_local_diagnostic_rollback.py --effect-receipt <receipt.json> --rollback-plan <rollback-plan.json> --output-dir-scope /tmp/sentientos-local-effect --summary",
            "not_general_cleanup": True,
            "no_directory_recursive_wildcard_or_unrelated_delete": True,
            "no_fan_pwm_thermal_power_service_package_driver": True,
            "no_network_provider_prompt_subprocess_shell_control_plane": True,
        }),
        "local_effect_transaction_ledger_capability": _pretty_json({
            "metadata_only": True,
            "reviewer_proof_only": True,
            "capability_available": True,
            "explicit_command_required": True,
            "run_by_reviewer_proof_bundle_default": False,
            "proof_bundle_effect_performed": False,
            "proof_bundle_rollback_performed": False,
            "proof_bundle_ledger_built_by_default": False,
            "proof_bundle_host_mutation_performed": False,
            "transaction_ledger_exists": True,
            "performs_no_new_host_effect_by_default": True,
            "builds_from_explicit_effect_and_rollback_record_files": True,
            "command": "python scripts/build_local_effect_transaction_ledger.py --effect-receipt <effect_receipt.json> --postcondition-check <postcondition.json> --production-audit <audit.json> --rollback-plan <rollback_plan.json> --summary",
            "detects_open_orphaned_incomplete_contradicted_and_closed_transactions": True,
            "general_cleanup_hardware_service_network_provider_prompt_remain_blocked": True,
            "no_fan_pwm_thermal_power_service_package_driver": True,
            "no_network_provider_prompt_subprocess_shell_control_plane": True,
        }),

        "builtin_local_effect_runner_capability": _pretty_json({
            "metadata_only": True,
            "reviewer_proof_only": True,
            "capability_available": True,
            "built_in_runner_exists": True,
            "first_actual_delegated_runner_implementation": True,
            "bounded_builtin_runner_only": True,
            "in_process_only": True,
            "explicit_command_required": True,
            "run_by_reviewer_proof_bundle_default": False,
            "proof_bundle_runner_invoked": False,
            "proof_bundle_effect_performed": False,
            "proof_bundle_rollback_performed": False,
            "proof_bundle_host_mutation_performed": False,
            "supported_action_kinds": ["local_diagnostic_artifact_write", "local_diagnostic_exact_rollback", "workspace_scoped_file_update", "workspace_scoped_file_exact_rollback"],
            "not_general_runner_framework": True,
            "no_subprocess_shell_network_provider_prompt": True,
            "no_hardware_service_power_general_cleanup": True,
            "delegated_runners_do_not_inherit_ambient_authority": True,
            "proof_command": "python scripts/run_builtin_local_effect_runner.py --action local_diagnostic_artifact_write --output-dir /tmp/sentientos-local-effect-runner --summary",
            "rollback_proof_command": "python scripts/run_builtin_local_effect_runner.py --action local_diagnostic_exact_rollback --effect-receipt <effect_receipt.json> --rollback-plan <rollback_plan.json> --output-dir-scope /tmp/sentientos-local-effect-runner --summary",
        }),

        "builtin_runner_transaction_orchestrator_capability": _pretty_json({
            "metadata_only": True,
            "reviewer_proof_only": True,
            "capability_available": True,
            "orchestrator_exists": True,
            "bounded_transaction_orchestrator_only": True,
            "supports_only_bounded_builtin_runner_diagnostic_write_and_exact_rollback": True,
            "supported_runner_actions": ["local_diagnostic_artifact_write", "local_diagnostic_exact_rollback"],
            "can_build_transaction_ledger_explicitly": True,
            "explicit_command_required": True,
            "run_by_reviewer_proof_bundle_default": False,
            "proof_bundle_orchestrator_invoked": False,
            "proof_bundle_effect_performed": False,
            "proof_bundle_rollback_performed": False,
            "proof_bundle_ledger_built_by_default": False,
            "proof_bundle_host_mutation_performed": False,
            "not_general_runner_framework": True,
            "no_subprocess_shell_network_provider_prompt": True,
            "no_hardware_service_power_general_cleanup": True,
            "delegated_runners_do_not_inherit_ambient_authority": True,
            "partial_state_not_hidden": True,
            "proof_command_status": "proof_command_not_run",
            "proof_command": "python scripts/run_builtin_runner_transaction.py --output-dir /tmp/sentientos-builtin-runner-transaction --mode diagnostic_write_rollback_with_ledger --ledger-output /tmp/sentientos-builtin-runner-transaction/transaction_ledger.json --summary",
        }),
        "workspace_file_effect_capability": _pretty_json({
            "metadata_only": True,
            "reviewer_proof_only": True,
            "capability_available": True,
            "explicit_command_required": True,
            "api_available": True,
            "command_available": True,
            "run_by_reviewer_proof_bundle_default": False,
            "proof_bundle_effect_performed": False,
            "proof_bundle_rollback_performed": False,
            "proof_bundle_host_mutation_performed": False,
            "supports_exactly_one_workspace_scoped_file_target": True,
            "captures_preimage_before_replacement": True,
            "distinguishes_new_file_creation_from_replacement": True,
            "supports_exact_rollback": True,
            "rollback_removes_only_exact_created_target_or_restores_exact_preimage": True,
            "not_general_filesystem_access": True,
            "not_cleanup": True,
            "no_recursive_wildcard_unrelated_delete": True,
            "no_subprocess_shell_network_provider_prompt": True,
            "no_hardware_service_power_general_cleanup": True,
            "builtin_runner_support_deferred": False,
            "proof_command_status": "proof_command_not_run",
            "proof_command": "python scripts/run_workspace_file_effect.py --workspace-root /tmp/sentientos-workspace-file-effect --target demo.txt --payload \"hello\" --summary",
            "rollback_proof_command": "python scripts/run_workspace_file_effect.py --workspace-root /tmp/sentientos-workspace-file-effect --target demo.txt --payload \"hello\" --rollback --summary",
        }),

        "workspace_file_runner_transaction_capability": _pretty_json({
            "metadata_only": True,
            "reviewer_proof_only": True,
            "capability_available": True,
            "built_in_runner_can_invoke_workspace_scoped_file_update": True,
            "built_in_runner_can_invoke_workspace_scoped_file_exact_rollback": True,
            "in_process_only": True,
            "transaction_ledger_can_be_built_explicitly": True,
            "run_by_reviewer_proof_bundle_default": False,
            "proof_bundle_runner_invoked": False,
            "proof_bundle_ledger_built_by_default": False,
            "proof_bundle_effect_performed": False,
            "proof_bundle_rollback_performed": False,
            "proof_bundle_host_mutation_performed": False,
            "one_explicit_target_only": True,
            "not_general_filesystem_access": True,
            "not_cleanup": True,
            "no_recursive_wildcard_unrelated_delete": True,
            "no_subprocess_shell_network_provider_prompt": True,
            "no_hardware_service_power_fan_thermal": True,
            "runner_update_proof_command": "python scripts/run_builtin_local_effect_runner.py --action workspace_scoped_file_update --workspace-root /tmp/sentientos-workspace-runner --target demo.txt --payload \"hello\" --summary",
            "runner_rollback_proof_command": "python scripts/run_builtin_local_effect_runner.py --action workspace_scoped_file_exact_rollback --workspace-effect-receipt <workspace_effect_receipt.json> --workspace-rollback-plan <workspace_rollback_plan.json> --workspace-root-scope /tmp/sentientos-workspace-runner --summary",
            "ledger_proof_command": "python scripts/build_workspace_file_transaction_ledger.py --effect-receipt <workspace_effect_receipt.json> --preimage <workspace_preimage.json> --postcondition-check <workspace_postcondition_check.json> --production-audit <workspace_production_audit.json> --rollback-plan <workspace_rollback_plan.json> --summary",
        }),

        "workspace_file_transaction_orchestrator_capability": _pretty_json({
            "metadata_only": True,
            "reviewer_proof_only": True,
            "capability_available": True,
            "workspace_transaction_orchestrator_support": "implemented",
            "supports_only_workspace_file_update_exact_rollback_ledger_modes": True,
            "supported_modes": ("workspace_file_update_only", "workspace_file_update_with_rollback", "workspace_file_update_with_ledger", "workspace_file_update_rollback_with_ledger"),
            "uses_existing_builtin_runner_workspace_actions_only": True,
            "uses_existing_workspace_transaction_ledger_helpers_only": True,
            "one_explicit_target_only": True,
            "run_by_reviewer_proof_bundle_default": False,
            "proof_bundle_orchestrator_invoked": False,
            "proof_bundle_runner_invoked": False,
            "proof_bundle_ledger_built_by_default": False,
            "proof_bundle_effect_performed": False,
            "proof_bundle_rollback_performed": False,
            "proof_bundle_host_mutation_performed": False,
            "not_general_filesystem_access": True,
            "not_cleanup": True,
            "no_recursive_wildcard_unrelated_delete": True,
            "no_subprocess_shell_network_provider_prompt": True,
            "no_hardware_service_power_fan_thermal": True,
            "partial_state_visible_if_rollback_or_ledger_fails": True,
            "proof_command_status": "proof_command_not_run",
            "proof_command": "python scripts/run_builtin_runner_transaction.py --mode workspace_file_update_rollback_with_ledger --workspace-root /tmp/sentientos-workspace-transaction --target demo.txt --payload \"hello\" --ledger-output /tmp/sentientos-workspace-transaction/workspace_transaction_ledger.json --summary",
        }),
        "host_steward_boundary_posture": _pretty_json({
            "metadata_only": True,
            "reviewer_proof_only": True,
            "host_steward_boundary_only": True,
            "proof_statement": "Host steward authority may be broad at the top level under operator delegation, but delegated runners do not inherit ambient authority.",
            "delegated_runners_do_not_inherit_ambient_authority": True,
            "no_runner_executes_by_default": True,
            "containment_profiles_are_not_live_sandbox_execution": True,
            "backend_declarations_do_not_load_or_invoke_backends": True,
            "grant_scaffolds_do_not_issue_live_runner_grants": True,
            "boundary_assessments_do_not_authorize_runner_execution": True,
            "proof_bundle_effect_performed": False,
            "proof_bundle_rollback_performed": False,
            "proof_bundle_ledger_built_by_default": False,
            "runner_executed": False,
            "live_runner_grant_issued": False,
            "backend_loaded": False,
            "backend_invoked": False,
            "host_mutation_performed": False,
            "network_performed": False,
            "provider_invocation_performed": False,
            "prompt_assembly_performed": False,
            "subprocess_execution_performed": False,
            "shell_execution_performed": False,
            "summary": summarize_host_steward_boundary_wing(host_steward_boundary),
            "records": host_steward_boundary.to_dict(),
        }),
        "reviewer_readme": _readme_text(manifest_id, trace.digest),
    }
    artifact_records = tuple(_artifact(kind, content) for kind, content in contents.items())
    # The manifest artifact record describes the canonical manifest payload before
    # the final pretty JSON wrapper is materialized; this avoids recursive digest
    # ambiguity while still giving reviewers a stable manifest payload digest.
    manifest_artifact = ReviewerProofBundleArtifact(
        artifact_id="reviewer-proof-bundle-manifest",
        artifact_kind="bundle_manifest",
        relative_path=BUNDLE_FILE_NAMES["bundle_manifest"],
        media_type="application/json",
        digest="pending",
        byte_count=0,
    )
    manifest = ReviewerProofBundleManifest(
        manifest_id=manifest_id,
        scenario_id=trace.scenario_id,
        scenario_label=trace.scenario_label,
        bundle_status="reviewer_proof_bundle_ready",
        created_at=created_at,
        trace_id=trace.trace_id,
        trace_digest=trace.digest,
        artifact_records=artifact_records + (manifest_artifact,),
        proof_command_records=commands,
        blocked_action_labels=BLOCKED_ACTION_LABELS,
        deferred_capability_labels=DEFERRED_ACTION_LABELS,
        warning_codes=(),
        risk_codes=(),
        digest="",
    )
    manifest = replace(manifest, digest=reviewer_proof_bundle_manifest_digest(manifest))
    manifest_json = _pretty_json(manifest.to_dict())
    manifest_artifact = replace(
        manifest_artifact,
        digest=reviewer_proof_artifact_digest(manifest_json),
        byte_count=len(manifest_json.encode("utf-8")),
    )
    manifest = replace(manifest, artifact_records=artifact_records + (manifest_artifact,))
    manifest = replace(manifest, digest=reviewer_proof_bundle_manifest_digest(manifest))
    contents["bundle_manifest"] = _pretty_json(manifest.to_dict())
    return {"manifest": manifest, "artifacts": contents, "trace": trace, "capability_registry": registry, "safety_gates": safety_gates, "live_grant_readiness": live_grant_readiness, "local_authorization": local_authorization, "fulfillment_authorization": fulfillment_authorization, "executor_contract": executor_contract, "dry_run_execution": dry_run_execution, "dry_run_audit_closure": dry_run_audit_closure, "real_effect_admission": real_effect_admission, "host_steward_boundary": host_steward_boundary}


def validate_reviewer_proof_bundle_manifest(manifest: ReviewerProofBundleManifest | Mapping[str, Any]) -> ReviewerProofBundleValidationResult:
    payload = manifest.to_dict() if isinstance(manifest, ReviewerProofBundleManifest) else dict(manifest)
    findings: list[str] = []
    if not payload.get("manifest_id"):
        findings.append("missing_manifest_id")
    if payload.get("bundle_status") not in REVIEWER_PROOF_BUNDLE_STATUSES:
        findings.append("unknown_bundle_status")
    if not payload.get("metadata_only", False):
        findings.append("manifest_not_metadata_only")
    if not payload.get("reviewer_proof_only", False):
        findings.append("manifest_not_reviewer_proof_only")
    for flag in FORBIDDEN_MANIFEST_FLAGS:
        if payload.get(flag, False):
            findings.append(f"manifest_forbidden_flag:{flag}")
    artifacts = payload.get("artifact_records", ())
    if not isinstance(artifacts, (list, tuple)) or not artifacts:
        findings.append("missing_artifact_records")
        artifacts = ()
    seen_kinds: set[str] = set()
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, Mapping):
            findings.append(f"artifact_not_mapping:{index}")
            continue
        kind = str(artifact.get("artifact_kind", ""))
        seen_kinds.add(kind)
        if kind not in REVIEWER_PROOF_ARTIFACT_KINDS:
            findings.append(f"unknown_artifact_kind:{kind}")
        if not artifact.get("metadata_only", False):
            findings.append(f"artifact_not_metadata_only:{kind}")
        for flag in ("contains_live_host_data", "contains_prompt_text", "contains_secret_material", "contains_provider_material"):
            if artifact.get(flag, False):
                findings.append(f"artifact_forbidden_flag:{kind}:{flag}")
        if ".." in Path(str(artifact.get("relative_path", ""))).parts:
            findings.append(f"artifact_relative_path_escapes:{kind}")
    missing = REVIEWER_PROOF_ARTIFACT_KINDS - seen_kinds
    if missing:
        findings.append("missing_artifact_kinds:" + ",".join(sorted(missing)))
    commands = payload.get("proof_command_records", ())
    if not isinstance(commands, (list, tuple)) or not commands:
        findings.append("missing_proof_command_records")
        commands = ()
    for index, command in enumerate(commands):
        if not isinstance(command, Mapping):
            findings.append(f"proof_command_not_mapping:{index}")
            continue
        if command.get("status") not in REVIEWER_PROOF_COMMAND_STATUSES:
            findings.append(f"unknown_proof_command_status:{command.get('command_id', index)}")
        if command.get("executed", False) and command.get("status") == "proof_command_not_run":
            findings.append(f"proof_command_executed_but_not_run:{command.get('command_id', index)}")
    for label in DEFERRED_ACTION_LABELS:
        if label not in tuple(payload.get("deferred_capability_labels", ())):
            findings.append(f"missing_deferred_label:{label}")
    return ReviewerProofBundleValidationResult(not findings, tuple(findings))


def summarize_reviewer_proof_bundle_manifest(manifest: ReviewerProofBundleManifest | Mapping[str, Any]) -> dict[str, Any]:
    payload = manifest.to_dict() if isinstance(manifest, ReviewerProofBundleManifest) else dict(manifest)
    return {
        "manifest_id": payload.get("manifest_id"),
        "scenario_id": payload.get("scenario_id"),
        "bundle_status": payload.get("bundle_status"),
        "artifact_count": len(payload.get("artifact_records", ()) or ()),
        "proof_command_count": len(payload.get("proof_command_records", ()) or ()),
        "proof_commands_executed": sum(1 for record in payload.get("proof_command_records", ()) if isinstance(record, Mapping) and record.get("executed")),
        "metadata_only": payload.get("metadata_only"),
        "reviewer_proof_only": payload.get("reviewer_proof_only"),
        "live_host_collection_performed": payload.get("live_host_collection_performed"),
        "live_authorization_granted": payload.get("live_authorization_granted"),
        "effect_performed": payload.get("effect_performed"),
        "host_mutation_performed": payload.get("host_mutation_performed"),
        "network_performed": payload.get("network_performed"),
        "provider_invocation_performed": payload.get("provider_invocation_performed"),
        "prompt_assembly_performed": payload.get("prompt_assembly_performed"),
        "digest": payload.get("digest"),
    }


def write_reviewer_proof_bundle(
    output_dir: str | Path,
    payload: Mapping[str, Any] | None = None,
    *,
    force: bool = False,
    manifest_only: bool = False,
) -> tuple[Path, ...]:
    path = Path(output_dir)
    if not str(output_dir):
        raise ValueError("output directory is required")
    anchor_path = Path(path.anchor)
    if path == anchor_path or path.resolve() == anchor_path.resolve():
        raise ValueError("refusing to write bundle to filesystem root")
    if path.exists() and not path.is_dir():
        raise ValueError("output path must be a directory, not a file")
    path.mkdir(parents=True, exist_ok=True)
    bundle_payload = dict(payload or build_reviewer_proof_bundle_payload())
    artifacts = dict(bundle_payload["artifacts"])
    selected = {"bundle_manifest": artifacts["bundle_manifest"]} if manifest_only else artifacts
    targets = tuple(path / BUNDLE_FILE_NAMES[kind] for kind in selected)
    existing = tuple(target for target in targets if target.exists())
    if existing and not force:
        raise FileExistsError("bundle files already exist; pass --force to overwrite: " + ", ".join(str(target) for target in existing))
    written: list[Path] = []
    for kind in sorted(selected, key=lambda item: BUNDLE_FILE_NAMES[item]):
        target = path / BUNDLE_FILE_NAMES[kind]
        if target.parent != path:
            raise ValueError("bundle target escaped output directory")
        target.write_text(selected[kind], encoding="utf-8")
        written.append(target)
    return tuple(written)
