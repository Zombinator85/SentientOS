from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Literal, Mapping, Sequence, cast

TrendStatus = Literal[
    "operator_review_trend_ledger_ready",
    "operator_review_trend_ledger_ready_with_warnings",
    "operator_review_trend_ledger_blocked_missing_decision_records",
    "operator_review_trend_ledger_blocked_invalid_decision_record",
    "operator_review_trend_ledger_blocked_scope_mismatch",
    "operator_review_trend_ledger_blocked_media_payload",
    "operator_review_trend_ledger_blocked_speaker_boundary",
    "operator_review_trend_ledger_blocked_external_authority",
    "operator_review_trend_ledger_invalid",
    "operator_review_trend_ledger_failed",
]

TrendType = Literal[
    "repeated_capture_denials",
    "repeated_review_deferrals",
    "repeated_operator_grant_renewals",
    "repeated_dry_run_repairs",
    "repeated_policy_chain_repairs",
    "repeated_zone_config_repairs",
    "repeated_disabled_capture_boundary_repairs",
    "dry_run_only_continuation_history",
    "future_live_review_deferred_history",
    "sustained_denial_history",
    "rejected_review_packet_history",
    "stale_review_pattern",
    "mixed_operator_review_pattern",
    "no_trend_detected",
]

SafeNextAction = Literal[
    "no_action_allowed",
    "operator_review_required",
    "inspect_decision_history",
    "renew_operator_grant",
    "repair_dry_run_proof",
    "repair_policy_chain_proof",
    "repair_zone_config",
    "repair_disabled_capture_boundary",
    "rerun_capture_review_packet",
    "continue_dry_run_only_review",
    "defer_future_live_review",
    "sustain_capture_denial",
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
    "bypass_policy_chain",
    "bypass_zone_config",
    "bypass_disabled_capture_boundary",
    "bypass_dry_run",
    "infer_operator_consent_from_trends",
    "convert_trend_to_live_readiness",
    "enable_speaker_output",
    "enable_external_disclosure",
)

MEDIA_KEYS = frozenset({
    "raw_media",
    "raw_media_payload",
    "media_payload",
    "base64",
    "base64_media",
    "base64_payload",
    "image",
    "video",
    "audio",
    "thumbnail",
    "screenshot",
    "transcript",
})

DECISION_TO_TREND: dict[str, TrendType] = {
    "deny_capture_request": "repeated_capture_denials",
    "defer_review": "repeated_review_deferrals",
    "require_operator_grant_renewal": "repeated_operator_grant_renewals",
    "require_dry_run_repair": "repeated_dry_run_repairs",
    "require_policy_chain_repair": "repeated_policy_chain_repairs",
    "require_zone_config_repair": "repeated_zone_config_repairs",
    "require_disabled_capture_boundary_repair": "repeated_disabled_capture_boundary_repairs",
    "allow_dry_run_only_continuation": "dry_run_only_continuation_history",
    "mark_future_live_review_deferred": "future_live_review_deferred_history",
    "sustain_denial_history": "sustained_denial_history",
    "reject_review_packet": "rejected_review_packet_history",
}

SAFE_ACTION_BY_TREND: dict[str, SafeNextAction] = {
    "repeated_capture_denials": "sustain_capture_denial",
    "repeated_review_deferrals": "operator_review_required",
    "repeated_operator_grant_renewals": "renew_operator_grant",
    "repeated_dry_run_repairs": "repair_dry_run_proof",
    "repeated_policy_chain_repairs": "repair_policy_chain_proof",
    "repeated_zone_config_repairs": "repair_zone_config",
    "repeated_disabled_capture_boundary_repairs": "repair_disabled_capture_boundary",
    "dry_run_only_continuation_history": "continue_dry_run_only_review",
    "future_live_review_deferred_history": "defer_future_live_review",
    "sustained_denial_history": "sustain_capture_denial",
    "rejected_review_packet_history": "rerun_capture_review_packet",
    "stale_review_pattern": "operator_review_required",
    "mixed_operator_review_pattern": "inspect_decision_history",
    "no_trend_detected": "inspect_decision_history",
}

DENY_DECISIONS = frozenset({"deny_capture_request", "sustain_denial_history"})
DEFER_DECISIONS = frozenset({"defer_review", "mark_future_live_review_deferred"})
REPAIR_DECISIONS = frozenset({
    "require_dry_run_repair",
    "require_policy_chain_repair",
    "require_zone_config_repair",
    "require_disabled_capture_boundary_repair",
    "reject_review_packet",
})
GRANT_RENEWAL_DECISIONS = frozenset({"require_operator_grant_renewal"})
DRY_RUN_CONTINUATION_DECISIONS = frozenset({"allow_dry_run_only_continuation"})
FUTURE_LIVE_DEFERRED_DECISIONS = frozenset({"mark_future_live_review_deferred"})
KNOWN_DECISIONS = frozenset(DECISION_TO_TREND)


@dataclass(frozen=True)
class HouseholdCameraOperatorReviewTrendPolicy:
    schema_version: str = "household_presence_camera_operator_review_trend_ledger_policy.v1"
    repeated_threshold: int = 2
    stale_review_threshold: int = 1
    allow_mixed_scope_summary: bool = False
    stale_review_mode: Literal["block", "warn"] = "warn"
    allow_empty_history: bool = False


@dataclass(frozen=True)
class HouseholdCameraOperatorReviewTrendInput:
    decision_records: tuple[dict[str, Any], ...]
    policy: HouseholdCameraOperatorReviewTrendPolicy = HouseholdCameraOperatorReviewTrendPolicy()


@dataclass(frozen=True)
class HouseholdCameraOperatorReviewTrendFinding:
    code: str
    message: str


@dataclass(frozen=True)
class HouseholdCameraOperatorReviewTrendRecord:
    record_id: str
    trend_id: str
    trend_type: TrendType
    source_record_ids: tuple[str, ...]
    decision_types: tuple[str, ...]
    review_packet_ids: tuple[str, ...]
    source_candidate_id: str | None
    requested_mode: str | None
    operator_label: str | None
    first_seen_at: str
    last_seen_at: str
    total_decision_count: int
    deny_count: int
    defer_count: int
    repair_count: int
    grant_renewal_count: int
    dry_run_continuation_count: int
    future_live_deferred_count: int
    stale_review_count: int
    unresolved_denial_count_total: int
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
    trend_enables_live_capture: bool
    trend_confers_operator_consent: bool
    digest: str


@dataclass(frozen=True)
class HouseholdCameraOperatorReviewTrendLedger:
    records: tuple[HouseholdCameraOperatorReviewTrendRecord, ...]
    digest: str


@dataclass(frozen=True)
class HouseholdCameraOperatorReviewTrendReport:
    status: TrendStatus
    summary_counts: dict[str, int]
    findings: tuple[HouseholdCameraOperatorReviewTrendFinding, ...]


@dataclass(frozen=True)
class HouseholdCameraOperatorReviewTrendResult:
    status: TrendStatus
    ledger: HouseholdCameraOperatorReviewTrendLedger
    report: HouseholdCameraOperatorReviewTrendReport

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def build_default_policy() -> HouseholdCameraOperatorReviewTrendPolicy:
    return HouseholdCameraOperatorReviewTrendPolicy()


def validate_policy(policy: HouseholdCameraOperatorReviewTrendPolicy) -> dict[str, Any]:
    ok = (
        policy.schema_version.endswith(".v1")
        and policy.repeated_threshold >= 1
        and policy.stale_review_threshold >= 0
        and policy.stale_review_mode in {"block", "warn"}
    )
    return {"ok": ok, "status": "household_presence_camera_operator_review_trend_ledger_policy_valid" if ok else "household_presence_camera_operator_review_trend_ledger_policy_invalid"}


def _has_media_payload(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            lower = str(key).lower()
            if lower in MEDIA_KEYS and item not in (None, "", False, [], {}):
                return True
            if lower.endswith("payload") and "media" in lower and item not in (None, "", False, [], {}):
                return True
            if _has_media_payload(item):
                return True
    elif isinstance(value, list):
        return any(_has_media_payload(item) for item in value)
    return False


def _has_base64_payload(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            lower = str(key).lower()
            if "base64" in lower and item not in (None, "", False, [], {}):
                return True
            if _has_base64_payload(item):
                return True
    elif isinstance(value, list):
        return any(_has_base64_payload(item) for item in value)
    return False


def _truthy_boundary(value: Mapping[str, Any], key: str) -> bool:
    if bool(value.get(key)):
        return True
    nested = value.get("review_packet")
    if isinstance(nested, Mapping) and bool(nested.get(key)):
        return True
    proof = nested.get("proof_set") if isinstance(nested, Mapping) else None
    return isinstance(proof, Mapping) and bool(proof.get(key))


def _records_from_payload(payload: Mapping[str, Any]) -> Sequence[Any]:
    for key in ("decision_records", "records", "decisions"):
        value = payload.get(key)
        if isinstance(value, list):
            return cast(Sequence[Any], value)
    ledger = payload.get("ledger")
    if isinstance(ledger, Mapping) and isinstance(ledger.get("records"), list):
        return cast(Sequence[Any], ledger["records"])
    return ()


def _scope_key(record: Mapping[str, Any]) -> str:
    candidate = str(record.get("source_candidate_id") or "")
    mode = str(record.get("requested_mode") or "")
    operator = str(record.get("operator_label") or "")
    return f"candidate={candidate}|mode={mode}|operator={operator}"


def _record_time(record: Mapping[str, Any]) -> str:
    return str(record.get("reviewed_at") or record.get("last_seen_at") or record.get("first_seen_at") or "1970-01-01T00:00:00Z")


def _stale_count(record: Mapping[str, Any]) -> int:
    explicit = record.get("stale_review_count")
    if explicit is not None:
        return int(explicit)
    stale_proof_count = int(record.get("stale_proof_count") or 0)
    reviewed_at = str(record.get("reviewed_at") or "")
    expires_at = str(record.get("review_expires_at") or "")
    return 1 if stale_proof_count > 0 or (reviewed_at and expires_at and reviewed_at > expires_at) else 0


def _blocked(status: TrendStatus, code: str, message: str) -> HouseholdCameraOperatorReviewTrendResult:
    finding = HouseholdCameraOperatorReviewTrendFinding(code, message)
    ledger = HouseholdCameraOperatorReviewTrendLedger((), _digest({"status": status, "finding": asdict(finding)}))
    report = HouseholdCameraOperatorReviewTrendReport(status, {}, (finding,))
    return HouseholdCameraOperatorReviewTrendResult(status, ledger, report)


def _validate_record(record: Mapping[str, Any]) -> str | None:
    if not str(record.get("record_id") or record.get("decision_id") or ""):
        return "missing_record_id"
    decision_type = str(record.get("decision_type") or "")
    if decision_type not in KNOWN_DECISIONS:
        return "unknown_decision_type"
    if not str(record.get("review_packet_id") or ""):
        return "missing_review_packet_id"
    if record.get("capture_enabled") is True or record.get("live_hardware_enabled") is True or record.get("raw_media_storage_enabled") is True:
        return "capture_boundary_enabled"
    if record.get("speaker_output_enabled") is True or record.get("external_disclosure_enabled") is True:
        return "output_boundary_enabled"
    return None


def _counts(records: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    out = {
        "total_decision_count": len(records),
        "deny_count": 0,
        "defer_count": 0,
        "repair_count": 0,
        "grant_renewal_count": 0,
        "dry_run_continuation_count": 0,
        "future_live_deferred_count": 0,
        "stale_review_count": 0,
        "unresolved_denial_count_total": 0,
    }
    for record in records:
        decision = str(record.get("decision_type"))
        if decision in DENY_DECISIONS:
            out["deny_count"] += 1
        if decision in DEFER_DECISIONS:
            out["defer_count"] += 1
        if decision in REPAIR_DECISIONS:
            out["repair_count"] += 1
        if decision in GRANT_RENEWAL_DECISIONS:
            out["grant_renewal_count"] += 1
        if decision in DRY_RUN_CONTINUATION_DECISIONS:
            out["dry_run_continuation_count"] += 1
        if decision in FUTURE_LIVE_DEFERRED_DECISIONS:
            out["future_live_deferred_count"] += 1
        out["stale_review_count"] += _stale_count(record)
        out["unresolved_denial_count_total"] += int(record.get("unresolved_denial_count") or 0)
    return out


def _make_trend_record(trend_type: TrendType, records: Sequence[Mapping[str, Any]]) -> HouseholdCameraOperatorReviewTrendRecord:
    sorted_records = sorted(records, key=lambda item: (str(item.get("reviewed_at") or ""), str(item.get("record_id") or item.get("decision_id") or "")))
    counts = _counts(sorted_records)
    source_record_ids = tuple(str(r.get("record_id") or r.get("decision_id")) for r in sorted_records)
    decision_types = tuple(sorted({str(r.get("decision_type")) for r in sorted_records}))
    review_packet_ids = tuple(sorted({str(r.get("review_packet_id")) for r in sorted_records}))
    scope_keys = tuple(sorted({_scope_key(r) for r in sorted_records}))
    seed = {
        "trend_type": trend_type,
        "source_record_ids": source_record_ids,
        "decision_types": decision_types,
        "review_packet_ids": review_packet_ids,
        "scope_keys": scope_keys,
        "counts": counts,
    }
    digest = _digest(seed)
    first = sorted_records[0]
    return HouseholdCameraOperatorReviewTrendRecord(
        record_id=f"operator-review-trend-record-{digest[:12]}",
        trend_id=f"operator-review-trend-{trend_type}-{digest[:12]}",
        trend_type=trend_type,
        source_record_ids=source_record_ids,
        decision_types=decision_types,
        review_packet_ids=review_packet_ids,
        source_candidate_id=str(first.get("source_candidate_id")) if len({str(r.get("source_candidate_id") or "") for r in sorted_records}) == 1 and str(first.get("source_candidate_id") or "") else None,
        requested_mode=str(first.get("requested_mode")) if len({str(r.get("requested_mode") or "") for r in sorted_records}) == 1 and str(first.get("requested_mode") or "") else None,
        operator_label=str(first.get("operator_label")) if len({str(r.get("operator_label") or "") for r in sorted_records}) == 1 and str(first.get("operator_label") or "") else None,
        first_seen_at=min(_record_time(r) for r in sorted_records),
        last_seen_at=max(_record_time(r) for r in sorted_records),
        total_decision_count=counts["total_decision_count"],
        deny_count=counts["deny_count"],
        defer_count=counts["defer_count"],
        repair_count=counts["repair_count"],
        grant_renewal_count=counts["grant_renewal_count"],
        dry_run_continuation_count=counts["dry_run_continuation_count"],
        future_live_deferred_count=counts["future_live_deferred_count"],
        stale_review_count=counts["stale_review_count"],
        unresolved_denial_count_total=counts["unresolved_denial_count_total"],
        scope_keys=scope_keys,
        safe_next_action=SAFE_ACTION_BY_TREND[trend_type],
        forbidden_next_steps=FORBIDDEN_NEXT_STEPS,
        capture_enabled=False,
        capture_available=False,
        live_hardware_enabled=False,
        raw_media_storage_enabled=False,
        no_live_capture_performed=True,
        speaker_output_enabled=False,
        external_disclosure_enabled=False,
        trend_enables_live_capture=False,
        trend_confers_operator_consent=False,
        digest=digest,
    )


def evaluate_operator_review_trend_ledger(payload: Mapping[str, Any], policy: HouseholdCameraOperatorReviewTrendPolicy | None = None) -> HouseholdCameraOperatorReviewTrendResult:
    if policy is None and isinstance(payload.get("policy"), Mapping):
        allowed = set(HouseholdCameraOperatorReviewTrendPolicy.__dataclass_fields__)
        active_policy = HouseholdCameraOperatorReviewTrendPolicy(**{str(k): v for k, v in cast(Mapping[str, Any], payload["policy"]).items() if str(k) in allowed})
    else:
        active_policy = policy or build_default_policy()
    if not validate_policy(active_policy)["ok"]:
        return _blocked("operator_review_trend_ledger_invalid", "invalid_policy", "trend policy is invalid")

    raw_records = _records_from_payload(payload)
    if not raw_records and not active_policy.allow_empty_history:
        return _blocked("operator_review_trend_ledger_blocked_missing_decision_records", "missing_decision_records", "decision ledger records are required")
    if not raw_records and active_policy.allow_empty_history:
        empty_record = _make_trend_record("no_trend_detected", ({"record_id": "empty-history", "decision_type": "defer_review", "review_packet_id": "none", "reviewed_at": "1970-01-01T00:00:00Z"},))
        ledger = HouseholdCameraOperatorReviewTrendLedger((empty_record,), _digest([asdict(empty_record)]))
        report = HouseholdCameraOperatorReviewTrendReport("operator_review_trend_ledger_ready", {"no_trend_detected": 1, "total_decision_count": 0}, ())
        return HouseholdCameraOperatorReviewTrendResult("operator_review_trend_ledger_ready", ledger, report)

    records: list[Mapping[str, Any]] = []
    for raw in raw_records:
        if not isinstance(raw, Mapping):
            return _blocked("operator_review_trend_ledger_blocked_invalid_decision_record", "invalid_decision_record", "decision record must be an object")
        if _has_media_payload(raw) or _has_base64_payload(raw):
            return _blocked("operator_review_trend_ledger_blocked_media_payload", "media_payload", "media and base64 payloads are forbidden")
        if _truthy_boundary(raw, "speaker_output_requested") or _truthy_boundary(raw, "speaker_output_enabled") or _truthy_boundary(raw, "talkback_requested"):
            return _blocked("operator_review_trend_ledger_blocked_speaker_boundary", "speaker_boundary", "speaker/talkback boundary is forbidden")
        if _truthy_boundary(raw, "external_disclosure_requested") or _truthy_boundary(raw, "external_disclosure_enabled"):
            return _blocked("operator_review_trend_ledger_blocked_external_authority", "external_authority", "external disclosure boundary is forbidden")
        invalid = _validate_record(raw)
        if invalid is not None:
            return _blocked("operator_review_trend_ledger_blocked_invalid_decision_record", invalid, invalid)
        records.append(raw)

    scope_keys = {_scope_key(record) for record in records}
    findings: list[HouseholdCameraOperatorReviewTrendFinding] = []
    warned = False
    if len(scope_keys) > 1 and not active_policy.allow_mixed_scope_summary:
        return _blocked("operator_review_trend_ledger_blocked_scope_mismatch", "scope_mismatch", "decision records span multiple scopes")
    if len(scope_keys) > 1:
        warned = True
        findings.append(HouseholdCameraOperatorReviewTrendFinding("mixed_scope_summary", "mixed scope summary is metadata-only and confers no authority"))

    stale_records = [record for record in records if _stale_count(record) >= active_policy.stale_review_threshold and _stale_count(record) > 0]
    if stale_records:
        if active_policy.stale_review_mode == "block":
            return _blocked("operator_review_trend_ledger_invalid", "stale_review_pattern", "stale review pattern blocked by policy")
        warned = True
        findings.append(HouseholdCameraOperatorReviewTrendFinding("stale_review_pattern", "stale review pattern warning; operator-only review remains required"))

    trend_records: list[HouseholdCameraOperatorReviewTrendRecord] = []
    grouped: dict[TrendType, list[Mapping[str, Any]]] = {}
    for source_record in records:
        trend = DECISION_TO_TREND[str(source_record.get("decision_type"))]
        grouped.setdefault(trend, []).append(source_record)
    for trend, members in sorted(grouped.items()):
        if trend.startswith("repeated_") and len(members) < active_policy.repeated_threshold:
            continue
        trend_records.append(_make_trend_record(trend, members))
    if stale_records:
        trend_records.append(_make_trend_record("stale_review_pattern", stale_records))
    if len(grouped) > 1:
        trend_records.append(_make_trend_record("mixed_operator_review_pattern", records))
    if not trend_records:
        trend_records.append(_make_trend_record("no_trend_detected", records))

    trend_records = sorted(trend_records, key=lambda item: item.trend_id)
    ledger = HouseholdCameraOperatorReviewTrendLedger(tuple(trend_records), _digest([asdict(record) for record in trend_records]))
    summary_counts: dict[str, int] = {"total_decision_count": len(records)}
    for record in trend_records:
        summary_counts[record.trend_type] = summary_counts.get(record.trend_type, 0) + 1
    status: TrendStatus = "operator_review_trend_ledger_ready_with_warnings" if warned else "operator_review_trend_ledger_ready"
    report = HouseholdCameraOperatorReviewTrendReport(status, dict(sorted(summary_counts.items())), tuple(findings))
    return HouseholdCameraOperatorReviewTrendResult(status, ledger, report)
