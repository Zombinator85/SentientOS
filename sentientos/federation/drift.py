"""Drift detection logic for the SentientOS federation layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Literal, Optional

from .summary import FederationSummary
from .sync_view import PeerSyncView, build_peer_sync_view

DriftLevel = Literal["ok", "warn", "drift", "incompatible"]


@dataclass
class DriftReport:
    peer: str
    level: DriftLevel
    reasons: List[str]


_SEVERITY_ORDER: Dict[DriftLevel, int] = {"ok": 0, "warn": 1, "drift": 2, "incompatible": 3}


def _promote(current: DriftLevel, candidate: DriftLevel) -> DriftLevel:
    return candidate if _SEVERITY_ORDER[candidate] > _SEVERITY_ORDER[current] else current


def _reason(message: str) -> str:
    return message.strip()


def compare_summaries(local: FederationSummary, peer: FederationSummary) -> DriftReport:
    """Compare two federation summaries returning a deterministic drift report."""

    reasons: List[str] = []
    level: DriftLevel = "ok"

    try:
        sync_view: Optional[PeerSyncView] = build_peer_sync_view(local, peer)
    except Exception:  # pragma: no cover - defensive
        sync_view = None

    same_digest = local.cathedral.last_applied_digest == peer.cathedral.last_applied_digest
    same_config = local.config.config_digest == peer.config.config_digest
    same_dsl = local.experiments.dsl_version == peer.experiments.dsl_version
    peer_height = int(peer.cathedral.ledger_height)
    local_height = int(local.cathedral.ledger_height)

    if not same_dsl:
        level = "incompatible"
        reasons.append(
            _reason(
                f"Different DSL version (local={local.experiments.dsl_version}, peer={peer.experiments.dsl_version})"
            )
        )
        return _finalise_report(peer.node_name, level, reasons, sync_view)

    if not same_config and not same_digest:
        level = "incompatible"
        reasons.append(
            _reason(
                f"Config and Cathedral digests differ (local={local.config.config_digest}, peer={peer.config.config_digest})"
            )
        )
        return _finalise_report(peer.node_name, level, reasons, sync_view)

    if peer_height < local_height and not same_digest:
        level = "incompatible"
        reasons.append(
            _reason(
                f"Peer ledger behind (local={local_height}, peer={peer_height}) with divergent digest"
            )
        )
        return _finalise_report(peer.node_name, level, reasons, sync_view)

    if same_digest and same_config:
        if peer_height != local_height:
            level = "warn"
            reasons.append(
                _reason(
                    f"Ledger height mismatch despite matching digest (local={local_height}, peer={peer_height})"
                )
            )
        if local.fingerprint != peer.fingerprint:
            level = _promote(level, "warn")
            reasons.append(
                _reason(
                    f"Fingerprint mismatch (local={local.fingerprint}, peer={peer.fingerprint})"
                )
            )
        if not reasons:
            reasons.append("State aligned")
        return _finalise_report(peer.node_name, level, reasons, sync_view)

    if same_digest:
        # Matching Cathedral digest but config diverged
        level = "warn"
        reasons.append(
            _reason(
                f"Config digest mismatch (local={local.config.config_digest}, peer={peer.config.config_digest})"
            )
        )
        return _finalise_report(peer.node_name, level, reasons, sync_view)

    if peer_height >= local_height:
        level = "drift"
        reasons.append(
            _reason(
                f"Peer ahead or divergent (local_digest={local.cathedral.last_applied_digest}, peer_digest={peer.cathedral.last_applied_digest})"
            )
        )
        if peer_height > local_height:
            reasons.append(
                _reason(
                    f"Peer ledger height {peer_height} exceeds local {local_height}"
                )
            )
        return _finalise_report(peer.node_name, level, reasons, sync_view)

    level = "incompatible"
    reasons.append(
        _reason(
            f"Unclassified divergence (local_digest={local.cathedral.last_applied_digest}, peer_digest={peer.cathedral.last_applied_digest})"
        )
    )
    return _finalise_report(peer.node_name, level, reasons, sync_view)


def _finalise_report(peer_name: str, level: DriftLevel, reasons: List[str], sync_view: Optional[PeerSyncView]) -> DriftReport:
    if sync_view is not None and level == "drift":
        _append_sync_reasons(reasons, sync_view)
    return DriftReport(peer=peer_name, level=level, reasons=reasons)


def _append_sync_reasons(reasons: List[str], sync_view: PeerSyncView) -> None:
    cathedral_status = getattr(sync_view.cathedral, "status", "unknown")
    if cathedral_status == "ahead_of_me" and "peer_ahead_cathedral" not in reasons:
        reasons.append("peer_ahead_cathedral")
    elif cathedral_status == "behind_me" and "peer_behind_cathedral" not in reasons:
        reasons.append("peer_behind_cathedral")
    elif cathedral_status == "divergent" and "cathedral_history_divergent" not in reasons:
        reasons.append("cathedral_history_divergent")

    experiment_status = getattr(sync_view.experiments, "status", "unknown")
    if experiment_status == "ahead_of_me" and "peer_ahead_experiments" not in reasons:
        reasons.append("peer_ahead_experiments")
    elif experiment_status == "behind_me" and "peer_behind_experiments" not in reasons:
        reasons.append("peer_behind_experiments")
    elif experiment_status == "divergent" and "experiments_divergent" not in reasons:
        reasons.append("experiments_divergent")
