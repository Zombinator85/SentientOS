from __future__ import annotations

import json

import pytest

from scripts.gaming_companion_deployment_cli import main
from sentientos.gaming_companion_deployment import (
    GamingCompanionDeploymentError,
    inspect_local,
    validate_manifest,
)

pytestmark = pytest.mark.no_legacy_skip


def _manifest(**updates):
    value = {
        "schema_version": "sentientos.gaming_companion_deployment:v1",
        "deployment_id": "glorp-prehardware",
        "repository_root": "/home/operator/SentientOS",
        "python_executable": "/home/operator/SentientOS/.venv/bin/python",
        "state_root": "/home/operator/.local/share/sentientos",
        "installation_identity_ref": None,
        "serving_operation_ref": None,
        "runtime_handoff_ref": None,
        "software_generation_digest": None,
        "enabled_windows_components": ["foreground_observer", "godot_renderer"],
        "bridge_key_reference": None,
        "bridge_bind_scope": "loopback_only",
        "firewall_rule_reference": None,
        "start_on_login": False,
        "automatic_capture": False,
        "automatic_speech": False,
    }
    value.update(updates)
    return value


def test_manifest_is_closed_and_manual_activation_only():
    validated = validate_manifest(_manifest())
    assert validated["deployment_id"] == "glorp-prehardware"

    with pytest.raises(GamingCompanionDeploymentError, match="manifest_fields_invalid"):
        validate_manifest({**_manifest(), "unexpected": "ignored-fields-are-not-safe"})
    with pytest.raises(GamingCompanionDeploymentError, match="explicit_manual_activation"):
        validate_manifest(_manifest(automatic_capture=True))


@pytest.mark.parametrize("scope,firewall,reason", [
    ("public", None, "manifest_bridge_scope_invalid"),
    ("private_host_firewall", None, "manifest_firewall_reference_required"),
])
def test_manifest_rejects_public_or_unscoped_networking(scope, firewall, reason):
    with pytest.raises(GamingCompanionDeploymentError, match=reason):
        validate_manifest(_manifest(bridge_bind_scope=scope, firewall_rule_reference=firewall))


def test_manifest_rejects_duplicate_or_unknown_windows_components():
    with pytest.raises(GamingCompanionDeploymentError, match="manifest_windows_components_invalid"):
        validate_manifest(_manifest(enabled_windows_components=["godot_renderer", "godot_renderer"]))
    with pytest.raises(GamingCompanionDeploymentError, match="manifest_windows_components_invalid"):
        validate_manifest(_manifest(enabled_windows_components=["screen_capture_all_desktops"]))


def test_local_doctor_is_read_only_and_does_not_claim_external_readiness(tmp_path):
    manifest = _manifest(repository_root=str(tmp_path), state_root=str(tmp_path / "state"))

    result = inspect_local(manifest)

    assert result["status"] == "blocked"
    assert result["facts"]["bridge_listener"] == "not_implemented"
    assert result["facts"]["foreground_observer"] == "not_observed_from_this_environment"
    assert result["facts"]["godot_renderer"] == "not_observed_from_this_environment"
    assert result["host_mutation_performed"] is False
    assert not (tmp_path / "state").exists()


def test_state_root_on_windows_mount_is_not_accepted_as_posix_custody():
    result = inspect_local(_manifest(state_root="/mnt/c/sentientos-state"))
    assert "state_root_native_linux_path_not_ready" in result["reason_codes"]


def test_cli_validate_and_doctor_never_create_or_modify_manifest(tmp_path, capsys):
    manifest_path = tmp_path / "deployment.json"
    original = json.dumps(_manifest(), sort_keys=True)
    manifest_path.write_text(original, encoding="utf-8")

    assert main(["validate", "--manifest", str(manifest_path)]) == 0
    validated = json.loads(capsys.readouterr().out)
    assert validated["status"] == "manifest_validated"
    assert validated["host_mutation_performed"] is False

    assert main(["doctor", "--manifest", str(manifest_path)]) == 2
    diagnosis = json.loads(capsys.readouterr().out)
    assert diagnosis["status"] == "blocked"
    assert diagnosis["authority_effects_performed"] is False
    assert manifest_path.read_text(encoding="utf-8") == original
