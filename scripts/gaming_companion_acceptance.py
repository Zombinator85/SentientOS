"""Run the local gaming-companion acceptance suite and read-only deployment doctor.

This command exercises software fixtures and any local components detected by
their tests. It does not provision identities, secrets, firewall rules,
services, user consent, or Windows/WSL authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from sentientos.gaming_companion_deployment import inspect_local

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_TESTS = (
    "tests/test_gaming_companion_acceptance.py",
    "tests/test_gaming_companion_deployment.py",
    "tests/test_host_resource_runtime.py",
    "tests/test_runtime_governor.py",
    "tests/test_control_plane_kernel.py",
    "tests/test_governed_local_model_invocation.py",
    "tests/test_governed_local_model_resource_invocation_composition.py",
    "tests/test_gaming_companion_tls_transport.py",
    "tests/test_gaming_companion_bridge_runtime.py",
    "tests/test_gaming_companion_supervisor.py",
    "tests/test_gaming_companion_process_supervisor.py",
    "tests/test_gaming_companion_pair_supervisor.py",
    "tests/test_gaming_companion_pair_entrypoint.py",
    "tests/test_gaming_companion_authority.py",
    "tests/test_gaming_companion_platform_custody.py",
    "tests/test_gaming_companion_platform_provider.py",
    "tests/test_gaming_companion_platform_installation.py",
    "tests/test_gaming_companion_platform_pair_process.py",
    "tests/test_gaming_companion_process_profile.py",
    "tests/test_gaming_companion_bidirectional_runtime.py",
    "tests/test_gaming_companion_edge_runtime.py",
    "tests/test_gaming_companion_core_runtime.py",
    "tests/test_gaming_companion_role_entrypoint.py",
    "tests/test_gaming_companion_avatar_output.py",
    "tests/test_foreground_game_bridge.py",
    "tests/test_windows_game_performance.py",
    "tests/test_game_performance_bridge.py",
    "tests/test_avatar_renderer_report_ingress.py",
    "tests/test_avatar_demo_cli.py",
    "tests/test_avatar_authoring.py::test_configured_blender_authors_and_reopens_glb_candidate",
    "tests/test_godot_renderer_report_integration.py",
    "tests/test_godot_avatar_demo.py",
    "tests/test_godot_avatar_receiver.py",
    "tests/test_gaming_companion_vertical_godot.py",
    "tests/test_chat_avatar_output.py",
    "tests/test_chat_speech_output.py",
    "tests/test_chat_service_resource_allocation.py",
    "tests/test_chat_service_hardened_serving.py::test_gaming_companion_vertical_fixture_survives_forwarding_and_restart",
    "tests/test_chat_service_hardened_serving.py::test_new_chat_turn_interrupts_previous_local_speech",
    "tests/test_chat_service_hardened_serving.py::test_production_chat_owns_wsl_core_avatar_session_and_uses_its_emitter",
)


def _write_private(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def run_acceptance(*, manifest_path: Path, results_dir: Path,
                   runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run
                   ) -> dict[str, Any]:
    """Run the read-only doctor and reproducible fixture suite, retaining logs."""
    manifest_path = Path(manifest_path)
    results_dir = Path(results_dir)
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("manifest_path_unsafe_or_missing")
    manifest_value = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest_value, dict):
        raise ValueError("manifest_not_object")
    doctor = inspect_local(manifest_value)

    if results_dir.exists() or results_dir.is_symlink():
        raise ValueError("results_directory_must_be_new")
    results_dir.mkdir(parents=True, mode=0o700)
    log_path = results_dir / "fixture-tests.log"
    junit_path = results_dir / "fixture-tests.xml"
    report_path = results_dir / "acceptance.json"
    started = time.monotonic()
    test_data_root = results_dir / "test-state"
    test_environment = os.environ.copy()
    test_environment.update({
        "SENTIENTOS_TEST_RUN_DIR": str(test_data_root / "test-runs"),
        "SENTIENTOS_DATA_DIR": str(test_data_root / "data"),
        "SENTIENTOS_RUNTIME_STATE_ROOT": str(test_data_root / "runtime"),
        "SENTIENTOS_CONTROL_KERNEL_ROOT": str(test_data_root / "control-plane"),
        "SENTIENTOS_GOVERNOR_ROOT": str(test_data_root / "governor"),
    })
    command = [sys.executable, "-m", "scripts.run_tests", "-q",
               *FIXTURE_TESTS, f"--junitxml={junit_path}"]
    try:
        with log_path.open("wb") as log_stream:
            os.chmod(log_path, 0o600)
            completed = runner(command, cwd=ROOT, stdout=log_stream,
                               stderr=subprocess.STDOUT, check=False,
                               env=test_environment)
        exit_code = int(completed.returncode)
        runner_failure = None
    except OSError as exc:
        exit_code = 127
        runner_failure = type(exc).__name__
        _write_private(log_path, ("runner could not start: " + runner_failure + "\n").encode())
    duration = max(0.0, time.monotonic() - started)
    counts = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    junit_status = "unavailable"
    executed_nodes: dict[str, str] = {}
    try:
        root = ET.parse(junit_path).getroot()
        suite = root if root.tag == "testsuite" else root.find("testsuite")
        if suite is not None:
            counts = {name: int(suite.attrib.get(name, "0")) for name in counts}
            junit_status = "parsed"
        for case in root.iter("testcase"):
            node = str(case.attrib.get("name", ""))
            skipped_case = case.find("skipped")
            executed_nodes[node] = ("skipped: " + str(skipped_case.attrib.get("message", ""))
                                    if skipped_case is not None else "passed")
    except (OSError, ET.ParseError, ValueError):
        pass
    log_bytes = log_path.read_bytes()
    try:
        git_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
            check=True, capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        git_head = None
    tests_passed = (exit_code == 0 and junit_status == "parsed" and counts["tests"] > 0
                    and counts["failures"] == 0 and counts["errors"] == 0)
    blender_test_status = executed_nodes.get(
        "test_configured_blender_authors_and_reopens_glb_candidate", "not_run")
    blender_path = shutil.which("blender")
    godot_path = shutil.which("godot") or shutil.which("godot4")
    report: dict[str, Any] = {
        "schema_version": "sentientos.gaming_companion_acceptance:v1",
        "status": "local_fixture_validation_passed" if tests_passed else "local_fixture_validation_blocked",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "repository_head": git_head,
        "manifest_path": str(manifest_path.resolve()),
        "read_only_deployment_doctor": doctor,
        "fixture_tests": {"status": "passed" if tests_passed else "blocked",
            "command": command, "exit_code": exit_code, "junit_status": junit_status,
            **counts, "duration_seconds": round(duration, 3),
            "isolated_test_state_directory": str(test_data_root),
            "log_path": str(log_path),
            "log_sha256": hashlib.sha256(log_bytes).hexdigest(),
            "failure_class": runner_failure},
        "real_software_scenarios": {
            "screen_observation_chat_to_godot": {
                "status": executed_nodes.get(
                    "test_fixture_screen_observation_reaches_real_godot_without_persisting_screen_data",
                    "not_run"),
                "test_node": "test_fixture_screen_observation_reaches_real_godot_without_persisting_screen_data",
                "godot_renderer_executable": godot_path,
                "raw_frame_retained": False,
                "target_host_or_live_screen_capture_claimed": False,
            },
            "blender_authored_glb_candidate": {
                "status": blender_test_status,
                "blender_executable": blender_path,
                "godot_renderer_executable": godot_path,
                "godot_renderer_subcheck": ("executed" if blender_test_status == "passed"
                    and godot_path is not None else "not_available_or_not_run"),
                "scope": "generated fixture adoption through the Python receipt-verifying loader, Godot activation, lineage report, and rollback; fixture approval is not production authority",
                "adopted_body_round_trip": ("executed" if blender_test_status == "passed"
                    and godot_path is not None else "not_available_or_not_run"),
                "production_adoption_claimed": False,
            },
            "windows_game_performance": {
                "status": "controlled_windows_fixtures_only",
                "test_node": "test_windows_performance_sample_crosses_mtls_and_retains_measured_lineage",
                "glorp_capture_claimed": False,
            },
            "reverse_avatar_edge_composition": {
                "status": "custody_bound_factory_fixture_only",
                "test_node": "test_edge_runtime_factory_resolves_only_v3_reverse_custody_and_builds_stopped_owner",
                "target_listener_started": False,
            },
            "reverse_avatar_core_output_composition": {
                "status": "custody_bound_bidirectional_factory_fixture_only",
                "test_node": "test_core_companion_factory_composes_verified_game_input_and_reverse_output",
                "target_listener_started": False,
                "target_listener_contacted": False,
                "production_chat_binding_fixture": "test_production_chat_owns_wsl_core_avatar_session_and_uses_its_emitter",
            },
            "paired_role_entrypoint": {
                "status": "lifecycle_and_host_rejection_fixtures_only" if tests_passed else "blocked",
                "test_node": "tests/test_gaming_companion_role_entrypoint.py",
                "windows_or_wsl_process_launched": False,
                "platform_provider_installed": False,
            },
            "platform_custody_resolution": {
                "status": ("fixture_custody_policy_passed"
                    if tests_passed and all(executed_nodes.get(node) == "passed" for node in (
                        "test_wsl_custody_resolves_generation_keys_and_mtls_contexts",
                        "test_windows_custody_uses_dpapi_reader_for_opaque_key_reference"))
                    else "blocked"),
                "test_nodes": [
                    "test_wsl_custody_resolves_generation_keys_and_mtls_contexts",
                    "test_windows_custody_uses_dpapi_reader_for_opaque_key_reference",
                ],
                "windows_or_wsl_target_execution": False,
                "installation_catalog_or_authority_provisioned": False,
            },
            "platform_role_provider_composition": {
                "status": ("fixture_role_provider_composition_passed"
                    if tests_passed and all(executed_nodes.get(node) == "passed" for node in (
                        "test_platform_provider_composes_windows_edge_with_custody_and_explicit_renderer_hooks",
                        "test_platform_provider_composes_wsl_core_and_requires_governed_admission_hook"))
                    else "blocked"),
                "test_nodes": [
                    "test_platform_provider_composes_windows_edge_with_custody_and_explicit_renderer_hooks",
                    "test_platform_provider_composes_wsl_core_and_requires_governed_admission_hook",
                ],
                "windows_or_wsl_target_execution": False,
                "operator_authority_or_service_installation_performed": False,
            },
            "platform_installation_catalog": {
                "status": ("signed_catalog_fixture_passed"
                    if tests_passed and all(executed_nodes.get(node) == "passed" for node in (
                        "test_signed_platform_catalog_builds_custody_and_authority_adapters",
                        "test_verified_installation_composes_role_provider_without_rebinding_authority",
                        "test_platform_catalog_signature_binds_reference_paths_before_asset_access",
                        "test_platform_catalog_rejects_untrusted_receipt_and_path_escape",
                        "test_platform_catalog_rejects_duplicate_json_fields_and_open_permissions"))
                    else "blocked"),
                "test_nodes": [
                    "test_signed_platform_catalog_builds_custody_and_authority_adapters",
                    "test_verified_installation_composes_role_provider_without_rebinding_authority",
                    "test_platform_catalog_signature_binds_reference_paths_before_asset_access",
                    "test_platform_catalog_rejects_untrusted_receipt_and_path_escape",
                    "test_platform_catalog_rejects_duplicate_json_fields_and_open_permissions",
                ],
                "target_host_catalog_installed": False,
                "issuer_trust_anchor_provisioned": False,
                "production_commissioning_claimed": False,
            },
            "platform_pair_process_provider": {
                "status": ("fixture_pair_process_composition_passed"
                    if tests_passed and all(executed_nodes.get(node) == "passed" for node in (
                        "test_installed_profiles_compose_authorized_core_first_pair_and_shutdown_order",
                        "test_pair_provider_rejects_missing_roles_and_wrong_host_before_spawning",
                        "test_pair_provider_rejects_role_profile_mismatch_before_any_spawn",
                        "test_pair_provider_rejects_invalid_manifest_before_supervisor_construction",
                        "test_edge_launch_denial_rolls_back_the_already_started_core",
                        "test_process_profile_factory_uses_loaded_specs_without_starting_children",
                        "test_process_launch_receipt_is_scoped_to_installation_identity"))
                    else "blocked"),
                "test_nodes": [
                    "test_installed_profiles_compose_authorized_core_first_pair_and_shutdown_order",
                    "test_pair_provider_rejects_missing_roles_and_wrong_host_before_spawning",
                    "test_pair_provider_rejects_role_profile_mismatch_before_any_spawn",
                    "test_pair_provider_rejects_invalid_manifest_before_supervisor_construction",
                    "test_edge_launch_denial_rolls_back_the_already_started_core",
                    "test_process_profile_factory_uses_loaded_specs_without_starting_children",
                    "test_process_launch_receipt_is_scoped_to_installation_identity",
                ],
                "target_processes_spawned": False,
                "installation_profiles_or_authority_provisioned": False,
                "production_commissioning_claimed": False,
            },
            "platform_process_profiles": {
                "status": ("bounded_profile_fixture_passed"
                    if tests_passed and all(executed_nodes.get(node) == "passed" for node in (
                        "test_profile_loader_builds_closed_windows_and_wsl_role_specs",
                        "test_profile_loader_rejects_extra_command_arguments_and_secret_environment",
                        "test_profile_loader_rejects_duplicate_fields_and_untrusted_hosts",
                        "test_profile_loader_rejects_path_escape_and_wrong_role_binding"))
                    else "blocked"),
                "test_nodes": [
                    "test_profile_loader_builds_closed_windows_and_wsl_role_specs",
                    "test_profile_loader_rejects_extra_command_arguments_and_secret_environment",
                    "test_profile_loader_rejects_duplicate_fields_and_untrusted_hosts",
                    "test_profile_loader_rejects_path_escape_and_wrong_role_binding",
                ],
                "authority_granted": False,
                "processes_spawned": False,
                "target_profile_provisioned": False,
            },
            "paired_role_coordinator": {
                "status": executed_nodes.get(
                    "test_pair_starts_core_then_edge_and_shuts_down_edge_then_core",
                    "not_run"),
                "startup_rollback_test": executed_nodes.get(
                    "test_edge_start_denial_rolls_back_already_started_core", "not_run"),
                "peer_failure_shutdown_test": executed_nodes.get(
                    "test_role_exhausting_recovery_stops_its_peer", "not_run"),
                "windows_or_wsl_process_launched": False,
                "platform_provider_installed": False,
            },
            "bidirectional_authenticated_transport": {
                "status": executed_nodes.get(
                    "test_windows_edge_and_wsl_core_exchange_observations_and_governed_avatar_output",
                    "not_run"),
                "test_node": "test_windows_edge_and_wsl_core_exchange_observations_and_governed_avatar_output",
                "scope": "loopback mTLS fixture identities; forward performance observation and reverse receipt-gated avatar output",
                "target_windows_or_wsl_transport_claimed": False,
                "firewall_validation_claimed": False,
            },
        },
        "target_host_validation": {"status": "not_run",
            "required_environment": "GLORP Windows 11 + WSL2",
            "runbook_path": "docs/development/glorp_gaming_companion_handoff.md",
            "required_checks": ["Windows DPAPI and process counters",
                "PresentMon capture and frame-time ingress",
                "both-direction Windows/WSL mTLS and firewall",
                "platform-provider launch authority and separate OS-process startup, shutdown, and recovery",
                "Godot renderer report return", "local speech device timing and interruption",
                "production-adopted Blender body pointer/manifest/receipt handoff to the renderer"]},
        "authority_effects_performed": False,
        "production_commissioning_claimed": False,
    }
    encoded = (json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n").encode()
    _write_private(report_path, encoded)
    report["report_path"] = str(report_path)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--results-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = run_acceptance(manifest_path=args.manifest, results_dir=args.results_dir)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        report = {"schema_version": "sentientos.gaming_companion_acceptance:v1",
                  "status": "blocked", "reason": str(exc),
                  "authority_effects_performed": False,
                  "production_commissioning_claimed": False}
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report.get("status") == "local_fixture_validation_passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
