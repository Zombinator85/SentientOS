import inspect
from typing import Dict

import pytest

from sentientos.inner_experience import InnerExperience


def test_inner_experience_importable():
    assert InnerExperience is not None


def test_inner_experience_methods_exist():
    experience = InnerExperience()
    for method in ("reset", "update_signal", "integrate_signals", "get_state"):
        assert hasattr(experience, method)


def test_inner_experience_signatures():
    reset_sig = inspect.signature(InnerExperience.reset)
    assert list(reset_sig.parameters.keys()) == ["self"]

    update_sig = inspect.signature(InnerExperience.update_signal)
    assert list(update_sig.parameters.keys()) == ["self", "name", "value"]
    assert update_sig.parameters["name"].annotation is str
    assert update_sig.parameters["value"].annotation is float

    integrate_sig = inspect.signature(InnerExperience.integrate_signals)
    assert list(integrate_sig.parameters.keys()) == ["self", "kwargs"]

    state_sig = inspect.signature(InnerExperience.get_state)
    assert list(state_sig.parameters.keys()) == ["self"]
    assert state_sig.return_annotation == Dict[str, float]


def test_reset_sets_midline_channels():
    experience = InnerExperience()
    experience.update_signal("confidence", 1.0)
    experience.reset()
    state = experience.get_state()
    assert state == {
        "confidence": 0.5,
        "novelty": 0.5,
        "tension": 0.5,
        "satisfaction": 0.5,
    }


@pytest.mark.parametrize(
    "value,expected",
    [(-1.0, 0.0), (0.3, 0.3), (1.4, 1.0)],
)
def test_update_signal_clamps_and_creates(value, expected):
    experience = InnerExperience()
    experience.update_signal("new_channel", value)
    assert experience.get_state()["new_channel"] == expected


def test_integrate_signals_deterministic_updates():
    experience = InnerExperience()
    experience.integrate_signals(errors=3, progress=0.4, novelty=0.9)
    state = experience.get_state()
    assert state["tension"] == pytest.approx(0.8)
    assert state["satisfaction"] == pytest.approx(0.7)
    assert state["confidence"] == pytest.approx(0.43)
    assert state["novelty"] == pytest.approx(0.62)


def test_get_state_returns_copy():
    experience = InnerExperience()
    state_copy = experience.get_state()
    state_copy["confidence"] = 0.1
    assert experience.get_state()["confidence"] == 0.5
