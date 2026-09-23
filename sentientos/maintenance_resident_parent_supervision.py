"""Bounded parent custody for one configured maintenance resident.

This controller is deliberately narrower than a service manager.  Its child contract
is derived from the already validated resident-adoption configuration, and recovery
can only replay that contract for the canonically reconstructed generation.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, cast

from sentientos import maintenance_resident_runtime_adoption as resident
from sentientos import maintenance_successor_generation_adoption as successor
from sentientos.runtime.services import ChildProcessServiceAdapter, HealthResult, ServiceAdapter

STATE_SCHEMA = "sentientos.maintenance_resident_parent_supervision_state:v1"
RECEIPT_SCHEMA = "sentientos.maintenance_resident_parent_supervision_receipt:v1"
SERVICE_ID = "exact-maintenance-resident"


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


class MaintenanceResidentParentSupervisor:
    """Own exactly one ``sentientosd`` child and no generation-selection policy."""

    def __init__(self, resident_config: Mapping[str, Any], *, state_root: Path,
                 resident_readiness_guard: Callable[[Mapping[str, Any]], bool],
                 restart_budget: int = 3, rolling_restart_window: float = 300.0,
                 min_backoff: float = 0.1, max_backoff: float = 30.0,
                 clock: Callable[[], float] = time.time,
                 sleeper: Callable[[float], None] = time.sleep,
                 adapter_factory: Callable[..., ServiceAdapter] = ChildProcessServiceAdapter) -> None:
        if restart_budget < 0 or rolling_restart_window <= 0 or min_backoff < 0 or max_backoff < min_backoff:
            raise ValueError("invalid_parent_restart_policy")
        self.config = resident.validate_config(resident_config)
        if not self.config["enabled"]:
            raise ValueError("resident_parent_supervision_disabled")
        self.root = Path(state_root).resolve()
        repository = Path(self.config["repository_root"])
        if self.root == repository or repository in self.root.parents:
            raise ValueError("parent_supervision_custody_inside_repository")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._state_path = self.root / "parent-state.json"
        self._receipt_path = self.root / "parent-receipts.jsonl"
        self._readiness_guard, self._clock, self._sleep = resident_readiness_guard, clock, sleeper
        self._budget, self._window = restart_budget, rolling_restart_window
        self._min_backoff, self._max_backoff = min_backoff, max_backoff
        self._environment = self._exact_environment()
        self._argv = (self.config["python_executable"], "-m", "sentientosd")
        self._spec = {"service_id": SERVICE_ID, "executable": self._argv[0], "argv": list(self._argv),
            "cwd": self.config["working_directory"], "environment": self._environment,
            "resident_config_digest": self.config["config_digest"]}
        self._spec_digest = _digest(self._spec)
        self._adapter = adapter_factory(name=SERVICE_ID, argv=self._argv,
            cwd=Path(self.config["working_directory"]), environment=self._environment)
        self._sequence = 0; self._restart_history: list[float] = []
        self._panic = False; self._shutdown = False; self._exhausted = False
        self._status = "configured"; self._generation_digest: str | None = None
        self._launch: dict[str, Any] | None = None
        self._load()
        self._receipt("parent_startup", {"child_spec_digest": self._spec_digest})

    def _exact_environment(self) -> dict[str, str]:
        env = {key: os.environ[key] for key in self.config["inherited_environment_allowlist"] if key in os.environ}
        env.update(self.config["required_environment"])
        env.pop("PYTHONPATH", None); env.pop("PYTHONHOME", None); env.pop(resident.TRANSITION_ENV, None)
        return env

    def _atomic(self, value: Mapping[str, Any]) -> None:
        fd, temporary = tempfile.mkstemp(prefix=".parent-", dir=self.root)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(_canonical(value) + b"\n"); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, self._state_path)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)

    def _persist(self) -> None:
        self._atomic({"schema_version": STATE_SCHEMA, "child_spec_digest": self._spec_digest,
            "sequence": self._sequence, "restart_history": self._restart_history,
            "panic_latched": self._panic, "shutdown_latched": self._shutdown,
            "restart_budget_exhausted": self._exhausted, "status": self._status,
            "generation_digest": self._generation_digest, "launch": self._launch})

    def _load(self) -> None:
        if not self._state_path.exists(): return
        try:
            value = json.loads(self._state_path.read_text(encoding="utf-8"))
            if value.get("schema_version") != STATE_SCHEMA or value.get("child_spec_digest") != self._spec_digest:
                raise ValueError("parent_state_binding_mismatch")
            self._sequence = int(value["sequence"])
            self._restart_history = [float(item) for item in value["restart_history"]]
            self._panic = bool(value["panic_latched"]); self._shutdown = bool(value["shutdown_latched"])
            self._exhausted = bool(value["restart_budget_exhausted"])
            self._status = str(value["status"]); self._generation_digest = value["generation_digest"]
            launch = value.get("launch"); self._launch = dict(launch) if isinstance(launch, dict) else None
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            self._panic = True; self._status = "fail_closed_state"; self._launch = None

    def _receipt(self, event: str, detail: Mapping[str, Any] | None = None) -> None:
        self._sequence += 1
        row = {"schema_version": RECEIPT_SCHEMA, "sequence": self._sequence,
            "timestamp": datetime.fromtimestamp(self._clock(), timezone.utc).isoformat(),
            "event": event, "child_spec_digest": self._spec_digest, "detail": dict(detail or {})}
        row["receipt_digest"] = _digest(row)
        with self._receipt_path.open("ab") as stream:
            stream.write(_canonical(row) + b"\n"); stream.flush(); os.fsync(stream.fileno())
        self._persist()

    def _current_generation(self) -> dict[str, Any]:
        posture = resident.inspect_transition_custody(self.config)
        status = posture["status"]
        if status not in {"no_resident_transactions", "complete_resident_transactions_only"}:
            self._receipt("fail_closed_custody", {"custody": posture})
            raise ValueError("resident_transition_custody_not_recoverable")
        generation, _ = successor.reconstruct_current(
            successor.load_config(self.config["successor_adoption_config_path"]))
        if self._generation_digest is not None and generation["generation_digest"] != self._generation_digest:
            self._receipt("fail_closed_custody", {"reason": "maintenance_lineage_changed"})
            raise ValueError("maintenance_lineage_changed")
        return cast(dict[str, Any], generation)

    def _launch_exact(self, generation: Mapping[str, Any], *, recovery: bool) -> None:
        self._status = "launching"; self._launch = None
        self._receipt("recovery_attempt" if recovery else "child_launch_attempt",
                      {"generation_digest": generation["generation_digest"]})
        try:
            self._adapter.start()
            identity = dict(self._adapter.identity)
            observed_argv = identity.get("argv")
            if (not isinstance(observed_argv, (list, tuple)) or tuple(observed_argv) != self._argv or identity.get("cwd") != self._spec["cwd"] or
                    identity.get("adapter") != "child_process" or identity.get("name") != SERVICE_ID or
                    not isinstance(identity.get("pid"), int)):
                raise ValueError("exact_child_identity_mismatch")
            launch = {"child_spec_digest": self._spec_digest, "config_digest": self.config["config_digest"],
                "lineage_id": generation["lineage_id"], "generation_digest": generation["generation_digest"],
                "pid": identity["pid"], "launched_at": self._clock()}
            launch["launch_provenance_digest"] = _digest(launch)
            self._launch = launch; self._generation_digest = str(generation["generation_digest"])
            self._status = "awaiting_resident_readiness"
            self._receipt("launch_provenance_verified", launch)
        except Exception as exc:
            self._status = "recovery_failed" if recovery else "launch_failed"
            self._receipt("recovery_failure" if recovery else "fail_closed_provenance",
                          {"reason": type(exc).__name__})
            raise

    def start(self) -> None:
        if self._panic: raise RuntimeError("panic_latched")
        if self._shutdown: raise RuntimeError("shutdown_latched")
        self._launch_exact(self._current_generation(), recovery=False)

    def observe(self) -> None:
        if self._panic or self._shutdown or self._exhausted: return
        health = self._adapter.health()
        if not isinstance(health, HealthResult):
            self._fail("invalid_child_health")
            return
        if not health.ready:
            self._unexpected_death(health.reason)
            return
        if self._launch is None:
            self._fail("missing_launch_provenance")
            return
        if self._status == "awaiting_resident_readiness":
            if self._readiness_guard(dict(self._launch)):
                self._status = "maintenance_eligible"
                self._receipt("child_resident_readiness", {"launch_provenance_digest": self._launch["launch_provenance_digest"]})
                if len(self._restart_history) > 0:
                    self._receipt("recovery_success", {"launch_provenance_digest": self._launch["launch_provenance_digest"]})
            else:
                self._receipt("fail_closed_readiness", {"reason": "resident_readiness_not_proven"})

    def _fail(self, reason: str) -> None:
        self._status = "fail_closed"; self._receipt("fail_closed_provenance", {"reason": reason})

    def _unexpected_death(self, reason: str) -> None:
        prior = self._launch["launch_provenance_digest"] if self._launch else None
        self._status = "child_dead"; self._receipt("unexpected_child_death", {"reason": reason, "launch_provenance_digest": prior})
        try: generation = self._current_generation()
        except ValueError:
            self._receipt("recovery_eligibility", {"eligible": False, "reason": "custody_not_proven"}); return
        now = self._clock(); self._restart_history = [stamp for stamp in self._restart_history if now - stamp <= self._window]
        if len(self._restart_history) >= self._budget:
            self._exhausted = True; self._status = "restart_budget_exhausted"
            self._receipt("restart_budget_exhaustion", {"used": len(self._restart_history), "budget": self._budget}); return
        self._receipt("recovery_eligibility", {"eligible": True, "generation_digest": generation["generation_digest"]})
        delay = min(self._max_backoff, self._min_backoff * (2 ** len(self._restart_history)))
        self._sleep(delay); self._restart_history.append(self._clock()); self._persist()
        try: self._launch_exact(generation, recovery=True)
        except Exception: return

    def shutdown(self, *, panic: bool = False) -> None:
        self._shutdown = True; self._panic = self._panic or panic
        self._adapter.stop(); self._status = "panic_stopped" if panic else "stopped"
        self._receipt("panic_stop" if panic else "explicit_shutdown")

    def status(self) -> dict[str, Any]:
        return {"schema_version": STATE_SCHEMA, "status": self._status,
            "maintenance_eligible": self._status == "maintenance_eligible",
            "panic_latched": self._panic, "shutdown_latched": self._shutdown,
            "restart_budget_exhausted": self._exhausted, "restart_count": len(self._restart_history),
            "child_spec_digest": self._spec_digest, "generation_digest": self._generation_digest,
            "launch_provenance_digest": self._launch.get("launch_provenance_digest") if self._launch else None}


__all__ = ["MaintenanceResidentParentSupervisor", "STATE_SCHEMA", "RECEIPT_SCHEMA", "SERVICE_ID"]
