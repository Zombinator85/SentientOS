import json
import time
from sentientos.feedback import FeedbackManager, FeedbackRule


def test_rule_trigger(tmp_path):
    fm = FeedbackManager()
    triggered = {}

    def record(rule, uid, value):
        triggered['hit'] = (uid, value)

    fm.register_action('record', record)
    fm.add_rule(FeedbackRule(emotion='Joy', threshold=0.5, action='record'))
    fm.process(1, {'Joy': 0.6})
    assert triggered.get('hit') == (1, 0.6)


def test_load_rules(tmp_path):
    cfg = tmp_path / 'rules.json'
    cfg.write_text(json.dumps([{'emotion': 'Anger', 'threshold': 0.7, 'action': 'rec'}]))
    fm = FeedbackManager()
    fm.register_action('rec', lambda r, u, v: None)
    fm.load_rules(str(cfg))
    assert fm.rules and fm.rules[0].emotion == 'Anger'


def test_rule_duration(monkeypatch):
    fm = FeedbackManager()
    out = {}
    fm.register_action('rec', lambda r, u, v: out.setdefault('hits', 0) or out.update({'hits': out.get('hits',0)+1}))
    fm.add_rule(FeedbackRule(emotion='Focus', threshold=0.5, action='rec', duration=0.1))
    fm.process(1, {'Focus': 0.6})
    assert out.get('hits') is None
    time.sleep(0.11)
    fm.process(1, {'Focus': 0.6})
    assert out.get('hits') == 1


def test_load_rules_with_check(tmp_path, monkeypatch):
    mod = tmp_path / 'mod.py'
    mod.write_text('def check(v,e,c):\n    return c.get("flag")')
    cfg = tmp_path / 'rules.json'
    cfg.write_text(json.dumps([{'emotion': 'Joy', 'threshold': 0.5, 'action': 'rec', 'check_func': 'mod:check'}]))
    import sys
    fm = FeedbackManager()
    trig = {}
    fm.register_action('rec', lambda r,u,v: trig.setdefault('hit', True))
    fm.load_rules(str(cfg))
    fm.process(1, {'Joy':0.6}, {'flag': True})
    assert trig.get('hit')
    sys.path.remove(str(tmp_path))
