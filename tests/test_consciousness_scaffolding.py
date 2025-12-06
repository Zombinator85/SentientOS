import importlib

from sentientos.consciousness.attention_arbitrator import AttentionArbitrator, PulseEvent
from sentientos.daemons import pulse_bus
from sentientos.glow import self_state


MODULE_NAMES = [
    "sentientos.consciousness.attention_arbitrator",
    "sentientos.consciousness.sentience_kernel",
    "sentientos.consciousness.inner_narrator",
    "sentientos.consciousness.simulation_engine",
]


def test_consciousness_modules_importable():
    for name in MODULE_NAMES:
        module = importlib.import_module(name)
        assert hasattr(module, "run_cycle")
        module.run_cycle()


def test_pulse_bus_schema_defaults_non_destructive():
    event = {
        "timestamp": "2024-01-01T00:00:00Z",
        "source_daemon": "test",
        "event_type": "unit",
        "payload": {},
        "focus": "keep_me",
    }
    enriched = pulse_bus.apply_pulse_defaults(event)
    assert enriched["focus"] == "keep_me"
    for field in ("context", "internal_priority", "event_origin"):
        assert field in enriched
    for field in pulse_bus.PULSE_V2_SCHEMA:
        assert field in pulse_bus.PULSE_V2_SCHEMA


def test_self_state_defaults_round_trip(tmp_path):
    target = tmp_path / "self.json"
    loaded = self_state.load(path=target)
    assert loaded["identity"] == "SentientOS"
    updated = self_state.update({"mood": "curious"}, path=target)
    assert updated["mood"] == "curious"


def test_attention_arbitrator_uses_pulse_metadata():
    arbitrator = AttentionArbitrator()
    arbitrator.submit(
        PulseEvent(
            payload={"id": "peer_high"},
            priority="high",
            internal_priority="routine",
            event_origin="peer",
            focus="peer_focus",
            timestamp=1.0,
        )
    )
    arbitrator.submit(
        PulseEvent(
            payload={"id": "local_critical"},
            priority="high",
            internal_priority="critical",
            event_origin="local",
            focus="local_focus",
            context={"topic": "safety"},
            timestamp=2.0,
        )
    )

    winner = arbitrator.choose_focus()
    assert winner is not None
    assert winner.focus == "local_focus"
    telemetry = arbitrator.telemetry_snapshot()
    assert telemetry["last_decision"]["priority"] == "high"


def test_attention_arbitrator_guardrails_and_fallback():
    arbitrator = AttentionArbitrator()
    arbitrator.submit(
        PulseEvent(
            payload={"id": "invalid_origin"},
            priority="urgent",
            event_origin="unauthorized",
            focus="unsafe",
        )
    )
    arbitrator.submit(
        PulseEvent(
            payload={"id": "valid"},
            priority="normal",
            event_origin="system",
            focus="safe",
            timestamp=5.0,
        )
    )

    winner = arbitrator.choose_focus()
    assert winner is not None
    assert winner.focus == "safe"
    telemetry = arbitrator.telemetry_snapshot()
    assert telemetry["last_decision"]["skipped"] == 1
