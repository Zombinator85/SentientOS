"""Pure version consensus primitives for vow digest alignment."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VersionConsensus:
    """Compute-only digest comparison helper.

    This helper does not perform any network activity or scheduling. It simply
    exposes deterministic comparisons that higher layers can wire into their own
    coordination flows.
    """

    local_digest: str

    def compare(self, peer_digest: str) -> dict:
        """Return a structured comparison against a peer's digest."""

        match = self.local_digest == peer_digest
        return {
            "match": match,
            "local_digest": self.local_digest,
            "peer_digest": peer_digest,
        }

    def is_compatible(self, peer_digest: str) -> bool:
        """Return True when the peer digest matches the local digest."""

        return self.local_digest == peer_digest
