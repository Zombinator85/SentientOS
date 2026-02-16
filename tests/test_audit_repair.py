"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()


import os
import sys
import json
import subprocess
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import audit_immutability as ai


def test_audit_repair(tmp_path: Path) -> None:
    log = tmp_path / "log.jsonl"
    ai.append_entry(log, {"a": 1})
    ai.append_entry(log, {"b": 2})
    ai.append_entry(log, {"c": 3})

    lines = [json.loads(l) for l in log.read_text().splitlines()]
    lines[1]["prev_hash"] = "bad"
    log.write_text("\n".join(json.dumps(l) for l in lines) + "\n", encoding="utf-8")

    env = os.environ.copy()
    env["LUMOS_AUTO_APPROVE"] = "1"
    env["PYTHONPATH"] = "."

    cp = subprocess.run([sys.executable, "-m", "scripts.verify_audits", str(tmp_path), "--check-only"], env=env)
    assert cp.returncode != 0

    cp = subprocess.run([sys.executable, "scripts/audit_repair.py", "--logs-dir", str(tmp_path), "--fix"], env=env)
    assert cp.returncode == 0

    cp = subprocess.run([sys.executable, "-m", "scripts.verify_audits", str(tmp_path), "--check-only"], env=env)
    assert cp.returncode == 0
