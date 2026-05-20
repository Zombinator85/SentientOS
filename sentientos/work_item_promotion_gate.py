from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from sentientos.work_item_authority_claims import authority_claim_summary, authority_claims_from_nested_evidence
from sentientos.work_item_intake import EXPLICIT_NON_AUTHORITY_BOUNDARIES

PROMOTION_READY_STATUSES = frozenset(
    {
        "promotion_ready_for_admission_review",
        "promotion_ready_with_warnings",
        "promotion_requires_manual_review",
        "promotion_requires_clarification",
    }
)

BLOCKING_AUTHORITY_FAMILIES = frozenset(
    {
        "execution_authority",
        "verification_replay",
        "lifecycle_real_closure",
        "agent_execution",
        "scheduler",
        "live_tracker",
        "network",
        "provider",
        "prompt_export",
        "subprocess_or_shell",
        "pr_branch_issue_mutation",
        "workspace_execution",
    }
)


@dataclass(frozen=True)
class WorkItemPromotionPolicy:
    allow_warning_promotion: bool = True
    matrix_required: bool = False
    require_artifacts: bool = True


@dataclass(frozen=True)
class WorkItemPromotionRequest:
    review_packet: Mapping[str, Any]
    packet: Mapping[str, Any] | None = None
    handoff: Mapping[str, Any] | None = None
    dry_run_result: Mapping[str, Any] | None = None
    dry_run_closure: Mapping[str, Any] | None = None
    matrix_report: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class WorkItemPromotionDecision:
    status: str
    readiness_reasons: tuple[str, ...]
    rejection_reasons: tuple[str, ...]
    required_operator_acknowledgements: tuple[str, ...]


@dataclass(frozen=True)
class WorkItemPromotionDossier:
    promotion_dossier_id: str
    promotion_dossier_digest: str
    work_item_id: str
    source_kind: str
    source_ref: str
    review_packet_id: str
    review_packet_digest: str
    review_packet_operator_action: str
    intake_status: str
    risk_class: str
    handoff_recommended_surface: str
    dry_run_adapter_status: str | None
    dry_run_closure_status: str | None
    lifecycle_dry_run_invoked: bool
    lifecycle_mode_used: str | None
    lifecycle_stop_reason: str | None
    admission_status: str | None
    preflight_status: str | None
    transaction_plan_ready: bool | None
    authority_claim_summary: tuple[str, ...]
    structured_authority_claims: Mapping[str, bool]
    contradiction_source: str
    contradiction_codes: tuple[str, ...]
    blocker_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    missing_metadata_fields: tuple[str, ...]
    required_operator_acknowledgements: tuple[str, ...]
    readiness_reasons: tuple[str, ...]
    rejection_reasons: tuple[str, ...]
    artifact_records: tuple[Mapping[str, Any], ...]
    matrix_report_status: str | None
    explicit_non_authority_boundaries: tuple[str, ...]
    candidate_next_command_suggestion: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkItemPromotionResult:
    decision: WorkItemPromotionDecision
    dossier: WorkItemPromotionDossier

    def to_dict(self) -> dict[str, Any]:
        return {"decision": asdict(self.decision), "dossier": self.dossier.to_dict()}


def _tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(str(x) for x in value if str(x).strip())
    return ()


def _as_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _blocked_by_claims(claims: Mapping[str, bool]) -> tuple[str, ...]:
    return tuple(sorted(f"blocked_authority_{k}" for k, v in claims.items() if v and k in BLOCKING_AUTHORITY_FAMILIES))


def evaluate_work_item_promotion(request: WorkItemPromotionRequest, *, policy: WorkItemPromotionPolicy | None = None) -> WorkItemPromotionResult:
    selected = policy or WorkItemPromotionPolicy()
    packet = dict(request.review_packet.get("packet", request.review_packet))

    work_item_id = str(packet.get("source_work_item_id") or packet.get("work_item_id") or "")
    review_packet_id = str(packet.get("review_packet_id") or "")
    review_packet_digest = str(packet.get("digest") or "")
    missing: list[str] = []
    if not review_packet_id:
        missing.append("review_packet_id")
    if not review_packet_digest:
        missing.append("review_packet_digest")
    if not work_item_id:
        missing.append("work_item_id")

    claims = authority_claims_from_nested_evidence(packet, request.packet or {}, request.handoff or {}, request.dry_run_result or {}, request.dry_run_closure or {}, request.matrix_report or {})
    claim_summary = authority_claim_summary(claims)
    blocker_codes = set(_tuple(packet.get("blocker_codes")))
    blocker_codes.update(_blocked_by_claims(claims))

    contradiction_codes = set(_tuple(packet.get("contradiction_codes")))
    if request.matrix_report is not None and str(request.matrix_report.get("status", "")) != "passed":
        blocker_codes.add("matrix_report_not_passed")
    if selected.matrix_required and request.matrix_report is None:
        missing.append("matrix_report")

    if packet.get("lifecycle_dry_run_invoked") is True and str(packet.get("lifecycle_mode_used") or "") != "dry_run_full_lifecycle":
        blocker_codes.add("lifecycle_mode_not_dry_run_full_lifecycle")

    closure_status = str(packet.get("dry_run_closure_status") or "")
    if any(code in claim_summary for code in ("execution_authority", "verification_replay", "lifecycle_real_closure")):
        blocker_codes.add("dry_run_claims_real_execution_or_closure")
    if closure_status == "dry_run_closed_with_warnings" and not selected.allow_warning_promotion:
        blocker_codes.add("warning_promotion_disallowed")

    artifacts = tuple(packet.get("artifact_records") or ())
    if selected.require_artifacts and not artifacts:
        missing.append("artifact_records")

    operator_action = str(packet.get("operator_action") or "")
    status = "promotion_failed"
    readiness: list[str] = []
    rejections: list[str] = []
    if missing:
        status = "promotion_insufficient_evidence"
        rejections.append("missing_required_metadata")
    elif contradiction_codes or str(packet.get("contradiction_source") or "none") != "none":
        status = "promotion_contradicted"
        rejections.append("contradicted_evidence_detected")
    elif blocker_codes:
        status = "promotion_blocked_authority"
        rejections.append("blocked_claims_or_policy")
    elif operator_action == "request_clarification":
        status = "promotion_requires_clarification"
        readiness.append("operator_requested_clarification")
    elif operator_action == "manual_review_required":
        status = "promotion_requires_manual_review"
        readiness.append("manual_review_required_by_packet")
    elif closure_status == "dry_run_closed_with_warnings":
        status = "promotion_ready_with_warnings"
        readiness.append("warning_closure_allowed_by_policy")
    elif operator_action in {"ready_for_workspace_admission_review", "dry_run_clean_review"}:
        status = "promotion_ready_for_admission_review"
        readiness.append("coherent_dry_run_review_packet")
    else:
        status = "promotion_requires_manual_review"
        readiness.append("fallback_manual_review")

    acknowledgements: tuple[str, ...] = ()
    if status in {"promotion_ready_for_admission_review", "promotion_ready_with_warnings"}:
        acknowledgements = (
            "operator_must_run_workspace_admission_explicitly",
            "promotion_does_not_authorize_execution",
            "dry_run_evidence_only",
            "artifacts_must_be_reviewed",
            "authority_claims_must_remain_empty_or_allowed",
            "rollback_policy_must_be_reviewed_before_execution",
            "reviewer_matrix_should_be_current",
        )

    basis = {
        "packet": packet,
        "matrix": request.matrix_report,
        "status": status,
        "missing": sorted(set(missing)),
        "blockers": sorted(blocker_codes),
        "contradictions": sorted(contradiction_codes),
    }
    digest = hashlib.sha256(json.dumps(basis, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    dossier = WorkItemPromotionDossier(
        promotion_dossier_id=f"wip_{digest[:16]}",
        promotion_dossier_digest=digest,
        work_item_id=work_item_id,
        source_kind=str(packet.get("source_kind") or ""),
        source_ref=str(packet.get("source_ref") or ""),
        review_packet_id=review_packet_id,
        review_packet_digest=review_packet_digest,
        review_packet_operator_action=operator_action,
        intake_status=str(packet.get("intake_status") or ""),
        risk_class=str(packet.get("risk_class") or ""),
        handoff_recommended_surface=str(packet.get("handoff_recommended_surface") or ""),
        dry_run_adapter_status=(str(packet.get("dry_run_adapter_status") or "") or None),
        dry_run_closure_status=(closure_status or None),
        lifecycle_dry_run_invoked=bool(packet.get("lifecycle_dry_run_invoked")),
        lifecycle_mode_used=(str(packet.get("lifecycle_mode_used") or "") or None),
        lifecycle_stop_reason=(str(packet.get("lifecycle_stop_reason") or "") or None),
        admission_status=(str(packet.get("admission_status") or "") or None),
        preflight_status=(str(packet.get("preflight_status") or "") or None),
        transaction_plan_ready=_as_bool(packet.get("transaction_readiness", packet.get("transaction_plan_ready"))),
        authority_claim_summary=claim_summary,
        structured_authority_claims=claims,
        contradiction_source=str(packet.get("contradiction_source") or "none"),
        contradiction_codes=tuple(sorted(contradiction_codes)),
        blocker_codes=tuple(sorted(blocker_codes)),
        warning_codes=tuple(sorted(set(_tuple(packet.get("warning_codes"))))),
        missing_metadata_fields=tuple(sorted(set(missing + list(_tuple(packet.get("missing_metadata_fields")))))),
        required_operator_acknowledgements=acknowledgements,
        readiness_reasons=tuple(readiness),
        rejection_reasons=tuple(rejections),
        artifact_records=tuple(artifacts),
        matrix_report_status=(str(request.matrix_report.get("status")) if request.matrix_report is not None else None),
        explicit_non_authority_boundaries=tuple(packet.get("explicit_non_authority_boundaries") or EXPLICIT_NON_AUTHORITY_BOUNDARIES),
        candidate_next_command_suggestion=("python scripts/run_workspace_change_set_admission.py --input <promotion-dossier.json> --review-only" if status in PROMOTION_READY_STATUSES else None),
    )
    decision = WorkItemPromotionDecision(status=status, readiness_reasons=tuple(readiness), rejection_reasons=tuple(rejections), required_operator_acknowledgements=acknowledgements)
    return WorkItemPromotionResult(decision=decision, dossier=dossier)


def write_work_item_promotion_dossier(result: WorkItemPromotionResult, path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


__all__ = [
    "WorkItemPromotionPolicy",
    "WorkItemPromotionRequest",
    "WorkItemPromotionDecision",
    "WorkItemPromotionDossier",
    "WorkItemPromotionResult",
    "PROMOTION_READY_STATUSES",
    "evaluate_work_item_promotion",
    "write_work_item_promotion_dossier",
]
