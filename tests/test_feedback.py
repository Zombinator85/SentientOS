import json
from feedback import FeedbackManager, FeedbackRule


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
