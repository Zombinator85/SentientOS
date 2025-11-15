"""Federation window aggregation helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Mapping, Optional, TYPE_CHECKING

from .drift import DriftReport
from .identity import NodeId

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .sync_view import PeerSyncView

__all__ = ["FederationWindow", "build_window"]


@dataclass(frozen=True)
class FederationWindow:
    """Aggregated snapshot of cluster drift from the local node."""

    local_node: NodeId
    ts: datetime
    peers: Dict[str, DriftReport]
    ok_count: int
    warn_count: int
    drift_count: int
    incompatible_count: int
    missing_count: int
    is_quorum_healthy: bool
    is_cluster_unstable: bool
    peer_sync: Dict[str, "PeerSyncView"] = field(default_factory=dict)

    @property
    def total_peers(self) -> int:
        return len(self.peers)


def _coerce_threshold(value: int) -> int:
    return max(0, int(value))


def build_window(
    local_node: NodeId,
    reports: Mapping[str, DriftReport],
    now: datetime,
    *,
    expected_peer_count: int = 0,
    max_drift_peers: int = 0,
    max_incompatible_peers: int = 0,
    max_missing_peers: int = 0,
    peer_sync: Optional[Mapping[str, "PeerSyncView"]] = None,
) -> FederationWindow:
    """Deterministically aggregate per-peer :class:`DriftReport` objects."""

    ok_count = 0
    warn_count = 0
    drift_count = 0
    incompatible_count = 0

    for report in reports.values():
        level = getattr(report, "level", "ok")
        if level == "ok":
            ok_count += 1
        elif level == "warn":
            warn_count += 1
        elif level == "drift":
            drift_count += 1
        elif level == "incompatible":
            incompatible_count += 1
        else:
            warn_count += 1

    expected = max(0, int(expected_peer_count))
    missing_count = max(0, expected - len(reports))

    max_drift = _coerce_threshold(max_drift_peers)
    max_incompatible = _coerce_threshold(max_incompatible_peers)
    max_missing = _coerce_threshold(max_missing_peers)

    if expected == 0 and not reports:
        # Single-node execution defaults to healthy.
        is_quorum_healthy = True
        is_cluster_unstable = False
    else:
        is_quorum_healthy = incompatible_count == 0 and drift_count <= max_drift
        is_cluster_unstable = (
            incompatible_count > max_incompatible
            or drift_count > max_drift
            or missing_count > max_missing
        )

    peer_sync_map = dict(peer_sync or {})

    return FederationWindow(
        local_node=local_node,
        ts=now,
        peers=dict(reports),
        ok_count=ok_count,
        warn_count=warn_count,
        drift_count=drift_count,
        incompatible_count=incompatible_count,
        missing_count=missing_count,
        is_quorum_healthy=is_quorum_healthy,
        is_cluster_unstable=is_cluster_unstable,
        peer_sync=peer_sync_map,
    )

