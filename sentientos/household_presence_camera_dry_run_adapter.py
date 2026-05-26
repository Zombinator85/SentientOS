from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Literal, Mapping

from sentientos.household_presence_camera_policy_chain import evaluate_policy_chain

SessionStatus = Literal["dry_run_ready", "dry_run_ready_with_warnings", "dry_run_operator_confirmation_required", "dry_run_blocked", "dry_run_failed"]
Route = Literal["live_awareness_only", "redacted_ambient_journal", "wildlife_ledger_candidate", "security_event_metadata", "nuisance_evidence_metadata", "protected_care_summary", "operator_review_required", "blocked_by_deadzone", "blocked_by_missing_redaction", "blocked_by_adult_private_policy", "blocked_by_child_visible_policy", "blocked_by_speaker_boundary", "blocked_by_external_authority_boundary", "blocked_by_unknown_zone", "blocked_by_stale_config", "blocked_by_low_confidence", "blocked_by_policy"]

@dataclass(frozen=True)
class HouseholdCameraDryRunAdapterPolicy:
    schema_version: str = "household_presence_camera_dry_run_adapter_policy.v1"
    confirmation_max_age_days: int = 30

@dataclass(frozen=True)
class HouseholdCameraDryRunOperatorConfirmation:
    operator_id: str = ""
    operator_label: str = ""
    confirmed_at: str = ""
    confirmation_scope: str = ""
    dry_run_only: bool = True
    live_hardware_allowed: bool = False
    speaker_output_allowed: bool = False
    external_disclosure_allowed: bool = False
    raw_media_allowed: bool = False
    policy_chain_required: bool = True

@dataclass(frozen=True)
class HouseholdCameraDryRunEvent:
    event_id: str
    source_id: str
    event_payload: dict[str, Any]
    zone_config_payload: dict[str, Any]
    expected_route: str = ""

@dataclass(frozen=True)
class HouseholdCameraDryRunSessionRequest:
    confirmation: HouseholdCameraDryRunOperatorConfirmation
    events: tuple[HouseholdCameraDryRunEvent, ...]

@dataclass(frozen=True)
class HouseholdCameraDryRunEventResult:
    event_id: str
    route: Route
    blocked: bool
    reasons: tuple[str, ...]
    policy_chain_stages: tuple[dict[str, str], ...]

@dataclass(frozen=True)
class HouseholdCameraDryRunSessionReport:
    status: SessionStatus
    event_results: tuple[HouseholdCameraDryRunEventResult, ...]
    route_counts: dict[str, int]
    blocked_reason_counts: dict[str, int]
    operator_review_count: int
    deterministic_digest: str

@dataclass(frozen=True)
class HouseholdCameraDryRunAdapterResult:
    report: HouseholdCameraDryRunSessionReport
    def to_dict(self) -> dict[str, Any]: return asdict(self)

def build_default_policy() -> HouseholdCameraDryRunAdapterPolicy: return HouseholdCameraDryRunAdapterPolicy()
def validate_policy(policy: HouseholdCameraDryRunAdapterPolicy) -> dict[str, Any]:
    ok = policy.schema_version.endswith(".v1") and policy.confirmation_max_age_days > 0
    return {"ok": ok, "status": "household_presence_camera_dry_run_adapter_policy_valid" if ok else "household_presence_camera_dry_run_adapter_policy_invalid"}

def _has_media(payload: Mapping[str, Any]) -> bool:
    text = json.dumps(payload, sort_keys=True).lower()
    banned = ("base64", "image", "audio", "video", "thumbnail", "screenshot", "raw_transcript")
    return any(k in text for k in banned)

def _check_confirmation(raw: Mapping[str, Any], policy: HouseholdCameraDryRunAdapterPolicy) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if not (raw.get("operator_id") or raw.get("operator_label")): reasons.append("missing_operator_identity")
    if not raw.get("confirmed_at"): reasons.append("missing_confirmed_at")
    if not raw.get("confirmation_scope"): reasons.append("missing_confirmation_scope")
    if raw.get("dry_run_only") is not True: reasons.append("dry_run_only_required")
    if raw.get("live_hardware_allowed") is not False: reasons.append("blocked_live_hardware")
    if raw.get("speaker_output_allowed") is not False: reasons.append("blocked_speaker_boundary")
    if raw.get("external_disclosure_allowed") is not False: reasons.append("blocked_external_authority_boundary")
    if raw.get("raw_media_allowed") is not False: reasons.append("blocked_raw_media")
    if raw.get("policy_chain_required") is not True: reasons.append("policy_chain_required")
    return (len(reasons) == 0, reasons)

def evaluate_dry_run_session(payload: Mapping[str, Any], policy: HouseholdCameraDryRunAdapterPolicy | None = None) -> HouseholdCameraDryRunAdapterResult:
    p = policy or build_default_policy()
    confirmation = dict(payload.get("operator_confirmation", {})) if isinstance(payload.get("operator_confirmation"), Mapping) else {}
    ok, confirmation_reasons = _check_confirmation(confirmation, p)
    events_raw = payload.get("events", []) if isinstance(payload.get("events"), list) else []
    route_counts: dict[str, int] = {}
    blocked_reason_counts: dict[str, int] = {}
    results: list[HouseholdCameraDryRunEventResult] = []
    all_blocked = False
    if not ok:
        report = HouseholdCameraDryRunSessionReport("dry_run_operator_confirmation_required", tuple(), {}, {k: 1 for k in confirmation_reasons}, 0, hashlib.sha256(json.dumps({"confirmation": confirmation_reasons}, sort_keys=True).encode()).hexdigest())
        return HouseholdCameraDryRunAdapterResult(report)
    for item in events_raw:
        if not isinstance(item, Mapping):
            continue
        eid = str(item.get("event_id", "unknown"))
        event_payload = dict(item.get("event_payload", {})) if isinstance(item.get("event_payload"), Mapping) else {}
        if _has_media(event_payload):
            route: Route = "blocked_by_policy"
            reasons: tuple[str, ...] = ("media_payload_forbidden",)
            stages: tuple[dict[str, str], ...] = ({"name": "media_payload_scan", "status": "blocked"},)
            blocked = True
        else:
            chain = evaluate_policy_chain({"event": event_payload, "config": dict(item.get("zone_config_payload", {})) if isinstance(item.get("zone_config_payload"), Mapping) else {}})
            route = chain.decision.route
            reasons = tuple(sorted(set(chain.decision.reasons) | ({"speaker_output_requested"} if bool(event_payload.get("metadata", {}).get("speaker_action_requested", False)) else set()) | ({"external_disclosure_requested"} if bool(event_payload.get("metadata", {}).get("external_authority_contact", False)) else set())))
            if bool(event_payload.get("metadata", {}).get("speaker_action_requested", False)):
                route = "blocked_by_speaker_boundary"; blocked = True
            elif bool(event_payload.get("metadata", {}).get("external_authority_contact", False)):
                route = "blocked_by_external_authority_boundary"; blocked = True
            else:
                blocked = chain.decision.blocked
            stages = tuple(asdict(s) for s in chain.report.stages)
        route_counts[route] = route_counts.get(route, 0) + 1
        for r in reasons: blocked_reason_counts[r] = blocked_reason_counts.get(r, 0) + 1
        if blocked: all_blocked = True
        results.append(HouseholdCameraDryRunEventResult(eid, route, blocked, reasons, stages))
    review_count = route_counts.get("operator_review_required", 0)
    status: SessionStatus = "dry_run_blocked" if all_blocked else ("dry_run_ready_with_warnings" if review_count else "dry_run_ready")
    digest = hashlib.sha256(json.dumps({"routes": route_counts, "blocked": blocked_reason_counts, "events": [asdict(r) for r in results]}, sort_keys=True).encode()).hexdigest()
    return HouseholdCameraDryRunAdapterResult(HouseholdCameraDryRunSessionReport(status, tuple(results), dict(sorted(route_counts.items())), dict(sorted(blocked_reason_counts.items())), review_count, digest))

def load_session_fixture(path: str) -> dict[str, Any]: return dict(json.loads(Path(path).read_text()))
def dumps_result(result: HouseholdCameraDryRunAdapterResult) -> str: return json.dumps(result.to_dict(), indent=2, sort_keys=True)
