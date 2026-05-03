"""Public control/admission façade for expressive modules.

This boundary surface is DTO/validation-only and delegates to existing
control-plane and task-admission authority semantics.
"""

from __future__ import annotations

from typing import Any, Iterable

from control_plane.enums import Decision, ReasonCode, RequestType
from control_plane.records import AuthorizationError
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


__all__ = [
    "require_authorization_for_request_types",
    "require_self_patch_apply_authority",
]
