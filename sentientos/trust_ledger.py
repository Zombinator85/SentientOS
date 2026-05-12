"""Deterministic federation trust ledger and bounded peer probe scheduling."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Mapping


_TRUST_ORDER = {"trusted": 0, "watched": 1, "degraded": 2, "quarantined": 3, "incompatible": 4}


def _as_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def _probe_history_from(value: object) -> dict[str, int]:
    base = {"ok": 0, "warn": 0, "fail": 0, "skipped": 0}
    if not isinstance(value, Mapping):
        return base
    for key in tuple(base):
        base[key] = max(0, _as_int(value.get(key), 0))
    return base


@dataclass(frozen=True)
class PeerTrustSnapshot:
    peer_id: str
    trust_state: str
    trust_reasons: list[str]
    trust_score_class: str
    reconciliation_needed: bool
    last_probe_at: str | None
    last_probe_status: str
    probe_history: dict[str, int]
    divergence_events: int
    epoch_mismatch_events: int
    digest_mismatch_events: int
    quorum_success_events: int
    quorum_failure_events: int
    replay_events: int
    control_denied_events: int

    def to_dict(self) -> dict[str, object]:
        return {
            "peer_id": self.peer_id,
            "trust_state": self.trust_state,
            "trust_reasons": list(self.trust_reasons),
            "trust_score_class": self.trust_score_class,
            "reconciliation_needed": self.reconciliation_needed,
            "last_probe_at": self.last_probe_at,
            "last_probe_status": self.last_probe_status,
            "probe_history": dict(self.probe_history),
            "divergence_events": self.divergence_events,
            "epoch_mismatch_events": self.epoch_mismatch_events,
            "digest_mismatch_events": self.digest_mismatch_events,
            "quorum_success_events": self.quorum_success_events,
            "quorum_failure_events": self.quorum_failure_events,
            "replay_events": self.replay_events,
            "control_denied_events": self.control_denied_events,
        }


class FederationTrustLedger:
    """Append-only and bounded trust signals for federation peers."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._governor_root = Path(os.getenv("SENTIENTOS_GOVERNOR_ROOT", "/glow/governor"))
        self._federation_root = Path(os.getenv("SENTIENTOS_FEDERATION_ROOT", "/glow/federation"))
        self._history_limit = self._env_int("SENTIENTOS_TRUST_LEDGER_HISTORY_LIMIT", 128)
        self._event_log_limit = self._env_int("SENTIENTOS_TRUST_LEDGER_EVENT_LOG_LIMIT", 512)
        self._probe_plan_limit = self._env_int("SENTIENTOS_TRUST_PROBE_PLAN_LIMIT", 6)
        self._probe_plan_warn_limit = self._env_int("SENTIENTOS_TRUST_PROBE_PLAN_WARN_LIMIT", 3)
        self._probe_plan_storm_limit = self._env_int("SENTIENTOS_TRUST_PROBE_PLAN_STORM_LIMIT", 1)
        self._peer_state: dict[str, dict[str, object]] = {}
        self._events: list[dict[str, object]] = []
        self._schema_version = 1
        self._recovery_status: dict[str, object] = {
            "schema_version": self._schema_version,
            "recovered_from_state": False,
            "recovered_from_events": False,
            "recovery_degraded": False,
            "recovery_findings": [],
        }
        self._recover()

    def _record_finding(self, finding: str) -> None:
        findings = self._recovery_status.get("recovery_findings")
        if not isinstance(findings, list):
            findings = []
            self._recovery_status["recovery_findings"] = findings
        findings.append(finding)
        self._recovery_status["recovery_degraded"] = True

    def _recover(self) -> None:
        state_path = self._federation_root / "trust_ledger_state.json"
        events_path = self._federation_root / "trust_ledger_events.jsonl"
        state_ok = self._recover_from_state(state_path)
        if not state_ok:
            self._recover_from_events(events_path)
            if not state_path.exists() and not events_path.exists():
                self._record_finding("recovery_genesis_empty")

    def _recover_from_state(self, path: Path) -> bool:
        if not path.exists():
            self._record_finding("state_missing")
            return False
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._record_finding("state_unreadable_or_invalid_json")
            return False
        if not isinstance(payload, Mapping):
            self._record_finding("state_invalid_shape")
            return False
        if _as_int(payload.get("schema_version"), -1) != self._schema_version:
            self._record_finding("state_schema_mismatch")
            return False
        rows = payload.get("peer_states")
        if not isinstance(rows, list):
            self._record_finding("state_peer_states_missing")
            return False
        loaded: dict[str, dict[str, object]] = {}
        for row in rows:
            if not isinstance(row, Mapping):
                self._record_finding("state_peer_row_invalid")
                continue
            peer_id = str(row.get("peer_id") or "").strip()
            if not peer_id:
                self._record_finding("state_peer_missing_id")
                continue
            state = self._ensure_peer(peer_id)
            for key in (
                "divergence_events",
                "epoch_mismatch_events",
                "digest_mismatch_events",
                "quorum_success_events",
                "quorum_failure_events",
                "replay_events",
                "control_denied_events",
            ):
                state[key] = max(0, _as_int(row.get(key), 0))
            state["last_probe_status"] = str(row.get("last_probe_status") or "never")
            lpa = row.get("last_probe_at")
            state["last_probe_at"] = str(lpa) if isinstance(lpa, str) else None
            state["probe_history"] = _probe_history_from(row.get("probe_history"))
            self._refresh_state(state)
            loaded[peer_id] = state
        self._peer_state = loaded
        self._recovery_status["recovered_from_state"] = True
        self._detect_state_event_contradictions(path.parent / "trust_ledger_events.jsonl")
        return True

    def _detect_state_event_contradictions(self, events_path: Path) -> None:
        if not events_path.exists():
            return
        latest: dict[str, str] = {}
        try:
            lines = events_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            self._record_finding("events_unreadable_for_contradiction_check")
            return
        for line in lines:
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, Mapping):
                continue
            peer_id = str(event.get("peer_id") or "").strip()
            trust_state = str(event.get("trust_state") or "").strip()
            if peer_id and trust_state:
                latest[peer_id] = trust_state
        for peer_id, logged_state in latest.items():
            current = self._snapshot_for(peer_id).trust_state
            if current != logged_state:
                self._record_finding(f"state_event_contradiction:{peer_id}:{logged_state}!={current}")

    def _apply_event(self, event: Mapping[str, object]) -> bool:
        event_type = str(event.get("event") or "")
        peer_id = str(event.get("peer_id") or "").strip()
        if event_type != "probe_schedule" and not peer_id:
            self._record_finding("event_missing_peer_id")
            return False
        if event_type == "probe":
            status = str(event.get("status") or "warn")
            state = self._ensure_peer(peer_id)
            history = _probe_history_from(state.get("probe_history"))
            history[status if status in history else "warn"] += 1
            state["probe_history"] = history
            if status == "fail":
                self._bounded_increment(state, "divergence_events")
            elif status == "warn":
                self._bounded_increment(state, "quorum_failure_events")
            self._refresh_state(state)
            return True
        if event_type == "governance_evaluation":
            state = self._ensure_peer(peer_id)
            if str(event.get("digest_status") or "") in {"missing", "incompatible"}:
                self._bounded_increment(state, "digest_mismatch_events")
            if str(event.get("epoch_status") or "") == "unexpected":
                self._bounded_increment(state, "epoch_mismatch_events")
            denial = str(event.get("denial_cause") or "")
            if denial == "quorum_failure" or not bool(event.get("quorum_satisfied", False)):
                self._bounded_increment(state, "quorum_failure_events")
            if bool(event.get("quorum_satisfied", False)) and denial == "none":
                self._bounded_increment(state, "quorum_success_events")
            if denial in {"digest_mismatch", "trust_epoch"}:
                self._bounded_increment(state, "divergence_events")
            self._refresh_state(state)
            return True
        if event_type == "epoch_classification":
            state = self._ensure_peer(peer_id)
            if str(event.get("classification") or "") in {"revoked_epoch", "unknown_epoch", "invalid_signature"}:
                self._bounded_increment(state, "epoch_mismatch_events")
                self._bounded_increment(state, "divergence_events")
            self._refresh_state(state)
            return True
        if event_type == "replay_duplicate":
            state = self._ensure_peer(peer_id)
            self._bounded_increment(state, "replay_events")
            self._refresh_state(state)
            return True
        if event_type == "control_attempt":
            state = self._ensure_peer(peer_id)
            if not bool(event.get("allowed", False)):
                self._bounded_increment(state, "control_denied_events")
            self._refresh_state(state)
            return True
        if event_type == "probe_schedule":
            return True
        self._record_finding(f"unknown_event_type:{event_type or 'missing'}")
        return False

    def _recover_from_events(self, path: Path) -> bool:
        if not path.exists():
            self._record_finding("events_missing")
            return False
        rebuilt: dict[str, dict[str, object]] = {}
        events: list[dict[str, object]] = []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            self._record_finding("events_unreadable")
            return False
        for idx, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                self._record_finding(f"event_invalid_json_line:{idx}")
                continue
            if not isinstance(parsed, Mapping):
                self._record_finding(f"event_invalid_shape_line:{idx}")
                continue
            events.append(dict(parsed))
            self._apply_event(parsed)
            rebuilt = self._peer_state
        self._peer_state = rebuilt
        self._events = events[-self._event_log_limit :]
        self._recovery_status["recovered_from_events"] = True
        return True

    def recovery_status(self) -> dict[str, object]:
        with self._lock:
            return {
                "schema_version": self._schema_version,
                "recovered_from_state": bool(self._recovery_status.get("recovered_from_state", False)),
                "recovered_from_events": bool(self._recovery_status.get("recovered_from_events", False)),
                "recovery_degraded": bool(self._recovery_status.get("recovery_degraded", False)),
                "recovery_findings": [str(item) for item in self._recovery_status.get("recovery_findings", []) if isinstance(item, str)],
            }

    @staticmethod
    def _env_int(name: str, default: int) -> int:
        value = os.getenv(name)
        if value is None:
            return default
        try:
            return max(1, int(value))
        except ValueError:
            return default

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _ensure_peer(self, peer_id: str) -> dict[str, object]:
        normalized = peer_id.strip() or "unknown-peer"
        state = self._peer_state.get(normalized)
        if state is not None:
            return state
        state = {
            "peer_id": normalized,
            "last_probe_at": None,
            "last_probe_status": "never",
            "probe_history": {"ok": 0, "warn": 0, "fail": 0, "skipped": 0},
            "probe_sequence": [],
            "divergence_events": 0,
            "epoch_mismatch_events": 0,
            "digest_mismatch_events": 0,
            "quorum_success_events": 0,
            "quorum_failure_events": 0,
            "replay_events": 0,
            "control_denied_events": 0,
            "trust_state": "trusted",
            "trust_reasons": ["no_negative_signals"],
            "reconciliation_needed": False,
            "updated_at": self._now(),
        }
        self._peer_state[normalized] = state
        return state

    def _bounded_increment(self, state: dict[str, object], key: str, amount: int = 1) -> None:
        current = _as_int(state.get(key), 0)
        state[key] = min(9999, current + amount)

    def _derive_state(self, state: Mapping[str, object]) -> tuple[str, list[str], bool]:
        reasons: list[str] = []
        digest = _as_int(state.get("digest_mismatch_events"), 0)
        epoch = _as_int(state.get("epoch_mismatch_events"), 0)
        divergence = _as_int(state.get("divergence_events"), 0)
        replay = _as_int(state.get("replay_events"), 0)
        denied = _as_int(state.get("control_denied_events"), 0)
        quorum_fail = _as_int(state.get("quorum_failure_events"), 0)
        quorum_ok = _as_int(state.get("quorum_success_events"), 0)
        probe_fail = _probe_history_from(state.get("probe_history")).get("fail", 0)

        if digest >= 3 or epoch >= 3:
            reasons.append("repeated_protocol_mismatch")
            return "incompatible", reasons, True
        if digest >= 1:
            reasons.append("digest_mismatch")
        if epoch >= 1:
            reasons.append("epoch_mismatch")
        if divergence >= 3 or quorum_fail >= 3:
            reasons.append("repeated_divergence_or_quorum_failure")
        if replay >= 3:
            reasons.append("replay_duplication_repeated")
        if denied >= 2:
            reasons.append("federated_control_denied")
        if probe_fail >= 3:
            reasons.append("probe_failures_repeated")

        if any(reason in reasons for reason in {"repeated_divergence_or_quorum_failure", "probe_failures_repeated", "federated_control_denied"}):
            return "quarantined", sorted(set(reasons)), True
        if reasons:
            if replay >= 1 or divergence >= 1 or quorum_fail >= 1:
                return "degraded", sorted(set(reasons)), True
            return "watched", sorted(set(reasons)), False
        if quorum_ok >= 1:
            return "trusted", ["quorum_compatible"], False
        return "trusted", ["no_negative_signals"], False

    def _refresh_state(self, state: dict[str, object]) -> None:
        trust_state, reasons, reconciliation_needed = self._derive_state(state)
        state["trust_state"] = trust_state
        state["trust_reasons"] = reasons
        state["reconciliation_needed"] = reconciliation_needed
        state["updated_at"] = self._now()

    def _append_event(self, payload: dict[str, object]) -> None:
        self._events.append(dict(payload))
        if len(self._events) > self._event_log_limit:
            self._events = self._events[-self._event_log_limit :]

    def _snapshot_for(self, peer_id: str) -> PeerTrustSnapshot:
        state = self._ensure_peer(peer_id)
        probe_history = _probe_history_from(state.get("probe_history"))
        trust_state = str(state.get("trust_state") or "trusted")
        reasons = state.get("trust_reasons")
        trust_reasons = [str(item) for item in reasons] if isinstance(reasons, list) else ["unknown"]
        return PeerTrustSnapshot(
            peer_id=str(state.get("peer_id") or peer_id),
            trust_state=trust_state,
            trust_reasons=sorted(set(trust_reasons)),
            trust_score_class=trust_state,
            reconciliation_needed=bool(state.get("reconciliation_needed", False)),
            last_probe_at=str(state.get("last_probe_at")) if isinstance(state.get("last_probe_at"), str) else None,
            last_probe_status=str(state.get("last_probe_status") or "never"),
            probe_history={
                "ok": _as_int(probe_history.get("ok"), 0),
                "warn": _as_int(probe_history.get("warn"), 0),
                "fail": _as_int(probe_history.get("fail"), 0),
                "skipped": _as_int(probe_history.get("skipped"), 0),
            },
            divergence_events=_as_int(state.get("divergence_events"), 0),
            epoch_mismatch_events=_as_int(state.get("epoch_mismatch_events"), 0),
            digest_mismatch_events=_as_int(state.get("digest_mismatch_events"), 0),
            quorum_success_events=_as_int(state.get("quorum_success_events"), 0),
            quorum_failure_events=_as_int(state.get("quorum_failure_events"), 0),
            replay_events=_as_int(state.get("replay_events"), 0),
            control_denied_events=_as_int(state.get("control_denied_events"), 0),
        )

    def record_probe(self, peer_id: str, *, status: str, actor: str, reason: str) -> PeerTrustSnapshot:
        normalized = status if status in {"ok", "warn", "fail", "skipped"} else "warn"
        with self._lock:
            state = self._ensure_peer(peer_id)
            history = _probe_history_from(state.get("probe_history"))
            state["probe_history"] = history
            history[normalized] = _as_int(history.get(normalized), 0) + 1
            sequence = state.get("probe_sequence")
            if not isinstance(sequence, list):
                sequence = []
                state["probe_sequence"] = sequence
            sequence.append({"status": normalized, "at": self._now(), "reason": reason})
            if len(sequence) > self._history_limit:
                state["probe_sequence"] = sequence[-self._history_limit :]
            state["last_probe_at"] = self._now()
            state["last_probe_status"] = normalized
            if normalized == "fail":
                self._bounded_increment(state, "divergence_events")
            elif normalized == "warn":
                self._bounded_increment(state, "quorum_failure_events")
            self._refresh_state(state)
            snapshot = self._snapshot_for(peer_id)
            self._append_event(
                {
                    "timestamp": self._now(),
                    "event": "probe",
                    "actor": actor,
                    "peer_id": peer_id,
                    "status": normalized,
                    "reason": reason,
                    "trust_state": snapshot.trust_state,
                }
            )
            self._write_artifacts()
            return snapshot

    def record_governance_evaluation(self, peer_id: str, evaluation: Mapping[str, object], *, actor: str) -> PeerTrustSnapshot:
        with self._lock:
            state = self._ensure_peer(peer_id)
            digest_status = str(evaluation.get("digest_status") or "missing")
            epoch_status = str(evaluation.get("epoch_status") or "unknown")
            denial = str(evaluation.get("denial_cause") or "none")
            quorum_satisfied = bool(evaluation.get("quorum_satisfied", False))
            if digest_status in {"missing", "incompatible"}:
                self._bounded_increment(state, "digest_mismatch_events")
            if epoch_status == "unexpected":
                self._bounded_increment(state, "epoch_mismatch_events")
            if denial == "quorum_failure" or not quorum_satisfied:
                self._bounded_increment(state, "quorum_failure_events")
            if quorum_satisfied and denial == "none":
                self._bounded_increment(state, "quorum_success_events")
            if denial in {"digest_mismatch", "trust_epoch"}:
                self._bounded_increment(state, "divergence_events")
            self._refresh_state(state)
            snapshot = self._snapshot_for(peer_id)
            self._append_event(
                {
                    "timestamp": self._now(),
                    "event": "governance_evaluation",
                    "actor": actor,
                    "peer_id": peer_id,
                    "digest_status": digest_status,
                    "epoch_status": epoch_status,
                    "quorum_satisfied": quorum_satisfied,
                    "denial_cause": denial,
                    "trust_state": snapshot.trust_state,
                }
            )
            self._write_artifacts()
            return snapshot

    def record_epoch_classification(self, peer_id: str, *, classification: str, actor: str) -> PeerTrustSnapshot:
        with self._lock:
            state = self._ensure_peer(peer_id)
            if classification in {"revoked_epoch", "unknown_epoch", "invalid_signature"}:
                self._bounded_increment(state, "epoch_mismatch_events")
                self._bounded_increment(state, "divergence_events")
            self._refresh_state(state)
            snapshot = self._snapshot_for(peer_id)
            self._append_event(
                {
                    "timestamp": self._now(),
                    "event": "epoch_classification",
                    "actor": actor,
                    "peer_id": peer_id,
                    "classification": classification,
                    "trust_state": snapshot.trust_state,
                }
            )
            self._write_artifacts()
            return snapshot

    def record_replay_signal(self, peer_id: str, *, actor: str, event_hash: str) -> PeerTrustSnapshot:
        with self._lock:
            state = self._ensure_peer(peer_id)
            self._bounded_increment(state, "replay_events")
            self._refresh_state(state)
            snapshot = self._snapshot_for(peer_id)
            self._append_event(
                {
                    "timestamp": self._now(),
                    "event": "replay_duplicate",
                    "actor": actor,
                    "peer_id": peer_id,
                    "event_hash": event_hash,
                    "trust_state": snapshot.trust_state,
                }
            )
            self._write_artifacts()
            return snapshot

    def record_control_attempt(self, peer_id: str, *, allowed: bool, reason: str, actor: str) -> PeerTrustSnapshot:
        with self._lock:
            state = self._ensure_peer(peer_id)
            if not allowed:
                self._bounded_increment(state, "control_denied_events")
            self._refresh_state(state)
            snapshot = self._snapshot_for(peer_id)
            self._append_event(
                {
                    "timestamp": self._now(),
                    "event": "control_attempt",
                    "actor": actor,
                    "peer_id": peer_id,
                    "allowed": allowed,
                    "reason": reason,
                    "trust_state": snapshot.trust_state,
                }
            )
            self._write_artifacts()
            return snapshot

    def get_peer_trust(self, peer_id: str) -> PeerTrustSnapshot:
        with self._lock:
            return self._snapshot_for(peer_id)

    def _probe_slots_for_pressure(self, *, pressure_composite: float, scheduling_window_open: bool, storm_active: bool) -> int:
        if not scheduling_window_open:
            return 0
        if storm_active:
            return self._probe_plan_storm_limit
        if pressure_composite >= 0.7:
            return self._probe_plan_warn_limit
        return self._probe_plan_limit

    def build_probe_schedule(
        self,
        *,
        peer_ids: list[str],
        pressure_composite: float,
        scheduling_window_open: bool,
        storm_active: bool,
    ) -> dict[str, object]:
        with self._lock:
            slots = self._probe_slots_for_pressure(
                pressure_composite=pressure_composite,
                scheduling_window_open=scheduling_window_open,
                storm_active=storm_active,
            )
            peers = [self._snapshot_for(peer_id) for peer_id in sorted(set(peer_ids))]
            prioritized = sorted(
                peers,
                key=lambda item: (
                    _TRUST_ORDER.get(item.trust_state, 9),
                    -item.divergence_events,
                    -item.epoch_mismatch_events,
                    -item.digest_mismatch_events,
                    item.peer_id,
                ),
                reverse=True,
            )
            selected = prioritized[:slots]
            pending: list[dict[str, object]] = []
            for snapshot in selected:
                action = "probe_peer_nodes"
                if snapshot.trust_state in {"degraded", "quarantined", "incompatible"}:
                    action = "reconcile_divergent_nodes"
                elif snapshot.digest_mismatch_events > 0 or snapshot.epoch_mismatch_events > 0:
                    action = "verify_attestation_ring"
                pending.append(
                    {
                        "peer_id": snapshot.peer_id,
                        "action": action,
                        "trust_state": snapshot.trust_state,
                        "reason": ",".join(snapshot.trust_reasons),
                    }
                )
            schedule = {
                "schema_version": 1,
                "generated_at": self._now(),
                "scheduling_window_open": scheduling_window_open,
                "storm_active": storm_active,
                "pressure_composite": round(pressure_composite, 4),
                "probe_slots": slots,
                "pending_actions": pending,
                "blocked_actions": [
                    item.peer_id
                    for item in peers
                    if item.peer_id not in {entry["peer_id"] for entry in pending}
                ],
            }
            self._write_schedule(schedule)
            self._append_event(
                {
                    "timestamp": self._now(),
                    "event": "probe_schedule",
                    "slots": slots,
                    "storm_active": storm_active,
                    "scheduling_window_open": scheduling_window_open,
                    "pressure_composite": round(pressure_composite, 4),
                    "pending_count": len(pending),
                }
            )
            self._write_artifacts()
            return schedule

    def _write_schedule(self, payload: Mapping[str, object]) -> None:
        for root in (self._governor_root, self._federation_root):
            root.mkdir(parents=True, exist_ok=True)
            (root / "federation_probe_schedule.json").write_text(
                json.dumps(dict(payload), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

    def _write_artifacts(self) -> None:
        peers = [self._snapshot_for(name).to_dict() for name in sorted(self._peer_state)]
        payload = {
            "schema_version": 1,
            "generated_at": self._now(),
            "peer_count": len(peers),
            "peer_states": peers,
            "state_summary": {
                "trusted": len([item for item in peers if item["trust_state"] == "trusted"]),
                "watched": len([item for item in peers if item["trust_state"] == "watched"]),
                "degraded": len([item for item in peers if item["trust_state"] == "degraded"]),
                "quarantined": len([item for item in peers if item["trust_state"] == "quarantined"]),
                "incompatible": len([item for item in peers if item["trust_state"] == "incompatible"]),
            },
        }
        for root in (self._governor_root, self._federation_root):
            root.mkdir(parents=True, exist_ok=True)
            self._atomic_write_text(root / "trust_ledger_state.json", json.dumps(payload, indent=2, sort_keys=True) + "\n")
            event_payload = "".join(json.dumps(entry, sort_keys=True) + "\n" for entry in self._events[-self._event_log_limit :])
            self._atomic_write_text(root / "trust_ledger_events.jsonl", event_payload)

    @staticmethod
    def _atomic_write_text(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()


_LEDGER = FederationTrustLedger()


def get_trust_ledger() -> FederationTrustLedger:
    return _LEDGER


def reset_trust_ledger() -> None:
    global _LEDGER
    _LEDGER = FederationTrustLedger()
