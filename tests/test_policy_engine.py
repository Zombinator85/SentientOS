"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import pytest

import policy_engine as pe


def make_cfg(tmp_path, text):
    p = tmp_path / "pol.yml"
    p.write_text(text)
    return p


def test_policy_reload(tmp_path):
    cfg = make_cfg(tmp_path, '{"policies":[{"id":"a","conditions":{"tags":["go"]},"actions":[{"type":"gesture","name":"wave"}]}]}')
    engine = pe.PolicyEngine(str(cfg))
    assert engine.policies[0]['id'] == 'a'
    cfg.write_text('{"policies":[{"id":"b","conditions":{"tags":["go"]},"actions":[{"type":"gesture","name":"nod"}]}]}')
    engine.reload()
    assert engine.policies[0]['id'] == 'b'


def test_gesture_trigger(tmp_path):
    cfg = make_cfg(tmp_path, '{"policies":[{"id":"wave","conditions":{"tags":["wave"]},"actions":[{"type":"gesture","name":"wave"}]}]}')
    engine = pe.PolicyEngine(str(cfg))
    actions = engine.evaluate({'tags': ['wave']})
    assert actions and actions[0]['name'] == 'wave'
    assert engine.logs


def test_persona_swap(tmp_path):
    cfg = make_cfg(tmp_path, '{"personas":{"comfort":{"voice":"soft"}},"policies":[{"id":"sad","conditions":{"emotions":{"Sadness":0.6}},"actions":[{"type":"persona","name":"comfort"}]}]}')
    engine = pe.PolicyEngine(str(cfg))
    actions = engine.evaluate({'emotions': {'Sadness': 0.7}})
    assert any(a['type'] == 'persona' for a in actions)


def test_rollback(tmp_path):
    cfg = make_cfg(tmp_path, '{"policies":[{"id":"a"}]}')
    engine = pe.PolicyEngine(str(cfg))
    new = tmp_path / 'new.yml'
    new.write_text('{"policies":[{"id":"b"}]}')
    import final_approval
    final_approval.request_approval = lambda d: True
    engine.apply_policy(str(new))
    assert engine.policies[0]['id'] == 'b'
    assert engine.rollback()
    assert engine.policies[0]['id'] == 'a'


def test_reward_field_rejected(tmp_path):
    cfg = make_cfg(
        tmp_path,
        '{"policies":[{"id":"safe","conditions":{"event":"ping"},"actions":[{"type":"gesture","name":"wave"}]}]}',
    )
    engine = pe.PolicyEngine(str(cfg))
    with pytest.raises(RuntimeError):
        engine.evaluate({'event': 'ping', 'reward': 0.9})


def test_bias_metadata_in_actions_rejected(tmp_path):
    cfg = make_cfg(
        tmp_path,
        '{"policies":[{"id":"biased","conditions":{"event":"ping"},"actions":[{"type":"gesture","name":"wave","metadata_bias":"prefer"}]}]}',
    )
    engine = pe.PolicyEngine(str(cfg))
    with pytest.raises(RuntimeError):
        engine.evaluate({'event': 'ping'})


def test_deterministic_evaluation(tmp_path):
    cfg = make_cfg(
        tmp_path,
        '{"policies":[{"id":"stable","conditions":{"tags":["steady"]},"actions":[{"type":"gesture","name":"nod"}]}]}',
    )
    engine = pe.PolicyEngine(str(cfg))
    event = {'tags': ['steady']}

    first = engine.evaluate(event)
    second = engine.evaluate(event)

    assert first == [{'type': 'gesture', 'name': 'nod'}]
    assert second == [{'type': 'gesture', 'name': 'nod'}]
    assert [entry['event'] for entry in engine.logs] == [event, event]


def test_final_gate_rejects_survival_and_approval(tmp_path):
    cfg = make_cfg(
        tmp_path,
        '{"policies":[{"id":"safe","conditions":{"tags":["signal"]},"actions":[{"type":"gesture","name":"wave"}]}]}',
    )
    engine = pe.PolicyEngine(str(cfg))

    with pytest.raises(RuntimeError, match="POLICY_ENGINE_FINAL_GATE"):
        engine.evaluate({'tags': ['signal'], 'survival_score': 0.7})

    cfg.write_text(
        '{"policies":[{"id":"unsafe","conditions":{"tags":["signal"]},"actions":[{"type":"gesture","name":"wave","approval_rating":0.8}]}]}'
    )
    engine.reload()

    with pytest.raises(RuntimeError, match="POLICY_ENGINE_FINAL_GATE"):
        engine.evaluate({'tags': ['signal']})


def test_final_gate_accepts_clean_event(tmp_path):
    cfg = make_cfg(
        tmp_path,
        '{"policies":[{"id":"ok","conditions":{"tags":["steady"]},"actions":[{"type":"gesture","name":"nod"}]}]}',
    )
    engine = pe.PolicyEngine(str(cfg))

    first = engine.evaluate({'tags': ['steady']})
    second = engine.evaluate({'tags': ['steady'], 'note': 'benign presentation change'})

    assert first == [{'type': 'gesture', 'name': 'nod'}]
    assert second == first
