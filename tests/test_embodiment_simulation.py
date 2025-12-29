from __future__ import annotations

import json

import pytest

from sentientos.diagnostics import DiagnosticError
from sentientos.embodiment import SignalDirection, SignalType, simulate_signal


def test_simulation_emits_introspection_and_memory_plan(tmp_path) -> None:
    path = tmp_path / "introspection.jsonl"
    result = simulate_signal(
        SignalDirection.INGRESS,
        SignalType.SENSOR_EVENT,
        {"sensor_id": "cam-1", "value": 0.42, "frequency_hz": 1.0},
        context="test",
        introspection_path=str(path),
    )

    assert result.simulation_only is True
    assert result.mutation_allowed is False
    assert result.memory_plan.simulation_only is True
    assert result.memory_cost > 0

    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines
    events = [json.loads(line) for line in lines]
    event_types = {entry.get("event_type") for entry in events}
    assert "CLI_ACTION" in event_types
    assert "MEMORY_ECONOMICS" in event_types


def test_forbidden_context_rejected(tmp_path) -> None:
    with pytest.raises(DiagnosticError) as excinfo:
        simulate_signal(
            SignalDirection.INGRESS,
            SignalType.USER_INPUT,
            {"user_id": "u-1", "input": "hello"},
            context="cognition",
            introspection_path=str(tmp_path / "introspection.jsonl"),
        )
    assert excinfo.value.frame.error_code == "EMBODIMENT_CONTRACT_VIOLATION"


def test_payload_field_rejected(tmp_path) -> None:
    with pytest.raises(DiagnosticError):
        simulate_signal(
            SignalDirection.EGRESS,
            SignalType.STATUS_REPORT,
            {"component": "kernel", "status": "ok", "extra": "nope"},
            context="test",
            introspection_path=str(tmp_path / "introspection.jsonl"),
        )


def test_simulation_deterministic_id(tmp_path) -> None:
    payload = {"sensor_id": "cam-2", "value": 0.1, "frequency_hz": 1.0}
    first = simulate_signal(
        SignalDirection.INGRESS,
        SignalType.SENSOR_EVENT,
        payload,
        context="test",
        introspection_path=str(tmp_path / "introspection.jsonl"),
    )
    second = simulate_signal(
        SignalDirection.INGRESS,
        SignalType.SENSOR_EVENT,
        payload,
        context="test",
        introspection_path=str(tmp_path / "introspection.jsonl"),
    )
    assert first.simulation_id == second.simulation_id
    assert first.memory_cost == second.memory_cost


def test_simulation_reports_no_mutation(tmp_path) -> None:
    result = simulate_signal(
        SignalDirection.EGRESS,
        SignalType.ADVISORY_SIGNAL,
        {"advice": "keep steady", "severity": "low"},
        context="test",
        introspection_path=str(tmp_path / "introspection.jsonl"),
    )
    assert result.simulation_only is True
    assert result.mutation_allowed is False
