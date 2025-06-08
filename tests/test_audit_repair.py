import os
import sys
import json
import subprocess
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import audit_immutability as ai
from scripts import audit_repair


def test_audit_repair(tmp_path: Path) -> None:
    log = tmp_path / "log.jsonl"
    ai.append_entry(log, {"a": 1})
    ai.append_entry(log, {"b": 2})
    ai.append_entry(log, {"c": 3})

    lines = [json.loads(l) for l in log.read_text().splitlines()]
    lines[1]["prev_hash"] = "bad"
    log.write_text("\n".join(json.dumps(l) for l in lines) + "\n", encoding="utf-8")

    prev, fixed = audit_repair.repair_log(log, "0" * 64)
    assert fixed > 0

    repaired = [json.loads(l) for l in log.read_text().splitlines()]
    for i in range(1, len(repaired)):
        assert repaired[i]["prev_hash"] == repaired[i - 1]["rolling_hash"]

    env = os.environ.copy()
    env["LUMOS_AUTO_APPROVE"] = "1"
    env["PYTHONPATH"] = "."
    cp = subprocess.run([sys.executable, "verify_audits.py", str(tmp_path), "--repair"], env=env)
    assert cp.returncode == 0
