"""Federation poller glue code for SentientOS."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

from sentientos.persona_events import publish_event

from .config import FederationConfig, PeerConfig
from .delta import DeltaResult, ReplaySeverity, compute_delta
from .drift import DriftLevel, DriftReport, compare_summaries
from .replay import PassiveReplay, ReplayResult
from .summary import FederationSummary, build_local_summary, read_peer_summary, summary_digest, write_local_summary
from .sync_view import PeerSyncView, build_peer_sync_view
from .window import FederationWindow, build_window


@dataclass
class FederationState:
    last_poll_ts: Optional[datetime] = None
    peer_reports: Dict[str, DriftReport] = field(default_factory=dict)
    peer_replay: Dict[str, "PeerReplaySnapshot"] = field(default_factory=dict)

    def counts(self) -> Dict[str, int]:
        summary: Dict[str, int] = {"total": len(self.peer_reports), "ok": 0, "warn": 0, "drift": 0, "incompatible": 0}
        for report in self.peer_reports.values():
            summary[report.level] = summary.get(report.level, 0) + 1
        summary["healthy"] = summary["ok"]
        return summary


@dataclass
class PeerReplaySnapshot:
    peer: str
    severity: ReplaySeverity
    delta: DeltaResult
    last_seen: datetime
    summary_digest: Optional[str] = None

    def to_payload(self) -> Dict[str, Any]:
        return {
            "peer": self.peer,
            "severity": self.severity,
            "last_seen": self.last_seen.astimezone(timezone.utc).isoformat(),
            "delta": self.delta.to_payload(),
            "summary_digest": self.summary_digest,
        }

    @staticmethod
    def from_payload(payload: Mapping[str, Any]) -> "PeerReplaySnapshot":
        ts_value = payload.get("last_seen")
        if isinstance(ts_value, str) and ts_value.strip():
            try:
                ts = datetime.fromisoformat(ts_value)
            except ValueError:
                ts = datetime.now(timezone.utc)
        else:
            ts = datetime.now(timezone.utc)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        delta_payload = payload.get("delta", {})
        return PeerReplaySnapshot(
            peer=str(payload.get("peer") or ""),
            severity=str(payload.get("severity") or "none"),
            delta=DeltaResult.from_payload(delta_payload if isinstance(delta_payload, Mapping) else {}),
            last_seen=ts,
            summary_digest=(str(payload.get("summary_digest")) or None),
        )


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
        state_path = Path(self.config.state_file)
        state_dir = state_path.parent
        federation_root = state_dir.parent if state_dir.parent != state_dir else state_dir
        self._replay_dir = federation_root / "replay"
        self._quarantine_dir = federation_root / "quarantine"
        self._replay_dir.mkdir(parents=True, exist_ok=True)
        self._quarantine_dir.mkdir(parents=True, exist_ok=True)
        self._peer_replay: Dict[str, PeerReplaySnapshot] = self._load_persisted_replay()
        self._state.peer_replay = dict(self._peer_replay)

    @property
    def state(self) -> FederationState:
        with self._lock:
            return FederationState(
                last_poll_ts=self._state.last_poll_ts,
                peer_reports=dict(self._state.peer_reports),
                peer_replay=dict(self._state.peer_replay),
            )

    def get_window(self) -> Optional[FederationWindow]:
        with self._lock:
            return self._window

    def get_peer_sync_views(self) -> Dict[str, PeerSyncView]:
        with self._lock:
            return dict(self._peer_sync_views)

    def get_replay_state(self) -> Dict[str, PeerReplaySnapshot]:
        with self._lock:
            return dict(self._peer_replay)

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

        local_registry = self._collect_local_registry()
        local_replay = PassiveReplay(self.config.node_id.fingerprint, summary, registry=local_registry).simulate()
        reports: Dict[str, DriftReport] = {}
        peer_sync_views: Dict[str, PeerSyncView] = {}
        replay_updates: Dict[str, PeerReplaySnapshot] = {}
        for peer in self.config.peers:
            state_path = Path(peer.state_file)
            existed = state_path.exists()
            report, peer_summary = self._evaluate_peer(peer, summary)
            reports[peer.node_name] = report
            if peer_summary is None and existed:
                self._quarantine_peer_summary(state_path)
            if peer_summary is not None:
                try:
                    view = build_peer_sync_view(summary, peer_summary)
                except Exception:  # pragma: no cover - defensive
                    continue
                peer_sync_views[peer.node_name] = view
                snapshot = self._build_peer_replay_snapshot(peer, peer_summary, local_replay)
                replay_updates[peer.node_name] = snapshot
                self._persist_replay_snapshot(snapshot)

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
            if replay_updates:
                self._peer_replay.update(replay_updates)
            self._state.peer_replay = dict(self._peer_replay)
            window = self._window
        self._emit_aggregate_event(reports)
        self._emit_sync_events(peer_sync_views)
        self._emit_replay_events(replay_updates)
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

    def replay_peer(self, peer_id: str) -> Optional[PeerReplaySnapshot]:
        peer = next((candidate for candidate in self.config.peers if candidate.node_name == peer_id), None)
        if peer is None:
            return None
        peer_summary = read_peer_summary(peer.state_file)
        if peer_summary is None:
            return None
        summary = build_local_summary(self.runtime)
        write_local_summary(summary, self.config.state_file)
        local_replay = PassiveReplay(
            self.config.node_id.fingerprint,
            summary,
            registry=self._collect_local_registry(),
        ).simulate()
        snapshot = self._build_peer_replay_snapshot(peer, peer_summary, local_replay)
        self._persist_replay_snapshot(snapshot)
        with self._lock:
            self._peer_replay[peer_id] = snapshot
            self._state.peer_replay = dict(self._peer_replay)
        self._emit_replay_events({peer_id: snapshot})
        return snapshot

    def _collect_local_registry(self) -> Dict[str, Any]:
        registry: Dict[str, Any] = {}
        persona_getter = getattr(self.runtime, "get_persona_snapshot", None)
        if callable(persona_getter):
            try:
                persona = persona_getter()
            except Exception:  # pragma: no cover - defensive
                persona = None
            if persona:
                registry["persona"] = persona
        dream_getter = getattr(self.runtime, "get_dream_snapshot", None)
        if callable(dream_getter):
            try:
                dream = dream_getter()
            except Exception:  # pragma: no cover - defensive
                dream = None
            if dream:
                registry["dream"] = dream
        return registry

    def _build_peer_replay_snapshot(
        self,
        peer: PeerConfig,
        peer_summary: FederationSummary,
        local_replay: ReplayResult,
    ) -> PeerReplaySnapshot:
        identity = peer_summary.fingerprint or peer.node_name
        remote_replay = PassiveReplay(identity, peer_summary).simulate()
        delta = compute_delta(local_replay, remote_replay)
        return PeerReplaySnapshot(
            peer=peer.node_name,
            severity=delta.severity,
            delta=delta,
            last_seen=datetime.now(timezone.utc),
            summary_digest=summary_digest(peer_summary),
        )

    def _load_persisted_replay(self) -> Dict[str, PeerReplaySnapshot]:
        snapshots: Dict[str, PeerReplaySnapshot] = {}
        if not self._replay_dir.exists():
            return snapshots
        for path in self._replay_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # pragma: no cover - defensive
                continue
            if not isinstance(data, Mapping):
                continue
            try:
                snapshot = PeerReplaySnapshot.from_payload(data)
            except Exception:  # pragma: no cover - defensive
                continue
            if snapshot.peer:
                snapshots[snapshot.peer] = snapshot
        return snapshots

    def _persist_replay_snapshot(self, snapshot: PeerReplaySnapshot) -> None:
        target = self._replay_dir / f"{snapshot.peer}.json"
        payload = snapshot.to_payload()
        try:
            target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        except OSError:  # pragma: no cover - defensive
            self.log_cb(f"Failed to persist replay snapshot for {snapshot.peer}")

    def _quarantine_peer_summary(self, path: Path) -> None:
        if not path.exists():
            return
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        target = self._quarantine_dir / f"{path.stem}-{timestamp}{path.suffix}"
        try:
            path.replace(target)
            self.log_cb(f"Quarantined invalid federation summary {path} -> {target}")
        except OSError:  # pragma: no cover - defensive
            self.log_cb(f"Failed to quarantine invalid federation summary {path}")

    def _emit_replay_events(self, updated: Mapping[str, PeerReplaySnapshot]) -> None:
        for snapshot in updated.values():
            publish_event(
                {
                    "kind": "federation",
                    "event": "replay_delta",
                    "peer": snapshot.peer,
                    "severity": snapshot.severity,
                    "ts": snapshot.last_seen.astimezone(timezone.utc).isoformat(),
                }
            )
        severity, peer = self._max_replay_severity()
        publish_event(
            {
                "kind": "federation_replay",
                "severity": severity,
                "peer": peer,
                "ts": datetime.now(timezone.utc).isoformat(),
            }
        )

    def _max_replay_severity(self) -> tuple[ReplaySeverity, Optional[str]]:
        order = {"none": 0, "low": 1, "medium": 2, "high": 3}
        best: ReplaySeverity = "none"
        peer: Optional[str] = None
        for name, snapshot in self._peer_replay.items():
            candidate = snapshot.severity
            if order.get(candidate, 0) >= order.get(best, 0):
                best = candidate
                peer = name
        return best, peer
