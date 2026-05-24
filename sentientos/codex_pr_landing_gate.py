from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
import json

from sentientos.codex_pr_validation_evidence import build_validation_section_from_matrix, verify_pr_validation_evidence
from sentientos.codex_validation_matrix_lane_contract import summarize_lane_contract, verify_lane_contract


@dataclass(frozen=True)
class CodexPRLandingGateResult:
    status: str
    decision: str
    title_check_summary: dict[str, Any]
    body_contract_summary: dict[str, Any]
    evidence_alignment_summary: dict[str, Any]
    lane_contract_summary: dict[str, Any]
    blocker_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    suggested_fixed_pr_body: str | None
    non_authority_boundaries: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_json(text: str | None) -> dict[str, Any]:
    if not text:
        return {}
    parsed = json.loads(text)
    return parsed if isinstance(parsed, dict) else {}


def verify_pr_landing_gate(*, proposed_pr_title: str, intended_commit_title: str, proposed_pr_body: str | None = None, structured_rollup_json_text: str | None = None, matrix_json_text: str, bootstrap_summary_json_text: str | None = None, strict_mode_policy_json_text: str | None = None) -> CodexPRLandingGateResult:
    body = proposed_pr_body
    if not body and structured_rollup_json_text:
        payload = _read_json(structured_rollup_json_text)
        body = build_validation_section_from_matrix(matrix_json_text=matrix_json_text) if not payload else build_validation_section_from_matrix(matrix_json_text=matrix_json_text)
    body = body or ""

    evidence = verify_pr_validation_evidence(
        pr_title=proposed_pr_title,
        pr_body=body,
        intended_commit_title=intended_commit_title,
        matrix_json_text=matrix_json_text,
        bootstrap_summary_json_text=bootstrap_summary_json_text,
        explicit_rollup_json_text=structured_rollup_json_text,
    )
    matrix = _read_json(matrix_json_text)
    lane = verify_lane_contract(matrix)

    blockers = list(evidence.findings)
    blockers.extend(f.code for f in lane.findings if f.severity == "error")
    warnings = [f.code for f in lane.findings if f.severity == "warning"]

    strict = _read_json(strict_mode_policy_json_text)
    if bool(strict.get("treat_warnings_as_blockers")) and warnings:
        blockers.extend([f"strict_warning_block:{c}" for c in warnings])

    decision = "pr_metadata_allowed"
    if blockers:
        decision = "pr_metadata_blocked"
    elif warnings:
        decision = "manual_review_required"

    suggested = None
    if decision != "pr_metadata_allowed":
        suggested = build_validation_section_from_matrix(matrix_json_text=matrix_json_text)

    return CodexPRLandingGateResult(
        status="codex_pr_landing_gate_ready" if decision == "pr_metadata_allowed" else "codex_pr_landing_gate_blocked",
        decision=decision,
        title_check_summary={"title_ok": evidence.title_ok, "intended_commit_title_ok": evidence.intended_commit_title_ok},
        body_contract_summary={"missing_body_markers": list(evidence.missing_body_markers), "local_only_validation_claim_detected": evidence.local_only_validation_claim_detected},
        evidence_alignment_summary={"status": evidence.status, "findings": list(evidence.findings), "evidence_present": evidence.evidence_present},
        lane_contract_summary=summarize_lane_contract(matrix),
        blocker_codes=tuple(dict.fromkeys(blockers)),
        warning_codes=tuple(dict.fromkeys(warnings)),
        suggested_fixed_pr_body=suggested,
        non_authority_boundaries=(
            "metadata-only",
            "no_github_calls",
            "no_branch_issue_comment_mutation",
            "no_provider_network_shell_subprocess_action_wing_invocation_from_library",
        ),
    )


def build_and_verify_pr_body(*, proposed_pr_title: str, intended_commit_title: str, matrix_json_text: str, bootstrap_summary_json_text: str | None = None, strict_mode_policy_json_text: str | None = None) -> CodexPRLandingGateResult:
    body = build_validation_section_from_matrix(matrix_json_text=matrix_json_text)
    return verify_pr_landing_gate(
        proposed_pr_title=proposed_pr_title,
        intended_commit_title=intended_commit_title,
        proposed_pr_body=body,
        matrix_json_text=matrix_json_text,
        bootstrap_summary_json_text=bootstrap_summary_json_text,
        strict_mode_policy_json_text=strict_mode_policy_json_text,
    )
