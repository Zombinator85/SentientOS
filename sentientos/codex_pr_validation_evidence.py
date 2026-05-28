from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import json

from sentientos.codex_pr_metadata_contract import FORBIDDEN_LOCAL_ONLY_MARKERS, _norm, verify_pr_metadata
from sentientos.codex_validation_matrix_lane_contract import summarize_lane_contract, verify_lane_contract


@dataclass(frozen=True)
class CodexPRValidationEvidenceVerification:
    status: str
    metadata_contract_status: str
    title_ok: bool
    intended_commit_title_ok: bool
    missing_body_markers: tuple[str, ...]
    local_only_validation_claim_detected: bool
    evidence_present: bool
    findings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_json_text(inline_text: str | None, file_path: str | None) -> dict[str, Any]:
    if inline_text:
        payload = json.loads(inline_text)
        return payload if isinstance(payload, dict) else {}
    if file_path:
        payload = json.loads(Path(file_path).read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    return {}


def _lane_ok(matrix: dict[str, Any], label: str) -> bool:
    for row in matrix.get("results", []):
        if str(row.get("label")) == label:
            return int(row.get("exit_code", 1)) == 0
    return False


def verify_pr_validation_evidence(*, pr_title: str, pr_body: str, intended_commit_title: str | None = None, matrix_json_text: str | None = None, matrix_json_path: str | None = None, bootstrap_summary_json_text: str | None = None, explicit_rollup_json_text: str | None = None) -> CodexPRValidationEvidenceVerification:
    base = verify_pr_metadata(pr_title=pr_title, pr_body=pr_body, intended_commit_title=intended_commit_title)
    normalized_body = _norm(pr_body)
    findings: list[str] = []

    matrix = _read_json_text(matrix_json_text, matrix_json_path)
    evidence_present = bool(matrix)
    if not evidence_present:
        findings.append("matrix_evidence_missing")

    if any(marker in normalized_body for marker in FORBIDDEN_LOCAL_ONLY_MARKERS):
        findings.append("local_only_validation_claim_detected")

    if evidence_present:
        if str(matrix.get("status")) != "passed":
            findings.append("matrix_status_not_passed")
        if int(matrix.get("required_failure_count", -1)) != 0:
            findings.append("required_failure_count_nonzero")
        if "matrix runner --output result/path" not in normalized_body and matrix_json_path is None:
            findings.append("matrix_output_reference_missing")
        lane_check = verify_lane_contract(matrix)
        for finding in lane_check.findings:
            if finding.severity == "error":
                findings.append(finding.code)

    # optional payloads accepted to keep API contract stable and metadata-only.
    _ = bootstrap_summary_json_text, explicit_rollup_json_text

    status = "codex_pr_validation_evidence_ready" if (not findings and base.status == "codex_pr_metadata_contract_ready") else "codex_pr_validation_evidence_incomplete"
    return CodexPRValidationEvidenceVerification(
        status=status,
        metadata_contract_status=base.status,
        title_ok=base.title_ok,
        intended_commit_title_ok=base.intended_commit_title_ok,
        missing_body_markers=base.missing_body_markers,
        local_only_validation_claim_detected=base.local_only_validation_claim_detected,
        evidence_present=evidence_present,
        findings=tuple(findings),
    )


def build_validation_section_from_matrix(*, matrix_json_text: str | None = None, matrix_json_path: str | None = None) -> str:
    matrix = _read_json_text(matrix_json_text, matrix_json_path)
    status = str(matrix.get("status", "unknown"))
    required_failure_count = int(matrix.get("required_failure_count", -1))
    out_ref = matrix_json_path or "(inline matrix json supplied)"
    return "\n\n".join(
        [
            "## Full command matrix results\n" + f"status={status}; required_failure_count={required_failure_count}",
            "## Matrix runner --summary result\n" + status,
            "## Matrix runner --output result/path\n" + out_ref,
            "## Targeted mypy result\n" + ("passed" if _lane_ok(matrix, "targeted_mypy") else "failed"),
            "## Baseline result\n" + ("passed (new_errors=0 expected)" if _lane_ok(matrix, "mypy_baseline") else "failed"),
            "## Docs build result\n" + ("passed" if _lane_ok(matrix, "docs_build") else "failed"),
            "## Prompt-boundary result\n" + ("passed" if _lane_ok(matrix, "prompt_boundaries") else "failed"),
            "## Strict audit result\n" + ("passed" if _lane_ok(matrix, "strict_audits") else "failed"),
            "## Immutability verifier result\n" + ("passed" if _lane_ok(matrix, "audit_immutability") else "failed"),
            "## Lane contract behavior\n" + json.dumps(summarize_lane_contract(matrix), sort_keys=True),
            "## Unresolved risks\nNone known.",
        ]
    )
