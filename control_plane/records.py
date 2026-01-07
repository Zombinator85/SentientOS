from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, MutableMapping

from .enums import Decision, ReasonCode, RequestType
from sentientos.federation.enablement import assert_federation_contract, has_federation_artifacts


class AuthorizationError(RuntimeError):
    pass


@dataclass(frozen=True)
class AuthorizationRecord:
    request_type: RequestType
    requester_id: str
    intent_hash: str
    context_hash: str
    policy_version: str
    decision: Decision
    reason: ReasonCode
    timestamp: float
    metadata: Mapping[str, object] | None = None

    @classmethod
    def create(
        cls,
        *,
        request_type: RequestType,
        requester_id: str,
        intent_hash: str,
        context_hash: str,
        policy_version: str,
        decision: Decision,
        reason: ReasonCode,
        metadata: Mapping[str, object] | None,
    ) -> "AuthorizationRecord":
        now = datetime.now(tz=timezone.utc).timestamp()
        if has_federation_artifacts(metadata):
            assert_federation_contract("authorization:metadata")
        return cls(
            request_type=request_type,
            requester_id=requester_id,
            intent_hash=intent_hash,
            context_hash=context_hash,
            policy_version=policy_version,
            decision=decision,
            reason=reason,
            timestamp=now,
            metadata=dict(metadata) if metadata else None,
        )

    def require(self, expected_type: RequestType) -> None:
        if self.decision != Decision.ALLOW:
            raise AuthorizationError(f"decision is {self.decision}, not allowed")
        if self.request_type != expected_type:
            raise AuthorizationError(f"authorization for {self.request_type} cannot be used for {expected_type}")

    def as_log_entry(self) -> MutableMapping[str, object]:
        entry: MutableMapping[str, object] = {
            "request_type": self.request_type.value,
            "requester_id": self.requester_id,
            "intent_hash": self.intent_hash,
            "context_hash": self.context_hash,
            "policy_version": self.policy_version,
            "decision": self.decision.value,
            "reason": self.reason.value,
            "timestamp": self.timestamp,
        }
        if self.metadata:
            entry["metadata"] = dict(self.metadata)
        return entry


__all__ = ["AuthorizationRecord", "AuthorizationError"]
