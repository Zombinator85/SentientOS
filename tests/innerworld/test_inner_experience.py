import inspect
from typing import Dict

import pytest

from sentientos.inner_experience import InnerExperience


def test_inner_experience_importable():
    assert InnerExperience is not None


def test_inner_experience_methods_exist():
    experience = InnerExperience()
    for method in ("reset", "update_signal", "get_state"):
        assert hasattr(experience, method)


def test_inner_experience_signatures():
    reset_sig = inspect.signature(InnerExperience.reset)
    assert list(reset_sig.parameters.keys()) == ["self"]

    update_sig = inspect.signature(InnerExperience.update_signal)
    assert list(update_sig.parameters.keys()) == ["self", "name", "value"]
    assert update_sig.parameters["name"].annotation is str
    assert update_sig.parameters["value"].annotation is float

    state_sig = inspect.signature(InnerExperience.get_state)
    assert list(state_sig.parameters.keys()) == ["self"]
    assert state_sig.return_annotation == Dict[str, float]


def test_inner_experience_placeholders_raise():
    experience = InnerExperience()
    with pytest.raises(NotImplementedError):
        experience.reset()

    with pytest.raises(NotImplementedError):
        experience.update_signal("mood", 0.5)

    with pytest.raises(NotImplementedError):
        experience.get_state()
