from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from sentientos.work_item_intake import normalize_work_item_intake


def _script() -> list[str]:
    return [sys.executable, "scripts/plan_work_item_handoff.py"]


def test_cli_matches_api(tmp_path: Path) -> None:
    payload = {
        "source_kind": "generic_issue",
        "source_ref": "GH-2",
        "title": "Plan",
        "description": "Plan handoff",
        "requested_outcome": "Provide next step",
        "declared_targets": ["sentientos/work_item_intake.py"],
    }
    packet, _ = normalize_work_item_intake(payload, derive_workspace_proposal=True)
    packet_path = tmp_path / "packet.json"
    out = tmp_path / "handoff.json"
    packet_path.write_text(json.dumps(packet.__dict__), encoding="utf-8")
    proc = subprocess.run(_script() + ["--packet", str(packet_path), "--output", str(out), "--summary", "--emit-lifecycle-candidate"], check=False, capture_output=True, text=True)
    assert proc.returncode == 0
    printed = json.loads(proc.stdout)
    written = json.loads(out.read_text(encoding="utf-8"))
    assert printed == written
    assert written["lifecycle_orchestration_request_candidate_metadata"]["orchestration_not_invoked"] is True


def test_cli_nonzero_blocked(tmp_path: Path) -> None:
    payload = {
        "source_kind": "generic_issue",
        "source_ref": "GH-3",
        "title": "Blocked",
        "description": "Needs network",
        "requested_outcome": "Call api",
        "declared_authority_requests": ["network"],
    }
    packet, _ = normalize_work_item_intake(payload)
    path = tmp_path / "packet.json"
    path.write_text(json.dumps(packet.__dict__), encoding="utf-8")
    proc = subprocess.run(_script() + ["--packet", str(path)], check=False, capture_output=True, text=True)
    assert proc.returncode != 0
