from __future__ import annotations

import json
from pathlib import Path

from scripts.run_work_item_dry_run import main
from sentientos.work_item_intake import normalize_work_item_intake
from sentientos.work_item_lifecycle_handoff import WorkItemLifecycleHandoffRequest, plan_work_item_lifecycle_handoff


def test_script_summary(tmp_path: Path, capsys) -> None:
    payload = {
        "source_kind": "generic_issue",
        "title": "x",
        "description": "d",
        "requested_outcome": "o",
        "declared_targets": ["sentientos/work_item_intake.py"],
        "change_intent": "metadata",
    }
    packet, _ = normalize_work_item_intake(payload, derive_workspace_proposal=True)
    handoff = plan_work_item_lifecycle_handoff(WorkItemLifecycleHandoffRequest(packet=packet.__dict__))
    packet_path = tmp_path / "packet.json"
    handoff_path = tmp_path / "handoff.json"
    packet_path.write_text(json.dumps(packet.__dict__), encoding="utf-8")
    handoff_path.write_text(json.dumps(handoff.__dict__), encoding="utf-8")
    rc = main(["--packet", str(packet_path), "--handoff", str(handoff_path), "--workspace-root", str(tmp_path), "--summary"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "dry_run_adapter_completed" in out
