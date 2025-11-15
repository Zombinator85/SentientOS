"""Filesystem-based federation primitives for SentientOS."""

from .identity import NodeId
from .config import PeerConfig, FederationConfig, load_federation_config
from .summary import (
    FederationSummary,
    build_local_summary,
    summary_to_dict,
    summary_from_dict,
    summary_digest,
    write_local_summary,
    read_peer_summary,
)
from .drift import DriftReport, DriftLevel, compare_summaries
from .poller import FederationPoller, FederationState
from .window import FederationWindow, build_window

__all__ = [
    "NodeId",
    "PeerConfig",
    "FederationConfig",
    "load_federation_config",
    "FederationSummary",
    "build_local_summary",
    "summary_to_dict",
    "summary_from_dict",
    "summary_digest",
    "write_local_summary",
    "read_peer_summary",
    "DriftReport",
    "DriftLevel",
    "compare_summaries",
    "FederationPoller",
    "FederationState",
    "FederationWindow",
    "build_window",
]
