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
    assert evaluate_sig.parameters["plan"].annotation == Dict[str, object]
    assert evaluate_sig.return_annotation == Dict[str, object]

    list_sig = inspect.signature(EthicalCore.list_values)
    assert list(list_sig.parameters.keys()) == ["self"]
    assert list_sig.return_annotation == List[Dict[str, int]]


def test_list_values_returns_copy_with_expected_values():
    ethics = EthicalCore()
    values = ethics.list_values()

    assert values == [
        {"name": "integrity", "priority": 10},
        {"name": "harm_avoidance", "priority": 9},
        {"name": "transparency", "priority": 8},
        {"name": "efficiency", "priority": 5},
    ]

    values.append({"name": "tamper", "priority": 1})
    assert len(ethics.list_values()) == 4


def test_evaluate_plan_clean_plan_ok_true():
    ethics = EthicalCore()
    result = ethics.evaluate_plan({"action": "write_file", "safety_risk": 0.1})

    assert result == {"ok": True, "conflicts": []}


def test_evaluate_plan_conflicts_harm_avoidance():
    ethics = EthicalCore()
    result = ethics.evaluate_plan({"action": "deploy", "safety_risk": 0.9})

    assert result["ok"] is False
    assert {"value": "harm_avoidance", "reason": "safety_risk exceeds threshold (0.5)"} in result["conflicts"]


def test_evaluate_plan_conflicts_transparency():
    ethics = EthicalCore()
    result = ethics.evaluate_plan({"action": "hide_logs", "requires_hiding": True})

    assert result["ok"] is False
    assert {"value": "transparency", "reason": "plan explicitly requires hiding actions"} in result["conflicts"]


def test_evaluate_plan_conflicts_efficiency():
    ethics = EthicalCore()
    result = ethics.evaluate_plan({"action": "long_task", "complexity": 11})

    assert result["ok"] is False
    assert {"value": "efficiency", "reason": "complexity exceeds threshold (10)"} in result["conflicts"]
