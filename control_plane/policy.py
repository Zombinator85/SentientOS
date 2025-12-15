from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, Mapping

from .enums import Decision, RequestType


@dataclass(frozen=True)
class RequestRule:
    """Static rule governing a single request class."""

    allow: bool = True
    allowed_requesters: FrozenSet[str] = field(default_factory=frozenset)
    rate_cap: int | None = None
    allowed_contexts: FrozenSet[str] = field(default_factory=frozenset)
    ban_recursion: bool = True
    require_human: bool = True

    def can_allow(self, requester_id: str, *, context_hash: str | None = None) -> bool:
        if not self.allow:
            return False
        if self.allowed_requesters and requester_id not in self.allowed_requesters:
            return False
        if self.allowed_contexts and context_hash and context_hash not in self.allowed_contexts:
            return False
        return True


@dataclass(frozen=True)
class ControlPlanePolicy:
    version: str
    request_rules: Mapping[RequestType, RequestRule]

    def rule_for(self, request_type: RequestType) -> RequestRule | None:
        return self.request_rules.get(request_type)

    def describe(self) -> dict[str, object]:
        return {
            "version": self.version,
            "request_rules": {
                r_type.value: {
                    "allow": rule.allow,
                    "allowed_requesters": sorted(rule.allowed_requesters),
                    "rate_cap": rule.rate_cap,
                    "allowed_contexts": sorted(rule.allowed_contexts),
                    "ban_recursion": rule.ban_recursion,
                    "require_human": rule.require_human,
                }
                for r_type, rule in self.request_rules.items()
            },
        }


def load_policy(version: str | None = None) -> ControlPlanePolicy:
    """Return the static, deterministic Control Plane policy."""

    policy_version = version or "v1-static"
    request_rules = {
        RequestType.TASK_EXECUTION: RequestRule(
            allow=True,
            allowed_requesters=frozenset({"operator", "codex", "reviewer"}),
            rate_cap=128,
            require_human=False,
        ),
        RequestType.SPEECH_TTS: RequestRule(
            allow=True,
            allowed_requesters=frozenset({"operator", "narrator"}),
            rate_cap=64,
            require_human=True,
        ),
        RequestType.AVATAR_EMISSION: RequestRule(
            allow=True,
            allowed_requesters=frozenset({"operator", "narrator", "bridge"}),
            rate_cap=256,
            require_human=True,
        ),
    }
    return ControlPlanePolicy(version=policy_version, request_rules=request_rules)


def evaluate_rate(rule: RequestRule, metadata: Mapping[str, object] | None) -> Decision | None:
    if rule.rate_cap is None:
        return None
    if metadata is None:
        return None
    observed = metadata.get("requests_in_window")
    if isinstance(observed, int) and observed > rule.rate_cap:
        return Decision.DENY
    return None


def requires_human(rule: RequestRule, metadata: Mapping[str, object] | None) -> bool:
    if not rule.require_human:
        return False
    approved_by = metadata.get("approved_by") if metadata else None
    return not isinstance(approved_by, str) or not approved_by.strip()
