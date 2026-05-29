from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Literal, Mapping, Sequence, cast

RegistryStatus = Literal[
    "future_live_deferral_registry_ready",
    "future_live_deferral_registry_ready_with_warnings",
    "future_live_deferral_registry_blocked_missing_dry_run_gate",
    "future_live_deferral_registry_blocked_missing_renewal_request_packet",
    "future_live_deferral_registry_blocked_missing_trend_ledger",
    "future_live_deferral_registry_blocked_missing_decision_ledger",
    "future_live_deferral_registry_blocked_missing_review_packet",
    "future_live_deferral_registry_blocked_dry_run_gate_not_ready",
    "future_live_deferral_registry_blocked_unsafe_live_implication",
    "future_live_deferral_registry_blocked_operator_grant_required",
    "future_live_deferral_registry_blocked_proof_refresh_required",
    "future_live_deferral_registry_blocked_unresolved_denials",
    "future_live_deferral_registry_blocked_scope_mismatch",
    "future_live_deferral_registry_blocked_stale_gate",
    "future_live_deferral_registry_blocked_stale_request",
    "future_live_deferral_registry_blocked_stale_trend",
    "future_live_deferral_registry_blocked_stale_review",
    "future_live_deferral_registry_blocked_media_payload",
    "future_live_deferral_registry_blocked_speaker_boundary",
    "future_live_deferral_registry_blocked_external_authority",
    "future_live_deferral_registry_invalid",
    "future_live_deferral_registry_failed",
]

DeferralType = Literal[
    "future_live_review_deferred",
    "live_candidate_review_not_requested",
    "live_candidate_review_requires_separate_operator_confirmation",
    "dry_run_continuation_not_live_readiness",
    "grant_renewal_request_not_live_consent",
    "trend_history_not_live_consent",
    "decision_history_not_live_consent",
    "unresolved_denial_blocks_future_live",
    "proof_refresh_required_before_future_live_review",
    "operator_grant_required_before_future_live_review",
    "stale_evidence_requires_review_before_future_live",
    "mixed_scope_requires_operator_review",
    "no_future_live_path_available",
]

SafeNextAction = Literal[
    "no_action_allowed",
    "maintain_future_live_deferral",
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
    "inspect_dry_run_gate",
    "sustain_capture_denial",
]

FORBIDDEN_NEXT_STEPS = (
    "open_camera_now",
    "attempt_capture",
    "enable_live_capture",
    "enable_live_recording",
    "store_raw_media",
    "attach_media_payload",
    "schedule_live_capture_review",
    "approve_live_candidate",
    "mark_live_ready",
    "bypass_authorization_envelope",
    "bypass_denial_ledger",
    "bypass_review_packet",
    "bypass_review_decision_ledger",
    "bypass_operator_review_trend_ledger",
    "bypass_operator_grant_renewal_request_packet",
    "bypass_dry_run_continuation_gate",
    "bypass_policy_chain",
    "bypass_zone_config",
    "bypass_disabled_capture_boundary",
    "bypass_dry_run",
    "infer_operator_consent_from_deferral",
    "infer_operator_consent_from_gate",
    "infer_operator_consent_from_trends",
    "infer_operator_consent_from_renewal_request",
    "convert_renewal_request_to_grant",
    "convert_dry_run_gate_to_live_readiness",
    "convert_deferral_to_live_readiness",
    "convert_deferral_to_live_capture_permission",
    "enable_speaker_output",
    "enable_external_disclosure",
)

MEDIA_KEYS = frozenset({"raw_media", "raw_media_payload", "media_payload", "image", "video", "audio", "thumbnail", "screenshot", "transcript", "base64", "base64_media", "base64_payload"})
UNSAFE_LIVE_KEYS = frozenset({
    "live_ready", "live_readiness", "live_capture_permission", "capture_authorized", "capture_authorization_granted",
    "operator_consent_granted", "operator_grant_renewed", "schedule_live_capture_review", "live_review_scheduled",
    "approved_live_candidate", "live_candidate_approved", "capture_enabled", "capture_available", "live_hardware_enabled",
    "raw_media_storage_enabled", "speaker_output_enabled", "external_disclosure_enabled", "gate_grants_operator_consent",
    "gate_renews_operator_grant", "gate_enables_live_capture", "gate_enables_live_hardware", "gate_enables_raw_media_storage",
    "gate_enables_speaker_output", "gate_enables_external_disclosure", "gate_confers_live_readiness", "gate_confers_capture_authorization",
    "deferral_grants_operator_consent", "deferral_renews_operator_grant", "deferral_enables_live_capture", "deferral_confers_live_readiness",
})

@dataclass(frozen=True)
class HouseholdCameraFutureLiveDeferralRegistryPolicy:
    schema_version: str = "household_presence_camera_future_live_deferral_registry_policy.v1"
    require_dry_run_gate_digest: bool = True
    require_renewal_request_packet_digest: bool = True
    require_trend_ledger_digest: bool = True
    require_decision_ledger_digest: bool = True
    require_review_packet_digest: bool = True
    allow_gate_only_diagnostic_deferral: bool = False
    allow_diagnostic_deferral_when_refresh_required: bool = True
    allow_diagnostic_deferral_when_operator_grant_required: bool = True
    allow_mixed_scope_diagnostic_summary: bool = False
    max_unresolved_denials: int = 0
    stale_gate_mode: Literal["block", "warn"] = "warn"
    stale_request_mode: Literal["block", "warn"] = "warn"
    stale_trend_mode: Literal["block", "warn"] = "warn"
    stale_review_mode: Literal["block", "warn"] = "warn"
    allow_ready_with_warnings_deferral: bool = True

@dataclass(frozen=True)
class HouseholdCameraFutureLiveDeferralRegistryInput:
    dry_run_gate: dict[str, Any]
    renewal_request_packet: dict[str, Any] | None = None
    trend_ledger: dict[str, Any] | None = None
    decision_ledger: dict[str, Any] | None = None
    review_packet: dict[str, Any] | None = None
    policy: HouseholdCameraFutureLiveDeferralRegistryPolicy | None = None

@dataclass(frozen=True)
class HouseholdCameraFutureLiveDeferralFinding:
    code: str
    message: str

@dataclass(frozen=True)
class HouseholdCameraFutureLiveDeferralRecord:
    record_id: str
    deferral_id: str
    dry_run_gate_digest: str
    renewal_request_packet_digest: str | None
    trend_ledger_digest: str | None
    decision_ledger_digest: str | None
    review_packet_digest: str | None
    authorization_envelope_digest: str | None
    denial_ledger_digest: str | None
    policy_chain_digest: str | None
    zone_config_digest: str | None
    dry_run_proof_digest: str | None
    source_gate_ids: tuple[str, ...]
    source_request_ids: tuple[str, ...]
    source_trend_ids: tuple[str, ...]
    source_decision_record_ids: tuple[str, ...]
    source_review_packet_ids: tuple[str, ...]
    source_candidate_id: str | None
    requested_mode: str | None
    operator_label: str | None
    deferral_type: DeferralType
    deferral_reason: str
    registered_at: str
    deferral_expires_at: str | None
    stale_gate_count: int
    stale_request_count: int
    stale_trend_count: int
    stale_review_count: int
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
    deferral_grants_operator_consent: bool
    deferral_renews_operator_grant: bool
    deferral_enables_live_capture: bool
    deferral_enables_live_hardware: bool
    deferral_enables_raw_media_storage: bool
    deferral_enables_speaker_output: bool
    deferral_enables_external_disclosure: bool
    deferral_confers_live_readiness: bool
    deferral_confers_capture_authorization: bool
    deferral_schedules_live_review: bool
    deferral_approves_live_candidate: bool
    deferral_executes_dry_run: bool
    digest: str

@dataclass(frozen=True)
class HouseholdCameraFutureLiveDeferralRegistry:
    registry_id: str
    schema_version: str
    records: tuple[HouseholdCameraFutureLiveDeferralRecord, ...]
    digest: str

@dataclass(frozen=True)
class HouseholdCameraFutureLiveDeferralReport:
    status: RegistryStatus
    summary_counts: dict[str, int]
    findings: tuple[HouseholdCameraFutureLiveDeferralFinding, ...]

@dataclass(frozen=True)
class HouseholdCameraFutureLiveDeferralResult:
    status: RegistryStatus
    registry: HouseholdCameraFutureLiveDeferralRegistry | None
    report: HouseholdCameraFutureLiveDeferralReport
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def build_default_policy() -> HouseholdCameraFutureLiveDeferralRegistryPolicy:
    return HouseholdCameraFutureLiveDeferralRegistryPolicy()


def validate_policy(policy: HouseholdCameraFutureLiveDeferralRegistryPolicy) -> dict[str, Any]:
    modes = {policy.stale_gate_mode, policy.stale_request_mode, policy.stale_trend_mode, policy.stale_review_mode}
    ok = policy.schema_version.endswith(".v1") and modes <= {"block", "warn"} and policy.max_unresolved_denials >= 0
    return {"ok": ok, "status": "household_presence_camera_future_live_deferral_registry_policy_valid" if ok else "household_presence_camera_future_live_deferral_registry_policy_invalid"}


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
    keyset = {k.lower() for k in keys}
    if isinstance(value, Mapping):
        for key, item in value.items():
            lower = str(key).lower()
            if lower in keyset and bool(item):
                return True
            if _truthy_any(item, tuple(keyset)):
                return True
    if isinstance(value, list):
        return any(_truthy_any(item, tuple(keyset)) for item in value)
    return False


def _contains_text(value: Any, needles: frozenset[str]) -> bool:
    if isinstance(value, str):
        return any(needle in value for needle in needles)
    if isinstance(value, Mapping):
        return any(_contains_text(k, needles) or _contains_text(v, needles) for k, v in value.items())
    if isinstance(value, list):
        return any(_contains_text(item, needles) for item in value)
    return False


def _records(value: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    for key in ("records", "entries", "decision_records", "trend_records", "request_records"):
        candidate = value.get(key)
        if isinstance(candidate, list):
            return tuple(item for item in candidate if isinstance(item, Mapping))
    return ()


def _scope(value: Mapping[str, Any]) -> str:
    raw = value.get("scope_key") or value.get("scope") or value.get("zone_id") or value.get("requested_mode") or value.get("candidate_id") or "household_presence_camera"
    return str(raw)


def _ids(value: Mapping[str, Any], *keys: str) -> tuple[str, ...]:
    found: list[str] = []
    for key in keys:
        item = value.get(key)
        if isinstance(item, str) and item:
            found.append(item)
        elif isinstance(item, list):
            found.extend(str(v) for v in item if v)
    for record in _records(value):
        for key in keys:
            item = record.get(key)
            if item:
                found.append(str(item))
    return tuple(sorted(set(found)))


def _count(value: Any, *keys: str) -> int:
    total = 0
    wanted = {k.lower() for k in keys}
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).lower() in wanted:
                if isinstance(item, bool):
                    total += int(item)
                elif isinstance(item, int):
                    total += item
                elif isinstance(item, list):
                    total += len(item)
            total += _count(item, *keys)
    elif isinstance(value, list):
        for item in value:
            total += _count(item, *keys)
    return total


def _first_str(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value:
            return value
    return None


def _ready_gate(gate: Mapping[str, Any], policy: HouseholdCameraFutureLiveDeferralRegistryPolicy) -> bool:
    status = str(gate.get("status") or gate.get("gate_status") or "")
    if status in {"dry_run_continuation_gate_ready", "future_live_deferral_registry_ready"}:
        return True
    return policy.allow_ready_with_warnings_deferral and status in {"dry_run_continuation_gate_ready_with_warnings", "future_live_deferral_registry_ready_with_warnings"}


def _evidence_digest(value: Mapping[str, Any], explicit_key: str) -> str:
    explicit = value.get(explicit_key) or value.get("digest")
    return str(explicit) if explicit else _digest(value)


def _policy_from_payload(payload: Mapping[str, Any]) -> HouseholdCameraFutureLiveDeferralRegistryPolicy:
    policy_payload = payload.get("policy")
    if isinstance(policy_payload, Mapping):
        allowed = set(HouseholdCameraFutureLiveDeferralRegistryPolicy.__dataclass_fields__)
        return HouseholdCameraFutureLiveDeferralRegistryPolicy(**{k: v for k, v in policy_payload.items() if k in allowed})
    return build_default_policy()


def evaluate_future_live_deferral_registry(payload: Mapping[str, Any], policy: HouseholdCameraFutureLiveDeferralRegistryPolicy | None = None) -> HouseholdCameraFutureLiveDeferralResult:
    active_policy = policy or _policy_from_payload(payload)

    def blocked(status: RegistryStatus, code: str, message: str) -> HouseholdCameraFutureLiveDeferralResult:
        finding = HouseholdCameraFutureLiveDeferralFinding(code, message)
        report = HouseholdCameraFutureLiveDeferralReport(status, {"record_count": 0}, (finding,))
        return HouseholdCameraFutureLiveDeferralResult(status, None, report)

    if validate_policy(active_policy)["ok"] is not True:
        return blocked("future_live_deferral_registry_invalid", "policy_invalid", "future live deferral registry policy is invalid")
    if _has_media_payload(payload):
        return blocked("future_live_deferral_registry_blocked_media_payload", "media_payload", "media and base64 payloads are forbidden")
    if _truthy_any(payload, ("speaker_output_requested", "talkback_requested", "enable_speaker_output", "speaker_output_enabled")):
        return blocked("future_live_deferral_registry_blocked_speaker_boundary", "speaker_boundary", "speaker and talkback behavior are outside this registry")
    if _truthy_any(payload, ("external_disclosure_requested", "external_disclosure_enabled", "network_disclosure_requested", "provider_disclosure_requested")):
        return blocked("future_live_deferral_registry_blocked_external_authority", "external_authority", "external disclosure is outside this registry")

    gate = payload.get("dry_run_gate") or payload.get("gate") or payload.get("dry_run_continuation_gate")
    if not isinstance(gate, Mapping) or not gate:
        return blocked("future_live_deferral_registry_blocked_missing_dry_run_gate", "missing_dry_run_gate", "dry-run continuation gate evidence is required")
    renewal = payload.get("renewal_request_packet") or payload.get("operator_grant_renewal_request_packet")
    trend = payload.get("trend_ledger") or payload.get("operator_review_trend_ledger")
    decision = payload.get("decision_ledger") or payload.get("capture_review_decision_ledger")
    review = payload.get("review_packet") or payload.get("capture_review_packet")
    if active_policy.require_renewal_request_packet_digest and not isinstance(renewal, Mapping) and not active_policy.allow_gate_only_diagnostic_deferral:
        return blocked("future_live_deferral_registry_blocked_missing_renewal_request_packet", "missing_renewal_request_packet", "operator grant renewal request packet evidence is required")
    if active_policy.require_trend_ledger_digest and not isinstance(trend, Mapping) and not active_policy.allow_gate_only_diagnostic_deferral:
        return blocked("future_live_deferral_registry_blocked_missing_trend_ledger", "missing_trend_ledger", "operator review trend ledger evidence is required")
    if active_policy.require_decision_ledger_digest and not isinstance(decision, Mapping) and not active_policy.allow_gate_only_diagnostic_deferral:
        return blocked("future_live_deferral_registry_blocked_missing_decision_ledger", "missing_decision_ledger", "capture review decision ledger evidence is required")
    if active_policy.require_review_packet_digest and not isinstance(review, Mapping) and not active_policy.allow_gate_only_diagnostic_deferral:
        return blocked("future_live_deferral_registry_blocked_missing_review_packet", "missing_review_packet", "capture review packet evidence is required")
    if not _ready_gate(gate, active_policy):
        return blocked("future_live_deferral_registry_blocked_dry_run_gate_not_ready", "dry_run_gate_not_ready", "dry-run continuation gate must be ready or ready with warnings")
    if _truthy_any(payload, tuple(UNSAFE_LIVE_KEYS)):
        return blocked("future_live_deferral_registry_blocked_unsafe_live_implication", "unsafe_live_implication", "upstream evidence must not imply live readiness, consent, grant renewal, schedule, approval, capture, hardware, media, speaker, or external authority")
    if _truthy_any(gate, ("gate_executes_dry_run",)):
        return blocked("future_live_deferral_registry_blocked_unsafe_live_implication", "gate_executes_dry_run", "dry-run gate evidence must not execute dry-run capture")

    evidence = tuple(item for item in (gate, renewal, trend, decision, review) if isinstance(item, Mapping))
    scope_keys = tuple(sorted({_scope(item) for item in evidence + tuple(r for item in evidence for r in _records(item))}))
    findings: list[HouseholdCameraFutureLiveDeferralFinding] = []
    warned = False
    if len(scope_keys) > 1 and not active_policy.allow_mixed_scope_diagnostic_summary:
        return blocked("future_live_deferral_registry_blocked_scope_mismatch", "scope_mismatch", "upstream evidence scopes differ")
    if len(scope_keys) > 1:
        warned = True
        findings.append(HouseholdCameraFutureLiveDeferralFinding("mixed_scope_diagnostic_summary", "mixed scope remains warning-only and never merges authority"))

    stale_gate_count = _count(payload, "stale_gate_count", "stale_gate")
    stale_request_count = _count(payload, "stale_request_count", "stale_request")
    stale_trend_count = _count(payload, "stale_trend_count", "stale_trend")
    stale_review_count = _count(payload, "stale_review_count", "stale_review")
    stale_modes = ((stale_gate_count, active_policy.stale_gate_mode, "future_live_deferral_registry_blocked_stale_gate", "stale_gate"), (stale_request_count, active_policy.stale_request_mode, "future_live_deferral_registry_blocked_stale_request", "stale_request"), (stale_trend_count, active_policy.stale_trend_mode, "future_live_deferral_registry_blocked_stale_trend", "stale_trend"), (stale_review_count, active_policy.stale_review_mode, "future_live_deferral_registry_blocked_stale_review", "stale_review"))
    for count, mode, blocked_status, code in stale_modes:
        if count and mode == "block":
            return blocked(cast(RegistryStatus, blocked_status), code, f"{code} evidence is blocked by policy")
        if count:
            warned = True
            findings.append(HouseholdCameraFutureLiveDeferralFinding(code, f"{code} evidence requires review before future-live review"))

    unresolved_denial_count_total = _count(payload, "unresolved_denial_count", "unresolved_denial_count_total")
    if unresolved_denial_count_total > active_policy.max_unresolved_denials:
        return blocked("future_live_deferral_registry_blocked_unresolved_denials", "unresolved_denials", "unresolved denials block future-live consideration")
    renewal_required_count = _count(payload, "renewal_required_count", "operator_grant_required_count") + int(_contains_text(payload, frozenset({"operator_grant_required", "request_operator_grant_renewal"})))
    proof_refresh_required_count = _count(payload, "proof_refresh_required_count") + int(_contains_text(payload, frozenset({"proof_refresh_required", "dry_run_proof_refresh", "policy_chain_proof_refresh", "zone_config_refresh", "disabled_capture_boundary_refresh"})))
    if renewal_required_count and not active_policy.allow_diagnostic_deferral_when_operator_grant_required:
        return blocked("future_live_deferral_registry_blocked_operator_grant_required", "operator_grant_required", "operator grant is required before any future-live review")
    if proof_refresh_required_count and not active_policy.allow_diagnostic_deferral_when_refresh_required:
        return blocked("future_live_deferral_registry_blocked_proof_refresh_required", "proof_refresh_required", "proof refresh is required before any future-live review")
    if renewal_required_count:
        warned = True
        findings.append(HouseholdCameraFutureLiveDeferralFinding("operator_grant_required", "operator grant requirement is recorded as deferral only"))
    if proof_refresh_required_count:
        warned = True
        findings.append(HouseholdCameraFutureLiveDeferralFinding("proof_refresh_required", "proof refresh requirement is recorded as deferral only"))

    if _contains_text(payload, frozenset({"dry_run_continuation_not_live_readiness", "continue_dry_run_only"})):
        deferral_type: DeferralType = "dry_run_continuation_not_live_readiness"
        safe_next_action: SafeNextAction = "inspect_dry_run_gate"
    elif _contains_text(payload, frozenset({"grant_renewal_request_not_live_consent"})):
        deferral_type = "grant_renewal_request_not_live_consent"
        safe_next_action = "inspect_renewal_request"
    elif _contains_text(payload, frozenset({"trend_history_not_live_consent"})):
        deferral_type = "trend_history_not_live_consent"
        safe_next_action = "inspect_trend_history"
    elif _contains_text(payload, frozenset({"decision_history_not_live_consent"})):
        deferral_type = "decision_history_not_live_consent"
        safe_next_action = "inspect_decision_history"
    elif renewal_required_count:
        deferral_type = "operator_grant_required_before_future_live_review"
        safe_next_action = "request_operator_grant_renewal"
    elif proof_refresh_required_count:
        deferral_type = "proof_refresh_required_before_future_live_review"
        safe_next_action = "request_dry_run_proof_refresh"
    elif stale_gate_count or stale_request_count or stale_trend_count or stale_review_count:
        deferral_type = "stale_evidence_requires_review_before_future_live"
        safe_next_action = "operator_review_required"
    elif len(scope_keys) > 1:
        deferral_type = "mixed_scope_requires_operator_review"
        safe_next_action = "operator_review_required"
    else:
        requested = str(payload.get("deferral_type") or gate.get("gate_decision") or "")
        if requested in {"live_candidate_review_not_requested", "live_candidate_review_requires_separate_operator_confirmation", "future_live_review_deferred"}:
            deferral_type = cast(DeferralType, requested)
        else:
            deferral_type = "future_live_review_deferred"
        safe_next_action = "maintain_future_live_deferral"

    registered_at = str(payload.get("registered_at") or "2026-01-01T00:00:00Z")
    record_shell: dict[str, Any] = {
        "record_id": str(payload.get("record_id") or "future-live-deferral-record-001"),
        "deferral_id": str(payload.get("deferral_id") or "future-live-deferral-001"),
        "dry_run_gate_digest": _evidence_digest(gate, "dry_run_gate_digest"),
        "renewal_request_packet_digest": _evidence_digest(renewal, "renewal_request_packet_digest") if isinstance(renewal, Mapping) else None,
        "trend_ledger_digest": _evidence_digest(trend, "trend_ledger_digest") if isinstance(trend, Mapping) else None,
        "decision_ledger_digest": _evidence_digest(decision, "decision_ledger_digest") if isinstance(decision, Mapping) else None,
        "review_packet_digest": _evidence_digest(review, "review_packet_digest") if isinstance(review, Mapping) else None,
        "authorization_envelope_digest": _first_str(payload.get("authorization_envelope_digest"), gate.get("authorization_envelope_digest")),
        "denial_ledger_digest": _first_str(payload.get("denial_ledger_digest"), gate.get("denial_ledger_digest")),
        "policy_chain_digest": _first_str(payload.get("policy_chain_digest"), gate.get("policy_chain_digest")),
        "zone_config_digest": _first_str(payload.get("zone_config_digest"), gate.get("zone_config_digest")),
        "dry_run_proof_digest": _first_str(payload.get("dry_run_proof_digest"), gate.get("dry_run_proof_digest")),
        "source_gate_ids": _ids(gate, "gate_id", "record_id"),
        "source_request_ids": _ids(renewal, "request_id", "packet_id", "record_id") if isinstance(renewal, Mapping) else (),
        "source_trend_ids": _ids(trend, "trend_id", "ledger_id", "record_id") if isinstance(trend, Mapping) else (),
        "source_decision_record_ids": _ids(decision, "decision_record_id", "decision_id", "record_id") if isinstance(decision, Mapping) else (),
        "source_review_packet_ids": _ids(review, "review_packet_id", "packet_id", "record_id") if isinstance(review, Mapping) else (),
        "source_candidate_id": _first_str(payload.get("source_candidate_id"), gate.get("source_candidate_id"), gate.get("candidate_id")),
        "requested_mode": _first_str(payload.get("requested_mode"), gate.get("requested_mode")),
        "operator_label": _first_str(payload.get("operator_label"), gate.get("operator_label")),
        "deferral_type": deferral_type,
        "deferral_reason": str(payload.get("deferral_reason") or "future live-candidate review remains explicitly deferred and operator-only"),
        "registered_at": registered_at,
        "deferral_expires_at": _first_str(payload.get("deferral_expires_at")),
        "stale_gate_count": stale_gate_count,
        "stale_request_count": stale_request_count,
        "stale_trend_count": stale_trend_count,
        "stale_review_count": stale_review_count,
        "unresolved_denial_count_total": unresolved_denial_count_total,
        "renewal_required_count": renewal_required_count,
        "proof_refresh_required_count": proof_refresh_required_count,
        "dry_run_continuation_count": max(1, _count(payload, "dry_run_continuation_count")) if deferral_type == "dry_run_continuation_not_live_readiness" else _count(payload, "dry_run_continuation_count"),
        "future_live_deferred_count": max(1, _count(payload, "future_live_deferred_count")),
        "scope_keys": scope_keys or ("household_presence_camera",),
        "safe_next_action": safe_next_action,
        "forbidden_next_steps": FORBIDDEN_NEXT_STEPS,
        "capture_enabled": False,
        "capture_available": False,
        "live_hardware_enabled": False,
        "raw_media_storage_enabled": False,
        "no_live_capture_performed": True,
        "speaker_output_enabled": False,
        "external_disclosure_enabled": False,
        "deferral_grants_operator_consent": False,
        "deferral_renews_operator_grant": False,
        "deferral_enables_live_capture": False,
        "deferral_enables_live_hardware": False,
        "deferral_enables_raw_media_storage": False,
        "deferral_enables_speaker_output": False,
        "deferral_enables_external_disclosure": False,
        "deferral_confers_live_readiness": False,
        "deferral_confers_capture_authorization": False,
        "deferral_schedules_live_review": False,
        "deferral_approves_live_candidate": False,
        "deferral_executes_dry_run": False,
    }
    record = HouseholdCameraFutureLiveDeferralRecord(**record_shell, digest=_digest(record_shell))
    registry_id = str(payload.get("registry_id") or "household-presence-camera-future-live-deferral-registry")
    registry_schema_version = "household_presence_camera_future_live_deferral_registry.v1"
    registry_shell: dict[str, Any] = {"registry_id": registry_id, "schema_version": registry_schema_version, "records": [asdict(record)]}
    registry = HouseholdCameraFutureLiveDeferralRegistry(registry_id, registry_schema_version, (record,), _digest(registry_shell))
    summary_counts = dict(sorted({
        "record_count": len(registry.records),
        "future_live_deferred_count": record.future_live_deferred_count,
        "dry_run_continuation_count": record.dry_run_continuation_count,
        "renewal_required_count": record.renewal_required_count,
        "proof_refresh_required_count": record.proof_refresh_required_count,
        "stale_gate_count": record.stale_gate_count,
        "stale_request_count": record.stale_request_count,
        "stale_trend_count": record.stale_trend_count,
        "stale_review_count": record.stale_review_count,
        "unresolved_denial_count_total": record.unresolved_denial_count_total,
        "scope_count": len(record.scope_keys),
    }.items()))
    status: RegistryStatus = "future_live_deferral_registry_ready_with_warnings" if warned else "future_live_deferral_registry_ready"
    return HouseholdCameraFutureLiveDeferralResult(status, registry, HouseholdCameraFutureLiveDeferralReport(status, summary_counts, tuple(findings)))

