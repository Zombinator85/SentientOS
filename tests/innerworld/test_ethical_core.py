import inspect
from typing import Dict, List

import pytest

from sentientos.ethics_core import EthicalCore


def test_ethical_core_importable():
    assert EthicalCore is not None


def test_ethical_core_methods_exist():
    ethics = EthicalCore()
    for method in ("evaluate_plan", "list_values"):
        assert hasattr(ethics, method)


def test_ethical_core_signatures():
    evaluate_sig = inspect.signature(EthicalCore.evaluate_plan)
    assert list(evaluate_sig.parameters.keys()) == ["self", "plan"]
    assert evaluate_sig.parameters["plan"].annotation == Dict[str, str]
    assert evaluate_sig.return_annotation == Dict[str, str]

    list_sig = inspect.signature(EthicalCore.list_values)
    assert list(list_sig.parameters.keys()) == ["self"]
    assert list_sig.return_annotation == List[str]


def test_ethical_core_placeholders_raise():
    ethics = EthicalCore()
    with pytest.raises(NotImplementedError):
        ethics.evaluate_plan({})

    with pytest.raises(NotImplementedError):
        ethics.list_values()
