from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip


def test_pulse_modules_do_not_import_task_execution_stack():
    pulse_dir = Path("sentientos") / "pulse"
    assert pulse_dir.is_dir(), "pulse package missing"
    forbidden_tokens = ("task_admission", "task_executor", "control_plane")
    offenders: list[str] = []

    for path in pulse_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            if f"import {token}" in text or f"from {token} " in text:
                offenders.append(f"{path}: {token}")

    assert not offenders, f"pulse modules import execution stack: {offenders}"


def test_pulse_callbacks_do_not_enqueue_tasks():
    pulse_dir = Path("sentientos") / "pulse"
    assert pulse_dir.is_dir(), "pulse package missing"
    forbidden_tokens = ("execute_task", "run_task_with_admission", "enqueue_task", "task_executor")
    offenders: list[str] = []

    for path in pulse_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            if token in text:
                offenders.append(f"{path}: {token}")

    assert not offenders, f"pulse modules reference task execution hooks: {offenders}"


def test_observe_is_read_only():
    from sentientos.pulse.pulse_observer import observe

    events = [{"type": "TASK_ADMISSION_DENIED", "timestamp": "t1", "data": {"task_id": "t1"}}]
    snapshot = list(events)

    signal = observe(events, window=10)

    assert events == snapshot
    assert signal.metrics["admission_denials"] == 1
