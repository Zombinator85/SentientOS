from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos import maintenance_activation_profiles as profiles
from sentientos import maintenance_initial_resident_genesis_provisioning as genesis
from tests.test_maintenance_activation_profiles import _manifest, _rewrite
from tests.test_maintenance_initial_resident_genesis_provisioning import manifest


def test_commissioned_profile_has_no_codex_policy_or_codex_fields(tmp_path: Path) -> None:
    path, value = _manifest(tmp_path)
    activation = tmp_path / "commissioned-activation.json"
    activation.write_text('{"schema_version":"sentientos.local_model_activation:v1"}')
    value.update(schema_version=profiles.BACKEND_MANIFEST_SCHEMA,
                 implementation_backend="commissioned_local",
                 commissioned_local_activation=str(activation.resolve()),
                 commissioned_local_activation_digest="sha256:" + hashlib.sha256(activation.read_bytes()).hexdigest())
    del value["codex_executable"]; del value["codex_home"]
    _rewrite(path, value)
    result = profiles.render_profile_bundle(path)
    bundle = Path(result["output_directory"])
    assert (bundle / profiles.FILENAMES["workspace_custody_policy"]).is_file()
    assert not (bundle / profiles.FILENAMES["foreman_policy"]).exists()
    assert {entry["role"] for entry in __import__("json").loads((bundle / "bundle_index.json").read_text())["artifacts"]} == {
        "standing_grant", "selector_policy", "workspace_custody_policy", "validation_policy", "landing_policy"}


def test_commissioned_genesis_doctor_needs_activation_but_not_codex(tmp_path: Path) -> None:
    value = manifest(tmp_path)
    value["schema_version"] = genesis.BACKEND_MANIFEST_SCHEMA
    value["implementation_backend"] = "commissioned_local"
    del value["codex_executable"]; del value["codex_home"]
    value["manifest_digest"] = genesis.digest(value, "manifest_digest")
    assert genesis.doctor(value)["reason_codes"] == ["commissioned_local_activation_required"]
    activation = tmp_path / "activation.json"; activation.write_text("{}")
    value["commissioned_local_activation"] = str(activation.resolve())
    value["commissioned_local_activation_digest"] = "sha256:" + hashlib.sha256(activation.read_bytes()).hexdigest()
    value["manifest_digest"] = genesis.digest(value, "manifest_digest")
    assert genesis.doctor(value)["status"] == "genesis_provisioning_ready"
    assert "codex_executable" not in value and "codex_home" not in value


def test_backend_specific_fields_are_closed(tmp_path: Path) -> None:
    path, value = _manifest(tmp_path)
    value["schema_version"] = profiles.BACKEND_MANIFEST_SCHEMA
    value["implementation_backend"] = "local_codex"
    value["commissioned_local_activation"] = "/forbidden"
    value["manifest_digest"] = profiles.digest(value, "manifest_digest")
    path.write_bytes(profiles.canonical_bytes(value))
    with pytest.raises(ValueError, match="closed_schema"):
        profiles.validate_manifest(value)
