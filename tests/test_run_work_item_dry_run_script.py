from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.run_work_item_dry_run import main
from sentientos.work_item_intake import normalize_work_item_intake
from sentientos.work_item_lifecycle_handoff import WorkItemLifecycleHandoffRequest, plan_work_item_lifecycle_handoff



def _write_packet_handoff(tmp_path: Path, *, packet_overrides: dict[str, object] | None = None, handoff_overrides: dict[str, object] | None = None) -> tuple[Path, Path]:
    payload = {
        "source_kind": "generic_issue",
        "title": "x",
        "description": "d",
        "requested_outcome": "o",
        "declared_targets": ["sentientos/work_item_intake.py"],
        "change_intent": "metadata",
    }
    packet, _ = normalize_work_item_intake(payload, derive_workspace_proposal=True)
    packet_data = packet.__dict__.copy()
    if packet_overrides:
        packet_data.update(packet_overrides)
    handoff = plan_work_item_lifecycle_handoff(WorkItemLifecycleHandoffRequest(packet=packet_data))
    handoff_data = handoff.__dict__.copy()
    if handoff_overrides:
        handoff_data.update(handoff_overrides)
    packet_path = tmp_path / "packet.json"
    handoff_path = tmp_path / "handoff.json"
    packet_path.write_text(json.dumps(packet_data), encoding="utf-8")
    handoff_path.write_text(json.dumps(handoff_data), encoding="utf-8")
    return packet_path, handoff_path


def test_script_summary_completed(tmp_path: Path, capsys) -> None:
    packet_path, handoff_path = _write_packet_handoff(tmp_path)
    rc = main(["--packet", str(packet_path), "--handoff", str(handoff_path), "--workspace-root", str(tmp_path), "--summary"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "dry_run_adapter_completed" in out


@pytest.mark.parametrize(
    "packet_overrides,handoff_overrides,expected_status",
    [
        ({"declared_authority_requests": ["network"]}, {}, "dry_run_adapter_blocked"),
        ({"intake_status": "intake_insufficient_metadata"}, {}, "dry_run_adapter_blocked"),
        ({}, {"recommended_next_governed_surface": "needs_manual_review"}, "dry_run_adapter_manual_review_required"),
        ({"workspace_change_set_proposal_metadata": None}, {}, "dry_run_adapter_insufficient_metadata"),
    ],
)
def test_script_summary_negative_paths(tmp_path: Path, capsys, packet_overrides: dict[str, object], handoff_overrides: dict[str, object], expected_status: str) -> None:
    packet_path, handoff_path = _write_packet_handoff(tmp_path, packet_overrides=packet_overrides, handoff_overrides=handoff_overrides)
    rc = main(["--packet", str(packet_path), "--handoff", str(handoff_path), "--workspace-root", str(tmp_path), "--summary"])
    out = capsys.readouterr().out
    assert rc == 2
    assert expected_status in out
