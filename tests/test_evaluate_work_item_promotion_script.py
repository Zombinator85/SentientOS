from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate_work_item_promotion import main


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_summary_and_output(tmp_path: Path, capsys) -> None:
    packet = tmp_path / "review.json"
    out = tmp_path / "out.json"
    _write(packet, {"review_packet_id": "wir_1", "digest": "abc", "source_work_item_id": "w1", "operator_action": "ready_for_workspace_admission_review", "dry_run_closure_status": "dry_run_closed_clean", "lifecycle_dry_run_invoked": True, "lifecycle_mode_used": "dry_run_full_lifecycle", "artifact_records": [{"digest": "1"}], "contradiction_source": "none"})
    assert main(["--review-packet", str(packet), "--summary", "--output", str(out)]) == 0
    text = capsys.readouterr().out
    assert "promotion_ready_for_admission_review" in text
    assert out.exists()


def test_nonzero_on_blocked(tmp_path: Path) -> None:
    packet = tmp_path / "review.json"
    _write(packet, {"review_packet_id": "wir_1", "digest": "abc", "source_work_item_id": "w1", "operator_action": "ready_for_workspace_admission_review", "dry_run_closure_status": "dry_run_closed_clean", "lifecycle_dry_run_invoked": True, "lifecycle_mode_used": "dry_run_full_lifecycle", "artifact_records": [{"digest": "1"}], "contradiction_source": "none", "provider_requested": True})
    assert main(["--review-packet", str(packet)]) == 2
