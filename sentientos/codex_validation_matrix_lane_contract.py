from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class LaneContract:
    lane_id: str
    display_name: str
    aliases: tuple[str, ...]
    required: bool
    pass_when_exit_code_zero: bool = True


@dataclass(frozen=True)
class LaneVerificationFinding:
    severity: str
    code: str
    message: str


@dataclass(frozen=True)
class LaneContractVerification:
    status: str
    required_failure_count: int
    computed_required_failure_count: int
    findings: tuple[LaneVerificationFinding, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "required_failure_count": self.required_failure_count,
            "computed_required_failure_count": self.computed_required_failure_count,
            "findings": [asdict(item) for item in self.findings],
        }


LANE_CONTRACT: tuple[LaneContract, ...] = (
    LaneContract("targeted_tests", "Targeted tests", ("targeted_tests", "tests_targeted"), True),
    LaneContract("targeted_mypy", "Targeted mypy", ("targeted_mypy",), True),
    LaneContract("mypy_baseline", "Mypy baseline", ("mypy_baseline",), True),
    LaneContract("matrix_summary_output", "Matrix summary/output", ("matrix_summary", "matrix_output"), False),
    LaneContract("docs_check_bootstrap_recheck_build", "Docs check/bootstrap/recheck/build", ("docs_check_deps", "docs_bootstrap", "docs_check_deps_recheck", "docs_build"), True),
    LaneContract("prompt_boundary", "Prompt-boundary", ("prompt_boundaries", "prompt_boundary"), True),
    LaneContract("strict_audits", "Strict audits", ("strict_audits",), True),
    LaneContract("audit_immutability", "Audit immutability", ("audit_immutability",), True),
    LaneContract("capability_proof_readiness", "Capability/proof/readiness", ("capability_registry", "proof_bundle", "readiness_checks"), False),
)
TARGETED_TEST_LANE_ALIASES: tuple[str, ...] = (
    "selective_memory_distillation_contract_tests",
    "selective_memory_distillation_receipt_gate_tests",
    "selective_memory_tomb_receipt_verifier_tests",
    "governed_memory_writer_adapter_tests",
    "live_memory_boundary_admission_gate_tests",
    "memory_commit_plan_packet_tests",
    "memory_commit_operator_approval_packet_tests",
    "memory_commit_execution_gate_tests",
    "live_memory_commit_dry_run_adapter_tests",
    "live_commit_safety_interlock_tests",
    "sandboxed_live_memory_commit_adapter_tests",
    "real_memory_root_admission_gate_tests",
    "final_live_memory_commit_review_gate_tests",
    "real_live_memory_commit_adapter_readiness_envelope_tests",
    "explicit_live_memory_runtime_execution_gate_tests",
    "real_live_memory_commit_executor_plan_packet_tests",
    "live_executor_lock_lease_gate_tests",
    "live_executor_preflight_packet_tests",
    "live_executor_activation_record_tests",
    "live_executor_invocation_harness_tests",
    "real_live_memory_commit_executor_implementation_skeleton_tests",
    "real_live_memory_commit_executor_enablement_gate_tests",
    "constrained_executor_enablement_path_packet_tests",
    "future_live_memory_commit_execution_gate_tests",
    "live_commit_execution_packet_tests",
    "real_executor_runtime_enablement_packet_tests",
    "real_executor_runtime_gate_tests",
    "guarded_executor_path_packet_tests",
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
    "household_presence_layer_tests",
    "household_presence_camera_event_bridge_tests",
    "household_presence_camera_capture_review_decision_ledger_tests",
    "household_presence_camera_operator_review_trend_ledger_tests",
    "household_presence_camera_operator_grant_renewal_request_packet_tests",
    "household_presence_camera_dry_run_continuation_gate_tests",
    "household_presence_camera_future_live_deferral_registry_tests",
    "household_presence_camera_review_chain_summary_packet_tests",
    "proof_bundle_tests",
    "codex_pr_validation_evidence_tests",
    "codex_pr_landing_gate_tests",
    "codex_pr_metadata_guard_tests",
)


def _rows(matrix: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in matrix.get("results", []):
        if isinstance(row, dict):
            out.append(row)
    return out


def _exit_ok(row: dict[str, Any]) -> bool:
    return int(row.get("exit_code", 1)) == 0


def _find_row(rows: list[dict[str, Any]], labels: tuple[str, ...]) -> dict[str, Any] | None:
    wanted = set(labels)
    for row in rows:
        if str(row.get("label")) in wanted:
            return row
    return None


def verify_lane_contract(matrix: dict[str, Any], *, fail_on_unknown_lanes: bool = False) -> LaneContractVerification:
    rows = _rows(matrix)
    findings: list[LaneVerificationFinding] = []

    required_failures = 0
    required_map = {lane.lane_id: lane for lane in LANE_CONTRACT if lane.required}

    targeted_tests_row = _find_row(rows, ("targeted_tests", "tests_targeted"))
    if targeted_tests_row is not None:
        if not _exit_ok(targeted_tests_row):
            findings.append(LaneVerificationFinding("error", "targeted_tests_failed", "required lane targeted_tests did not pass"))
            required_failures += 1
    else:
        missing_targeted_test_lanes = [alias for alias in TARGETED_TEST_LANE_ALIASES if _find_row(rows, (alias,)) is None]
        failed_targeted_test_lanes = [alias for alias in TARGETED_TEST_LANE_ALIASES if (row := _find_row(rows, (alias,))) is not None and not _exit_ok(row)]
        if missing_targeted_test_lanes:
            findings.append(
                LaneVerificationFinding(
                    "error",
                    "missing_targeted_tests",
                    "required targeted test lanes are missing: " + ", ".join(missing_targeted_test_lanes),
                )
            )
            required_failures += 1
        if failed_targeted_test_lanes:
            findings.append(
                LaneVerificationFinding(
                    "error",
                    "targeted_tests_failed",
                    "required targeted test lanes failed: " + ", ".join(failed_targeted_test_lanes),
                )
            )
            required_failures += 1

    for lane_id, lane in required_map.items():
        if lane_id in {"targeted_tests", "docs_check_bootstrap_recheck_build"}:
            continue
        row = _find_row(rows, lane.aliases)
        if row is None:
            findings.append(LaneVerificationFinding("error", f"missing_{lane_id}", f"required lane {lane_id} is missing"))
            required_failures += 1
        elif lane.pass_when_exit_code_zero and not _exit_ok(row):
            findings.append(LaneVerificationFinding("error", f"{lane_id}_failed", f"required lane {lane_id} did not pass"))
            required_failures += 1

    docs_check = _find_row(rows, ("docs_check_deps",))
    docs_build = _find_row(rows, ("docs_build",))
    docs_bootstrap = _find_row(rows, ("docs_bootstrap",))
    docs_recheck = _find_row(rows, ("docs_check_deps_recheck",))
    docs_ok = bool(docs_check and _exit_ok(docs_check) and docs_build and _exit_ok(docs_build))
    docs_recovery_ok = bool(docs_check and not _exit_ok(docs_check) and docs_bootstrap and _exit_ok(docs_bootstrap) and docs_recheck and _exit_ok(docs_recheck) and docs_build and _exit_ok(docs_build))
    if not (docs_ok or docs_recovery_ok):
        findings.append(LaneVerificationFinding("error", "docs_contract_not_satisfied", "docs contract requires docs_check_deps+docs_build pass or bootstrap+recheck+build recovery"))
        required_failures += 1

    declared_required_failure_count = int(matrix.get("required_failure_count", -1))
    if declared_required_failure_count != required_failures:
        findings.append(LaneVerificationFinding("error", "required_failure_count_mismatch", "matrix required_failure_count does not match required lane failures"))

    known_labels = {a for lane in LANE_CONTRACT for a in lane.aliases}
    known_labels.update(TARGETED_TEST_LANE_ALIASES)
    known_labels.update({"docs_build"})
    for row in sorted(rows, key=lambda r: str(r.get("label", ""))):
        label = str(row.get("label"))
        if label not in known_labels:
            sev = "error" if fail_on_unknown_lanes else "warning"
            findings.append(LaneVerificationFinding(sev, "unknown_lane", f"unknown lane label: {label}"))

    has_error = any(f.severity == "error" for f in findings)
    return LaneContractVerification(
        status="codex_validation_matrix_lane_contract_ready" if not has_error else "codex_validation_matrix_lane_contract_failed",
        required_failure_count=declared_required_failure_count,
        computed_required_failure_count=required_failures,
        findings=tuple(findings),
    )


def summarize_lane_contract(matrix: dict[str, Any]) -> dict[str, Any]:
    verification = verify_lane_contract(matrix)
    return {
        "status": verification.status,
        "required_failure_count": verification.required_failure_count,
        "computed_required_failure_count": verification.computed_required_failure_count,
        "findings": [asdict(f) for f in verification.findings],
        "lane_contract": [asdict(l) for l in LANE_CONTRACT],
    }
