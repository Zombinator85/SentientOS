from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def test_cli_end_to_end(tmp_path: Path) -> None:
    policy = tmp_path / "policy.json"
    fixture = Path("tests/fixtures/household_presence_camera_events/wildlife_squirrel_fat_boi.json")
    out = tmp_path / "out.json"
    subprocess.run([sys.executable, "scripts/build_household_presence_camera_redaction_pipeline.py", "build-default", "--output", str(policy)], check=True)
    assert subprocess.run([sys.executable, "scripts/build_household_presence_camera_redaction_pipeline.py", "validate", "--input", str(policy)], check=False).returncode == 0
    assert subprocess.run([sys.executable, "scripts/build_household_presence_camera_redaction_pipeline.py", "evaluate", "--input", str(fixture), "--output", str(out)], check=False).returncode == 0
    summary = subprocess.run([sys.executable, "scripts/build_household_presence_camera_redaction_pipeline.py", "summarize", "--input", str(fixture)], check=True, capture_output=True, text=True)
    assert "wildlife_ledger_candidate" in summary.stdout


def test_no_media_payloads_in_fixtures() -> None:
    fixtures = Path("tests/fixtures/household_presence_camera_events")
    for path in fixtures.glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        text = json.dumps(payload)
        assert "base64" not in text
        assert "image" not in payload
        assert "audio" not in payload
        assert "video" not in payload
