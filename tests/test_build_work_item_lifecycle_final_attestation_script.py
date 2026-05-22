import json
from pathlib import Path

from scripts.build_work_item_lifecycle_final_attestation import main


def test_script_summary_and_output(tmp_path: Path, capsys: object) -> None:
    d = tmp_path / "d.json"; r = tmp_path / "r.json"; o = tmp_path / "o.json"
    d.write_text(json.dumps({"completion_dossier_id": "d1", "completion_dossier_digest": "dd", "work_item_id": "w1", "status": "lifecycle_completion_dossier_complete", "completed_stage_order": ["intake"], "stage_count": 1}), encoding="utf-8")
    r.write_text(json.dumps({"verification_report_id": "v1", "verification_report_digest": "vv", "work_item_id": "w1", "verification_status": "lifecycle_completion_verification_passed"}), encoding="utf-8")
    code = main(["--completion-dossier", str(d), "--verification-report", str(r), "--output", str(o), "--summary"])
    assert code == 0
    assert o.exists()
    assert "lifecycle_final_attestation" in o.read_text(encoding="utf-8")
