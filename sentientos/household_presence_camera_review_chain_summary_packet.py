from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Literal, Mapping, Sequence, cast

SummaryStatus = Literal[
    "review_chain_summary_packet_ready",
    "review_chain_summary_packet_ready_with_warnings",
    "review_chain_summary_packet_blocked_missing_review_packet",
    "review_chain_summary_packet_blocked_missing_decision_ledger",
    "review_chain_summary_packet_blocked_missing_trend_ledger",
    "review_chain_summary_packet_blocked_missing_renewal_request_packet",
    "review_chain_summary_packet_blocked_missing_dry_run_gate",
    "review_chain_summary_packet_blocked_missing_future_live_deferral_registry",
    "review_chain_summary_packet_blocked_upstream_not_ready",
    "review_chain_summary_packet_blocked_unsafe_live_implication",
    "review_chain_summary_packet_blocked_operator_grant_required",
    "review_chain_summary_packet_blocked_proof_refresh_required",
    "review_chain_summary_packet_blocked_unresolved_denials",
    "review_chain_summary_packet_blocked_scope_mismatch",
    "review_chain_summary_packet_blocked_stale_review",
    "review_chain_summary_packet_blocked_stale_decision",
    "review_chain_summary_packet_blocked_stale_trend",
    "review_chain_summary_packet_blocked_stale_request",
    "review_chain_summary_packet_blocked_stale_gate",
    "review_chain_summary_packet_blocked_stale_deferral",
    "review_chain_summary_packet_blocked_media_payload",
    "review_chain_summary_packet_blocked_speaker_boundary",
    "review_chain_summary_packet_blocked_external_authority",
    "review_chain_summary_packet_invalid",
    "review_chain_summary_packet_failed",
]

SummaryConclusion = Literal[
    "review_chain_metadata_ready",
    "review_chain_ready_with_warnings",
    "review_chain_operator_review_required",
    "review_chain_operator_grant_required",
    "review_chain_proof_refresh_required",
    "review_chain_capture_review_packet_rerun_required",
    "review_chain_decision_history_review_required",
    "review_chain_trend_history_review_required",
    "review_chain_renewal_request_review_required",
    "review_chain_dry_run_gate_review_required",
    "review_chain_future_live_deferral_confirmed",
    "review_chain_future_live_remains_deferred",
    "review_chain_sustain_capture_denial",
    "review_chain_blocked_by_unresolved_denials",
    "review_chain_blocked_by_scope_mismatch",
    "review_chain_blocked_by_stale_evidence",
    "review_chain_blocked_by_unsafe_live_implication",
]

SafeNextAction = Literal[
    "no_action_allowed",
    "operator_review_required",
    "inspect_review_chain",
    "inspect_decision_history",
    "inspect_trend_history",
    "inspect_renewal_request",
    "inspect_dry_run_gate",
    "inspect_future_live_deferral",
    "request_operator_grant_renewal",
    "request_dry_run_proof_refresh",
    "request_policy_chain_proof_refresh",
    "request_zone_config_refresh",
    "request_disabled_capture_boundary_refresh",
    "rerun_capture_review_packet",
    "sustain_capture_denial",
    "maintain_future_live_deferral",
]

FORBIDDEN_NEXT_STEPS = (
    "open_camera_now",
    "attempt_capture",
    "enable_live_capture",
    "enable_live_recording",
    "store_raw_media",
    "attach_media_payload",
    "execute_dry_run_capture",
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
    "bypass_future_live_deferral_registry",
    "bypass_policy_chain",
    "bypass_zone_config",
    "bypass_disabled_capture_boundary",
    "bypass_dry_run",
    "infer_operator_consent_from_summary",
    "infer_operator_consent_from_chain",
    "infer_operator_consent_from_gate",
    "infer_operator_consent_from_trends",
    "infer_operator_consent_from_renewal_request",
    "convert_renewal_request_to_grant",
    "convert_dry_run_gate_to_live_readiness",
    "convert_deferral_to_live_readiness",
    "convert_summary_to_live_readiness",
    "convert_summary_to_live_capture_permission",
    "enable_speaker_output",
    "enable_external_disclosure",
)

MEDIA_KEYS = frozenset({"raw_media", "raw_media_payload", "media_payload", "image", "video", "audio", "thumbnail", "screenshot", "transcript", "base64", "base64_media", "base64_payload"})
UNSAFE_LIVE_KEYS = frozenset({
    "live_ready", "live_readiness", "live_capture_permission", "capture_authorized", "capture_authorization_granted",
    "operator_consent_granted", "operator_grant_renewed", "live_review_scheduled", "schedule_live_capture_review",
    "approved_live_candidate", "live_candidate_approved", "capture_enabled", "capture_available", "live_hardware_enabled",
    "raw_media_storage_enabled", "speaker_output_enabled", "external_disclosure_enabled", "summary_grants_operator_consent",
    "summary_renews_operator_grant", "summary_enables_live_capture", "summary_enables_live_hardware", "summary_enables_raw_media_storage",
    "summary_enables_speaker_output", "summary_enables_external_disclosure", "summary_confers_live_readiness",
    "summary_confers_capture_authorization", "summary_schedules_live_review", "summary_approves_live_candidate", "summary_executes_dry_run",
    "gate_executes_dry_run", "deferral_confers_live_readiness", "deferral_enables_live_capture", "deferral_approves_live_candidate",
})

@dataclass(frozen=True)
class HouseholdCameraReviewChainSummaryPolicy:
    schema_version: str = "household_presence_camera_review_chain_summary_packet_policy.v1"
    require_review_packet_digest: bool = True
    require_decision_ledger_digest: bool = True
    require_trend_ledger_digest: bool = True
    require_renewal_request_packet_digest: bool = True
    require_dry_run_gate_digest: bool = True
    require_future_live_deferral_registry_digest: bool = True
    allow_diagnostic_summary_when_upstream_blocked: bool = True
    allow_diagnostic_summary_when_refresh_required: bool = True
    allow_diagnostic_summary_when_operator_grant_required: bool = True
    allow_ready_with_warnings_summary: bool = True
    allow_mixed_scope_diagnostic_summary: bool = False
    max_unresolved_denials: int = 0
    stale_review_mode: Literal["block", "warn"] = "warn"
    stale_decision_mode: Literal["block", "warn"] = "warn"
    stale_trend_mode: Literal["block", "warn"] = "warn"
    stale_request_mode: Literal["block", "warn"] = "warn"
    stale_gate_mode: Literal["block", "warn"] = "warn"
    stale_deferral_mode: Literal["block", "warn"] = "warn"

@dataclass(frozen=True)
class HouseholdCameraReviewChainSummaryInput:
    review_packet: dict[str, Any]
    decision_ledger: dict[str, Any]
    trend_ledger: dict[str, Any]
    renewal_request_packet: dict[str, Any]
    dry_run_gate: dict[str, Any]
    future_live_deferral_registry: dict[str, Any]
    policy: HouseholdCameraReviewChainSummaryPolicy | None = None

@dataclass(frozen=True)
class HouseholdCameraReviewChainSummaryFinding:
    code: str
    message: str

@dataclass(frozen=True)
class HouseholdCameraReviewChainSummaryRecord:
    record_id: str
    summary_id: str
    review_packet_digest: str
    decision_ledger_digest: str
    trend_ledger_digest: str
    renewal_request_packet_digest: str
    dry_run_gate_digest: str
    future_live_deferral_registry_digest: str
    authorization_envelope_digest: str | None
    denial_ledger_digest: str | None
    policy_chain_digest: str | None
    zone_config_digest: str | None
    dry_run_proof_digest: str | None
    source_review_packet_ids: tuple[str, ...]
    source_decision_record_ids: tuple[str, ...]
    source_trend_ids: tuple[str, ...]
    source_request_ids: tuple[str, ...]
    source_gate_ids: tuple[str, ...]
    source_deferral_ids: tuple[str, ...]
    source_candidate_id: str | None
    requested_mode: str | None
    operator_label: str | None
    summary_conclusion: SummaryConclusion
    summary_reason: str
    generated_at: str
    summary_expires_at: str | None
    stale_review_count: int
    stale_decision_count: int
    stale_trend_count: int
    stale_request_count: int
    stale_gate_count: int
    stale_deferral_count: int
    unresolved_denial_count_total: int
    renewal_required_count: int
    proof_refresh_required_count: int
    dry_run_continuation_count: int
    future_live_deferred_count: int
    blocker_count: int
    warning_count: int
    scope_keys: tuple[str, ...]
    safe_next_actions: tuple[SafeNextAction, ...]
    forbidden_next_steps: tuple[str, ...]
    capture_enabled: bool
    capture_available: bool
    live_hardware_enabled: bool
    raw_media_storage_enabled: bool
    no_live_capture_performed: bool
    speaker_output_enabled: bool
    external_disclosure_enabled: bool
    summary_grants_operator_consent: bool
    summary_renews_operator_grant: bool
    summary_enables_live_capture: bool
    summary_enables_live_hardware: bool
    summary_enables_raw_media_storage: bool
    summary_enables_speaker_output: bool
    summary_enables_external_disclosure: bool
    summary_confers_live_readiness: bool
    summary_confers_capture_authorization: bool
    summary_schedules_live_review: bool
    summary_approves_live_candidate: bool
    summary_executes_dry_run: bool
    digest: str

@dataclass(frozen=True)
class HouseholdCameraReviewChainSummaryPacket:
    packet_id: str
    schema_version: str
    records: tuple[HouseholdCameraReviewChainSummaryRecord, ...]
    digest: str

@dataclass(frozen=True)
class HouseholdCameraReviewChainSummaryReport:
    status: SummaryStatus
    summary_counts: dict[str, int]
    findings: tuple[HouseholdCameraReviewChainSummaryFinding, ...]

@dataclass(frozen=True)
class HouseholdCameraReviewChainSummaryResult:
    status: SummaryStatus
    packet: HouseholdCameraReviewChainSummaryPacket | None
    report: HouseholdCameraReviewChainSummaryReport
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def build_default_policy() -> HouseholdCameraReviewChainSummaryPolicy:
    return HouseholdCameraReviewChainSummaryPolicy()


def validate_policy(policy: HouseholdCameraReviewChainSummaryPolicy) -> dict[str, Any]:
    modes = {policy.stale_review_mode, policy.stale_decision_mode, policy.stale_trend_mode, policy.stale_request_mode, policy.stale_gate_mode, policy.stale_deferral_mode}
    ok = policy.schema_version.endswith(".v1") and modes <= {"block", "warn"} and policy.max_unresolved_denials >= 0
    return {"ok": ok, "status": "household_presence_camera_review_chain_summary_packet_policy_valid" if ok else "household_presence_camera_review_chain_summary_packet_policy_invalid"}


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
    records: list[Mapping[str, Any]] = []
    for key in ("records", "entries", "decision_records", "trend_records", "request_records"):
        candidate = value.get(key)
        if isinstance(candidate, list):
            records.extend(item for item in candidate if isinstance(item, Mapping))
    return tuple(records)


def _scope(value: Mapping[str, Any]) -> str:
    raw = value.get("scope_key") or value.get("scope") or value.get("zone_id") or value.get("requested_mode") or value.get("candidate_id") or value.get("source_candidate_id") or "household_presence_camera"
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


def _evidence_digest(value: Mapping[str, Any], explicit_key: str) -> str:
    explicit = value.get(explicit_key) or value.get("digest")
    return str(explicit) if explicit else _digest(value)


def _policy_from_payload(payload: Mapping[str, Any]) -> HouseholdCameraReviewChainSummaryPolicy:
    policy_payload = payload.get("policy")
    if isinstance(policy_payload, Mapping):
        allowed = set(HouseholdCameraReviewChainSummaryPolicy.__dataclass_fields__)
        return HouseholdCameraReviewChainSummaryPolicy(**{k: v for k, v in policy_payload.items() if k in allowed})
    return build_default_policy()


def _status_of(evidence: Mapping[str, Any]) -> str:
    return str(evidence.get("status") or evidence.get("packet_status") or evidence.get("ledger_status") or evidence.get("gate_status") or evidence.get("registry_status") or "")


def _upstream_problem_status(status: str) -> bool:
    return bool(status) and ("blocked" in status or status.endswith("invalid") or status.endswith("failed"))


def evaluate_review_chain_summary_packet(payload: Mapping[str, Any], policy: HouseholdCameraReviewChainSummaryPolicy | None = None) -> HouseholdCameraReviewChainSummaryResult:
    active_policy = policy or _policy_from_payload(payload)

    def blocked(status: SummaryStatus, code: str, message: str) -> HouseholdCameraReviewChainSummaryResult:
        finding = HouseholdCameraReviewChainSummaryFinding(code, message)
        report = HouseholdCameraReviewChainSummaryReport(status, {"record_count": 0}, (finding,))
        return HouseholdCameraReviewChainSummaryResult(status, None, report)

    if validate_policy(active_policy)["ok"] is not True:
        return blocked("review_chain_summary_packet_invalid", "invalid_policy", "summary policy is invalid")
    if _has_media_payload(payload):
        return blocked("review_chain_summary_packet_blocked_media_payload", "media_payload", "review-chain summary accepts metadata only and blocks media/base64 payloads")
    if _truthy_any(payload, ("speaker_request", "talkback_request", "speaker_output_requested", "enable_speaker_output")):
        return blocked("review_chain_summary_packet_blocked_speaker_boundary", "speaker_boundary", "speaker or talkback requests are outside summary scope")
    if _truthy_any(payload, ("external_disclosure_requested", "external_authority_requested", "network_disclosure_requested", "enable_external_disclosure")):
        return blocked("review_chain_summary_packet_blocked_external_authority", "external_authority", "external disclosure or authority is outside summary scope")

    review = payload.get("review_packet") or payload.get("capture_review_packet")
    decision = payload.get("decision_ledger") or payload.get("capture_review_decision_ledger")
    trend = payload.get("trend_ledger") or payload.get("operator_review_trend_ledger")
    renewal = payload.get("renewal_request_packet") or payload.get("operator_grant_renewal_request_packet")
    gate = payload.get("dry_run_gate") or payload.get("dry_run_continuation_gate")
    deferral = payload.get("future_live_deferral_registry") or payload.get("deferral_registry")
    required = (
        (review, active_policy.require_review_packet_digest, "review_chain_summary_packet_blocked_missing_review_packet", "missing_review_packet", "capture review packet evidence is required"),
        (decision, active_policy.require_decision_ledger_digest, "review_chain_summary_packet_blocked_missing_decision_ledger", "missing_decision_ledger", "capture review decision ledger evidence is required"),
        (trend, active_policy.require_trend_ledger_digest, "review_chain_summary_packet_blocked_missing_trend_ledger", "missing_trend_ledger", "operator review trend ledger evidence is required"),
        (renewal, active_policy.require_renewal_request_packet_digest, "review_chain_summary_packet_blocked_missing_renewal_request_packet", "missing_renewal_request_packet", "operator grant renewal request packet evidence is required"),
        (gate, active_policy.require_dry_run_gate_digest, "review_chain_summary_packet_blocked_missing_dry_run_gate", "missing_dry_run_gate", "dry-run continuation gate evidence is required"),
        (deferral, active_policy.require_future_live_deferral_registry_digest, "review_chain_summary_packet_blocked_missing_future_live_deferral_registry", "missing_future_live_deferral_registry", "future live deferral registry evidence is required"),
    )
    for evidence, required_digest, status, code, message in required:
        if required_digest and not isinstance(evidence, Mapping):
            return blocked(cast(SummaryStatus, status), code, message)
    evidence_items = tuple(item for item in (review, decision, trend, renewal, gate, deferral) if isinstance(item, Mapping))
    if _truthy_any(payload, tuple(UNSAFE_LIVE_KEYS)):
        return blocked("review_chain_summary_packet_blocked_unsafe_live_implication", "unsafe_live_implication", "upstream evidence must not imply capture, live readiness, consent, grant renewal, live review scheduling, candidate approval, dry-run execution, hardware, media, speaker, or external authority")

    findings: list[HouseholdCameraReviewChainSummaryFinding] = []
    blocker_count = 0
    warning_count = 0
    for item in evidence_items:
        status_text = _status_of(item)
        if _upstream_problem_status(status_text):
            if not active_policy.allow_diagnostic_summary_when_upstream_blocked:
                return blocked("review_chain_summary_packet_blocked_upstream_not_ready", "upstream_not_ready", f"upstream evidence status {status_text} is not ready")
            warning_count += 1
            findings.append(HouseholdCameraReviewChainSummaryFinding("upstream_not_ready", f"upstream evidence status {status_text} is summarized diagnostically only"))
        elif "ready_with_warnings" in status_text:
            if not active_policy.allow_ready_with_warnings_summary:
                return blocked("review_chain_summary_packet_blocked_upstream_not_ready", "upstream_ready_with_warnings", f"upstream evidence status {status_text} has warnings")
            warning_count += 1
            findings.append(HouseholdCameraReviewChainSummaryFinding("upstream_ready_with_warnings", f"upstream evidence status {status_text} carries warnings"))

    scope_keys = tuple(sorted({_scope(item) for item in evidence_items + tuple(r for item in evidence_items for r in _records(item))}))
    if len(scope_keys) > 1 and not active_policy.allow_mixed_scope_diagnostic_summary:
        return blocked("review_chain_summary_packet_blocked_scope_mismatch", "scope_mismatch", "review-chain evidence scopes differ")
    if len(scope_keys) > 1:
        warning_count += 1
        findings.append(HouseholdCameraReviewChainSummaryFinding("mixed_scope_diagnostic_summary", "mixed scope remains warning-only and never merges authority"))

    stale_review_count = _count(payload, "stale_review_count", "stale_review")
    stale_decision_count = _count(payload, "stale_decision_count", "stale_decision")
    stale_trend_count = _count(payload, "stale_trend_count", "stale_trend")
    stale_request_count = _count(payload, "stale_request_count", "stale_request")
    stale_gate_count = _count(payload, "stale_gate_count", "stale_gate")
    stale_deferral_count = _count(payload, "stale_deferral_count", "stale_deferral")
    stale_modes = (
        (stale_review_count, active_policy.stale_review_mode, "review_chain_summary_packet_blocked_stale_review", "stale_review"),
        (stale_decision_count, active_policy.stale_decision_mode, "review_chain_summary_packet_blocked_stale_decision", "stale_decision"),
        (stale_trend_count, active_policy.stale_trend_mode, "review_chain_summary_packet_blocked_stale_trend", "stale_trend"),
        (stale_request_count, active_policy.stale_request_mode, "review_chain_summary_packet_blocked_stale_request", "stale_request"),
        (stale_gate_count, active_policy.stale_gate_mode, "review_chain_summary_packet_blocked_stale_gate", "stale_gate"),
        (stale_deferral_count, active_policy.stale_deferral_mode, "review_chain_summary_packet_blocked_stale_deferral", "stale_deferral"),
    )
    stale_warning = False
    for count, mode, status, code in stale_modes:
        if count and mode == "block":
            return blocked(cast(SummaryStatus, status), code, f"{code} evidence is blocked by policy")
        if count:
            stale_warning = True
            warning_count += 1
            findings.append(HouseholdCameraReviewChainSummaryFinding(code, f"{code} evidence requires operator review"))

    unresolved_denial_count_total = _count(payload, "unresolved_denial_count", "unresolved_denial_count_total")
    if unresolved_denial_count_total > active_policy.max_unresolved_denials:
        return blocked("review_chain_summary_packet_blocked_unresolved_denials", "unresolved_denials", "unresolved denials block review-chain readiness")
    renewal_required_count = _count(payload, "renewal_required_count", "operator_grant_required_count") + int(_contains_text(payload, frozenset({"operator_grant_required", "request_operator_grant_renewal"})))
    proof_refresh_required_count = _count(payload, "proof_refresh_required_count") + int(_contains_text(payload, frozenset({"proof_refresh_required", "dry_run_proof_refresh", "policy_chain_proof_refresh", "zone_config_refresh", "disabled_capture_boundary_refresh"})))
    if renewal_required_count and not active_policy.allow_diagnostic_summary_when_operator_grant_required:
        return blocked("review_chain_summary_packet_blocked_operator_grant_required", "operator_grant_required", "operator grant is required outside this summary packet")
    if proof_refresh_required_count and not active_policy.allow_diagnostic_summary_when_refresh_required:
        return blocked("review_chain_summary_packet_blocked_proof_refresh_required", "proof_refresh_required", "proof refresh is required outside this summary packet")
    if renewal_required_count:
        warning_count += 1
        findings.append(HouseholdCameraReviewChainSummaryFinding("operator_grant_required", "operator grant requirement is summarized but not granted"))
    if proof_refresh_required_count:
        warning_count += 1
        findings.append(HouseholdCameraReviewChainSummaryFinding("proof_refresh_required", "proof refresh requirement is summarized but not repaired"))

    dry_run_continuation_count = max(_count(payload, "dry_run_continuation_count"), int(_contains_text(payload, frozenset({"dry_run_continuation"}))))
    future_live_deferred_count = max(_count(payload, "future_live_deferred_count"), 1 if isinstance(deferral, Mapping) else 0)
    requested = str(payload.get("summary_conclusion") or payload.get("review_chain_conclusion") or "")
    conclusion: SummaryConclusion
    actions: list[SafeNextAction]
    reason = str(payload.get("summary_reason") or "review-chain summary is metadata-only and confers no authority")
    if requested in SummaryConclusion.__args__:  # type: ignore[attr-defined]
        conclusion = cast(SummaryConclusion, requested)
    elif renewal_required_count:
        conclusion = "review_chain_operator_grant_required"
    elif proof_refresh_required_count:
        conclusion = "review_chain_proof_refresh_required"
    elif stale_warning:
        conclusion = "review_chain_blocked_by_stale_evidence"
    elif warning_count:
        conclusion = "review_chain_ready_with_warnings"
    elif future_live_deferred_count:
        conclusion = "review_chain_future_live_remains_deferred"
    else:
        conclusion = "review_chain_metadata_ready"

    if conclusion == "review_chain_operator_review_required":
        actions = ["operator_review_required", "inspect_review_chain", "maintain_future_live_deferral"]
    elif conclusion == "review_chain_operator_grant_required":
        actions = ["operator_review_required", "inspect_renewal_request", "request_operator_grant_renewal", "maintain_future_live_deferral"]
    elif conclusion == "review_chain_proof_refresh_required":
        actions = ["operator_review_required", "request_dry_run_proof_refresh", "request_policy_chain_proof_refresh", "inspect_dry_run_gate", "maintain_future_live_deferral"]
    elif conclusion == "review_chain_capture_review_packet_rerun_required":
        actions = ["operator_review_required", "rerun_capture_review_packet", "maintain_future_live_deferral"]
    elif conclusion == "review_chain_decision_history_review_required":
        actions = ["operator_review_required", "inspect_decision_history", "maintain_future_live_deferral"]
    elif conclusion == "review_chain_trend_history_review_required":
        actions = ["operator_review_required", "inspect_trend_history", "maintain_future_live_deferral"]
    elif conclusion == "review_chain_renewal_request_review_required":
        actions = ["operator_review_required", "inspect_renewal_request", "maintain_future_live_deferral"]
    elif conclusion == "review_chain_dry_run_gate_review_required":
        actions = ["operator_review_required", "inspect_dry_run_gate", "maintain_future_live_deferral"]
    elif conclusion == "review_chain_sustain_capture_denial":
        actions = ["operator_review_required", "sustain_capture_denial", "maintain_future_live_deferral"]
    elif conclusion in {"review_chain_future_live_deferral_confirmed", "review_chain_future_live_remains_deferred"}:
        actions = ["inspect_future_live_deferral", "maintain_future_live_deferral"]
    elif warning_count:
        actions = ["operator_review_required", "inspect_review_chain", "maintain_future_live_deferral"]
    else:
        actions = ["inspect_review_chain", "maintain_future_live_deferral"]

    generated_at = str(payload.get("generated_at") or "2026-01-01T00:00:00Z")
    record_shell: dict[str, Any] = {
        "record_id": str(payload.get("record_id") or "review-chain-summary-record-001"),
        "summary_id": str(payload.get("summary_id") or "review-chain-summary-001"),
        "review_packet_digest": _evidence_digest(cast(Mapping[str, Any], review), "review_packet_digest"),
        "decision_ledger_digest": _evidence_digest(cast(Mapping[str, Any], decision), "decision_ledger_digest"),
        "trend_ledger_digest": _evidence_digest(cast(Mapping[str, Any], trend), "trend_ledger_digest"),
        "renewal_request_packet_digest": _evidence_digest(cast(Mapping[str, Any], renewal), "renewal_request_packet_digest"),
        "dry_run_gate_digest": _evidence_digest(cast(Mapping[str, Any], gate), "dry_run_gate_digest"),
        "future_live_deferral_registry_digest": _evidence_digest(cast(Mapping[str, Any], deferral), "future_live_deferral_registry_digest"),
        "authorization_envelope_digest": _first_str(payload.get("authorization_envelope_digest"), *(item.get("authorization_envelope_digest") for item in evidence_items)),
        "denial_ledger_digest": _first_str(payload.get("denial_ledger_digest"), *(item.get("denial_ledger_digest") for item in evidence_items)),
        "policy_chain_digest": _first_str(payload.get("policy_chain_digest"), *(item.get("policy_chain_digest") for item in evidence_items)),
        "zone_config_digest": _first_str(payload.get("zone_config_digest"), *(item.get("zone_config_digest") for item in evidence_items)),
        "dry_run_proof_digest": _first_str(payload.get("dry_run_proof_digest"), *(item.get("dry_run_proof_digest") for item in evidence_items)),
        "source_review_packet_ids": _ids(cast(Mapping[str, Any], review), "review_packet_id", "packet_id", "record_id"),
        "source_decision_record_ids": _ids(cast(Mapping[str, Any], decision), "decision_record_id", "decision_id", "record_id"),
        "source_trend_ids": _ids(cast(Mapping[str, Any], trend), "trend_id", "ledger_id", "record_id"),
        "source_request_ids": _ids(cast(Mapping[str, Any], renewal), "request_id", "packet_id", "record_id"),
        "source_gate_ids": _ids(cast(Mapping[str, Any], gate), "gate_id", "record_id"),
        "source_deferral_ids": _ids(cast(Mapping[str, Any], deferral), "deferral_id", "registry_id", "record_id"),
        "source_candidate_id": _first_str(payload.get("source_candidate_id"), *(item.get("source_candidate_id") or item.get("candidate_id") for item in evidence_items)),
        "requested_mode": _first_str(payload.get("requested_mode"), *(item.get("requested_mode") for item in evidence_items)),
        "operator_label": _first_str(payload.get("operator_label"), *(item.get("operator_label") for item in evidence_items)),
        "summary_conclusion": conclusion,
        "summary_reason": reason,
        "generated_at": generated_at,
        "summary_expires_at": _first_str(payload.get("summary_expires_at")),
        "stale_review_count": stale_review_count,
        "stale_decision_count": stale_decision_count,
        "stale_trend_count": stale_trend_count,
        "stale_request_count": stale_request_count,
        "stale_gate_count": stale_gate_count,
        "stale_deferral_count": stale_deferral_count,
        "unresolved_denial_count_total": unresolved_denial_count_total,
        "renewal_required_count": renewal_required_count,
        "proof_refresh_required_count": proof_refresh_required_count,
        "dry_run_continuation_count": dry_run_continuation_count,
        "future_live_deferred_count": future_live_deferred_count,
        "blocker_count": blocker_count,
        "warning_count": warning_count,
        "scope_keys": scope_keys or ("household_presence_camera",),
        "safe_next_actions": tuple(actions),
        "forbidden_next_steps": FORBIDDEN_NEXT_STEPS,
        "capture_enabled": False,
        "capture_available": False,
        "live_hardware_enabled": False,
        "raw_media_storage_enabled": False,
        "no_live_capture_performed": True,
        "speaker_output_enabled": False,
        "external_disclosure_enabled": False,
        "summary_grants_operator_consent": False,
        "summary_renews_operator_grant": False,
        "summary_enables_live_capture": False,
        "summary_enables_live_hardware": False,
        "summary_enables_raw_media_storage": False,
        "summary_enables_speaker_output": False,
        "summary_enables_external_disclosure": False,
        "summary_confers_live_readiness": False,
        "summary_confers_capture_authorization": False,
        "summary_schedules_live_review": False,
        "summary_approves_live_candidate": False,
        "summary_executes_dry_run": False,
    }
    record = HouseholdCameraReviewChainSummaryRecord(**record_shell, digest=_digest(record_shell))
    packet_shell: dict[str, Any] = {"packet_id": str(payload.get("packet_id") or "household-presence-camera-review-chain-summary-packet"), "schema_version": "household_presence_camera_review_chain_summary_packet.v1", "records": [asdict(record)]}
    packet = HouseholdCameraReviewChainSummaryPacket(packet_id=str(packet_shell["packet_id"]), schema_version=str(packet_shell["schema_version"]), records=(record,), digest=_digest(packet_shell))
    final_status: SummaryStatus = "review_chain_summary_packet_ready_with_warnings" if warning_count else "review_chain_summary_packet_ready"
    counts = {
        "record_count": 1,
        "stale_review_count": stale_review_count,
        "stale_decision_count": stale_decision_count,
        "stale_trend_count": stale_trend_count,
        "stale_request_count": stale_request_count,
        "stale_gate_count": stale_gate_count,
        "stale_deferral_count": stale_deferral_count,
        "unresolved_denial_count_total": unresolved_denial_count_total,
        "renewal_required_count": renewal_required_count,
        "proof_refresh_required_count": proof_refresh_required_count,
        "dry_run_continuation_count": dry_run_continuation_count,
        "future_live_deferred_count": future_live_deferred_count,
        "blocker_count": blocker_count,
        "warning_count": warning_count,
    }
    report = HouseholdCameraReviewChainSummaryReport(final_status, counts, tuple(findings))
    return HouseholdCameraReviewChainSummaryResult(final_status, packet, report)
