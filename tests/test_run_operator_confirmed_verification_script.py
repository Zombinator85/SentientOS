from __future__ import annotations

import json
from pathlib import Path

from scripts.run_operator_confirmed_verification import main


def test_script_blocks_without_confirmation(tmp_path: Path) -> None:
    e = tmp_path / "execution.json"
    p = tmp_path / "proposal.json"
    e.write_text(json.dumps({"status": "execution_run_completed", "packet": {"work_item_id": "w1", "execution_wing_invoked": True}}), encoding="utf-8")
    p.write_text(json.dumps({"work_item_id": "w1", "proposal_id": "p1", "proposed_targets": []}), encoding="utf-8")
    code = main(["--execution-run", str(e), "--proposal", str(p), "--workspace-root", str(tmp_path), "--summary"])
    assert code == 2


def test_script_writes_output(tmp_path: Path) -> None:
    e = tmp_path / "execution.json"
    p = tmp_path / "proposal.json"
    out = tmp_path / "verification.json"
    e.write_text(json.dumps({"status": "execution_run_completed", "packet": {"work_item_id": "w1", "execution_wing_invoked": True, "artifact_references": ["a"]}}), encoding="utf-8")
    p.write_text(json.dumps({"work_item_id": "w1", "proposal_id": "p1", "proposed_targets": []}), encoding="utf-8")
    code = main(["--execution-run", str(e), "--proposal", str(p), "--workspace-root", str(tmp_path), "--confirm-verification", "--output", str(out)])
    assert code in {0, 2}
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert "packet" in payload and payload["packet"]["verification_run_packet_id"].startswith("wivrun_")
