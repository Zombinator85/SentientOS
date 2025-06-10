"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()
require_lumos_approval()
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval
# 🕯️ Privilege ritual migrated 2025-06-07 by Cathedral decree.
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
