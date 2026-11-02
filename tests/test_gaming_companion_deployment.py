from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.gaming_companion_deployment_cli import main
from sentientos.gaming_companion_deployment import (
    GamingCompanionDeploymentError,
    SCHEMA_MUTUAL_TLS,
    SCHEMA_MUTUAL_TLS_REVERSE,
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


def _mutual_tls_manifest(**updates):
    value = _manifest(
        schema_version=SCHEMA_MUTUAL_TLS,
        bridge_key_reference="credential-store:sentientos/windows-edge-source",
        bridge_bind_scope="mutual_tls_private",
        firewall_rule_reference="operator-firewall-rule:sentientos-wsl-core",
        bridge_tls={
            "schema_version": "sentientos.companion_bridge_mtls:v1",
            "core_bind_address": "172.20.0.1",
            "port": 54321,
            "server_hostname": "sentientos-wsl-core",
            "ca_bundle_reference": "wsl:/etc/sentientos/bridge/ca.pem",
            "core_certificate_reference": "wsl:/etc/sentientos/bridge/core.pem",
            "core_private_key_reference": "wsl:/etc/sentientos/bridge/core.key",
            "windows_edge_client_certificate_reference": "windows:credential-store/edge-cert",
            "windows_edge_client_private_key_reference": "windows:dpapi/edge-key",
            "expected_windows_edge_certificate_sha256": "a" * 64,
            "source_key_custody_reference": "credential-store:sentientos/windows-edge-source",
            "source_generation_custody_reference": "operator-ledger:windows-edge-generation",
            "acknowledgment_generation_custody_reference": "operator-ledger:wsl-core-generation",
        },
    )
    value.update(updates)
    return value


def _reverse_mutual_tls_manifest(**updates):
    reverse = _mutual_tls_manifest()
    reverse.update({
        "schema_version": SCHEMA_MUTUAL_TLS_REVERSE,
        "reverse_firewall_rule_reference": "operator-firewall-rule:sentientos-windows-edge",
        "reverse_avatar_tls": {
            "schema_version": "sentientos.companion_avatar_reverse_mtls:v1",
            "windows_bind_address": "192.168.1.42",
            "port": 54322,
            "server_hostname": "sentientos-windows-edge",
            "ca_bundle_reference": "windows:credential-store/bridge-ca",
            "windows_edge_certificate_reference": "windows:credential-store/edge-server-cert",
            "windows_edge_private_key_reference": "windows:dpapi/edge-server-key",
            "wsl_core_client_certificate_reference": "wsl:/etc/sentientos/bridge/core-client.pem",
            "wsl_core_client_private_key_reference": "wsl:/etc/sentientos/bridge/core-client.key",
            "expected_wsl_core_certificate_sha256": "b" * 64,
            "source_key_custody_reference": "credential-store:sentientos/wsl-core-avatar-source",
            "source_generation_custody_reference": "operator-ledger:wsl-core-avatar-generation",
            "acknowledgment_generation_custody_reference": "operator-ledger:windows-edge-avatar-generation",
        },
    })
    reverse.update(updates)
    return reverse


def test_manifest_is_closed_and_manual_activation_only():
    validated = validate_manifest(_manifest())
    assert validated["deployment_id"] == "glorp-prehardware"

    with pytest.raises(GamingCompanionDeploymentError, match="manifest_fields_invalid"):
        validate_manifest({**_manifest(), "unexpected": "ignored-fields-are-not-safe"})
    with pytest.raises(GamingCompanionDeploymentError, match="explicit_manual_activation"):
        validate_manifest(_manifest(automatic_capture=True))


@pytest.mark.parametrize("scope,firewall,reason", [
    ("public", None, "manifest_bridge_scope_invalid"),
    ("private_host_firewall", "operator-managed-rule", "manifest_bridge_scope_not_implemented"),
    ("loopback_only", "operator-managed-rule", "manifest_firewall_reference_unsupported"),
])
def test_manifest_rejects_networking_scopes_without_a_supported_transport(scope, firewall, reason):
    with pytest.raises(GamingCompanionDeploymentError, match=reason):
        validate_manifest(_manifest(bridge_bind_scope=scope, firewall_rule_reference=firewall))


def test_manifest_rejects_duplicate_or_unknown_windows_components():
    with pytest.raises(GamingCompanionDeploymentError, match="manifest_windows_components_invalid"):
        validate_manifest(_manifest(enabled_windows_components=["godot_renderer", "godot_renderer"]))
    with pytest.raises(GamingCompanionDeploymentError, match="manifest_windows_components_invalid"):
        validate_manifest(_manifest(enabled_windows_components=["screen_capture_all_desktops"]))


def test_manifest_requires_absolute_posix_paths_without_nul_bytes():
    with pytest.raises(GamingCompanionDeploymentError, match="posix_absolute_path_required"):
        validate_manifest(_manifest(state_root="relative/state"))
    with pytest.raises(GamingCompanionDeploymentError, match="posix_absolute_path_required"):
        validate_manifest(_manifest(repository_root="/tmp/bad\x00path"))


def test_local_doctor_is_read_only_and_does_not_claim_external_readiness(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    manifest = _manifest(repository_root=str(repo), state_root="/sentientos-nonexistent-state-fixture")

    result = inspect_local(manifest)

    assert result["status"] == "blocked"
    assert result["facts"]["bridge_runtime_source_in_checkout"] is True
    assert result["facts"]["bridge_listener"] == "not_observed_from_this_environment"
    assert "authenticated_bridge_listener_unobserved" in result["warning_codes"]
    assert result["facts"]["foreground_observer"] == "not_observed_from_this_environment"
    assert result["facts"]["godot_renderer"] == "not_observed_from_this_environment"
    assert result["facts"]["state_root_separate_from_checkout"] is True
    assert result["host_mutation_performed"] is False
    assert not Path("/sentientos-nonexistent-state-fixture").exists()


def test_state_root_on_windows_mount_is_not_accepted_as_posix_custody():
    result = inspect_local(_manifest(state_root="/mnt/c/sentientos-state"))
    assert "state_root_native_linux_path_not_ready" in result["reason_codes"]


def test_mutual_tls_v2_manifest_requires_private_transport_and_custody_references():
    validated = validate_manifest(_mutual_tls_manifest())
    assert validated["bridge_bind_scope"] == "mutual_tls_private"
    result = inspect_local(_mutual_tls_manifest())
    assert result["facts"]["bridge_transport_kind"] == "mutual_tls_private"
    assert "split_host_tls_listener_not_observed" in result["warning_codes"]
    assert "firewall_rule_not_independently_verified" in result["warning_codes"]
    assert result["host_mutation_performed"] is False


@pytest.mark.parametrize("changes,reason", [
    ({"bridge_tls": {"schema_version": "sentientos.companion_bridge_mtls:v1"}}, "manifest_bridge_tls_fields_invalid"),
    ({"firewall_rule_reference": None}, "manifest_firewall_reference_required"),
])
def test_mutual_tls_manifest_rejects_missing_security_prerequisites(changes, reason):
    with pytest.raises(GamingCompanionDeploymentError, match=reason):
        validate_manifest(_mutual_tls_manifest(**changes))


def test_mutual_tls_manifest_rejects_public_bind_and_key_reference_mismatch():
    manifest = _mutual_tls_manifest()
    manifest["bridge_tls"]["core_bind_address"] = "8.8.8.8"
    with pytest.raises(GamingCompanionDeploymentError, match="private_address_required"):
        validate_manifest(manifest)
    manifest = _mutual_tls_manifest()
    manifest["bridge_tls"]["source_key_custody_reference"] = "different-key"
    with pytest.raises(GamingCompanionDeploymentError, match="source_key_reference_mismatch"):
        validate_manifest(manifest)


def test_reverse_avatar_v3_manifest_requires_independent_windows_mtls_custody():
    manifest = _reverse_mutual_tls_manifest()
    validated = validate_manifest(manifest)
    assert validated["schema_version"] == SCHEMA_MUTUAL_TLS_REVERSE
    result = inspect_local(manifest)
    assert result["facts"]["reverse_avatar_transport_kind"] == "mutual_tls_private"
    assert result["facts"]["reverse_avatar_listener"] == "not_observed_from_this_environment"
    assert "split_host_reverse_avatar_listener_not_observed" in result["warning_codes"]
    assert "reverse_avatar_firewall_rule_not_independently_verified" in result["warning_codes"]
    assert result["authority_effects_performed"] is False
    assert result["host_mutation_performed"] is False


@pytest.mark.parametrize("mutation,reason", [
    (lambda value: value["reverse_avatar_tls"].update(windows_bind_address="8.8.8.8"),
     "manifest_reverse_avatar_tls_private_address_required"),
    (lambda value: value["reverse_avatar_tls"].update(source_key_custody_reference=
        value["bridge_tls"]["source_key_custody_reference"]),
     "manifest_reverse_avatar_tls_source_key_reuse_forbidden"),
    (lambda value: value.update(reverse_firewall_rule_reference=None),
     "manifest_reverse_firewall_reference_required"),
])
def test_reverse_avatar_manifest_rejects_unsafe_transport_or_custody(mutation, reason):
    manifest = _reverse_mutual_tls_manifest()
    mutation(manifest)
    with pytest.raises(GamingCompanionDeploymentError, match=reason):
        validate_manifest(manifest)


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
