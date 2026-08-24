from __future__ import annotations
import subprocess
import pytest
from sentientos.local_runtime_backend_verification import (RuntimeBackendVerificationError,
    authorization_for, compose_verification_plan, sanitized_backend_environment, verify_runtime_backend)
from sentientos.local_runtime_dependencies import semantic_digest
from sentientos.local_runtime_import_verification import (authorization_for as import_authorization,
    compose_verification_plan as compose_import_plan, verify_runtime_import)
from tests.test_local_runtime_import_verification import _installed

pytestmark = pytest.mark.no_legacy_skip

def _case(tmp_path, **kwargs):
    installation, installed, _, _ = _installed(tmp_path, **kwargs)
    import_plan = compose_import_plan(installation, installed, tmp_path / "imports")
    imported = verify_runtime_import(import_plan, installation, installed,
        authorization=import_authorization(import_plan, operator_confirmed=True), execute=True)
    provisioning = {"status":"selected", **{key: installation[key] for key in ("runtime_id","engine","backend_family","backend_variant","package_name","package_version","environment_profile_digest")}, "external_prerequisite_codes": ["synthetic_catalog_requirement"] if installation["backend_family"] != "cpu" else []}
    provisioning["provisioning_plan_digest"] = semantic_digest(provisioning)
    installation["runtime_provisioning_plan_digest"] = provisioning["provisioning_plan_digest"]
    installation["installation_plan_digest"] = semantic_digest({k:v for k,v in installation.items() if k != "installation_plan_digest"})
    # Reinstall because the installation receipt is plan-bound.
    from sentientos.local_runtime_installation import install, authorization_for as installation_authorization
    paths = [__import__("pathlib").Path(a["verified_source_path"]) for a in installation["artifacts"]]
    installed = install(installation, wheel_paths=paths, observed_environment=installation["environment"], authorization=installation_authorization(installation, operator_confirmed=True), execute=True)
    import_plan = compose_import_plan(installation, installed, tmp_path / "imports")
    imported = verify_runtime_import(import_plan, installation, installed, authorization=import_authorization(import_plan, operator_confirmed=True), execute=True)
    plan = compose_verification_plan(provisioning, installation, installed, import_plan, imported, tmp_path / "backends")
    return provisioning, installation, installed, import_plan, imported, plan

def _run(case):
    provisioning, installation, installed, import_plan, imported, plan = case
    return verify_runtime_backend(plan, provisioning, installation, installed, import_plan, imported,
        authorization=authorization_for(plan, operator_confirmed=True), execute=True)

def test_selected_cpu_synthetic_exact_interpreter_backend_verification(tmp_path):
    result = _run(_case(tmp_path))
    assert result["selected_backend"] == "CPU"
    assert result["gpu_offload_supported"] is False
    assert result["runtime_execution_authority_granted"] is False

def test_selected_cpu_can_also_expose_metal(tmp_path):
    result = _run(_case(tmp_path, backend_info="CPU : name = host\nMTL : name = metal", gpu=True))
    assert result["selected_backend"] == "CPU"
    assert result["additional_accelerator_registries"] == ["MTL"]

def test_selected_cuda_synthetic_exact_interpreter_backend_verification(tmp_path):
    result = _run(_case(tmp_path, backend_family="cuda", backend_variant="cu124",
                        backend_info="CPU : name = host\nCUDA : name = cuda", gpu=True))
    assert result["selected_backend"] == "CUDA"
    assert result["backend_runtime_visibility_verified"] is True

def test_accelerator_rpc_cannot_become_local_backend_verified(tmp_path):
    case = _case(tmp_path, backend_family="cuda", backend_variant="cu124",
                 backend_info="CPU : name = host\nCUDA : name = cuda", gpu=True, rpc=True)
    with pytest.raises(RuntimeBackendVerificationError, match="runtime_backend_rpc_ambiguity"):
        _run(case)

def test_selected_registry_mismatch_fails(tmp_path):
    case = _case(tmp_path, backend_family="cuda", backend_variant="cu124",
                 backend_info="CPU : name = host\nROCm : name = hip", gpu=True)
    with pytest.raises(RuntimeBackendVerificationError, match="runtime_backend_registry_missing"):
        _run(case)

def test_competing_accelerators_fail_ambiguously(tmp_path):
    case = _case(tmp_path, backend_family="cuda", backend_variant="cu124",
                 backend_info="CPU : name = host\nCUDA : name = cuda\nROCm : name = hip", gpu=True)
    with pytest.raises(RuntimeBackendVerificationError, match="runtime_backend_accelerator_ambiguous"):
        _run(case)

def test_environment_strips_simulation_and_preserves_host_visibility(monkeypatch):
    for key in ("PYTHONPATH", "LLAMA_CPP_LIB_PATH", "GGML_CUDA_DEVICES", "GGML_METAL_DEVICES"):
        monkeypatch.setenv(key, "synthetic")
    for key in ("CUDA_VISIBLE_DEVICES", "HIP_VISIBLE_DEVICES", "ROCR_VISIBLE_DEVICES"):
        monkeypatch.setenv(key, "real-host")
    env = sanitized_backend_environment()
    assert all(key not in env for key in ("PYTHONPATH", "LLAMA_CPP_LIB_PATH", "GGML_CUDA_DEVICES", "GGML_METAL_DEVICES"))
    assert all(env[key] == "real-host" for key in ("CUDA_VISIBLE_DEVICES", "HIP_VISIBLE_DEVICES", "ROCR_VISIBLE_DEVICES"))

def test_timeout_and_duplicate_sentinel_fail_closed(tmp_path):
    case = _case(tmp_path); provisioning, installation, installed, import_plan, imported, plan = case
    auth = authorization_for(plan, operator_confirmed=True)
    def timeout(*a, **k): raise subprocess.TimeoutExpired(a[0], 1)
    with pytest.raises(RuntimeBackendVerificationError, match="runtime_backend_verification_timeout"):
        verify_runtime_backend(plan, provisioning, installation, installed, import_plan, imported,
            authorization=auth, execute=True, runner=timeout)

def test_missing_authorization_fails_before_backend_subprocess(tmp_path):
    provisioning, installation, installed, import_plan, imported, plan = _case(tmp_path)
    called = False
    def runner(*a, **k):
        nonlocal called; called=True; raise AssertionError
    with pytest.raises(RuntimeBackendVerificationError, match="runtime_backend_authorization_invalid"):
        verify_runtime_backend(plan, provisioning, installation, installed, import_plan, imported, execute=True, runner=runner)
    assert called is False

def test_repeat_fresh_probe_observes_identical_immutable_receipt(tmp_path):
    case = _case(tmp_path)
    first = _run(case)
    target = __import__("pathlib").Path(case[-1]["verification_receipt_root"]) / case[-1]["runtime_backend_verification_plan_digest"] / "runtime-backend-verification-receipt.json"
    before = target.read_bytes()
    second = _run(case)
    assert first["status"] == "runtime_backend_verified"
    assert second["status"] == "already_verified_current"
    assert target.read_bytes() == before

def test_conflicting_immutable_backend_receipt_fails_closed(tmp_path):
    case = _case(tmp_path); _run(case)
    target = __import__("pathlib").Path(case[-1]["verification_receipt_root"]) / case[-1]["runtime_backend_verification_plan_digest"] / "runtime-backend-verification-receipt.json"
    target.write_bytes(b"conflict")
    with pytest.raises(RuntimeBackendVerificationError, match="runtime_backend_receipt_conflict"):
        _run(case)

def test_unknown_accelerator_registry_is_observed_and_ambiguous(tmp_path):
    case = _case(tmp_path, backend_family="cuda", backend_variant="cu124",
                 backend_info="CPU : name = host\nCUDA : name = cuda\nFutureGPU : name = device", gpu=True)
    with pytest.raises(RuntimeBackendVerificationError, match="runtime_backend_accelerator_ambiguous"):
        _run(case)

def test_registry_name_in_feature_value_is_not_registry_evidence(tmp_path):
    case = _case(tmp_path, backend_family="cuda", backend_variant="cu124",
                 backend_info="CPU : description = CUDA", gpu=True)
    with pytest.raises(RuntimeBackendVerificationError, match="runtime_backend_registry_missing"):
        _run(case)

def test_crossed_provisioning_plan_fails_before_runner(tmp_path):
    case = list(_case(tmp_path)); crossed = dict(case[0]); crossed["runtime_id"] = "other"
    crossed["provisioning_plan_digest"] = semantic_digest({k:v for k,v in crossed.items() if k != "provisioning_plan_digest"})
    called = False
    def runner(*a, **k):
        nonlocal called; called = True
    with pytest.raises(RuntimeBackendVerificationError, match="runtime_backend_provisioning_mismatch"):
        verify_runtime_backend(case[-1], crossed, *case[1:-1], authorization=authorization_for(case[-1], operator_confirmed=True), execute=True, runner=runner)
    assert called is False
