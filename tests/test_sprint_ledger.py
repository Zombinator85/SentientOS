import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import healing_sprint_ledger as hsl


def test_gather_metrics(tmp_path, monkeypatch):
    docs = tmp_path
    monkeypatch.chdir(docs)
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    # create sample federation log
    (log_dir / "federation_log.jsonl").write_text(json.dumps({"peer":"a"})+"\n"+json.dumps({"peer":"b"})+"\n")
    # wounds file
    (log_dir / "memory.jsonl.wounds").write_text("one\ntwo\n")
    # AUDIT_LOG_FIXES.md with a repaired line
    (docs / "AUDIT_LOG_FIXES.md").write_text("- 2025-11 Living Audit Sprint: 5 malformed lines repaired.\n")
    # CONTRIBUTORS.md with saints
    (docs / "CONTRIBUTORS.md").write_text("## Audit Saints\n- Ada\n")

    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(log_dir))
    metrics = hsl.gather_metrics()
    assert metrics["logs_healed"] == 5
    assert metrics["saints"] == 1
    assert metrics["wounds"] == 2
    assert metrics["nodes"] == 2

    # writing dashboard
    (log_dir / "saint_stories.jsonl").write_text(json.dumps({"saint":"Ada","story":"Fixed"})+"\n")
    hsl.write_dashboard(metrics, hsl.read_stories())
    out = (docs / "docs" / "SPRINT_LEDGER.md")
    assert out.exists()
    text = out.read_text()
    assert "Ada" in text

