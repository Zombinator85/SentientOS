from datetime import datetime, timedelta, timezone

import pytest

from sentientos.pressure_queue import (
    PRESSURE_PERSISTENCE_ESCALATION_REVIEWS,
    close_pressure_signal,
    enqueue_pressure_signal,
    get_pressure_signal_state,
    list_due_pressure_signals,
    pressure_review_interval,
    read_pressure_queue,
    revalidate_pressure_signal,
)

pytestmark = pytest.mark.no_legacy_skip


def _build_signal(digest: str, *, severity: str = "low") -> dict[str, object]:
    return {
        "digest": digest,
        "signal_type": "drift",
        "as_of_date": "2024-01-05",
        "window_days": 3,
        "severity": severity,
        "counts": {"posture_stuck": 2},
        "source": "drift_alerts",
    }


def test_review_policy_schedule_and_due_listing(tmp_path, monkeypatch) -> None:
    log_path = tmp_path / "pressure_queue.jsonl"
    monkeypatch.setenv("PRESSURE_QUEUE_LOG", str(log_path))
    now = datetime(2024, 1, 5, 12, 0, tzinfo=timezone.utc)
    signal = _build_signal("digest-1", severity="low")

    enqueue_pressure_signal(signal, now=now)
    state = get_pressure_signal_state("digest-1", log_path=log_path)
    assert state is not None

    interval = pressure_review_interval("drift", "low")
    expected_due = now + interval
    assert datetime.fromisoformat(state["next_review_due_at"]) == expected_due
    assert state["status"] == "open"

    assert list_due_pressure_signals(expected_due - timedelta(seconds=1), log_path=log_path) == []
    due = list_due_pressure_signals(expected_due, log_path=log_path)
    assert [record["digest"] for record in due] == ["digest-1"]


def test_revalidate_updates_schedule_and_escalates(tmp_path, monkeypatch) -> None:
    log_path = tmp_path / "pressure_queue.jsonl"
    monkeypatch.setenv("PRESSURE_QUEUE_LOG", str(log_path))
    now = datetime(2024, 1, 5, 12, 0, tzinfo=timezone.utc)
    signal = _build_signal("digest-2", severity="low")

    enqueue_pressure_signal(signal, now=now)
    interval = pressure_review_interval("drift", "low")
    review_time = now + interval

    revalidate_pressure_signal("digest-2", as_of_time=review_time, actor="operator")
    state = get_pressure_signal_state("digest-2", log_path=log_path)
    assert state is not None
    assert state["last_reviewed_at"] == review_time.isoformat()
    assert datetime.fromisoformat(state["next_review_due_at"]) == review_time + interval
    assert state["status"] == "acknowledged"

    for idx in range(2, PRESSURE_PERSISTENCE_ESCALATION_REVIEWS):
        review_time = review_time + interval
        revalidate_pressure_signal("digest-2", as_of_time=review_time, actor=f"operator-{idx}")
        state = get_pressure_signal_state("digest-2", log_path=log_path)
        assert state is not None
        assert state["severity"] == "low"

    review_time = review_time + interval
    revalidate_pressure_signal("digest-2", as_of_time=review_time, actor="operator-final")
    state = get_pressure_signal_state("digest-2", log_path=log_path)
    assert state is not None
    assert state["severity"] == "medium"


def test_close_removes_from_due_listing_and_logs(tmp_path, monkeypatch) -> None:
    log_path = tmp_path / "pressure_queue.jsonl"
    monkeypatch.setenv("PRESSURE_QUEUE_LOG", str(log_path))
    now = datetime(2024, 1, 5, 12, 0, tzinfo=timezone.utc)
    signal = _build_signal("digest-3", severity="medium")

    enqueue_pressure_signal(signal, now=now)
    close_pressure_signal("digest-3", actor="operator", reason="resolved", note="pressure cleared")

    due = list_due_pressure_signals(now + timedelta(days=30), log_path=log_path)
    assert [record["digest"] for record in due] == []

    entries = read_pressure_queue(log_path)
    close_entries = [entry for entry in entries if entry.get("event") == "pressure_closed"]
    assert close_entries
    logged = close_entries[-1]
    assert logged["digest"] == "digest-3"
    assert logged["actor"] == "operator"
    assert logged["closure_reason"] == "resolved"
    assert logged["closure_note"] == "pressure cleared"
    assert logged["closed_at"]
