from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from sentientos.work_item_intake import EXPLICIT_NON_AUTHORITY_BOUNDARIES

DRY_RUN_CLOSURE_STATUSES = frozenset({
    "dry_run_closed_clean",
    "dry_run_closed_with_warnings",
    "dry_run_closed_blocked",
    "dry_run_closed_manual_review",
    "dry_run_closed_insufficient_metadata",
    "dry_run_closed_contradicted",
    "dry_run_closure_insufficient_evidence",
})


@dataclass(frozen=True)
class WorkItemDryRunClosurePolicy:
    metadata_only: bool = True
    require_dry_run_full_lifecycle_when_invoked: bool = True


@dataclass(frozen=True)
class WorkItemDryRunClosureRequest:
    packet: Mapping[str, Any] | None
    handoff_plan: Mapping[str, Any] | None
    dry_run_result: Mapping[str, Any] | None
    closure_artifact_output_path: str | None = None


@dataclass(frozen=True)
class WorkItemDryRunClosureManifest:
    closure_status: str
    work_item_id: str
    source_kind: str
    source_ref: str
    intake_status: str
    risk_class: str
    handoff_recommended_surface: str
    dry_run_adapter_status: str
    lifecycle_dry_run_invoked: bool
    lifecycle_mode_used: str | None
    lifecycle_stop_reason: str | None
    admission_status: str | None
    preflight_status: str | None
    transaction_plan_status: str | None
    transaction_plan_ready: bool | None
    blocker_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    contradiction_codes: tuple[str, ...]
    missing_metadata_fields: tuple[str, ...]
    authority_request_summary: tuple[str, ...]
    proposal_candidate_id: str | None
    proposal_candidate_digest: str | None
    handoff_plan_id: str | None
    dry_run_artifact_records: tuple[Mapping[str, str], ...]
    explicit_non_authority_boundaries: tuple[str, ...] = EXPLICIT_NON_AUTHORITY_BOUNDARIES
    metadata_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkItemDryRunClosureResult:
    manifest: WorkItemDryRunClosureManifest
    artifact_records: tuple[Mapping[str, str], ...]

    def to_dict(self) -> dict[str, Any]:
        return {"manifest": self.manifest.to_dict(), "artifact_records": list(self.artifact_records)}


def _tuple(v: Any) -> tuple[str, ...]:
    if isinstance(v, (list, tuple)):
        return tuple(sorted({str(x).strip() for x in v if str(x).strip()}))
    return ()


def _handoff_id(plan: Mapping[str, Any]) -> str | None:
    wid = str(plan.get("work_item_id", "")).strip()
    if not wid:
        return None
    seed = json.dumps({"work_item_id": wid, "surface": plan.get("recommended_next_governed_surface", "")}, sort_keys=True, separators=(",", ":"))
    return "wih_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _write_artifact(path: str | None, payload: Mapping[str, Any]) -> tuple[Mapping[str, str], ...]:
    if not path:
        return ()
    p = Path(path)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    return ({"stage": "work_item_dry_run_closure", "path": str(p), "digest": digest},)


def build_work_item_dry_run_closure_manifest(request: WorkItemDryRunClosureRequest, *, policy: WorkItemDryRunClosurePolicy | None = None) -> WorkItemDryRunClosureResult:
    _ = policy or WorkItemDryRunClosurePolicy()
    if request.packet is None or request.handoff_plan is None or request.dry_run_result is None:
        manifest = WorkItemDryRunClosureManifest(
            closure_status="dry_run_closure_insufficient_evidence", work_item_id="", source_kind="", source_ref="", intake_status="", risk_class="",
            handoff_recommended_surface="", dry_run_adapter_status="", lifecycle_dry_run_invoked=False, lifecycle_mode_used=None, lifecycle_stop_reason=None,
            admission_status=None, preflight_status=None, transaction_plan_status=None, transaction_plan_ready=None, blocker_codes=(), warning_codes=(),
            contradiction_codes=(), missing_metadata_fields=("packet", "handoff_plan", "dry_run_result"), authority_request_summary=(), proposal_candidate_id=None,
            proposal_candidate_digest=None, handoff_plan_id=None, dry_run_artifact_records=(),
        )
        return WorkItemDryRunClosureResult(manifest=manifest, artifact_records=())

    packet = request.packet
    handoff = request.handoff_plan
    dry = request.dry_run_result

    blockers = set(_tuple(packet.get("blocker_codes")) + _tuple(handoff.get("blocker_codes")) + _tuple(dry.get("blocker_codes")))
    warnings = set(_tuple(packet.get("warning_codes")) + _tuple(handoff.get("warning_codes")) + _tuple(dry.get("warning_codes")))
    missing = set(_tuple(handoff.get("missing_metadata_fields")) + _tuple(dry.get("missing_metadata_fields")))
    contradictions: set[str] = set()

    work_item_id = str(packet.get("work_item_id", "")).strip()
    handoff_work_item_id = str(handoff.get("work_item_id", "")).strip()
    dry_work_item_id = str(dry.get("work_item_id", "")).strip()
    if not work_item_id or not handoff_work_item_id or not dry_work_item_id:
        missing.update({"work_item_id"})
    if work_item_id and handoff_work_item_id and work_item_id != handoff_work_item_id:
        contradictions.add("work_item_id_packet_handoff_mismatch")
    if work_item_id and dry_work_item_id and work_item_id != dry_work_item_id:
        contradictions.add("work_item_id_packet_dry_run_mismatch")

    if dry.get("lifecycle_orchestration_invoked") and dry.get("lifecycle_mode_used") != "dry_run_full_lifecycle":
        contradictions.add("lifecycle_mode_not_dry_run_full_lifecycle")
    if bool(packet.get("agent_execution_is_requested", False) or packet.get("agent_execution_is_permitted_by_this_packet", False)):
        contradictions.add("agent_execution_not_denied")

    forbidden = {"execution", "verification", "closure"}
    if any(tok in " ".join(_tuple(dry.get("blocker_codes")) + _tuple(dry.get("warning_codes"))).lower() for tok in forbidden):
        contradictions.add("dry_run_claims_real_effect_authority")

    adapter_status = str(dry.get("adapter_status", "")).strip()
    closure_status = "dry_run_closed_clean"
    if contradictions:
        closure_status = "dry_run_closed_contradicted"
    elif missing or adapter_status == "dry_run_adapter_insufficient_metadata":
        closure_status = "dry_run_closed_insufficient_metadata"
    elif adapter_status == "dry_run_adapter_blocked":
        closure_status = "dry_run_closed_blocked"
    elif adapter_status == "dry_run_adapter_manual_review_required":
        closure_status = "dry_run_closed_manual_review"
    elif adapter_status == "dry_run_adapter_completed" and warnings:
        closure_status = "dry_run_closed_with_warnings"

    manifest = WorkItemDryRunClosureManifest(
        closure_status=closure_status,
        work_item_id=work_item_id,
        source_kind=str(packet.get("source_kind", "")).strip(),
        source_ref=str(packet.get("source_ref", "")).strip(),
        intake_status=str(packet.get("intake_status", "")).strip(),
        risk_class=str(packet.get("risk_class", "")).strip(),
        handoff_recommended_surface=str(handoff.get("recommended_next_governed_surface", "")).strip(),
        dry_run_adapter_status=adapter_status,
        lifecycle_dry_run_invoked=bool(dry.get("lifecycle_orchestration_invoked", False)),
        lifecycle_mode_used=str(dry.get("lifecycle_mode_used", "")).strip() or None,
        lifecycle_stop_reason=str(dry.get("lifecycle_stop_reason", "")).strip() or None,
        admission_status=str(dry.get("admission_status", "")).strip() or None,
        preflight_status=str(dry.get("preflight_status", "")).strip() or None,
        transaction_plan_status=str(dry.get("transaction_plan_status", "")).strip() or None,
        transaction_plan_ready=dry.get("transaction_plan_ready") if isinstance(dry.get("transaction_plan_ready"), bool) else None,
        blocker_codes=tuple(sorted(blockers)),
        warning_codes=tuple(sorted(warnings)),
        contradiction_codes=tuple(sorted(contradictions)),
        missing_metadata_fields=tuple(sorted(missing)),
        authority_request_summary=_tuple(packet.get("declared_authority_requests")),
        proposal_candidate_id=str(handoff.get("workspace_change_set_proposal_candidate_id", "")).strip() or None,
        proposal_candidate_digest=str(handoff.get("workspace_change_set_proposal_candidate_digest", "")).strip() or None,
        handoff_plan_id=_handoff_id(handoff),
        dry_run_artifact_records=tuple(dry.get("artifact_records", ())) if isinstance(dry.get("artifact_records"), (list, tuple)) else (),
    )
    artifact_records = _write_artifact(request.closure_artifact_output_path, manifest.to_dict())
    return WorkItemDryRunClosureResult(manifest=manifest, artifact_records=artifact_records)


__all__ = [
    "DRY_RUN_CLOSURE_STATUSES",
    "WorkItemDryRunClosurePolicy",
    "WorkItemDryRunClosureRequest",
    "WorkItemDryRunClosureManifest",
    "WorkItemDryRunClosureResult",
    "build_work_item_dry_run_closure_manifest",
]
