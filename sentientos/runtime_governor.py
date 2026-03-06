from __future__ import annotations

import hashlib
import json
import os
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Deque


@dataclass(frozen=True)
class PressureSnapshot:
    cpu: float
    io: float
    thermal: float
    gpu: float
    composite: float
    sampled_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "cpu": self.cpu,
            "io": self.io,
            "thermal": self.thermal,
            "gpu": self.gpu,
            "composite": self.composite,
            "sampled_at": self.sampled_at,
        }


@dataclass(frozen=True)
class GovernorDecision:
    action_class: str
    allowed: bool
    mode: str
    reason: str
    subject: str
    scope: str
    origin: str
    sampled_pressure: PressureSnapshot
    reason_hash: str
    correlation_id: str

    def to_dict(self) -> dict[str, object]:
        return {
            "action_class": self.action_class,
            "allowed": self.allowed,
            "mode": self.mode,
            "reason": self.reason,
            "subject": self.subject,
            "scope": self.scope,
            "origin": self.origin,
            "sampled_pressure": self.sampled_pressure.to_dict(),
            "reason_hash": self.reason_hash,
            "correlation_id": self.correlation_id,
        }


class RuntimeGovernor:
    """Deterministic admissibility layer for runtime control-plane actions."""

    def __init__(self) -> None:
        self._mode = os.getenv("SENTIENTOS_GOVERNOR_MODE", "shadow").strip().lower()
        if self._mode not in {"shadow", "advisory", "enforce"}:
            self._mode = "shadow"
        self._root = Path(os.getenv("SENTIENTOS_GOVERNOR_ROOT", "/glow/governor"))
        self._root.mkdir(parents=True, exist_ok=True)
        self._decisions_path = self._root / "decisions.jsonl"
        self._pressure_path = self._root / "pressure.jsonl"
        self._budget_path = self._root / "storm_budget.json"

        # budgets
        self._restart_window = timedelta(seconds=self._env_int("SENTIENTOS_GOVERNOR_RESTART_WINDOW_SECONDS", 300))
        self._repair_window = timedelta(seconds=self._env_int("SENTIENTOS_GOVERNOR_REPAIR_WINDOW_SECONDS", 600))
        self._federated_window = timedelta(seconds=self._env_int("SENTIENTOS_GOVERNOR_FEDERATED_WINDOW_SECONDS", 120))
        self._critical_window = timedelta(seconds=self._env_int("SENTIENTOS_GOVERNOR_CRITICAL_WINDOW_SECONDS", 120))
        self._task_window = timedelta(seconds=self._env_int("SENTIENTOS_GOVERNOR_TASK_WINDOW_SECONDS", 120))
        self._amendment_window = timedelta(seconds=self._env_int("SENTIENTOS_GOVERNOR_AMENDMENT_WINDOW_SECONDS", 300))

        self._restart_limit = self._env_int("SENTIENTOS_GOVERNOR_RESTART_LIMIT", 3)
        self._repair_limit = self._env_int("SENTIENTOS_GOVERNOR_REPAIR_LIMIT", 5)
        self._federated_limit = self._env_int("SENTIENTOS_GOVERNOR_FEDERATED_LIMIT", 20)
        self._critical_limit = self._env_int("SENTIENTOS_GOVERNOR_CRITICAL_LIMIT", 50)
        self._task_limit = self._env_int("SENTIENTOS_GOVERNOR_TASK_LIMIT", 128)
        self._amendment_limit = self._env_int("SENTIENTOS_GOVERNOR_AMENDMENT_LIMIT", 16)

        self._pressure_block = self._env_float("SENTIENTOS_GOVERNOR_PRESSURE_BLOCK", 0.85)
        self._pressure_warn = self._env_float("SENTIENTOS_GOVERNOR_PRESSURE_WARN", 0.70)
        self._schedule_threshold = self._env_float("SENTIENTOS_GOVERNOR_SCHEDULING_THRESHOLD", 0.45)

        self._restarts: dict[str, Deque[datetime]] = defaultdict(deque)
        self._repairs: dict[str, Deque[datetime]] = defaultdict(deque)
        self._federated_controls: Deque[datetime] = deque()
        self._critical_events: Deque[datetime] = deque()
        self._control_plane_tasks: dict[str, Deque[datetime]] = defaultdict(deque)
        self._amendments: dict[str, Deque[datetime]] = defaultdict(deque)
        self._quarantine: dict[str, bool] = defaultdict(bool)

    def admit_action(
        self,
        action_type: str,
        actor: str,
        correlation_id: str,
        metadata: dict[str, object] | None = None,
    ) -> GovernorDecision:
        normalized = action_type.strip().lower()
        payload = dict(metadata or {})
        subject = str(payload.get("subject") or payload.get("daemon_name") or payload.get("target") or actor or "unknown")
        scope = str(payload.get("scope") or "local")

        if normalized == "restart_daemon":
            return self.admit_restart(
                daemon_name=subject,
                scope=scope,
                origin=actor,
                metadata=payload,
                correlation_id=correlation_id,
            )
        if normalized == "repair_action":
            anomaly_kind = str(payload.get("anomaly_kind") or payload.get("kind") or "unknown")
            return self.admit_repair(
                anomaly_kind=anomaly_kind,
                subject=subject,
                metadata=payload,
                correlation_id=correlation_id,
            )
        if normalized == "federated_control":
            return self.admit_federated_control(
                subject=subject,
                origin=actor,
                metadata=payload,
                correlation_id=correlation_id,
            )
        if normalized == "control_plane_task":
            return self._admit_control_plane_task(
                requester=actor,
                subject=subject,
                metadata=payload,
                correlation_id=correlation_id,
            )
        if normalized == "amendment_apply":
            return self._admit_amendment_apply(
                actor=actor,
                subject=subject,
                metadata=payload,
                correlation_id=correlation_id,
            )
        return self._decision(
            action_class=normalized,
            allowed=self._mode != "enforce",
            reason="unknown_action_type",
            subject=subject,
            scope=scope,
            origin=actor,
            pressure=self.sample_pressure(),
            metadata=payload,
            correlation_id=correlation_id,
        )

    def sample_pressure(self) -> PressureSnapshot:
        now = datetime.now(timezone.utc)
        cpu = self._read_cpu()
        io = self._read_io()
        thermal = self._read_thermal()
        gpu = self._read_gpu()
        composite = round(min(1.0, max(0.0, 0.4 * cpu + 0.25 * io + 0.2 * thermal + 0.15 * gpu)), 4)
        snapshot = PressureSnapshot(cpu=cpu, io=io, thermal=thermal, gpu=gpu, composite=composite, sampled_at=now.isoformat())
        self._append_jsonl(self._pressure_path, snapshot.to_dict())
        self._publish_governor_state(snapshot)
        return snapshot

    def scheduling_window_open(self) -> bool:
        pressure = self.sample_pressure()
        return pressure.composite <= self._schedule_threshold

    def observe_pulse_event(self, event: dict[str, Any]) -> None:
        event_type = str(event.get("event_type", ""))
        if event_type.startswith("governor_"):
            return
        priority = str(event.get("priority", "info")).lower()
        if priority == "critical":
            now = datetime.now(timezone.utc)
            self._critical_events.append(now)
            self._trim(self._critical_events, now, self._critical_window)

    def admit_restart(
        self,
        *,
        daemon_name: str,
        scope: str,
        origin: str,
        metadata: dict[str, object] | None = None,
        correlation_id: str | None = None,
    ) -> GovernorDecision:
        pressure = self.sample_pressure()
        now = datetime.now(timezone.utc)
        dq = self._restarts[daemon_name]
        dq.append(now)
        self._trim(dq, now, self._restart_window)

        if scope == "federated":
            self._federated_controls.append(now)
            self._trim(self._federated_controls, now, self._federated_window)

        reason = "allowed"
        enforce_block = False
        if self._quarantine[daemon_name]:
            reason = "daemon_quarantined"
            enforce_block = True
        elif len(dq) > self._restart_limit:
            reason = "restart_budget_exceeded"
            self._quarantine[daemon_name] = True
            enforce_block = True
        elif scope == "federated" and len(self._federated_controls) > self._federated_limit:
            reason = "federated_control_rate_exceeded"
            enforce_block = True
        elif len(self._critical_events) > self._critical_limit:
            reason = "critical_event_storm_detected"
            enforce_block = True
        elif pressure.composite >= self._pressure_block:
            reason = "pressure_block"
            enforce_block = True
        elif pressure.composite >= self._pressure_warn:
            reason = "pressure_warn"

        allowed = not enforce_block or self._mode != "enforce"
        decision = self._decision(
            action_class="daemon_restart",
            allowed=allowed,
            reason=reason,
            subject=daemon_name,
            scope=scope,
            origin=origin,
            pressure=pressure,
            metadata=metadata,
            correlation_id=correlation_id,
        )
        return decision

    def admit_repair(
        self,
        *,
        anomaly_kind: str,
        subject: str,
        metadata: dict[str, object] | None = None,
        correlation_id: str | None = None,
    ) -> GovernorDecision:
        pressure = self.sample_pressure()
        now = datetime.now(timezone.utc)
        dq = self._repairs[anomaly_kind]
        dq.append(now)
        self._trim(dq, now, self._repair_window)

        reason = "allowed"
        enforce_block = False
        if len(dq) > self._repair_limit:
            reason = "repair_budget_exceeded"
            enforce_block = True
        elif pressure.composite >= self._pressure_block:
            reason = "pressure_block"
            enforce_block = True
        elif len(self._critical_events) > self._critical_limit:
            reason = "critical_event_storm_detected"
            enforce_block = True
        elif pressure.composite >= self._pressure_warn:
            reason = "pressure_warn"

        allowed = not enforce_block or self._mode != "enforce"
        return self._decision(
            action_class="repair_action",
            allowed=allowed,
            reason=reason,
            subject=subject,
            scope="local",
            origin="codex_healer",
            pressure=pressure,
            metadata={"anomaly_kind": anomaly_kind, **(metadata or {})},
            correlation_id=correlation_id,
        )

    def admit_federated_control(
        self,
        *,
        subject: str,
        origin: str,
        metadata: dict[str, object] | None = None,
        correlation_id: str | None = None,
    ) -> GovernorDecision:
        pressure = self.sample_pressure()
        now = datetime.now(timezone.utc)
        self._federated_controls.append(now)
        self._trim(self._federated_controls, now, self._federated_window)

        reason = "allowed"
        enforce_block = False
        if len(self._federated_controls) > self._federated_limit:
            reason = "federated_control_rate_exceeded"
            enforce_block = True
        elif pressure.composite >= self._pressure_block:
            reason = "pressure_block"
            enforce_block = True
        elif len(self._critical_events) > self._critical_limit:
            reason = "critical_event_storm_detected"
            enforce_block = True
        elif pressure.composite >= self._pressure_warn:
            reason = "pressure_warn"
        allowed = not enforce_block or self._mode != "enforce"
        return self._decision(
            action_class="federated_control",
            allowed=allowed,
            reason=reason,
            subject=subject,
            scope="federated",
            origin=origin,
            pressure=pressure,
            metadata=metadata,
            correlation_id=correlation_id,
        )

    def _admit_control_plane_task(
        self,
        *,
        requester: str,
        subject: str,
        metadata: dict[str, object] | None,
        correlation_id: str | None,
    ) -> GovernorDecision:
        pressure = self.sample_pressure()
        now = datetime.now(timezone.utc)
        dq = self._control_plane_tasks[requester]
        dq.append(now)
        self._trim(dq, now, self._task_window)

        reason = "allowed"
        enforce_block = False
        if len(dq) > self._task_limit:
            reason = "control_plane_task_rate_exceeded"
            enforce_block = True
        elif pressure.composite >= self._pressure_block:
            reason = "pressure_block"
            enforce_block = True
        elif len(self._critical_events) > self._critical_limit:
            reason = "critical_event_storm_detected"
            enforce_block = True
        elif pressure.composite >= self._pressure_warn:
            reason = "pressure_warn"

        allowed = not enforce_block or self._mode != "enforce"
        return self._decision(
            action_class="control_plane_task",
            allowed=allowed,
            reason=reason,
            subject=subject,
            scope="local",
            origin=requester,
            pressure=pressure,
            metadata=metadata,
            correlation_id=correlation_id,
        )

    def _admit_amendment_apply(
        self,
        *,
        actor: str,
        subject: str,
        metadata: dict[str, object] | None,
        correlation_id: str | None,
    ) -> GovernorDecision:
        pressure = self.sample_pressure()
        now = datetime.now(timezone.utc)
        dq = self._amendments[actor]
        dq.append(now)
        self._trim(dq, now, self._amendment_window)

        reason = "allowed"
        enforce_block = False
        if len(dq) > self._amendment_limit:
            reason = "amendment_rate_exceeded"
            enforce_block = True
        elif pressure.composite >= self._pressure_block:
            reason = "pressure_block"
            enforce_block = True
        elif pressure.composite >= self._pressure_warn:
            reason = "pressure_warn"

        allowed = not enforce_block or self._mode != "enforce"
        return self._decision(
            action_class="amendment_apply",
            allowed=allowed,
            reason=reason,
            subject=subject,
            scope="local",
            origin=actor,
            pressure=pressure,
            metadata=metadata,
            correlation_id=correlation_id,
        )

    def _decision(
        self,
        *,
        action_class: str,
        allowed: bool,
        reason: str,
        subject: str,
        scope: str,
        origin: str,
        pressure: PressureSnapshot,
        metadata: dict[str, object] | None,
        correlation_id: str | None,
    ) -> GovernorDecision:
        correlation = correlation_id or hashlib.sha256(
            json.dumps(
                {
                    "action_class": action_class,
                    "subject": subject,
                    "scope": scope,
                    "origin": origin,
                    "reason": reason,
                    "metadata": metadata or {},
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        reasoning_payload = {
            "action_class": action_class,
            "allowed": allowed,
            "mode": self._mode,
            "reason": reason,
            "subject": subject,
            "scope": scope,
            "origin": origin,
            "pressure": pressure.to_dict(),
            "metadata": metadata or {},
            "correlation_id": correlation,
        }
        reason_hash = hashlib.sha256(json.dumps(reasoning_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        decision = GovernorDecision(
            action_class=action_class,
            allowed=allowed,
            mode=self._mode,
            reason=reason,
            subject=subject,
            scope=scope,
            origin=origin,
            sampled_pressure=pressure,
            reason_hash=reason_hash,
            correlation_id=correlation,
        )
        payload = decision.to_dict()
        payload["metadata"] = metadata or {}
        payload["timestamp"] = datetime.now(timezone.utc).isoformat()
        payload["decision"] = "allow" if allowed else "deny"
        payload["governor_mode"] = self._mode
        payload["pressure_snapshot"] = pressure.to_dict()
        self._append_jsonl(self._decisions_path, payload)
        self._write_budget_snapshot()
        self._publish_governor_decision(payload)
        return decision

    def _write_budget_snapshot(self) -> None:
        snapshot = {
            "schema_version": 1,
            "mode": self._mode,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "restart_counts": {name: len(entries) for name, entries in self._restarts.items()},
            "repair_counts": {name: len(entries) for name, entries in self._repairs.items()},
            "federated_controls": len(self._federated_controls),
            "control_plane_task_counts": {name: len(entries) for name, entries in self._control_plane_tasks.items()},
            "amendment_counts": {name: len(entries) for name, entries in self._amendments.items()},
            "critical_events": len(self._critical_events),
            "quarantine": dict(self._quarantine),
            "limits": {
                "restart_limit": self._restart_limit,
                "repair_limit": self._repair_limit,
                "federated_limit": self._federated_limit,
                "critical_limit": self._critical_limit,
                "task_limit": self._task_limit,
                "amendment_limit": self._amendment_limit,
            },
        }
        self._budget_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _publish_governor_state(self, pressure: PressureSnapshot) -> None:
        self._publish_event(
            "governor_state",
            "info",
            {
                "mode": self._mode,
                "pressure": pressure.to_dict(),
                "scheduling_window_open": pressure.composite <= self._schedule_threshold,
            },
        )

    def _publish_governor_decision(self, payload: dict[str, object]) -> None:
        priority = "info" if bool(payload.get("allowed", False)) else "warning"
        self._publish_event("governor_decision", priority, payload)

    def _publish_event(self, event_type: str, priority: str, payload: dict[str, object]) -> None:
        correlation_id = str(payload.get("correlation_id") or "")
        try:
            from sentientos.daemons import pulse_bus

            pulse_bus.publish(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "source_daemon": "runtime_governor",
                    "event_type": event_type,
                    "priority": priority,
                    "correlation_id": correlation_id,
                    "payload": payload,
                }
            )
        except Exception:
            # telemetry failures must not break control paths
            return

    @staticmethod
    def _trim(entries: Deque[datetime], now: datetime, window: timedelta) -> None:
        cutoff = now - window
        while entries and entries[0] < cutoff:
            entries.popleft()

    @staticmethod
    def _append_jsonl(path: Path, payload: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")

    @staticmethod
    def _env_int(name: str, default: int) -> int:
        value = os.getenv(name)
        if value is None:
            return default
        try:
            parsed = int(value)
            return max(1, parsed)
        except ValueError:
            return default

    @staticmethod
    def _env_float(name: str, default: float) -> float:
        value = os.getenv(name)
        if value is None:
            return default
        try:
            parsed = float(value)
        except ValueError:
            return default
        return min(1.0, max(0.0, parsed))

    @staticmethod
    def _read_cpu() -> float:
        override = os.getenv("SENTIENTOS_GOVERNOR_CPU", "")
        if override:
            try:
                return min(1.0, max(0.0, float(override)))
            except ValueError:
                pass
        try:
            import psutil  # type: ignore

            return round(min(1.0, max(0.0, psutil.cpu_percent(interval=0.0) / 100.0)), 4)
        except Exception:
            return 0.0

    @staticmethod
    def _read_io() -> float:
        override = os.getenv("SENTIENTOS_GOVERNOR_IO", "")
        if override:
            try:
                return min(1.0, max(0.0, float(override)))
            except ValueError:
                pass
        try:
            import shutil

            usage = shutil.disk_usage(Path.cwd())
            return round(min(1.0, max(0.0, usage.used / usage.total)), 4)
        except Exception:
            return 0.0

    @staticmethod
    def _read_thermal() -> float:
        override = os.getenv("SENTIENTOS_GOVERNOR_THERMAL", "")
        if override:
            try:
                return min(1.0, max(0.0, float(override)))
            except ValueError:
                pass
        try:
            import psutil  # type: ignore

            temps = psutil.sensors_temperatures()
            if not temps:
                return 0.0
            current: list[float] = []
            for entries in temps.values():
                for entry in entries:
                    if entry.current is not None:
                        current.append(float(entry.current))
            if not current:
                return 0.0
            max_temp = max(current)
            return round(min(1.0, max(0.0, (max_temp - 30.0) / 70.0)), 4)
        except Exception:
            return 0.0

    @staticmethod
    def _read_gpu() -> float:
        override = os.getenv("SENTIENTOS_GOVERNOR_GPU", "")
        if override:
            try:
                return min(1.0, max(0.0, float(override)))
            except ValueError:
                pass
        return 0.0


_GOVERNOR: RuntimeGovernor | None = None


def get_runtime_governor() -> RuntimeGovernor:
    global _GOVERNOR
    if _GOVERNOR is None:
        _GOVERNOR = RuntimeGovernor()
    return _GOVERNOR


def reset_runtime_governor() -> None:
    global _GOVERNOR
    _GOVERNOR = None
