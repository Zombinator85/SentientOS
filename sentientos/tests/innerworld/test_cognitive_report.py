import copy

import pytest

from sentientos.innerworld import CognitiveReportGenerator

pytestmark = pytest.mark.no_legacy_skip


def base_inputs():
    history = {
        "count": 3,
        "qualia_trends": {"confidence": 0.5, "tension": 0.2},
        "ethical_conflict_rate": 0.0,
        "metacog_note_frequency": 2,
    }
    reflection = {
        "trend_summary": {"confidence": "stable"},
        "insights": ["Confidence has remained stable across cycles."],
    }
    latest = {
        "cycle_id": 3,
        "qualia": {"confidence": 0.5, "tension": 0.2},
        "meta": [{"message": "note"}],
    }
    ethics = {"conflicts": []}
    return history, reflection, latest, ethics


def test_deterministic_output():
    generator = CognitiveReportGenerator()
    history, reflection, latest, ethics = base_inputs()

    first = generator.generate(history, reflection, latest, ethics)
    second = generator.generate(history, reflection, latest, ethics)

    assert first == second


def test_qualia_stability_classification():
    generator = CognitiveReportGenerator()
    history, reflection, latest, ethics = base_inputs()

    stable_report = generator.generate(history, reflection, latest, ethics)
    assert stable_report["overview"]["qualia_stability"] == "stable"

    shifting_latest = copy.deepcopy(latest)
    shifting_latest["qualia"]["confidence"] = 0.9
    shifting_report = generator.generate(history, reflection, shifting_latest, ethics)
    assert shifting_report["overview"]["qualia_stability"] == "shifting"

    volatile_latest = copy.deepcopy(latest)
    volatile_latest["qualia"]["confidence"] = 1.6
    volatile_report = generator.generate(history, reflection, volatile_latest, ethics)
    assert volatile_report["overview"]["qualia_stability"] == "volatile"


def test_ethical_signal_classification():
    generator = CognitiveReportGenerator()
    history, reflection, latest, ethics = base_inputs()

    low = generator.generate(history, reflection, latest, ethics)
    assert low["overview"]["ethical_signal"] == "low"

    moderate_history = dict(history, ethical_conflict_rate=0.1)
    moderate = generator.generate(moderate_history, reflection, latest, ethics)
    assert moderate["overview"]["ethical_signal"] == "moderate"

    high_history = dict(history, ethical_conflict_rate=0.3)
    high = generator.generate(high_history, reflection, latest, ethics)
    assert high["overview"]["ethical_signal"] == "high"

    critical_history = dict(history, ethical_conflict_rate=0.5)
    critical = generator.generate(critical_history, reflection, latest, ethics)
    assert critical["overview"]["ethical_signal"] == "critical"


def test_metacog_density_classification():
    generator = CognitiveReportGenerator()
    history, reflection, latest, ethics = base_inputs()

    low_history = dict(history, metacog_note_frequency=0)
    low = generator.generate(low_history, reflection, latest, ethics)
    assert low["overview"]["metacog_activity"] == "low"

    moderate_history = dict(history, metacog_note_frequency=4)
    moderate = generator.generate(moderate_history, reflection, latest, ethics)
    assert moderate["overview"]["metacog_activity"] == "moderate"

    high_history = dict(history, metacog_note_frequency=10, count=3)
    high = generator.generate(high_history, reflection, latest, ethics)
    assert high["overview"]["metacog_activity"] == "high"


def test_inputs_are_not_mutated():
    generator = CognitiveReportGenerator()
    history, reflection, latest, ethics = base_inputs()

    history_original = copy.deepcopy(history)
    reflection_original = copy.deepcopy(reflection)
    latest_original = copy.deepcopy(latest)
    ethics_original = copy.deepcopy(ethics)

    generator.generate(history, reflection, latest, ethics)

    assert history == history_original
    assert reflection == reflection_original
    assert latest == latest_original
    assert ethics == ethics_original


def test_simulation_notes_optional():
    generator = CognitiveReportGenerator()
    history, reflection, latest, ethics = base_inputs()

    report = generator.generate(history, reflection, latest, ethics, simulation_report=None)

    assert report["simulation_notes"] == {}
