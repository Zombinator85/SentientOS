import pytest

from sentientos.innerworld.history import CycleHistory


pytestmark = pytest.mark.no_legacy_skip


def _make_report(value: int) -> dict:
    return {
        "qualia": {"novelty": float(value)},
        "ethics": {"conflicts": []},
        "metacog": [{"message": f"note-{value}"}],
    }


def test_records_defensive_snapshots():
    history = CycleHistory()
    original_one = _make_report(1)
    original_two = _make_report(2)

    history.record(original_one)
    history.record(original_two)

    stored = history.get_all()
    assert stored[0] is not original_one
    assert stored[1] is not original_two


def test_maxlen_enforced():
    history = CycleHistory(maxlen=3)

    for value in range(5):
        history.record(_make_report(value))

    stored = history.get_all()
    assert len(stored) == 3
    assert [entry["qualia"]["novelty"] for entry in stored] == [2.0, 3.0, 4.0]


def test_deterministic_summary():
    history = CycleHistory()

    history.record({"qualia": {"focus": 1.0, "clarity": 2.0}, "ethics": {"conflicts": [{}]}, "metacog": [{}]})
    history.record({"qualia": {"focus": 3.0, "clarity": 4.0}, "ethics": {"conflicts": []}, "metacog": []})
    history.record({"qualia": {"focus": 5.0}, "ethics": {"conflicts": [{}]}, "metacog": [{}, {}]})

    summary = history.summarize()

    assert summary["count"] == 3
    assert summary["qualia_trends"] == {"focus": 3.0, "clarity": 3.0}
    assert summary["ethical_conflict_rate"] == pytest.approx(2 / 3)
    assert summary["metacog_note_frequency"] == 3


def test_no_side_effects_from_calls():
    history = CycleHistory()
    original = _make_report(5)

    history.record(original)
    original["qualia"]["novelty"] = -1

    stored_before = history.get_all()
    assert stored_before[0]["qualia"]["novelty"] == 5.0

    retrieved_entry = stored_before[0]
    retrieved_entry["qualia"]["novelty"] = 999

    stored_after = history.get_all()

    assert stored_after[0]["qualia"]["novelty"] == 5.0
