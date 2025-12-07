"""Caller-driven integration facade for the Consciousness Layer.

This module wires the Consciousness Layer scaffolding behind a single
`run_consciousness_cycle` function without introducing any autonomous
execution. Every call is deterministic and must be explicitly triggered by a
higher-level orchestrator. It also exposes Stage-0 federation primitives for
passive drift awareness with no mutation, enforcement, scheduling, or network
activity.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Mapping, MutableMapping, Optional

from version_consensus import VersionConsensus
from vow_digest import canonical_vow_digest

from sentientos.consciousness.recursion_guard import (
    RecursionGuard,
    RecursionLimitExceeded,
)

# Exposed for orchestration layers to wire into external consensus handling
# without enforcing network activity or self-scheduling within this module.
vc = VersionConsensus(canonical_vow_digest())


def get_version_consensus_summary() -> dict:
    """Return a passive summary of the current canonical digest state."""

    return vc.summary()


def load_attention_arbitrator() -> type:
    """Safely import the AttentionArbitrator class without side effects."""

    from sentientos.consciousness.attention_arbitrator import AttentionArbitrator

    return AttentionArbitrator


def load_sentience_kernel() -> type:
    """Safely import the SentienceKernel class without scheduling cycles."""

    from sentientos.consciousness.sentience_kernel import SentienceKernel

    return SentienceKernel


def load_inner_narrator() -> Callable[[Mapping[str, object], Mapping[str, object]], Any]:
    """Safely import the Inner Narrator ``run_cycle`` routine."""

    from sentientos.consciousness.inner_narrator import run_cycle as narrator_run_cycle

    return narrator_run_cycle


def load_simulation_engine() -> type:
    """Safely import the SimulationEngine class without running it."""

    from sentientos.consciousness.simulation_engine import SimulationEngine

    return SimulationEngine


def _coerce_mapping(candidate: Mapping[str, object] | None, name: str) -> MutableMapping[str, object]:
    if candidate is None:
        return {}
    if not isinstance(candidate, Mapping):
        raise TypeError(f"{name} must be a mapping if provided")
    return dict(candidate)


def _maybe_run_arbitrator(context: Mapping[str, object]) -> Optional[Dict[str, object]]:
    arbitrator = context.get("arbitrator")
    run_default = bool(context.get("run_arbitrator"))
    if arbitrator is None and not run_default:
        return None
    if arbitrator is None:
        arbitrator_cls = load_attention_arbitrator()
        arbitrator = arbitrator_cls()
    if hasattr(arbitrator, "run_cycle"):
        arbitrator.run_cycle()
    telemetry = arbitrator.telemetry_snapshot() if hasattr(arbitrator, "telemetry_snapshot") else None
    return telemetry if isinstance(telemetry, Mapping) else None


def _maybe_run_kernel(context: Mapping[str, object]) -> Optional[Dict[str, object]]:
    kernel = context.get("kernel")
    run_default = bool(context.get("run_kernel"))
    if kernel is None and not run_default:
        return None
    if kernel is None:
        kernel_cls = load_sentience_kernel()
        emitter = context.get("kernel_emitter")
        kernel = kernel_cls(emitter=emitter or (lambda payload: payload))
    if hasattr(kernel, "run_cycle"):
        report = kernel.run_cycle()
        return report if isinstance(report, Mapping) else None
    return None


def _maybe_run_narrator(context: Mapping[str, object]) -> Optional[str]:
    narrator = context.get("inner_narrator")
    run_default = bool(context.get("run_narrator"))
    if narrator is None and not run_default:
        return None
    if narrator is None:
        narrator = load_inner_narrator()
    if not callable(narrator):
        return None
    pulse_snapshot = _coerce_mapping(context.get("pulse_snapshot"), "pulse_snapshot")
    self_model = _coerce_mapping(context.get("self_model"), "self_model")
    log_path = context.get("introspection_log_path")
    return narrator(pulse_snapshot, self_model, log_path=log_path)  # type: ignore[arg-type]


def _maybe_run_simulation(context: Mapping[str, object]) -> Optional[Dict[str, object]]:
    simulation_engine = context.get("simulation_engine")
    run_default = bool(context.get("run_simulation"))
    if simulation_engine is None and not run_default:
        return None
    if simulation_engine is None:
        engine_cls = load_simulation_engine()
        simulation_engine = engine_cls()
    if hasattr(simulation_engine, "run_cycle"):
        simulation_engine.run_cycle()
        summary = getattr(simulation_engine, "last_summary", None)
        transcript = getattr(simulation_engine, "last_transcript", None)
        return {"summary": summary, "transcript": transcript}
    return None


def daemon_heartbeat() -> bool:
    """Placeholder heartbeat hook for deterministic liveness checks."""

    return True


def _heartbeat_or_interrupt() -> Optional[Dict[str, object]]:
    if daemon_heartbeat():
        return None
    return {
        "status": "error",
        "error": "heartbeat_interrupt",
        "message": "Daemon heartbeat check failed",
    }


_RECURSION_GUARD = RecursionGuard()


def run_consciousness_cycle(context: Mapping[str, object]) -> Dict[str, object]:
    """Execute a single Consciousness Layer cycle when explicitly invoked.

    The cycle runs synchronously with no scheduling, timers, or background
    triggers. Each component executes only when an instance is provided or a
    ``run_*`` flag is set in *context*.
    """

    if not isinstance(context, Mapping):
        raise TypeError("context must be a mapping")

    try:
        with _RECURSION_GUARD.enter():
            heartbeat = _heartbeat_or_interrupt()
            if heartbeat:
                return heartbeat

            pulse_updates = _maybe_run_arbitrator(context)

            heartbeat = _heartbeat_or_interrupt()
            if heartbeat:
                return heartbeat

            kernel_updates = _maybe_run_kernel(context)

            heartbeat = _heartbeat_or_interrupt()
            if heartbeat:
                return heartbeat

            introspection_output = _maybe_run_narrator(context)

            heartbeat = _heartbeat_or_interrupt()
            if heartbeat:
                return heartbeat

            simulation_output = _maybe_run_simulation(context)

            return {
                "pulse_updates": pulse_updates,
                "self_model_updates": kernel_updates,
                "introspection_output": introspection_output,
                "simulation_output": simulation_output,
            }
    except RecursionLimitExceeded as exc:
        return {
            "status": "error",
            "error": "recursion_limit_exceeded",
            "message": str(exc),
        }


__all__ = [
    "get_version_consensus_summary",
    "load_attention_arbitrator",
    "load_sentience_kernel",
    "load_inner_narrator",
    "load_simulation_engine",
    "daemon_heartbeat",
    "run_consciousness_cycle",
]
