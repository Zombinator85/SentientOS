from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _script() -> list[str]:
    return [sys.executable, "scripts/intake_work_item.py"]


def test_cli_summary_matches_api(tmp_path: Path) -> None:
    payload = {
        "source_kind": "generic_issue",
        "source_ref": "GH-12",
        "title": "Normalize",
        "description": "Normalize metadata only",
        "requested_outcome": "A packet",
        "declared_targets": ["sentientos/work_item_intake.py"],
    }
    input_file = tmp_path / "task.json"
    output_file = tmp_path / "packet.json"
    input_file.write_text(json.dumps(payload), encoding="utf-8")

    proc = subprocess.run(_script() + ["--input", str(input_file), "--output", str(output_file), "--summary", "--derive-workspace-proposal"], check=False, capture_output=True, text=True)
    assert proc.returncode == 0
    printed = json.loads(proc.stdout)
    written = json.loads(output_file.read_text(encoding="utf-8"))
    assert printed == written
    assert written["workspace_change_set_proposal_metadata"]["proposal_kind"] == "workspace_change_set_proposal_metadata_only"


def test_cli_nonzero_for_insufficient_metadata(tmp_path: Path) -> None:
    input_file = tmp_path / "task.json"
    input_file.write_text(json.dumps({"source_kind": "generic_issue", "title": "x"}), encoding="utf-8")
    proc = subprocess.run(_script() + ["--input", str(input_file)], check=False, capture_output=True, text=True)
    assert proc.returncode != 0
