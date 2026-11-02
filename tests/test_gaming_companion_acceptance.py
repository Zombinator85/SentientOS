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
        assert check is False
        assert env["SENTIENTOS_TEST_RUN_DIR"].startswith(str(results / "test-state"))
        assert env["SENTIENTOS_CONTROL_KERNEL_ROOT"].startswith(str(results / "test-state"))
        stdout.write(b"fixture acceptance output\n")
        junit = next(Path(item.split("=", 1)[1]) for item in command
                     if item.startswith("--junitxml="))
        junit.write_text('<testsuite tests="11" failures="0" errors="0" skipped="2"/>',
                         encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)

    report = run_acceptance(manifest_path=manifest, results_dir=results,
                            runner=successful_runner)
    assert report["status"] == "local_fixture_validation_passed"
    assert report["read_only_deployment_doctor"]["host_mutation_performed"] is False
    assert report["fixture_tests"]["tests"] == 11
    assert report["fixture_tests"]["skipped"] == 2
    assert report["real_software_scenarios"]["blender_authored_glb_candidate"]["status"] == "not_run"
    assert report["real_software_scenarios"]["reverse_avatar_edge_composition"]["target_listener_started"] is False
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
