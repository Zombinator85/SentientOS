import importlib
import json
import sys
from typing import Dict, List

import pytest


@pytest.fixture
def demo_env(tmp_path, monkeypatch):
    monkeypatch.setenv("EXPERIMENTS_FILE", str(tmp_path / "experiments.json"))
    monkeypatch.setenv("EXPERIMENT_AUDIT_FILE", str(tmp_path / "experiment_audit.jsonl"))
    monkeypatch.setenv("EXPERIMENT_CHAIN_FILE", str(tmp_path / "chains.json"))
    monkeypatch.setenv("EXPERIMENT_CHAIN_LOG", str(tmp_path / "chain_log.jsonl"))

    for module_name in [
        "experiment_tracker",
        "sentientos.experiments.chain",
        "sentientos.experiments.runner",
        "sentientos.experiments.demo_gallery",
    ]:
        sys.modules.pop(module_name, None)

    import experiment_tracker

    importlib.reload(experiment_tracker)
    chain_module = importlib.import_module("sentientos.experiments.chain")
    runner_module = importlib.import_module("sentientos.experiments.runner")
    gallery_module = importlib.import_module("sentientos.experiments.demo_gallery")
    importlib.reload(chain_module)
    importlib.reload(runner_module)
    importlib.reload(gallery_module)

    yield gallery_module, runner_module, experiment_tracker, tmp_path


def _read_log(path) -> List[Dict[str, object]]:
    if not path.exists():
        return []
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    return [json.loads(line) for line in lines]


def test_demo_simple_success(demo_env):
    gallery, runner, tracker, _ = demo_env

    demos = gallery.list_demos()
    assert any(item.demo_id == "demo_simple_success" for item in demos)

    first_run = gallery.run_demo("demo_simple_success")
    assert first_run.result.outcome == "success"
    assert len(first_run.result.steps) == 1
    assert first_run.result.steps[0].experiment_id == "demo_simple_step"
    assert first_run.result.steps[0].success is True
    assert first_run.result.steps[0].context.get("adapter_name") == "mock"

    log_entries = _read_log(runner.CHAIN_LOG_PATH)
    assert any(entry.get("chain_id") == first_run.chain.chain_id for entry in log_entries)
    assert any(entry.get("event") == "chain_complete" for entry in log_entries)

    second_run = gallery.run_demo("demo_simple_success")
    seq_first = [(step.experiment_id, step.success) for step in first_run.result.steps]
    seq_second = [(step.experiment_id, step.success) for step in second_run.result.steps]
    assert seq_first == seq_second

    if tracker.DATA_FILE.exists():
        experiments = json.loads(tracker.DATA_FILE.read_text(encoding="utf-8"))
        assert all(exp.get("adapter") == "mock" for exp in experiments)


def test_demo_chain_branch_paths(demo_env, monkeypatch):
    gallery, runner, tracker, _ = demo_env

    success_run = gallery.run_demo("demo_chain_branch")
    assert success_run.result.outcome == "success"
    assert success_run.result.steps[0].success is True
    assert success_run.result.steps[-1].experiment_id == "demo_branch_success"
    assert all(step.context.get("adapter_name") == "mock" for step in success_run.result.steps)

    original_execute = runner.execute_experiment

    def forced_context(exp):
        context = original_execute(exp)
        if exp.get("id") == "demo_branch_entry":
            context = dict(context)
            context["temp_c"] = 19.0
        return context

    monkeypatch.setattr(runner, "execute_experiment", forced_context)
    failure_run = gallery.run_demo("demo_chain_branch")
    assert failure_run.result.steps[0].success is False
    assert failure_run.result.steps[1].experiment_id == "demo_branch_recovery"
    assert failure_run.result.outcome == "success"

    log_entries = _read_log(runner.CHAIN_LOG_PATH)
    branch_entries = [entry for entry in log_entries if entry.get("chain_id") == failure_run.chain.chain_id]
    assert branch_entries

    if tracker.DATA_FILE.exists():
        experiments = json.loads(tracker.DATA_FILE.read_text(encoding="utf-8"))
        assert all(exp.get("adapter") == "mock" for exp in experiments)
