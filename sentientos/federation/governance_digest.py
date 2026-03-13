"""Federation governance digest exchange helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from sentientos.federated_governance import GovernanceDigest, get_controller


@dataclass(frozen=True)
class GovernanceCompatibility:
    status: str
    reason: str


def local_digest() -> GovernanceDigest:
    return get_controller().local_governance_digest()


def evaluate_compatibility(peer_digest: Mapping[str, object], local: GovernanceDigest | None = None) -> GovernanceCompatibility:
    local_digest_payload = local or get_controller().local_governance_digest()
    peer_value = str(peer_digest.get("digest") or "")
    if not peer_value:
        return GovernanceCompatibility(status="incompatible", reason="missing_digest")
    if peer_value == local_digest_payload.digest:
        return GovernanceCompatibility(status="exact_match", reason="digest_equal")
    local_prefix = local_digest_payload.digest[:12]
    peer_prefix = peer_value[:12]
    if local_prefix == peer_prefix:
        return GovernanceCompatibility(status="same_family_different_patch", reason="digest_prefix_match")
    return GovernanceCompatibility(status="incompatible", reason="digest_mismatch")
