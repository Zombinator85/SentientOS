import json

from scripts import admit_workspace_change_set as script


def test_cli_builds_admission_decision_from_proposal_json_only(tmp_path):
    proposal = tmp_path / "proposal.json"
    proposal.write_text(json.dumps({
        "declared_target_count": 1,
        "proposed_targets": [{"target_id": "a", "relative_target_path": "docs/a.txt", "operation": "create_file", "declared_payload_byte_count": 5, "declared_payload_digest": "sha256:a"}],
    }), encoding="utf-8")
    output = tmp_path / "admission.json"
    assert script.main(["--proposal", str(proposal), "--output", str(output)]) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["decision"]["admission_status"] == "admission_accepted"
    assert payload["decision"]["preflight_may_be_attempted_next"] is True
    assert payload["decision"]["preflight_performed"] is False
    assert sorted(p.name for p in tmp_path.iterdir()) == ["admission.json", "proposal.json"]


def test_cli_returns_blocked_for_forbidden_authority(tmp_path):
    proposal = tmp_path / "proposal.json"
    proposal.write_text(json.dumps({
        "declared_target_count": 1,
        "requested_authority_labels": ["network"],
        "proposed_targets": [{"target_id": "a", "relative_target_path": "docs/a.txt", "operation": "create_file", "declared_payload_byte_count": 5, "declared_payload_digest": "sha256:a"}],
    }), encoding="utf-8")
    assert script.main(["--proposal", str(proposal), "--summary"]) == 2
