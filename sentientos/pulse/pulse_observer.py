from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Protocol

from .signals import PulseSignal

DEFAULT_PULSE_PATH = Path("/pulse/status.json")


class AuditEvent(Protocol):
    type: str
    timestamp: str
    data: dict


def observe(events: list[AuditEvent], *, window: int = 50) -> PulseSignal:
    recent_events = events[-window:] if window > 0 else []

    admission_denials = 0
    admission_accepts = 0
    executor_failures = 0
    executor_successes = 0
    tasks_seen: set[str] = set()
    actors_seen: set[str] = set()

    for event in recent_events:
        event_type = getattr(event, "type", "")
        data = getattr(event, "data", {}) or {}

        if event_type == "TASK_ADMISSION_DENIED":
            admission_denials += 1
        elif event_type == "TASK_ADMITTED":
            admission_accepts += 1

        if _is_executor_failure(event_type):
            executor_failures += 1
        if _is_executor_success(event_type):
            executor_successes += 1

        task_id = data.get("task_id")
        if task_id is not None:
            tasks_seen.add(str(task_id))

        actor = data.get("actor")
        if actor is not None:
            actors_seen.add(str(actor))

    metrics = {
        "admission_denials": admission_denials,
        "admission_accepts": admission_accepts,
        "executor_failures": executor_failures,
        "executor_successes": executor_successes,
        "unique_tasks_seen": len(tasks_seen),
        "actors_seen": len(actors_seen),
    }
    level, reason = _classify_signal(metrics)

    return PulseSignal(level=level, reason=reason, metrics=metrics, window=len(recent_events))


def emit_pulse(signal: PulseSignal, path: Path = DEFAULT_PULSE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(asdict(signal), separators=(",", ":"), sort_keys=True)
    fd, temp_path = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(serialized)
        Path(temp_path).replace(path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def update_pulse_from_events(events: list[AuditEvent], *, path: Path = DEFAULT_PULSE_PATH, window: int = 50) -> PulseSignal:
    signal = observe(events, window=window)
    emit_pulse(signal, path)
    return signal


def _is_executor_failure(event_type: str) -> bool:
    normalized = event_type.upper()
    failure_tokens = {
        "TASK_EXECUTION_FAILED",
        "EXECUTOR_FAILURE",
        "EXECUTOR_TASK_FAILED",
        "EXECUTOR_STEP_FAILED",
        "TASK_FAILED",
    }
    return normalized in failure_tokens or (
        "EXECUTOR" in normalized and "FAIL" in normalized
    ) or ("TASK_EXECUTION" in normalized and "FAIL" in normalized)


def _is_executor_success(event_type: str) -> bool:
    normalized = event_type.upper()
    success_tokens = {
        "TASK_EXECUTION_SUCCEEDED",
        "TASK_EXECUTION_COMPLETED",
        "EXECUTOR_SUCCESS",
        "EXECUTOR_TASK_COMPLETED",
        "EXECUTOR_STEP_COMPLETED",
        "TASK_COMPLETED",
    }
    return normalized in success_tokens or (
        "EXECUTOR" in normalized and ("SUCCESS" in normalized or "COMPLETED" in normalized)
    ) or ("TASK_EXECUTION" in normalized and ("SUCCESS" in normalized or "COMPLETED" in normalized))


def _classify_signal(metrics: dict[str, int]):
    admission_denials = metrics["admission_denials"]
    admission_accepts = metrics["admission_accepts"]
    executor_failures = metrics["executor_failures"]

    if executor_failures >= 3 or (admission_denials >= 2 * admission_accepts and admission_denials > 0):
        return "DEGRADED", "SYSTEM_DEGRADED"
    if admission_denials > admission_accepts:
        return "WARNING", "ELEVATED_DENIAL_RATE"
    if 0 < executor_failures < 3:
        return "WARNING", "EXECUTION_FAILURES"
    return "STABLE", "NORMAL_OPERATION"
