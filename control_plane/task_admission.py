from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, MutableMapping

from logging_config import get_log_path
from log_utils import append_json

from .enums import Decision, ReasonCode, RequestType
from .policy import ControlPlanePolicy, evaluate_rate, load_policy, requires_human
from .records import AuthorizationRecord


CONTROL_PLANE_LOG_PATH = get_log_path("control_plane_admission.jsonl", "CONTROL_PLANE_LOG")


@dataclass(frozen=True)
class AdmissionResponse:
    decision: Decision
    reason: ReasonCode
    record: AuthorizationRecord


def _build_record(
    request_type: RequestType,
    requester_id: str,
    intent_hash: str,
    context_hash: str,
    policy_version: str,
    decision: Decision,
    reason: ReasonCode,
    metadata: Mapping[str, object] | None,
) -> AuthorizationRecord:
    return AuthorizationRecord.create(
        request_type=request_type,
        requester_id=requester_id,
        intent_hash=intent_hash,
        context_hash=context_hash,
        policy_version=policy_version,
        decision=decision,
        reason=reason,
        metadata=metadata,
    )


def _log_decision(record: AuthorizationRecord, metadata: Mapping[str, object] | None) -> None:
    entry: MutableMapping[str, object] = {
        "event": "CONTROL_PLANE_ADMISSION",
        **record.as_log_entry(),
    }
    if metadata:
        entry["metadata"] = dict(metadata)
    append_json(CONTROL_PLANE_LOG_PATH, entry)


def admit_request(
    *,
    request_type: RequestType,
    requester_id: str,
    intent_hash: str,
    context_hash: str,
    policy_version: str,
    metadata: Mapping[str, object] | None = None,
    policy: ControlPlanePolicy | None = None,
) -> AdmissionResponse:
    """Deterministically gate execution-capable actions.

    This performs no execution, retries, inference, or side effects
    other than logging the admission decision.
    """

    policy_obj = policy or load_policy(policy_version)
    rule = policy_obj.rule_for(request_type)

    decision = Decision.ALLOW
    reason = ReasonCode.OK

    if policy_obj.version != policy_version:
        decision, reason = Decision.DENY, ReasonCode.POLICY_VERSION_MISMATCH
    elif rule is None:
        decision, reason = Decision.DENY, ReasonCode.UNKNOWN_REQUEST
    elif requester_id == "control_plane":
        decision, reason = Decision.DENY, ReasonCode.SELF_AUTH_FORBIDDEN
    elif rule.ban_recursion and _is_recursive(request_type, intent_hash, metadata):
        decision, reason = Decision.DENY, ReasonCode.RECURSION_BLOCKED
    elif not rule.can_allow(requester_id, context_hash=context_hash):
        decision, reason = Decision.DENY, ReasonCode.UNAUTHORIZED_REQUESTER
    elif evaluate_rate(rule, metadata) == Decision.DENY:
        decision, reason = Decision.DENY, ReasonCode.RATE_LIMIT_EXCEEDED
    elif requires_human(rule, metadata):
        decision, reason = Decision.DENY, ReasonCode.HUMAN_APPROVAL_REQUIRED

    record = _build_record(
        request_type=request_type,
        requester_id=requester_id,
        intent_hash=intent_hash,
        context_hash=context_hash,
        policy_version=policy_obj.version,
        decision=decision,
        reason=reason,
        metadata=metadata,
    )
    _log_decision(record, metadata)
    return AdmissionResponse(decision=decision, reason=reason, record=record)


def _is_recursive(request_type: RequestType, intent_hash: str, metadata: Mapping[str, object] | None) -> bool:
    if not metadata:
        return False
    parent_type = metadata.get("parent_request_type")
    parent_intent = metadata.get("parent_intent_hash")
    if isinstance(parent_type, str) and parent_type == request_type.value:
        return True
    if isinstance(parent_intent, str) and parent_intent == intent_hash:
        return True
    return False


__all__ = ["AdmissionResponse", "admit_request", "CONTROL_PLANE_LOG_PATH"]
