"""Pure version consensus primitives for vow digest alignment.

Stage-0 federation primitive for comparing vow digests without scheduling,
network activity, or enforcement. All helpers are deterministic and
informational only.
"""
from __future__ import annotations

from dataclasses import dataclass

from drift_report import generate_drift_report


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

    def drift_report(self, expected_digest: str) -> dict:
        """Return a passive drift report against an expected digest."""

        return generate_drift_report(self.local_digest, expected_digest)

    def summary(self) -> dict:
        """Expose a passive summary for orchestration layers.

        The ``ready_for_network_use`` flag is always False to communicate that
        this module is purely informational and does not initiate any transport
        or scheduling behavior.
        """

        return {
            "canonical_digest": self.local_digest,
            "ready_for_network_use": False,
        }
