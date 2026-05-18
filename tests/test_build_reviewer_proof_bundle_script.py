from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

import pytest

from scripts import build_reviewer_proof_bundle as script
from sentientos.reviewer_proof_bundle import BUNDLE_FILE_NAMES, validate_reviewer_proof_bundle_manifest

pytestmark = pytest.mark.no_legacy_skip


def _run_main(args: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            code = script.main(args)
        except SystemExit as exc:
            code = int(exc.code or 0)
    return code, stdout.getvalue(), stderr.getvalue()


def test_requires_output_dir() -> None:
    code, _stdout, stderr = _run_main([])
    assert code != 0
    assert "output-dir" in stderr


def test_refuses_empty_root_and_file_output_dir(tmp_path: Path) -> None:
    code, _stdout, stderr = _run_main(["--output-dir", "/"])
    assert code != 0
    assert "filesystem root" in stderr
    file_path = tmp_path / "file.txt"
    file_path.write_text("not a directory", encoding="utf-8")
    code, _stdout, stderr = _run_main(["--output-dir", str(file_path)])
    assert code != 0
    assert "directory" in stderr


def test_writes_expected_files_and_manifest_validates(tmp_path: Path) -> None:
    out = tmp_path / "bundle"
    code, stdout, stderr = _run_main(["--output-dir", str(out)])
    assert code == 0, stderr
    assert "proof commands executed: 0" in stdout
    for relative in BUNDLE_FILE_NAMES.values():
        assert (out / relative).exists(), relative
    manifest = json.loads((out / "bundle_manifest.json").read_text(encoding="utf-8"))
    validation = validate_reviewer_proof_bundle_manifest(manifest)
    assert validation.ok, validation.findings
    assert all(record["executed"] is False for record in manifest["proof_command_records"])
    assert all(record["status"] == "proof_command_not_run" for record in manifest["proof_command_records"])


def test_summary_prints_compact_summary(tmp_path: Path) -> None:
    code, stdout, stderr = _run_main(["--output-dir", str(tmp_path / "bundle"), "--summary"])
    assert code == 0, stderr
    assert "SentientOS Reviewer First-Run Proof Bundle" in stdout
    assert "metadata only: true" in stdout
    assert "fake/sample telemetry by default: true" in stdout


def test_existing_files_require_force_and_force_overwrites_only_bundle_files(tmp_path: Path) -> None:
    out = tmp_path / "bundle"
    code, _stdout, stderr = _run_main(["--output-dir", str(out)])
    assert code == 0, stderr
    sentinel = out / "sentinel.txt"
    sentinel.write_text("keep", encoding="utf-8")
    code, _stdout, stderr = _run_main(["--output-dir", str(out)])
    assert code != 0
    assert "--force" in stderr
    (out / "trace.summary.txt").write_text("changed", encoding="utf-8")
    code, _stdout, stderr = _run_main(["--output-dir", str(out), "--force"])
    assert code == 0, stderr
    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert "changed" not in (out / "trace.summary.txt").read_text(encoding="utf-8")


def test_default_does_not_run_live_collection_network_provider_or_prompt(tmp_path: Path) -> None:
    out = tmp_path / "bundle"
    code, _stdout, stderr = _run_main(["--output-dir", str(out)])
    assert code == 0, stderr
    manifest = json.loads((out / "bundle_manifest.json").read_text(encoding="utf-8"))
    assert manifest["live_host_collection_performed"] is False
    assert manifest["live_authorization_granted"] is False
    assert manifest["effect_performed"] is False
    assert manifest["host_mutation_performed"] is False
    assert manifest["network_performed"] is False
    assert manifest["provider_invocation_performed"] is False
    assert manifest["prompt_assembly_performed"] is False


def test_manifest_only_writes_only_manifest(tmp_path: Path) -> None:
    out = tmp_path / "bundle"
    code, _stdout, stderr = _run_main(["--output-dir", str(out), "--manifest-only"])
    assert code == 0, stderr
    assert (out / "bundle_manifest.json").exists()
    assert not (out / "trace.json").exists()


def test_verify_is_explicitly_unsupported(tmp_path: Path) -> None:
    code, _stdout, stderr = _run_main(["--output-dir", str(tmp_path / "bundle"), "--verify"])
    assert code == 2
    assert "not implemented" in stderr


def test_reviewer_proof_bundle_cli_writes_safety_gates_json(tmp_path) -> None:
    output_dir = tmp_path / "bundle"
    code, _stdout, stderr = _run_main(["--output-dir", str(output_dir), "--force"])
    assert code == 0, stderr
    safety_gates = output_dir / "safety_gates.json"
    assert safety_gates.exists()
    text = safety_gates.read_text(encoding="utf-8")
    assert "safety_gate_only" in text
    assert "not authorization" in text


def test_reviewer_proof_bundle_cli_writes_live_grant_readiness_json(tmp_path) -> None:
    output_dir = tmp_path / "bundle"
    code, stdout, stderr = _run_main(["--output-dir", str(output_dir)])
    assert code == 0, (stdout, stderr)
    live_grant = output_dir / "live_grant_readiness.json"
    assert live_grant.exists()
    text = live_grant.read_text(encoding="utf-8")
    assert "Live-grant readiness is not a live grant" in text
    assert "grant_not_issued" in text


def test_reviewer_proof_bundle_cli_writes_local_authorization_json(tmp_path) -> None:
    output_dir = tmp_path / "bundle"
    code, stdout, stderr = _run_main(["--output-dir", str(output_dir)])
    assert code == 0, (stdout, stderr)
    local_authorization = output_dir / "local_authorization.json"
    assert local_authorization.exists()
    payload = json.loads(local_authorization.read_text(encoding="utf-8"))
    assert payload["authorization_record_only"] is True
    assert payload["grant_summary"]["live_authorization_granted"] is True
    assert payload["grant_summary"]["fulfillment_granted"] is False
    assert payload["grant_summary"]["effect_performed"] is False
    assert payload["grant_summary"]["host_mutation_performed"] is False
    assert payload["verification_summary"]["authorizes_fulfillment"] is False


def test_reviewer_proof_bundle_cli_writes_fulfillment_authorization_json(tmp_path) -> None:
    output_dir = tmp_path / "bundle"
    code, stdout, stderr = _run_main(["--output-dir", str(output_dir)])
    assert code == 0, (stdout, stderr)
    path = output_dir / "fulfillment_authorization.json"
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["consumption_pre_fulfillment_only"] is True
    assert payload["authorization_consumed_for_future_fulfillment"] is True
    assert payload["fulfillment_granted"] is False
    assert payload["effect_performed"] is False
    assert payload["host_mutation_performed"] is False
    assert payload["consumption_receipt_summary"]["fan_pwm_write_performed"] is False
    assert payload["consumption_receipt_summary"]["thermal_actuation_performed"] is False


def test_reviewer_proof_bundle_cli_writes_executor_contract_json(tmp_path) -> None:
    output_dir = tmp_path / "bundle"
    code, stdout, stderr = _run_main(["--output-dir", str(output_dir)])
    assert code == 0, (stdout, stderr)
    path = output_dir / "executor_contract.json"
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["executor_contract_readiness_only"] is True
    assert payload["contract_summary"]["executor_implemented"] is False
    assert payload["backend_declaration_summary"]["backend_loaded"] is False
    assert payload["backend_declaration_summary"]["backend_invoked"] is False
    assert payload["dry_run_plan_summary"]["dry_run_executed"] is False
    assert payload["admission_packet_summary"]["control_plane_admission_granted"] is False
    assert payload["readiness_receipt_summary"]["fulfillment_granted"] is False
    assert payload["readiness_receipt_summary"]["effect_performed"] is False
    assert payload["readiness_receipt_summary"]["host_mutation_performed"] is False


def test_reviewer_proof_bundle_cli_writes_dry_run_execution_json(tmp_path) -> None:
    output_dir = tmp_path / "bundle"
    code, stdout, stderr = _run_main(["--output-dir", str(output_dir)])
    assert code == 0, (stdout, stderr)
    path = output_dir / "dry_run_execution.json"
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["dry_run_execution_harness_only"] is True
    assert payload["simulation_only"] is True
    assert payload["dry_run_executed"] is True
    assert payload["real_backend_invoked"] is False
    assert payload["real_fulfillment_performed"] is False
    assert payload["real_effect_performed"] is False
    assert payload["host_mutation_performed"] is False
    assert payload["fan_pwm_write_performed"] is False
    assert payload["thermal_actuation_performed"] is False


def test_reviewer_proof_bundle_cli_writes_dry_run_audit_closure_json(tmp_path) -> None:
    output_dir = tmp_path / "bundle"
    code, stdout, stderr = _run_main(["--output-dir", str(output_dir)])
    assert code == 0, (stdout, stderr)
    path = output_dir / "dry_run_audit_closure.json"
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["dry_run_audit_closure_only"] is True
    assert payload["effect_verification_summary"]["real_effect_receipt_created"] is False
    assert payload["postcondition_verification_summary"]["real_postcondition_check_performed"] is False
    assert payload["rollback_rehearsal_summary"]["real_rollback_performed"] is False
    assert payload["audit_closure_receipt_summary"]["production_audit_receipt_created"] is False
    assert payload["real_fulfillment_performed"] is False
    assert payload["host_mutation_performed"] is False
    assert payload["fan_pwm_write_performed"] is False
    assert payload["thermal_actuation_performed"] is False


def test_reviewer_proof_bundle_cli_writes_real_effect_admission_json(tmp_path) -> None:
    output_dir = tmp_path / "bundle"
    code, stdout, stderr = _run_main(["--output-dir", str(output_dir)])
    assert code == 0, (stdout, stderr)
    path = output_dir / "real_effect_admission.json"
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["real_effect_admission_only"] is True
    assert payload["decision_summary"]["authorizes_implementation"] is False
    assert payload["decision_summary"]["authorizes_execution"] is False
    assert payload["implementation_not_started"] is True
    assert payload["backend_loaded"] is False
    assert payload["backend_invoked"] is False
    assert payload["host_mutation_performed"] is False


def test_reviewer_proof_bundle_cli_writes_local_diagnostic_capability_without_running_effect(tmp_path: Path) -> None:
    output_dir = tmp_path / "bundle"
    code, stdout, stderr = _run_main(["--output-dir", str(output_dir)])
    assert code == 0, (stdout, stderr)
    payload = json.loads((output_dir / "local_diagnostic_effect_capability.json").read_text(encoding="utf-8"))
    assert payload["explicit_command_required"] is True
    assert payload["run_by_reviewer_proof_bundle_default"] is False
    assert payload["proof_bundle_effect_performed"] is False
    commands = json.loads((output_dir / "proof_commands.json").read_text(encoding="utf-8"))["commands"]
    assert any("run_local_diagnostic_effect.py" in " ".join(record["command"]) and record["status"] == "proof_command_not_run" for record in commands)


def test_script_writes_host_steward_boundary_artifact(tmp_path: Path) -> None:
    out = tmp_path / "bundle"
    code, stdout, stderr = _run_main(["--output-dir", str(out), "--force"])
    assert code == 0, stderr
    assert "artifacts:" in stdout
    assert (out / "host_steward_boundary.json").exists()
    posture = json.loads((out / "host_steward_boundary.json").read_text(encoding="utf-8"))
    assert posture["delegated_runners_do_not_inherit_ambient_authority"] is True
    assert posture["no_runner_executes_by_default"] is True


def test_reviewer_proof_bundle_cli_writes_builtin_runner_capability_without_running_runner(tmp_path: Path) -> None:
    output_dir = tmp_path / "bundle"
    code, stdout, stderr = _run_main(["--output-dir", str(output_dir), "--force"])
    assert code == 0, (stdout, stderr)
    path = output_dir / "builtin_local_effect_runner_capability.json"
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["built_in_runner_exists"] is True
    assert payload["run_by_reviewer_proof_bundle_default"] is False
    assert payload["proof_bundle_runner_invoked"] is False
    assert payload["no_subprocess_shell_network_provider_prompt"] is True
    commands = json.loads((output_dir / "proof_commands.json").read_text(encoding="utf-8"))["commands"]
    assert any("run_builtin_local_effect_runner.py" in " ".join(record["command"]) and record["status"] == "proof_command_not_run" for record in commands)


def test_build_reviewer_proof_bundle_writes_transaction_orchestrator_capability(tmp_path):
    from scripts.build_reviewer_proof_bundle import main
    import json

    output_dir = tmp_path / "bundle"
    assert script.main(["--output-dir", str(output_dir), "--force"]) == 0
    path = output_dir / "builtin_runner_transaction_orchestrator_capability.json"
    assert path.exists()
    artifact = json.loads(path.read_text(encoding="utf-8"))
    assert artifact["run_by_reviewer_proof_bundle_default"] is False
    commands = json.loads((output_dir / "proof_commands.json").read_text(encoding="utf-8"))["commands"]
    assert any("run_builtin_runner_transaction.py" in " ".join(record["command"]) and record["status"] == "proof_command_not_run" for record in commands)


def test_build_reviewer_proof_bundle_writes_workspace_file_effect_capability(tmp_path: Path) -> None:
    output_dir = tmp_path / "bundle"
    code, stdout, stderr = _run_main(["--output-dir", str(output_dir), "--force"])
    assert code == 0, (stdout, stderr)
    path = output_dir / "workspace_file_effect_capability.json"
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["run_by_reviewer_proof_bundle_default"] is False
    assert payload["proof_bundle_effect_performed"] is False
    assert payload["supports_exactly_one_workspace_scoped_file_target"] is True
    commands = json.loads((output_dir / "proof_commands.json").read_text(encoding="utf-8"))["commands"]
    assert any("run_workspace_file_effect.py" in " ".join(record["command"]) and record["status"] == "proof_command_not_run" for record in commands)


def test_build_reviewer_proof_bundle_writes_workspace_transaction_orchestrator_capability(tmp_path: Path) -> None:
    output_dir = tmp_path / "bundle"
    assert script.main(["--output-dir", str(output_dir), "--force"]) == 0
    path = output_dir / "workspace_file_transaction_orchestrator_capability.json"
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["workspace_transaction_orchestrator_support"] == "implemented"
    assert payload["run_by_reviewer_proof_bundle_default"] is False
    manifest = json.loads((output_dir / "bundle_manifest.json").read_text(encoding="utf-8"))
    commands = manifest["proof_command_records"]
    assert any("workspace_file_update_rollback_with_ledger" in " ".join(record["command"]) and record["status"] == "proof_command_not_run" for record in commands)


def test_reviewer_proof_bundle_cli_writes_workspace_change_set_preflight_capability(tmp_path) -> None:
    output_dir = tmp_path / "bundle"
    code, stdout, stderr = _run_main(["--output-dir", str(output_dir), "--force"])
    assert code == 0, (stdout, stderr)
    path = output_dir / "workspace_change_set_preflight_capability.json"
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["preflight_planning_only"] is True
    assert payload["run_by_reviewer_proof_bundle_default"] is False
    assert payload["target_writes_occur"] is False
    assert payload["rollback_occurs"] is False
