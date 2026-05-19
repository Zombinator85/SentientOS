from __future__ import annotations

import json

from scripts.build_work_item_dry_run_closure import main


def test_script(tmp_path):
    packet = tmp_path / "packet.json"
    handoff = tmp_path / "handoff.json"
    dry = tmp_path / "dry.json"
    out = tmp_path / "out.json"
    packet.write_text(json.dumps({"work_item_id": "wi_1", "source_kind": "manual_operator_task", "source_ref": "x", "intake_status": "intake_accepted", "risk_class": "bounded_workspace_change", "declared_authority_requests": [], "agent_execution_is_requested": False, "agent_execution_is_permitted_by_this_packet": False}), encoding="utf-8")
    handoff.write_text(json.dumps({"work_item_id": "wi_1", "recommended_next_governed_surface": "eligible_for_workspace_change_set_admission"}), encoding="utf-8")
    dry.write_text(json.dumps({"work_item_id": "wi_1", "adapter_status": "dry_run_adapter_completed", "lifecycle_orchestration_invoked": True, "lifecycle_mode_used": "dry_run_full_lifecycle"}), encoding="utf-8")
    rc = main(["--packet", str(packet), "--handoff", str(handoff), "--dry-run-result", str(dry), "--output", str(out), "--summary"])
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["manifest"]["closure_status"] == "dry_run_closed_clean"
    assert payload["manifest"]["contradiction_source"] == "none"
