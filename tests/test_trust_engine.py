from admin_utils import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Banner: This script requires admin & Lumos approval."""
require_admin_banner()
require_lumos_approval()
# 🕯️ Privilege ritual migrated 2025-06-07 by Cathedral decree.
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import trust_engine as te


def test_log_and_explain(tmp_path, monkeypatch):
    monkeypatch.setenv("TRUST_DIR", str(tmp_path))
    monkeypatch.setenv("SENTIENTOS_HEADLESS", "1")
    from importlib import reload
    reload(te)

    event_id = te.log_event("gesture", "emotion vector", "User's tone joyful", "AI")
    assert event_id
    entry = te.get_event(event_id)
    assert entry and entry["explanation"] == "User's tone joyful"


def test_policy_triggers_gesture(tmp_path, monkeypatch):
    """Policy evaluation logs a gesture and explanation."""
    monkeypatch.setenv("TRUST_DIR", str(tmp_path))
    monkeypatch.setenv("SENTIENTOS_HEADLESS", "1")
    from importlib import reload
    reload(te)
    import policy_engine as pe
    reload(pe)

    # Save a policy for the trust engine
    te.update_policy("gestures", {"wave": True}, "tester", "init")
    assert te.load_policy("gestures")["wave"] is True

    cfg = tmp_path / "pol.yml"
    cfg.write_text('{"policies":[{"id":"wave","conditions":{"tags":["wave"]},"actions":[{"type":"gesture","name":"wave"}]}]}')
    engine = pe.PolicyEngine(str(cfg))
    actions = engine.evaluate({"tags": ["wave"]})
    assert actions and actions[0]["name"] == "wave"

    eid = te.log_event("gesture", "policy:wave", "Triggered wave gesture", "policy_engine")
    entry = te.get_event(eid)
    assert entry and entry["explanation"] == "Triggered wave gesture"
