from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from scripts.gaming_companion_acceptance import run_acceptance

pytestmark = pytest.mark.no_legacy_skip


def _manifest() -> dict[str, object]:
    return {
        "schema_version": "sentientos.gaming_companion_deployment:v1",
        "deployment_id": "acceptance-fixture",
        "repository_root": "/srv/sentientos",
        "python_executable": "/srv/sentientos/.venv/bin/python",
        "state_root": "/var/lib/sentientos",
        "installation_identity_ref": None,
        "serving_operation_ref": None,
        "runtime_handoff_ref": None,
        "software_generation_digest": None,
        "enabled_windows_components": [],
        "bridge_key_reference": None,
        "bridge_bind_scope": "loopback_only",
        "firewall_rule_reference": None,
        "start_on_login": False,
        "automatic_capture": False,
        "automatic_speech": False,
    }


def test_acceptance_records_fixture_results_and_keeps_target_checks_deferred(tmp_path: Path) -> None:
    manifest = tmp_path / "deployment.json"
    manifest.write_text(json.dumps(_manifest()), encoding="utf-8")
    results = tmp_path / "results"

    def successful_runner(command, *, cwd, stdout, stderr, check, env):
        assert command[1:4] == ["-m", "scripts.run_tests", "-q"]
        assert "tests/test_gaming_companion_vertical_godot.py" in command
        assert "tests/test_gaming_companion_bridge_runtime.py" in command
        assert "tests/test_gaming_companion_pair_supervisor.py" in command
        assert "tests/test_gaming_companion_pair_entrypoint.py" in command
        assert "tests/test_gaming_companion_authority.py" in command
        assert "tests/test_gaming_companion_platform_custody.py" in command
        assert "tests/test_gaming_companion_platform_provider.py" in command
        assert "tests/test_gaming_companion_platform_installation.py" in command
        assert "tests/test_gaming_companion_bidirectional_runtime.py" in command
        assert check is False
        assert env["SENTIENTOS_TEST_RUN_DIR"].startswith(str(results / "test-state"))
        assert env["SENTIENTOS_CONTROL_KERNEL_ROOT"].startswith(str(results / "test-state"))
        stdout.write(b"fixture acceptance output\n")
        junit = next(Path(item.split("=", 1)[1]) for item in command
                     if item.startswith("--junitxml="))
        junit.write_text(
            '<testsuite tests="15" failures="0" errors="0" skipped="2">'
            '<testcase name="test_wsl_custody_resolves_generation_keys_and_mtls_contexts"/>'
            '<testcase name="test_windows_custody_uses_dpapi_reader_for_opaque_key_reference"/>'
            '<testcase name="test_platform_provider_composes_windows_edge_with_custody_and_explicit_renderer_hooks"/>'
            '<testcase name="test_platform_provider_composes_wsl_core_and_requires_governed_admission_hook"/>'
            '<testcase name="test_signed_platform_catalog_builds_custody_and_authority_adapters"/>'
            '<testcase name="test_platform_catalog_signature_binds_reference_paths_before_asset_access"/>'
            '<testcase name="test_platform_catalog_rejects_untrusted_receipt_and_path_escape"/>'
            '<testcase name="test_platform_catalog_rejects_duplicate_json_fields_and_open_permissions"/>'
            '</testsuite>', encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)

    report = run_acceptance(manifest_path=manifest, results_dir=results,
                            runner=successful_runner)
    assert report["status"] == "local_fixture_validation_passed"
    assert report["real_software_scenarios"]["screen_observation_chat_to_godot"]["status"] == "not_run"
    assert report["real_software_scenarios"]["screen_observation_chat_to_godot"]["raw_frame_retained"] is False
    assert report["real_software_scenarios"]["paired_role_coordinator"]["status"] == "not_run"
    assert report["real_software_scenarios"]["paired_role_coordinator"]["windows_or_wsl_process_launched"] is False
    transport_scenario = report["real_software_scenarios"]["bidirectional_authenticated_transport"]
    assert transport_scenario["status"] == "not_run"
    assert transport_scenario["target_windows_or_wsl_transport_claimed"] is False
    assert transport_scenario["firewall_validation_claimed"] is False
    assert report["read_only_deployment_doctor"]["host_mutation_performed"] is False
    assert report["fixture_tests"]["tests"] == 15
    assert report["fixture_tests"]["skipped"] == 2
    assert report["real_software_scenarios"]["blender_authored_glb_candidate"]["status"] == "not_run"
    assert report["real_software_scenarios"]["reverse_avatar_edge_composition"]["target_listener_started"] is False
    core_scenario = report["real_software_scenarios"]["reverse_avatar_core_output_composition"]
    assert core_scenario["target_listener_started"] is False
    assert core_scenario["target_listener_contacted"] is False
    assert core_scenario["production_chat_binding_fixture"] == "test_production_chat_owns_wsl_core_avatar_session_and_uses_its_emitter"
    role_scenario = report["real_software_scenarios"]["paired_role_entrypoint"]
    assert role_scenario["status"] == "lifecycle_and_host_rejection_fixtures_only"
    assert role_scenario["windows_or_wsl_process_launched"] is False
    assert role_scenario["platform_provider_installed"] is False
    custody_scenario = report["real_software_scenarios"]["platform_custody_resolution"]
    assert custody_scenario["status"] == "fixture_custody_policy_passed"
    assert custody_scenario["windows_or_wsl_target_execution"] is False
    assert custody_scenario["installation_catalog_or_authority_provisioned"] is False
    provider_scenario = report["real_software_scenarios"]["platform_role_provider_composition"]
    assert provider_scenario["status"] == "fixture_role_provider_composition_passed"
    assert provider_scenario["windows_or_wsl_target_execution"] is False
    assert provider_scenario["operator_authority_or_service_installation_performed"] is False
    catalog_scenario = report["real_software_scenarios"]["platform_installation_catalog"]
    assert catalog_scenario["status"] == "signed_catalog_fixture_passed"
    assert catalog_scenario["target_host_catalog_installed"] is False
    assert catalog_scenario["issuer_trust_anchor_provisioned"] is False
    assert catalog_scenario["production_commissioning_claimed"] is False
    assert len(report["fixture_tests"]["log_sha256"]) == 64
    assert report["target_host_validation"]["status"] == "not_run"
    assert report["authority_effects_performed"] is False
    assert report["production_commissioning_claimed"] is False
    assert os.stat(results).st_mode & 0o777 == 0o700
    assert os.stat(results / "acceptance.json").st_mode & 0o777 == 0o600


def test_acceptance_rejects_manifest_symlinks_before_running_tests(tmp_path: Path) -> None:
    target = tmp_path / "real.json"
    target.write_text(json.dumps(_manifest()), encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(target)
    invoked = False

    def runner(*args, **kwargs):
        nonlocal invoked
        invoked = True
        return subprocess.CompletedProcess([], 0)

    with pytest.raises(ValueError, match="manifest_path_unsafe_or_missing"):
        run_acceptance(manifest_path=link, results_dir=tmp_path / "results", runner=runner)
    assert invoked is False
