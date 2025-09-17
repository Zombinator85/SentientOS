"""Simple network monitoring daemon.

This module provides a minimal :class:`NetworkDaemon` used by the tests.
It tracks bandwidth usage, open ports and federation reachability while
collecting emitted events in memory for inspection.
"""

from __future__ import annotations

import json
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Deque, Dict, Iterable, List

from sentientos.daemons import pulse_bus


class NetworkDaemon:
    """A lightweight network daemon for testing purposes.

    Parameters
    ----------
    config:
        Configuration dictionary. Relevant keys:
        ``network_policies`` may include ``allowed_ports``, ``blocked_ports``,
        ``bandwidth_limit`` (kbps) and structured ``rules`` for enforcement.
        ``federation_peers`` provides the list of reachable nodes for
        federation and ``federation_enabled`` toggles whether reachability
        monitoring should enqueue resync requests. ``log_dir`` configures
        detection logging and ``enforcement_enabled`` toggles ledger-backed
        enforcement.
    """

    def __init__(self, config: dict) -> None:
        policies = config.get("network_policies", {})
        self.allowed_ports = set(policies.get("allowed_ports", []))
        self.blocked_ports = set(policies.get("blocked_ports", []))
        self.bandwidth_limit = float(policies.get("bandwidth_limit", 0))
        self.policy_rules = self._load_policy_rules(policies)
        raw_peers = config.get("federation_peers")
        if isinstance(raw_peers, str):
            peer_list = [raw_peers]
        else:
            peer_list = list(raw_peers or [])
        legacy_peer = config.get("federation_peer_ip")
        if legacy_peer:
            legacy_peer_str = str(legacy_peer)
            if legacy_peer_str and legacy_peer_str not in peer_list:
                peer_list.append(legacy_peer_str)
        self.federation_enabled = bool(config.get("federation_enabled", False))
        self.federation_peers = [str(peer) for peer in peer_list if str(peer)]
        self.peer_ip = self.federation_peers[0] if self.federation_peers else None
        self.log_dir = Path(config.get("log_dir", "."))
        self.uptime_threshold = float(config.get("uptime_threshold", 300))
        self.enforcement_enabled = bool(config.get("enforcement_enabled", False))
        self.ledger_path = Path("/daemon/logs/codex.jsonl")
        self._resync_rule = self._build_rule(
            "federation", "peer_unreachable", "resync", source="builtin"
        )

        self.events: List[str] = []
        self.resync_queued = False
        self._iface_uptime: Dict[str, float] = {}
        self._iface_event_emitted: Dict[str, bool] = {}
        self._last_checked: float | None = None
        self._enforcement_window = timedelta(minutes=5)
        self._enforcement_events: Deque[datetime] = deque()
        self._last_restart_request: datetime | None = None

    # ------------------------------------------------------------------
    # Policy helpers
    def _build_rule(
        self, rule_type: str, value: object, action: str, *, source: str
    ) -> Dict[str, object]:
        """Create a normalized policy rule representation."""

        description_value: str
        if rule_type == "bandwidth":
            try:
                description_value = f"{float(value):g}"
            except (TypeError, ValueError):
                description_value = str(value)
        else:
            description_value = str(value)

        description = f"{rule_type}={description_value}:{action}"
        if rule_type == "bandwidth":
            description = f"{rule_type}>{description_value}:{action}"

        return {
            "type": rule_type,
            "value": value,
            "action": action,
            "source": source,
            "description": description,
        }

    def _create_ledger_event(
        self, interface: str, policy: str, action: str, detail: str | None
    ) -> Dict[str, object]:
        """Build a structured payload mirroring Codex ledger entries."""

        event: Dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "interface": interface,
            "policy": policy,
            "action": action,
        }
        if detail is not None:
            event["detail"] = detail
        return event

    def _policy_payload_from_rule(
        self, interface: str, rule: Dict[str, object], detail: str | None
    ) -> Dict[str, object]:
        """Convert a policy rule into a ledger-style payload."""

        description = str(rule.get("description", "")).strip()
        action = str(rule.get("action", "observe"))
        if not description:
            value = rule.get("value", "?")
            rule_type = rule.get("type", "rule")
            description = f"{rule_type}={value}:{action}"
        return self._create_ledger_event(interface, description, action, detail)

    def _publish_pulse_event(
        self,
        event_type: str,
        payload: Dict[str, object],
        *,
        priority: str = "info",
    ) -> None:
        """Publish a pulse event carrying ``payload`` to subscribers."""

        timestamp = payload.get("timestamp")
        if not isinstance(timestamp, str):
            timestamp = str(timestamp)
        event = {
            "timestamp": timestamp,
            "source_daemon": "network",
            "event_type": event_type,
            "payload": dict(payload),
            "priority": priority,
        }
        pulse_bus.publish(event)

    def _load_policy_rules(self, policies: dict) -> List[Dict[str, object]]:
        """Normalise policy definitions from configuration."""

        rules: List[Dict[str, object]] = []

        for entry in policies.get("rules", []):
            if not isinstance(entry, dict):
                continue
            action = entry.get("action")
            if action not in {"block", "throttle", "resync"}:
                continue
            if "port" in entry:
                try:
                    port_value = int(entry["port"])
                except (TypeError, ValueError):
                    continue
                rules.append(
                    self._build_rule("port", port_value, action, source="rules")
                )
            elif "bandwidth" in entry:
                try:
                    bandwidth_value = float(entry["bandwidth"])
                except (TypeError, ValueError):
                    continue
                rules.append(
                    self._build_rule("bandwidth", bandwidth_value, action, source="rules")
                )
            elif entry.get("type") == "federation":
                rules.append(
                    self._build_rule(
                        "federation",
                        entry.get("value", "peer_unreachable"),
                        action,
                        source="rules",
                    )
                )

        for port in self.blocked_ports:
            if not any(r["type"] == "port" and r["value"] == port for r in rules):
                rules.append(
                    self._build_rule("port", port, "block", source="blocked_ports")
                )

        if self.bandwidth_limit:
            if not any(r["type"] == "bandwidth" for r in rules):
                rules.append(
                    self._build_rule(
                        "bandwidth",
                        float(self.bandwidth_limit),
                        "throttle",
                        source="bandwidth_limit",
                    )
                )

        return rules

    def _match_rules(self, rule_type: str, metric_value: object) -> List[Dict[str, object]]:
        """Retrieve policy rules triggered by the provided metric value."""

        matches: List[Dict[str, object]] = []
        for rule in self.policy_rules:
            if rule["type"] != rule_type:
                continue
            if rule_type == "bandwidth":
                try:
                    if float(metric_value) > float(rule["value"]):
                        matches.append(rule)
                except (TypeError, ValueError):
                    continue
            else:
                if rule["value"] == metric_value:
                    matches.append(rule)
        return matches

    def _maybe_enforce(
        self, interface: str, rule: Dict[str, object], detail: str | None = None
    ) -> None:
        """Simulate enforcement and emit a ledger event when enabled."""

        if not self.enforcement_enabled:
            return None

        action = str(rule.get("action", "observe"))
        policy_description = str(rule.get("description", "unknown_policy"))
        detail_message = f" detail={detail}" if detail else ""
        self._log(
            f"enforcement:{interface}:{policy_description}:{action}{detail_message}"
        )
        payload = self._emit_ledger_event(interface, policy_description, action, detail)
        self._publish_pulse_event("enforcement", payload, priority="critical")
        self._record_enforcement_cycle(policy_description, detail)
        return payload

    def _emit_ledger_event(
        self, interface: str, policy: str, action: str, detail: str | None
    ) -> None:
        """Append an enforcement record to the Codex ledger sink."""

        event = self._create_ledger_event(interface, policy, action, detail)

        try:
            self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
            with self.ledger_path.open("a", encoding="utf-8") as ledger_file:
                ledger_file.write(json.dumps(event) + "\n")
        except Exception:
            # Ledger failures should not interrupt daemon behaviour.
            pass
        return event

    def _record_enforcement_cycle(
        self, policy: str, detail: str | None
    ) -> None:
        now = datetime.now(timezone.utc)
        self._enforcement_events.append(now)
        cutoff = now - self._enforcement_window
        while self._enforcement_events and self._enforcement_events[0] < cutoff:
            self._enforcement_events.popleft()
        if len(self._enforcement_events) < 3:
            return
        if self._last_restart_request and now - self._last_restart_request < self._enforcement_window:
            return
        reason = f"enforcement_loop:{policy}" if policy else "enforcement_loop"
        self._publish_restart_request(reason, detail)
        self._last_restart_request = now

    def _publish_restart_request(self, reason: str, detail: str | None) -> None:
        payload = {
            "action": "restart_daemon",
            "daemon": "network",
            "reason": reason,
        }
        if detail:
            payload["detail"] = detail
        pulse_bus.publish(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source_daemon": "network",
                "event_type": "restart_request",
                "priority": "critical",
                "payload": payload,
            }
        )

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
    def _check_bandwidth(self, usage_kbps: float, interface: str = "aggregate") -> None:
        """Emit an event if bandwidth exceeds the configured limit."""

        matches = self._match_rules("bandwidth", usage_kbps)
        exceeded = self.bandwidth_limit and usage_kbps > self.bandwidth_limit
        if matches or exceeded:
            detail = f"usage_kbps={usage_kbps}"
            self._log(f"bandwidth_saturation:{usage_kbps}")
            if matches:
                for rule in matches:
                    payload = self._policy_payload_from_rule(interface, rule, detail)
                    self._publish_pulse_event(
                        "bandwidth_saturation", payload, priority="warning"
                    )
                    self._maybe_enforce(interface, rule, detail)
            elif exceeded:
                rule = self._build_rule(
                    "bandwidth",
                    float(self.bandwidth_limit or usage_kbps),
                    "observe",
                    source="bandwidth_limit",
                )
                payload = self._policy_payload_from_rule(interface, rule, detail)
                self._publish_pulse_event(
                    "bandwidth_saturation", payload, priority="warning"
                )

    def _check_ports(self, open_ports: Iterable[int], interface: str = "unknown") -> None:
        """Inspect open ports and emit events for unexpected or blocked ones."""
        for port in open_ports:
            matches = self._match_rules("port", port)
            if matches:
                primary_action = str(matches[0].get("action"))
                event = "blocked_port" if primary_action == "block" else "port_policy_violation"
                self._log(f"{event}:{port}")
                detail = f"port={port}"
                for rule in matches:
                    payload = self._policy_payload_from_rule(interface, rule, detail)
                    self._publish_pulse_event("port_violation", payload)
                    self._maybe_enforce(interface, rule, detail)
                continue

            if port in self.blocked_ports:
                self._log(f"blocked_port:{port}")
                detail = f"port={port}"
                rule = self._build_rule("port", port, "block", source="blocked_ports")
                payload = self._policy_payload_from_rule(interface, rule, detail)
                self._publish_pulse_event("port_violation", payload)
                self._maybe_enforce(interface, rule, detail)
            elif port not in self.allowed_ports:
                self._log(f"unexpected_port:{port}")
                detail = f"port={port}"
                rule = self._build_rule("port", port, "observe", source="unexpected_port")
                payload = self._policy_payload_from_rule(interface, rule, detail)
                self._publish_pulse_event("port_violation", payload)

    def _check_federation(self, reachable: bool, interface: str = "federation_link") -> None:
        """Mark resync if federation peer is unreachable."""
        if not reachable:
            self.resync_queued = True
            self._log("federation_link_down")
            matches = self._match_rules("federation", self._resync_rule["value"])
            if not matches:
                matches = [self._resync_rule]
            detail = "peer_unreachable"
            for rule in matches:
                payload = self._policy_payload_from_rule(interface, rule, detail)
                self._publish_pulse_event(
                    "resync_required", payload, priority="critical"
                )
                self._maybe_enforce(interface, rule, detail)

    def _check_uptime(self, status: Dict[str, bool], now: float) -> None:
        """Track interface uptime and emit events when threshold exceeded."""
        if self._last_checked is None:
            self._last_checked = now
            for iface, is_up in status.items():
                self._iface_uptime.setdefault(iface, 0.0)
                self._iface_event_emitted.setdefault(iface, False)
            return

        delta = now - self._last_checked
        for iface, is_up in status.items():
            uptime = self._iface_uptime.get(iface, 0.0)
            if is_up:
                uptime += delta
                if (
                    uptime >= self.uptime_threshold
                    and not self._iface_event_emitted.get(iface, False)
                ):
                    self._log(f"uptime_event:{iface}:{int(uptime)}")
                    self._iface_event_emitted[iface] = True
                    payload = {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "interface": iface,
                        "uptime_seconds": int(uptime),
                    }
                    self._publish_pulse_event("uptime_event", payload, priority="info")
            else:
                uptime = 0.0
                self._iface_event_emitted[iface] = False
            self._iface_uptime[iface] = uptime
        self._last_checked = now

