"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from logging_config import get_log_path
import os
import json
import time
import datetime
from pathlib import Path
import autonomous_reflector as ar
import doctrine
from system_continuity import (
    CheckpointLedger,
    DriftSentinel,
    HumanLens,
    PhaseGate,
    SystemPhase,
    UpdateOrchestrator,
)

MEMORY_DIR = get_log_path("memory", "MEMORY_DIR")
STATE_PATH = MEMORY_DIR / "orchestrator_state.json"
STATE_PATH.parent.mkdir(parents=True, exist_ok=True)


def _load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


class Orchestrator:
    def __init__(self, interval: float = 60.0):
        self.interval = interval
        self.state = _load_state()

    def run_cycle(self) -> None:
        ar.run_once()
        doctrine.maybe_prompt(7, os.getenv("USER", "admin"))
        self.state["last_run"] = datetime.datetime.utcnow().isoformat()
        _save_state(self.state)

    def run_forever(self) -> None:
        self.state["running"] = True
        _save_state(self.state)
        iterations = 0
        cycles = self.state.get("cycles")
        while self.state.get("running"):
            self.run_cycle()
            iterations += 1
            if cycles is not None and iterations >= cycles:
                break
            time.sleep(self.interval)
            self.state = _load_state()
        self.state["running"] = False
        _save_state(self.state)

    # New public helpers
    def start(self, cycles: int | None = None) -> None:
        self.state["cycles"] = cycles
        self.state["running"] = True
        _save_state(self.state)
        self.run_forever()

    def stop(self) -> None:
        self.state["running"] = False
        _save_state(self.state)

    def status(self) -> dict:
        self.state = _load_state()
        return {
            "running": self.state.get("running", False),
            "last_run": self.state.get("last_run"),
        }


# New lifecycle utilities
def build_update_orchestrator(phase: SystemPhase = SystemPhase.ADVISORY_WINDOW) -> UpdateOrchestrator:
    """Construct a deterministic, rollback-capable orchestrator.

    The helper is intentionally lightweight so tests can provision
    a fully-guarded orchestrator without touching the global process state.
    """

    gate = PhaseGate(phase=phase)
    ledger = CheckpointLedger()
    return UpdateOrchestrator(gate, ledger)


__all__ = [
    "HumanLens",
    "Orchestrator",
    "build_update_orchestrator",
    "CheckpointLedger",
    "DriftSentinel",
    "PhaseGate",
    "SystemPhase",
    "UpdateOrchestrator",
]
