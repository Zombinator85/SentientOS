from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any, Mapping, Sequence

from sentientos.context_hygiene.prompt_materialization_policy import (
    PromptMaterializationPolicyDecision,
    PromptMaterializationPolicyRing,
    PromptMaterializationPolicyStatus,
    policy_decision_denies_materialization,
    policy_decision_requires_operator_review,
)


class PromptOperatorReviewStatus:
    REVIEW_ACCEPTED = "review_accepted"
    REVIEW_REJECTED = "review_rejected"
    REVIEW_PARTIALLY_ACCEPTED = "review_partially_accepted"
    REVIEW_EXPIRED = "review_expired"
    REVIEW_INVALID = "review_invalid"
    REVIEW_FORBIDDEN_OVERRIDE_ATTEMPTED = "review_forbidden_override_attempted"
    REVIEW_NOT_APPLICABLE = "review_not_applicable"


class PromptOperatorReviewDecision:
    ACCEPT_REQUIRED_WARNINGS = "accept_required_warnings"
    REJECT_REQUIRED_WARNINGS = "reject_required_warnings"
    ACCEPT_REQUIRED_CAVEATS = "accept_required_caveats"
    REJECT_REQUIRED_CAVEATS = "reject_required_caveats"
    ACCEPT_SYNTHETIC_FIXTURE_ONLY = "accept_synthetic_fixture_only"
    REJECT_SYNTHETIC_FIXTURE = "reject_synthetic_fixture"
    REQUEST_MORE_EVIDENCE = "request_more_evidence"
    NO_DECISION = "no_decision"


@dataclass(frozen=True)
class PromptOperatorReviewFinding:
    code: str
    detail: str
    severity: str = "blocker"


@dataclass(frozen=True)
class PromptOperatorReviewScope:
    scope_id: str = "synthetic_fixture_review"
    review_required_warnings_only: bool = True
    review_required_caveats_only: bool = True
    synthetic_fixture_only: bool = True
    grants_runtime_authority: bool = False


@dataclass(frozen=True)
class PromptOperatorReviewBoundary:
    operator_review_receipt_only: bool = True
    policy_review_support_only: bool = True
    prompt_materialization_precondition_only: bool = True
    does_not_materialize_prompt_text: bool = True
    does_not_assemble_prompt: bool = True
    does_not_contain_final_prompt_text: bool = True
    does_not_call_llm: bool = True
    does_not_retrieve_memory: bool = True
    does_not_write_memory: bool = True
    does_not_trigger_feedback: bool = True
    does_not_commit_retention: bool = True
    does_not_execute_or_route_work: bool = True
    does_not_admit_work: bool = True


@dataclass(frozen=True)
class PromptOperatorReviewExpiration:
    reviewed_at: str = ""
    expires_at: str = ""
    ttl_seconds: int = 0
    evaluated_at: str = ""


@dataclass(frozen=True)
class PromptOperatorReviewReceipt:
    review_receipt_id: str
    review_status: str
    policy_decision_id: str
    policy_status: str
    policy_digest: str
    requested_ring: str
    effective_ring: str
    receipt_id: str
    audit_receipt_digest: str
    packet_id: str
    packet_scope: str
    reviewer_ref: str
    review_scope: PromptOperatorReviewScope
    decisions: tuple[str, ...]
    accepted_warning_codes: tuple[str, ...]
    rejected_warning_codes: tuple[str, ...]
    accepted_caveat_codes: tuple[str, ...]
    rejected_caveat_codes: tuple[str, ...]
    required_warning_codes: tuple[str, ...]
    required_caveat_codes: tuple[str, ...]
    expiration: PromptOperatorReviewExpiration
    expired: bool
    forbidden_override_attempted: bool
    findings: tuple[PromptOperatorReviewFinding, ...]
    rationale: str
    review_digest: str
    operator_review_receipt_only: bool = True
    does_not_materialize_prompt_text: bool = True
    does_not_assemble_prompt: bool = True
    does_not_contain_final_prompt_text: bool = True
    does_not_call_llm: bool = True
    does_not_retrieve_memory: bool = True
    does_not_write_memory: bool = True
    does_not_trigger_feedback: bool = True
    does_not_commit_retention: bool = True
    does_not_execute_or_route_work: bool = True
    does_not_admit_work: bool = True
    boundary: PromptOperatorReviewBoundary = field(default_factory=PromptOperatorReviewBoundary)


_ALLOWED_DECISIONS = frozenset(
    {
        PromptOperatorReviewDecision.ACCEPT_REQUIRED_WARNINGS,
        PromptOperatorReviewDecision.REJECT_REQUIRED_WARNINGS,
        PromptOperatorReviewDecision.ACCEPT_REQUIRED_CAVEATS,
        PromptOperatorReviewDecision.REJECT_REQUIRED_CAVEATS,
        PromptOperatorReviewDecision.ACCEPT_SYNTHETIC_FIXTURE_ONLY,
        PromptOperatorReviewDecision.REJECT_SYNTHETIC_FIXTURE,
        PromptOperatorReviewDecision.REQUEST_MORE_EVIDENCE,
        PromptOperatorReviewDecision.NO_DECISION,
    }
)
_ACCEPT_DECISIONS = frozenset(
    {
        PromptOperatorReviewDecision.ACCEPT_REQUIRED_WARNINGS,
        PromptOperatorReviewDecision.ACCEPT_REQUIRED_CAVEATS,
        PromptOperatorReviewDecision.ACCEPT_SYNTHETIC_FIXTURE_ONLY,
    }
)
_REJECT_DECISIONS = frozenset(
    {
        PromptOperatorReviewDecision.REJECT_REQUIRED_WARNINGS,
        PromptOperatorReviewDecision.REJECT_REQUIRED_CAVEATS,
        PromptOperatorReviewDecision.REJECT_SYNTHETIC_FIXTURE,
        PromptOperatorReviewDecision.REQUEST_MORE_EVIDENCE,
    }
)
_NON_RUNTIME_MARKERS = (
    "operator_review_receipt_only",
    "does_not_materialize_prompt_text",
    "does_not_assemble_prompt",
    "does_not_contain_final_prompt_text",
    "does_not_call_llm",
    "does_not_retrieve_memory",
    "does_not_write_memory",
    "does_not_trigger_feedback",
    "does_not_commit_retention",
    "does_not_execute_or_route_work",
    "does_not_admit_work",
)
_FORBIDDEN_POLICY_STATUSES = frozenset(
    {
        PromptMaterializationPolicyStatus.POLICY_DENY,
        PromptMaterializationPolicyStatus.POLICY_INVALID_INPUT,
        PromptMaterializationPolicyStatus.POLICY_RUNTIME_WIRING_DETECTED,
    }
)
_FORBIDDEN_RINGS = frozenset(
    {
        PromptMaterializationPolicyRing.RING_LIVE_LLM_FORBIDDEN,
    }
)
_HARD_DENIAL_REASON_CODES = frozenset(
    {
        "missing_audit_receipt",
        "audit_runtime_wiring_detected",
        "audit_status_not_ready",
        "audit_disallows_shadow_materializer",
        "digest_chain_incomplete",
        "chain_status_not_ready",
        "unknown_policy_ring",
        "phase77_ring_forbidden",
        "forbidden_prompt_marker",
        "forbidden_raw_marker",
        "runtime_authority_marker",
        "violations_present",
        "blocking_findings_present",
        "unknown_source_kind",
        "synthetic_fixture_required",
        "malformed_policy_input",
    }
)


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
        return {k: _stable(v) for k, v in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(k): _stable(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (tuple, list)):
        return [_stable(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_stable(v) for v in value)
    return value


def _tuple_str(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, (tuple, list, set, frozenset)):
        return tuple(sorted({str(item) for item in value if str(item)}))
    return ()


def _compact_rationale(value: str, *, limit: int = 240) -> str:
    compact = " ".join(str(value or "").split())
    return compact[:limit]


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _format_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _build_expiration(*, expires_at: str = "", ttl_seconds: int | None = None, reviewed_at: str = "", evaluated_at: str = "") -> PromptOperatorReviewExpiration:
    ttl = int(ttl_seconds or 0)
    resolved_expires_at = str(expires_at or "")
    if not resolved_expires_at and ttl > 0:
        base = _parse_time(reviewed_at) or datetime(1970, 1, 1, tzinfo=timezone.utc)
        resolved_expires_at = _format_time(base + timedelta(seconds=ttl))
    return PromptOperatorReviewExpiration(reviewed_at=str(reviewed_at or ""), expires_at=resolved_expires_at, ttl_seconds=ttl, evaluated_at=str(evaluated_at or ""))


def _is_expired(expiration: PromptOperatorReviewExpiration) -> bool:
    expires = _parse_time(expiration.expires_at)
    evaluated = _parse_time(expiration.evaluated_at)
    return bool(expires and evaluated and evaluated >= expires)


def _reason_codes(policy_decision: PromptMaterializationPolicyDecision | Mapping[str, Any]) -> tuple[str, ...]:
    data = _mapping(policy_decision)
    return tuple(str(_mapping(reason).get("code", "")) for reason in data.get("reasons", ()) or () if str(_mapping(reason).get("code", "")))


def _review_base_code(policy_decision: PromptMaterializationPolicyDecision | Mapping[str, Any]) -> str:
    data = _mapping(policy_decision)
    review_codes: list[str] = []
    for reason in data.get("reasons", ()) or ():
        item = _mapping(reason)
        code = str(item.get("code", ""))
        detail = str(item.get("detail", "")).lower()
        severity = str(item.get("severity", "")).lower()
        if code and (severity == "review" or "review" in detail or "operator" in code):
            review_codes.append(code)
    for mitigation in data.get("required_mitigations", ()) or ():
        item = _mapping(mitigation)
        code = str(item.get("code", ""))
        detail = str(item.get("detail", "")).lower()
        if code and ("review" in code or "review" in detail or "operator" in detail):
            review_codes.append(code)
    return sorted(set(review_codes))[0] if review_codes else "operator_review_required"


def extract_required_operator_review_warning_codes(policy_decision: PromptMaterializationPolicyDecision | Mapping[str, Any]) -> tuple[str, ...]:
    data = _mapping(policy_decision)
    if not policy_decision_requires_operator_review(policy_decision):
        return ()
    count = int(data.get("warning_count", 0) or 0)
    base = _review_base_code(policy_decision)
    if count <= 0 and int(data.get("caveat_count", 0) or 0) <= 0:
        count = 1
    return tuple(f"warning:{base}:{index}" for index in range(1, count + 1))


def extract_required_operator_review_caveat_codes(policy_decision: PromptMaterializationPolicyDecision | Mapping[str, Any]) -> tuple[str, ...]:
    data = _mapping(policy_decision)
    if not policy_decision_requires_operator_review(policy_decision):
        return ()
    count = int(data.get("caveat_count", 0) or 0)
    base = _review_base_code(policy_decision)
    return tuple(f"caveat:{base}:{index}" for index in range(1, count + 1))


def _has_acceptance(decisions: Sequence[str], accepted_warning_codes: Sequence[str], accepted_caveat_codes: Sequence[str]) -> bool:
    return bool(set(decisions) & _ACCEPT_DECISIONS or accepted_warning_codes or accepted_caveat_codes)


def operator_review_attempts_forbidden_override(policy_decision: PromptMaterializationPolicyDecision | Mapping[str, Any], review_receipt: PromptOperatorReviewReceipt | Mapping[str, Any] | None = None) -> bool:
    data = _mapping(policy_decision)
    review_data = _mapping(review_receipt)
    decisions = _tuple_str(review_data.get("decisions", ())) if review_data else ()
    accepted_warning_codes = _tuple_str(review_data.get("accepted_warning_codes", ())) if review_data else ()
    accepted_caveat_codes = _tuple_str(review_data.get("accepted_caveat_codes", ())) if review_data else ()
    if not review_data:
        decisions = (PromptOperatorReviewDecision.ACCEPT_REQUIRED_WARNINGS, PromptOperatorReviewDecision.ACCEPT_REQUIRED_CAVEATS)
    tries_acceptance = _has_acceptance(decisions, accepted_warning_codes, accepted_caveat_codes)
    if not tries_acceptance:
        return False
    if str(data.get("policy_status", "")) in _FORBIDDEN_POLICY_STATUSES or policy_decision_denies_materialization(policy_decision):
        return True
    if str(data.get("requested_ring", "")) in _FORBIDDEN_RINGS or str(data.get("effective_ring", "")) in _FORBIDDEN_RINGS:
        return True
    return bool(set(_reason_codes(policy_decision)) & _HARD_DENIAL_REASON_CODES)


def _make_findings(
    policy_decision: PromptMaterializationPolicyDecision | Mapping[str, Any],
    *,
    reviewer_ref: str,
    decisions: Sequence[str],
    accepted_warning_codes: Sequence[str],
    rejected_warning_codes: Sequence[str],
    accepted_caveat_codes: Sequence[str],
    rejected_caveat_codes: Sequence[str],
    required_warning_codes: Sequence[str],
    required_caveat_codes: Sequence[str],
    expired: bool,
) -> tuple[PromptOperatorReviewFinding, ...]:
    findings: list[PromptOperatorReviewFinding] = []
    if not reviewer_ref:
        findings.append(PromptOperatorReviewFinding("reviewer_ref_missing", "reviewer_ref is required for operator review", "blocker"))
    unknown = tuple(decision for decision in decisions if decision not in _ALLOWED_DECISIONS)
    if unknown:
        findings.append(PromptOperatorReviewFinding("unknown_review_decision", f"unknown review decision(s): {','.join(unknown)}", "blocker"))
    if expired:
        findings.append(PromptOperatorReviewFinding("review_expired", "operator review receipt is expired", "blocker"))
    if operator_review_attempts_forbidden_override(policy_decision, {"decisions": decisions, "accepted_warning_codes": accepted_warning_codes, "accepted_caveat_codes": accepted_caveat_codes}):
        findings.append(PromptOperatorReviewFinding("forbidden_override_attempted", "operator review cannot override hard policy denial or runtime authority", "blocker"))
    missing_warnings = tuple(code for code in required_warning_codes if code not in accepted_warning_codes)
    missing_caveats = tuple(code for code in required_caveat_codes if code not in accepted_caveat_codes)
    if missing_warnings:
        findings.append(PromptOperatorReviewFinding("required_warning_not_accepted", f"missing accepted warning code(s): {','.join(missing_warnings)}", "review"))
    if missing_caveats:
        findings.append(PromptOperatorReviewFinding("required_caveat_not_accepted", f"missing accepted caveat code(s): {','.join(missing_caveats)}", "review"))
    if rejected_warning_codes:
        findings.append(PromptOperatorReviewFinding("required_warning_rejected", f"rejected warning code(s): {','.join(rejected_warning_codes)}", "review"))
    if rejected_caveat_codes:
        findings.append(PromptOperatorReviewFinding("required_caveat_rejected", f"rejected caveat code(s): {','.join(rejected_caveat_codes)}", "review"))
    if not policy_decision_requires_operator_review(policy_decision):
        findings.append(PromptOperatorReviewFinding("operator_review_not_applicable", "policy decision does not require operator review", "info"))
    return tuple(findings)


def _status_for(
    policy_decision: PromptMaterializationPolicyDecision | Mapping[str, Any],
    *,
    reviewer_ref: str,
    decisions: Sequence[str],
    accepted_warning_codes: Sequence[str],
    accepted_caveat_codes: Sequence[str],
    required_warning_codes: Sequence[str],
    required_caveat_codes: Sequence[str],
    expired: bool,
    forbidden_override_attempted: bool,
) -> str:
    if expired:
        return PromptOperatorReviewStatus.REVIEW_EXPIRED
    if not reviewer_ref or any(decision not in _ALLOWED_DECISIONS for decision in decisions):
        return PromptOperatorReviewStatus.REVIEW_INVALID
    if forbidden_override_attempted:
        return PromptOperatorReviewStatus.REVIEW_FORBIDDEN_OVERRIDE_ATTEMPTED
    if not policy_decision_requires_operator_review(policy_decision):
        return PromptOperatorReviewStatus.REVIEW_NOT_APPLICABLE
    if set(decisions) & _REJECT_DECISIONS:
        return PromptOperatorReviewStatus.REVIEW_REJECTED
    accepted_required_warnings = set(required_warning_codes).issubset(set(accepted_warning_codes))
    accepted_required_caveats = set(required_caveat_codes).issubset(set(accepted_caveat_codes))
    if accepted_required_warnings and accepted_required_caveats:
        return PromptOperatorReviewStatus.REVIEW_ACCEPTED
    if set(accepted_warning_codes) & set(required_warning_codes) or set(accepted_caveat_codes) & set(required_caveat_codes):
        return PromptOperatorReviewStatus.REVIEW_PARTIALLY_ACCEPTED
    return PromptOperatorReviewStatus.REVIEW_REJECTED


def compute_prompt_operator_review_digest(receipt: PromptOperatorReviewReceipt | Mapping[str, Any]) -> str:
    data = dict(_mapping(receipt))
    data.pop("review_digest", None)
    data.pop("review_receipt_id", None)
    payload = {
        "review_status": data.get("review_status", ""),
        "policy_decision_id": data.get("policy_decision_id", ""),
        "policy_status": data.get("policy_status", ""),
        "policy_digest": data.get("policy_digest", ""),
        "requested_ring": data.get("requested_ring", ""),
        "effective_ring": data.get("effective_ring", ""),
        "receipt_id": data.get("receipt_id", ""),
        "audit_receipt_digest": data.get("audit_receipt_digest", ""),
        "packet_id": data.get("packet_id", ""),
        "packet_scope": data.get("packet_scope", ""),
        "reviewer_ref": data.get("reviewer_ref", ""),
        "review_scope": _stable(data.get("review_scope", {})),
        "decisions": _stable(data.get("decisions", ())),
        "accepted_warning_codes": _stable(data.get("accepted_warning_codes", ())),
        "rejected_warning_codes": _stable(data.get("rejected_warning_codes", ())),
        "accepted_caveat_codes": _stable(data.get("accepted_caveat_codes", ())),
        "rejected_caveat_codes": _stable(data.get("rejected_caveat_codes", ())),
        "required_warning_codes": _stable(data.get("required_warning_codes", ())),
        "required_caveat_codes": _stable(data.get("required_caveat_codes", ())),
        "expiration": _stable(data.get("expiration", {})),
        "expired": bool(data.get("expired", False)),
        "forbidden_override_attempted": bool(data.get("forbidden_override_attempted", False)),
        "findings": _stable(data.get("findings", ())),
        "rationale": data.get("rationale", ""),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_prompt_operator_review_receipt(
    policy_decision: PromptMaterializationPolicyDecision | Mapping[str, Any],
    *,
    reviewer_ref: str = "",
    reviewer_id: str = "",
    decisions: Sequence[str] = (PromptOperatorReviewDecision.NO_DECISION,),
    accepted_warning_codes: Sequence[str] = (),
    rejected_warning_codes: Sequence[str] = (),
    accepted_caveat_codes: Sequence[str] = (),
    rejected_caveat_codes: Sequence[str] = (),
    review_scope: PromptOperatorReviewScope | Mapping[str, Any] | None = None,
    expires_at: str = "",
    ttl_seconds: int | None = None,
    reviewed_at: str = "",
    evaluated_at: str = "",
    rationale: str = "",
) -> PromptOperatorReviewReceipt:
    data = _mapping(policy_decision)
    reviewer = str(reviewer_ref or reviewer_id or "")
    normalized_decisions = _tuple_str(decisions) or (PromptOperatorReviewDecision.NO_DECISION,)
    normalized_accepted_warning_codes = _tuple_str(accepted_warning_codes)
    normalized_rejected_warning_codes = _tuple_str(rejected_warning_codes)
    normalized_accepted_caveat_codes = _tuple_str(accepted_caveat_codes)
    normalized_rejected_caveat_codes = _tuple_str(rejected_caveat_codes)
    required_warning_codes = extract_required_operator_review_warning_codes(policy_decision)
    required_caveat_codes = extract_required_operator_review_caveat_codes(policy_decision)
    scope_data = _mapping(review_scope)
    scope = review_scope if isinstance(review_scope, PromptOperatorReviewScope) else PromptOperatorReviewScope(**scope_data) if scope_data else PromptOperatorReviewScope()
    expiration = _build_expiration(expires_at=expires_at, ttl_seconds=ttl_seconds, reviewed_at=reviewed_at, evaluated_at=evaluated_at)
    expired = _is_expired(expiration)
    forbidden_override_attempted = operator_review_attempts_forbidden_override(
        policy_decision,
        {
            "decisions": normalized_decisions,
            "accepted_warning_codes": normalized_accepted_warning_codes,
            "accepted_caveat_codes": normalized_accepted_caveat_codes,
        },
    )
    findings = _make_findings(
        policy_decision,
        reviewer_ref=reviewer,
        decisions=normalized_decisions,
        accepted_warning_codes=normalized_accepted_warning_codes,
        rejected_warning_codes=normalized_rejected_warning_codes,
        accepted_caveat_codes=normalized_accepted_caveat_codes,
        rejected_caveat_codes=normalized_rejected_caveat_codes,
        required_warning_codes=required_warning_codes,
        required_caveat_codes=required_caveat_codes,
        expired=expired,
    )
    status = _status_for(
        policy_decision,
        reviewer_ref=reviewer,
        decisions=normalized_decisions,
        accepted_warning_codes=normalized_accepted_warning_codes,
        accepted_caveat_codes=normalized_accepted_caveat_codes,
        required_warning_codes=required_warning_codes,
        required_caveat_codes=required_caveat_codes,
        expired=expired,
        forbidden_override_attempted=forbidden_override_attempted,
    )
    receipt = PromptOperatorReviewReceipt(
        review_receipt_id="",
        review_status=status,
        policy_decision_id=str(data.get("decision_id", "")),
        policy_status=str(data.get("policy_status", "")),
        policy_digest=str(data.get("policy_digest", "")),
        requested_ring=str(data.get("requested_ring", "")),
        effective_ring=str(data.get("effective_ring", "")),
        receipt_id=str(data.get("receipt_id", "")),
        audit_receipt_digest=str(data.get("receipt_digest", "")),
        packet_id=str(data.get("packet_id", "")),
        packet_scope=str(data.get("packet_scope", "")),
        reviewer_ref=reviewer,
        review_scope=scope,
        decisions=normalized_decisions,
        accepted_warning_codes=normalized_accepted_warning_codes,
        rejected_warning_codes=normalized_rejected_warning_codes,
        accepted_caveat_codes=normalized_accepted_caveat_codes,
        rejected_caveat_codes=normalized_rejected_caveat_codes,
        required_warning_codes=required_warning_codes,
        required_caveat_codes=required_caveat_codes,
        expiration=expiration,
        expired=expired,
        forbidden_override_attempted=forbidden_override_attempted,
        findings=findings,
        rationale=_compact_rationale(rationale),
        review_digest="",
    )
    digest = compute_prompt_operator_review_digest(receipt)
    return replace(receipt, review_receipt_id=f"operator-review:{data.get('decision_id', 'missing')}:{digest[:16]}", review_digest=digest)


def build_prompt_operator_review_receipt_from_policy_decision(
    policy_decision: PromptMaterializationPolicyDecision | Mapping[str, Any],
    **kwargs: Any,
) -> PromptOperatorReviewReceipt:
    return build_prompt_operator_review_receipt(policy_decision, **kwargs)


def operator_review_accepts_required_warnings(review_receipt: PromptOperatorReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(review_receipt)
    return set(_tuple_str(data.get("required_warning_codes", ()))).issubset(set(_tuple_str(data.get("accepted_warning_codes", ()))))


def operator_review_accepts_required_caveats(review_receipt: PromptOperatorReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(review_receipt)
    return set(_tuple_str(data.get("required_caveat_codes", ()))).issubset(set(_tuple_str(data.get("accepted_caveat_codes", ()))))


def _non_runtime_markers_true(review_receipt: PromptOperatorReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(review_receipt)
    boundary = _mapping(data.get("boundary", {}))
    return all(bool(data.get(marker, boundary.get(marker, False))) for marker in _NON_RUNTIME_MARKERS)


def validate_prompt_operator_review_receipt(review_receipt: PromptOperatorReviewReceipt | Mapping[str, Any]) -> tuple[PromptOperatorReviewFinding, ...]:
    data = _mapping(review_receipt)
    findings: list[PromptOperatorReviewFinding] = []
    if not data:
        return (PromptOperatorReviewFinding("review_receipt_malformed", "operator review receipt is malformed", "blocker"),)
    if not str(data.get("reviewer_ref", "")):
        findings.append(PromptOperatorReviewFinding("reviewer_ref_missing", "reviewer_ref is required for operator review", "blocker"))
    if not _non_runtime_markers_true(review_receipt):
        findings.append(PromptOperatorReviewFinding("non_runtime_marker_missing", "operator review receipt non-runtime markers must all be true", "blocker"))
    if bool(data.get("expired", False)):
        findings.append(PromptOperatorReviewFinding("review_expired", "operator review receipt is expired", "blocker"))
    if bool(data.get("forbidden_override_attempted", False)):
        findings.append(PromptOperatorReviewFinding("forbidden_override_attempted", "operator review attempted a forbidden override", "blocker"))
    expected_digest = compute_prompt_operator_review_digest(review_receipt)
    if str(data.get("review_digest", "")) != expected_digest:
        findings.append(PromptOperatorReviewFinding("review_digest_mismatch", "operator review digest does not match receipt metadata", "blocker"))
    return tuple(findings)


def operator_review_satisfies_policy_decision(
    policy_decision: PromptMaterializationPolicyDecision | Mapping[str, Any],
    review_receipt: PromptOperatorReviewReceipt | Mapping[str, Any] | None,
) -> bool:
    if review_receipt is None or not policy_decision_requires_operator_review(policy_decision) or policy_decision_denies_materialization(policy_decision):
        return False
    policy_data = _mapping(policy_decision)
    review_data = _mapping(review_receipt)
    if not review_data:
        return False
    if str(review_data.get("policy_decision_id", "")) != str(policy_data.get("decision_id", "")):
        return False
    if str(review_data.get("policy_digest", "")) != str(policy_data.get("policy_digest", "")):
        return False
    if str(review_data.get("review_status", "")) not in {PromptOperatorReviewStatus.REVIEW_ACCEPTED, PromptOperatorReviewStatus.REVIEW_PARTIALLY_ACCEPTED}:
        return False
    if bool(review_data.get("expired", False)) or bool(review_data.get("forbidden_override_attempted", False)):
        return False
    if validate_prompt_operator_review_receipt(review_receipt):
        return False
    if not operator_review_accepts_required_warnings(review_receipt):
        return False
    if not operator_review_accepts_required_caveats(review_receipt):
        return False
    return _non_runtime_markers_true(review_receipt)


def explain_prompt_operator_review_findings(review_receipt: PromptOperatorReviewReceipt | Mapping[str, Any]) -> tuple[str, ...]:
    data = _mapping(review_receipt)
    return tuple(
        f"{item.get('severity', '')}:{item.get('code', '')}:{item.get('detail', '')}"
        for item in (_mapping(finding) for finding in data.get("findings", ()) or ())
    )


def summarize_prompt_operator_review_receipt(review_receipt: PromptOperatorReviewReceipt | Mapping[str, Any]) -> Mapping[str, Any]:
    data = _mapping(review_receipt)
    return {
        "review_receipt_id": str(data.get("review_receipt_id", "")),
        "review_status": str(data.get("review_status", "")),
        "policy_decision_id": str(data.get("policy_decision_id", "")),
        "policy_status": str(data.get("policy_status", "")),
        "policy_digest": str(data.get("policy_digest", "")),
        "requested_ring": str(data.get("requested_ring", "")),
        "effective_ring": str(data.get("effective_ring", "")),
        "receipt_id": str(data.get("receipt_id", "")),
        "audit_receipt_digest": str(data.get("audit_receipt_digest", "")),
        "packet_id": str(data.get("packet_id", "")),
        "packet_scope": str(data.get("packet_scope", "")),
        "reviewer_ref": str(data.get("reviewer_ref", "")),
        "accepted_warning_count": len(_tuple_str(data.get("accepted_warning_codes", ()))),
        "rejected_warning_count": len(_tuple_str(data.get("rejected_warning_codes", ()))),
        "accepted_caveat_count": len(_tuple_str(data.get("accepted_caveat_codes", ()))),
        "rejected_caveat_count": len(_tuple_str(data.get("rejected_caveat_codes", ()))),
        "required_warning_count": len(_tuple_str(data.get("required_warning_codes", ()))),
        "required_caveat_count": len(_tuple_str(data.get("required_caveat_codes", ()))),
        "expired": bool(data.get("expired", False)),
        "forbidden_override_attempted": bool(data.get("forbidden_override_attempted", False)),
        "review_digest": str(data.get("review_digest", "")),
    }
