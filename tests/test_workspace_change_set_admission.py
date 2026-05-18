import builtins
import json
from pathlib import Path

from sentientos.workspace_change_set_admission import (
    WorkspaceChangeSetAdmissionPolicy,
    build_workspace_change_set_admission_artifact,
    run_workspace_change_set_admission_wing,
)


def proposal(**overrides):
    base = {
        "request_id": "admission-demo",
        "declared_target_count": 2,
        "proposed_targets": [
            {"target_id": "a", "relative_target_path": "docs/a.txt", "operation": "create_file", "declared_payload_byte_count": 5, "declared_payload_digest": "sha256:aaa"},
            {"target_id": "b", "relative_target_path": "docs/b.txt", "operation": "update_file", "declared_payload_byte_count": 7, "declared_payload_digest": "sha256:bbb"},
        ],
    }
    base.update(overrides)
    return base


def status(payload, **kwargs):
    return run_workspace_change_set_admission_wing(payload, **kwargs).decision


def test_valid_create_update_change_set_is_admitted():
    decision = status(proposal())
    assert decision.admission_status == "admission_accepted"
    assert decision.preflight_may_be_attempted_next is True
    assert decision.proposed_operation_types == ("create_file", "update_file")
    assert decision.proposed_payload_byte_counts == (5, 7)
    assert decision.declared_payload_digests == ("sha256:aaa", "sha256:bbb")


def test_admitted_with_warnings_for_missing_conservative_metadata():
    payload = proposal(declared_target_count=1, proposed_targets=[{"target_id": "a", "relative_target_path": "docs/a.txt", "operation": "create_file"}])
    decision = status(payload)
    assert decision.admission_status == "admission_accepted_with_warnings"
    assert decision.preflight_may_be_attempted_next is True
    assert "declared_payload_byte_count_missing" in decision.warning_codes
    assert "declared_payload_digest_missing" in decision.warning_codes


def test_duplicate_target_path_blocks():
    payload = proposal(proposed_targets=[
        {"target_id": "a", "relative_target_path": "docs/a.txt", "operation": "create_file", "declared_payload_byte_count": 1, "declared_payload_digest": "sha256:a"},
        {"target_id": "b", "relative_target_path": "docs/./a.txt", "operation": "update_file", "declared_payload_byte_count": 1, "declared_payload_digest": "sha256:b"},
    ])
    decision = status(payload)
    assert decision.admission_status == "admission_blocked"
    assert "duplicate_target_path" in decision.blocker_codes


def test_absolute_traversal_wildcard_root_empty_and_directory_paths_block():
    cases = [
        ("/tmp/a", "absolute_target_path"),
        ("../a", "path_traversal"),
        ("docs/*.txt", "wildcard_target_path"),
        ("", "empty_target_path"),
        (".", "root_target_path"),
        ("docs/", "directory_like_target_path"),
    ]
    for path, code in cases:
        payload = proposal(declared_target_count=1, proposed_targets=[{"target_id": "a", "relative_target_path": path, "operation": "create_file", "declared_payload_byte_count": 1, "declared_payload_digest": "sha256:a"}])
        decision = status(payload)
        assert decision.admission_status in {"admission_blocked", "admission_insufficient_metadata"}
        assert code in decision.blocker_codes


def test_forbidden_cleanup_delete_authority_blocks():
    decision = status(proposal(requested_authority_labels=["cleanup", "recursive_delete", "wildcard_delete", "unrelated_file_delete"]))
    assert decision.admission_status == "admission_blocked"
    assert "cleanup" in decision.forbidden_authority_findings
    assert "recursive_delete" in decision.forbidden_authority_findings


def test_forbidden_subprocess_shell_network_provider_prompt_authority_blocks():
    decision = status(proposal(requested_authority_labels=["subprocess", "shell", "network", "provider", "prompt_assembly", "prompt_export"]))
    assert decision.admission_status == "admission_blocked"
    for label in ["subprocess", "shell", "network", "provider", "prompt_assembly", "prompt_export"]:
        assert label in decision.forbidden_authority_findings


def test_forbidden_hardware_service_power_fan_thermal_package_driver_authority_blocks():
    decision = status(proposal(requested_authority_labels=["hardware", "service", "power", "fan", "thermal", "package", "driver", "plugin", "generated_code", "federation_execution"]))
    assert decision.admission_status == "admission_blocked"
    for label in ["hardware", "service", "power", "fan", "thermal", "package", "driver", "plugin", "generated_code", "federation_execution"]:
        assert label in decision.forbidden_authority_findings


def test_oversized_target_count_blocks():
    targets = [
        {"target_id": str(i), "relative_target_path": f"docs/{i}.txt", "operation": "create_file", "declared_payload_byte_count": 1, "declared_payload_digest": f"sha256:{i}"}
        for i in range(3)
    ]
    decision = status({"declared_target_count": 3, "proposed_targets": targets}, policy=WorkspaceChangeSetAdmissionPolicy(max_targets=2))
    assert decision.admission_status == "admission_blocked"
    assert "target_count_over_limit" in decision.blocker_codes


def test_missing_required_metadata_yields_insufficient_metadata():
    decision = status({"proposed_targets": [{"relative_target_path": "docs/a.txt"}]})
    assert decision.admission_status == "admission_insufficient_metadata"
    assert "missing_declared_target_count" in decision.blocker_codes
    assert "missing_operation" in decision.blocker_codes


def test_contradictory_supplied_flags_yield_contradicted():
    decision = status(proposal(proposal_flags={"metadata_only": False, "execution_performed": True}))
    assert decision.admission_status == "admission_contradicted"
    assert "contradiction:metadata_only_false" in decision.blocker_codes
    assert "contradiction:execution_performed" in decision.blocker_codes


def test_admission_artifact_is_metadata_only_and_omits_payload_bodies():
    payload = proposal(declared_target_count=1, proposed_targets=[{"target_id": "a", "relative_target_path": "docs/a.txt", "operation": "create_file", "declared_payload_byte_count": 11, "declared_payload_digest": "sha256:a", "payload_text": "SECRET BODY"}])
    wing = run_workspace_change_set_admission_wing(payload)
    artifact = build_workspace_change_set_admission_artifact(wing)
    rendered = json.dumps(artifact, sort_keys=True)
    assert artifact["metadata_only"] is True
    assert "SECRET BODY" not in rendered
    assert "payload_text" not in rendered
    assert wing.decision.admission_status == "admission_blocked"
    assert "payload_body_supplied_to_metadata_only_admission" in wing.decision.blocker_codes


def test_optional_artifact_write_is_the_only_write(tmp_path):
    output = tmp_path / "admission.json"
    wing = run_workspace_change_set_admission_wing(proposal(), artifact_output_path=output)
    assert wing.artifact_written is True
    assert output.exists()
    assert json.loads(output.read_text())["decision"]["admission_status"] == "admission_accepted"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["admission.json"]


def test_admission_does_not_read_target_files(monkeypatch):
    target_file = "docs/a.txt"
    original_open = builtins.open

    def guarded_open(file, *args, **kwargs):
        if str(file).endswith(target_file):
            raise AssertionError("target file was read")
        return original_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)
    decision = status(proposal(declared_target_count=1, proposed_targets=[{"target_id": "a", "relative_target_path": target_file, "operation": "create_file", "declared_payload_byte_count": 1, "declared_payload_digest": "sha256:a"}]))
    assert decision.admission_status == "admission_accepted"
    assert decision.workspace_files_read is False
    assert decision.filesystem_existence_checked is False
    assert decision.filesystem_digests_computed is False


def test_admission_does_not_call_preflight_execution_verification_or_closure_helpers(monkeypatch):
    import sentientos.workspace_change_set_preflight as preflight

    def forbidden(*args, **kwargs):
        raise AssertionError("preflight helper was called")

    monkeypatch.setattr(preflight, "run_workspace_change_set_preflight_wing", forbidden)
    monkeypatch.setattr(preflight, "preflight_workspace_change_target", forbidden)
    decision = status(proposal())
    assert decision.admission_status == "admission_accepted"
    assert decision.preflight_performed is False
    assert decision.execution_performed is False
    assert decision.verification_replay_performed is False
    assert decision.lifecycle_closure_built is False
