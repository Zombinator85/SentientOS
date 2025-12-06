import importlib

from sentientos.daemons import pulse_bus
from sentientos.glow import self_state


MODULE_NAMES = [
    "attention_arbitrator",
    "sentience_kernel",
    "inner_narrator",
    "simulation_engine",
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
