from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import pytest

from attention_arbitrator import AttentionArbitratorDaemon, PulseEvent
from inner_narrator import run_cycle as narrator_run_cycle
from sentience_kernel import SentienceKernel
from simulation_engine import SimulationEngine
from sentientos.daemons import pulse_bus
from sentientos.glow import self_state
from sentientos.integrity import covenant_autoalign


@pytest.fixture
def autoalign_calls(monkeypatch: pytest.MonkeyPatch) -> List[str]:
    calls: List[str] = []

    def _stub() -> Dict[str, object]:
        calls.append("cycle")
        return {"stage": "cycle", "guardrails_active": True, "daemons_constrained": True}

    monkeypatch.setattr(covenant_autoalign, "autoalign_before_cycle", _stub)
    return calls


def _prepare_self_model(tmp_path: Path) -> Path:
    target = tmp_path / "glow" / "self.json"
    self_state.save(self_state.DEFAULT_SELF_STATE, path=target)
    return target


def test_full_cycle_writes_back_self_model(autoalign_calls: List[str], tmp_path: Path) -> None:
    self_path = _prepare_self_model(tmp_path)

    arbitrator = AttentionArbitratorDaemon()
    arbitrator.arbitrator.submit(
        PulseEvent(
            payload={"id": "stable"},
            priority="normal",
            internal_priority="baseline",
            event_origin="local",
            focus="focus-a",
            timestamp=10.0,
        )
    )
    arbitrator.arbitrator.submit(
        PulseEvent(
            payload={"id": "secondary"},
            priority="high",
            internal_priority="elevated",
            event_origin="peer",
            focus="focus-b",
            timestamp=5.0,
        )
    )
    arbitrator.run_cycle()

    kernel_events: List[Dict[str, object]] = []
    kernel = SentienceKernel(emitter=kernel_events.append, self_path=self_path)
    kernel_report = kernel.run_cycle()

    pulse_snapshot = {
        "cycle": 1,
        "events": kernel_events,
        "focus": kernel_report.get("goal", {}).get("description", "focus-a"),
    }
    narrator_reflection = narrator_run_cycle(pulse_snapshot, self_state.load(path=self_path))

    pulse_state_path = tmp_path / "pulse" / "system.json"
    pulse_state_path.parent.mkdir(parents=True, exist_ok=True)
    pulse_state_path.write_text(json.dumps({"focus": {"topic": "focus-a"}, "context": {}, "events": []}))
    engine = SimulationEngine(
        log_path=tmp_path / "daemon" / "logs" / "simulation.jsonl",
        pulse_state_path=pulse_state_path,
        self_path=self_path,
        deterministic_seed="cycle-seed",
    )
    engine.run_cycle()

    updated_state = self_state.load(path=self_path)
    assert updated_state["last_reflection_summary"] == narrator_reflection
    assert updated_state["last_focus"] in {"focus-a", "focus-b", "introspection"}
    assert updated_state["last_cycle_result"]
    assert updated_state["goal_context"] == updated_state.get("last_generated_goal", {}).get("context", {})

    introspection_log = Path(tmp_path / "daemon" / "logs" / "introspection.jsonl")
    assert introspection_log.exists()
    assert not pulse_bus.pending_events()

    assert autoalign_calls.count("cycle") == 4


def test_guardrails_block_invalid_arbitration(autoalign_calls: List[str], tmp_path: Path) -> None:
    self_path = _prepare_self_model(tmp_path)

    arbitrator = AttentionArbitratorDaemon()
    arbitrator.arbitrator.submit(
        PulseEvent(
            payload={"id": "invalid"},
            priority="urgent",
            event_origin="sensor",
            context="not-a-dict",
            focus="unsafe",
            timestamp=2.0,
        )
    )
    arbitrator.arbitrator.submit(
        PulseEvent(
            payload={"id": "valid"},
            priority="low",
            event_origin="system",
            context={"note": "ok"},
            focus="safe",
            timestamp=3.0,
        )
    )

    focus = arbitrator.choose_focus()
    assert focus is not None
    assert focus.focus == "safe"
    telemetry = arbitrator.telemetry_snapshot()["last_decision"]
    assert telemetry["skipped"] == 1

    kernel = SentienceKernel(emitter=lambda payload: payload, self_path=self_path)
    self_state.update({"novelty_score": 0.0, "last_focus": "safe"}, path=self_path)
    report = kernel.run_cycle()
    assert report["generated"] in {True, False}

    stored = self_state.load(path=self_path)
    assert stored["last_focus"] == "safe"
    assert stored["novelty_score"] >= 0.0
    assert autoalign_calls.count("cycle") == 1
