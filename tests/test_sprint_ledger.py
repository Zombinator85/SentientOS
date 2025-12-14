"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations


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
    # integrity issue file
    (log_dir / "memory.jsonl.wounds").write_text("one\ntwo\n")
    # AUDIT_LOG_FIXES.md with a repaired line
    (docs / "AUDIT_LOG_FIXES.md").write_text("- 2025-11 Living Audit Sprint: 5 malformed lines repaired.\n")
    # CONTRIBUTORS.md with contributors
    (docs / "CONTRIBUTORS.md").write_text("## Audit Contributors\n- Ada\n")

    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(log_dir))
    metrics = hsl.gather_metrics()
    assert metrics["logs_healed"] == 5
    assert metrics["contributors"] == 1
    assert metrics["integrity_issues"] == 2
    assert metrics["nodes"] == 2

    # writing dashboard
    (log_dir / "contributor_stories.jsonl").write_text(
        json.dumps({"contributor": "Ada", "story": "Fixed"}) + "\n"
    )
    hsl.write_dashboard(metrics, hsl.read_stories())
    out = (docs / "docs" / "SPRINT_LEDGER.md")
    assert out.exists()
    text = out.read_text()
    assert "Ada" in text

