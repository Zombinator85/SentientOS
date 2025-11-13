from __future__ import annotations

import importlib
import json
import sys
from typing import Callable, Dict

import pytest


def _reload_module(name: str) -> None:
    if name in sys.modules:
        del sys.modules[name]
    importlib.invalidate_caches()


@pytest.fixture
def load_hypothesis(tmp_path, monkeypatch) -> Callable[[str, str], object]:
    def _loader(rate_minutes: str = "0", subdir: str = "default"):
        base = tmp_path / subdir
        base.mkdir()
        monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(base))
        monkeypatch.setenv("SENTIENTOS_HYPOTHESIS_RATE_MINUTES", rate_minutes)
        _reload_module("sentientos.experiments.hypothesis")
        module = importlib.import_module("sentientos.experiments.hypothesis")
        return module

    return _loader


def test_deterministic_generation(load_hypothesis) -> None:
    module = load_hypothesis(subdir="determinism")
    event = {"type": "stress_spike", "stress": 0.92, "beta": 0.88}
    spec_one = module.generate_hypothesis(event)
    spec_two = module.generate_hypothesis(event)
    assert spec_one == spec_two


def test_caching_reuses_previous_spec(load_hypothesis) -> None:
    module = load_hypothesis(subdir="cache")
    event = {"type": "stress_spike", "stress": 0.91, "beta": 0.81}
    assert module.generate_hypothesis(event) is not None
    cache_path = module.CACHE_PATH
    assert cache_path.exists()
    with cache_path.open("r", encoding="utf-8") as handle:
        lines_after_first = handle.readlines()
    assert len(lines_after_first) == 1
    module.generate_hypothesis(event)
    with cache_path.open("r", encoding="utf-8") as handle:
        lines_after_second = handle.readlines()
    assert lines_after_second == lines_after_first


def test_rate_limiting_blocks_fast_repeats(load_hypothesis) -> None:
    module = load_hypothesis(rate_minutes="30", subdir="rate")
    first = module.generate_hypothesis({"type": "stress_spike", "stress": 0.95, "beta": 0.87})
    assert first is not None
    blocked = module.generate_hypothesis({"type": "stress_spike", "stress": 0.96, "beta": 0.9})
    assert blocked is None


def test_generated_spec_contains_required_fields(load_hypothesis) -> None:
    module = load_hypothesis(subdir="fields")
    event = {"type": "sensor_anomaly", "signal": "gamma", "gamma": 0.77}
    spec = module.generate_hypothesis(event)
    assert spec is not None
    for key in {"description", "conditions", "expected", "criteria", "proposer"}:
        assert key in spec
        assert isinstance(spec[key], str)
        assert spec[key]
    from sentientos.experiments.criteria_dsl import parse_criteria

    parse_criteria(spec["criteria"])
    assert spec["proposer"] == "auto"


@pytest.mark.parametrize(
    "event", [{"type": "experiment_proposal", "experiment_id": "abc123"}, {"proposal": "existing"}]
)
def test_safety_filters_preexisting_proposals(load_hypothesis, event: Dict[str, str]) -> None:
    module = load_hypothesis(subdir="safety")
    original = dict(event)
    result = module.generate_hypothesis(event)
    assert result is None
    assert event == original
    assert "actuator" not in module.__dict__


def test_autonomous_ops_integration(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("SENTIENTOS_HYPOTHESIS_RATE_MINUTES", "0")
    for name in [
        "sentientos.experiments.hypothesis",
        "experiment_tracker",
        "autonomous_ops",
    ]:
        _reload_module(name)
    import experiment_tracker as et

    data_file = et.DATA_FILE
    if data_file.exists():
        data_file.unlink()

    import autonomous_ops as ops

    event = {"type": "stress_spike", "stress": 0.91, "beta": 0.83}
    ops.analyze_events([event])

    assert data_file.exists()
    payload = json.loads(data_file.read_text(encoding="utf-8"))
    assert len(payload) == 1
    experiment = payload[0]
    assert experiment["proposer"] == "auto"
    assert experiment["description"].startswith("Investigate")
    assert experiment["criteria"]
