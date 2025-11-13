from __future__ import annotations

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import importlib
import json
import sys
from typing import Dict

import pytest

from sentientos.experiments.criteria_dsl import (
    CriteriaEvaluationError,
    CriteriaParseError,
    evaluate_criteria,
    parse_criteria,
)


@pytest.fixture
def tracker_env(tmp_path, monkeypatch):
    monkeypatch.setenv("EXPERIMENTS_FILE", str(tmp_path / "experiments.json"))
    monkeypatch.setenv("EXPERIMENT_AUDIT_FILE", str(tmp_path / "audit.jsonl"))

    if "experiment_tracker" in sys.modules:
        del sys.modules["experiment_tracker"]
    import experiment_tracker  # type: ignore

    importlib.reload(experiment_tracker)
    yield experiment_tracker, tmp_path


def evaluate(expr: str, context: Dict[str, object]) -> bool:
    parsed = parse_criteria(expr)
    return evaluate_criteria(parsed, context)


def test_parse_valid_expressions():
    assert evaluate("accuracy >= 0.9 && errors == 0", {"accuracy": 0.95, "errors": 0})
    assert evaluate("errors != 0 || retries > 3", {"errors": 1, "retries": 2})


def test_parse_invalid_expression():
    with pytest.raises(CriteriaParseError):
        parse_criteria("accuracy >=")


def test_unknown_identifier_raises():
    expr = parse_criteria("missing > 0")
    with pytest.raises(CriteriaEvaluationError):
        evaluate_criteria(expr, {"other": 1})


def test_malformed_expression_returns_failure(tracker_env):
    tracker, tmp_path = tracker_env
    exp_id = tracker.propose_experiment(
        "test",
        "cond",
        "expected",
        criteria="accuracy >=",
    )

    assert tracker.evaluate_experiment_success(exp_id, {"accuracy": 1.0}) is False
    result = tracker.evaluate_and_log_experiment_success(exp_id, {"accuracy": 1.0})
    assert result is False

    audit_entries = (tmp_path / "audit.jsonl").read_text().strip().splitlines()
    assert any(json.loads(entry)["action"] == "criteria_evaluation" for entry in audit_entries)


def test_evaluate_experiment_success(tracker_env):
    tracker, _ = tracker_env
    criteria = "accuracy >= 0.9 && errors == 0"
    exp_id = tracker.propose_experiment(
        "improve accuracy",
        "conditions",
        "expected",
        criteria=criteria,
    )

    assert tracker.evaluate_experiment_success(
        exp_id, {"accuracy": 0.95, "errors": 0}
    ) is True
    assert tracker.evaluate_experiment_success(
        exp_id, {"accuracy": 0.8, "errors": 1}
    ) is False
    assert tracker.evaluate_experiment_success(
        exp_id, {"accuracy": 0.95}
    ) is False
