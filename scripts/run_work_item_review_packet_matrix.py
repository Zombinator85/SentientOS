from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Callable, TypedDict


@dataclass(frozen=True)
class MatrixCommand:
    label: str
    command: tuple[str, ...]
    required: bool = True


class MatrixResult(TypedDict):
    label: str
    command: list[str]
    required: bool
    exit_code: int
    duration_seconds: float
    output_tail: str


class MatrixReport(TypedDict, total=False):
    generated_at: str
    status: str
    command_count: int
    required_failure_count: int
    required_failures: list[str]
    results: list[MatrixResult]
    strict_audit_repair_command: str
    strict_audit_auto_repair_exit_code: int


def default_matrix_commands() -> list[MatrixCommand]:
    return [
        MatrixCommand("selective_memory_distillation_contract_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_selective_memory_distillation_contract.py", "tests/test_build_selective_memory_distillation_contract_script.py")),
        MatrixCommand("selective_memory_distillation_receipt_gate_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_selective_memory_distillation_receipt_gate.py", "tests/test_build_selective_memory_distillation_receipt_gate_script.py")),
        MatrixCommand("selective_memory_tomb_receipt_verifier_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_selective_memory_tomb_receipt_verifier.py", "tests/test_build_selective_memory_tomb_receipt_verifier_script.py")),
        MatrixCommand("governed_memory_writer_adapter_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_governed_memory_writer_adapter.py", "tests/test_build_governed_memory_writer_adapter_script.py")),
        MatrixCommand("live_memory_boundary_admission_gate_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_live_memory_boundary_admission_gate.py", "tests/test_build_live_memory_boundary_admission_gate_script.py")),
        MatrixCommand("memory_commit_plan_packet_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_memory_commit_plan_packet.py", "tests/test_build_memory_commit_plan_packet_script.py")),
        MatrixCommand("memory_commit_operator_approval_packet_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_memory_commit_operator_approval_packet.py", "tests/test_build_memory_commit_operator_approval_packet_script.py")),
        MatrixCommand("memory_commit_execution_gate_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_memory_commit_execution_gate.py", "tests/test_build_memory_commit_execution_gate_script.py")),
        MatrixCommand("live_memory_commit_dry_run_adapter_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_live_memory_commit_dry_run_adapter.py", "tests/test_build_live_memory_commit_dry_run_adapter_script.py")),
        MatrixCommand("live_commit_safety_interlock_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_live_commit_safety_interlock.py", "tests/test_build_live_commit_safety_interlock_script.py")),
        MatrixCommand("sandboxed_live_memory_commit_adapter_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_sandboxed_live_memory_commit_adapter.py", "tests/test_build_sandboxed_live_memory_commit_adapter_script.py")),
        MatrixCommand("sandboxed_live_memory_commit_adapter_gate_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_sandboxed_live_memory_commit_adapter_gate.py", "tests/test_build_sandboxed_live_memory_commit_adapter_gate_script.py")),
        MatrixCommand("real_memory_root_admission_gate_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_real_memory_root_admission_gate.py", "tests/test_build_real_memory_root_admission_gate_script.py")),
        MatrixCommand("real_memory_root_admission_packet_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_real_memory_root_admission_packet.py", "tests/test_build_real_memory_root_admission_packet_script.py")),
        MatrixCommand("final_live_memory_commit_review_gate_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_final_live_memory_commit_review_gate.py", "tests/test_build_final_live_memory_commit_review_gate_script.py")),
        MatrixCommand("real_live_memory_commit_adapter_readiness_envelope_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_real_live_memory_commit_adapter_readiness_envelope.py", "tests/test_build_real_live_memory_commit_adapter_readiness_envelope_script.py")),
        MatrixCommand("explicit_live_memory_runtime_execution_gate_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_explicit_live_memory_runtime_execution_gate.py", "tests/test_build_explicit_live_memory_runtime_execution_gate_script.py")),
        MatrixCommand("real_live_memory_commit_executor_plan_packet_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_real_live_memory_commit_executor_plan_packet.py", "tests/test_build_real_live_memory_commit_executor_plan_packet_script.py")),
        MatrixCommand("live_executor_lock_lease_gate_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_live_executor_lock_lease_gate.py", "tests/test_build_live_executor_lock_lease_gate_script.py")),
        MatrixCommand("live_executor_preflight_packet_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_live_executor_preflight_packet.py", "tests/test_build_live_executor_preflight_packet_script.py")),
        MatrixCommand("live_executor_activation_record_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_live_executor_activation_record.py", "tests/test_build_live_executor_activation_record_script.py")),
        MatrixCommand("live_executor_invocation_harness_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_live_executor_invocation_harness.py", "tests/test_build_live_executor_invocation_harness_script.py")),
        MatrixCommand("real_live_memory_commit_executor_implementation_skeleton_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_real_live_memory_commit_executor_implementation_skeleton.py", "tests/test_build_real_live_memory_commit_executor_implementation_skeleton_script.py")),
        MatrixCommand("real_live_memory_commit_executor_enablement_gate_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_real_live_memory_commit_executor_enablement_gate.py", "tests/test_build_real_live_memory_commit_executor_enablement_gate_script.py")),
        MatrixCommand("constrained_executor_enablement_path_packet_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_constrained_executor_enablement_path_packet.py", "tests/test_build_constrained_executor_enablement_path_packet_script.py")),
        MatrixCommand("future_live_memory_commit_execution_gate_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_future_live_memory_commit_execution_gate.py", "tests/test_build_future_live_memory_commit_execution_gate_script.py")),
        MatrixCommand("live_commit_execution_packet_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_live_commit_execution_packet.py", "tests/test_build_live_commit_execution_packet_script.py")),
        MatrixCommand("real_executor_runtime_enablement_packet_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_real_executor_runtime_enablement_packet.py", "tests/test_build_real_executor_runtime_enablement_packet_script.py")),
        MatrixCommand("real_executor_runtime_gate_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_real_executor_runtime_gate.py", "tests/test_build_real_executor_runtime_gate_script.py")),
        MatrixCommand("guarded_executor_path_packet_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_guarded_executor_path_packet.py", "tests/test_build_guarded_executor_path_packet_script.py")),
        MatrixCommand("guarded_executor_invocation_packet_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_guarded_executor_invocation_packet.py", "tests/test_build_guarded_executor_invocation_packet_script.py")),
        MatrixCommand("real_executor_invocation_gate_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_real_executor_invocation_gate.py", "tests/test_build_real_executor_invocation_gate_script.py")),
        MatrixCommand("real_executor_run_packet_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_real_executor_run_packet.py", "tests/test_build_real_executor_run_packet_script.py")),
        MatrixCommand("real_executor_run_gate_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_real_executor_run_gate.py", "tests/test_build_real_executor_run_gate_script.py")),
        MatrixCommand("real_executor_execution_plan_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_real_executor_execution_plan.py", "tests/test_build_real_executor_execution_plan_script.py")),
        MatrixCommand("real_executor_execution_gate_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_real_executor_execution_gate.py", "tests/test_build_real_executor_execution_gate_script.py")),
        MatrixCommand("real_executor_execution_authorization_packet_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_real_executor_execution_authorization_packet.py", "tests/test_build_real_executor_execution_authorization_packet_script.py")),
        MatrixCommand("real_executor_execution_authorization_gate_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_real_executor_execution_authorization_gate.py", "tests/test_build_real_executor_execution_authorization_gate_script.py")),
        MatrixCommand("real_executor_execution_permit_packet_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_real_executor_execution_permit_packet.py", "tests/test_build_real_executor_execution_permit_packet_script.py")),
        MatrixCommand("real_executor_execution_permit_gate_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_real_executor_execution_permit_gate.py", "tests/test_build_real_executor_execution_permit_gate_script.py")),
        MatrixCommand("real_executor_execution_release_packet_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_real_executor_execution_release_packet.py", "tests/test_build_real_executor_execution_release_packet_script.py")),
        MatrixCommand("real_executor_execution_release_gate_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_real_executor_execution_release_gate.py", "tests/test_build_real_executor_execution_release_gate_script.py")),
        MatrixCommand("real_executor_execution_activation_packet_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_real_executor_execution_activation_packet.py", "tests/test_build_real_executor_execution_activation_packet_script.py")),
        MatrixCommand("real_executor_execution_activation_gate_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_real_executor_execution_activation_gate.py", "tests/test_build_real_executor_execution_activation_gate_script.py")),
        MatrixCommand("real_executor_execution_invocation_packet_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_real_executor_execution_invocation_packet.py", "tests/test_build_real_executor_execution_invocation_packet_script.py")),
        MatrixCommand("real_executor_execution_invocation_gate_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_real_executor_execution_invocation_gate.py", "tests/test_build_real_executor_execution_invocation_gate_script.py")),
        MatrixCommand("real_executor_execution_preflight_packet_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_real_executor_execution_preflight_packet.py", "tests/test_build_real_executor_execution_preflight_packet_script.py")),
        MatrixCommand("real_executor_execution_preflight_gate_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_real_executor_execution_preflight_gate.py", "tests/test_build_real_executor_execution_preflight_gate_script.py")),
        MatrixCommand("real_executor_execution_lock_lease_packet_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_real_executor_execution_lock_lease_packet.py", "tests/test_build_real_executor_execution_lock_lease_packet_script.py")),
        MatrixCommand("real_executor_execution_lock_lease_gate_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_real_executor_execution_lock_lease_gate.py", "tests/test_build_real_executor_execution_lock_lease_gate_script.py")),
        MatrixCommand("real_executor_execution_commit_plan_packet_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_real_executor_execution_commit_plan_packet.py", "tests/test_build_real_executor_execution_commit_plan_packet_script.py")),
        MatrixCommand("real_executor_execution_commit_plan_gate_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_real_executor_execution_commit_plan_gate.py", "tests/test_build_real_executor_execution_commit_plan_gate_script.py")),
        MatrixCommand("real_executor_execution_commit_window_packet_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_real_executor_execution_commit_window_packet.py", "tests/test_build_real_executor_execution_commit_window_packet_script.py")),
        MatrixCommand("real_live_memory_commit_execution_gate_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_real_live_memory_commit_execution_gate.py", "tests/test_build_real_live_memory_commit_execution_gate_script.py")),
        MatrixCommand("real_live_memory_commit_execution_packet_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_real_live_memory_commit_execution_packet.py", "tests/test_build_real_live_memory_commit_execution_packet_script.py")),
        MatrixCommand("real_live_memory_commit_adapter_admission_gate_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_real_live_memory_commit_adapter_admission_gate.py", "tests/test_build_real_live_memory_commit_adapter_admission_gate_script.py")),
        MatrixCommand("real_live_memory_commit_adapter_admission_packet_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_real_live_memory_commit_adapter_admission_packet.py", "tests/test_build_real_live_memory_commit_adapter_admission_packet_script.py")),
        MatrixCommand("real_live_memory_commit_adapter_readiness_gate_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_real_live_memory_commit_adapter_readiness_gate.py", "tests/test_build_real_live_memory_commit_adapter_readiness_gate_script.py")),
        MatrixCommand("review_packet_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_work_item_review_packet.py", "tests/test_build_work_item_review_packet_script.py")),
        MatrixCommand("authority_closure_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_work_item_authority_claims.py", "tests/test_work_item_dry_run_closure.py", "tests/test_build_work_item_dry_run_closure_script.py")),
        MatrixCommand("dry_run_adapter_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_work_item_dry_run_adapter.py", "tests/test_run_work_item_dry_run_script.py")),
        MatrixCommand("handoff_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_work_item_lifecycle_handoff.py", "tests/test_plan_work_item_handoff_script.py")),
        MatrixCommand("intake_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_work_item_intake.py", "tests/test_intake_work_item_script.py")),
        MatrixCommand("promotion_gate_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_work_item_promotion_gate.py", "tests/test_evaluate_work_item_promotion_script.py")),
        MatrixCommand("operator_admission_review_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_work_item_operator_admission_review.py", "tests/test_build_operator_admission_review_script.py")),
        MatrixCommand("operator_confirmed_admission_run_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_work_item_admission_run.py", "tests/test_run_operator_confirmed_admission_script.py")),
        MatrixCommand("operator_confirmed_preflight_run_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_work_item_preflight_run.py", "tests/test_run_operator_confirmed_preflight_script.py")),
        MatrixCommand("operator_execution_review_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_work_item_execution_review.py", "tests/test_build_operator_execution_review_script.py")),
        MatrixCommand("operator_confirmed_execution_run_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_work_item_execution_run.py", "tests/test_run_operator_confirmed_execution_script.py")),
        MatrixCommand("operator_confirmed_verification_run_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_work_item_verification_run.py", "tests/test_run_operator_confirmed_verification_script.py")),
        MatrixCommand("operator_lifecycle_closure_review_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_work_item_lifecycle_closure_review.py", "tests/test_build_operator_lifecycle_closure_review_script.py")),
        MatrixCommand("work_item_lifecycle_completion_dossier_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_work_item_lifecycle_completion_dossier.py", "tests/test_build_work_item_lifecycle_completion_dossier_script.py")),
        MatrixCommand("codex_task_scaffold_verifier_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_codex_task_scaffold_verifier.py", "tests/test_verify_codex_task_scaffold_script.py")),
        MatrixCommand("work_item_lifecycle_completion_verifier_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_work_item_lifecycle_completion_verifier.py", "tests/test_verify_work_item_lifecycle_completion_dossier_script.py")),
        MatrixCommand("work_item_lifecycle_final_attestation_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_work_item_lifecycle_final_attestation.py", "tests/test_build_work_item_lifecycle_final_attestation_script.py")),
        MatrixCommand("work_item_lifecycle_attestation_index_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_work_item_lifecycle_attestation_index.py", "tests/test_build_work_item_lifecycle_attestation_index_script.py")),
        MatrixCommand("work_item_lifecycle_attestation_index_verifier_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_work_item_lifecycle_attestation_index_verifier.py", "tests/test_verify_work_item_lifecycle_attestation_index_script.py")),
        MatrixCommand("work_item_lifecycle_attestation_review_digest_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_work_item_lifecycle_attestation_review_digest.py", "tests/test_build_work_item_lifecycle_attestation_review_digest_script.py")),
        MatrixCommand("work_item_lifecycle_attestation_review_digest_verifier_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_work_item_lifecycle_attestation_review_digest_verifier.py", "tests/test_verify_work_item_lifecycle_attestation_review_digest_script.py")),
        MatrixCommand("work_item_lifecycle_attestation_review_digest_index_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_work_item_lifecycle_attestation_review_digest_index.py", "tests/test_build_work_item_lifecycle_attestation_review_digest_index_script.py")),
        MatrixCommand("work_item_lifecycle_attestation_review_digest_index_verifier_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_work_item_lifecycle_attestation_review_digest_index_verifier.py", "tests/test_verify_work_item_lifecycle_attestation_review_digest_index_script.py")),
        MatrixCommand("operator_confirmed_lifecycle_closure_run_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_work_item_lifecycle_closure_run.py", "tests/test_run_operator_confirmed_lifecycle_closure_script.py")),
                MatrixCommand("household_presence_camera_event_bridge_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_household_presence_camera_event_bridge.py", "tests/test_build_household_presence_camera_event_bridge_script.py")),
        MatrixCommand("household_presence_camera_capture_review_decision_ledger_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_household_presence_camera_capture_review_decision_ledger.py", "tests/test_build_household_presence_camera_capture_review_decision_ledger_script.py")),
        MatrixCommand("household_presence_camera_operator_review_trend_ledger_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_household_presence_camera_operator_review_trend_ledger.py", "tests/test_build_household_presence_camera_operator_review_trend_ledger_script.py")),
        MatrixCommand("household_presence_camera_operator_grant_renewal_request_packet_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_household_presence_camera_operator_grant_renewal_request_packet.py", "tests/test_build_household_presence_camera_operator_grant_renewal_request_packet_script.py")),
        MatrixCommand("household_presence_camera_dry_run_continuation_gate_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_household_presence_camera_dry_run_continuation_gate.py", "tests/test_build_household_presence_camera_dry_run_continuation_gate_script.py")),
        MatrixCommand("household_presence_camera_future_live_deferral_registry_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_household_presence_camera_future_live_deferral_registry.py", "tests/test_build_household_presence_camera_future_live_deferral_registry_script.py")),
        MatrixCommand("household_presence_camera_review_chain_summary_packet_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_household_presence_camera_review_chain_summary_packet.py", "tests/test_build_household_presence_camera_review_chain_summary_packet_script.py")),
        MatrixCommand("household_presence_layer_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_household_presence_layer.py", "tests/test_build_household_presence_layer_script.py")),
        MatrixCommand("proof_bundle_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_capability_registry.py", "tests/test_reviewer_proof_bundle.py", "tests/test_build_reviewer_proof_bundle_script.py", "tests/test_reviewer_release_readiness_index.py", "tests/test_codex_operating_doctrine_docs.py")),
        MatrixCommand("codex_pr_validation_evidence_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_codex_pr_validation_evidence.py", "tests/test_codex_pr_validation_evidence_script.py")),
        MatrixCommand("codex_pr_landing_gate_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_codex_pr_landing_gate.py", "tests/test_codex_pr_landing_gate_script.py")),
        MatrixCommand("codex_pr_metadata_guard_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_codex_pr_metadata_guard.py", "tests/test_codex_pr_metadata_guard_script.py")),
        MatrixCommand("targeted_mypy", ("python", "-m", "mypy", "sentientos/work_item_authority_claims.py", "sentientos/work_item_intake.py", "scripts/intake_work_item.py", "sentientos/work_item_lifecycle_handoff.py", "scripts/plan_work_item_handoff.py", "sentientos/work_item_lifecycle_dry_run_adapter.py", "scripts/run_work_item_dry_run.py", "sentientos/work_item_dry_run_closure.py", "scripts/build_work_item_dry_run_closure.py", "sentientos/work_item_review_packet.py", "scripts/build_work_item_review_packet.py", "sentientos/work_item_promotion_gate.py", "scripts/evaluate_work_item_promotion.py", "sentientos/work_item_operator_admission_review.py", "scripts/build_operator_admission_review.py", "sentientos/work_item_admission_run.py", "scripts/run_operator_confirmed_admission.py", "sentientos/work_item_preflight_run.py", "scripts/run_operator_confirmed_preflight.py", "sentientos/work_item_execution_review.py", "scripts/build_operator_execution_review.py", "sentientos/work_item_execution_run.py", "scripts/run_operator_confirmed_execution.py", "sentientos/work_item_verification_run.py", "scripts/run_operator_confirmed_verification.py", "sentientos/work_item_lifecycle_closure_review.py", "scripts/build_operator_lifecycle_closure_review.py", "sentientos/work_item_lifecycle_closure_run.py", "scripts/run_operator_confirmed_lifecycle_closure.py", "sentientos/work_item_lifecycle_completion_dossier.py", "scripts/build_work_item_lifecycle_completion_dossier.py", "sentientos/work_item_lifecycle_completion_verifier.py", "scripts/verify_work_item_lifecycle_completion_dossier.py", "sentientos/codex_task_scaffold_verifier.py", "scripts/verify_codex_task_scaffold.py", "sentientos/codex_pr_validation_evidence.py", "scripts/codex_pr_validation_evidence.py", "sentientos/codex_pr_landing_gate.py", "scripts/codex_pr_landing_gate.py", "sentientos/codex_pr_metadata_guard.py", "scripts/codex_pr_metadata_guard.py", "sentientos/work_item_lifecycle_final_attestation.py", "scripts/build_work_item_lifecycle_final_attestation.py", "sentientos/work_item_lifecycle_attestation_index.py", "scripts/build_work_item_lifecycle_attestation_index.py", "sentientos/work_item_lifecycle_attestation_index_verifier.py", "scripts/verify_work_item_lifecycle_attestation_index.py", "sentientos/work_item_lifecycle_attestation_review_digest.py", "scripts/build_work_item_lifecycle_attestation_review_digest.py", "sentientos/work_item_lifecycle_attestation_review_digest_verifier.py", "scripts/verify_work_item_lifecycle_attestation_review_digest.py", "sentientos/work_item_lifecycle_attestation_review_digest_index.py", "scripts/build_work_item_lifecycle_attestation_review_digest_index.py", "sentientos/work_item_lifecycle_attestation_review_digest_index_verifier.py", "scripts/verify_work_item_lifecycle_attestation_review_digest_index.py", "sentientos/household_presence_camera_capture_review_decision_ledger.py", "scripts/build_household_presence_camera_capture_review_decision_ledger.py", "sentientos/household_presence_camera_operator_review_trend_ledger.py", "scripts/build_household_presence_camera_operator_review_trend_ledger.py", "sentientos/household_presence_camera_operator_grant_renewal_request_packet.py", "scripts/build_household_presence_camera_operator_grant_renewal_request_packet.py", "sentientos/household_presence_camera_dry_run_continuation_gate.py", "scripts/build_household_presence_camera_dry_run_continuation_gate.py", "sentientos/household_presence_camera_future_live_deferral_registry.py", "scripts/build_household_presence_camera_future_live_deferral_registry.py", "sentientos/household_presence_camera_review_chain_summary_packet.py", "scripts/build_household_presence_camera_review_chain_summary_packet.py", "sentientos/selective_memory_distillation_contract.py", "scripts/build_selective_memory_distillation_contract.py", "sentientos/selective_memory_distillation_receipt_gate.py", "scripts/build_selective_memory_distillation_receipt_gate.py", "sentientos/selective_memory_tomb_receipt_verifier.py", "scripts/build_selective_memory_tomb_receipt_verifier.py", "sentientos/governed_memory_writer_adapter.py", "scripts/build_governed_memory_writer_adapter.py", "sentientos/live_memory_boundary_admission_gate.py", "scripts/build_live_memory_boundary_admission_gate.py", "sentientos/memory_commit_plan_packet.py", "scripts/build_memory_commit_plan_packet.py", "sentientos/memory_commit_operator_approval_packet.py", "scripts/build_memory_commit_operator_approval_packet.py", "sentientos/memory_commit_execution_gate.py", "scripts/build_memory_commit_execution_gate.py", "sentientos/live_memory_commit_dry_run_adapter.py", "scripts/build_live_memory_commit_dry_run_adapter.py", "sentientos/live_commit_safety_interlock.py", "scripts/build_live_commit_safety_interlock.py", "sentientos/sandboxed_live_memory_commit_adapter.py", "scripts/build_sandboxed_live_memory_commit_adapter.py", "sentientos/sandboxed_live_memory_commit_adapter_gate.py", "scripts/build_sandboxed_live_memory_commit_adapter_gate.py", "sentientos/real_live_memory_commit_executor_plan_packet.py", "scripts/build_real_live_memory_commit_executor_plan_packet.py", "sentientos/live_executor_lock_lease_gate.py", "scripts/build_live_executor_lock_lease_gate.py", "sentientos/live_executor_preflight_packet.py", "scripts/build_live_executor_preflight_packet.py", "sentientos/live_executor_activation_record.py", "scripts/build_live_executor_activation_record.py", "sentientos/live_executor_invocation_harness.py", "scripts/build_live_executor_invocation_harness.py", "sentientos/real_live_memory_commit_executor_enablement_gate.py", "scripts/build_real_live_memory_commit_executor_enablement_gate.py", "sentientos/constrained_executor_enablement_path_packet.py", "scripts/build_constrained_executor_enablement_path_packet.py", "sentientos/live_commit_execution_packet.py", "scripts/build_live_commit_execution_packet.py", "sentientos/real_executor_runtime_enablement_packet.py", "scripts/build_real_executor_runtime_enablement_packet.py", "sentientos/real_executor_runtime_gate.py", "scripts/build_real_executor_runtime_gate.py", "sentientos/guarded_executor_path_packet.py", "scripts/build_guarded_executor_path_packet.py", "sentientos/guarded_executor_invocation_packet.py", "scripts/build_guarded_executor_invocation_packet.py", "sentientos/real_executor_invocation_gate.py", "scripts/build_real_executor_invocation_gate.py", "sentientos/real_executor_execution_authorization_packet.py", "scripts/build_real_executor_execution_authorization_packet.py", "sentientos/real_executor_execution_authorization_gate.py", "scripts/build_real_executor_execution_authorization_gate.py", "sentientos/real_executor_execution_release_packet.py", "scripts/build_real_executor_execution_release_packet.py", "sentientos/real_executor_execution_release_gate.py", "scripts/build_real_executor_execution_release_gate.py", "sentientos/real_executor_execution_activation_packet.py", "scripts/build_real_executor_execution_activation_packet.py", "sentientos/real_executor_execution_activation_gate.py", "scripts/build_real_executor_execution_activation_gate.py", "sentientos/real_executor_execution_invocation_packet.py", "scripts/build_real_executor_execution_invocation_packet.py", "sentientos/real_executor_execution_invocation_gate.py", "scripts/build_real_executor_execution_invocation_gate.py", "sentientos/real_executor_execution_preflight_packet.py", "scripts/build_real_executor_execution_preflight_packet.py", "sentientos/real_executor_execution_lock_lease_packet.py", "scripts/build_real_executor_execution_lock_lease_packet.py", "sentientos/real_executor_execution_lock_lease_gate.py", "scripts/build_real_executor_execution_lock_lease_gate.py", "sentientos/real_executor_execution_commit_plan_packet.py", "scripts/build_real_executor_execution_commit_plan_packet.py", "sentientos/real_executor_execution_commit_plan_gate.py", "scripts/build_real_executor_execution_commit_plan_gate.py", "sentientos/real_executor_execution_commit_window_packet.py", "scripts/build_real_executor_execution_commit_window_packet.py", "sentientos/real_live_memory_commit_execution_gate.py", "scripts/build_real_live_memory_commit_execution_gate.py", "sentientos/real_live_memory_commit_execution_packet.py", "scripts/build_real_live_memory_commit_execution_packet.py", "sentientos/real_live_memory_commit_adapter_readiness_gate.py", "scripts/build_real_live_memory_commit_adapter_readiness_gate.py", "sentientos/real_live_memory_commit_adapter_readiness_envelope.py", "scripts/build_real_live_memory_commit_adapter_readiness_envelope.py")),
        MatrixCommand("mypy_baseline", ("python", "scripts/check_mypy_baseline.py")),
        MatrixCommand("docs_check_deps", ("python", "scripts/build_docs.py", "--check-deps"), required=False),
        MatrixCommand("docs_build", ("python", "scripts/build_docs.py")),
        MatrixCommand("prompt_boundaries", ("python", "scripts/verify_context_hygiene_prompt_boundaries.py")),
        MatrixCommand("strict_audits", ("python", "verify_audits.py", "--strict")),
        MatrixCommand("audit_immutability", ("python", "scripts/audit_immutability_verifier.py")),
    ]


def _tail(text: str, lines: int = 30) -> str:
    parts = text.splitlines()
    return "\n".join(parts[-lines:])


def run_one(command: MatrixCommand, runner: Callable[[tuple[str, ...]], subprocess.CompletedProcess[str]]) -> MatrixResult:
    started = time.perf_counter()
    completed = runner(command.command)
    duration = round(time.perf_counter() - started, 3)
    output = completed.stdout
    if completed.stderr:
        output = f"{output}\n{completed.stderr}" if output else completed.stderr
    return {
        "label": command.label,
        "command": list(command.command),
        "required": command.required,
        "exit_code": completed.returncode,
        "duration_seconds": duration,
        "output_tail": _tail(output),
    }


def run_matrix(*, commands: list[MatrixCommand], runner: Callable[[tuple[str, ...]], subprocess.CompletedProcess[str]]) -> MatrixReport:
    results: list[MatrixResult] = []
    failed_required = False
    docs_check_passed = False

    for command in commands:
        if command.label == "docs_build" and not docs_check_passed:
            probe = next(item for item in results if item["label"] == "docs_check_deps")
            if probe["exit_code"] != 0:
                bootstrap = run_one(MatrixCommand("docs_bootstrap", ("python", "scripts/build_docs.py", "--bootstrap-docs"), required=False), runner)
                results.append(bootstrap)
                recheck = run_one(MatrixCommand("docs_check_deps_recheck", ("python", "scripts/build_docs.py", "--check-deps")), runner)
                results.append(recheck)
                docs_check_passed = recheck["exit_code"] == 0
                if recheck["exit_code"] != 0:
                    failed_required = True
            else:
                docs_check_passed = True

        result = run_one(command, runner)
        results.append(result)
        if command.label == "docs_check_deps":
            docs_check_passed = result["exit_code"] == 0
        if command.required and result["exit_code"] != 0:
            failed_required = True

    required_failures = [r["label"] for r in results if bool(r["required"]) and int(r["exit_code"]) != 0]
    summary: MatrixReport = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "failed" if failed_required else "passed",
        "command_count": len(results),
        "required_failure_count": len(required_failures),
        "required_failures": required_failures,
        "results": results,
    }
    return summary


def _default_runner(command: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, capture_output=True, text=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run full work-item review packet proof matrix with continue-on-failure behavior.")
    parser.add_argument("--summary", action="store_true", help="print compact human summary after JSON")
    parser.add_argument("--output", type=Path, help="optional JSON output path")
    parser.add_argument("--auto-repair-audits", action="store_true")
    args = parser.parse_args(argv)

    report = run_matrix(commands=default_matrix_commands(), runner=_default_runner)
    if any(r["label"]=="strict_audits" and r["exit_code"]!=0 for r in report["results"]):
        report["strict_audit_repair_command"]="python scripts/codex_strict_audit_repair.py diagnose --summary"
        if args.auto_repair_audits:
            cp=_default_runner(("python","scripts/codex_strict_audit_repair.py","repair","--allow-runtime-chain-reseal","--summary"))
            report["strict_audit_auto_repair_exit_code"]=cp.returncode
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.summary:
        for row in report["results"]:
            label = row["label"]
            code = row["exit_code"]
            print(f"[{label}] exit={code}")
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    return 1 if report["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
