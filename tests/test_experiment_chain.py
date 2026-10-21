import importlib
import json
import sys
from typing import Dict, List

import pytest


@pytest.fixture
def chain_env(tmp_path, monkeypatch):
    monkeypatch.setenv("EXPERIMENTS_FILE", str(tmp_path / "experiments.json"))
    monkeypatch.setenv("EXPERIMENT_AUDIT_FILE", str(tmp_path / "experiment_audit.jsonl"))
    monkeypatch.setenv("EXPERIMENT_CHAIN_FILE", str(tmp_path / "chains.json"))
    monkeypatch.setenv("EXPERIMENT_CHAIN_LOG", str(tmp_path / "chain_log.jsonl"))

    for module_name in [
        "experiment_tracker",
        "sentientos.experiments.chain",
        "sentientos.experiments.runner",
    ]:
        if module_name in sys.modules:
            del sys.modules[module_name]

    import experiment_tracker  # type: ignore

    importlib.reload(experiment_tracker)
    monkeypatch.setattr(experiment_tracker, "require_admin_banner", lambda: None)
    monkeypatch.setattr(experiment_tracker, "require_lumos_approval", lambda: None)

    chain_module = importlib.import_module("sentientos.experiments.chain")
    runner_module = importlib.import_module("sentientos.experiments.runner")
    importlib.reload(chain_module)
    importlib.reload(runner_module)

    yield chain_module, runner_module, experiment_tracker, tmp_path


def _propose_active_experiment(
    tracker,
    description: str,
    criteria: str,
    *,
    requires_consensus: bool = False,
) -> str:
    exp_id = tracker.propose_experiment(
        description,
        "conditions",
        "expected",
        criteria=criteria,
        requires_consensus=requires_consensus,
    )
    tracker.update_status(exp_id, "active")
    return exp_id


def _read_log_lines(path) -> List[Dict[str, object]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _set_experiment_adapter(tracker, exp_id: str, name: str) -> None:
    from sentientos.experiments.consensus import compute_experiment_digest

    experiments = tracker._load()
    experiment = next(item for item in experiments if item["id"] == exp_id)
    experiment["adapter"] = {"name": name}
    experiment["digest"] = compute_experiment_digest(experiment)
    tracker._save(experiments)


def test_pending_nondeterministic_adapter_waits_for_approval(chain_env, monkeypatch):
    chain_module, runner, tracker, _ = chain_env
    exp_id = tracker.propose_experiment(
        "unreviewed camera experiment", "conditions", "expected",
        criteria="value >= 1", requires_consensus=False)
    _set_experiment_adapter(tracker, exp_id, "webcam")

    def fail_execute(_experiment):  # pragma: no cover - defensive
        raise AssertionError("unreviewed non-deterministic adapter must not execute")

    monkeypatch.setattr(runner, "execute_experiment", fail_execute)
    chain = chain_module.ExperimentChain(
        chain_id="nondeterministic-pending",
        description="pending hardware adapter waits for approval",
        start=exp_id,
        steps={exp_id: chain_module.ChainStep(id=exp_id)},
    )

    result = runner.run_chain(chain)

    assert result.outcome == "pending_consensus"
    assert result.steps[0].error == "pending_consensus"
    assert result.steps[0].success is None


def test_nondeterministic_adapter_runs_after_consensus_approval(chain_env, monkeypatch):
    chain_module, runner, tracker, _ = chain_env
    exp_id = tracker.propose_experiment(
        "reviewed camera experiment", "conditions", "expected",
        criteria="value >= 1", requires_consensus=True, quorum_k=2, quorum_n=3)
    _set_experiment_adapter(tracker, exp_id, "webcam")
    assert tracker.vote_experiment(exp_id, "peer-a", True)
    assert tracker.vote_experiment(exp_id, "peer-b", True)
    assert tracker.get_experiment(exp_id)["status"] == "active"
    executed: list[str] = []

    def execute(experiment):
        executed.append(experiment["id"])
        return {"value": 1}

    monkeypatch.setattr(runner, "execute_experiment", execute)
    chain = chain_module.ExperimentChain(
        chain_id="nondeterministic-approved",
        description="approved hardware adapter may execute",
        start=exp_id,
        steps={exp_id: chain_module.ChainStep(id=exp_id)},
    )

    result = runner.run_chain(chain)

    assert result.outcome == "success"
    assert executed == [exp_id]


def test_pending_deterministic_adapter_keeps_existing_execution_behavior(
        chain_env, monkeypatch):
    chain_module, runner, tracker, _ = chain_env
    exp_id = tracker.propose_experiment(
        "deterministic mock experiment", "conditions", "expected",
        criteria="value >= 1", requires_consensus=False)
    executed: list[str] = []

    def execute(experiment):
        executed.append(experiment["id"])
        return {"value": 1}

    monkeypatch.setattr(runner, "execute_experiment", execute)
    chain = chain_module.ExperimentChain(
        chain_id="deterministic-pending",
        description="deterministic adapter behavior is preserved",
        start=exp_id,
        steps={exp_id: chain_module.ChainStep(id=exp_id)},
    )

    result = runner.run_chain(chain)

    assert result.outcome == "success"
    assert executed == [exp_id]


def test_linear_chain_success(chain_env, monkeypatch):
    chain_module, runner, tracker, tmp_path = chain_env

    exp_ids = [
        _propose_active_experiment(tracker, f"exp-{idx}", "metric >= 1") for idx in range(3)
    ]

    for idx, exp_id in enumerate(exp_ids, start=1):
        tracker.comment_experiment(exp_id, "tester", f"step {idx}")

    contexts = {exp_id: {"metric": 5} for exp_id in exp_ids}

    def fake_execute(exp):
        return dict(contexts.get(exp["id"], {"metric": 5}))

    monkeypatch.setattr(runner, "execute_experiment", fake_execute)

    steps = {}
    for idx, exp_id in enumerate(exp_ids):
        next_id = exp_ids[idx + 1] if idx + 1 < len(exp_ids) else None
        steps[exp_id] = chain_module.ChainStep(id=exp_id, on_success=next_id)

    chain = chain_module.ExperimentChain(
        chain_id="linear",
        description="linear success",
        start=exp_ids[0],
        steps=steps,
        max_steps=6,
    )

    result = runner.run_chain(chain)

    assert result.outcome == "success"
    assert [step.experiment_id for step in result.steps] == exp_ids
    assert all(step.success is True for step in result.steps)

    log_entries = _read_log_lines(runner.CHAIN_LOG_PATH)
    assert log_entries[-1]["event"] == "chain_complete"
    assert log_entries[-1]["outcome"] == "success"


def test_failure_branch_terminates(chain_env, monkeypatch):
    chain_module, runner, tracker, _ = chain_env

    first = _propose_active_experiment(tracker, "first", "value >= 1")
    second = _propose_active_experiment(tracker, "second", "value >= 10")

    contexts = {
        first: {"value": 2},
        second: {"value": 1},
    }

    def fake_execute(exp):
        return dict(contexts[exp["id"]])

    monkeypatch.setattr(runner, "execute_experiment", fake_execute)

    chain = chain_module.ExperimentChain(
        chain_id="failure",
        description="failure branch",
        start=first,
        steps={
            first: chain_module.ChainStep(id=first, on_success=second),
            second: chain_module.ChainStep(id=second),
        },
        max_steps=4,
    )

    result = runner.run_chain(chain)
    assert result.outcome == "failure"
    assert [step.experiment_id for step in result.steps] == [first, second]
    assert result.steps[-1].success is False

    log_entries = _read_log_lines(runner.CHAIN_LOG_PATH)
    assert log_entries[-1]["outcome"] == "failure"


def test_max_steps_guard(chain_env, monkeypatch):
    chain_module, runner, tracker, _ = chain_env

    a = _propose_active_experiment(tracker, "a", "flag == 1")
    b = _propose_active_experiment(tracker, "b", "flag == 1")

    contexts = {a: {"flag": 1}, b: {"flag": 1}}

    def fake_execute(exp):
        return dict(contexts[exp["id"]])

    monkeypatch.setattr(runner, "execute_experiment", fake_execute)

    chain = chain_module.ExperimentChain(
        chain_id="loop",
        description="looping",
        start=a,
        steps={
            a: chain_module.ChainStep(id=a, on_success=b),
            b: chain_module.ChainStep(id=b, on_success=a),
        },
        max_steps=5,
    )

    result = runner.run_chain(chain)
    assert result.outcome == "aborted_limit"
    assert len(result.steps) == chain.max_steps

    log_entries = _read_log_lines(runner.CHAIN_LOG_PATH)
    assert log_entries[-1]["outcome"] == "aborted_limit"


def test_consensus_blocks_execution(chain_env, monkeypatch):
    chain_module, runner, tracker, _ = chain_env

    exp_id = tracker.propose_experiment(
        "needs consensus",
        "conditions",
        "expected",
        criteria="value > 0",
        requires_consensus=True,
    )

    chain = chain_module.ExperimentChain(
        chain_id="consensus",
        description="consensus gate",
        start=exp_id,
        steps={exp_id: chain_module.ChainStep(id=exp_id)},
    )

    def fail_execute(exp):  # pragma: no cover - defensive
        raise AssertionError("execute should not be called")

    monkeypatch.setattr(runner, "execute_experiment", fail_execute)

    result = runner.run_chain(chain)
    assert result.outcome == "pending_consensus"
    assert len(result.steps) == 1
    assert result.steps[0].error == "pending_consensus"

    log_entries = _read_log_lines(runner.CHAIN_LOG_PATH)
    assert log_entries[-1]["outcome"] == "pending_consensus"


def test_chain_determinism(chain_env, monkeypatch):
    chain_module, runner, tracker, _ = chain_env

    ids = [
        _propose_active_experiment(tracker, f"det-{idx}", "value >= 1")
        for idx in range(2)
    ]

    contexts = {ids[0]: {"value": 2}, ids[1]: {"value": 2}}

    def fake_execute(exp):
        return dict(contexts[exp["id"]])

    monkeypatch.setattr(runner, "execute_experiment", fake_execute)

    chain = chain_module.ExperimentChain(
        chain_id="determinism",
        description="deterministic",
        start=ids[0],
        steps={
            ids[0]: chain_module.ChainStep(id=ids[0], on_success=ids[1]),
            ids[1]: chain_module.ChainStep(id=ids[1]),
        },
    )

    result_one = runner.run_chain(chain)
    result_two = runner.run_chain(chain)

    seq_one = [(step.experiment_id, step.success) for step in result_one.steps]
    seq_two = [(step.experiment_id, step.success) for step in result_two.steps]

    assert seq_one == seq_two
