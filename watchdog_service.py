"""Portable watchdog primitives for service-mode orchestration tests."""

from __future__ import annotations

import socket
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional

CheckCallable = Callable[[], tuple[bool, Optional[str]]]
RestartCallable = Callable[[], None]


@dataclass
class _Monitor:
    name: str
    check: CheckCallable
    restart: Optional[RestartCallable] = None
    last_ok: bool = True
    last_checked: float = 0.0
    failures: int = 0
    restarts: int = 0
    message: Optional[str] = None

    def snapshot(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "healthy": self.last_ok,
            "checked_at": self.last_checked,
            "failures": self.failures,
            "restarts": self.restarts,
            "message": self.message,
        }


class WatchdogService:
    """Monitors health checks and invokes restart hooks on failure."""

    def __init__(self, *, interval: float = 5.0) -> None:
        self._interval = interval
        self._monitors: Dict[str, _Monitor] = {}
        self._lock = threading.RLock()

    def register_check(
        self,
        name: str,
        check: CheckCallable,
        *,
        restart: Optional[RestartCallable] = None,
    ) -> None:
        with self._lock:
            self._monitors[name] = _Monitor(name=name, check=check, restart=restart)

    def register_port(
        self,
        name: str,
        host: str,
        port: int,
        *,
        timeout: float = 0.5,
        restart: Optional[RestartCallable] = None,
    ) -> None:
        def _probe() -> tuple[bool, Optional[str]]:
            try:
                with socket.create_connection((host, port), timeout=timeout):
                    return True, None
            except OSError as exc:
                return False, str(exc)

        self.register_check(name, _probe, restart=restart)

    def probe_once(self) -> None:
        with self._lock:
            for monitor in self._monitors.values():
                ok, message = monitor.check()
                monitor.last_checked = time.time()
                monitor.last_ok = ok
                monitor.message = message
                if ok:
                    monitor.failures = 0
                    continue
                monitor.failures += 1
                if monitor.restart:
                    monitor.restart()
                    monitor.restarts += 1

    def snapshot(self) -> Dict[str, object]:
        with self._lock:
            data = [monitor.snapshot() for monitor in self._monitors.values()]
        healthy = all(item["healthy"] for item in data) if data else True
        return {"checks": data, "healthy": healthy, "interval": self._interval}

    def report_heartbeat(self, name: str) -> None:
        with self._lock:
            monitor = self._monitors.get(name)
            if monitor is None:
                return
            monitor.last_ok = True
            monitor.last_checked = time.time()
            monitor.failures = 0
            monitor.message = None


__all__ = ["WatchdogService"]
