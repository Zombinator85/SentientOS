from __future__ import annotations
from dataclasses import replace
import importlib.util
import json
import platform
import sys
import pytest
from sentientos.local_runtime_provisioning import (CATALOG_SCHEMA_VERSION, LocalRuntimeEnvironmentProfile,
    CATALOG_SCHEMA_VERSION_V2, ENVIRONMENT_SCHEMA_VERSION_V2,
    normalize_architecture, observe_local_runtime_environment, plan_local_runtime_provisioning, semantic_digest,
    validate_runtime_catalog)

pytestmark = pytest.mark.no_legacy_skip

SHA = "a" * 64
def env(**changes: object) -> LocalRuntimeEnvironmentProfile:
    return replace(LocalRuntimeEnvironmentProfile("linux", "x86_64", "cpython", 3, 11,
        "cpython-311-x86_64-linux-gnu", "fixture", "b" * 64), **changes)
def selection(backend: str = "cpu") -> dict[str, object]:
    value = {"status": "selected", "selected": {"model_id": "model", "artifact_sha256": "c" * 64,
        "route_id": f"{backend}-route", "runtime_requirement": {"engine": "llama_cpp", "backend_family": backend}}}
    value["plan_digest"] = semantic_digest(value); return value
def entry(backend: str = "cpu", runtime_id: str | None = None, **changes: object) -> dict[str, object]:
    value: dict[str, object] = {"runtime_id": runtime_id or f"synthetic-{backend}", "engine": "llama_cpp",
        "backend_family": backend, "distribution_kind": "python_wheel", "package_name": "synthetic-runtime",
        "package_version": "1.2.3", "artifact_filename": f"synthetic-{backend}.whl", "artifact_sha256": SHA,
        "artifact_urls": [f"https://fixtures.invalid/synthetic-{backend}.whl"], "runtime_priority": 10,
        "os_family": "linux", "architecture": "amd64", "python_implementation": "cpython",
        "python_abi": "cpython-311-x86_64-linux-gnu"}
    value.update(changes); return value
def catalog(*entries: dict[str, object]) -> dict[str, object]:
    return {"schema_version": CATALOG_SCHEMA_VERSION, "runtimes": list(entries)}

def v2_entry(platform_tag: str = "win_amd64", **changes: object) -> dict[str, object]:
    value: dict[str, object] = {"runtime_id": "synthetic-v2", "engine": "llama_cpp",
        "backend_family": "cpu", "backend_variant": "synthetic-cpu", "distribution_kind": "python_wheel",
        "package_name": "synthetic_runtime", "package_version": "1.2.3",
        "artifact_filename": f"synthetic_runtime-1.2.3-py3-none-{platform_tag}.whl",
        "artifact_sha256": SHA, "artifact_urls": ["https://fixtures.invalid/synthetic.whl"],
        "runtime_priority": 10, "python_implementation": "cpython", "python_tag": "py3",
        "abi_tag": "none", "platform_tag": platform_tag,
        "supported_python_versions": ["3.10", "3.11", "3.12"]}
    value.update(changes); return value

def v2_catalog(*entries: dict[str, object]) -> dict[str, object]:
    return {"schema_version": CATALOG_SCHEMA_VERSION_V2, "runtimes": list(entries)}

def v2_env(**changes: object) -> LocalRuntimeEnvironmentProfile:
    return env(schema_version=ENVIRONMENT_SCHEMA_VERSION_V2, **changes)

def test_environment_profile_identity_is_deterministic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Linux"); monkeypatch.setattr(platform, "machine", lambda: "AMD64")
    first, second = observe_local_runtime_environment(), observe_local_runtime_environment()
    assert first == second and first.digest == second.digest and first.metadata_only and first.no_authority
    assert first.python_major == sys.version_info.major
@pytest.mark.parametrize(("alias", "canonical"), [("amd64", "x86_64"), ("x86_64", "x86_64"), ("aarch64", "arm64"), ("arm64", "arm64")])
def test_architecture_aliases(alias: str, canonical: str) -> None: assert normalize_architecture(alias) == canonical
@pytest.mark.parametrize("backend", ["cpu", "cuda", "rocm", "metal"])
def test_route_selects_only_exact_backend(backend: str) -> None:
    plan = plan_local_runtime_provisioning(selection(backend), env(), catalog(entry(backend)))
    assert plan["status"] == "selected" and plan["backend_family"] == backend
    assert plan["runtime_availability_status"] == plan["runtime_installed"] == "not_evaluated"
@pytest.mark.parametrize("changes", [{"python_abi": "cp312"}, {"os_family": "windows"}])
def test_exact_environment_match_fails_closed(changes: dict[str, object]) -> None:
    assert plan_local_runtime_provisioning(selection(), env(**changes), catalog(entry()))["status"] == "blocked_no_compatible_runtime"
def test_cuda_never_falls_back_to_cpu() -> None:
    assert plan_local_runtime_provisioning(selection("cuda"), env(), catalog(entry("cpu")))["status"] == "blocked_no_compatible_runtime"
@pytest.mark.parametrize("bad", [{}, {"status": "blocked_no_eligible_model", "selected": None}, {"status": "selected", "selected": {"model_id": "v1"}}])
def test_malformed_v1_and_blocked_selections_fail_closed(bad: dict[str, object]) -> None:
    assert plan_local_runtime_provisioning(bad, env(), catalog(entry()))["status"] == "blocked_invalid_selection"
def test_unsupported_engine_blocks() -> None:
    chosen = selection(); selected = chosen["selected"]; assert isinstance(selected, dict)
    requirement = selected["runtime_requirement"]; assert isinstance(requirement, dict); requirement["engine"] = "other"
    assert plan_local_runtime_provisioning(chosen, env(), catalog(entry()))["status"] == "blocked_invalid_selection"
@pytest.mark.parametrize(("changes", "reason"), [({"artifact_sha256": "bad"}, "invalid_artifact_sha256"),
    ({"package_version": "latest"}, "non_exact_package_version"), ({"package_version": ">=1"}, "non_exact_package_version"),
    ({"artifact_urls": ["https://example.invalid/simple/pkg"]}, "untrusted_artifact_url")])
def test_catalog_rejects_non_custodial_artifacts(changes: dict[str, object], reason: str) -> None:
    with pytest.raises(ValueError, match=reason): validate_runtime_catalog(catalog(entry(**changes)))
def test_empty_and_duplicate_catalogs_block() -> None:
    assert plan_local_runtime_provisioning(selection(), env(), catalog())["status"] == "blocked_invalid_catalog"
    with pytest.raises(ValueError, match="duplicate_runtime_id"): validate_runtime_catalog(catalog(entry(), entry()))
def test_catalog_order_normalizes_and_priority_then_id_ranks() -> None:
    a, b = entry(runtime_id="a", runtime_priority=2), entry(runtime_id="b", runtime_priority=1)
    assert validate_runtime_catalog(catalog(a, b))["catalog_digest"] == validate_runtime_catalog(catalog(b, a))["catalog_digest"]
    assert plan_local_runtime_provisioning(selection(), env(), catalog(a, b))["runtime_id"] == "b"
def test_prerequisites_preserved_but_not_evaluated_and_plan_stable() -> None:
    runtime = entry("cuda", external_prerequisite_codes=["nvidia_driver_compatible"])
    first = plan_local_runtime_provisioning(selection("cuda"), env(), catalog(runtime))
    second = plan_local_runtime_provisioning(json.loads(json.dumps(selection("cuda"), sort_keys=True)), env(), catalog(runtime))
    assert first == second and first["prerequisite_status"] == "not_evaluated"
    assert first["external_prerequisite_codes"] == ("nvidia_driver_compatible",)
def test_missing_environment_facts_block() -> None:
    profile = replace(env(), python_abi="", missing_fact_codes=("python_abi_unknown",))
    assert plan_local_runtime_provisioning(selection(), profile, catalog(entry()))["status"] == "blocked_missing_environment_facts"
def test_successful_plan_is_zero_effect_metadata() -> None:
    plan = plan_local_runtime_provisioning(selection(), env(), catalog(entry()))
    assert plan["status"] == "selected" and plan["package_version"] == "1.2.3" and plan["artifact_sha256"] == SHA
    for key in ("runtime_provisioning_executed", "network_performed", "download_performed", "package_install_performed",
                "subprocess_performed", "model_load_performed", "commissioning_performed", "authority_granted"):
        assert plan[key] is False
def test_end_to_end_selected_route_to_pinned_runtime_witness() -> None:
    plan = plan_local_runtime_provisioning(selection("rocm"), env(), catalog(entry("cpu"), entry("rocm")))
    assert (plan["selected_model_id"], plan["selected_route_id"], plan["runtime_id"]) == ("model", "rocm-route", "synthetic-rocm")
def test_static_zero_effect_verifier() -> None:
    spec = importlib.util.spec_from_file_location("verifier", "scripts/verify_local_runtime_provisioning.py")
    assert spec and spec.loader; module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    assert module.main() == 0

def test_v1_exact_soabi_contract_is_preserved() -> None:
    assert plan_local_runtime_provisioning(selection(), env(), catalog(entry()))["status"] == "selected"
    plan = plan_local_runtime_provisioning(selection(), env(python_abi="cp311"), catalog(entry()))
    assert plan["reason_codes"] == ("python_abi_mismatch",)

def test_v2_py3_none_windows_uses_allowlist_not_soabi() -> None:
    profile = v2_env(os_family="windows", python_abi="deliberately-unrelated-soabi")
    plan = plan_local_runtime_provisioning(selection(), profile, v2_catalog(v2_entry()))
    assert plan["status"] == "selected" and plan["abi_tag"] == "none"
    assert plan["backend_variant"] == "synthetic-cpu"

def test_v2_python_allowlist_and_exact_python_tag_fail_closed() -> None:
    profile = v2_env(os_family="windows", python_minor=12)
    denied = v2_entry(supported_python_versions=["3.11"])
    assert "python_version_not_supported" in plan_local_runtime_provisioning(selection(), profile, v2_catalog(denied))["reason_codes"]
    cp311 = v2_entry(python_tag="cp311", artifact_filename="synthetic_runtime-1.2.3-cp311-none-win_amd64.whl")
    assert "python_tag_mismatch" in plan_local_runtime_provisioning(selection(), profile, v2_catalog(cp311))["reason_codes"]

def test_v2_explicit_cpython_abi_is_exact() -> None:
    runtime = v2_entry(python_tag="cp311", abi_tag="cp311",
        artifact_filename="synthetic_runtime-1.2.3-cp311-cp311-win_amd64.whl")
    assert plan_local_runtime_provisioning(selection(), v2_env(os_family="windows", python_abi="cp311"), v2_catalog(runtime))["status"] == "selected"
    plan = plan_local_runtime_provisioning(selection(), v2_env(os_family="windows"), v2_catalog(runtime))
    assert "python_abi_mismatch" in plan["reason_codes"]

def test_v2_windows_platform_mismatch_is_precise() -> None:
    plan = plan_local_runtime_provisioning(selection(), v2_env(), v2_catalog(v2_entry()))
    assert plan["reason_codes"] == ("wheel_os_mismatch",)

@pytest.mark.parametrize(("libc_version", "status", "reason"), [
    ("2.35", "selected", None), ("2.40", "selected", None),
    ("2.34", "blocked_no_compatible_runtime", "glibc_too_old")])
def test_manylinux_glibc_floor(libc_version: str, status: str, reason: str | None) -> None:
    runtime = v2_entry("manylinux_2_35_x86_64")
    plan = plan_local_runtime_provisioning(selection(), v2_env(libc_family="glibc", libc_version=libc_version), v2_catalog(runtime))
    assert plan["status"] == status
    if reason: assert reason in plan["reason_codes"]

@pytest.mark.parametrize(("libc_family", "libc_version", "reason", "status"), [
    ("", "", "libc_unknown", "blocked_missing_environment_facts"),
    ("musl", "1.2.5", "libc_family_mismatch", "blocked_no_compatible_runtime")])
def test_manylinux_unknown_and_musl_fail_closed(libc_family: str, libc_version: str, reason: str, status: str) -> None:
    plan = plan_local_runtime_provisioning(selection(), v2_env(libc_family=libc_family, libc_version=libc_version),
                                            v2_catalog(v2_entry("manylinux_2_35_x86_64")))
    assert plan["status"] == status and reason in plan["reason_codes"]

@pytest.mark.parametrize(("version", "architecture", "status", "reason"), [
    ("11.0", "arm64", "selected", None), ("10.15", "arm64", "blocked_no_compatible_runtime", "macos_version_too_old"),
    ("", "arm64", "blocked_missing_environment_facts", "macos_version_unknown"),
    ("14.0", "x86_64", "blocked_no_compatible_runtime", "wheel_architecture_mismatch")])
def test_macos_deployment_floor(version: str, architecture: str, status: str, reason: str | None) -> None:
    runtime = v2_entry("macosx_11_0_arm64")
    profile = v2_env(os_family="darwin", architecture=architecture, macos_version=version)
    plan = plan_local_runtime_provisioning(selection(), profile, v2_catalog(runtime))
    assert plan["status"] == status
    if reason: assert reason in plan["reason_codes"]

@pytest.mark.parametrize(("changes", "reason"), [
    ({"artifact_filename": "synthetic_runtime-1.2.3-py3-none-win32.whl"}, "wheel_tag_metadata_mismatch"),
    ({"artifact_filename": "synthetic_runtime-2.0.0-py3-none-win_amd64.whl"}, "wheel_version_mismatch")])
def test_v2_filename_is_cross_validation_only(changes: dict[str, object], reason: str) -> None:
    with pytest.raises(ValueError, match=reason): validate_runtime_catalog(v2_catalog(v2_entry(**changes)))

def test_v2_digest_is_order_stable_and_includes_backend_variant() -> None:
    a = v2_entry(runtime_id="a", backend_variant="cpu-a")
    b = v2_entry(runtime_id="b", backend_variant="cpu-b")
    first = validate_runtime_catalog(v2_catalog(a, b))
    assert first["catalog_digest"] == validate_runtime_catalog(v2_catalog(b, a))["catalog_digest"]
    assert first["catalog_digest"] != validate_runtime_catalog(v2_catalog({**a, "backend_variant": "changed"}, b))["catalog_digest"]

def test_end_to_end_v2_route_to_py3_none_runtime_plan() -> None:
    plan = plan_local_runtime_provisioning(selection(), v2_env(os_family="windows"), v2_catalog(v2_entry()))
    assert (plan["catalog_schema_version"], plan["runtime_id"], plan["python_tag"], plan["platform_tag"]) == (
        CATALOG_SCHEMA_VERSION_V2, "synthetic-v2", "py3", "win_amd64")
    assert plan["supported_python_versions"] == ("3.10", "3.11", "3.12")
