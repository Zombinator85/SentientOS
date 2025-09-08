"""Simple network monitoring daemon.

This module provides a minimal :class:`NetworkDaemon` used by the tests.
It tracks bandwidth usage, open ports and federation reachability while
collecting emitted events in memory for inspection.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List


class NetworkDaemon:
    """A lightweight network daemon for testing purposes.

    Parameters
    ----------
    config:
        Configuration dictionary. Relevant keys:
        ``network_policies`` with ``allowed_ports``, ``blocked_ports`` and
        ``bandwidth_limit`` (kbps) as well as ``federation_peer_ip`` and
        ``log_dir`` for event logging.
    """

    def __init__(self, config: dict) -> None:
        policies = config.get("network_policies", {})
        self.allowed_ports = set(policies.get("allowed_ports", []))
        self.blocked_ports = set(policies.get("blocked_ports", []))
        self.bandwidth_limit = float(policies.get("bandwidth_limit", 0))
        self.peer_ip = config.get("federation_peer_ip")
        self.log_dir = Path(config.get("log_dir", "."))

        self.events: List[str] = []
        self.resync_queued = False

    # ------------------------------------------------------------------
    # Internal helpers
    def _log(self, message: str) -> None:
        """Record an event message in memory and append to a log file."""
        self.events.append(message)
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            with (self.log_dir / "network_daemon.log").open("a", encoding="utf-8") as fh:
                fh.write(message + "\n")
        except Exception:
            # Logging failure should not break daemon behaviour
            pass

    # ------------------------------------------------------------------
    # Event checks
    def _check_bandwidth(self, usage_kbps: float) -> None:
        """Emit an event if bandwidth exceeds the configured limit."""
        # Only log when usage exceeds limit
        if self.bandwidth_limit and usage_kbps > self.bandwidth_limit:
            self._log(f"bandwidth_saturation:{usage_kbps}")

    def _check_ports(self, open_ports: Iterable[int]) -> None:
        """Inspect open ports and emit events for unexpected or blocked ones."""
        for port in open_ports:
            if port in self.blocked_ports:
                self._log(f"blocked_port:{port}")
            elif port not in self.allowed_ports:
                self._log(f"unexpected_port:{port}")

    def _check_federation(self, reachable: bool) -> None:
        """Mark resync if federation peer is unreachable."""
        if not reachable:
            self.resync_queued = True
            self._log("federation_link_down")

