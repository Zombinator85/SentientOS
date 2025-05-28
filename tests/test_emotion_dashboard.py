import json
from importlib import reload


def test_load_and_query(tmp_path):
    log = tmp_path / "vision.jsonl"
    entries = [
        {"timestamp": 1.0, "faces": [{"id": 1, "emotions": {"happy": 0.8}, "dominant": "happy"}]},
        {"timestamp": 2.0, "faces": [{"id": 1, "emotions": {"happy": 0.3, "sad": 0.7}, "dominant": "sad"}]},
    ]
    log.write_text("\n".join(json.dumps(e) for e in entries))
    import emotion_dashboard as ed
    reload(ed)
    data = ed.load_logs(log)
    assert 1 in data and len(data[1]) == 2
    state = ed.query_state(data, 1, 2.0)
    assert state and state["dominant"] == "sad"
