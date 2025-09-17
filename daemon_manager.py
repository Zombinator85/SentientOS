"""In-memory daemon lifecycle orchestration utilities."""

from __future__ import annotations

import inspect
import json
import logging
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Dict

from sentientos.daemons import pulse_bus

try:  # pragma: no cover - optional federation support during import
    from sentientos.daemons import pulse_federation
except Exception:  # pragma: no cover - fallback when federation unavailable
    pulse_federation = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)

LEDGER_PATH = Path("/daemon/logs/codex.jsonl")


@dataclass
class DaemonStatus:
    """Represents the most recent lifecycle information for a daemon."""

    name: str
    running: bool = False
    last_restart: datetime | None = None
    last_reason: str | None = None
    last_outcome: str | None = None
    last_error: str | None = None


@dataclass
class _DaemonRecord:
    start_fn: Callable[[], Any]
    stop_fn: Callable[[Any], None]
    instance: Any | None = None
    status: DaemonStatus | None = None


class _DaemonManager:
    def __init__(self) -> None:
        self._lock = Lock()
        self._registry: Dict[str, _DaemonRecord] = {}
        self._subscription: pulse_bus.PulseSubscription | None = None

    # ------------------------------------------------------------------
    # Public API
    def register(
        self, name: str, start_fn: Callable[[], Any], stop_fn: Callable[[Any], None]
    ) -> DaemonStatus:
        if not callable(start_fn):
            raise TypeError("start_fn must be callable")
        if not callable(stop_fn):
            raise TypeError("stop_fn must be callable")

        self._ensure_subscription()

        with self._lock:
            if name in self._registry:
                raise ValueError(f"Daemon '{name}' is already registered")

            record = _DaemonRecord(start_fn=start_fn, stop_fn=stop_fn)
            record.status = DaemonStatus(name=name)
            self._registry[name] = record
            logger.debug("Registered daemon '%s'", name)
            return replace(record.status)

    def restart(
        self,
        name: str,
        *,
        reason: str | None = None,
        requested_by: str | None = None,
        scope: str | None = None,
    ) -> bool:
        reason_text = self._normalize_reason(reason)
        scope_value = self._normalize_scope(scope)
        initiator = self._normalize_peer(requested_by)
        self._ensure_subscription()

        with self._lock:
            record = self._registry.get(name)
            if record is None:
                raise KeyError(f"Daemon '{name}' is not registered")
            previous_instance = record.instance

        stop_error: str | None = None
        start_error: str | None = None
        stop_success = True

        if previous_instance is not None:
            try:
                self._invoke_stop(record.stop_fn, previous_instance)
            except Exception as exc:  # pragma: no cover - defensive logging
                stop_success = False
                stop_error = f"stop_failed:{exc}"
                logger.exception(
                    "Error stopping daemon '%s' during restart", name
                )

        new_instance: Any | None = None
        alive = False

        if stop_success:
            try:
                new_instance = record.start_fn()
                alive = self._is_alive(new_instance)
            except Exception as exc:  # pragma: no cover - defensive logging
                start_error = f"start_failed:{exc}"
                logger.exception(
                    "Error starting daemon '%s' during restart", name
                )
        else:
            new_instance = previous_instance

        if stop_success and new_instance is not None and not alive:
            start_error = start_error or "daemon_not_alive"

        success = bool(stop_success and alive and start_error is None)
        outcome = "success" if success else "failure"
        error_detail = start_error or stop_error

        timestamp = datetime.now(timezone.utc)

        with self._lock:
            status = record.status or DaemonStatus(name=name)
            status.running = success
            status.last_restart = timestamp
            status.last_reason = reason_text
            status.last_outcome = outcome
            status.last_error = error_detail
            record.status = status
            if success:
                record.instance = new_instance
            else:
                record.instance = previous_instance if not stop_success else None

        self._log_restart(
            name,
            reason_text,
            outcome,
            error_detail,
            timestamp,
            initiator,
            scope_value,
        )
        self._publish_restart_event(
            name,
            reason_text,
            outcome,
            error_detail,
            timestamp,
            initiator,
            scope_value,
        )

        return success

    def status(self, name: str) -> DaemonStatus:
        self._ensure_subscription()
        with self._lock:
            record = self._registry.get(name)
            if record is None:
                raise KeyError(f"Daemon '{name}' is not registered")
            status = record.status or DaemonStatus(name=name)
            return replace(status)

    def reset(self) -> None:
        with self._lock:
            self._registry.clear()
            if self._subscription is not None:
                try:
                    if self._subscription.active:
                        self._subscription.unsubscribe()
                finally:
                    self._subscription = None

    # ------------------------------------------------------------------
    # Internal helpers
    def _ensure_subscription(self) -> None:
        with self._lock:
            subscription = self._subscription
        if subscription is not None and subscription.active:
            return

        new_subscription = pulse_bus.subscribe(
            self._handle_pulse_event, priorities=["critical"]
        )
        with self._lock:
            self._subscription = new_subscription

    def _handle_pulse_event(self, event: Dict[str, Any]) -> None:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            return
        action = str(payload.get("action", "")).lower()
        if action != "restart_daemon":
            return
        target = (
            payload.get("daemon")
            or payload.get("daemon_name")
            or payload.get("target")
        )
        if not target:
            return
        scope_value = payload.get("scope")
        scope = self._normalize_scope(scope_value)
        source_peer = self._normalize_peer(event.get("source_peer"))

        if scope == "federated":
            if source_peer in {"", "local"}:
                # Local node is asking peers to restart themselves; ignore locally.
                return
            if not self._is_trusted_peer(source_peer):
                logger.warning(
                    "Rejected federated restart for '%s' from untrusted peer '%s'",
                    target,
                    source_peer,
                )
                return
            if not pulse_bus.verify(event):
                logger.warning(
                    "Rejected federated restart for '%s' due to invalid signature",
                    target,
                )
                return
            requester = source_peer
        else:
            requester = "local"

        reason_value = payload.get("reason") or event.get("event_type")
        reason_text = self._normalize_reason(reason_value)
        try:
            self.restart(
                str(target),
                reason=reason_text,
                requested_by=requester,
                scope=scope,
            )
        except KeyError:
            logger.warning(
                "Received restart request for unregistered daemon '%s'", target
            )

    def _log_restart(
        self,
        name: str,
        reason: str,
        outcome: str,
        error: str | None,
        timestamp: datetime,
        initiator: str,
        scope: str,
    ) -> None:
        entry = {
            "timestamp": timestamp.isoformat(),
            "daemon": name,
            "reason": reason,
            "outcome": outcome,
            "scope": scope,
            "source_peer": initiator,
        }
        if error:
            entry["error"] = error
        try:
            LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
            with LEDGER_PATH.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, sort_keys=True) + "\n")
        except Exception:  # pragma: no cover - best effort logging
            logger.exception("Failed to write daemon restart entry to ledger")

    def _publish_restart_event(
        self,
        name: str,
        reason: str,
        outcome: str,
        error: str | None,
        timestamp: datetime,
        initiator: str,
        scope: str,
    ) -> None:
        payload: Dict[str, Any] = {
            "daemon_name": name,
            "daemon": name,
            "reason": reason,
            "outcome": outcome,
            "scope": scope,
            "requested_by": initiator,
        }
        if error:
            payload["error"] = error
        priority = "info" if outcome == "success" else "critical"
        event = {
            "timestamp": timestamp.isoformat(),
            "source_daemon": "daemon_manager",
            "event_type": "daemon_restart",
            "priority": priority,
            "payload": payload,
        }
        try:
            pulse_bus.publish(event)
        except Exception:  # pragma: no cover - pulse failures shouldn't crash
            logger.exception("Failed to publish daemon restart event to pulse bus")

    def _is_alive(self, instance: Any) -> bool:
        if instance is None:
            return False
        if hasattr(instance, "is_alive") and callable(instance.is_alive):
            try:
                return bool(instance.is_alive())
            except Exception:
                return False
        if hasattr(instance, "alive"):
            try:
                return bool(getattr(instance, "alive"))
            except Exception:
                return False
        return True

    def _invoke_stop(self, stop_fn: Callable[[Any], None], instance: Any) -> None:
        try:
            signature = inspect.signature(stop_fn)
        except (TypeError, ValueError):
            stop_fn(instance)
            return

        if not signature.parameters:
            stop_fn()
            return
        stop_fn(instance)

    def _normalize_reason(self, reason: Any) -> str:
        if isinstance(reason, str):
            text = reason.strip()
            return text or "unspecified"
        if reason is None:
            return "unspecified"
        return str(reason)

    def _normalize_scope(self, scope: Any) -> str:
        if isinstance(scope, str) and scope.strip().lower() == "federated":
            return "federated"
        return "local"

    def _normalize_peer(self, peer: Any) -> str:
        if isinstance(peer, str):
            value = peer.strip()
            return value or "local"
        if peer is None:
            return "local"
        return str(peer)

    def _is_trusted_peer(self, peer: str) -> bool:
        if not peer or peer == "local":
            return False
        if pulse_federation is None:
            return False
        try:
            if not pulse_federation.is_enabled():
                return False
            return peer in pulse_federation.peers()
        except Exception:  # pragma: no cover - defensive fallback
            return False


_MANAGER = _DaemonManager()


def register(
    name: str, start_fn: Callable[[], Any], stop_fn: Callable[[Any], None]
) -> DaemonStatus:
    """Register a daemon lifecycle with the global manager."""

    return _MANAGER.register(name, start_fn, stop_fn)


def restart(
    name: str,
    *,
    reason: str | None = None,
    requested_by: str | None = None,
    scope: str | None = None,
) -> bool:
    """Restart a registered daemon and return whether it succeeded."""

    return _MANAGER.restart(
        name,
        reason=reason,
        requested_by=requested_by,
        scope=scope,
    )


def status(name: str) -> DaemonStatus:
    """Return the recorded status for ``name``."""

    return _MANAGER.status(name)


def reset() -> None:
    """Reset the global daemon manager (primarily for testing)."""

    _MANAGER.reset()


__all__ = [
    "DaemonStatus",
    "register",
    "restart",
    "status",
    "reset",
]

