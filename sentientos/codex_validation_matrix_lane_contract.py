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
    if targeted_tests_row is None:
        findings.append(LaneVerificationFinding("error", "missing_targeted_tests", "required lane targeted_tests is missing"))
        required_failures += 1
    elif not _exit_ok(targeted_tests_row):
        findings.append(LaneVerificationFinding("error", "targeted_tests_failed", "required lane targeted_tests did not pass"))
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
