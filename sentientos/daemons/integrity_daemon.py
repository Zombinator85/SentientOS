"""Stub integrity daemon that listens to pulse bus events."""

from __future__ import annotations

import json
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Deque, List

from . import pulse_bus


class IntegrityDaemon:
    """Minimal daemon that records every pulse broadcast."""

    def __init__(self, *, hungry_eyes: object | None = None, hungry_threshold: float = 0.5) -> None:
        self.received_events: List[dict[str, object]] = []
        self.messages: List[str] = []
        self.invalid_events: List[dict[str, object]] = []
        self.alerts: List[dict[str, object]] = []
        self._restart_window = timedelta(minutes=5)
        self._invalid_times: Deque[datetime] = deque()
        self._last_restart_request: datetime | None = None
        self._hungry_eyes = hungry_eyes
        self._hungry_threshold = float(hungry_threshold)
        self._subscription: pulse_bus.PulseSubscription | None = pulse_bus.subscribe(
            self._handle_event
        )

    def _handle_event(self, event: dict[str, object]) -> None:
        self.received_events.append(event)
        message = json.dumps(event, sort_keys=True)
        self.messages.append(message)
        priority = str(event.get("priority", "info")).lower()
        if pulse_bus.verify(event):
            print(f"[IntegrityDaemon] {message}")
            self._integrate_hungry_eyes(event)
            if priority == "critical":
                self.alerts.append(event)
                print(f"[IntegrityDaemon][ALERT] {message}")
            return
        warning = f"INVALID SIGNATURE: {message}"
        self.invalid_events.append(event)
        self.messages.append(warning)
        self.alerts.append(event)
        print(f"[IntegrityDaemon] {warning}")
        self._record_invalid_signature()
        violation_timestamp = datetime.now(timezone.utc).isoformat()
        payload = {
            "timestamp": violation_timestamp,
            "source_event": {
                "source_daemon": str(event.get("source_daemon", "unknown")),
                "event_type": str(event.get("event_type", "unknown")),
            },
            "detail": "signature_mismatch",
        }
        pulse_bus.publish(
            {
                "timestamp": violation_timestamp,
                "source_daemon": "integrity",
                "event_type": "integrity_violation",
                "priority": "critical",
                "payload": payload,
            }
        )

    def _integrate_hungry_eyes(self, event: dict[str, object]) -> None:
        consult = self._consult_hungry_eyes(event)
        if consult is None:
            return
        proof_report = event.get("proof_report")
        if not isinstance(proof_report, dict):
            proof_report = {}
            event["proof_report"] = proof_report
        proof_report["hungry_eyes"] = consult
        integrity_valid = bool(proof_report.get("valid", False))
        risk = consult.get("risk", 1.0)
        threshold = consult.get("threshold", self._hungry_threshold)
        auto_commit = bool(integrity_valid and risk < threshold)
        proof_report["dual_control"] = {
            "integrity_valid": integrity_valid,
            "hungry_eyes_risk": risk,
            "threshold": threshold,
            "auto_commit": auto_commit,
        }
        status_message = (
            "Approval granted"
            if auto_commit
            else "Approval withheld"
        )
        log_message = (
            f"[IntegrityDaemon][DualControl] {status_message}: risk={risk:.3f}, threshold={threshold:.3f}"
        )
        self.messages.append(log_message)
        print(log_message)
        if not auto_commit:
            self.alerts.append(event)

    def _consult_hungry_eyes(self, event: dict[str, object]) -> dict[str, float | str] | None:
        observer = self._hungry_eyes
        if observer is None:
            return None
        mode = str(getattr(observer, "mode", "observe")).lower()
        if mode not in {"observe", "repair", "full", "expand"}:
            return None

        # Primary path: a modern sentinel exposes an ``assess`` method returning
        # a mapping with at least ``risk`` and ``threshold`` entries.
        if hasattr(observer, "assess"):
            try:
                assessment = observer.assess(event)
            except Exception:  # pragma: no cover - advisory only
                assessment = None
            if isinstance(assessment, dict) and "risk" in assessment:
                payload = dict(assessment)
                payload.setdefault("mode", mode)
                payload.setdefault("threshold", self._hungry_threshold)
                return payload

        # Legacy fall-back: the observer may expose scalar risk functions.
        risk_score = None
        for attr in ("risk_score", "score"):
            if hasattr(observer, attr):
                candidate = getattr(observer, attr)
                try:
                    risk_score = float(candidate(event))
                except Exception:  # pragma: no cover - advisory only
                    risk_score = None
                if risk_score is not None:
                    break
        if risk_score is None:
            return None
        return {
            "mode": mode,
            "risk": risk_score,
            "threshold": getattr(observer, "threshold", self._hungry_threshold),
        }

    def stop(self) -> None:
        """Unsubscribe from the pulse bus."""

        if self._subscription and self._subscription.active:
            self._subscription.unsubscribe()
            self._subscription = None

    def _record_invalid_signature(self) -> None:
        now = datetime.now(timezone.utc)
        self._invalid_times.append(now)
        cutoff = now - self._restart_window
        while self._invalid_times and self._invalid_times[0] < cutoff:
            self._invalid_times.popleft()
        if len(self._invalid_times) < 3:
            return
        if self._last_restart_request and now - self._last_restart_request < self._restart_window:
            return
        self._publish_restart_request("signature_mismatch")
        self._last_restart_request = now

    def _publish_restart_request(self, reason: str) -> None:
        payload = {
            "action": "restart_daemon",
            "daemon": "integrity",
            "reason": reason,
        }
        pulse_bus.publish(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source_daemon": "integrity",
                "event_type": "restart_request",
                "priority": "critical",
                "payload": payload,
            }
        )
