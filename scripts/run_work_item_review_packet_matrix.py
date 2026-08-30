from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
import os
import signal
import time
from datetime import datetime, timezone
from typing import Callable, TypedDict


@dataclass(frozen=True)
class MatrixCommand:
    label: str
    command: tuple[str, ...]
    required: bool = True
    proof_required: bool = True
    execution_required: bool = True
    diagnostic_only: bool = False
    nonexecution_allowed: bool = False
    classification_reason: str | None = None


class MatrixResult(TypedDict, total=False):
    label: str
    command: list[str]
    required: bool
    proof_required: bool
    execution_required: bool
    diagnostic_only: bool
    nonexecution_allowed: bool
    classification_reason: str | None
    proof_status: str
    exit_code: int
    duration_seconds: float
    output_tail: str
    exit_reason: str | None
    tests_selected: int | None
    tests_executed: int | None
    tests_passed: int | None
    tests_skipped: int | None
    metrics_status: str | None


class MatrixReport(TypedDict, total=False):
    schema_version: str
    generated_at: str
    status: str
    command_count: int
    required_failure_count: int
    required_failures: list[str]
    diagnostic_failure_count: int
    nonproof_count: int
    results: list[MatrixResult]
    strict_audit_repair_command: str
    strict_audit_auto_repair_exit_code: int
    next_lane_index: int
    completed_labels: list[str]
    checkpoint_digest: str
    completion_status: str
    matrix_contract: dict[str, object]
    matrix_contract_digest: object
    workspace_binding: dict[str, object]
    resume_block_reasons: list[str]
    active_lane: dict[str, object] | None


MATRIX_SCHEMA = "sentientos.work_item_review_packet_matrix:v2"
GENERATED_PREFIXES = ("glow/", "pulse/", "artifacts/codex/", "sentientos_data/vow", "sentientos_data/runtime")


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def matrix_contract(commands: list[MatrixCommand]) -> dict[str, object]:
    manifest = [{"label": c.label, "command": list(c.command), "required": c.required,
                 "proof_required": c.proof_required, "execution_required": c.execution_required,
                 "diagnostic_only": c.diagnostic_only} for c in commands]
    return {"schema_version": MATRIX_SCHEMA, "command_count": len(commands), "lanes": manifest,
            "manifest_digest": _digest(manifest)}


def workspace_binding(commands: list[MatrixCommand], repo: Path = Path(".")) -> dict[str, object]:
    root = repo.resolve()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=root, text=True).strip()
    status = subprocess.check_output(["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=root, text=True)
    files: list[dict[str, str]] = []
    for line in status.splitlines():
        path = line[3:].split(" -> ")[-1]
        if path.startswith(GENERATED_PREFIXES):
            continue
        target = root / path
        content = target.read_bytes() if target.is_file() and not target.is_symlink() else b"<deleted-or-nonregular>"
        files.append({"path": path, "status": line[:2], "sha256": hashlib.sha256(content).hexdigest()})
    locks = []
    for name in ("pyproject.toml", "requirements-codex.txt", "requirements.txt", "uv.lock", "poetry.lock"):
        p = root / name
        if p.is_file():
            locks.append({"path": name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()})
    contract_digest = str(matrix_contract(commands)["manifest_digest"])
    payload: dict[str, object] = {"head_sha": head, "tracked_tree_sha": tree, "changed_files": sorted(files, key=lambda x: x["path"]),
        "dependency_digests": locks, "python_executable": str(Path(sys.executable).resolve()), "python_version": sys.version,
        "matrix_contract_digest": contract_digest}
    payload["binding_digest"] = _digest(payload)
    return payload


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)
    try:
        directory = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
    except OSError:
        pass


NONEXECUTION_DIAGNOSTIC_LANES = {
    "real_memory_root_admission_gate_tests",
    "real_memory_root_admission_packet_tests",
    "live_executor_lock_lease_gate_tests",
    "live_executor_activation_record_tests",
    "real_live_memory_commit_executor_implementation_skeleton_tests",
    "real_live_memory_commit_executor_enablement_gate_tests",
    "real_executor_run_gate_tests",
    "real_executor_execution_plan_tests",
    "real_executor_execution_gate_tests",
    "real_executor_execution_authorization_packet_tests",
    "real_executor_execution_authorization_gate_tests",
    "real_executor_execution_permit_packet_tests",
    "real_executor_execution_permit_gate_tests",
    "review_packet_tests",
    "authority_closure_tests",
    "dry_run_adapter_tests",
    "handoff_tests",
    "intake_tests",
    "promotion_gate_tests",
    "operator_admission_review_tests",
    "operator_confirmed_admission_run_tests",
    "operator_confirmed_preflight_run_tests",
    "operator_execution_review_tests",
    "operator_confirmed_execution_run_tests",
    "operator_confirmed_verification_run_tests",
    "operator_lifecycle_closure_review_tests",
    "work_item_lifecycle_completion_dossier_tests",
    "codex_task_scaffold_verifier_tests",
    "work_item_lifecycle_completion_verifier_tests",
    "work_item_lifecycle_final_attestation_tests",
    "work_item_lifecycle_attestation_index_tests",
    "work_item_lifecycle_attestation_index_verifier_tests",
    "work_item_lifecycle_attestation_review_digest_tests",
    "work_item_lifecycle_attestation_review_digest_verifier_tests",
    "work_item_lifecycle_attestation_review_digest_index_tests",
    "work_item_lifecycle_attestation_review_digest_index_verifier_tests",
    "operator_confirmed_lifecycle_closure_run_tests",
    "household_presence_camera_event_bridge_tests",
    "household_presence_camera_operator_grant_renewal_request_packet_tests",
    "household_presence_layer_tests",
    "codex_pr_validation_evidence_tests",
    "codex_pr_landing_gate_tests",
    "codex_pr_metadata_guard_tests",
}


def _classify_default_command(command: MatrixCommand) -> MatrixCommand:
    if command.label not in NONEXECUTION_DIAGNOSTIC_LANES:
        return command
    return MatrixCommand(
        label=command.label,
        command=command.command,
        required=False,
        proof_required=False,
        execution_required=False,
        diagnostic_only=True,
        nonexecution_allowed=True,
        classification_reason="known nonexecuted/skipped targeted lane; retained as diagnostic non-proof evidence",
    )


def default_matrix_commands() -> list[MatrixCommand]:
    commands = [
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
        MatrixCommand("sandboxed_live_memory_commit_adapter_packet_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_sandboxed_live_memory_commit_adapter_packet.py", "tests/test_build_sandboxed_live_memory_commit_adapter_packet_script.py")),
        MatrixCommand("sandboxed_live_memory_commit_adapter_envelope_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_sandboxed_live_memory_commit_adapter_envelope.py", "tests/test_build_sandboxed_live_memory_commit_adapter_envelope_script.py")),
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
        MatrixCommand("phase97_external_security_review_packet_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_phase97_external_security_review_packet.py")),
        MatrixCommand("phase98_external_audit_export_receipt_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_phase98_external_audit_export_receipt.py")),
        MatrixCommand("phase99_invocation_denial_attestation_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_phase99_provider_invocation_denial_attestation.py")),
        MatrixCommand("phase100_invocation_denial_closure_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_phase100_provider_invocation_denial_closure.py")),
        MatrixCommand("phase101_invocation_denial_enforcement_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_phase101_provider_invocation_denial_enforcement.py")),
        MatrixCommand("phase102_invocation_denial_drift_review_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_phase102_provider_invocation_denial_drift_review.py")),
        MatrixCommand("phase103_invocation_denial_custody_checkpoint_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_phase103_provider_invocation_denial_custody_checkpoint.py")),
        MatrixCommand("governed_local_model_invocation_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_local_model_authority.py", "tests/test_governed_local_model_invocation.py", "tests/test_chat_service_lazy_loading.py")),
        MatrixCommand("genesis_reviewed_candidate_adoption_custody_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_genesis_reviewed_adoption.py", "tests/test_build_genesis_reviewed_adoption_script.py", "tests/test_genesis_forge.py", "tests/test_genesis_model_advice.py", "tests/test_governed_local_model_invocation.py", "sentientos/tests/test_constitutional_mutation_fabric.py", "tests/test_sentientosd_runtime_closure.py", "tests/test_world_state_board.py", "tests/test_capability_registry.py", "tests/test_reviewer_proof_bundle.py", "tests/test_codex_validation_matrix_lane_contract.py", "tests/test_repository_mutation_custody_regression.py")),
        MatrixCommand("genesis_model_advice_runtime_closure_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_genesis_model_advice.py", "tests/test_build_genesis_model_advice_script.py", "tests/test_governed_local_model_invocation.py", "tests/test_genesis_forge.py", "tests/test_sentientosd_runtime_closure.py")),
        MatrixCommand("governed_improvement_signal_plane_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_governed_improvement_signal_plane.py", "tests/test_build_governed_improvement_signal_plane_script.py", "tests/test_repository_mutation_custody_regression.py")),
        MatrixCommand("host_resource_observation_runtime_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_host_resource_runtime.py", "tests/test_build_host_resource_runtime_script.py", "tests/test_host_collectors.py", "tests/test_host_resource_governor.py", "tests/test_host_resource_policy.py", "tests/test_sentientosd_runtime_closure.py", "tests/test_world_state_board.py", "tests/test_world_state_sources.py", "tests/test_dashboard_world_state.py", "tests/test_capability_registry.py", "tests/test_reviewer_proof_bundle.py", "tests/test_codex_validation_matrix_lane_contract.py", "tests/test_repository_mutation_custody_regression.py")),
        MatrixCommand("host_privilege_review_rehearsal_runtime_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_host_privilege_review_runtime.py", "tests/test_build_host_privilege_review_runtime_script.py", "tests/test_host_resource_runtime.py", "tests/test_host_resource_policy.py", "tests/test_privilege_broker.py", "tests/test_actuation_fulfillment.py", "tests/test_host_embodiment_trace.py", "tests/test_sentientosd_runtime_closure.py", "tests/test_world_state_board.py", "tests/test_dashboard_world_state.py", "tests/test_capability_registry.py", "tests/test_reviewer_proof_bundle.py", "tests/test_codex_validation_matrix_lane_contract.py", "tests/test_repository_mutation_custody_regression.py")),
        MatrixCommand("host_controlled_authorization_safety_runtime_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_host_controlled_authorization_runtime.py", "tests/test_build_host_controlled_authorization_runtime_script.py", "tests/test_host_execution_readiness_runtime.py", "tests/test_controlled_authorization.py", "tests/test_host_actuation_safety.py", "tests/test_live_grant_readiness.py", "tests/test_runtime_supervisor.py", "tests/test_sentientosd_runtime_closure.py", "tests/test_world_state_board.py", "tests/test_dashboard_world_state.py", "tests/test_capability_registry.py", "tests/test_reviewer_proof_bundle.py", "tests/test_codex_validation_matrix_lane_contract.py", "tests/test_repository_mutation_custody_regression.py")),

        MatrixCommand("host_fulfillment_authorization_consumption_custody_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_host_fulfillment_authorization_runtime.py", "tests/test_build_host_fulfillment_authorization_runtime_script.py", "tests/test_host_local_authorization_runtime.py", "tests/test_local_authorization_grant.py", "tests/test_fulfillment_authorization.py", "tests/test_control_plane_kernel.py", "tests/test_sentientosd_runtime_closure.py", "tests/test_world_state_board.py", "tests/test_dashboard_world_state.py", "tests/test_capability_registry.py", "tests/test_reviewer_proof_bundle.py", "tests/test_codex_validation_matrix_lane_contract.py", "tests/test_repository_mutation_custody_regression.py")),
        MatrixCommand("host_fulfillment_executor_contract_readiness_runtime_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_host_fulfillment_executor_readiness_runtime.py", "tests/test_build_host_fulfillment_executor_readiness_runtime_script.py", "tests/test_host_fulfillment_authorization_runtime.py", "tests/test_fulfillment_executor_contract.py", "tests/test_host_local_authorization_runtime.py", "tests/test_local_authorization_grant.py", "tests/test_host_actuation_safety.py", "tests/test_effect_proof.py", "tests/test_control_plane_kernel.py", "tests/test_runtime_supervisor.py", "tests/test_sentientosd_runtime_closure.py", "tests/test_world_state_board.py", "tests/test_dashboard_world_state.py", "tests/test_capability_registry.py", "tests/test_reviewer_proof_bundle.py", "tests/test_codex_validation_matrix_lane_contract.py", "tests/test_repository_mutation_custody_regression.py")),
        MatrixCommand("host_dry_run_audit_closure_runtime_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_host_dry_run_audit_closure_runtime.py", "tests/test_build_host_dry_run_audit_closure_runtime_script.py", "tests/test_dry_run_audit_closure.py", "tests/test_host_dry_run_execution_runtime.py", "tests/test_build_host_dry_run_execution_runtime_script.py", "tests/test_sentientosd_runtime_closure.py", "tests/test_dashboard_world_state.py", "tests/test_capability_registry.py", "tests/test_reviewer_proof_bundle.py", "tests/test_codex_validation_matrix_lane_contract.py", "tests/test_repository_mutation_custody_regression.py")),
        MatrixCommand("host_real_effect_admission_runtime_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_host_real_effect_admission_runtime.py", "tests/test_build_host_real_effect_admission_runtime_script.py", "tests/test_real_effect_admission.py", "tests/test_capability_registry.py", "tests/test_reviewer_proof_bundle.py", "tests/test_codex_validation_matrix_lane_contract.py")),
        MatrixCommand("host_local_diagnostic_execution_source_runtime_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_host_local_diagnostic_execution_source_runtime.py", "tests/test_build_host_local_diagnostic_execution_source_runtime_script.py", "tests/test_host_real_effect_admission_runtime.py", "tests/test_host_dry_run_execution_runtime.py", "tests/test_host_fulfillment_executor_readiness_runtime.py", "tests/test_capability_registry.py", "tests/test_reviewer_proof_bundle.py", "tests/test_codex_validation_matrix_lane_contract.py")),
        MatrixCommand("host_local_diagnostic_execution_runtime_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_host_local_diagnostic_execution_runtime.py", "tests/test_run_host_local_diagnostic_execution_runtime_script.py", "tests/test_host_local_diagnostic_execution_source_runtime.py", "tests/test_builtin_runner_transaction_orchestrator.py", "tests/test_capability_registry.py", "tests/test_reviewer_proof_bundle.py", "tests/test_codex_validation_matrix_lane_contract.py")),
        MatrixCommand("host_local_diagnostic_rollback_runtime_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_host_local_diagnostic_rollback_runtime.py", "tests/test_run_host_local_diagnostic_rollback_runtime_script.py", "tests/test_local_diagnostic_exact_rollback.py", "tests/test_host_local_diagnostic_execution_runtime.py", "tests/test_capability_registry.py", "tests/test_reviewer_proof_bundle.py", "tests/test_codex_validation_matrix_lane_contract.py")),
        MatrixCommand("host_local_diagnostic_lifecycle_closure_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_host_local_diagnostic_lifecycle_closure.py", "tests/test_build_host_local_diagnostic_lifecycle_closure_script.py", "tests/test_host_local_diagnostic_execution_runtime.py", "tests/test_host_local_diagnostic_rollback_runtime.py", "tests/test_reviewer_proof_bundle.py", "tests/test_codex_validation_matrix_lane_contract.py")),
        MatrixCommand("host_dry_run_execution_runtime_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_host_dry_run_execution_runtime.py", "tests/test_build_host_dry_run_execution_runtime_script.py", "tests/test_host_fulfillment_executor_readiness_runtime.py", "tests/test_dry_run_execution_harness.py", "tests/test_dry_run_audit_closure.py", "tests/test_fulfillment_executor_contract.py", "tests/test_host_local_authorization_runtime.py", "tests/test_local_authorization_grant.py", "tests/test_host_fulfillment_authorization_runtime.py", "tests/test_control_plane_kernel.py", "tests/test_runtime_supervisor.py", "tests/test_sentientosd_runtime_closure.py", "tests/test_world_state_board.py", "tests/test_dashboard_world_state.py", "tests/test_capability_registry.py", "tests/test_reviewer_proof_bundle.py", "tests/test_codex_validation_matrix_lane_contract.py", "tests/test_repository_mutation_custody_regression.py")),
        MatrixCommand("host_local_authorization_grant_custody_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_host_local_authorization_runtime.py", "tests/test_build_host_local_authorization_runtime_script.py", "tests/test_host_live_grant_readiness_runtime.py", "tests/test_local_authorization_grant.py", "tests/test_fulfillment_authorization.py", "tests/test_control_plane_kernel.py", "tests/test_sentientosd_runtime_closure.py", "tests/test_world_state_board.py", "tests/test_dashboard_world_state.py", "tests/test_capability_registry.py", "tests/test_reviewer_proof_bundle.py", "tests/test_codex_validation_matrix_lane_contract.py", "tests/test_repository_mutation_custody_regression.py")),
        MatrixCommand("host_live_grant_readiness_runtime_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_host_live_grant_readiness_runtime.py", "tests/test_build_host_live_grant_readiness_runtime_script.py", "tests/test_host_controlled_authorization_runtime.py", "tests/test_live_grant_readiness.py", "tests/test_local_authorization_grant.py", "tests/test_runtime_supervisor.py", "tests/test_sentientosd_runtime_closure.py", "tests/test_world_state_board.py", "tests/test_dashboard_world_state.py", "tests/test_capability_registry.py", "tests/test_reviewer_proof_bundle.py", "tests/test_codex_validation_matrix_lane_contract.py", "tests/test_repository_mutation_custody_regression.py")),
        MatrixCommand("host_execution_readiness_authorization_review_runtime_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_host_execution_readiness_runtime.py", "tests/test_build_host_execution_readiness_runtime_script.py", "tests/test_host_privilege_review_runtime.py", "tests/test_actuation_fulfillment.py", "tests/test_effect_proof.py", "tests/test_authorization_review.py", "tests/test_runtime_supervisor.py", "tests/test_sentientosd_runtime_closure.py", "tests/test_world_state_board.py", "tests/test_dashboard_world_state.py", "tests/test_capability_registry.py", "tests/test_reviewer_proof_bundle.py", "tests/test_codex_validation_matrix_lane_contract.py", "tests/test_repository_mutation_custody_regression.py")),
        MatrixCommand("world_state_evidence_board_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_world_state_board.py", "tests/test_world_state_sources.py", "tests/test_build_world_state_board_script.py", "tests/test_dashboard_world_state.py", "tests/test_sentientosd_runtime_closure.py", "tests/test_capability_registry.py", "tests/test_reviewer_proof_bundle.py", "tests/test_codex_validation_matrix_lane_contract.py", "tests/test_repository_mutation_custody_regression.py")),
        MatrixCommand("proof_bundle_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_capability_registry.py", "tests/test_reviewer_proof_bundle.py", "tests/test_build_reviewer_proof_bundle_script.py", "tests/test_reviewer_release_readiness_index.py", "tests/test_host_local_diagnostic_lifecycle_reviewer_guide.py", "tests/test_codex_operating_doctrine_docs.py")),
        MatrixCommand("codex_pr_validation_evidence_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_codex_pr_validation_evidence.py", "tests/test_codex_pr_validation_evidence_script.py")),
        MatrixCommand("codex_pr_landing_gate_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_codex_pr_landing_gate.py", "tests/test_codex_pr_landing_gate_script.py")),
        MatrixCommand("codex_pr_metadata_guard_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_codex_pr_metadata_guard.py", "tests/test_codex_pr_metadata_guard_script.py")),
        MatrixCommand("codex_landing_commit_body_binding_tests", ("python", "-m", "scripts.run_tests", "-q", "tests/test_codex_landing_evidence_binding.py", "tests/test_verify_codex_landing_evidence_binding_script.py", "tests/test_codex_finalize_landing.py", "tests/test_codex_finalize_landing_script.py", "tests/test_codex_pr_metadata_guard.py", "tests/test_build_codex_landing_evidence_body_script.py", "tests/test_codex_pr_landing_gate.py", "tests/test_codex_landing_supervisor.py", "tests/test_codex_validation_matrix_lane_contract.py")),
        MatrixCommand("targeted_mypy", ("python", "-m", "mypy", "sentientos/work_item_authority_claims.py", "sentientos/work_item_intake.py", "scripts/intake_work_item.py", "sentientos/work_item_lifecycle_handoff.py", "scripts/plan_work_item_handoff.py", "sentientos/work_item_lifecycle_dry_run_adapter.py", "scripts/run_work_item_dry_run.py", "sentientos/work_item_dry_run_closure.py", "scripts/build_work_item_dry_run_closure.py", "sentientos/work_item_review_packet.py", "scripts/build_work_item_review_packet.py", "sentientos/work_item_promotion_gate.py", "scripts/evaluate_work_item_promotion.py", "sentientos/work_item_operator_admission_review.py", "scripts/build_operator_admission_review.py", "sentientos/work_item_admission_run.py", "scripts/run_operator_confirmed_admission.py", "sentientos/work_item_preflight_run.py", "scripts/run_operator_confirmed_preflight.py", "sentientos/work_item_execution_review.py", "scripts/build_operator_execution_review.py", "sentientos/work_item_execution_run.py", "scripts/run_operator_confirmed_execution.py", "sentientos/work_item_verification_run.py", "scripts/run_operator_confirmed_verification.py", "sentientos/work_item_lifecycle_closure_review.py", "scripts/build_operator_lifecycle_closure_review.py", "sentientos/work_item_lifecycle_closure_run.py", "scripts/run_operator_confirmed_lifecycle_closure.py", "sentientos/work_item_lifecycle_completion_dossier.py", "scripts/build_work_item_lifecycle_completion_dossier.py", "sentientos/work_item_lifecycle_completion_verifier.py", "scripts/verify_work_item_lifecycle_completion_dossier.py", "sentientos/codex_task_scaffold_verifier.py", "scripts/verify_codex_task_scaffold.py", "sentientos/codex_pr_validation_evidence.py", "scripts/codex_pr_validation_evidence.py", "sentientos/codex_pr_landing_gate.py", "scripts/codex_pr_landing_gate.py", "sentientos/codex_pr_metadata_guard.py", "scripts/codex_pr_metadata_guard.py", "sentientos/work_item_lifecycle_final_attestation.py", "scripts/build_work_item_lifecycle_final_attestation.py", "sentientos/work_item_lifecycle_attestation_index.py", "scripts/build_work_item_lifecycle_attestation_index.py", "sentientos/work_item_lifecycle_attestation_index_verifier.py", "scripts/verify_work_item_lifecycle_attestation_index.py", "sentientos/work_item_lifecycle_attestation_review_digest.py", "scripts/build_work_item_lifecycle_attestation_review_digest.py", "sentientos/work_item_lifecycle_attestation_review_digest_verifier.py", "scripts/verify_work_item_lifecycle_attestation_review_digest.py", "sentientos/work_item_lifecycle_attestation_review_digest_index.py", "scripts/build_work_item_lifecycle_attestation_review_digest_index.py", "sentientos/work_item_lifecycle_attestation_review_digest_index_verifier.py", "scripts/verify_work_item_lifecycle_attestation_review_digest_index.py", "sentientos/household_presence_camera_capture_review_decision_ledger.py", "scripts/build_household_presence_camera_capture_review_decision_ledger.py", "sentientos/household_presence_camera_operator_review_trend_ledger.py", "scripts/build_household_presence_camera_operator_review_trend_ledger.py", "sentientos/household_presence_camera_operator_grant_renewal_request_packet.py", "scripts/build_household_presence_camera_operator_grant_renewal_request_packet.py", "sentientos/household_presence_camera_dry_run_continuation_gate.py", "scripts/build_household_presence_camera_dry_run_continuation_gate.py", "sentientos/household_presence_camera_future_live_deferral_registry.py", "scripts/build_household_presence_camera_future_live_deferral_registry.py", "sentientos/household_presence_camera_review_chain_summary_packet.py", "scripts/build_household_presence_camera_review_chain_summary_packet.py", "sentientos/selective_memory_distillation_contract.py", "scripts/build_selective_memory_distillation_contract.py", "sentientos/selective_memory_distillation_receipt_gate.py", "scripts/build_selective_memory_distillation_receipt_gate.py", "sentientos/selective_memory_tomb_receipt_verifier.py", "scripts/build_selective_memory_tomb_receipt_verifier.py", "sentientos/governed_memory_writer_adapter.py", "scripts/build_governed_memory_writer_adapter.py", "sentientos/live_memory_boundary_admission_gate.py", "scripts/build_live_memory_boundary_admission_gate.py", "sentientos/memory_commit_plan_packet.py", "scripts/build_memory_commit_plan_packet.py", "sentientos/memory_commit_operator_approval_packet.py", "scripts/build_memory_commit_operator_approval_packet.py", "sentientos/memory_commit_execution_gate.py", "scripts/build_memory_commit_execution_gate.py", "sentientos/live_memory_commit_dry_run_adapter.py", "scripts/build_live_memory_commit_dry_run_adapter.py", "sentientos/live_commit_safety_interlock.py", "scripts/build_live_commit_safety_interlock.py", "sentientos/sandboxed_live_memory_commit_adapter.py", "scripts/build_sandboxed_live_memory_commit_adapter.py", "sentientos/sandboxed_live_memory_commit_adapter_gate.py", "scripts/build_sandboxed_live_memory_commit_adapter_gate.py", "sentientos/sandboxed_live_memory_commit_adapter_packet.py", "scripts/build_sandboxed_live_memory_commit_adapter_packet.py", "sentientos/sandboxed_live_memory_commit_adapter_envelope.py", "scripts/build_sandboxed_live_memory_commit_adapter_envelope.py", "sentientos/real_live_memory_commit_executor_plan_packet.py", "scripts/build_real_live_memory_commit_executor_plan_packet.py", "sentientos/live_executor_lock_lease_gate.py", "scripts/build_live_executor_lock_lease_gate.py", "sentientos/live_executor_preflight_packet.py", "scripts/build_live_executor_preflight_packet.py", "sentientos/live_executor_activation_record.py", "scripts/build_live_executor_activation_record.py", "sentientos/live_executor_invocation_harness.py", "scripts/build_live_executor_invocation_harness.py", "sentientos/real_live_memory_commit_executor_enablement_gate.py", "scripts/build_real_live_memory_commit_executor_enablement_gate.py", "sentientos/constrained_executor_enablement_path_packet.py", "scripts/build_constrained_executor_enablement_path_packet.py", "sentientos/live_commit_execution_packet.py", "scripts/build_live_commit_execution_packet.py", "sentientos/real_executor_runtime_enablement_packet.py", "scripts/build_real_executor_runtime_enablement_packet.py", "sentientos/real_executor_runtime_gate.py", "scripts/build_real_executor_runtime_gate.py", "sentientos/guarded_executor_path_packet.py", "scripts/build_guarded_executor_path_packet.py", "sentientos/guarded_executor_invocation_packet.py", "scripts/build_guarded_executor_invocation_packet.py", "sentientos/real_executor_invocation_gate.py", "scripts/build_real_executor_invocation_gate.py", "sentientos/real_executor_execution_authorization_packet.py", "scripts/build_real_executor_execution_authorization_packet.py", "sentientos/real_executor_execution_authorization_gate.py", "scripts/build_real_executor_execution_authorization_gate.py", "sentientos/real_executor_execution_release_packet.py", "scripts/build_real_executor_execution_release_packet.py", "sentientos/real_executor_execution_release_gate.py", "scripts/build_real_executor_execution_release_gate.py", "sentientos/real_executor_execution_activation_packet.py", "scripts/build_real_executor_execution_activation_packet.py", "sentientos/real_executor_execution_activation_gate.py", "scripts/build_real_executor_execution_activation_gate.py", "sentientos/real_executor_execution_invocation_packet.py", "scripts/build_real_executor_execution_invocation_packet.py", "sentientos/real_executor_execution_invocation_gate.py", "scripts/build_real_executor_execution_invocation_gate.py", "sentientos/real_executor_execution_preflight_packet.py", "scripts/build_real_executor_execution_preflight_packet.py", "sentientos/real_executor_execution_lock_lease_packet.py", "scripts/build_real_executor_execution_lock_lease_packet.py", "sentientos/real_executor_execution_lock_lease_gate.py", "scripts/build_real_executor_execution_lock_lease_gate.py", "sentientos/real_executor_execution_commit_plan_packet.py", "scripts/build_real_executor_execution_commit_plan_packet.py", "sentientos/real_executor_execution_commit_plan_gate.py", "scripts/build_real_executor_execution_commit_plan_gate.py", "sentientos/real_executor_execution_commit_window_packet.py", "scripts/build_real_executor_execution_commit_window_packet.py", "sentientos/real_live_memory_commit_execution_gate.py", "scripts/build_real_live_memory_commit_execution_gate.py", "sentientos/real_live_memory_commit_execution_packet.py", "scripts/build_real_live_memory_commit_execution_packet.py", "sentientos/real_live_memory_commit_adapter_readiness_gate.py", "scripts/build_real_live_memory_commit_adapter_readiness_gate.py", "sentientos/real_live_memory_commit_adapter_readiness_envelope.py", "scripts/build_real_live_memory_commit_adapter_readiness_envelope.py")),
        MatrixCommand("mypy_baseline", ("python", "scripts/check_mypy_baseline.py")),
        MatrixCommand("docs_check_deps", ("python", "scripts/build_docs.py", "--check-deps"), required=False),
        MatrixCommand("docs_build", ("python", "scripts/build_docs.py")),
        MatrixCommand("prompt_boundaries", ("python", "scripts/verify_context_hygiene_prompt_boundaries.py")),
        MatrixCommand("strict_audits", ("python", "verify_audits.py", "--strict")),
        MatrixCommand("audit_immutability", ("python", "scripts/audit_immutability_verifier.py")),
    ]
    return [_classify_default_command(command) for command in commands]


def _tail(text: str, lines: int = 30) -> str:
    parts = text.splitlines()
    return "\n".join(parts[-lines:])


def _latest_run_tests_provenance(command: tuple[str, ...]) -> dict[str, object]:
    if "scripts.run_tests" not in command:
        return {}
    path = Path("glow/test_runs/test_run_provenance.json")
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _int_metric(payload: dict[str, object], key: str) -> int | None:
    value = payload.get(key)
    return value if isinstance(value, int) else None


def _proof_status(command: MatrixCommand, completed: subprocess.CompletedProcess[str], provenance: dict[str, object]) -> str:
    if not command.proof_required:
        if completed.returncode == 0:
            return "nonproof-diagnostic-passed" if command.diagnostic_only else "nonproof-passed"
        return "nonproof-diagnostic-failed" if command.diagnostic_only else "nonproof-failed"
    if completed.returncode != 0:
        return "proof-failed"
    if command.execution_required and "scripts.run_tests" in command.command:
        selected = _int_metric(provenance, "tests_selected")
        executed = _int_metric(provenance, "tests_executed")
        passed = _int_metric(provenance, "tests_passed")
        if selected is None or executed is None or passed is None:
            return "proof-metrics-unavailable"
        if selected <= 0 or executed <= 0 or passed <= 0:
            return "proof-not-executed"
    return "proof-passed"


def _is_required_failure(result: MatrixResult) -> bool:
    return bool(result["required"]) and str(result.get("proof_status")) != "proof-passed"


def run_one(command: MatrixCommand, runner: Callable[[tuple[str, ...]], subprocess.CompletedProcess[str]]) -> MatrixResult:
    started = time.perf_counter()
    completed = runner(command.command)
    duration = round(time.perf_counter() - started, 3)
    output = completed.stdout
    if completed.stderr:
        output = f"{output}\n{completed.stderr}" if output else completed.stderr
    provenance = _latest_run_tests_provenance(command.command)
    proof_status = _proof_status(command, completed, provenance)
    raw_exit_reason = provenance.get("exit_reason")
    exit_reason = raw_exit_reason if isinstance(raw_exit_reason, str) else None
    raw_metrics_status = provenance.get("metrics_status")
    metrics_status = raw_metrics_status if isinstance(raw_metrics_status, str) else None
    return {
        "label": command.label,
        "command": list(command.command),
        "required": command.required,
        "proof_required": command.proof_required,
        "execution_required": command.execution_required,
        "diagnostic_only": command.diagnostic_only,
        "nonexecution_allowed": command.nonexecution_allowed,
        "classification_reason": command.classification_reason,
        "proof_status": proof_status,
        "exit_code": completed.returncode,
        "duration_seconds": duration,
        "output_tail": _tail(output),
        "exit_reason": exit_reason,
        "tests_selected": _int_metric(provenance, "tests_selected"),
        "tests_executed": _int_metric(provenance, "tests_executed"),
        "tests_passed": _int_metric(provenance, "tests_passed"),
        "tests_skipped": _int_metric(provenance, "tests_skipped"),
        "metrics_status": metrics_status,
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
        if _is_required_failure(result):
            failed_required = True

    required_failures = [r["label"] for r in results if _is_required_failure(r)]
    summary: MatrixReport = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "failed" if failed_required else "passed",
        "command_count": len(results),
        "required_failure_count": len(required_failures),
        "required_failures": required_failures,
        "diagnostic_failure_count": len([r for r in results if bool(r.get("diagnostic_only")) and int(r["exit_code"]) != 0]),
        "nonproof_count": len([r for r in results if not bool(r.get("proof_required", True))]),
        "results": results,
    }
    return summary


def _default_runner(command: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, capture_output=True, text=True)


def _terminate_process_tree(process: subprocess.Popen[str], *, grace_seconds: float = 2.0) -> str:
    """Terminate only the process tree created for one matrix lane and reap it."""
    if process.poll() is not None:
        process.communicate()
        return "child_already_exited"
    if os.name == "posix":
        os.killpg(process.pid, signal.SIGTERM)
    else:  # pragma: no cover - exercised on supported Windows runners
        process.terminate()
    try:
        process.communicate(timeout=grace_seconds)
        return "process_tree_terminated"
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:  # pragma: no cover
            process.kill()
        process.communicate()
        return "process_tree_killed_after_grace"


def _run_bounded(command: tuple[str, ...], *, timeout_seconds: int, repo: Path) -> tuple[subprocess.CompletedProcess[str], float]:
    started = time.perf_counter()
    process = subprocess.Popen(command, cwd=repo, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=(os.name == "posix"))
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        termination_reason = _terminate_process_tree(process)
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
        timeout = subprocess.TimeoutExpired(command, timeout_seconds, output=stdout, stderr=stderr)
        timeout.termination_reason = termination_reason  # type: ignore[attr-defined]
        raise timeout
    except KeyboardInterrupt:
        _terminate_process_tree(process)
        raise
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr), time.perf_counter() - started


def run_resumable_matrix(*, commands: list[MatrixCommand], checkpoint: Path,
                         resume_from: Path | None = None, command_timeout_seconds: int = 900,
                         progress: bool = False, repo: Path = Path(".")) -> MatrixReport:
    """Run lanes sequentially while preserving exact, content-bound custody."""
    contract = matrix_contract(commands)
    binding = workspace_binding(commands, repo)
    results: list[MatrixResult] = []
    if resume_from is not None:
        try:
            prior = json.loads(resume_from.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            prior = {}
        reason = None
        if prior.get("schema_version") != MATRIX_SCHEMA: reason = "resume_schema_invalid"
        elif prior.get("matrix_contract_digest") != contract["manifest_digest"]: reason = "matrix_contract_changed"
        elif prior.get("workspace_binding", {}).get("binding_digest") != binding["binding_digest"]: reason = "workspace_binding_changed"
        elif prior.get("checkpoint_digest") != _digest({k: v for k, v in prior.items() if k != "checkpoint_digest"}): reason = "checkpoint_digest_mismatch"
        else:
            candidate = prior.get("results", [])
            if prior.get("status") in {"matrix_timed_out", "matrix_interrupted"} and candidate and candidate[-1].get("proof_status") in {"timed-out", "interrupted"}:
                candidate = candidate[:-1]
            labels = prior.get("completed_labels", [])
            expected = [c.label for c in commands[:len(candidate)]]
            if labels != expected or [r.get("label") for r in candidate] != expected or len(set(labels)) != len(labels):
                reason = "completed_lane_order_invalid"
            elif any(r.get("command") != list(commands[i].command) for i, r in enumerate(candidate)):
                reason = "matrix_contract_changed"
            elif any(_is_required_failure(r) for r in candidate):
                reason = "failed_lane_requires_rerun"
            else: results = candidate
        if reason:
            report: MatrixReport = {"schema_version": MATRIX_SCHEMA, "status": "matrix_resume_blocked", "resume_block_reasons": [reason],
                "matrix_contract": contract, "matrix_contract_digest": contract["manifest_digest"], "workspace_binding": binding,
                "results": [], "completed_labels": [], "next_lane_index": 0, "command_count": len(commands)}
            base = dict(report); report["checkpoint_digest"] = _digest(base)
            _atomic_json(checkpoint, report); return report
        if prior.get("status") == "matrix_passed" and len(results) == len(commands):
            if checkpoint != resume_from: _atomic_json(checkpoint, prior)
            return prior  # type: ignore[no-any-return]

    active_lane: dict[str, object] | None = None

    def emit(status: str) -> MatrixReport:
        failures = [str(r["label"]) for r in results if _is_required_failure(r)]
        payload: MatrixReport = {"schema_version": MATRIX_SCHEMA, "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "status": status, "command_count": len(commands), "required_failure_count": len(failures), "required_failures": failures,
            "diagnostic_failure_count": len([r for r in results if r.get("diagnostic_only") and r.get("exit_code") != 0]),
            "nonproof_count": len([r for r in results if not r.get("proof_required", True)]), "results": results,
            "matrix_contract": contract, "matrix_contract_digest": contract["manifest_digest"], "workspace_binding": binding,
            "completed_labels": [str(r["label"]) for r in results], "next_lane_index": len(results), "completion_status": status,
            "active_lane": active_lane}
        payload["checkpoint_digest"] = _digest(dict(payload))
        _atomic_json(checkpoint, payload); return payload

    emit("matrix_in_progress")
    for index, command in enumerate(commands[len(results):], start=len(results)):
        active_lane = {"label": command.label, "command": list(command.command), "lifecycle_state": "running",
                       "lane_index": index, "execution_deadline_seconds": command_timeout_seconds}
        emit("matrix_in_progress")
        if progress: print(f"[matrix] start {index + 1}/{len(commands)} {command.label}", flush=True)
        started = time.perf_counter()
        try:
            completed, elapsed = _run_bounded(command.command, timeout_seconds=command_timeout_seconds, repo=repo)
            result = run_one(command, lambda _: completed)
            result["duration_seconds"] = round(elapsed, 3)
            results.append(result)
            active_lane = None
            state = "matrix_failed" if _is_required_failure(result) else "matrix_in_progress"
        except subprocess.TimeoutExpired as exc:
            output = ((exc.stdout or "") + "\n" + (exc.stderr or "")) if isinstance(exc.stdout, str) else ""
            results.append({"label": command.label, "command": list(command.command), "required": command.required,
                "proof_required": command.proof_required, "execution_required": command.execution_required, "diagnostic_only": command.diagnostic_only,
                "nonexecution_allowed": command.nonexecution_allowed, "classification_reason": command.classification_reason,
                "exit_code": 124, "duration_seconds": round(time.perf_counter() - started, 3), "output_tail": _tail(output),
                "proof_status": "timed-out", "exit_reason": getattr(exc, "termination_reason", "execution_deadline_exceeded")})
            active_lane = None
            if progress: print(f"[matrix] end {index + 1}/{len(commands)} {command.label} status=timed_out", flush=True)
            report = emit("matrix_timed_out")
            report["next_lane_index"] = index
            report["completed_labels"] = [str(r["label"]) for r in results[:-1]]
            report["checkpoint_digest"] = _digest({k: v for k, v in report.items() if k != "checkpoint_digest"})
            _atomic_json(checkpoint, report)
            return report
        except KeyboardInterrupt:
            active_lane = None
            report = emit("matrix_interrupted")
            report["next_lane_index"] = index
            report["checkpoint_digest"] = _digest({k: v for k, v in report.items() if k != "checkpoint_digest"})
            _atomic_json(checkpoint, report)
            return report
        if progress: print(f"[matrix] end {index + 1}/{len(commands)} {command.label} exit={results[-1]['exit_code']}", flush=True)
        emit(state)
    return emit("matrix_failed" if any(_is_required_failure(r) for r in results) else "matrix_passed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run full work-item review packet proof matrix with continue-on-failure behavior.")
    parser.add_argument("--summary", action="store_true", help="print compact human summary after JSON")
    parser.add_argument("--output", type=Path, help="optional JSON output path")
    parser.add_argument("--auto-repair-audits", action="store_true")
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--resume-from", type=Path)
    parser.add_argument("--command-timeout-seconds", type=int, default=900)
    parser.add_argument("--progress", action="store_true")
    args = parser.parse_args(argv)

    if args.command_timeout_seconds <= 0:
        parser.error("--command-timeout-seconds must be positive")
    commands = default_matrix_commands()
    checkpoint = args.checkpoint or args.output or Path("/tmp/work_item_review_packet_matrix.checkpoint.json")
    report = run_resumable_matrix(commands=commands, checkpoint=checkpoint, resume_from=args.resume_from,
                                  command_timeout_seconds=args.command_timeout_seconds, progress=args.progress)
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
    return 0 if report["status"] in {"passed", "matrix_passed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
