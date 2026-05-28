from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Literal, Mapping, Sequence, cast

DecisionStatus = Literal[
    "capture_review_decision_ledger_ready",
    "capture_review_decision_ledger_ready_with_warnings",
    "capture_review_decision_ledger_blocked_missing_review_packet",
    "capture_review_decision_ledger_blocked_review_packet_not_ready",
    "capture_review_decision_ledger_blocked_unresolved_denials",
    "capture_review_decision_ledger_blocked_scope_mismatch",
    "capture_review_decision_ledger_blocked_stale_review",
    "capture_review_decision_ledger_blocked_media_payload",
    "capture_review_decision_ledger_blocked_speaker_boundary",
    "capture_review_decision_ledger_blocked_external_authority",
    "capture_review_decision_ledger_invalid",
    "capture_review_decision_ledger_failed",
]

DecisionType = Literal[
    "deny_capture_request",
    "defer_review",
    "require_operator_grant_renewal",
    "require_dry_run_repair",
    "require_policy_chain_repair",
    "require_zone_config_repair",
    "require_disabled_capture_boundary_repair",
    "allow_dry_run_only_continuation",
    "mark_future_live_review_deferred",
    "sustain_denial_history",
    "reject_review_packet",
]

SafeNextAction = Literal[
    "no_action_allowed",
    "operator_review_required",
    "renew_operator_grant",
    "repair_dry_run_proof",
    "repair_policy_chain_proof",
    "repair_zone_config",
    "repair_disabled_capture_boundary",
    "rerun_capture_review_packet",
    "continue_dry_run_only",
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
    "bypass_policy_chain",
    "bypass_zone_config",
    "bypass_disabled_capture_boundary",
    "bypass_dry_run",
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

REPAIR_DECISIONS = frozenset({
    "deny_capture_request",
    "defer_review",
    "require_operator_grant_renewal",
    "require_dry_run_repair",
    "require_policy_chain_repair",
    "require_zone_config_repair",
    "require_disabled_capture_boundary_repair",
    "sustain_denial_history",
    "reject_review_packet",
})

CONTINUATION_READY_STATUSES = frozenset({
    "capture_review_packet_ready_for_dry_run_only",
    "capture_review_packet_ready_for_operator_review",
    "capture_review_packet_valid_with_warnings",
})

BLOCKING_REVIEW_PACKET_STATUSES = (
    "blocked",
    "invalid",
    "failed",
)

SAFE_ACTION_BY_DECISION: dict[str, SafeNextAction] = {
    "deny_capture_request": "no_action_allowed",
    "defer_review": "operator_review_required",
    "require_operator_grant_renewal": "renew_operator_grant",
    "require_dry_run_repair": "repair_dry_run_proof",
    "require_policy_chain_repair": "repair_policy_chain_proof",
    "require_zone_config_repair": "repair_zone_config",
    "require_disabled_capture_boundary_repair": "repair_disabled_capture_boundary",
    "allow_dry_run_only_continuation": "continue_dry_run_only",
    "mark_future_live_review_deferred": "defer_future_live_review",
    "sustain_denial_history": "no_action_allowed",
    "reject_review_packet": "rerun_capture_review_packet",
}


@dataclass(frozen=True)
class HouseholdCameraCaptureReviewDecisionPolicy:
    schema_version: str = "household_presence_camera_capture_review_decision_ledger_policy.v1"
    max_unresolved_denials_for_dry_run_continuation: int = 0
    stale_review_mode: Literal["block", "warn"] = "block"
    allow_operator_review_status_for_dry_run_continuation: bool = True


@dataclass(frozen=True)
class HouseholdCameraCaptureReviewDecisionInput:
    decision_id: str
    review_packet: dict[str, Any] | None
    decision_type: DecisionType
    decision_reason: str
    reviewed_at: str
    requested_mode: str = "dry_run_only"
    review_expires_at: str | None = None
    review_packet_id: str | None = None
    review_packet_digest: str | None = None
    authorization_envelope_digest: str | None = None
    denial_ledger_digest: str | None = None
    policy_chain_digest: str | None = None
    zone_config_digest: str | None = None
    dry_run_proof_digest: str | None = None
    operator_label: str | None = None
    source_candidate_id: str | None = None
    unresolved_denial_count: int = 0
    stale_proof_count: int = 0
    media_payload_present: bool = False
    base64_media_present: bool = False
    speaker_output_requested: bool = False
    external_disclosure_requested: bool = False


@dataclass(frozen=True)
class HouseholdCameraCaptureReviewDecisionFinding:
    code: str
    message: str


@dataclass(frozen=True)
class HouseholdCameraCaptureReviewDecisionRecord:
    record_id: str
    decision_id: str
    review_packet_id: str
    review_packet_digest: str
    authorization_envelope_digest: str | None
    denial_ledger_digest: str | None
    policy_chain_digest: str | None
    zone_config_digest: str | None
    dry_run_proof_digest: str | None
    operator_label: str | None
    decision_type: DecisionType
    decision_reason: str
    reviewed_at: str
    review_expires_at: str | None
    requested_mode: str
    source_candidate_id: str | None
    unresolved_denial_count: int
    stale_proof_count: int
    safe_next_action: SafeNextAction
    forbidden_next_steps: tuple[str, ...]
    capture_enabled: bool
    capture_available: bool
    live_hardware_enabled: bool
    raw_media_storage_enabled: bool
    no_live_capture_performed: bool
    speaker_output_enabled: bool
    external_disclosure_enabled: bool
    digest: str


@dataclass(frozen=True)
class HouseholdCameraCaptureReviewDecisionLedger:
    records: tuple[HouseholdCameraCaptureReviewDecisionRecord, ...]
    digest: str


@dataclass(frozen=True)
class HouseholdCameraCaptureReviewDecisionReport:
    status: DecisionStatus
    summary_counts: dict[str, int]
    findings: tuple[HouseholdCameraCaptureReviewDecisionFinding, ...]


@dataclass(frozen=True)
class HouseholdCameraCaptureReviewDecisionResult:
    status: DecisionStatus
    ledger: HouseholdCameraCaptureReviewDecisionLedger
    report: HouseholdCameraCaptureReviewDecisionReport

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def build_default_policy() -> HouseholdCameraCaptureReviewDecisionPolicy:
    return HouseholdCameraCaptureReviewDecisionPolicy()


def validate_policy(policy: HouseholdCameraCaptureReviewDecisionPolicy) -> dict[str, Any]:
    ok = policy.schema_version.endswith(".v1") and policy.max_unresolved_denials_for_dry_run_continuation >= 0 and policy.stale_review_mode in {"block", "warn"}
    return {"ok": ok, "status": "household_presence_camera_capture_review_decision_ledger_policy_valid" if ok else "household_presence_camera_capture_review_decision_ledger_policy_invalid"}


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


def _packet(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    packet = payload.get("review_packet") or payload.get("packet")
    return packet if isinstance(packet, Mapping) else None


def _packet_status(packet: Mapping[str, Any]) -> str:
    return str(packet.get("status") or packet.get("packet_status") or "")


def _nested_str(packet: Mapping[str, Any], *keys: str) -> str:
    current: Any = packet
    for key in keys:
        if not isinstance(current, Mapping):
            return ""
        current = current.get(key)
    return str(current) if current is not None else ""


def _value(payload: Mapping[str, Any], packet: Mapping[str, Any] | None, key: str) -> Any:
    if key in payload:
        return payload[key]
    if packet and key in packet:
        return packet[key]
    if packet:
        nested = _nested_str(packet, "proof_set", key)
        if nested:
            return nested
    return None


def _bool_boundary(payload: Mapping[str, Any], packet: Mapping[str, Any] | None, key: str) -> bool:
    return bool(payload.get(key) or (packet is not None and packet.get(key)) or (packet is not None and isinstance(packet.get("proof_set"), Mapping) and packet["proof_set"].get(key)))


def _blocked(status: DecisionStatus, code: str, message: str) -> HouseholdCameraCaptureReviewDecisionResult:
    finding = HouseholdCameraCaptureReviewDecisionFinding(code, message)
    ledger = HouseholdCameraCaptureReviewDecisionLedger((), _digest({"status": status, "finding": asdict(finding)}))
    report = HouseholdCameraCaptureReviewDecisionReport(status, {}, (finding,))
    return HouseholdCameraCaptureReviewDecisionResult(status, ledger, report)


def _is_stale(payload: Mapping[str, Any], packet: Mapping[str, Any]) -> bool:
    reviewed_at = str(payload.get("reviewed_at") or packet.get("reviewed_at") or _nested_str(packet, "proof_set", "reviewed_at"))
    expires_at = str(payload.get("review_expires_at") or packet.get("review_expires_at") or packet.get("expires_at") or _nested_str(packet, "proof_set", "expires_at"))
    return bool(reviewed_at and expires_at and reviewed_at > expires_at)


def _scope_mismatch(payload: Mapping[str, Any], packet: Mapping[str, Any]) -> bool:
    requested = str(payload.get("requested_mode") or "")
    packet_mode = str(packet.get("requested_mode") or _nested_str(packet, "proof_set", "requested_mode"))
    if requested and packet_mode and requested != packet_mode:
        return True
    candidate = str(payload.get("source_candidate_id") or "")
    packet_candidate = str(packet.get("source_candidate_id") or _nested_str(packet, "proof_set", "source_candidate_id"))
    return bool(candidate and packet_candidate and candidate != packet_candidate)


def _record_from_payload(payload: Mapping[str, Any], packet: Mapping[str, Any]) -> HouseholdCameraCaptureReviewDecisionRecord:
    decision_type = cast(DecisionType, str(payload.get("decision_type", "defer_review")))
    safe_next_action = SAFE_ACTION_BY_DECISION.get(decision_type, "operator_review_required")
    review_packet_id = str(payload.get("review_packet_id") or packet.get("review_packet_id") or packet.get("packet_id") or "review-packet-0001")
    review_packet_digest = str(payload.get("review_packet_digest") or packet.get("digest") or _digest(packet))
    record_seed = {
        "decision_id": str(payload.get("decision_id", "decision-0001")),
        "review_packet_id": review_packet_id,
        "review_packet_digest": review_packet_digest,
        "decision_type": decision_type,
        "reviewed_at": str(payload.get("reviewed_at", "1970-01-01T00:00:00Z")),
    }
    digest_payload = dict(record_seed)
    digest_payload["safe_next_action"] = safe_next_action
    digest = _digest(digest_payload)
    return HouseholdCameraCaptureReviewDecisionRecord(
        record_id=str(payload.get("record_id") or f"capture-review-decision-{digest[:12]}"),
        decision_id=record_seed["decision_id"],
        review_packet_id=review_packet_id,
        review_packet_digest=review_packet_digest,
        authorization_envelope_digest=cast(str | None, _value(payload, packet, "authorization_envelope_digest")),
        denial_ledger_digest=cast(str | None, _value(payload, packet, "denial_ledger_digest")),
        policy_chain_digest=cast(str | None, _value(payload, packet, "policy_chain_digest")),
        zone_config_digest=cast(str | None, _value(payload, packet, "zone_config_digest")),
        dry_run_proof_digest=cast(str | None, _value(payload, packet, "dry_run_proof_digest")),
        operator_label=cast(str | None, payload.get("operator_label")),
        decision_type=decision_type,
        decision_reason=str(payload.get("decision_reason", decision_type)),
        reviewed_at=record_seed["reviewed_at"],
        review_expires_at=cast(str | None, payload.get("review_expires_at") or packet.get("review_expires_at") or packet.get("expires_at")),
        requested_mode=str(payload.get("requested_mode") or packet.get("requested_mode") or _nested_str(packet, "proof_set", "requested_mode") or "dry_run_only"),
        source_candidate_id=cast(str | None, payload.get("source_candidate_id") or packet.get("source_candidate_id") or _nested_str(packet, "proof_set", "source_candidate_id") or None),
        unresolved_denial_count=int(payload.get("unresolved_denial_count") or packet.get("unresolved_denial_count") or _nested_str(packet, "proof_set", "unresolved_denial_count") or 0),
        stale_proof_count=int(payload.get("stale_proof_count") or 0),
        safe_next_action=safe_next_action,
        forbidden_next_steps=FORBIDDEN_NEXT_STEPS,
        capture_enabled=False,
        capture_available=False,
        live_hardware_enabled=False,
        raw_media_storage_enabled=False,
        no_live_capture_performed=True,
        speaker_output_enabled=False,
        external_disclosure_enabled=False,
        digest=digest,
    )


def evaluate_capture_review_decision_ledger(payload: Mapping[str, Any], policy: HouseholdCameraCaptureReviewDecisionPolicy | None = None) -> HouseholdCameraCaptureReviewDecisionResult:
    if policy is None and isinstance(payload.get("policy"), Mapping):
        allowed = set(HouseholdCameraCaptureReviewDecisionPolicy.__dataclass_fields__)
        active_policy = HouseholdCameraCaptureReviewDecisionPolicy(**{str(k): v for k, v in cast(Mapping[str, Any], payload["policy"]).items() if str(k) in allowed})
    else:
        active_policy = policy or build_default_policy()
    entries: Sequence[Any]
    if isinstance(payload.get("decisions"), list):
        entries = cast(Sequence[Any], payload["decisions"])
    elif isinstance(payload.get("records"), list):
        entries = cast(Sequence[Any], payload["records"])
    else:
        entries = (payload,)

    records: list[HouseholdCameraCaptureReviewDecisionRecord] = []
    findings: list[HouseholdCameraCaptureReviewDecisionFinding] = []
    warned = False
    for entry in entries:
        if not isinstance(entry, Mapping):
            return _blocked("capture_review_decision_ledger_invalid", "invalid_decision", "decision entry must be an object")
        packet = _packet(entry)
        if packet is None:
            return _blocked("capture_review_decision_ledger_blocked_missing_review_packet", "missing_review_packet", "review_packet is required")
        if _has_media_payload(entry) or _bool_boundary(entry, packet, "media_payload_present"):
            return _blocked("capture_review_decision_ledger_blocked_media_payload", "media_payload", "media payloads are forbidden")
        if _has_base64_payload(entry) or _bool_boundary(entry, packet, "base64_media_present"):
            return _blocked("capture_review_decision_ledger_blocked_media_payload", "base64_media_payload", "base64 media payloads are forbidden")
        if _bool_boundary(entry, packet, "speaker_output_requested"):
            return _blocked("capture_review_decision_ledger_blocked_speaker_boundary", "speaker_boundary", "speaker/talkback boundary is forbidden")
        if _bool_boundary(entry, packet, "external_disclosure_requested"):
            return _blocked("capture_review_decision_ledger_blocked_external_authority", "external_authority", "external disclosure boundary is forbidden")
        if _scope_mismatch(entry, packet):
            return _blocked("capture_review_decision_ledger_blocked_scope_mismatch", "scope_mismatch", "review packet scope does not match decision input")
        decision_type = str(entry.get("decision_type", ""))
        packet_status = _packet_status(packet)
        if decision_type not in SAFE_ACTION_BY_DECISION:
            return _blocked("capture_review_decision_ledger_invalid", "unknown_decision_type", decision_type)
        if any(token in packet_status for token in BLOCKING_REVIEW_PACKET_STATUSES) and decision_type not in REPAIR_DECISIONS:
            return _blocked("capture_review_decision_ledger_blocked_review_packet_not_ready", "review_packet_not_ready", packet_status)
        unresolved = int(entry.get("unresolved_denial_count") or packet.get("unresolved_denial_count") or _nested_str(packet, "proof_set", "unresolved_denial_count") or 0)
        if decision_type == "allow_dry_run_only_continuation" and unresolved > active_policy.max_unresolved_denials_for_dry_run_continuation:
            return _blocked("capture_review_decision_ledger_blocked_unresolved_denials", "unresolved_denials", str(unresolved))
        if decision_type == "allow_dry_run_only_continuation":
            if packet_status == "capture_review_packet_ready_for_operator_review" and not active_policy.allow_operator_review_status_for_dry_run_continuation:
                return _blocked("capture_review_decision_ledger_blocked_review_packet_not_ready", "operator_review_not_dry_run", packet_status)
            if packet_status not in CONTINUATION_READY_STATUSES:
                return _blocked("capture_review_decision_ledger_blocked_review_packet_not_ready", "review_packet_not_ready", packet_status)
            if str(entry.get("requested_mode") or packet.get("requested_mode") or _nested_str(packet, "proof_set", "requested_mode")) not in {"dry_run_only", "design_only"}:
                return _blocked("capture_review_decision_ledger_blocked_scope_mismatch", "future_live_not_continuable", "dry-run continuation cannot request future live mode")
        if _is_stale(entry, packet):
            if active_policy.stale_review_mode == "block":
                return _blocked("capture_review_decision_ledger_blocked_stale_review", "stale_review", "review packet is stale")
            warned = True
            findings.append(HouseholdCameraCaptureReviewDecisionFinding("stale_review", "review packet is stale; warning only by policy"))
        records.append(_record_from_payload(entry, packet))

    counts: dict[str, int] = {}
    for record in records:
        counts[record.decision_type] = counts.get(record.decision_type, 0) + 1
    status: DecisionStatus = "capture_review_decision_ledger_ready_with_warnings" if warned else "capture_review_decision_ledger_ready"
    digest = _digest([asdict(record) for record in records])
    ledger = HouseholdCameraCaptureReviewDecisionLedger(tuple(records), digest)
    report = HouseholdCameraCaptureReviewDecisionReport(status, dict(sorted(counts.items())), tuple(findings))
    return HouseholdCameraCaptureReviewDecisionResult(status, ledger, report)
