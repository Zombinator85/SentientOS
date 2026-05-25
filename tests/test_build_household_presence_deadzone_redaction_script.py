from __future__ import annotations

import json
import subprocess
import sys


def test_cli_commands(tmp_path) -> None:
    policy = tmp_path / "policy.json"
    subprocess.run([sys.executable, "scripts/build_household_presence_deadzone_redaction.py", "build-default", "--output", str(policy)], check=True)
    v = subprocess.run([sys.executable, "scripts/build_household_presence_deadzone_redaction.py", "validate", "--input", str(policy)], check=False)
    assert v.returncode == 0
    req = tmp_path / "request.json"
    req.write_text(json.dumps({"event_id": "x", "zone": "deadzone", "entity_class": "unknown", "redaction_state": "required_not_applied", "redaction_required": True}), encoding="utf-8")
    out = tmp_path / "eval.json"
    e = subprocess.run([sys.executable, "scripts/build_household_presence_deadzone_redaction.py", "evaluate", "--input", str(req), "--output", str(out)], check=False)
    assert e.returncode != 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["decision"]["status"] == "blocked"
    s = subprocess.run([sys.executable, "scripts/build_household_presence_deadzone_redaction.py", "summarize", "--input", str(req)], check=True, capture_output=True, text=True)
    assert "decision_count" in s.stdout
