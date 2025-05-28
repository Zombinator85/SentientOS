import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import trust_engine as te


def test_log_and_explain(tmp_path, monkeypatch):
    monkeypatch.setenv("TRUST_DIR", str(tmp_path))
    from importlib import reload
    reload(te)

    event_id = te.log_event("gesture", "emotion vector", "User's tone joyful", "AI")
    assert event_id
    entry = te.get_event(event_id)
    assert entry and entry["explanation"] == "User's tone joyful"
