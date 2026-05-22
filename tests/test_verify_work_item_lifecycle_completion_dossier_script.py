from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_work_item_lifecycle_completion_dossier import main


def test_script_summary_and_output(tmp_path: Path, capsys) -> None:
    dossier = tmp_path / "dossier.json"
    dossier.write_text(json.dumps({"status": "lifecycle_completion_dossier_complete", "completion_dossier_id": "cd1", "completion_dossier_digest": "dg1", "work_item_id": "w1", "stage_summaries": []}), encoding="utf-8")
    out = tmp_path / "report.json"
    code = main(["--completion-dossier", str(dossier), "--output", str(out), "--summary"])
    assert code == 0
    text = capsys.readouterr().out
    assert "status=lifecycle_completion_verification_passed" in text
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "lifecycle_completion_verification_passed"


def test_script_nonzero_for_insufficient(tmp_path: Path) -> None:
    dossier = tmp_path / "dossier.json"
    dossier.write_text(json.dumps({"status": "unknown", "completion_dossier_id": "cd1", "completion_dossier_digest": "dg1", "work_item_id": "w1", "stage_summaries": []}), encoding="utf-8")
    assert main(["--completion-dossier", str(dossier), "--require-full-chain"]) == 1
