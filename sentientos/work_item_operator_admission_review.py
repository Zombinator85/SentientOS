from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from sentientos.work_item_authority_claims import authority_claim_summary, authority_claims_from_nested_evidence
from sentientos.work_item_intake import EXPLICIT_NON_AUTHORITY_BOUNDARIES


@dataclass(frozen=True)
class OperatorAdmissionReviewPolicy:
    allow_warning_review: bool = True
    matrix_required: bool = False
    artifacts_required: bool = False


@dataclass(frozen=True)
class OperatorAdmissionReviewRequest:
    promotion_dossier: Mapping[str, Any]
    review_packet: Mapping[str, Any] | None = None
    work_item_packet: Mapping[str, Any] | None = None
    matrix_report: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class OperatorAdmissionReviewChecklistItem:
    id: str
    status: str
    reason: str
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class OperatorAdmissionReviewPacket:
    admission_review_packet_id: str
    admission_review_packet_digest: str
    work_item_id: str
    source_kind: str
    source_ref: str
    promotion_status: str
    promotion_dossier_id: str
    promotion_dossier_digest: str
    review_packet_id: str | None
    review_packet_digest: str | None
    risk_class: str
    authority_claim_summary: tuple[str, ...]
    contradiction_codes: tuple[str, ...]
    blocker_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    missing_metadata_fields: tuple[str, ...]
    required_operator_acknowledgements: tuple[str, ...]
    operator_checklist: tuple[OperatorAdmissionReviewChecklistItem, ...]
    admission_attempt_preconditions: tuple[str, ...]
    admission_attempt_blockers: tuple[str, ...]
    admission_attempt_warnings: tuple[str, ...]
    evidence_artifact_references: tuple[str, ...]
    matrix_report_status: str | None
    candidate_manual_command: str | None
    explicit_non_authority_boundaries: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["operator_checklist"] = [asdict(item) for item in self.operator_checklist]
        return payload


@dataclass(frozen=True)
class OperatorAdmissionReviewResult:
    status: str
    packet: OperatorAdmissionReviewPacket

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "packet": self.packet.to_dict()}


def _tuple(v: Any) -> tuple[str, ...]:
    if isinstance(v, (list, tuple)):
        return tuple(str(x) for x in v if str(x).strip())
    return ()


def evaluate_operator_admission_review(request: OperatorAdmissionReviewRequest, *, policy: OperatorAdmissionReviewPolicy | None = None) -> OperatorAdmissionReviewResult:
    p = policy or OperatorAdmissionReviewPolicy()
    dossier = dict(request.promotion_dossier.get("dossier", request.promotion_dossier))
    missing: list[str] = []
    work_item_id = str(dossier.get("work_item_id") or "")
    promotion_status = str(dossier.get("promotion_status") or request.promotion_dossier.get("decision", {}).get("status", ""))
    if not work_item_id:
        missing.append("work_item_id")
    if not str(dossier.get("promotion_dossier_id") or ""):
        missing.append("promotion_dossier_id")
    if not str(dossier.get("promotion_dossier_digest") or ""):
        missing.append("promotion_dossier_digest")

    contradiction_codes = set(_tuple(dossier.get("contradiction_codes")))
    blocker_codes = set(_tuple(dossier.get("blocker_codes")))
    warning_codes = set(_tuple(dossier.get("warning_codes")))

    review_packet = request.review_packet or {}
    if review_packet and str(review_packet.get("source_work_item_id") or review_packet.get("work_item_id") or "") not in {"", work_item_id}:
        contradiction_codes.add("review_packet_work_item_id_mismatch")
    if review_packet and str(review_packet.get("digest") or "") and str(dossier.get("review_packet_digest") or "") and str(review_packet.get("digest")) != str(dossier.get("review_packet_digest")):
        contradiction_codes.add("review_packet_digest_mismatch")

    artifacts = tuple(dossier.get("artifact_records") or ())
    evidence_refs = tuple(sorted(set(str(a.get("digest") or a.get("artifact_id") or "") for a in artifacts if isinstance(a, Mapping) and (a.get("digest") or a.get("artifact_id")))))
    if p.artifacts_required and not evidence_refs:
        missing.append("artifact_records")
    matrix_status = str((request.matrix_report or {}).get("status") or dossier.get("matrix_report_status") or "") or None
    if p.matrix_required and matrix_status != "passed":
        missing.append("matrix_report_passed")

    claims = authority_claims_from_nested_evidence(dossier, request.review_packet or {}, request.work_item_packet or {}, request.matrix_report or {})
    authority = authority_claim_summary(claims)

    status = "admission_review_failed"
    if missing:
        status = "admission_review_insufficient_evidence"
    elif contradiction_codes:
        status = "admission_review_contradicted"
    elif promotion_status == "promotion_blocked_authority":
        status = "admission_review_blocked"
    elif promotion_status == "promotion_insufficient_evidence":
        status = "admission_review_insufficient_evidence"
    elif promotion_status == "promotion_requires_clarification":
        status = "admission_review_requires_clarification"
    elif promotion_status == "promotion_requires_manual_review":
        status = "admission_review_manual_review_required"
    elif promotion_status == "promotion_ready_with_warnings":
        status = "admission_review_ready_with_warnings" if p.allow_warning_review else "admission_review_manual_review_required"
    elif promotion_status == "promotion_ready_for_admission_review":
        status = "admission_review_ready"

    checklist_ids = [
        "review_original_work_item_scope","review_declared_workspace_targets","review_dry_run_lifecycle_summary","review_promotion_dossier","review_authority_claim_summary",
        "confirm_no_agent_execution","confirm_no_network_provider_prompt_authority","confirm_no_branch_pr_issue_mutation","confirm_rollback_policy_before_any_execution",
        "confirm_matrix_report_current","confirm_artifact_digests_match","manually_run_workspace_admission_only_if_appropriate",
    ]
    checklist = tuple(OperatorAdmissionReviewChecklistItem(id=i, status=("blocked" if status in {"admission_review_blocked","admission_review_contradicted","admission_review_insufficient_evidence","admission_review_failed"} and i.startswith("manually_run") else "required"), reason="operator review step", evidence_refs=evidence_refs[:2]) for i in checklist_ids)

    candidate = None
    if status in {"admission_review_ready", "admission_review_ready_with_warnings"}:
        candidate = "manual_operator_command_candidate: python scripts/admit_workspace_change_set.py --proposal <proposal.json> --summary (not authorization)"

    basis = {"dossier": dossier, "status": status, "missing": sorted(set(missing)), "contradictions": sorted(contradiction_codes), "blockers": sorted(blocker_codes)}
    dg = hashlib.sha256(json.dumps(basis, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    packet = OperatorAdmissionReviewPacket(
        admission_review_packet_id=f"wiar_{dg[:16]}", admission_review_packet_digest=dg, work_item_id=work_item_id,
        source_kind=str(dossier.get("source_kind") or ""), source_ref=str(dossier.get("source_ref") or ""), promotion_status=promotion_status,
        promotion_dossier_id=str(dossier.get("promotion_dossier_id") or ""), promotion_dossier_digest=str(dossier.get("promotion_dossier_digest") or ""),
        review_packet_id=(str(dossier.get("review_packet_id") or "") or None), review_packet_digest=(str(dossier.get("review_packet_digest") or "") or None),
        risk_class=str(dossier.get("risk_class") or ""), authority_claim_summary=authority, contradiction_codes=tuple(sorted(contradiction_codes)), blocker_codes=tuple(sorted(blocker_codes)),
        warning_codes=tuple(sorted(warning_codes)), missing_metadata_fields=tuple(sorted(set(missing) | set(_tuple(dossier.get("missing_metadata_fields"))))),
        required_operator_acknowledgements=tuple(_tuple(dossier.get("required_operator_acknowledgements"))) or ("operator_review_packet_is_not_authorization",),
        operator_checklist=checklist, admission_attempt_preconditions=("human_review_complete", "manual_invocation_explicit"),
        admission_attempt_blockers=tuple(sorted(blocker_codes)), admission_attempt_warnings=tuple(sorted(warning_codes)), evidence_artifact_references=evidence_refs,
        matrix_report_status=matrix_status, candidate_manual_command=candidate,
        explicit_non_authority_boundaries=tuple(dossier.get("explicit_non_authority_boundaries") or EXPLICIT_NON_AUTHORITY_BOUNDARIES),
    )
    return OperatorAdmissionReviewResult(status=status, packet=packet)


def write_operator_admission_review_packet(result: OperatorAdmissionReviewResult, path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
