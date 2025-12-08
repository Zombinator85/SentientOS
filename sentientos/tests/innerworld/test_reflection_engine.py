from copy import deepcopy

import pytest

from sentientos.innerworld.reflection import CycleReflectionEngine

pytestmark = pytest.mark.no_legacy_skip


def _sample_history(values: list[float]) -> list[dict]:
    return [
        {
            "qualia": {"confidence": value, "tension": value * -1},
            "ethics": {"conflicts": [{}] if value > 0 else []},
            "metacog": [{"message": f"m-{value}"}] if value % 2 == 0 else [],
        }
        for value in values
    ]


def test_deterministic_reflection_output():
    history = _sample_history([0.1, 0.2, 0.3])
    engine = CycleReflectionEngine()

    first = engine.reflect(history)
    second = engine.reflect(history)

    assert first == second


def test_empty_history_neutral_summary():
    engine = CycleReflectionEngine()

    summary = engine.reflect([])

    assert summary["trend_summary"] == {
        "confidence": "stable",
        "tension": "stable",
        "ethical_conflict_rate": "none",
        "metacog_density": "stable",
    }
    assert summary["insights"] == ["No history available; trends are stable."]


def test_trend_classification_rising_falling_stable():
    engine = CycleReflectionEngine()
    rising_history = _sample_history([0.1, 0.5, 0.9])
    falling_history = _sample_history([0.9, 0.5, 0.1])
    stable_history = _sample_history([0.2, 0.2, 0.2])

    rising_trends = engine.summarize_trends(rising_history)
    falling_trends = engine.summarize_trends(falling_history)
    stable_trends = engine.summarize_trends(stable_history)

    assert rising_trends["confidence"] == "rising"
    assert falling_trends["confidence"] == "falling"
    assert stable_trends["confidence"] == "stable"


def test_insight_phrases_are_deterministic():
    engine = CycleReflectionEngine(max_insights=5)
    history = [
        {
            "qualia": {"confidence": 0.1, "tension": -0.1},
            "ethics": {"conflicts": [{}]},
            "metacog": [],
        },
        {
            "qualia": {"confidence": 0.4, "tension": -0.4},
            "ethics": {"conflicts": []},
            "metacog": [],
        },
        {
            "qualia": {"confidence": 0.4, "tension": -0.4},
            "ethics": {"conflicts": []},
            "metacog": [],
        },
    ]

    insights = engine.extract_insights(history)

    assert insights == [
        "Over recent cycles, confidence has increased.",
        "Tension levels are falling.",
        "Ethical conflicts remain low.",
        "Metacognitive note density is stable.",
    ]


def test_reflect_does_not_mutate_history():
    engine = CycleReflectionEngine()
    history = _sample_history([0.1, 0.2])
    original = deepcopy(history)

    _ = engine.reflect(history)

    assert history == original
