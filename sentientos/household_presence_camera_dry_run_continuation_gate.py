from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Literal, Mapping, Sequence, cast

GateStatus = Literal[
    "dry_run_continuation_gate_ready",
    "dry_run_continuation_gate_ready_with_warnings",
    "dry_run_continuation_gate_blocked_missing_review_packet",
    "dry_run_continuation_gate_blocked_missing_decision_ledger",
    "dry_run_continuation_gate_blocked_missing_trend_ledger",
    "dry_run_continuation_gate_blocked_missing_renewal_request_packet",
    "dry_run_continuation_gate_blocked_review_packet_not_ready",
    "dry_run_continuation_gate_blocked_decision_ledger_not_ready",
    "dry_run_continuation_gate_blocked_trend_ledger_not_ready",
    "dry_run_continuation_gate_blocked_renewal_request_not_ready",
    "dry_run_continuation_gate_blocked_operator_grant_required",
    "dry_run_continuation_gate_blocked_proof_refresh_required",
    "dry_run_continuation_gate_blocked_unresolved_denials",
    "dry_run_continuation_gate_blocked_scope_mismatch",
    "dry_run_continuation_gate_blocked_stale_review",
    "dry_run_continuation_gate_blocked_stale_trend",
    "dry_run_continuation_gate_blocked_stale_request",
    "dry_run_continuation_gate_blocked_future_live_only",
    "dry_run_continuation_gate_blocked_media_payload",
    "dry_run_continuation_gate_blocked_speaker_boundary",
    "dry_run_continuation_gate_blocked_external_authority",
    "dry_run_continuation_gate_invalid",
    "dry_run_continuation_gate_failed",
]

GateDecision = Literal[
    "continue_dry_run_only",
    "defer_dry_run_continuation",
    "require_operator_review",
    "require_operator_grant_renewal",
    "require_dry_run_proof_refresh",
    "require_policy_chain_proof_refresh",
    "require_zone_config_refresh",
    "require_disabled_capture_boundary_refresh",
    "require_capture_review_packet_rerun",
    "require_decision_ledger_review",
    "require_trend_ledger_review",
    "require_renewal_request_review",
    "sustain_capture_denial",
    "defer_future_live_review",
    "reject_continuation_request",
]

SafeNextAction = Literal[
    "no_action_allowed",
    "continue_dry_run_only_review",
    "operator_review_required",
    "request_operator_grant_renewal",
    "request_dry_run_proof_refresh",
    "request_policy_chain_proof_refresh",
    "request_zone_config_refresh",
    "request_disabled_capture_boundary_refresh",
    "rerun_capture_review_packet",
    "inspect_decision_history",
    "inspect_trend_history",
    "inspect_renewal_request",
    "sustain_capture_denial",
    "defer_future_live_review",
]

FORBIDDEN_NEXT_STEPS = (
    "open_camera_now",
    "attempt_capture",
    "enable_live_capture",
    "enable_live_recording",
    "store_raw_media",
    "attach_media_payload",
    "bypass_authorization_envelope",
    "bypass_denial_ledger",
    "bypass_review_packet",
    "bypass_review_decision_ledger",
    "bypass_operator_review_trend_ledger",
    "bypass_operator_grant_renewal_request_packet",
    "bypass_policy_chain",
    "bypass_zone_config",
    "bypass_disabled_capture_boundary",
    "bypass_dry_run",
    "infer_operator_consent_from_gate",
    "infer_operator_consent_from_trends",
    "infer_operator_consent_from_renewal_request",
    "convert_renewal_request_to_grant",
    "convert_dry_run_gate_to_live_readiness",
    "convert_dry_run_gate_to_live_capture_permission",
    "enable_speaker_output",
    "enable_external_disclosure",
)

MEDIA_KEYS = frozenset({
    "raw_media", "raw_media_payload", "media_payload", "image", "video", "audio",
    "thumbnail", "screenshot", "transcript", "base64", "base64_media", "base64_payload",
})
REFRESH_TO_DECISION_ACTION: dict[str, tuple[GateDecision, SafeNextAction]] = {
    "operator_grant_renewal": ("require_operator_grant_renewal", "request_operator_grant_renewal"),
    "dry_run_proof_refresh": ("require_dry_run_proof_refresh", "request_dry_run_proof_refresh"),
    "policy_chain_proof_refresh": ("require_policy_chain_proof_refresh", "request_policy_chain_proof_refresh"),
    "zone_config_refresh": ("require_zone_config_refresh", "request_zone_config_refresh"),
    "disabled_capture_boundary_refresh": ("require_disabled_capture_boundary_refresh", "request_disabled_capture_boundary_refresh"),
    "capture_review_packet_rerun": ("require_capture_review_packet_rerun", "rerun_capture_review_packet"),
    "decision_ledger_review": ("require_decision_ledger_review", "inspect_decision_history"),
    "trend_ledger_review": ("require_trend_ledger_review", "inspect_trend_history"),
    "denial_history_review": ("sustain_capture_denial", "sustain_capture_denial"),
    "future_live_review_deferral_confirmation": ("defer_future_live_review", "defer_future_live_review"),
}
PROOF_REFRESH_TYPES = frozenset({"dry_run_proof_refresh", "policy_chain_proof_refresh", "zone_config_refresh", "disabled_capture_boundary_refresh"})

@dataclass(frozen=True)
class HouseholdCameraDryRunContinuationGatePolicy:
    schema_version: str = "household_presence_camera_dry_run_continuation_gate_policy.v1"
    require_review_packet_digest: bool = True
    require_decision_ledger_digest: bool = True
    require_trend_ledger_digest: bool = True
    require_renewal_request_packet_digest: bool = True
    allow_diagnostic_without_renewal_request_packet: bool = False
    allow_diagnostic_continuation_when_refresh_required: bool = False
    allow_mixed_scope_diagnostic_summary: bool = False
    max_unresolved_denials: int = 0
    stale_review_mode: Literal["block", "warn"] = "block"
    stale_trend_mode: Literal["block", "warn"] = "warn"
    stale_request_mode: Literal["block", "warn"] = "warn"
    allow_ready_with_warnings_continuation_review: bool = True
    allow_future_live_deferred_context: bool = True

@dataclass(frozen=True)
class HouseholdCameraDryRunContinuationGateInput:
    review_packet: dict[str, Any]
    decision_ledger: dict[str, Any]
    trend_ledger: dict[str, Any]
    renewal_request_packet: dict[str, Any]
    policy: HouseholdCameraDryRunContinuationGatePolicy = HouseholdCameraDryRunContinuationGatePolicy()

@dataclass(frozen=True)
class HouseholdCameraDryRunContinuationGateFinding:
    code: str
    message: str

@dataclass(frozen=True)
class HouseholdCameraDryRunContinuationGateRecord:
    record_id: str
    gate_id: str
    review_packet_digest: str
    decision_ledger_digest: str
    trend_ledger_digest: str
    renewal_request_packet_digest: str
    authorization_envelope_digest: str | None
    denial_ledger_digest: str | None
    policy_chain_digest: str | None
    zone_config_digest: str | None
    dry_run_proof_digest: str | None
    source_review_packet_ids: tuple[str, ...]
    source_decision_record_ids: tuple[str, ...]
    source_trend_ids: tuple[str, ...]
    source_request_ids: tuple[str, ...]
    source_candidate_id: str | None
    requested_mode: str | None
    operator_label: str | None
    gate_decision: GateDecision
    gate_reason: str
    evaluated_at: str
    gate_expires_at: str | None
    stale_review_count: int
    stale_trend_count: int
    stale_request_count: int
    unresolved_denial_count_total: int
    renewal_required_count: int
    proof_refresh_required_count: int
    dry_run_continuation_count: int
    future_live_deferred_count: int
    scope_keys: tuple[str, ...]
    safe_next_action: SafeNextAction
    forbidden_next_steps: tuple[str, ...]
    capture_enabled: bool
    capture_available: bool
    live_hardware_enabled: bool
    raw_media_storage_enabled: bool
    no_live_capture_performed: bool
    speaker_output_enabled: bool
    external_disclosure_enabled: bool
    gate_grants_operator_consent: bool
    gate_renews_operator_grant: bool
    gate_enables_live_capture: bool
    gate_enables_live_hardware: bool
    gate_enables_raw_media_storage: bool
    gate_enables_speaker_output: bool
    gate_enables_external_disclosure: bool
    gate_confers_live_readiness: bool
    gate_confers_capture_authorization: bool
    gate_executes_dry_run: bool
    digest: str

@dataclass(frozen=True)
class HouseholdCameraDryRunContinuationGateReport:
    status: GateStatus
    summary_counts: dict[str, int]
    findings: tuple[HouseholdCameraDryRunContinuationGateFinding, ...]

@dataclass(frozen=True)
class HouseholdCameraDryRunContinuationGateResult:
    status: GateStatus
    gate: HouseholdCameraDryRunContinuationGateRecord | None
    report: HouseholdCameraDryRunContinuationGateReport
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

HouseholdCameraDryRunContinuationGateDecision = HouseholdCameraDryRunContinuationGateRecord

def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def build_default_policy() -> HouseholdCameraDryRunContinuationGatePolicy:
    return HouseholdCameraDryRunContinuationGatePolicy()

def validate_policy(policy: HouseholdCameraDryRunContinuationGatePolicy) -> dict[str, Any]:
    ok = (
        policy.schema_version.endswith(".v1")
        and policy.stale_review_mode in {"block", "warn"}
        and policy.stale_trend_mode in {"block", "warn"}
        and policy.stale_request_mode in {"block", "warn"}
        and policy.max_unresolved_denials >= 0
    )
    return {"ok": ok, "status": "household_presence_camera_dry_run_continuation_gate_policy_valid" if ok else "household_presence_camera_dry_run_continuation_gate_policy_invalid"}

def _has_media_payload(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            lower = str(key).lower()
            if (lower in MEDIA_KEYS or "base64" in lower or (lower.endswith("payload") and "media" in lower)) and item not in (None, "", False, [], {}):
                return True
            if _has_media_payload(item):
                return True
    if isinstance(value, list):
        return any(_has_media_payload(item) for item in value)
    return False

def _truthy_any(value: Any, keys: Sequence[str]) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            lower = str(key).lower()
            if lower in keys and bool(item):
                return True
            if _truthy_any(item, keys):
                return True
    if isinstance(value, list):
        return any(_truthy_any(item, keys) for item in value)
    return False

def _records(value: Any) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, Mapping):
        return ()
    candidates = (value.get("records"), value.get("decision_records"), value.get("trend_records"), value.get("request_records"))
    for candidate in candidates:
        if isinstance(candidate, list):
            return tuple(item for item in candidate if isinstance(item, Mapping))
    for key in ("packet", "ledger", "gate"):
        nested = value.get(key)
        if isinstance(nested, Mapping):
            found = _records(nested)
            if found:
                return found
    return ()

def _status(value: Mapping[str, Any]) -> str:
    return str(value.get("status") or value.get("packet_status") or value.get("ledger_status") or "")

def _ready(value: Mapping[str, Any], prefix: str, policy: HouseholdCameraDryRunContinuationGatePolicy) -> bool:
    status = _status(value)
    if status.endswith("_ready"):
        return True
    if status.endswith("_ready_with_warnings"):
        return policy.allow_ready_with_warnings_continuation_review
    return status == "ready" or (status == "ready_with_warnings" and policy.allow_ready_with_warnings_continuation_review)

def _digest_from(*values: Mapping[str, Any], key: str) -> str:
    for value in values:
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate:
            return candidate
        for nested_key in ("packet", "ledger", "gate", "metadata"):
            nested = value.get(nested_key)
            if isinstance(nested, Mapping):
                nested_candidate = nested.get(key)
                if isinstance(nested_candidate, str) and nested_candidate:
                    return nested_candidate
                generic = nested.get("digest")
                if key.endswith("digest") and isinstance(generic, str) and generic:
                    return generic
    return ""

def _ids(records: Sequence[Mapping[str, Any]], *keys: str) -> tuple[str, ...]:
    out: set[str] = set()
    for record in records:
        for key in keys:
            item = record.get(key)
            if isinstance(item, str) and item:
                out.add(item)
            elif isinstance(item, list):
                out.update(str(entry) for entry in item if str(entry))
            elif isinstance(item, tuple):
                out.update(str(entry) for entry in item if str(entry))
    return tuple(sorted(out))

def _count(value: Any, *keys: str) -> int:
    total = 0
    if isinstance(value, Mapping):
        for key in keys:
            item = value.get(key)
            if isinstance(item, bool):
                total += int(item)
            elif isinstance(item, int):
                total += item
            elif isinstance(item, str) and item.isdigit():
                total += int(item)
        counts = value.get("summary_counts")
        if isinstance(counts, Mapping):
            for key in keys:
                item = counts.get(key)
                if isinstance(item, int):
                    total += item
        for nested in (value.get("packet"), value.get("ledger"), value.get("gate")):
            total += _count(nested, *keys)
    elif isinstance(value, list):
        total += sum(_count(item, *keys) for item in value)
    return total

def _contains_text(value: Any, needles: frozenset[str]) -> bool:
    if isinstance(value, str):
        return value in needles or any(needle in value for needle in needles)
    if isinstance(value, Mapping):
        return any(_contains_text(item, needles) for item in value.values())
    if isinstance(value, list):
        return any(_contains_text(item, needles) for item in value)
    return False

def _scope(record: Mapping[str, Any]) -> str:
    candidate = record.get("source_candidate_id") or record.get("candidate_id") or "candidate:any"
    mode = record.get("requested_mode") or record.get("mode") or "mode:any"
    operator = record.get("operator_label") or "operator:any"
    return f"candidate={candidate}|mode={mode}|operator={operator}"

def _blocked(status: GateStatus, code: str, message: str) -> HouseholdCameraDryRunContinuationGateResult:
    finding = HouseholdCameraDryRunContinuationGateFinding(code, message)
    report = HouseholdCameraDryRunContinuationGateReport(status, {"record_count": 0}, (finding,))
    return HouseholdCameraDryRunContinuationGateResult(status, None, report)

def _make_record(*, payload: Mapping[str, Any], review: Mapping[str, Any], decision: Mapping[str, Any], trend: Mapping[str, Any], renewal: Mapping[str, Any], gate_decision: GateDecision, gate_reason: str, safe_next_action: SafeNextAction, findings: Sequence[HouseholdCameraDryRunContinuationGateFinding], warned: bool) -> HouseholdCameraDryRunContinuationGateRecord:
    decision_records = _records(decision)
    trend_records = _records(trend)
    request_records = _records(renewal)
    review_records = _records(review) or (review,)
    all_records = tuple(review_records + decision_records + trend_records + request_records)
    scope_keys = tuple(sorted({_scope(record) for record in all_records}))
    stale_review_count = _count(payload, "stale_review_count", "stale_review")
    stale_trend_count = _count(payload, "stale_trend_count", "stale_trend")
    stale_request_count = _count(payload, "stale_request_count", "stale_request")
    unresolved_denial_count_total = _count(payload, "unresolved_denial_count", "unresolved_denial_count_total")
    renewal_required_count = sum(1 for record in request_records if _contains_text(record, frozenset({"operator_grant_renewal", "request_operator_grant_renewal", "require_operator_grant_renewal"})))
    proof_refresh_required_count = sum(1 for record in request_records if _contains_text(record, PROOF_REFRESH_TYPES))
    dry_run_continuation_count = sum(1 for record in all_records if _contains_text(record, frozenset({"dry_run_only", "allow_dry_run_only_continuation", "continue_dry_run_only", "continue_dry_run_only_review"})))
    future_live_deferred_count = sum(1 for record in all_records if _contains_text(record, frozenset({"future_live_review_deferred", "mark_future_live_review_deferred", "defer_future_live_review"})))
    source_candidate_id = next((str(record.get("source_candidate_id") or record.get("candidate_id")) for record in all_records if record.get("source_candidate_id") or record.get("candidate_id")), None)
    requested_mode = next((str(record.get("requested_mode") or record.get("mode")) for record in all_records if record.get("requested_mode") or record.get("mode")), None)
    operator_label = next((str(record.get("operator_label")) for record in all_records if record.get("operator_label")), None)
    base: dict[str, Any] = {
        "record_id": "dry-run-continuation-gate-record-" + _digest({"decision": gate_decision, "scope_keys": scope_keys})[:16],
        "gate_id": "household-presence-camera-dry-run-continuation-gate-v1",
        "review_packet_digest": _digest_from(payload, review, key="review_packet_digest") or _digest(review),
        "decision_ledger_digest": _digest_from(payload, decision, key="decision_ledger_digest") or _digest(decision),
        "trend_ledger_digest": _digest_from(payload, trend, key="trend_ledger_digest") or _digest(trend),
        "renewal_request_packet_digest": _digest_from(payload, renewal, key="renewal_request_packet_digest") or _digest(renewal),
        "authorization_envelope_digest": _digest_from(payload, review, key="authorization_envelope_digest") or None,
        "denial_ledger_digest": _digest_from(payload, review, decision, key="denial_ledger_digest") or None,
        "policy_chain_digest": _digest_from(payload, review, decision, key="policy_chain_digest") or None,
        "zone_config_digest": _digest_from(payload, review, decision, key="zone_config_digest") or None,
        "dry_run_proof_digest": _digest_from(payload, review, decision, renewal, key="dry_run_proof_digest") or None,
        "source_review_packet_ids": _ids(review_records, "review_packet_id", "packet_id", "source_review_packet_ids"),
        "source_decision_record_ids": _ids(decision_records, "record_id", "decision_record_id", "source_record_ids", "source_decision_record_ids"),
        "source_trend_ids": _ids(trend_records, "trend_id", "source_trend_ids"),
        "source_request_ids": _ids(request_records, "request_id", "source_request_ids"),
        "source_candidate_id": source_candidate_id,
        "requested_mode": requested_mode,
        "operator_label": operator_label,
        "gate_decision": gate_decision,
        "gate_reason": gate_reason,
        "evaluated_at": "1970-01-01T00:00:00Z",
        "gate_expires_at": None,
        "stale_review_count": stale_review_count,
        "stale_trend_count": stale_trend_count,
        "stale_request_count": stale_request_count,
        "unresolved_denial_count_total": unresolved_denial_count_total,
        "renewal_required_count": renewal_required_count,
        "proof_refresh_required_count": proof_refresh_required_count,
        "dry_run_continuation_count": dry_run_continuation_count,
        "future_live_deferred_count": future_live_deferred_count,
        "scope_keys": scope_keys,
        "safe_next_action": safe_next_action,
        "forbidden_next_steps": FORBIDDEN_NEXT_STEPS,
        "capture_enabled": False,
        "capture_available": False,
        "live_hardware_enabled": False,
        "raw_media_storage_enabled": False,
        "no_live_capture_performed": True,
        "speaker_output_enabled": False,
        "external_disclosure_enabled": False,
        "gate_grants_operator_consent": False,
        "gate_renews_operator_grant": False,
        "gate_enables_live_capture": False,
        "gate_enables_live_hardware": False,
        "gate_enables_raw_media_storage": False,
        "gate_enables_speaker_output": False,
        "gate_enables_external_disclosure": False,
        "gate_confers_live_readiness": False,
        "gate_confers_capture_authorization": False,
        "gate_executes_dry_run": False,
    }
    base["digest"] = _digest(base)
    return HouseholdCameraDryRunContinuationGateRecord(**base)

def evaluate_dry_run_continuation_gate(payload: Mapping[str, Any], policy: HouseholdCameraDryRunContinuationGatePolicy | None = None) -> HouseholdCameraDryRunContinuationGateResult:
    active_policy = policy or _policy_from_payload(payload)
    if not validate_policy(active_policy)["ok"]:
        return _blocked("dry_run_continuation_gate_invalid", "invalid_policy", "gate policy is invalid")
    if _has_media_payload(payload):
        return _blocked("dry_run_continuation_gate_blocked_media_payload", "media_payload", "media/base64 payloads are forbidden")
    if _truthy_any(payload, ("speaker_output_requested", "speaker_output_enabled", "talkback_requested", "talkback_enabled")):
        return _blocked("dry_run_continuation_gate_blocked_speaker_boundary", "speaker_boundary", "speaker/talkback behavior is forbidden")
    if _truthy_any(payload, ("external_disclosure_requested", "external_disclosure_enabled", "external_authority_requested")):
        return _blocked("dry_run_continuation_gate_blocked_external_authority", "external_authority", "external disclosure/authority is forbidden")

    review = cast(Mapping[str, Any], payload.get("review_packet") or payload.get("capture_review_packet") or {})
    decision = cast(Mapping[str, Any], payload.get("decision_ledger") or payload.get("capture_review_decision_ledger") or {})
    trend = cast(Mapping[str, Any], payload.get("trend_ledger") or payload.get("operator_review_trend_ledger") or {})
    renewal = cast(Mapping[str, Any], payload.get("renewal_request_packet") or payload.get("operator_grant_renewal_request_packet") or {})
    if not review:
        return _blocked("dry_run_continuation_gate_blocked_missing_review_packet", "missing_review_packet", "capture review packet evidence is required")
    if not decision:
        return _blocked("dry_run_continuation_gate_blocked_missing_decision_ledger", "missing_decision_ledger", "capture review decision ledger evidence is required")
    if not trend:
        return _blocked("dry_run_continuation_gate_blocked_missing_trend_ledger", "missing_trend_ledger", "operator review trend ledger evidence is required")
    if not renewal and not active_policy.allow_diagnostic_without_renewal_request_packet:
        return _blocked("dry_run_continuation_gate_blocked_missing_renewal_request_packet", "missing_renewal_request_packet", "operator grant renewal request packet evidence is required")
    if active_policy.require_review_packet_digest and not (_digest_from(payload, review, key="review_packet_digest") or review.get("digest")):
        return _blocked("dry_run_continuation_gate_blocked_missing_review_packet", "missing_review_packet_digest", "review packet digest is required")
    if active_policy.require_decision_ledger_digest and not (_digest_from(payload, decision, key="decision_ledger_digest") or decision.get("digest")):
        return _blocked("dry_run_continuation_gate_blocked_missing_decision_ledger", "missing_decision_ledger_digest", "decision ledger digest is required")
    if active_policy.require_trend_ledger_digest and not (_digest_from(payload, trend, key="trend_ledger_digest") or trend.get("digest")):
        return _blocked("dry_run_continuation_gate_blocked_missing_trend_ledger", "missing_trend_ledger_digest", "trend ledger digest is required")
    if active_policy.require_renewal_request_packet_digest and renewal and not (_digest_from(payload, renewal, key="renewal_request_packet_digest") or renewal.get("digest")):
        return _blocked("dry_run_continuation_gate_blocked_missing_renewal_request_packet", "missing_renewal_request_packet_digest", "renewal request packet digest is required")

    if _contains_text(review, frozenset({"future_live_only", "live_only", "enable_live_capture"})):
        return _blocked("dry_run_continuation_gate_blocked_future_live_only", "future_live_only", "live-only or future-live-only review evidence cannot continue dry-run review")
    if not _ready(review, "capture_review_packet", active_policy):
        return _blocked("dry_run_continuation_gate_blocked_review_packet_not_ready", "review_packet_not_ready", "capture review packet is not ready")
    if not _ready(decision, "capture_review_decision_ledger", active_policy):
        return _blocked("dry_run_continuation_gate_blocked_decision_ledger_not_ready", "decision_ledger_not_ready", "capture review decision ledger is not ready")
    if not _ready(trend, "operator_review_trend_ledger", active_policy):
        return _blocked("dry_run_continuation_gate_blocked_trend_ledger_not_ready", "trend_ledger_not_ready", "operator review trend ledger is not ready")
    if renewal and not _ready(renewal, "operator_grant_renewal_request_packet", active_policy):
        return _blocked("dry_run_continuation_gate_blocked_renewal_request_not_ready", "renewal_request_not_ready", "operator grant renewal request packet is not ready")
    if _truthy_any(payload, ("request_grants_operator_consent", "request_renews_operator_grant", "trend_confers_live_readiness", "request_confers_live_readiness", "gate_grants_operator_consent", "gate_renews_operator_grant")):
        return _blocked("dry_run_continuation_gate_blocked_operator_grant_required", "unsafe_consent_or_grant_claim", "upstream evidence must not grant consent, renew grants, or confer live readiness")

    all_records = tuple((_records(review) or (review,)) + _records(decision) + _records(trend) + _records(renewal))
    scope_keys = tuple(sorted({_scope(record) for record in all_records}))
    findings: list[HouseholdCameraDryRunContinuationGateFinding] = []
    warned = False
    if len(scope_keys) > 1 and not active_policy.allow_mixed_scope_diagnostic_summary:
        return _blocked("dry_run_continuation_gate_blocked_scope_mismatch", "scope_mismatch", "review, decision, trend, and request evidence scopes differ")
    if len(scope_keys) > 1:
        warned = True
        findings.append(HouseholdCameraDryRunContinuationGateFinding("mixed_scope_diagnostic_summary", "mixed scope output is warning-only and never merges scope into authority"))
    if not renewal and active_policy.allow_diagnostic_without_renewal_request_packet:
        warned = True
        findings.append(HouseholdCameraDryRunContinuationGateFinding("diagnostic_without_renewal_request_packet", "missing renewal request packet is diagnostic-only"))

    stale_review_count = _count(payload, "stale_review_count", "stale_review")
    stale_trend_count = _count(payload, "stale_trend_count", "stale_trend")
    stale_request_count = _count(payload, "stale_request_count", "stale_request")
    if stale_review_count:
        if active_policy.stale_review_mode == "block":
            return _blocked("dry_run_continuation_gate_blocked_stale_review", "stale_review", "stale review evidence is blocked by policy")
        warned = True
        findings.append(HouseholdCameraDryRunContinuationGateFinding("stale_review", "stale review evidence requires review refresh"))
    if stale_trend_count:
        if active_policy.stale_trend_mode == "block":
            return _blocked("dry_run_continuation_gate_blocked_stale_trend", "stale_trend", "stale trend evidence is blocked by policy")
        warned = True
        findings.append(HouseholdCameraDryRunContinuationGateFinding("stale_trend", "stale trend evidence requires trend review"))
    if stale_request_count:
        if active_policy.stale_request_mode == "block":
            return _blocked("dry_run_continuation_gate_blocked_stale_request", "stale_request", "stale renewal request evidence is blocked by policy")
        warned = True
        findings.append(HouseholdCameraDryRunContinuationGateFinding("stale_request", "stale renewal request evidence requires request review"))

    unresolved_denial_count_total = _count(payload, "unresolved_denial_count", "unresolved_denial_count_total")
    if unresolved_denial_count_total > active_policy.max_unresolved_denials:
        return _blocked("dry_run_continuation_gate_blocked_unresolved_denials", "unresolved_denials", "unresolved denials exceed policy threshold")

    request_records = _records(renewal)
    if request_records:
        for record in request_records:
            refreshes = record.get("requested_refresh_types") or record.get("refresh_types") or []
            refresh_values = [str(item) for item in refreshes] if isinstance(refreshes, (list, tuple)) else [str(refreshes)]
            action = str(record.get("safe_next_action") or "")
            reason = str(record.get("request_reason") or "")
            if "operator_grant_renewal" in refresh_values or action == "request_operator_grant_renewal" or "operator_grant" in reason:
                return _blocked("dry_run_continuation_gate_blocked_operator_grant_required", "operator_grant_required", "operator grant renewal request blocks continuation until explicit renewal proof exists")
            for refresh in refresh_values:
                if refresh in PROOF_REFRESH_TYPES and not active_policy.allow_diagnostic_continuation_when_refresh_required:
                    return _blocked("dry_run_continuation_gate_blocked_proof_refresh_required", "proof_refresh_required", f"{refresh} blocks dry-run continuation by default")
                if refresh in {"capture_review_packet_rerun", "decision_ledger_review", "trend_ledger_review"}:
                    decision_name, action_name = REFRESH_TO_DECISION_ACTION[refresh]
                    status: GateStatus = "dry_run_continuation_gate_ready_with_warnings" if active_policy.allow_diagnostic_continuation_when_refresh_required else "dry_run_continuation_gate_blocked_proof_refresh_required"
                    if not active_policy.allow_diagnostic_continuation_when_refresh_required:
                        return _blocked(status, "proof_refresh_required", f"{refresh} blocks dry-run continuation by default")
                    warned = True
                    findings.append(HouseholdCameraDryRunContinuationGateFinding(refresh, f"{refresh} requires review before continuation"))
                    gate = _make_record(payload=payload, review=review, decision=decision, trend=trend, renewal=renewal, gate_decision=decision_name, gate_reason=refresh, safe_next_action=action_name, findings=findings, warned=warned)
                    report = HouseholdCameraDryRunContinuationGateReport(status, _summary_counts(gate), tuple(findings))
                    return HouseholdCameraDryRunContinuationGateResult(status, gate, report)
    if _contains_text(payload, frozenset({"sustain_capture_denial", "sustained_denial_history", "deny_capture_request"})):
        return _blocked("dry_run_continuation_gate_blocked_unresolved_denials", "sustain_capture_denial", "denial history must remain sustained")
    if _contains_text(payload, frozenset({"operator_review_required", "repeated_review_deferrals"})):
        gate_decision: GateDecision = "require_operator_review"
        safe_action: SafeNextAction = "operator_review_required"
        warned = True
        findings.append(HouseholdCameraDryRunContinuationGateFinding("operator_review_required", "operator review is required before continuation"))
    elif _contains_text(payload, frozenset({"future_live_review_deferred", "mark_future_live_review_deferred", "defer_future_live_review"})):
        if not active_policy.allow_future_live_deferred_context:
            return _blocked("dry_run_continuation_gate_blocked_future_live_only", "future_live_deferred_context", "future live context is blocked by policy")
        gate_decision = "defer_future_live_review"
        safe_action = "defer_future_live_review"
        warned = True
        findings.append(HouseholdCameraDryRunContinuationGateFinding("future_live_review_deferred", "future live review remains deferred and confers no live readiness"))
    else:
        gate_decision = "continue_dry_run_only"
        safe_action = "continue_dry_run_only_review"

    gate = _make_record(payload=payload, review=review, decision=decision, trend=trend, renewal=renewal, gate_decision=gate_decision, gate_reason="metadata_only_dry_run_continuation_review", safe_next_action=safe_action, findings=findings, warned=warned)
    status = "dry_run_continuation_gate_ready_with_warnings" if warned else "dry_run_continuation_gate_ready"
    report = HouseholdCameraDryRunContinuationGateReport(cast(GateStatus, status), _summary_counts(gate), tuple(findings))
    return HouseholdCameraDryRunContinuationGateResult(cast(GateStatus, status), gate, report)

def _summary_counts(gate: HouseholdCameraDryRunContinuationGateRecord) -> dict[str, int]:
    return dict(sorted({
        "record_count": 1,
        "stale_review_count": gate.stale_review_count,
        "stale_trend_count": gate.stale_trend_count,
        "stale_request_count": gate.stale_request_count,
        "unresolved_denial_count_total": gate.unresolved_denial_count_total,
        "renewal_required_count": gate.renewal_required_count,
        "proof_refresh_required_count": gate.proof_refresh_required_count,
        "dry_run_continuation_count": gate.dry_run_continuation_count,
        "future_live_deferred_count": gate.future_live_deferred_count,
        "scope_count": len(gate.scope_keys),
    }.items()))

def _policy_from_payload(payload: Mapping[str, Any]) -> HouseholdCameraDryRunContinuationGatePolicy:
    policy_payload = payload.get("policy")
    if isinstance(policy_payload, Mapping):
        allowed = set(HouseholdCameraDryRunContinuationGatePolicy.__dataclass_fields__)
        return HouseholdCameraDryRunContinuationGatePolicy(**{k: v for k, v in policy_payload.items() if k in allowed})
    return build_default_policy()
