"""Filesystem-based federation primitives for SentientOS."""

from .identity import NodeId
from .federation_digest import FederationDigest
from .consensus_sentinel import FederationConsensusSentinel
from .concord_daemon import ConcordDaemon, PeerSnapshot
from .config import PeerConfig, FederationConfig, load_federation_config
from .summary import (
    FederationSummary,
    build_cathedral_index,
    build_experiment_index,
    build_local_summary,
    summary_to_dict,
    summary_from_dict,
    summary_digest,
    write_local_summary,
    read_peer_summary,
)
from .drift import DriftReport, DriftLevel, compare_summaries
from .poller import FederationPoller, FederationState, PeerReplaySnapshot
from .window import FederationWindow, build_window
from .sync_view import (
    SyncStatus,
    CathedralSyncView,
    ExperimentSyncView,
    PeerSyncView,
    compute_cathedral_sync,
    compute_experiment_sync,
    build_peer_sync_view,
)
from .replay import PassiveReplay, ReplayResult
from .delta import DeltaResult, ReplaySeverity, compute_delta
from .enablement import ENABLEMENT_ENV, is_enabled

__all__ = [
    "NodeId",
    "PeerConfig",
    "FederationConfig",
    "load_federation_config",
    "FederationSummary",
    "build_cathedral_index",
    "build_experiment_index",
    "build_local_summary",
    "summary_to_dict",
    "summary_from_dict",
    "summary_digest",
    "write_local_summary",
    "read_peer_summary",
    "PassiveReplay",
    "ReplayResult",
    "DeltaResult",
    "ReplaySeverity",
    "compute_delta",
    "ENABLEMENT_ENV",
    "is_enabled",
    "DriftReport",
    "DriftLevel",
    "compare_summaries",
    "FederationPoller",
    "FederationState",
    "PeerReplaySnapshot",
    "FederationWindow",
    "build_window",
    "SyncStatus",
    "CathedralSyncView",
    "ExperimentSyncView",
    "PeerSyncView",
    "compute_cathedral_sync",
    "compute_experiment_sync",
    "build_peer_sync_view",
    "FederationDigest",
    "FederationConsensusSentinel",
    "ConcordDaemon",
    "PeerSnapshot",
]
