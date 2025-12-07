import inspect
from typing import Dict, List

import pytest

from sentientos.metacognition import MetaMonitor


def test_meta_monitor_initial_state():
    monitor = MetaMonitor()
    assert monitor.get_recent_notes() == []


def test_meta_monitor_signatures():
    review_sig = inspect.signature(MetaMonitor.review_cycle)
    assert list(review_sig.parameters.keys()) == ["self", "state"]
    assert review_sig.parameters["state"].annotation == Dict[str, float]
    assert review_sig.return_annotation == List[Dict[str, object]]

    notes_sig = inspect.signature(MetaMonitor.get_recent_notes)
    assert list(notes_sig.parameters.keys()) == ["self", "limit"]
    assert notes_sig.parameters["limit"].default == 10
    assert notes_sig.parameters["limit"].annotation is int
    assert notes_sig.return_annotation == List[Dict[str, object]]


def test_review_cycle_creates_notes_with_structure():
    monitor = MetaMonitor()
    notes = monitor.review_cycle({"errors": 1})

    assert len(notes) == 1
    note = notes[0]
    assert set(note.keys()) == {"timestamp", "level", "message"}
    assert note["timestamp"] == 1
    assert note["level"] == "info"
    assert note["message"] == "Errors observed in cycle."


def test_thresholds_generate_warnings():
    monitor = MetaMonitor()
    notes_low_conf = monitor.review_cycle({"confidence": 0.2})
    assert notes_low_conf[0]["level"] == "warning"
    assert "confidence" in notes_low_conf[0]["message"]

    notes_high_tension = monitor.review_cycle({"tension": 0.75})
    assert notes_high_tension[0]["level"] == "warning"
    assert "tension" in notes_high_tension[0]["message"]


def test_timestamps_increase():
    monitor = MetaMonitor()
    monitor.review_cycle({"errors": 1})
    monitor.review_cycle({"confidence": 0.2})
    monitor.review_cycle({"tension": 0.8})

    recent_notes = monitor.get_recent_notes(5)
    timestamps = [note["timestamp"] for note in recent_notes]
    assert timestamps == sorted(timestamps)
    assert timestamps == list(range(1, len(timestamps) + 1))


def test_get_recent_notes_returns_copies():
    monitor = MetaMonitor()
    monitor.review_cycle({"errors": 1})
    pulled = monitor.get_recent_notes()
    pulled[0]["message"] = "mutated"

    latest = monitor.get_recent_notes()
    assert latest[0]["message"] != "mutated"


def test_buffer_respects_max_size():
    monitor = MetaMonitor()
    for _ in range(60):
        monitor.review_cycle({"errors": 1})

    recent = monitor.get_recent_notes(100)
    assert len(recent) == 50
    assert recent[0]["timestamp"] == 11
    assert recent[-1]["timestamp"] == 60
