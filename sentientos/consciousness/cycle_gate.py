"""Stage-2 passive rate-limiter primitive for consciousness cycles.

CycleGate surfaces whether a consciousness cycle should run based on
pre-computed readiness conditions. It never schedules, enforces, or blocks
execution; it only reports deterministic readiness state for orchestrators.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CycleGate:
    recursion_ok: bool
    heartbeat_ok: bool
    narrative_ok: bool

    def ready(self) -> bool:
        return self.recursion_ok and self.heartbeat_ok and self.narrative_ok

    def as_dict(self) -> dict:
        return {
            "recursion_ok": self.recursion_ok,
            "heartbeat_ok": self.heartbeat_ok,
            "narrative_ok": self.narrative_ok,
            "ready": self.ready(),
        }


def build_cycle_gate(
    recursion_ok: bool, heartbeat_ok: bool, narrative_ok: bool
) -> CycleGate:
    return CycleGate(recursion_ok, heartbeat_ok, narrative_ok)
