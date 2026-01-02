"""Immutable, hashable policy digest for doctrine attribution."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Iterable, Sequence


def _normalize_lines(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in normalized.split("\n")]
    return "\n".join(lines).strip()


def _normalize_items(items: Iterable[str]) -> tuple[str, ...]:
    cleaned = [_normalize_lines(item) for item in items]
    return tuple(sorted(item for item in cleaned if item))


def _compute_doctrine_hash(invariants: Sequence[str]) -> str:
    normalized = "\n".join(_normalize_items(invariants))
    return sha256(normalized.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PolicyDigest:
    policy_id: str
    policy_version: str
    doctrine_hash: str
    declared_invariants: tuple[str, ...]
    scope: tuple[str, ...]

    def canonical_payload(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "doctrine_hash": self.doctrine_hash,
            "declared_invariants": list(self.declared_invariants),
            "scope": list(self.scope),
        }

    def canonical_json(self) -> str:
        return json.dumps(
            self.canonical_payload(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    def digest(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def reference(self) -> dict[str, str]:
        return {"policy_id": self.policy_id, "policy_hash": self.digest()}


def build_policy_digest(
    *,
    policy_id: str,
    policy_version: str,
    declared_invariants: Sequence[str],
    scope: Sequence[str],
) -> PolicyDigest:
    normalized_invariants = _normalize_items(declared_invariants)
    normalized_scope = _normalize_items(scope)
    doctrine_hash = _compute_doctrine_hash(normalized_invariants)
    return PolicyDigest(
        policy_id=policy_id,
        policy_version=policy_version,
        doctrine_hash=doctrine_hash,
        declared_invariants=normalized_invariants,
        scope=normalized_scope,
    )


# Doctrine attribution only: this digest records why constraints exist without enabling new authority.
_DEFAULT_POLICY_DIGEST = build_policy_digest(
    policy_id="sentientos-doctrine",
    policy_version="1.0",
    declared_invariants=(
        "Startup-only governance entrypoints are gated to bootstrap phases.",
        "Capability scopes narrow during volatility instead of revoking presence.",
        "Failures are classified as fatal versus quarantined with explicit rationale.",
        "Public surfaces are constrained to declared interfaces and scopes.",
        "Tooling classifications enforce release gates and audit visibility.",
    ),
    scope=("startup", "capability", "failure-mode", "public-surface", "tooling"),
)


def policy_digest() -> PolicyDigest:
    """Return the immutable PolicyDigest; policy attribution only."""

    return _DEFAULT_POLICY_DIGEST


def policy_digest_reference() -> dict[str, str]:
    """Return stable policy metadata for attribution at enforcement sites."""

    return _DEFAULT_POLICY_DIGEST.reference()


__all__ = [
    "PolicyDigest",
    "build_policy_digest",
    "policy_digest",
    "policy_digest_reference",
]
