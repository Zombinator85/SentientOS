"""Fixture oracle acceptance; these tests do not demonstrate real-model learning."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from sentientos.developmental_model_replacement_experiment import (
    DevelopmentalModelReplacementError, DevelopmentalModelReplacementExperiment,
    FrozenCausalContext, ModelReplacementArtifactStore, ObjectivePredictionTask,
)
from tests.test_developmental_model_replacement_experiment import FakeEndpoint, context, digest, identity

pytestmark = pytest.mark.no_legacy_skip


def task_context(task):
    values = asdict(context())
    values.pop('context_id'); values.pop('context_digest')
    current = dict(values['current_projection_payload'])
    current['objective_task'] = task.public_descriptor()
    values.update(current_projection_payload=current,
                  projected_content_digest=digest(current),
                  current_projection_digest=digest({'projection': current}))
    # Historical deterministic examples, not current truth or an authority grant.
    history = [{'record_id': 'record-1', 'input': 1, 'output': 5},
               {'record_id': 'record-2', 'input': 2, 'output': 8}]
    for row in history:
        row['record_digest'] = digest(row)
    values.update(history_projection_payload=tuple(history),
        history_record_ids=tuple(row['record_id'] for row in history),
        history_record_digests=tuple(row['record_digest'] for row in history),
        history_record_set_digest=digest({'record_ids': [row['record_id'] for row in history],
            'record_digests': [row['record_digest'] for row in history]}))
    return FrozenCausalContext.create(**values)


class TaskEndpoint(FakeEndpoint):
    def __init__(self, name, root, *, mode='derive'):
        super().__init__(identity(name))
        self.root, self.mode = root / 'developmental_experiments' / 'model_replacement', mode

    def infer(self, **kwargs):
        # The oracle plan must exist before even the first call.
        plans = list((self.root / 'protocols').glob('objective-task-plan-*.json'))
        assert len(plans) == 1
        plan = json.loads(plans[0].read_text())
        assert kwargs['upstream_evidence']['objective_task_plan_digest'] == plan['plan_digest']
        receipt = dict(super().infer(**kwargs))
        prompt = json.loads(kwargs['prompt'])
        history = prompt['developmental_history']
        assert 'multiplier' not in json.dumps(prompt['current_evidence'])
        answer = 0
        if history:
            a, b = history
            multiplier = (b['output'] - a['output']) // (b['input'] - a['input'])
            offset = a['output'] - multiplier * a['input']
            answer = multiplier * 7 + offset
        if self.mode == 'ignore': answer = 0
        if self.mode == 'degrade': answer = 0 if history else 23
        if self.mode == 'unstable' and len(self.calls) == 3: answer = 0
        output = json.dumps({'answer': answer}, sort_keys=True, separators=(',', ':'))
        if self.mode == 'malformed': output = '{"answer":23,"answer":0}'
        receipt.update(output_text=output, output_digest=digest({'output': output}))
        if self.mode == 'unavailable': receipt.pop('output_text')
        if self.mode == 'substitute': receipt['output_digest'] = digest({'output': 'different'})
        if self.mode == 'interrupt': raise KeyboardInterrupt('fixture crash after inference')
        return receipt


def experiment(root, mode='derive'):
    task = ObjectivePredictionTask(3, 2, 7)
    a, b = TaskEndpoint('a', root, mode=mode), TaskEndpoint('b', root, mode=mode)
    return DevelopmentalModelReplacementExperiment(context=task_context(task),
        model_a=a, model_b=b, artifact_root=root, objective_task=task), a, b


@pytest.mark.parametrize('mode,delta,stable,assessment', [
    ('derive', 1, True, 'single_preregistered_task_scored'),
    ('ignore', 0, True, 'single_preregistered_task_scored'),
    ('degrade', -1, True, 'single_preregistered_task_scored'),
    ('unstable', 1, False, 'single_preregistered_task_scored'),
    ('malformed', 0, True, 'single_preregistered_task_scored'),
    ('unavailable', None, None, 'unscoreable_missing_output'),
])
def test_objective_treatments_and_no_replay(tmp_path, mode, delta, stable, assessment):
    owner, a, b = experiment(tmp_path, mode)
    run = owner.run()
    evaluation = run['objective_evaluation']
    assert evaluation['model_a_history_accuracy_delta'] == delta
    assert evaluation['model_b_history_accuracy_delta'] == delta
    assert evaluation['restoration_correctness_stable'] is stable
    assert evaluation['assessment'] == assessment
    assert len(a.calls) == 3 and len(b.calls) == 2
    recovered, a2, b2 = experiment(tmp_path, mode)
    assert json.loads(json.dumps(recovered.run())) == json.loads(json.dumps(run))
    assert a2.calls == b2.calls == []
    readonly = ModelReplacementArtifactStore(tmp_path, read_only=True)
    loaded = readonly.load_verified_run(run['run_id'], run['run_digest'])
    assert loaded['objective_evaluation'] == evaluation
    assert loaded['run_digest'] == run['run_digest']


def test_output_substitution_is_incomplete_not_replayed(tmp_path):
    owner, a, b = experiment(tmp_path, 'substitute')
    run = owner.run()
    assert run['experiment_completion_posture'] == 'contradictory'
    assert len(a.calls) == 1 and not b.calls
    owner.run()
    assert len(a.calls) == 1


def test_missing_plan_recovery_rejected(tmp_path):
    owner, _, _ = experiment(tmp_path)
    run = owner.run()
    next((owner.store.protocols).glob('objective-task-plan-*')).unlink()
    with pytest.raises(DevelopmentalModelReplacementError, match='objective_plan_missing'):
        ModelReplacementArtifactStore(tmp_path, read_only=True).load_verified_run(run['run_id'], run['run_digest'])


def test_oracle_cannot_be_changed_after_calls(tmp_path):
    owner, _, _ = experiment(tmp_path)
    owner.run()
    plan_path = next((owner.store.protocols).glob('objective-task-plan-*'))
    value = json.loads(plan_path.read_text()); value['task']['offset'] = 9
    plan_path.write_text(json.dumps(value, sort_keys=True, separators=(',', ':')))
    with pytest.raises(DevelopmentalModelReplacementError, match='artifact_identity_collision'):
        owner.run()


def test_public_task_requires_matching_oracle_before_execution(tmp_path):
    task = ObjectivePredictionTask(3, 2, 7)
    with pytest.raises(DevelopmentalModelReplacementError, match='objective_task_oracle_missing'):
        DevelopmentalModelReplacementExperiment(context=task_context(task),
            model_a=FakeEndpoint(identity('a')), model_b=FakeEndpoint(identity('b')), artifact_root=tmp_path)


def test_rehashed_wrong_assessment_rejected_and_projection_is_bounded(tmp_path):
    owner, _, _ = experiment(tmp_path)
    run = owner.run()
    records = owner.store.world_state_records(run_refs=((run['run_id'], run['run_digest']),))
    assert records[0]['payload']['objective_evaluation'] == run['objective_evaluation']
    assert 'output_text' not in json.dumps(records)
    changed = json.loads(json.dumps(run))
    changed.pop('run_id'); changed.pop('run_digest')
    changed['objective_evaluation']['model_a_history_accuracy_delta'] = -1
    run_id, run_digest = owner.store.persist_run(changed)
    with pytest.raises(DevelopmentalModelReplacementError, match='objective_evaluation_binding_invalid'):
        owner.store.load_verified_run(run_id, run_digest)


def test_interrupted_scoring_recovery_never_replays_inference(tmp_path):
    owner, a, b = experiment(tmp_path, 'interrupt')
    with pytest.raises(KeyboardInterrupt, match='fixture crash'):
        owner.run(trial_id='interrupted-score')
    assert len(a.calls) == 1 and not b.calls
    recovered, a2, b2 = experiment(tmp_path, 'derive')
    result = recovered.run(trial_id='interrupted-score')
    assert result['experiment_completion_posture'] == 'incomplete'
    assert result['objective_evaluation']['assessment'] == 'unscoreable_missing_output'
    assert a2.calls == b2.calls == []


def test_oracle_identity_mismatch_fails_before_inference(tmp_path):
    declared = ObjectivePredictionTask(3, 2, 7)
    supplied = ObjectivePredictionTask(3, 9, 7)
    a, b = TaskEndpoint('a', tmp_path), TaskEndpoint('b', tmp_path)
    with pytest.raises(DevelopmentalModelReplacementError, match='objective_task_context_binding_invalid'):
        DevelopmentalModelReplacementExperiment(context=task_context(declared),
            model_a=a, model_b=b, artifact_root=tmp_path, objective_task=supplied)
    assert a.calls == b.calls == []
