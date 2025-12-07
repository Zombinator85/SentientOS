import pytest

from sentientos.consciousness.cycle_gate import CycleGate, build_cycle_gate


def test_cycle_gate_ready_true():
    gate = CycleGate(recursion_ok=True, heartbeat_ok=True, narrative_ok=True)

    assert gate.ready() is True


def test_cycle_gate_ready_false_cases():
    false_cases = [
        CycleGate(recursion_ok=False, heartbeat_ok=True, narrative_ok=True),
        CycleGate(recursion_ok=True, heartbeat_ok=False, narrative_ok=True),
        CycleGate(recursion_ok=True, heartbeat_ok=True, narrative_ok=False),
    ]

    for gate in false_cases:
        assert gate.ready() is False


def test_cycle_gate_as_dict_deterministic():
    gate = build_cycle_gate(recursion_ok=True, heartbeat_ok=False, narrative_ok=True)

    assert gate.as_dict() == {
        "recursion_ok": True,
        "heartbeat_ok": False,
        "narrative_ok": True,
        "ready": False,
    }
