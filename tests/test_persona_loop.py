from __future__ import annotations

import logging
import time
from typing import List

from sentientos.persona import PersonaLoop, decay_energy, initial_state, update_from_pulse


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: List[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _collecting_logger() -> tuple[logging.Logger, _ListHandler]:
    logger = logging.getLogger("test.persona")
    logger.handlers = []
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = _ListHandler()
    logger.addHandler(handler)
    return logger, handler


def test_update_from_pulse_success_sequence() -> None:
    state = initial_state()
    state.energy = 0.6
    for idx in range(3):
        update_from_pulse(
            state,
            {
                "kind": "experiment_result",
                "success": True,
                "description": f"calibration {idx}",
            },
        )
    assert state.pulse_snapshot["experiments"]["success"] == 3
    assert state.energy <= 1.0
    assert state.mood in {"curious", "focused"}


def test_update_from_pulse_failure_sequence() -> None:
    state = initial_state()
    for _ in range(2):
        update_from_pulse(
            state,
            {
                "kind": "experiment_result",
                "success": False,
                "description": "stress test",
            },
        )
    assert state.pulse_snapshot["experiments"]["failure"] == 2
    assert state.energy >= 0.0
    assert state.mood in {"alert", "concerned"}


def test_decay_energy_transitions_to_idle() -> None:
    state = initial_state()
    state.energy = 0.45
    decay_energy(state, 600.0)
    assert state.energy < 0.45
    assert state.mood in {"idle", "tired"}


def test_tick_once_emits_log_and_updates_state() -> None:
    state = initial_state()
    events = [
        {"kind": "runtime_status", "component": "relay", "status": "error"},
    ]
    logger, handler = _collecting_logger()
    loop = PersonaLoop(
        state,
        tick_interval_seconds=10.0,
        event_source=lambda: events,
        max_message_length=120,
        logger=logger,
    )

    message = loop._tick_once()

    assert handler.records, "expected a log record"
    assert handler.records[0].getMessage() == message
    assert "relay" in state.pulse_snapshot["runtime"]
    assert state.mood in {"alert", "concerned"}


def test_tick_once_is_deterministic() -> None:
    events = [
        {"kind": "experiment_result", "success": True, "description": "alignment"}
    ]
    logger, _ = _collecting_logger()
    loop_a = PersonaLoop(
        initial_state(),
        tick_interval_seconds=15.0,
        event_source=lambda: list(events),
        max_message_length=120,
        logger=logger,
    )
    loop_b = PersonaLoop(
        initial_state(),
        tick_interval_seconds=15.0,
        event_source=lambda: list(events),
        max_message_length=120,
        logger=logger,
    )

    msg_a = loop_a._tick_once()
    msg_b = loop_b._tick_once()

    assert loop_a.state.mood == loop_b.state.mood
    assert msg_a == msg_b


def test_loop_start_and_stop() -> None:
    loop = PersonaLoop(initial_state(), tick_interval_seconds=0.05, event_source=lambda: [])
    loop.start()
    time.sleep(0.12)
    loop.stop()
    assert loop.is_running() is False
