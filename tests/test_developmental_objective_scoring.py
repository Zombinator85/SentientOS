"""Fixture oracle acceptance; these tests do not demonstrate real-model learning."""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

from sentientos.developmental_model_replacement_experiment import (
    DevelopmentalModelReplacementError, DevelopmentalModelReplacementExperiment,
    FrozenCausalContext, ModelReplacementArtifactStore, ObjectivePredictionTask,
    _objective_score, _objective_score_legacy, _verify_objective_score,
)
from tests.test_developmental_model_replacement_experiment import FakeEndpoint, context, digest, identity

pytestmark = pytest.mark.no_legacy_skip


def task_context(task):
    values = asdict(context())
    values.pop('context_id'); values.pop('context_digest')
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
        assert 'objective_task' not in prompt['current_evidence']
        assert prompt['objective_task'] == plan['task_descriptor']
        descriptor = prompt['objective_task']
        suite = descriptor.get('probe_count', 1) > 1
        probes = descriptor['probe_inputs'] if 'probe_inputs' in descriptor else [
            int(descriptor['question'].split('input ')[1].split(' ')[0].rstrip('.'))]
        answers = [0 for _ in probes]
        if history:
            a, b = history
            multiplier = (b['output'] - a['output']) // (b['input'] - a['input'])
            offset = a['output'] - multiplier * a['input']
            answers = [multiplier * probe + offset for probe in probes]
        if self.mode == 'ignore': answers = [0 for _ in probes]
        if self.mode == 'partial': answers = ([*answers[:2], *([0] * max(0, len(answers) - 2))]
            if history else [0 for _ in probes])
        if self.mode == 'degrade': answers = ([0 for _ in probes] if history
            else [23] if not suite else [0 for _ in probes])
        if self.mode == 'unstable' and len(self.calls) == 3: answers = [0 for _ in probes]
        response = {'answers': answers} if suite else {'answer': answers[0]}
        output = json.dumps(response, sort_keys=True, separators=(',', ':'))
        if self.mode == 'malformed': output = '{"answer":23,"answer":0}'
        receipt.update(output_text=output, output_digest=digest({'output': output}))
        if self.mode == 'unavailable': receipt.pop('output_text')
        if self.mode == 'substitute': receipt['output_digest'] = digest({'output': 'different'})
        if self.mode == 'interrupt': raise KeyboardInterrupt('fixture crash after inference')
        return receipt


def experiment(root, mode='derive', *, model_b_mode=None, task=None):
    task = task or ObjectivePredictionTask(3, 2, 7)
    plans = list((root / 'developmental_experiments' / 'model_replacement' /
        'protocols').glob('objective-task-plan-*.json'))
    if len(plans) == 1:
        saved = json.loads(plans[0].read_text())
        if (saved.get('schema_version') == 'sentientos.objective_task_plan:v2'
                and saved.get('task') == task.specification()):
            task = ObjectivePredictionTask(task.multiplier, task.offset, task.probe_input,
                task.additional_probe_inputs, task.task_family_id,
                task.requires_task_family_history, saved['task_commitment_nonce'])
    a = TaskEndpoint('a', root, mode=mode)
    b = TaskEndpoint('b', root, mode=mode if model_b_mode is None else model_b_mode)
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
    task = ObjectivePredictionTask(3, 2, 7)
    owner, a, b = experiment(tmp_path, mode, task=task)
    run = owner.run()
    evaluation = run['objective_evaluation']
    assert 'output_text' not in json.dumps(run)
    assert evaluation['model_a_history_accuracy_delta'] == delta
    assert evaluation['model_b_history_accuracy_delta'] == delta
    assert evaluation['restoration_correctness_stable'] is stable
    assert evaluation['assessment'] == assessment
    assert len(a.calls) == 3 and len(b.calls) == 2
    assert all(task.commitment_nonce not in json.dumps(call['upstream_evidence'])
        for call in (*a.calls, *b.calls))
    recovered, a2, b2 = experiment(tmp_path, mode)
    assert json.loads(json.dumps(recovered.run())) == json.loads(json.dumps(run))
    assert a2.calls == b2.calls == []
    readonly = ModelReplacementArtifactStore(tmp_path, read_only=True)
    loaded = readonly.load_verified_run(run['run_id'], run['run_digest'])
    assert loaded['objective_evaluation'] == evaluation
    assert loaded['run_digest'] == run['run_digest']
    child = r"""
import json, sys
from pathlib import Path
from sentientos.developmental_model_replacement_experiment import ModelReplacementArtifactStore
value=json.load(sys.stdin)
store=ModelReplacementArtifactStore(Path(value["root"]), read_only=True)
run=store.load_verified_run(value["run_id"], value["run_digest"])
print(json.dumps({"run_digest":run["run_digest"],
    "objective_evaluation":run["objective_evaluation"],
    "condition_count":len(run["observations"])}, sort_keys=True))
"""
    recovered_child = subprocess.run([sys.executable, '-c', child],
        input=json.dumps({'root': str(tmp_path), 'run_id': run['run_id'],
            'run_digest': run['run_digest']}), text=True, capture_output=True,
        check=True, cwd=Path(__file__).resolve().parents[1])
    child_result = json.loads(recovered_child.stdout.strip().splitlines()[-1])
    assert child_result['run_digest'] == run['run_digest']
    assert child_result['objective_evaluation'] == evaluation
    assert child_result['condition_count'] == 5


def test_public_task_commitments_do_not_hash_low_entropy_oracle_inputs(tmp_path):
    task = ObjectivePredictionTask(3, 2, 7, (8, 9))
    owner, a, b = experiment(tmp_path, task=task)
    descriptor = task.public_descriptor()
    assert descriptor['task_digest_posture'] == 'salted_private_oracle_commitment:v1'
    assert 'multiplier' not in descriptor and 'offset' not in descriptor
    assert task.commitment_nonce not in json.dumps(descriptor)
    assert descriptor['task_digest'] != digest(task.specification())
    plan = owner.objective_plan
    legacy_semantic = {key: plan[key] for key in (
        'schema_version', 'protocol_id', 'protocol_digest', 'causal_context_digest',
        'task', 'task_descriptor', 'condition_order', 'rubric', 'authority')}
    legacy_semantic['schema_version'] = 'sentientos.objective_task_plan:v1'
    assert plan['plan_digest'] != digest(legacy_semantic)
    run = owner.run()
    assert task.commitment_nonce not in json.dumps(run)
    assert all(task.commitment_nonce not in call['prompt']
        and task.commitment_nonce not in json.dumps(call['upstream_evidence'])
        for call in (*a.calls, *b.calls))
    for multiplier in range(-8, 9):
        for offset in range(-8, 9):
            candidate = ObjectivePredictionTask(multiplier, offset, 7, (8, 9))
            assert digest(candidate.specification()) != descriptor['task_digest']


def test_historical_oracle_bearing_plan_remains_verifiable(tmp_path):
    from sentientos.developmental_history_intervention_experiment import (
        DevelopmentalExperimentStore, LEGACY_OBJECTIVE_SCHEMA, _digest as experiment_digest,
        make_protocol,
    )
    task = ObjectivePredictionTask(3, 2, 7)
    protocol = make_protocol(schema_version=LEGACY_OBJECTIVE_SCHEMA,
        snapshot_id='legacy-snapshot', snapshot_digest=experiment_digest({'snapshot': 1}),
        current_projection_id='legacy-current',
        current_projection_digest=experiment_digest({'current': 1}),
        current_fact_ids=(), record_ids=(), record_digests=(),
        record_set_digest=experiment_digest({'records': []}), model_id='legacy-model',
        model_artifact_digest=None, active_model_identity={},
        active_model_identity_digest=experiment_digest({}),
        authority_map_digest=experiment_digest({'authority': 'legacy'}),
        inference_budget={}, generation_posture={},
        instruction_template_digest=experiment_digest({'instruction': 'legacy'}),
        objective_task_digest=experiment_digest(task.specification()),
        objective_task_descriptor=task.legacy_public_descriptor())
    store = DevelopmentalExperimentStore(tmp_path / 'legacy')
    store.persist_protocol(protocol)
    plan = store.persist_objective_task_plan(protocol, task)
    assert plan['schema_version'] == 'sentientos.objective_task_plan:v1'
    assert plan['plan_digest'] == experiment_digest({key: value
        for key, value in plan.items() if key != 'plan_digest'})
    assert store.verify_objective_task_plan(protocol) == plan


def test_pending_legacy_request_recovers_privately_and_new_request_round_trips():
    from sentientos.resident_developmental_cognition import (
        LEGACY_OBJECTIVE_REQUEST_SCHEMA, _digest as request_digest,
        _parse_objective_request_bytes, _legacy_objective_request_digest,
        objective_request_payload, objective_task_for_request,
    )
    task = ObjectivePredictionTask(3, 2, 7)
    old_semantic = {"schema_version": LEGACY_OBJECTIVE_REQUEST_SCHEMA,
        "request_id": "historical-request", "task": task.specification(),
        "task_descriptor": task.legacy_public_descriptor()}
    old_request = {**old_semantic, "request_digest": request_digest(old_semantic)}
    recovered = objective_task_for_request(old_request)
    assert recovered.specification() == task.specification()
    assert recovered.public_descriptor()['task_digest'] != old_semantic[
        'task_descriptor']['task_digest']
    assert _legacy_objective_request_digest(request_id='historical-request',
        task=recovered) == old_request['request_digest']
    current = objective_request_payload(request_id='current-request', task=task)
    encoded = (json.dumps(current, sort_keys=True, indent=2) + '\n').encode()
    assert _parse_objective_request_bytes(encoded) == current
    assert current['task_commitment_nonce'] == task.commitment_nonce
    assert task.commitment_nonce not in json.dumps(current['task_descriptor'])


def test_historical_model_replacement_plan_remains_verifiable(tmp_path):
    from sentientos.developmental_model_replacement_experiment import _legacy_objective_plan
    task = ObjectivePredictionTask(3, 2, 7)
    owner, _, _ = experiment(tmp_path, task=task)
    legacy = _legacy_objective_plan(task, owner.protocol)
    path = owner.store.protocols / f"objective-task-plan-{owner.protocol.protocol_id}.json"
    owner.store._write(path, legacy)
    assert owner.store.verify_objective_plan(owner.protocol) == legacy
def test_new_digest_only_score_and_historical_output_retaining_score_are_readable(tmp_path):
    owner, _a, _b = experiment(tmp_path, 'derive')
    run = owner.run()
    score = run['observations'][0]['objective_task_score']
    assert 'output_text' not in score
    assert score['output_retention_posture'] == 'live_bytes_digest_verified_not_retained'
    assert _verify_objective_score(owner.objective_plan, score,
        run['observations'][0]['output_digest']) == score
    persisted = "\n".join(path.read_text(encoding="utf-8")
        for path in tmp_path.rglob("*.json"))
    assert '"output_text"' not in persisted
    assert '{"answer":23}' not in persisted

    # Preserve read compatibility for immutable v1 records already carrying the
    # exact bounded output bytes; new scoring never writes this representation.
    output = '{"answer":23}'
    historical = _objective_score_legacy(owner.objective_plan, output,
        digest({'output': output}))
    assert 'output_text' in historical
    assert _verify_objective_score(owner.objective_plan, historical,
        digest({'output': output})) == historical


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


def test_persisted_objective_run_recovers_oracle_from_private_plan(tmp_path):
    owner, _, _ = experiment(tmp_path)
    completed = owner.run()
    recovered = DevelopmentalModelReplacementExperiment(context=owner.context,
        model_a=FakeEndpoint(identity('a')), model_b=FakeEndpoint(identity('b')),
        artifact_root=tmp_path)
    assert recovered.objective_plan['task_commitment_nonce'] == owner.objective_plan[
        'task_commitment_nonce']
    assert recovered.run() == completed


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
    original, _, _ = experiment(tmp_path)
    original.run()
    supplied = ObjectivePredictionTask(3, 9, 7)
    a, b = TaskEndpoint('a', tmp_path), TaskEndpoint('b', tmp_path)
    with pytest.raises(DevelopmentalModelReplacementError, match='objective_task_context_binding_invalid'):
        DevelopmentalModelReplacementExperiment(context=original.context,
            model_a=a, model_b=b, artifact_root=tmp_path, objective_task=supplied)
    assert a.calls == b.calls == []


def test_score_evidence_reaches_durable_history_and_later_cognition(tmp_path):
    from sentientos.world_state_board import WorldStateBoardBuilder
    from tests.test_resident_developmental_cognition import owner as developmental_owner

    experiment_owner, _, _ = experiment(tmp_path / 'experiment')
    run = experiment_owner.run()
    records = experiment_owner.store.world_state_records(
        run_refs=((run['run_id'], run['run_digest']),))
    snapshot = WorldStateBoardBuilder().build(records)
    cognition_root = tmp_path / 'cognition'
    cognition, _ = developmental_owner(cognition_root,
        allowed_source_kinds=('embodiment',), max_selected_facts=1)
    first = cognition.run_tick(snapshot=snapshot, tick_id='tick-score-1')
    assert first.status == 'completed' and first.written_record_id
    record = cognition.writeback.store.get(first.written_record_id)
    selected = record.candidate['selected_facts'][0]
    projected_score = dict(run['objective_evaluation'])
    projected_score['condition_score_digests'] = [value.removeprefix('sha256:')
        for value in projected_score['condition_score_digests']]
    assert selected['payload']['objective_evaluation'] == projected_score
    assert selected['source']['digest'] == snapshot.facts[0].source.digest
    assert record.authority is False and record.current_truth is False
    # The score vector is meaningful only when its fixed condition order stays
    # joined to the independently verified endpoint and history bindings.
    projected_payload = snapshot.facts[0].payload
    observations = projected_payload['observations']
    assert [item['condition_id'] for item in observations] == [
        'model_a_history_present', 'model_a_history_withheld', 'model_b_history_present',
        'model_b_history_withheld', 'model_a_history_restored']
    assert [item['model_identity_digest'] for item in observations] == [
        identity('a').identity_digest, identity('a').identity_digest,
        identity('b').identity_digest, identity('b').identity_digest,
        identity('a').identity_digest]
    assert observations[0]['history_record_ids'] == observations[2]['history_record_ids'] == [
        'record-1', 'record-2']
    assert observations[1]['history_record_ids'] == observations[3]['history_record_ids'] == []
    assert observations[0]['output_digest'] == observations[4]['output_digest']

    recovered, invoker = developmental_owner(cognition_root,
        allowed_source_kinds=('embodiment',), max_selected_facts=1)
    later = recovered.run_tick(snapshot=snapshot, tick_id='tick-score-2')
    assert later.status == 'completed'
    assert first.written_record_id in later.prior_record_ids
    retrieval = next(request for request in invoker.requests
        if request.purpose == 'resident_developmental_retrieval_cognition')
    assert first.written_record_id in retrieval.upstream_evidence['record_ids']
    later_packet = recovered.writeback.store.get(first.written_record_id).candidate[
        'selected_facts'][0]['payload']
    assert later_packet['conditions'] == selected['payload']['conditions']
    assert later_packet['model_lineage'] == selected['payload']['model_lineage']
    assert later_packet['objective_evaluation'] == selected['payload']['objective_evaluation']


def test_model_specific_objective_outcome_survives_later_cognition(tmp_path):
    from sentientos.world_state_board import WorldStateBoardBuilder
    from tests.test_resident_developmental_cognition import owner as developmental_owner

    experiment_owner, _, _ = experiment(tmp_path / 'experiment', 'derive', model_b_mode='ignore')
    run = experiment_owner.run()
    assert run['objective_evaluation']['model_a_history_accuracy_delta'] == 1
    assert run['objective_evaluation']['model_b_history_accuracy_delta'] == 0
    snapshot = WorldStateBoardBuilder().build(experiment_owner.store.world_state_records(
        run_refs=((run['run_id'], run['run_digest']),)))
    cognition_root = tmp_path / 'cognition'
    cognition, _ = developmental_owner(cognition_root,
        allowed_source_kinds=('embodiment',), max_selected_facts=1)
    first = cognition.run_tick(snapshot=snapshot, tick_id='tick-model-score-1')
    assert first.status == 'completed' and first.written_record_id
    record = cognition.writeback.store.get(first.written_record_id)
    packet = record.candidate['selected_facts'][0]['payload']
    assert packet['objective_evaluation']['model_a_history_accuracy_delta'] == 1
    assert packet['objective_evaluation']['model_b_history_accuracy_delta'] == 0
    columns = packet['condition_columns']
    conditions = packet['conditions']
    assert [row[columns.index('cond')] for row in conditions] == [
        'model_a_history_present', 'model_a_history_withheld', 'model_b_history_present',
        'model_b_history_withheld', 'model_a_history_restored']
    assert [row[1] for row in packet['model_lineage']] == [
        identity('a').identity_digest.removeprefix('sha256:'),
        identity('b').identity_digest.removeprefix('sha256:')]
    assert len(packet['objective_evaluation']['condition_score_digests']) == len(conditions)
    assert [row[columns.index('withheld')] for row in conditions] == [False, True, False, True, False]

    recovered, invoker = developmental_owner(cognition_root,
        allowed_source_kinds=('embodiment',), max_selected_facts=1)
    later = recovered.run_tick(snapshot=snapshot, tick_id='tick-model-score-2')
    assert first.written_record_id in later.prior_record_ids
    retrieval = next(request for request in invoker.requests
        if request.purpose == 'resident_developmental_retrieval_cognition')
    assert first.written_record_id in retrieval.upstream_evidence['record_ids']


def test_preregistered_probe_suite_scores_transfer_and_recovers_without_replay(tmp_path):
    task = ObjectivePredictionTask(3, 2, 7, (8, 9, 10))
    owner, a, b = experiment(tmp_path, 'derive', model_b_mode='ignore', task=task)
    run = owner.run()
    assert run['objective_evaluation']['assessment'] == 'preregistered_probe_suite_scored'
    assert run['objective_evaluation']['model_a_history_accuracy_delta'] == 1
    assert run['objective_evaluation']['model_b_history_accuracy_delta'] == 0
    assert len(a.calls) == 3 and len(b.calls) == 2
    plan = owner.store.verify_objective_plan(owner.protocol)
    assert plan['task']['probe_inputs'] == [7, 8, 9, 10]
    a_history = run['observations'][0]['objective_task_score']
    a_withheld = run['observations'][1]['objective_task_score']
    b_history = run['observations'][2]['objective_task_score']
    assert a_history['answer'] == [23, 26, 29, 32] and a_history['correct'] is True
    assert a_withheld['correct'] is False and b_history['correct'] is False
    assert a_history['evaluator'] == 'deterministic_exact_integer_suite_oracle_v2'
    recovered, a2, b2 = experiment(tmp_path, 'derive', model_b_mode='ignore', task=task)
    assert recovered.run() == run
    assert a2.calls == b2.calls == []
    from sentientos.world_state_board import WorldStateBoardBuilder
    from tests.test_resident_developmental_cognition import owner as developmental_owner
    snapshot = WorldStateBoardBuilder().build(owner.store.world_state_records(
        run_refs=((run['run_id'], run['run_digest']),)))
    cognition_root = tmp_path / 'cognition'
    cognition, _ = developmental_owner(cognition_root,
        allowed_source_kinds=('embodiment',), max_selected_facts=1)
    first = cognition.run_tick(snapshot=snapshot, tick_id='tick-suite-1')
    assert first.status == 'completed' and first.written_record_id
    persisted = cognition.writeback.store.get(first.written_record_id)
    packet = persisted.candidate['selected_facts'][0]['payload']
    assert packet['objective_evaluation']['assessment'] == 'preregistered_probe_suite_scored'
    assert packet['objective_evaluation']['model_a_history_accuracy_delta'] == 1
    assert packet['objective_evaluation']['model_b_history_accuracy_delta'] == 0
    assert packet['objective_evaluation']['probe_count'] == 4
    assert packet['objective_evaluation']['model_a_history_correct_probe_delta'] == 4
    assert packet['objective_evaluation']['model_b_history_correct_probe_delta'] == 0
    assert len(packet['objective_evaluation']['condition_score_digests']) == 5
    later_owner, invoker = developmental_owner(cognition_root,
        allowed_source_kinds=('embodiment',), max_selected_facts=1)
    later = later_owner.run_tick(snapshot=snapshot, tick_id='tick-suite-2')
    assert first.written_record_id in later.prior_record_ids
    retrieval = next(request for request in invoker.requests
        if request.purpose == 'resident_developmental_retrieval_cognition')
    assert first.written_record_id in retrieval.upstream_evidence['record_ids']


@pytest.mark.parametrize('additional', [tuple(range(7, 23)), (7, 7), (7.5,)])
def test_probe_suite_bounds_and_identity_are_validated(additional):
    with pytest.raises(DevelopmentalModelReplacementError, match='objective_task_parameters_invalid'):
        ObjectivePredictionTask(3, 2, 7, additional).specification()


def test_probe_suite_malformed_answer_is_scored_as_failure_not_success(tmp_path):
    task = ObjectivePredictionTask(3, 2, 7, (8, 9))
    owner, _, _ = experiment(tmp_path, 'malformed', task=task)
    run = owner.run()
    assert run['experiment_completion_posture'] == 'completed'
    assert run['objective_evaluation']['assessment'] == 'preregistered_probe_suite_scored'
    assert all(item['objective_task_score']['status'] == 'invalid_answer'
        and item['objective_task_score']['correct'] is False
        for item in run['observations'])


def test_probe_suite_plan_tampering_fails_closed_without_replay(tmp_path):
    task = ObjectivePredictionTask(3, 2, 7, (8, 9))
    owner, a, b = experiment(tmp_path, task=task)
    run = owner.run()
    calls = (len(a.calls), len(b.calls))
    path = next(owner.store.protocols.glob('objective-task-plan-*.json'))
    value = json.loads(path.read_text())
    value['task']['offset'] += 1
    path.write_text(json.dumps(value, sort_keys=True, separators=(',', ':')))
    with pytest.raises(DevelopmentalModelReplacementError, match='objective_plan_binding_invalid'):
        owner.store.verify_objective_plan(owner.protocol, owner.objective_plan)
    assert (len(a.calls), len(b.calls)) == calls


def test_probe_suite_retains_partial_correctness_instead_of_collapsing_to_boolean(tmp_path):
    task = ObjectivePredictionTask(3, 2, 7, (8, 9, 10))
    owner, _, _ = experiment(tmp_path, 'partial', model_b_mode='ignore', task=task)
    run = owner.run()
    evaluation = run['objective_evaluation']
    assert evaluation['assessment'] == 'preregistered_probe_suite_scored'
    assert evaluation['model_a_history_accuracy_delta'] == 0
    assert evaluation['model_a_history_correct_probe_delta'] == 2
    assert evaluation['model_b_history_correct_probe_delta'] == 0
    assert run['observations'][0]['objective_task_score']['correct_count'] == 2
    assert run['observations'][0]['objective_task_score']['probe_count'] == 4


def test_probe_suite_output_substitution_is_incomplete_and_never_replayed(tmp_path):
    task = ObjectivePredictionTask(3, 2, 7, (8, 9))
    owner, a, b = experiment(tmp_path, 'substitute', task=task)
    run = owner.run()
    assert run['experiment_completion_posture'] == 'contradictory'
    assert len(a.calls) == 1 and not b.calls
    recovered, a2, b2 = experiment(tmp_path, 'derive', task=task)
    assert recovered.run() == run
    assert a2.calls == b2.calls == []


def test_truncated_output_is_unscorable_and_remains_receipt_bound(tmp_path):
    task = ObjectivePredictionTask(3, 2, 7)
    owner, _, _ = experiment(tmp_path, 'truncated', task=task)
    truncated = '{"answer":23'
    authenticated_full_output_digest = digest({"output": '{"answer":23} and trailing output'})
    score = _objective_score(owner.objective_plan, truncated,
        authenticated_full_output_digest, output_truncated=True)
    assert score['status'] == 'output_truncated'
    assert score['correct'] is None and score['answer'] is None
    assert _verify_objective_score(owner.objective_plan, score,
        authenticated_full_output_digest, output_truncated=True) == score
    with pytest.raises(DevelopmentalModelReplacementError, match='truncated_output_binding_invalid'):
        _verify_objective_score(owner.objective_plan, score, authenticated_full_output_digest,
            output_truncated=False)


def test_truncated_probe_suite_keeps_correctness_unknown(tmp_path):
    task = ObjectivePredictionTask(3, 2, 7, (8, 9))
    owner, _, _ = experiment(tmp_path, 'truncated-suite', task=task)
    authenticated_full_output_digest = digest({"output": '{"answers":[23,26,29]} and trailing output'})
    score = _objective_score(owner.objective_plan, '{"answers":[23,26,29]}',
        authenticated_full_output_digest, output_truncated=True)
    assert score['status'] == 'output_truncated'
    assert score['correct'] is None and score['answer'] is None
    assert score['correct_count'] is None
    assert _verify_objective_score(owner.objective_plan, score,
        authenticated_full_output_digest, output_truncated=True) == score
