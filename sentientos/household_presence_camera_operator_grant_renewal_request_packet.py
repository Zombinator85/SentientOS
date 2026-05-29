from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Literal, Mapping, Sequence, cast

RequestStatus = Literal[
    "operator_grant_renewal_request_packet_ready",
    "operator_grant_renewal_request_packet_ready_with_warnings",
    "operator_grant_renewal_request_packet_blocked_missing_trend_ledger",
    "operator_grant_renewal_request_packet_blocked_missing_decision_ledger",
    "operator_grant_renewal_request_packet_blocked_missing_review_packet",
    "operator_grant_renewal_request_packet_blocked_invalid_trend_record",
    "operator_grant_renewal_request_packet_blocked_no_renewal_pressure",
    "operator_grant_renewal_request_packet_blocked_scope_mismatch",
    "operator_grant_renewal_request_packet_blocked_stale_trend",
    "operator_grant_renewal_request_packet_blocked_media_payload",
    "operator_grant_renewal_request_packet_blocked_speaker_boundary",
    "operator_grant_renewal_request_packet_blocked_external_authority",
    "operator_grant_renewal_request_packet_invalid",
    "operator_grant_renewal_request_packet_failed",
]

RequestReason = Literal[
    "repeated_operator_grant_renewal_pressure",
    "expired_or_missing_operator_grant_pressure",
    "repeated_dry_run_repair_pressure",
    "repeated_policy_chain_repair_pressure",
    "repeated_zone_config_repair_pressure",
    "repeated_disabled_capture_boundary_repair_pressure",
    "repeated_capture_denial_pressure",
    "stale_review_refresh_required",
    "stale_trend_refresh_required",
    "future_live_review_remains_deferred",
    "dry_run_continuation_requires_operator_review",
    "mixed_scope_requires_operator_review",
    "no_renewal_request_required",
]

RequestedRefreshType = Literal[
    "operator_grant_renewal",
    "dry_run_proof_refresh",
    "policy_chain_proof_refresh",
    "zone_config_refresh",
    "disabled_capture_boundary_refresh",
    "capture_review_packet_rerun",
    "decision_ledger_review",
    "trend_ledger_review",
    "denial_history_review",
    "future_live_review_deferral_confirmation",
]

SafeNextAction = Literal[
    "no_action_allowed",
    "operator_review_required",
    "request_operator_grant_renewal",
    "request_dry_run_proof_refresh",
    "request_policy_chain_proof_refresh",
    "request_zone_config_refresh",
    "request_disabled_capture_boundary_refresh",
    "rerun_capture_review_packet",
    "inspect_decision_history",
    "inspect_trend_history",
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
    "bypass_policy_chain",
    "bypass_zone_config",
    "bypass_disabled_capture_boundary",
    "bypass_dry_run",
    "infer_operator_consent_from_trends",
    "infer_operator_consent_from_renewal_request",
    "convert_renewal_request_to_grant",
    "convert_renewal_request_to_live_readiness",
    "enable_speaker_output",
    "enable_external_disclosure",
)

MEDIA_KEYS = frozenset({"raw_media", "raw_media_payload", "media_payload", "image", "video", "audio", "thumbnail", "screenshot", "transcript"})

TREND_REASON_REFRESH_ACTION: dict[str, tuple[RequestReason, RequestedRefreshType, SafeNextAction]] = {
    "repeated_operator_grant_renewals": ("repeated_operator_grant_renewal_pressure", "operator_grant_renewal", "request_operator_grant_renewal"),
    "expired_or_missing_operator_grant_pressure": ("expired_or_missing_operator_grant_pressure", "operator_grant_renewal", "request_operator_grant_renewal"),
    "repeated_dry_run_repairs": ("repeated_dry_run_repair_pressure", "dry_run_proof_refresh", "request_dry_run_proof_refresh"),
    "repeated_policy_chain_repairs": ("repeated_policy_chain_repair_pressure", "policy_chain_proof_refresh", "request_policy_chain_proof_refresh"),
    "repeated_zone_config_repairs": ("repeated_zone_config_repair_pressure", "zone_config_refresh", "request_zone_config_refresh"),
    "repeated_disabled_capture_boundary_repairs": ("repeated_disabled_capture_boundary_repair_pressure", "disabled_capture_boundary_refresh", "request_disabled_capture_boundary_refresh"),
    "repeated_capture_denials": ("repeated_capture_denial_pressure", "denial_history_review", "sustain_capture_denial"),
    "sustained_denial_history": ("repeated_capture_denial_pressure", "denial_history_review", "sustain_capture_denial"),
    "rejected_review_packet_history": ("stale_review_refresh_required", "capture_review_packet_rerun", "rerun_capture_review_packet"),
    "stale_review_pattern": ("stale_review_refresh_required", "capture_review_packet_rerun", "rerun_capture_review_packet"),
    "stale_trend_pattern": ("stale_trend_refresh_required", "trend_ledger_review", "inspect_trend_history"),
    "dry_run_only_continuation_history": ("dry_run_continuation_requires_operator_review", "decision_ledger_review", "operator_review_required"),
    "future_live_review_deferred_history": ("future_live_review_remains_deferred", "future_live_review_deferral_confirmation", "defer_future_live_review"),
    "mixed_operator_review_pattern": ("mixed_scope_requires_operator_review", "decision_ledger_review", "inspect_decision_history"),
}

@dataclass(frozen=True)
class HouseholdCameraOperatorGrantRenewalRequestPolicy:
    schema_version: str = "household_presence_camera_operator_grant_renewal_request_packet_policy.v1"
    require_decision_ledger_digest: bool = True
    require_review_packet_digest: bool = True
    allow_trend_only_diagnostic_packet: bool = False
    allow_noop_request_packet: bool = False
    allow_mixed_scope_diagnostic_summary: bool = False
    stale_trend_mode: Literal["block", "warn"] = "warn"
    stale_review_mode: Literal["block", "warn"] = "warn"
    renewal_pressure_threshold: int = 1
    repair_pressure_threshold: int = 1
    denial_pressure_threshold: int = 1

@dataclass(frozen=True)
class HouseholdCameraOperatorGrantRenewalRequestInput:
    trend_ledger: dict[str, Any]
    decision_ledger_digest: str | None = None
    review_packet_digest: str | None = None
    policy: HouseholdCameraOperatorGrantRenewalRequestPolicy = HouseholdCameraOperatorGrantRenewalRequestPolicy()

@dataclass(frozen=True)
class HouseholdCameraOperatorGrantRenewalRequestFinding:
    code: str
    message: str

@dataclass(frozen=True)
class HouseholdCameraOperatorGrantRenewalRequestRecord:
    record_id: str
    request_id: str
    trend_ledger_digest: str
    decision_ledger_digest: str | None
    review_packet_digest: str | None
    authorization_envelope_digest: str | None
    denial_ledger_digest: str | None
    policy_chain_digest: str | None
    zone_config_digest: str | None
    dry_run_proof_digest: str | None
    source_trend_ids: tuple[str, ...]
    source_record_ids: tuple[str, ...]
    review_packet_ids: tuple[str, ...]
    source_candidate_id: str | None
    requested_mode: str | None
    operator_label: str | None
    request_reason: RequestReason
    requested_refresh_types: tuple[RequestedRefreshType, ...]
    requested_at: str
    request_expires_at: str | None
    stale_trend_count: int
    stale_review_count: int
    unresolved_denial_count_total: int
    renewal_pressure_count: int
    repair_pressure_count: int
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
    request_grants_operator_consent: bool
    request_renews_operator_grant: bool
    request_enables_live_capture: bool
    request_enables_dry_run_continuation: bool
    request_confers_live_readiness: bool
    digest: str

@dataclass(frozen=True)
class HouseholdCameraOperatorGrantRenewalRequestPacket:
    records: tuple[HouseholdCameraOperatorGrantRenewalRequestRecord, ...]
    digest: str

@dataclass(frozen=True)
class HouseholdCameraOperatorGrantRenewalRequestReport:
    status: RequestStatus
    summary_counts: dict[str, int]
    findings: tuple[HouseholdCameraOperatorGrantRenewalRequestFinding, ...]

@dataclass(frozen=True)
class HouseholdCameraOperatorGrantRenewalRequestResult:
    status: RequestStatus
    packet: HouseholdCameraOperatorGrantRenewalRequestPacket
    report: HouseholdCameraOperatorGrantRenewalRequestReport
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def build_default_policy() -> HouseholdCameraOperatorGrantRenewalRequestPolicy:
    return HouseholdCameraOperatorGrantRenewalRequestPolicy()


def validate_policy(policy: HouseholdCameraOperatorGrantRenewalRequestPolicy) -> dict[str, Any]:
    ok = policy.schema_version.endswith(".v1") and policy.stale_trend_mode in {"block", "warn"} and policy.stale_review_mode in {"block", "warn"} and policy.renewal_pressure_threshold >= 1 and policy.repair_pressure_threshold >= 1 and policy.denial_pressure_threshold >= 1
    return {"ok": ok, "status": "household_presence_camera_operator_grant_renewal_request_packet_policy_valid" if ok else "household_presence_camera_operator_grant_renewal_request_packet_policy_invalid"}


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


def _truthy(value: Mapping[str, Any], keys: Sequence[str]) -> bool:
    for key in keys:
        if bool(value.get(key)):
            return True
    return False


def _blocked(status: RequestStatus, code: str, message: str) -> HouseholdCameraOperatorGrantRenewalRequestResult:
    packet = HouseholdCameraOperatorGrantRenewalRequestPacket((), _digest([]))
    finding = HouseholdCameraOperatorGrantRenewalRequestFinding(code, message)
    report = HouseholdCameraOperatorGrantRenewalRequestReport(status, {"record_count": 0}, (finding,))
    return HouseholdCameraOperatorGrantRenewalRequestResult(status, packet, report)


def _payload_policy(payload: Mapping[str, Any], policy: HouseholdCameraOperatorGrantRenewalRequestPolicy | None) -> HouseholdCameraOperatorGrantRenewalRequestPolicy:
    if policy is not None:
        return policy
    raw = payload.get("policy")
    if isinstance(raw, Mapping):
        allowed = set(HouseholdCameraOperatorGrantRenewalRequestPolicy.__dataclass_fields__)
        return HouseholdCameraOperatorGrantRenewalRequestPolicy(**{str(k): v for k, v in raw.items() if str(k) in allowed})
    return build_default_policy()


def _trend_ledger(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    raw = payload.get("trend_ledger") or payload.get("ledger")
    return cast(Mapping[str, Any], raw) if isinstance(raw, Mapping) else None


def _records(ledger: Mapping[str, Any]) -> Sequence[Any]:
    raw = ledger.get("records")
    return cast(Sequence[Any], raw) if isinstance(raw, list) else ()


def _digest_from(payload: Mapping[str, Any], ledger: Mapping[str, Any], key: str) -> str | None:
    raw = payload.get(key)
    if isinstance(raw, str) and raw:
        return raw
    raw = ledger.get(key)
    return str(raw) if isinstance(raw, str) and raw else None


def _scope(record: Mapping[str, Any]) -> str:
    return "|".join(str(record.get(k) or "") for k in ("source_candidate_id", "requested_mode", "operator_label"))


def _count(record: Mapping[str, Any], *keys: str) -> int:
    for key in keys:
        value = record.get(key)
        if isinstance(value, int):
            return value
    return 0


def _ids(record: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = record.get(key)
    if isinstance(value, list):
        return tuple(sorted(str(item) for item in value))
    if isinstance(value, tuple):
        return tuple(sorted(str(item) for item in value))
    return ()


def _make_record(*, reason: RequestReason, refreshes: Sequence[RequestedRefreshType], action: SafeNextAction, members: Sequence[Mapping[str, Any]], payload: Mapping[str, Any], ledger: Mapping[str, Any], stale_trend_count: int) -> HouseholdCameraOperatorGrantRenewalRequestRecord:
    source_trend_ids = tuple(sorted(str(m.get("trend_id") or m.get("record_id") or "trend") for m in members))
    source_record_ids = tuple(sorted({rid for m in members for rid in _ids(m, "source_record_ids")}))
    review_packet_ids = tuple(sorted({rid for m in members for rid in _ids(m, "review_packet_ids")}))
    scope_keys = tuple(sorted({_scope(m) for m in members}))
    source_candidate_ids = tuple(sorted({str(m.get("source_candidate_id")) for m in members if m.get("source_candidate_id")}))
    requested_modes = tuple(sorted({str(m.get("requested_mode")) for m in members if m.get("requested_mode")}))
    operator_labels = tuple(sorted({str(m.get("operator_label")) for m in members if m.get("operator_label")}))
    trend_digest = _digest_from(payload, ledger, "trend_ledger_digest") or str(ledger.get("digest") or _digest(ledger))
    decision_digest = _digest_from(payload, ledger, "decision_ledger_digest")
    review_digest = _digest_from(payload, ledger, "review_packet_digest")
    requested_at = str(payload.get("requested_at") or "1970-01-01T00:00:00Z")
    base = {
        "trend_ledger_digest": trend_digest,
        "decision_ledger_digest": decision_digest,
        "review_packet_digest": review_digest,
        "source_trend_ids": source_trend_ids,
        "request_reason": reason,
        "requested_refresh_types": tuple(sorted(refreshes)),
        "scope_keys": scope_keys,
        "safe_next_action": action,
        "requested_at": requested_at,
    }
    digest = _digest(base)
    return HouseholdCameraOperatorGrantRenewalRequestRecord(
        record_id=f"operator-grant-renewal-request-record-{digest[:16]}",
        request_id=f"operator-grant-renewal-request-{digest[:16]}",
        trend_ledger_digest=trend_digest,
        decision_ledger_digest=decision_digest,
        review_packet_digest=review_digest,
        authorization_envelope_digest=_digest_from(payload, ledger, "authorization_envelope_digest"),
        denial_ledger_digest=_digest_from(payload, ledger, "denial_ledger_digest"),
        policy_chain_digest=_digest_from(payload, ledger, "policy_chain_digest"),
        zone_config_digest=_digest_from(payload, ledger, "zone_config_digest"),
        dry_run_proof_digest=_digest_from(payload, ledger, "dry_run_proof_digest"),
        source_trend_ids=source_trend_ids,
        source_record_ids=source_record_ids,
        review_packet_ids=review_packet_ids,
        source_candidate_id=source_candidate_ids[0] if len(source_candidate_ids) == 1 else None,
        requested_mode=requested_modes[0] if len(requested_modes) == 1 else None,
        operator_label=operator_labels[0] if len(operator_labels) == 1 else None,
        request_reason=reason,
        requested_refresh_types=tuple(sorted(refreshes)),
        requested_at=requested_at,
        request_expires_at=str(payload.get("request_expires_at")) if payload.get("request_expires_at") else None,
        stale_trend_count=stale_trend_count,
        stale_review_count=sum(_count(m, "stale_review_count") for m in members),
        unresolved_denial_count_total=sum(_count(m, "unresolved_denial_count_total") for m in members),
        renewal_pressure_count=sum(_count(m, "grant_renewal_count", "renewal_pressure_count") for m in members),
        repair_pressure_count=sum(_count(m, "repair_count", "repair_pressure_count") for m in members),
        dry_run_continuation_count=sum(_count(m, "dry_run_continuation_count") for m in members),
        future_live_deferred_count=sum(_count(m, "future_live_deferred_count") for m in members),
        scope_keys=scope_keys,
        safe_next_action=action,
        forbidden_next_steps=FORBIDDEN_NEXT_STEPS,
        capture_enabled=False,
        capture_available=False,
        live_hardware_enabled=False,
        raw_media_storage_enabled=False,
        no_live_capture_performed=True,
        speaker_output_enabled=False,
        external_disclosure_enabled=False,
        request_grants_operator_consent=False,
        request_renews_operator_grant=False,
        request_enables_live_capture=False,
        request_enables_dry_run_continuation=False,
        request_confers_live_readiness=False,
        digest=digest,
    )


def evaluate_operator_grant_renewal_request_packet(payload: Mapping[str, Any], policy: HouseholdCameraOperatorGrantRenewalRequestPolicy | None = None) -> HouseholdCameraOperatorGrantRenewalRequestResult:
    active_policy = _payload_policy(payload, policy)
    if not validate_policy(active_policy)["ok"]:
        return _blocked("operator_grant_renewal_request_packet_invalid", "invalid_policy", "request packet policy is invalid")
    if _has_media_payload(payload):
        return _blocked("operator_grant_renewal_request_packet_blocked_media_payload", "media_payload", "media and base64 payloads are forbidden")
    if _truthy(payload, ("speaker_output_requested", "speaker_output_enabled", "talkback_requested")):
        return _blocked("operator_grant_renewal_request_packet_blocked_speaker_boundary", "speaker_boundary", "speaker/talkback requests are forbidden")
    if _truthy(payload, ("external_disclosure_requested", "external_disclosure_enabled")):
        return _blocked("operator_grant_renewal_request_packet_blocked_external_authority", "external_authority", "external disclosure requests are forbidden")

    ledger = _trend_ledger(payload)
    if ledger is None:
        return _blocked("operator_grant_renewal_request_packet_blocked_missing_trend_ledger", "missing_trend_ledger", "trend ledger is required")
    if _has_media_payload(ledger):
        return _blocked("operator_grant_renewal_request_packet_blocked_media_payload", "media_payload", "trend ledger contains media/base64 payload")
    if _truthy(ledger, ("speaker_output_requested", "speaker_output_enabled", "talkback_requested")):
        return _blocked("operator_grant_renewal_request_packet_blocked_speaker_boundary", "speaker_boundary", "trend ledger speaker boundary is forbidden")
    if _truthy(ledger, ("external_disclosure_requested", "external_disclosure_enabled")):
        return _blocked("operator_grant_renewal_request_packet_blocked_external_authority", "external_authority", "trend ledger external authority is forbidden")

    if active_policy.require_decision_ledger_digest and not (active_policy.allow_trend_only_diagnostic_packet and not _digest_from(payload, ledger, "decision_ledger_digest")) and not _digest_from(payload, ledger, "decision_ledger_digest"):
        return _blocked("operator_grant_renewal_request_packet_blocked_missing_decision_ledger", "missing_decision_ledger", "decision ledger digest is required")
    if active_policy.require_review_packet_digest and not (active_policy.allow_trend_only_diagnostic_packet and not _digest_from(payload, ledger, "review_packet_digest")) and not _digest_from(payload, ledger, "review_packet_digest"):
        return _blocked("operator_grant_renewal_request_packet_blocked_missing_review_packet", "missing_review_packet", "review packet digest is required")

    raw_records = _records(ledger)
    if not raw_records:
        return _blocked("operator_grant_renewal_request_packet_blocked_missing_trend_ledger", "missing_trend_records", "trend ledger records are required")
    records: list[Mapping[str, Any]] = []
    for raw in raw_records:
        if not isinstance(raw, Mapping) or not raw.get("trend_type") or not raw.get("trend_id"):
            return _blocked("operator_grant_renewal_request_packet_blocked_invalid_trend_record", "invalid_trend_record", "trend record must include trend_type and trend_id")
        if _has_media_payload(raw):
            return _blocked("operator_grant_renewal_request_packet_blocked_media_payload", "media_payload", "trend record contains media/base64 payload")
        if _truthy(raw, ("speaker_output_requested", "speaker_output_enabled", "talkback_requested")):
            return _blocked("operator_grant_renewal_request_packet_blocked_speaker_boundary", "speaker_boundary", "trend record speaker/talkback boundary is forbidden")
        if _truthy(raw, ("external_disclosure_requested", "external_disclosure_enabled")):
            return _blocked("operator_grant_renewal_request_packet_blocked_external_authority", "external_authority", "trend record external authority is forbidden")
        records.append(raw)

    scope_keys = {_scope(record) for record in records}
    findings: list[HouseholdCameraOperatorGrantRenewalRequestFinding] = []
    warned = False
    if len(scope_keys) > 1 and not active_policy.allow_mixed_scope_diagnostic_summary:
        return _blocked("operator_grant_renewal_request_packet_blocked_scope_mismatch", "scope_mismatch", "trend records span multiple scopes")
    if len(scope_keys) > 1:
        warned = True
        findings.append(HouseholdCameraOperatorGrantRenewalRequestFinding("mixed_scope_diagnostic_summary", "mixed scope request packet is diagnostic only and grants no authority"))

    if active_policy.allow_trend_only_diagnostic_packet and (not _digest_from(payload, ledger, "decision_ledger_digest") or not _digest_from(payload, ledger, "review_packet_digest")):
        warned = True
        findings.append(HouseholdCameraOperatorGrantRenewalRequestFinding("trend_only_diagnostic_packet", "trend-only diagnostic packet is metadata-only and grants no authority"))

    stale_trend_count = sum(1 for record in records if bool(record.get("stale_trend")) or str(record.get("trend_staleness") or "") == "stale")
    stale_review_count = sum(_count(record, "stale_review_count") for record in records)
    if stale_trend_count:
        if active_policy.stale_trend_mode == "block":
            return _blocked("operator_grant_renewal_request_packet_blocked_stale_trend", "stale_trend", "stale trend evidence blocked by policy")
        warned = True
        findings.append(HouseholdCameraOperatorGrantRenewalRequestFinding("stale_trend_refresh_required", "stale trend evidence requires trend ledger review"))
    if stale_review_count:
        if active_policy.stale_review_mode == "block":
            return _blocked("operator_grant_renewal_request_packet_blocked_stale_trend", "stale_review", "stale review evidence blocked by policy")
        warned = True
        findings.append(HouseholdCameraOperatorGrantRenewalRequestFinding("stale_review_refresh_required", "stale review evidence requires review packet rerun"))

    grouped: dict[tuple[RequestReason, RequestedRefreshType, SafeNextAction], list[Mapping[str, Any]]] = {}
    for record in records:
        trend_type = str(record.get("trend_type"))
        mapped = TREND_REASON_REFRESH_ACTION.get(trend_type)
        if mapped is None and str(record.get("safe_next_action")) == "renew_operator_grant":
            mapped = TREND_REASON_REFRESH_ACTION["repeated_operator_grant_renewals"]
        if mapped is not None:
            grouped.setdefault(mapped, []).append(record)
    if stale_trend_count:
        grouped.setdefault(TREND_REASON_REFRESH_ACTION["stale_trend_pattern"], [records[0]])
    if stale_review_count:
        grouped.setdefault(TREND_REASON_REFRESH_ACTION["stale_review_pattern"], [records[0]])

    if not grouped and not active_policy.allow_noop_request_packet:
        return _blocked("operator_grant_renewal_request_packet_blocked_no_renewal_pressure", "no_renewal_pressure", "no renewal, repair, stale, denial, continuation, or deferral pressure found")
    if not grouped:
        grouped[("no_renewal_request_required", "trend_ledger_review", "no_action_allowed")] = [records[0]]
        warned = True
        findings.append(HouseholdCameraOperatorGrantRenewalRequestFinding("noop_request_packet", "no-op packet is diagnostic only"))

    request_records = tuple(sorted((_make_record(reason=reason, refreshes=(refresh,), action=action, members=members, payload=payload, ledger=ledger, stale_trend_count=stale_trend_count) for (reason, refresh, action), members in grouped.items()), key=lambda r: r.request_id))
    digest = _digest([asdict(record) for record in request_records])
    packet = HouseholdCameraOperatorGrantRenewalRequestPacket(request_records, digest)
    counts: dict[str, int] = {"record_count": len(request_records), "source_trend_count": len(records), "stale_trend_count": stale_trend_count, "stale_review_count": stale_review_count}
    for request_record in request_records:
        counts[request_record.request_reason] = counts.get(request_record.request_reason, 0) + 1
    status: RequestStatus = "operator_grant_renewal_request_packet_ready_with_warnings" if warned else "operator_grant_renewal_request_packet_ready"
    report = HouseholdCameraOperatorGrantRenewalRequestReport(status, dict(sorted(counts.items())), tuple(findings))
    return HouseholdCameraOperatorGrantRenewalRequestResult(status, packet, report)
