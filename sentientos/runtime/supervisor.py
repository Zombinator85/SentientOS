"""Canonical, local-only SentientOS lifecycle supervisor.

Lifecycle authority is limited to adapters explicitly supplied by the operator/runtime.
It does not grant inference, memory, network, host-actuation, or repository authority.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping

from .services import HealthResult, ServiceAdapter

SCHEMA = "sentientos.runtime_service:v1"
STATES = frozenset({"registered", "starting", "healthy", "degraded", "unhealthy", "restarting",
                    "stopped", "failed", "disabled", "panic_stopped"})


@dataclass(frozen=True)
class RuntimeServiceDescriptor:
    service_id: str
    display_name: str
    service_kind: str
    dependencies: tuple[str, ...] = ()
    enabled: bool = True
    startup_posture: str = "automatic"
    startup_timeout: float = 10.0
    health_posture: str = "semantic"
    health_timeout: float = 5.0
    shutdown_posture: str = "graceful_then_force"
    shutdown_timeout: float = 10.0
    restart_policy: str = "on_failure"
    restart_budget: int = 3
    rolling_restart_window: float = 300.0
    min_backoff: float = 0.1
    max_backoff: float = 30.0
    stable_interval: float = 300.0
    critical: bool = False
    schema: str = SCHEMA

    def __post_init__(self) -> None:
        if not self.service_id or self.schema != SCHEMA: raise ValueError("invalid_service_descriptor")
        if min(self.startup_timeout, self.health_timeout, self.shutdown_timeout) <= 0: raise ValueError("timeouts_must_be_positive")
        if self.restart_budget < 0 or self.min_backoff < 0 or self.max_backoff < self.min_backoff: raise ValueError("invalid_restart_policy")


class ServiceRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, tuple[RuntimeServiceDescriptor, ServiceAdapter]] = {}

    def register(self, descriptor: RuntimeServiceDescriptor, adapter: ServiceAdapter) -> None:
        if descriptor.service_id in self._entries: raise ValueError(f"duplicate_service_id:{descriptor.service_id}")
        self._entries[descriptor.service_id] = (descriptor, adapter)

    def freeze(self) -> None:
        unknown = sorted({d for descriptor, _ in self._entries.values() for d in descriptor.dependencies if d not in self._entries})
        if unknown: raise ValueError("unknown_dependencies:" + ",".join(unknown))
        self.startup_order()

    @property
    def descriptors(self) -> Mapping[str, RuntimeServiceDescriptor]:
        return MappingProxyType({key: value[0] for key, value in sorted(self._entries.items())})

    def adapter(self, service_id: str) -> ServiceAdapter: return self._entries[service_id][1]

    def startup_order(self) -> tuple[str, ...]:
        remaining = set(self._entries); done: list[str] = []
        while remaining:
            ready = sorted(x for x in remaining if set(self._entries[x][0].dependencies) <= set(done))
            if not ready: raise ValueError("dependency_cycle")
            done.extend(ready); remaining.difference_update(ready)
        return tuple(done)

    def shutdown_order(self) -> tuple[str, ...]: return tuple(reversed(self.startup_order()))

    def digest(self) -> str:
        rows = [asdict(self._entries[key][0]) for key in sorted(self._entries)]
        return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def runtime_state_root() -> Path:
    configured = os.getenv("SENTIENTOS_RUNTIME_STATE_ROOT")
    if configured: return Path(configured).expanduser().resolve()
    data = os.getenv("SENTIENTOS_DATA_DIR") or os.getenv("SENTIENTOS_DATA_ROOT")
    return (Path(data).expanduser().resolve() if data else (Path.cwd() / "sentientos_data").resolve()) / "runtime"


class RuntimeSupervisor:
    def __init__(self, registry: ServiceRegistry, *, state_root: Path | None = None,
                 clock: Callable[[], float] = time.time, sleeper: Callable[[float], None] = time.sleep) -> None:
        registry.freeze(); self.registry = registry; self.root = (state_root or runtime_state_root()).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._state_path, self._receipt_path = self.root / "supervisor-state.json", self.root / "lifecycle-receipts.jsonl"
        self._clock, self._sleep, self._lock = clock, sleeper, threading.RLock()
        self._sequence = 0; self.generation = uuid.uuid4().hex; self.panic_latched = False
        self._states = {key: ("disabled" if not d.enabled else "registered") for key, d in registry.descriptors.items()}
        self._health: dict[str, dict[str, object]] = {}; self._restarts: dict[str, list[float]] = {k: [] for k in self._states}
        self._latest: dict[str, str] = {k: "registered" for k in self._states}; self._exhausted: set[str] = set()
        self._load(); self._persist(); self._receipt("registry_snapshot", None, {"registry_digest": registry.digest()})

    def _load(self) -> None:
        if not self._state_path.exists(): return
        try:
            payload = json.loads(self._state_path.read_text(encoding="utf-8"))
            if payload.get("schema") != "sentientos.runtime_supervisor_state:v1": raise ValueError
            if payload.get("registry_digest") != self.registry.digest(): raise ValueError
            self.panic_latched = bool(payload["panic_latched"]); self._sequence = int(payload["sequence"])
            self._restarts = {k: [float(x) for x in payload["restart_histories"].get(k, [])] for k in self._states}
            self._exhausted = set(payload.get("exhausted_services", [])) & set(self._states)
            self._latest.update({k: str(v) for k, v in payload.get("latest_reasons", {}).items() if k in self._states})
            if self.panic_latched: self._states = {k: "panic_stopped" if d.enabled else "disabled" for k, d in self.registry.descriptors.items()}
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            self.panic_latched = True; self._states = {k: "panic_stopped" if d.enabled else "disabled" for k, d in self.registry.descriptors.items()}
            self._latest = {k: "malformed_durable_state" for k in self._states}

    def _atomic(self, payload: object) -> None:
        fd, tmp = tempfile.mkstemp(prefix=".supervisor-", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, sort_keys=True); stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
            os.replace(tmp, self._state_path)
            directory = os.open(self.root, os.O_RDONLY); os.fsync(directory); os.close(directory)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)

    def _persist(self) -> None:
        self._atomic({"schema": "sentientos.runtime_supervisor_state:v1", "registry_digest": self.registry.digest(),
            "generation": self.generation, "sequence": self._sequence, "panic_latched": self.panic_latched,
            "service_states": self._states, "latest_health": self._health, "restart_histories": self._restarts,
            "exhausted_services": sorted(self._exhausted), "latest_reasons": self._latest})

    def _receipt(self, event: str, service_id: str | None, detail: Mapping[str, object] | None = None) -> None:
        self._sequence += 1
        row = {"schema": "sentientos.runtime_lifecycle_receipt:v1", "sequence": self._sequence,
               "timestamp": datetime.fromtimestamp(self._clock(), timezone.utc).isoformat(), "generation": self.generation,
               "event": event, "service_id": service_id, "detail": dict(detail or {})}
        with self._receipt_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, sort_keys=True) + "\n"); stream.flush(); os.fsync(stream.fileno())
        self._persist()

    def _call(self, fn: Callable[[], object], timeout: float) -> object:
        pool = ThreadPoolExecutor(max_workers=1)
        future = pool.submit(fn)
        try: return future.result(timeout=timeout)
        except FutureTimeout as exc:
            future.cancel(); raise TimeoutError("adapter_timeout") from exc
        finally: pool.shutdown(wait=False, cancel_futures=True)

    def _transition(self, service_id: str, state: str, reason: str, event: str = "health_transition") -> None:
        assert state in STATES; previous = self._states[service_id]; self._states[service_id] = state; self._latest[service_id] = reason
        self._receipt(event, service_id, {"previous_state": previous, "state": state, "reason": reason})

    def start_all(self) -> None:
        with self._lock:
            if self.panic_latched: raise RuntimeError("panic_latched")
            for service_id in self.registry.startup_order(): self._start(service_id)

    def _start(self, service_id: str, restarting: bool = False) -> None:
        descriptor = self.registry.descriptors[service_id]
        if not descriptor.enabled: self._states[service_id] = "disabled"; return
        blocked = [d for d in descriptor.dependencies if self._states[d] != "healthy"]
        if blocked:
            self._transition(service_id, "degraded", "dependency_blocked:" + ",".join(blocked), "dependency_degradation"); return
        self._transition(service_id, "restarting" if restarting else "starting", "restart_attempt" if restarting else "start_requested",
                         "restart_attempted" if restarting else "start_requested")
        try:
            self._call(self.registry.adapter(service_id).start, descriptor.startup_timeout)
            self._receipt("restart_succeeded" if restarting else "start_succeeded", service_id)
            self._observe(service_id, restart_on_failure=False)
        except Exception as exc:
            self._transition(service_id, "failed", f"start_failed:{type(exc).__name__}", "restart_failed" if restarting else "start_failed")

    def _observe(self, service_id: str, *, restart_on_failure: bool = True) -> None:
        descriptor = self.registry.descriptors[service_id]
        dependencies = {d: self._states[d] for d in descriptor.dependencies}
        blocked = [d for d, state in dependencies.items() if state != "healthy"]
        if blocked:
            if self._states[service_id] != "degraded": self._transition(service_id, "degraded", "dependency_blocked:" + ",".join(blocked), "dependency_degradation")
            return
        if self._states[service_id] == "degraded" and self._latest[service_id].startswith("dependency_blocked"):
            self._receipt("dependency_recovery", service_id, {"dependencies": dependencies})
        started = time.monotonic()
        try:
            result = self._call(self.registry.adapter(service_id).health, descriptor.health_timeout)
            if not isinstance(result, HealthResult): raise TypeError("invalid_health_result")
        except Exception as exc: result = HealthResult(False, f"health_failed:{type(exc).__name__}")
        latency = time.monotonic() - started
        self._health[service_id] = {"sequence": self._sequence + 1, "timestamp": self._clock(), "latency_seconds": latency,
                                    "ready": result.ready, "reason": result.reason, "dependency_state": dependencies,
                                    "metadata": dict(result.metadata or {})}
        if result.ready:
            self._transition(service_id, "healthy", result.reason)
        else:
            self._transition(service_id, "unhealthy", result.reason)
            if restart_on_failure: self._restart(service_id)

    def observe(self) -> None:
        with self._lock:
            if self.panic_latched: return
            for service_id in self.registry.startup_order():
                if self.registry.descriptors[service_id].enabled and self._states[service_id] not in {"failed", "disabled", "panic_stopped"}:
                    self._observe(service_id)

    def _restart(self, service_id: str) -> None:
        d = self.registry.descriptors[service_id]
        if self.panic_latched or d.restart_policy != "on_failure" or service_id in self._exhausted: return
        now = self._clock(); history = [x for x in self._restarts[service_id] if now - x <= d.rolling_restart_window]
        self._restarts[service_id] = history
        if len(history) >= d.restart_budget:
            self._exhausted.add(service_id); self._transition(service_id, "failed", "restart_budget_exhausted", "restart_budget_exhausted"); return
        delay = min(d.max_backoff, d.min_backoff * (2 ** len(history)))
        self._receipt("restart_scheduled", service_id, {"backoff_seconds": delay, "used": len(history), "budget": d.restart_budget})
        self._sleep(delay); history.append(self._clock()); self._restarts[service_id] = history
        try: self._call(self.registry.adapter(service_id).force_stop, d.shutdown_timeout)
        except Exception: pass
        self._start(service_id, restarting=True)

    def reset_restart_budget(self, service_id: str) -> None:
        with self._lock:
            self._restarts[service_id] = []; self._exhausted.discard(service_id)
            self._states[service_id] = "registered"; self._transition(service_id, "registered", "operator_budget_reset", "restart_budget_reset")

    def shutdown(self, *, panic: bool = False) -> None:
        with self._lock:
            if panic: self.panic_latched = True
            for service_id in self.registry.shutdown_order():
                if self._states[service_id] in {"disabled", "stopped", "panic_stopped"}: continue
                d, adapter = self.registry.descriptors[service_id], self.registry.adapter(service_id)
                self._receipt("panic_stop" if panic else "graceful_stop_requested", service_id)
                try:
                    self._call(adapter.stop, d.shutdown_timeout)
                    self._transition(service_id, "panic_stopped" if panic else "stopped", "panic_latched" if panic else "graceful_stop_completed",
                                     "panic_stop" if panic else "graceful_stop_completed")
                except Exception:
                    self._call(adapter.force_stop, d.shutdown_timeout)
                    self._transition(service_id, "panic_stopped" if panic else "stopped", "forced_terminal_stop", "forced_terminal_stop")

    def panic_stop(self) -> None: self.shutdown(panic=True)

    def clear_panic(self) -> None:
        with self._lock:
            if not self.panic_latched: return
            self.panic_latched = False
            for key, descriptor in self.registry.descriptors.items(): self._states[key] = "registered" if descriptor.enabled else "disabled"
            self._receipt("panic_clear", None, {"operator_action_required": True})

    def status(self) -> Mapping[str, object]:
        with self._lock:
            services = {key: {"descriptor": asdict(d), "state": self._states[key],
                              "dependency_state": {x: self._states[x] for x in d.dependencies},
                              "restart_count": len(self._restarts[key]), "restart_budget": d.restart_budget,
                              "restart_budget_exhausted": key in self._exhausted, "latest_health": self._health.get(key),
                              "latest_reason": self._latest[key]} for key, d in self.registry.descriptors.items()}
            return {"schema": "sentientos.runtime_supervisor_status:v1", "generation": self.generation,
                    "state": "panic" if self.panic_latched else "running", "panic_latched": self.panic_latched,
                    "registry_digest": self.registry.digest(), "services": services}
