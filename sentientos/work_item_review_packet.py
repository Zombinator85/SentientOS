from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from sentientos.work_item_authority_claims import authority_claim_summary, authority_claims_from_nested_evidence
from sentientos.work_item_dry_run_closure import WorkItemDryRunClosureRequest, build_work_item_dry_run_closure_manifest
from sentientos.work_item_intake import EXPLICIT_NON_AUTHORITY_BOUNDARIES, normalize_work_item_intake, summarize_work_item_packet
from sentientos.work_item_lifecycle_dry_run_adapter import WorkItemLifecycleDryRunAdapterRequest, run_work_item_lifecycle_dry_run_adapter
from sentientos.work_item_lifecycle_handoff import WorkItemLifecycleHandoffRequest, plan_work_item_lifecycle_handoff, summarize_work_item_lifecycle_handoff_plan

REVIEW_PACKET_MODES = frozenset({"review_only", "review_with_dry_run", "review_with_dry_run_closure"})


@dataclass(frozen=True)
class WorkItemDryRunReviewPolicy:
    metadata_only: bool = True


@dataclass(frozen=True)
class WorkItemDryRunReviewRequest:
    work_item_payload: Mapping[str, Any]
    workspace_root: str | None
    mode: str = "review_with_dry_run_closure"
    intake_output_path: str | None = None
    handoff_output_path: str | None = None
    dry_run_output_path: str | None = None
    closure_output_path: str | None = None
    review_output_path: str | None = None


@dataclass(frozen=True)
class WorkItemDryRunReviewStageSummary:
    stage_name: str
    attempted: bool
    completed: bool
    status: str
    blocked: bool
    skipped_reason: str | None = None


@dataclass(frozen=True)
class WorkItemDryRunReviewPacket:
    review_packet_id: str
    digest: str
    source_work_item_id: str
    source_kind: str
    source_ref: str
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
    transaction_readiness: bool | None
    authority_claim_summary: tuple[str, ...]
    contradiction_source: str
    contradiction_codes: tuple[str, ...]
    blocker_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    missing_metadata_fields: tuple[str, ...]
    artifact_records: tuple[Mapping[str, str], ...]
    operator_action: str
    explicit_non_authority_boundaries: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkItemDryRunReviewResult:
    mode: str
    packet: WorkItemDryRunReviewPacket
    stage_summaries: tuple[WorkItemDryRunReviewStageSummary, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "packet": self.packet.to_dict(),
            "stage_summaries": [asdict(x) for x in self.stage_summaries],
        }


def _write(path: str | None, payload: Mapping[str, Any], stage: str) -> tuple[Mapping[str, str], ...]:
    if not path:
        return ()
    p = Path(path)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    return ({"stage": stage, "path": str(p), "digest": digest},)


def _action(packet: Mapping[str, Any], handoff: Mapping[str, Any], dry: Mapping[str, Any] | None, closure: Mapping[str, Any] | None) -> str:
    if not packet.get("work_item_id"):
        return "failed_review_generation"
    if closure:
        st = str(closure.get("closure_status", ""))
        if st == "dry_run_closed_contradicted":
            return "contradicted_evidence"
        if st in {"dry_run_closure_insufficient_evidence", "dry_run_closed_insufficient_metadata"}:
            return "insufficient_evidence"
        if st == "dry_run_closed_blocked":
            return "blocked_authority_request"
        if st == "dry_run_closed_with_warnings":
            return "dry_run_review_with_warnings"
        if st == "dry_run_closed_clean":
            return "dry_run_clean_review"
    if dry:
        dst = str(dry.get("adapter_status", ""))
        if dst == "dry_run_adapter_blocked":
            return "blocked_authority_request"
        if dst == "dry_run_adapter_insufficient_metadata":
            return "insufficient_evidence"
    surface = str(handoff.get("recommended_next_governed_surface", ""))
    if surface == "no_action_required":
        return "no_action_required"
    if surface == "needs_operator_clarification" or str(packet.get("intake_status")) == "intake_insufficient_metadata":
        return "request_clarification"
    if surface in {"blocked_authority_request", "blocked_external_integration_request", "blocked_agent_execution_request"}:
        return "blocked_authority_request"
    if surface == "eligible_for_workspace_change_set_admission":
        return "ready_for_workspace_admission_review"
    if surface == "eligible_for_dry_run_lifecycle":
        return "ready_for_dry_run_review"
    return "manual_review_required"


def build_work_item_dry_run_review_packet(request: WorkItemDryRunReviewRequest, *, policy: WorkItemDryRunReviewPolicy | None = None) -> WorkItemDryRunReviewResult:
    _ = policy or WorkItemDryRunReviewPolicy()
    if request.mode not in REVIEW_PACKET_MODES:
        raise ValueError("unsupported review mode")

    artifacts: list[Mapping[str, str]] = []
    stages: list[WorkItemDryRunReviewStageSummary] = []

    intake_packet, _intake_decision = normalize_work_item_intake(request.work_item_payload, derive_workspace_proposal=True)
    intake_summary = summarize_work_item_packet(intake_packet)
    artifacts.extend(_write(request.intake_output_path, intake_summary, "intake"))
    stages.append(WorkItemDryRunReviewStageSummary("intake", True, True, intake_packet.intake_status, intake_packet.intake_status in {"intake_blocked", "intake_contradicted", "intake_insufficient_metadata"}))

    handoff = plan_work_item_lifecycle_handoff(WorkItemLifecycleHandoffRequest(packet=intake_summary, emit_lifecycle_candidate=True))
    handoff_summary = summarize_work_item_lifecycle_handoff_plan(handoff)
    artifacts.extend(_write(request.handoff_output_path, handoff_summary, "handoff"))
    stages.append(WorkItemDryRunReviewStageSummary("handoff", True, True, handoff.recommended_next_governed_surface, handoff.recommended_next_governed_surface.startswith("blocked_")))

    dry_summary: dict[str, Any] | None = None
    closure_summary: dict[str, Any] | None = None

    eligible = request.mode != "review_only" and handoff.recommended_next_governed_surface in {"eligible_for_dry_run_lifecycle", "eligible_for_workspace_change_set_admission"}
    if request.mode != "review_only":
        if eligible:
            dry = run_work_item_lifecycle_dry_run_adapter(WorkItemLifecycleDryRunAdapterRequest(packet=intake_summary, handoff_plan=handoff_summary, workspace_root=request.workspace_root, request_dry_run=True))
            dry_summary = dry.to_dict()
            artifacts.extend(_write(request.dry_run_output_path, dry_summary, "dry_run"))
            stages.append(WorkItemDryRunReviewStageSummary("dry_run_adapter", True, True, dry.adapter_status, dry.adapter_status in {"dry_run_adapter_blocked", "dry_run_adapter_contradicted", "dry_run_adapter_insufficient_metadata", "dry_run_adapter_failed"}))
        else:
            stages.append(WorkItemDryRunReviewStageSummary("dry_run_adapter", False, False, "dry_run_not_attempted", False, skipped_reason="handoff_not_eligible_or_mode_review_only"))

    if request.mode == "review_with_dry_run_closure":
        if dry_summary:
            closure = build_work_item_dry_run_closure_manifest(WorkItemDryRunClosureRequest(packet=intake_summary, handoff_plan=handoff_summary, dry_run_result=dry_summary))
            closure_summary = closure.manifest.to_dict()
            artifacts.extend(_write(request.closure_output_path, closure.to_dict(), "dry_run_closure"))
            stages.append(WorkItemDryRunReviewStageSummary("dry_run_closure", True, True, closure.manifest.closure_status, "contradicted" in closure.manifest.closure_status or "blocked" in closure.manifest.closure_status))
        else:
            stages.append(WorkItemDryRunReviewStageSummary("dry_run_closure", False, False, "dry_run_closure_not_attempted", False, skipped_reason="dry_run_evidence_unavailable"))

    claims = authority_claims_from_nested_evidence(intake_summary, handoff_summary, dry_summary or {}, closure_summary or {})
    contradiction_codes = tuple(sorted(set((closure_summary or {}).get("contradiction_codes", ()))))
    digest_payload = json.dumps({"intake": intake_summary, "handoff": handoff_summary, "dry": dry_summary, "closure": closure_summary}, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(digest_payload.encode("utf-8")).hexdigest()

    packet = WorkItemDryRunReviewPacket(
        review_packet_id=f"wir_{digest[:16]}",
        digest=digest,
        source_work_item_id=str(intake_summary.get("work_item_id", "")),
        source_kind=str(intake_summary.get("source_kind", "")),
        source_ref=str(intake_summary.get("source_ref", "")),
        intake_status=str(intake_summary.get("intake_status", "")),
        risk_class=str(intake_summary.get("risk_class", "")),
        handoff_recommended_surface=str(handoff_summary.get("recommended_next_governed_surface", "")),
        dry_run_adapter_status=(str(dry_summary.get("adapter_status", "")) if dry_summary else None),
        dry_run_closure_status=(str(closure_summary.get("closure_status", "")) if closure_summary else None),
        lifecycle_dry_run_invoked=bool((dry_summary or {}).get("lifecycle_orchestration_invoked", False)),
        lifecycle_mode_used=(str((dry_summary or {}).get("lifecycle_mode_used", "")).strip() or None),
        lifecycle_stop_reason=(str((dry_summary or {}).get("lifecycle_stop_reason", "")).strip() or None),
        admission_status=(str((dry_summary or {}).get("admission_status", "")).strip() or None),
        preflight_status=(str((dry_summary or {}).get("preflight_status", "")).strip() or None),
        transaction_readiness=(dry_summary or {}).get("transaction_plan_ready") if isinstance((dry_summary or {}).get("transaction_plan_ready"), bool) else None,
        authority_claim_summary=authority_claim_summary(claims),
        contradiction_source=str((closure_summary or {}).get("contradiction_source", "none")),
        contradiction_codes=contradiction_codes,
        blocker_codes=tuple(
            sorted(
                set(
                    tuple(intake_summary.get("blocker_codes", ()))
                    + tuple(handoff_summary.get("blocker_codes", ()))
                    + tuple((dry_summary or {}).get("blocker_codes", ()))
                )
            )
        ),
        warning_codes=tuple(
            sorted(
                set(
                    tuple(intake_summary.get("warning_codes", ()))
                    + tuple(handoff_summary.get("warning_codes", ()))
                    + tuple((dry_summary or {}).get("warning_codes", ()))
                )
            )
        ),
        missing_metadata_fields=tuple(
            sorted(
                set(
                    tuple(handoff_summary.get("missing_metadata_fields", ()))
                    + tuple((dry_summary or {}).get("missing_metadata_fields", ()))
                    + tuple((closure_summary or {}).get("missing_metadata_fields", ()))
                )
            )
        ),
        artifact_records=tuple(artifacts),
        operator_action=_action(intake_summary, handoff_summary, dry_summary, closure_summary),
        explicit_non_authority_boundaries=EXPLICIT_NON_AUTHORITY_BOUNDARIES,
    )

    result = WorkItemDryRunReviewResult(mode=request.mode, packet=packet, stage_summaries=tuple(stages))
    artifacts.extend(_write(request.review_output_path, result.to_dict(), "review_packet"))
    return result


__all__ = [
    "WorkItemDryRunReviewPolicy",
    "WorkItemDryRunReviewRequest",
    "WorkItemDryRunReviewStageSummary",
    "WorkItemDryRunReviewPacket",
    "WorkItemDryRunReviewResult",
    "build_work_item_dry_run_review_packet",
    "REVIEW_PACKET_MODES",
]
