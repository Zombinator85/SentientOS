from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any, Mapping, Sequence

from sentientos.context_hygiene.prompt_internal_candidate import (
    InternalPromptCandidate,
    InternalPromptCandidateStatus,
    compute_internal_prompt_candidate_digest,
    internal_prompt_candidate_has_no_runtime_authority,
    internal_prompt_candidate_has_no_tool_or_action_capability,
    internal_prompt_candidate_is_no_llm,
    internal_prompt_candidate_is_operator_visible_only,
)


class InternalPromptDisplayStatus:
    DISPLAY_ALLOWED = "display_allowed"
    DISPLAY_ALLOWED_WITH_WARNINGS = "display_allowed_with_warnings"
    DISPLAY_DENIED = "display_denied"
    DISPLAY_INVALID_CANDIDATE = "display_invalid_candidate"
    DISPLAY_DIGEST_MISMATCH = "display_digest_mismatch"
    DISPLAY_SCOPE_FORBIDDEN = "display_scope_forbidden"
    DISPLAY_RUNTIME_AUTHORITY_DETECTED = "display_runtime_authority_detected"
    DISPLAY_MODEL_EGRESS_FORBIDDEN = "display_model_egress_forbidden"


class InternalPromptDisplayScope:
    OPERATOR_INTERNAL_REVIEW = "operator_internal_review"
    OPERATOR_INTERNAL_DEBUG = "operator_internal_debug"
    AUDIT_REPLAY = "audit_replay"
    EXTERNAL_USER_VISIBLE_FORBIDDEN = "external_user_visible_forbidden"
    MODEL_PROVIDER_FORBIDDEN = "model_provider_forbidden"
    TOOL_OR_ACTION_FORBIDDEN = "tool_or_action_forbidden"


_ALLOWED_DISPLAY_SCOPES = frozenset(
    {
        InternalPromptDisplayScope.OPERATOR_INTERNAL_REVIEW,
        InternalPromptDisplayScope.OPERATOR_INTERNAL_DEBUG,
        InternalPromptDisplayScope.AUDIT_REPLAY,
    }
)

_READY_CANDIDATE_STATUSES = frozenset(
    {
        InternalPromptCandidateStatus.INTERNAL_PROMPT_CANDIDATE_READY,
        InternalPromptCandidateStatus.INTERNAL_PROMPT_CANDIDATE_READY_WITH_WARNINGS,
    }
)

_INVALID_CANDIDATE_STATUSES = frozenset(
    {
        InternalPromptCandidateStatus.INTERNAL_PROMPT_CANDIDATE_INVALID_INPUT,
    }
)

_DENIED_CANDIDATE_STATUSES = frozenset(
    {
        InternalPromptCandidateStatus.INTERNAL_PROMPT_CANDIDATE_BLOCKED,
        InternalPromptCandidateStatus.INTERNAL_PROMPT_CANDIDATE_POLICY_DENIED,
        InternalPromptCandidateStatus.INTERNAL_PROMPT_CANDIDATE_REVIEW_REQUIRED,
        InternalPromptCandidateStatus.INTERNAL_PROMPT_CANDIDATE_FORBIDDEN_RAW_CONTEXT,
        InternalPromptCandidateStatus.INTERNAL_PROMPT_CANDIDATE_LLM_FORBIDDEN,
    }
)

_RAW_TEXT_MARKERS = (
    "raw_payload",
    "raw_memory_payload",
    "raw_screen_payload",
    "raw_audio_payload",
    "raw_vision_payload",
    "raw_multimodal_payload",
    "screen_frame",
    "mic_audio",
    "audio_payload",
    "vision_frame",
    "multimodal_raw_data",
    "hidden_chain_of_thought",
    "chain_of_thought",
)
_RUNTIME_TEXT_MARKERS = (
    "execution_handle",
    "action_handle",
    "retention_handle",
    "retrieval_handle",
    "runtime_authority",
    "browser_handle",
    "mouse_handle",
    "keyboard_handle",
)
_PROVIDER_TEXT_MARKERS = (
    "llm_params",
    "llm_parameters",
    "model_params",
    "provider_params",
)
_RUNTIME_CAPABILITY_FIELDS = (
    "live_prompt_assembly",
    "live_model_call",
    "model_egress",
    "external_user_visible",
)


@dataclass(frozen=True)
class InternalPromptDisplayBoundary:
    internal_display_receipt_only: bool = True
    operator_visible_only: bool = True
    no_llm: bool = True
    model_egress: bool = False
    external_user_visible: bool = False
    live_prompt_assembly: bool = False
    live_model_call: bool = False
    does_not_call_llm: bool = True
    does_not_retrieve_memory: bool = True
    does_not_write_memory: bool = True
    does_not_trigger_feedback: bool = True
    does_not_commit_retention: bool = True
    does_not_execute_or_route_work: bool = True
    does_not_admit_work: bool = True
    no_tool_or_action_capability: bool = True


@dataclass(frozen=True)
class InternalPromptDisplayFinding:
    code: str
    detail: str
    severity: str = "blocker"


@dataclass(frozen=True)
class InternalPromptDisplayDecision:
    display_status: str
    findings: tuple[InternalPromptDisplayFinding, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    rationale: str = ""


@dataclass(frozen=True)
class InternalPromptDisplayReceipt:
    display_receipt_id: str
    display_status: str
    candidate_id: str
    candidate_status: str
    candidate_digest: str
    expected_candidate_digest: str
    digest_match: bool
    policy_decision_id: str
    policy_status: str
    policy_digest: str
    audit_receipt_id: str
    audit_receipt_digest: str
    review_receipt_id: str
    review_digest: str
    packet_id: str
    packet_scope: str
    display_scope: str
    operator_ref: str
    display_reason: str
    candidate_text_digest: str
    candidate_text_length: int
    text_included: bool
    text_redacted: bool
    expires_at: str
    expired: bool
    findings: tuple[InternalPromptDisplayFinding, ...]
    warnings: tuple[str, ...]
    rationale: str
    display_receipt_digest: str
    internal_display_receipt_only: bool = True
    operator_visible_only: bool = True
    no_llm: bool = True
    model_egress: bool = False
    external_user_visible: bool = False
    live_prompt_assembly: bool = False
    live_model_call: bool = False
    does_not_call_llm: bool = True
    does_not_retrieve_memory: bool = True
    does_not_write_memory: bool = True
    does_not_trigger_feedback: bool = True
    does_not_commit_retention: bool = True
    does_not_execute_or_route_work: bool = True
    does_not_admit_work: bool = True
    no_tool_or_action_capability: bool = True
    boundary: InternalPromptDisplayBoundary = field(default_factory=InternalPromptDisplayBoundary)


def _is_dataclass_instance(value: Any) -> bool:
    return is_dataclass(value) and not isinstance(value, type)


def _mapping(value: Any) -> Mapping[str, Any]:
    if _is_dataclass_instance(value):
        return asdict(value)
    if isinstance(value, Mapping):
        return value
    return {}


def _stable(value: Any) -> Any:
    if _is_dataclass_instance(value):
        return {key: _stable(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _stable(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (tuple, list)):
        return [_stable(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_stable(item) for item in value)
    return value


def _finding(code: str, detail: str, severity: str = "blocker") -> InternalPromptDisplayFinding:
    return InternalPromptDisplayFinding(code=code, detail=detail, severity=severity)


def _contains_any(text: str, markers: Sequence[str]) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in markers)


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _expired(expires_at: str) -> bool:
    parsed = _parse_time(expires_at)
    if parsed is None:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed <= datetime.now(timezone.utc)


def _expiry_value(*, expires_at: str | None, ttl_seconds: int | None) -> str:
    if expires_at:
        return str(expires_at)
    if ttl_seconds is None:
        return ""
    return (datetime.now(timezone.utc) + timedelta(seconds=int(ttl_seconds))).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _candidate_text_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _candidate_digest_is_stable(candidate: InternalPromptCandidate | Mapping[str, Any]) -> bool:
    data = _mapping(candidate)
    recorded = str(data.get("candidate_digest", ""))
    if not recorded:
        return False
    try:
        return compute_internal_prompt_candidate_digest(candidate) == recorded
    except Exception:
        return False


def _candidate_digest(candidate: InternalPromptCandidate | Mapping[str, Any]) -> str:
    return str(_mapping(candidate).get("candidate_digest", ""))


def internal_prompt_display_is_operator_only(receipt: InternalPromptDisplayReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(
        data.get("display_scope") in _ALLOWED_DISPLAY_SCOPES
        and data.get("operator_visible_only") is True
        and data.get("external_user_visible") is False
        and str(data.get("operator_ref", ""))
    )


def internal_prompt_display_has_no_model_egress(receipt: InternalPromptDisplayReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(
        data.get("no_llm") is True
        and data.get("model_egress") is False
        and data.get("live_model_call") is False
        and data.get("does_not_call_llm") is True
        and data.get("display_scope") != InternalPromptDisplayScope.MODEL_PROVIDER_FORBIDDEN
    )


def internal_prompt_display_has_no_runtime_authority(receipt: InternalPromptDisplayReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(
        data.get("live_prompt_assembly") is False
        and data.get("live_model_call") is False
        and data.get("does_not_retrieve_memory") is True
        and data.get("does_not_write_memory") is True
        and data.get("does_not_trigger_feedback") is True
        and data.get("does_not_commit_retention") is True
        and data.get("does_not_execute_or_route_work") is True
        and data.get("does_not_admit_work") is True
        and data.get("no_tool_or_action_capability") is True
    )


def internal_prompt_display_preserves_candidate_digest(
    receipt: InternalPromptDisplayReceipt | Mapping[str, Any],
    candidate: InternalPromptCandidate | Mapping[str, Any] | None = None,
) -> bool:
    data = _mapping(receipt)
    expected = str(data.get("expected_candidate_digest", ""))
    recorded = str(data.get("candidate_digest", ""))
    if expected and expected != recorded:
        return False
    if data.get("digest_match") is not True:
        return False
    if candidate is not None and _candidate_digest(candidate) != recorded:
        return False
    return bool(recorded)


def _text_marker_findings(text: str) -> tuple[InternalPromptDisplayFinding, ...]:
    findings: list[InternalPromptDisplayFinding] = []
    lowered = text.lower()
    if _contains_any(text, _RAW_TEXT_MARKERS):
        findings.append(_finding("candidate_text_raw_payload_marker", "candidate text contains raw payload marker"))
    if _contains_any(text, _RUNTIME_TEXT_MARKERS):
        findings.append(_finding("candidate_text_runtime_handle_marker", "candidate text contains runtime handle marker"))
    if _contains_any(text, _PROVIDER_TEXT_MARKERS):
        findings.append(_finding("candidate_text_provider_marker", "candidate text contains LLM/provider parameter marker"))
    if "internal no-llm candidate" not in lowered:
        findings.append(_finding("missing_internal_no_llm_marker", "candidate text must retain internal no-LLM marker"))
    if "not been sent to a model" not in lowered and "not sent to model" not in lowered:
        findings.append(_finding("missing_not_sent_to_model_marker", "candidate text must state it was not sent to a model"))
    if "operator visible only" not in lowered:
        findings.append(_finding("missing_operator_visible_only_marker", "candidate text must retain operator-visible-only marker"))
    return tuple(findings)


def _display_findings(
    candidate: InternalPromptCandidate | Mapping[str, Any],
    *,
    display_scope: str,
    operator_ref: str,
    expected_candidate_digest: str,
    expires_at: str,
) -> tuple[InternalPromptDisplayFinding, ...]:
    data = _mapping(candidate)
    findings: list[InternalPromptDisplayFinding] = []
    status = str(data.get("status", ""))
    recorded_digest = str(data.get("candidate_digest", ""))
    if not data:
        return (_finding("candidate_missing", "InternalPromptCandidate is required"),)
    if status in _INVALID_CANDIDATE_STATUSES or not status:
        findings.append(_finding("candidate_invalid", "candidate status is invalid or missing"))
    elif status not in _READY_CANDIDATE_STATUSES:
        findings.append(_finding("candidate_not_display_ready", f"candidate status {status!r} cannot be displayed"))
    if status in _DENIED_CANDIDATE_STATUSES:
        findings.append(_finding("candidate_upstream_denial", "candidate is blocked, denied, review-required, or otherwise upstream-denied"))
    if display_scope == InternalPromptDisplayScope.MODEL_PROVIDER_FORBIDDEN:
        findings.append(_finding("model_provider_scope_forbidden", "model/provider display egress is forbidden"))
    elif display_scope not in _ALLOWED_DISPLAY_SCOPES:
        findings.append(_finding("display_scope_forbidden", "display scope is not internal/operator-only or audit replay"))
    if not operator_ref:
        findings.append(_finding("operator_ref_missing", "operator_ref is required before internal display egress"))
    if expires_at and _expired(expires_at):
        findings.append(_finding("display_receipt_expired", "display receipt has expired"))
    if not _candidate_digest_is_stable(candidate):
        findings.append(_finding("candidate_digest_unstable", "candidate digest is missing or no longer matches candidate contents"))
    if expected_candidate_digest and expected_candidate_digest != recorded_digest:
        findings.append(_finding("candidate_digest_mismatch", "expected candidate digest does not match candidate digest"))
    if not internal_prompt_candidate_is_operator_visible_only(candidate):
        findings.append(_finding("candidate_not_operator_visible_only", "candidate must be internal-only and operator-visible-only"))
    if not internal_prompt_candidate_is_no_llm(candidate):
        findings.append(_finding("candidate_llm_boundary_missing", "candidate must be no-LLM and non-model-call"))
    if not internal_prompt_candidate_has_no_runtime_authority(candidate):
        findings.append(_finding("candidate_runtime_authority_detected", "candidate has runtime authority or runtime handle markers"))
    if not internal_prompt_candidate_has_no_tool_or_action_capability(candidate):
        findings.append(_finding("candidate_tool_or_action_capability", "candidate has tool/action/memory/retention/routing capability"))
    for field_name in _RUNTIME_CAPABILITY_FIELDS:
        if bool(data.get(field_name, False)):
            findings.append(_finding("candidate_runtime_authority_detected", f"candidate field {field_name} enables forbidden runtime authority"))
    text = str(data.get("internal_candidate_text", ""))
    findings.extend(_text_marker_findings(text))
    return tuple(findings)


def _status_for_findings(candidate_status: str, display_scope: str, findings: Sequence[InternalPromptDisplayFinding]) -> str:
    codes = {finding.code for finding in findings}
    if "candidate_invalid" in codes or "candidate_missing" in codes:
        return InternalPromptDisplayStatus.DISPLAY_INVALID_CANDIDATE
    if "candidate_digest_mismatch" in codes or "candidate_digest_unstable" in codes:
        return InternalPromptDisplayStatus.DISPLAY_DIGEST_MISMATCH
    if "model_provider_scope_forbidden" in codes:
        return InternalPromptDisplayStatus.DISPLAY_MODEL_EGRESS_FORBIDDEN
    if "candidate_runtime_authority_detected" in codes or display_scope == InternalPromptDisplayScope.TOOL_OR_ACTION_FORBIDDEN:
        return InternalPromptDisplayStatus.DISPLAY_RUNTIME_AUTHORITY_DETECTED
    if "display_scope_forbidden" in codes:
        return InternalPromptDisplayStatus.DISPLAY_SCOPE_FORBIDDEN
    if findings:
        return InternalPromptDisplayStatus.DISPLAY_DENIED
    if candidate_status == InternalPromptCandidateStatus.INTERNAL_PROMPT_CANDIDATE_READY_WITH_WARNINGS:
        return InternalPromptDisplayStatus.DISPLAY_ALLOWED_WITH_WARNINGS
    return InternalPromptDisplayStatus.DISPLAY_ALLOWED


def compute_internal_prompt_display_receipt_digest(receipt: InternalPromptDisplayReceipt | Mapping[str, Any]) -> str:
    data = dict(_mapping(receipt))
    data.pop("display_receipt_digest", None)
    data.pop("display_receipt_id", None)
    encoded = json.dumps(_stable(data), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_internal_prompt_display_receipt(
    candidate: InternalPromptCandidate | Mapping[str, Any],
    *,
    display_scope: str,
    operator_ref: str,
    display_reason: str = "",
    expected_candidate_digest: str | None = None,
    expires_at: str | None = None,
    ttl_seconds: int | None = None,
    include_text_digest_only: bool = True,
) -> InternalPromptDisplayReceipt:
    data = _mapping(candidate)
    scope = str(display_scope)
    operator = str(operator_ref)
    expected_digest = str(expected_candidate_digest or "")
    expiry = _expiry_value(expires_at=expires_at, ttl_seconds=ttl_seconds)
    text = str(data.get("internal_candidate_text", ""))
    text_digest = _candidate_text_digest(text)
    findings = _display_findings(
        candidate,
        display_scope=scope,
        operator_ref=operator,
        expected_candidate_digest=expected_digest,
        expires_at=expiry,
    )
    candidate_status = str(data.get("status", ""))
    display_status = _status_for_findings(candidate_status, scope, findings)
    warnings = tuple(str(item) for item in data.get("warnings", ()) or ())
    rationale = "; ".join(f"{finding.code}: {finding.detail}" for finding in findings[:4]) or "internal operator display egress gates satisfied"
    receipt = InternalPromptDisplayReceipt(
        display_receipt_id="",
        display_status=display_status,
        candidate_id=str(data.get("candidate_id", "")),
        candidate_status=candidate_status,
        candidate_digest=str(data.get("candidate_digest", "")),
        expected_candidate_digest=expected_digest,
        digest_match=bool(not expected_digest or expected_digest == str(data.get("candidate_digest", ""))),
        policy_decision_id=str(data.get("policy_decision_id", "")),
        policy_status=str(data.get("policy_status", "")),
        policy_digest=str(data.get("policy_digest", "")),
        audit_receipt_id=str(data.get("audit_receipt_id", "")),
        audit_receipt_digest=str(data.get("audit_receipt_digest", "")),
        review_receipt_id=str(data.get("review_receipt_id", "")),
        review_digest=str(data.get("review_digest", "")),
        packet_id=str(data.get("packet_id", "")),
        packet_scope=str(data.get("packet_scope", "")),
        display_scope=scope,
        operator_ref=operator,
        display_reason=str(display_reason),
        candidate_text_digest=text_digest,
        candidate_text_length=len(text),
        text_included=False if include_text_digest_only else False,
        text_redacted=True,
        expires_at=expiry,
        expired=_expired(expiry),
        findings=tuple(findings),
        warnings=warnings,
        rationale=rationale,
        display_receipt_digest="",
    )
    digest = compute_internal_prompt_display_receipt_digest(receipt)
    return replace(receipt, display_receipt_id=f"internal-prompt-display:{receipt.candidate_id or 'missing'}:{digest[:16]}", display_receipt_digest=digest)


def validate_internal_prompt_display_receipt(
    receipt: InternalPromptDisplayReceipt | Mapping[str, Any],
    candidate: InternalPromptCandidate | Mapping[str, Any] | None = None,
) -> tuple[InternalPromptDisplayFinding, ...]:
    data = _mapping(receipt)
    findings: list[InternalPromptDisplayFinding] = []
    if not data:
        return (_finding("display_receipt_missing", "display receipt is required"),)
    recorded = str(data.get("display_receipt_digest", ""))
    if not recorded or compute_internal_prompt_display_receipt_digest(receipt) != recorded:
        findings.append(_finding("display_receipt_digest_mismatch", "display receipt digest is missing or unstable"))
    if data.get("display_status") not in {
        InternalPromptDisplayStatus.DISPLAY_ALLOWED,
        InternalPromptDisplayStatus.DISPLAY_ALLOWED_WITH_WARNINGS,
        InternalPromptDisplayStatus.DISPLAY_DENIED,
        InternalPromptDisplayStatus.DISPLAY_INVALID_CANDIDATE,
        InternalPromptDisplayStatus.DISPLAY_DIGEST_MISMATCH,
        InternalPromptDisplayStatus.DISPLAY_SCOPE_FORBIDDEN,
        InternalPromptDisplayStatus.DISPLAY_RUNTIME_AUTHORITY_DETECTED,
        InternalPromptDisplayStatus.DISPLAY_MODEL_EGRESS_FORBIDDEN,
    }:
        findings.append(_finding("display_status_unknown", "display status is unknown"))
    if data.get("expired") is True or _expired(str(data.get("expires_at", ""))):
        findings.append(_finding("display_receipt_expired", "display receipt has expired"))
    if not internal_prompt_display_is_operator_only(receipt):
        findings.append(_finding("display_not_operator_only", "receipt is not limited to internal operator/audit display"))
    if not internal_prompt_display_has_no_model_egress(receipt):
        findings.append(_finding("display_model_egress_detected", "receipt permits forbidden model egress"))
    if not internal_prompt_display_has_no_runtime_authority(receipt):
        findings.append(_finding("display_runtime_authority_detected", "receipt permits runtime authority"))
    if not internal_prompt_display_preserves_candidate_digest(receipt, candidate):
        findings.append(_finding("display_candidate_digest_not_preserved", "candidate digest linkage is not preserved"))
    if candidate is not None:
        text = str(_mapping(candidate).get("internal_candidate_text", ""))
        if str(data.get("candidate_text_digest", "")) != _candidate_text_digest(text):
            findings.append(_finding("display_text_digest_mismatch", "candidate text digest no longer matches candidate text"))
        if int(data.get("candidate_text_length", -1)) != len(text):
            findings.append(_finding("display_text_length_mismatch", "candidate text length no longer matches candidate text"))
    return tuple(findings)


def internal_prompt_candidate_may_be_displayed(
    receipt: InternalPromptDisplayReceipt | Mapping[str, Any],
    candidate: InternalPromptCandidate | Mapping[str, Any] | None = None,
) -> bool:
    data = _mapping(receipt)
    return bool(
        data.get("display_status")
        in {
            InternalPromptDisplayStatus.DISPLAY_ALLOWED,
            InternalPromptDisplayStatus.DISPLAY_ALLOWED_WITH_WARNINGS,
        }
        and data.get("candidate_status") in _READY_CANDIDATE_STATUSES
        and not validate_internal_prompt_display_receipt(receipt, candidate)
    )


def explain_internal_prompt_display_findings(
    receipt_or_findings: InternalPromptDisplayReceipt | Mapping[str, Any] | Sequence[InternalPromptDisplayFinding],
) -> tuple[str, ...]:
    if isinstance(receipt_or_findings, Sequence) and not isinstance(receipt_or_findings, (str, bytes, Mapping)):
        findings = tuple(receipt_or_findings)
    else:
        findings = tuple(_mapping(receipt_or_findings).get("findings", ()) or ())
    return tuple(f"{_mapping(finding).get('severity', '')}:{_mapping(finding).get('code', '')}:{_mapping(finding).get('detail', '')}" for finding in findings)


def summarize_internal_prompt_display_receipt(receipt: InternalPromptDisplayReceipt | Mapping[str, Any]) -> Mapping[str, Any]:
    data = _mapping(receipt)
    return {
        "display_receipt_id": str(data.get("display_receipt_id", "")),
        "display_status": str(data.get("display_status", "")),
        "candidate_id": str(data.get("candidate_id", "")),
        "candidate_status": str(data.get("candidate_status", "")),
        "candidate_digest": str(data.get("candidate_digest", "")),
        "digest_match": bool(data.get("digest_match", False)),
        "policy_decision_id": str(data.get("policy_decision_id", "")),
        "audit_receipt_id": str(data.get("audit_receipt_id", "")),
        "review_receipt_id": str(data.get("review_receipt_id", "")),
        "packet_id": str(data.get("packet_id", "")),
        "packet_scope": str(data.get("packet_scope", "")),
        "display_scope": str(data.get("display_scope", "")),
        "operator_ref": str(data.get("operator_ref", "")),
        "candidate_text_digest": str(data.get("candidate_text_digest", "")),
        "candidate_text_length": int(data.get("candidate_text_length", 0)),
        "text_included": bool(data.get("text_included", False)),
        "text_redacted": bool(data.get("text_redacted", False)),
        "finding_count": len(tuple(data.get("findings", ()) or ())),
        "display_receipt_digest": str(data.get("display_receipt_digest", "")),
        "model_egress": bool(data.get("model_egress", True)),
        "live_prompt_assembly": bool(data.get("live_prompt_assembly", True)),
        "live_model_call": bool(data.get("live_model_call", True)),
    }
