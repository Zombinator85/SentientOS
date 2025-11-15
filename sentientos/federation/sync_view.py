"""Helpers for comparing local vs peer federation indexes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Literal, Optional

from .summary import CathedralIndexSnapshot, ExperimentIndexSnapshot, FederationSummary, SummaryIndexes

SyncStatus = Literal["aligned", "ahead_of_me", "behind_me", "divergent", "unknown"]


@dataclass(frozen=True)
class CathedralSyncView:
    status: SyncStatus
    missing_local_ids: List[str]
    missing_peer_ids: List[str]
    reasons: List[str]


@dataclass(frozen=True)
class ExperimentSyncView:
    status: SyncStatus
    missing_local_ids: List[str]
    missing_peer_ids: List[str]
    reasons: List[str]


@dataclass(frozen=True)
class PeerSyncView:
    peer_name: str
    cathedral: CathedralSyncView
    experiments: ExperimentSyncView


def _normalise_ids(values: Iterable[str] | None) -> List[str]:
    if values is None:
        return []
    result: List[str] = []
    for item in values:
        if isinstance(item, str):
            text = item.strip()
            if text:
                result.append(text)
    return result


def compute_cathedral_sync(local_ids: List[str], peer_ids: List[str]) -> CathedralSyncView:
    local = list(local_ids or [])
    peer = list(peer_ids or [])
    if not local and not peer:
        return CathedralSyncView(status="unknown", missing_local_ids=[], missing_peer_ids=[], reasons=["no_index"])
    if local == peer:
        return CathedralSyncView(status="aligned", missing_local_ids=[], missing_peer_ids=[], reasons=["aligned"])
    if len(peer) > len(local) and peer[: len(local)] == local:
        return CathedralSyncView(
            status="ahead_of_me",
            missing_local_ids=peer[len(local):],
            missing_peer_ids=[],
            reasons=["peer_ahead"],
        )
    if len(local) > len(peer) and local[: len(peer)] == peer:
        return CathedralSyncView(
            status="behind_me",
            missing_local_ids=[],
            missing_peer_ids=local[len(peer):],
            reasons=["peer_behind"],
        )
    missing_local = [item for item in peer if item not in local]
    missing_peer = [item for item in local if item not in peer]
    return CathedralSyncView(
        status="divergent",
        missing_local_ids=missing_local,
        missing_peer_ids=missing_peer,
        reasons=["divergent_history"],
    )


def compute_experiment_sync(local_ids: List[str], peer_ids: List[str]) -> ExperimentSyncView:
    local = list(local_ids or [])
    peer = list(peer_ids or [])
    if not local and not peer:
        return ExperimentSyncView(status="unknown", missing_local_ids=[], missing_peer_ids=[], reasons=["no_index"])
    if local == peer:
        return ExperimentSyncView(status="aligned", missing_local_ids=[], missing_peer_ids=[], reasons=["aligned"])
    if len(peer) > len(local) and peer[: len(local)] == local:
        return ExperimentSyncView(
            status="ahead_of_me",
            missing_local_ids=peer[len(local):],
            missing_peer_ids=[],
            reasons=["peer_ahead"],
        )
    if len(local) > len(peer) and local[: len(peer)] == peer:
        return ExperimentSyncView(
            status="behind_me",
            missing_local_ids=[],
            missing_peer_ids=local[len(peer):],
            reasons=["peer_behind"],
        )
    missing_local = [item for item in peer if item not in local]
    missing_peer = [item for item in local if item not in peer]
    return ExperimentSyncView(
        status="divergent",
        missing_local_ids=missing_local,
        missing_peer_ids=missing_peer,
        reasons=["divergent_history"],
    )


def build_peer_sync_view(local_summary: FederationSummary, peer_summary: FederationSummary) -> PeerSyncView:
    local_indexes: Optional[SummaryIndexes] = getattr(local_summary, "indexes", None)
    peer_indexes: Optional[SummaryIndexes] = getattr(peer_summary, "indexes", None)

    local_cathedral = getattr(local_indexes, "cathedral", None)
    peer_cathedral = getattr(peer_indexes, "cathedral", None)

    if local_cathedral is None:
        cathedral_view = CathedralSyncView("unknown", [], [], ["local_no_index"])
    elif peer_cathedral is None:
        cathedral_view = CathedralSyncView("unknown", [], [], ["peer_no_index"])
    else:
        cathedral_view = compute_cathedral_sync(
            _normalise_ids(local_cathedral.applied_ids),
            _normalise_ids(peer_cathedral.applied_ids),
        )

    local_experiments = getattr(local_indexes, "experiments", None)
    peer_experiments = getattr(peer_indexes, "experiments", None)

    if local_experiments is None:
        experiments_view = ExperimentSyncView("unknown", [], [], ["local_no_index"])
    elif peer_experiments is None:
        experiments_view = ExperimentSyncView("unknown", [], [], ["peer_no_index"])
    else:
        experiments_view = compute_experiment_sync(
            _normalise_ids(local_experiments.latest_ids),
            _normalise_ids(peer_experiments.latest_ids),
        )

    if experiments_view.status not in {"aligned", "unknown"} and cathedral_view.status in {"aligned", "unknown"}:
        if "experiments_only" not in experiments_view.reasons:
            experiments_view.reasons.append("experiments_only")

    return PeerSyncView(
        peer_name=peer_summary.node_name,
        cathedral=cathedral_view,
        experiments=experiments_view,
    )


__all__ = [
    "SyncStatus",
    "CathedralSyncView",
    "ExperimentSyncView",
    "PeerSyncView",
    "compute_cathedral_sync",
    "compute_experiment_sync",
    "build_peer_sync_view",
]
