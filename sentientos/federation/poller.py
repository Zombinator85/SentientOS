"""Federation poller glue code for SentientOS."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, Mapping, Optional

from sentientos.persona_events import publish_event

from .config import FederationConfig, PeerConfig
from .drift import DriftLevel, DriftReport, compare_summaries
from .summary import FederationSummary, build_local_summary, read_peer_summary, write_local_summary
from .sync_view import PeerSyncView, build_peer_sync_view
from .window import FederationWindow, build_window


@dataclass
class FederationState:
    last_poll_ts: Optional[datetime] = None
    peer_reports: Dict[str, DriftReport] = field(default_factory=dict)

    def counts(self) -> Dict[str, int]:
        summary: Dict[str, int] = {"total": len(self.peer_reports), "ok": 0, "warn": 0, "drift": 0, "incompatible": 0}
        for report in self.peer_reports.values():
            summary[report.level] = summary.get(report.level, 0) + 1
        summary["healthy"] = summary["ok"]
        return summary


class FederationPoller:
    def __init__(self, config: FederationConfig, runtime, log_cb: Callable[[str], None]) -> None:
        self.config = config
        self.runtime = runtime
        self.log_cb = log_cb
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._state = FederationState()
        self._lock = threading.Lock()
        self._last_levels: Dict[str, DriftLevel] = {}
        self._window: Optional[FederationWindow] = None
        self._peer_sync_views: Dict[str, PeerSyncView] = {}
        self._last_sync_status: Dict[str, str] = {}

    @property
    def state(self) -> FederationState:
        with self._lock:
            return FederationState(
                last_poll_ts=self._state.last_poll_ts,
                peer_reports=dict(self._state.peer_reports),
            )

    def get_window(self) -> Optional[FederationWindow]:
        with self._lock:
            return self._window

    def get_peer_sync_views(self) -> Dict[str, PeerSyncView]:
        with self._lock:
            return dict(self._peer_sync_views)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="FederationPoller", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is None:
            return
        thread.join(timeout=self.config.poll_interval_seconds * 2)
        self._thread = None

    def _run(self) -> None:
        interval = max(1, int(self.config.poll_interval_seconds))
        while not self._stop.is_set():
            try:
                self._poll_once()
            except Exception:  # pragma: no cover - defensive
                self.log_cb("Federation poll failure; continuing")
            if self._stop.wait(interval):
                break

    def _poll_once(self) -> None:
        summary = build_local_summary(self.runtime)
        write_local_summary(summary, self.config.state_file)

        reports: Dict[str, DriftReport] = {}
        peer_sync_views: Dict[str, PeerSyncView] = {}
        for peer in self.config.peers:
            report, peer_summary = self._evaluate_peer(peer, summary)
            reports[peer.node_name] = report
            if peer_summary is not None:
                try:
                    view = build_peer_sync_view(summary, peer_summary)
                except Exception:  # pragma: no cover - defensive
                    continue
                peer_sync_views[peer.node_name] = view

        now = datetime.now(timezone.utc)
        with self._lock:
            self._state.last_poll_ts = now
            self._state.peer_reports = reports
            self._window = build_window(
                self.config.node_id,
                reports,
                now,
                expected_peer_count=len(self.config.peers),
                max_drift_peers=self.config.max_drift_peers,
                max_incompatible_peers=self.config.max_incompatible_peers,
                max_missing_peers=self.config.max_missing_peers,
                peer_sync=peer_sync_views,
            )
            self._peer_sync_views = dict(peer_sync_views)
            window = self._window
        self._emit_aggregate_event(reports)
        self._emit_sync_events(peer_sync_views)
        if window is not None:
            callback = getattr(self.runtime, "on_federation_window", None)
            if callable(callback):
                try:
                    callback(window)
                except Exception:  # pragma: no cover - defensive
                    self.log_cb("Federation window callback failed; continuing")

    def _evaluate_peer(self, peer: PeerConfig, local_summary) -> tuple[DriftReport, Optional[FederationSummary]]:
        peer_summary = read_peer_summary(peer.state_file)
        if peer_summary is None:
            report = DriftReport(peer=peer.node_name, level="incompatible", reasons=["Missing or invalid summary"])
        else:
            report = compare_summaries(local_summary, peer_summary)
        previous = self._last_levels.get(peer.node_name, "ok")
        self._last_levels[peer.node_name] = report.level
        if self._is_worse(report.level, previous):
            reason_text = "; ".join(report.reasons)
            if report.level == "incompatible":
                self.log_cb(f"Federation: peer {peer.node_name} now incompatible (reasons: {reason_text})")
            elif report.level == "drift":
                self.log_cb(f"Federation: peer {peer.node_name} drift detected (reasons: {reason_text})")
            elif report.level == "warn":
                self.log_cb(f"Federation: peer {peer.node_name} warning (reasons: {reason_text})")
        if report.level in {"drift", "incompatible"}:
            publish_event(
                {
                    "kind": "federation",
                    "peer": peer.node_name,
                    "level": report.level,
                    "reasons": list(report.reasons),
                    "ts": datetime.now(timezone.utc).isoformat(),
                }
            )
        return report, peer_summary

    @staticmethod
    def _is_worse(current: DriftLevel, previous: DriftLevel) -> bool:
        order = {"ok": 0, "warn": 1, "drift": 2, "incompatible": 3}
        return order[current] > order.get(previous, 0)

    def _emit_aggregate_event(self, reports: Dict[str, DriftReport]) -> None:
        if not reports:
            return
        if any(report.level in {"drift", "incompatible"} for report in reports.values()):
            publish_event(
                {
                    "kind": "federation",
                    "peer": "multiple",
                    "level": "drift",
                    "reasons": ["Multiple peers report drift or incompatibility"],
                    "ts": datetime.now(timezone.utc).isoformat(),
                }
            )

    def _emit_sync_events(self, views: Mapping[str, PeerSyncView]) -> None:
        interesting = {"ahead_of_me", "divergent"}
        for peer, view in views.items():
            status = getattr(view.cathedral, "status", "unknown")
            previous = self._last_sync_status.get(peer)
            self._last_sync_status[peer] = status
            if status not in interesting or status == previous:
                continue
            publish_event(
                {
                    "kind": "federation",
                    "event": "cathedral_sync_state",
                    "peer": peer,
                    "status": status,
                    "missing_local_ids": list(view.cathedral.missing_local_ids),
                    "missing_peer_ids": list(view.cathedral.missing_peer_ids),
                    "ts": datetime.now(timezone.utc).isoformat(),
                }
            )
        for peer in list(self._last_sync_status.keys()):
            if peer not in views:
                self._last_sync_status.pop(peer, None)
