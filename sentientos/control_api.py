"""Public control/admission façade for expressive modules.

This boundary surface is DTO/validation-only and delegates to existing
control-plane and task-admission authority semantics.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from control_plane.enums import Decision, ReasonCode, RequestType
from control_plane.records import AuthorizationError
from control_plane import admit_request
import task_executor


def require_authorization_for_request_types(
    authorization: Any,
    *,
    allowed_request_types: Iterable[str],
) -> Any:
    if authorization is None:
        raise AuthorizationError(ReasonCode.MISSING_AUTHORIZATION.value)
    if getattr(authorization, "decision", None) != Decision.ALLOW:
        reason = getattr(getattr(authorization, "reason", None), "value", None) or "authorization denied"
        raise AuthorizationError(str(reason))

    request_type = getattr(authorization, "request_type", None)
    if request_type not in {RequestType(item) for item in allowed_request_types}:
        raise AuthorizationError(ReasonCode.INVALID_AUTHORIZATION.value)
    return authorization


def require_self_patch_apply_authority(admission_token: Any, authorization: Any) -> None:
    if admission_token is None:
        raise AuthorizationError("admission token required for self-healing apply")
    if authorization is None:
        raise AuthorizationError("authorization required for self-healing apply")
    authorization.require(RequestType.TASK_EXECUTION)
    if admission_token.issued_by != "task_admission":
        raise AuthorizationError("admission token issuer invalid")
    if not isinstance(admission_token.provenance, task_executor.AuthorityProvenance):
        raise AuthorizationError("admission token provenance missing")
    fingerprint_value = admission_token.request_fingerprint.value
    if not isinstance(fingerprint_value, str) or len(fingerprint_value) != 64:
        raise AuthorizationError("admission token fingerprint missing")
    try:
        int(fingerprint_value, 16)
    except ValueError as exc:  # pragma: no cover - defensive
        raise AuthorizationError("admission token fingerprint missing") from exc


def admit_tts_request(*, requester_id: str, intent_hash: str, context_hash: str, policy_version: str, metadata: Mapping[str, Any] | None = None) -> Any:
    return admit_request(
        request_type=RequestType.SPEECH_TTS,
        requester_id=requester_id,
        intent_hash=intent_hash,
        context_hash=context_hash,
        policy_version=policy_version,
        metadata=dict(metadata or {}),
    )


def canonicalize_admission_provenance(provenance: Any) -> dict[str, Any]:
    return task_executor.canonicalise_provenance(provenance)


def require_request_fingerprint_match(admission_token: Any, request_fingerprint: Any | None) -> None:
    if request_fingerprint is not None and request_fingerprint.value != admission_token.request_fingerprint.value:
        raise AuthorizationError("request fingerprint mismatch for self-healing apply")


__all__ = [
    "require_authorization_for_request_types",
    "require_self_patch_apply_authority",
    "admit_tts_request",
    "canonicalize_admission_provenance",
    "require_request_fingerprint_match",
]
