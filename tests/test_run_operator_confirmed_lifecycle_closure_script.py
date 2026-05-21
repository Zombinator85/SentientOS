from __future__ import annotations

import json
from pathlib import Path

from scripts.run_operator_confirmed_lifecycle_closure import main


def test_script_blocks_without_confirmation(tmp_path: Path) -> None:
    c = tmp_path / "closure.json"
    p = tmp_path / "proposal.json"
    c.write_text(json.dumps({"status": "closure_review_ready", "packet": {"work_item_id": "w1"}}), encoding="utf-8")
    p.write_text(json.dumps({"work_item_id": "w1"}), encoding="utf-8")
    code = main(["--closure-review", str(c), "--proposal", str(p), "--summary"])
    assert code == 2


def test_script_writes_output(tmp_path: Path) -> None:
    c = tmp_path / "closure.json"
    p = tmp_path / "proposal.json"
    out = tmp_path / "run.json"
    c.write_text(json.dumps({"status": "closure_review_ready", "packet": {"work_item_id": "w1", "artifact_references": ["a"]}}), encoding="utf-8")
    p.write_text(json.dumps({"work_item_id": "w1"}), encoding="utf-8")
    code = main(["--closure-review", str(c), "--proposal", str(p), "--confirm-closure", "--output", str(out)])
    assert code in {0, 2}
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["packet"]["lifecycle_closure_run_packet_id"].startswith("wiclrun_")
