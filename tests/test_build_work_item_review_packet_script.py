from __future__ import annotations

import json

from scripts.build_work_item_review_packet import main


def test_script_summary_and_outputs(tmp_path):
    payload = tmp_path / "work_item.json"
    payload.write_text(json.dumps({"source_kind": "generic_issue", "title": "t", "description": "d", "requested_outcome": "o", "declared_targets": ["sentientos/work_item_intake.py"]}), encoding="utf-8")
    intake = tmp_path / "intake.json"
    handoff = tmp_path / "handoff.json"
    dry = tmp_path / "dry.json"
    closure = tmp_path / "closure.json"
    review = tmp_path / "review.json"

    rc = main(["--input", str(payload), "--workspace-root", str(tmp_path), "--mode", "review_with_dry_run_closure", "--summary", "--intake-output", str(intake), "--handoff-output", str(handoff), "--dry-run-output", str(dry), "--closure-output", str(closure), "--review-output", str(review)])
    assert rc in {0, 2}
    assert intake.exists() and handoff.exists() and dry.exists() and closure.exists() and review.exists()
    review_payload = json.loads(review.read_text(encoding="utf-8"))
    assert review_payload["packet"]["digest"]
    assert review_payload["packet"]["operator_action"]
