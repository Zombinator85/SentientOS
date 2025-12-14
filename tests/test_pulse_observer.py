from dataclasses import dataclass
import json

from sentientos.pulse.pulse_observer import observe


@dataclass
class FakeEvent:
    type: str
    timestamp: str
    data: dict


def test_stable_when_accepts_exceed_denials_and_no_failures():
    events = [
        FakeEvent("TASK_ADMITTED", "t1", {"task_id": "a", "actor": "alpha"}),
        FakeEvent("TASK_ADMITTED", "t2", {"task_id": "b", "actor": "beta"}),
        FakeEvent("TASK_ADMISSION_DENIED", "t3", {"task_id": "c", "actor": "alpha"}),
    ]
    signal = observe(events)

    assert signal.level == "STABLE"
    assert signal.reason == "NORMAL_OPERATION"
    assert signal.metrics["admission_accepts"] == 2
    assert signal.metrics["admission_denials"] == 1
    assert signal.metrics["unique_tasks_seen"] == 3
    assert signal.metrics["actors_seen"] == 2


def test_warning_when_denials_exceed_accepts():
    events = [
        FakeEvent("TASK_ADMITTED", "t1", {}),
        FakeEvent("TASK_ADMISSION_DENIED", "t2", {}),
        FakeEvent("TASK_ADMISSION_DENIED", "t3", {}),
    ]
    signal = observe(events)

    assert signal.level == "WARNING"
    assert signal.reason == "ELEVATED_DENIAL_RATE"


def test_warning_with_single_executor_failure():
    events = [
        FakeEvent("TASK_ADMITTED", "t1", {}),
        FakeEvent("TASK_EXECUTION_FAILED", "t2", {}),
    ]
    signal = observe(events)

    assert signal.level == "WARNING"
    assert signal.reason == "EXECUTION_FAILURES"


def test_degraded_with_three_executor_failures():
    events = [
        FakeEvent("TASK_EXECUTION_FAILED", "t1", {}),
        FakeEvent("TASK_EXECUTION_FAILED", "t2", {}),
        FakeEvent("TASK_EXECUTION_FAILED", "t3", {}),
    ]
    signal = observe(events)

    assert signal.level == "DEGRADED"
    assert signal.reason == "SYSTEM_DEGRADED"


def test_degraded_with_high_denial_ratio():
    events = [
        FakeEvent("TASK_ADMITTED", "t1", {}),
        FakeEvent("TASK_ADMISSION_DENIED", "t2", {}),
        FakeEvent("TASK_ADMISSION_DENIED", "t3", {}),
    ]
    signal = observe(events)

    assert signal.level == "DEGRADED"
    assert signal.reason == "SYSTEM_DEGRADED"


def test_deterministic_output_for_same_events():
    events = [
        FakeEvent("TASK_ADMITTED", "t1", {"task_id": "x", "actor": "a"}),
        FakeEvent("TASK_ADMISSION_DENIED", "t2", {"task_id": "y", "actor": "b"}),
        FakeEvent("TASK_EXECUTION_COMPLETED", "t3", {"task_id": "x", "actor": "a"}),
    ]

    first = observe(events)
    second = observe(list(events))

    assert first == second
    first_json = json.dumps(first.__dict__, sort_keys=True)
    second_json = json.dumps(second.__dict__, sort_keys=True)
    assert first_json == second_json
