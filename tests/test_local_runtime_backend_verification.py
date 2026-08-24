from __future__ import annotations
import subprocess
import pytest
from sentientos.local_runtime_backend_verification import (RuntimeBackendVerificationError,
    authorization_for, compose_verification_plan, sanitized_backend_environment, verify_runtime_backend)
from sentientos.local_runtime_import_verification import (authorization_for as import_authorization,
    compose_verification_plan as compose_import_plan, verify_runtime_import)
from tests.test_local_runtime_import_verification import _installed

pytestmark = pytest.mark.no_legacy_skip

def _case(tmp_path, **kwargs):
    installation, installed, _, _ = _installed(tmp_path, **kwargs)
    import_plan = compose_import_plan(installation, installed, tmp_path / "imports")
    imported = verify_runtime_import(import_plan, installation, installed,
        authorization=import_authorization(import_plan, operator_confirmed=True), execute=True)
    plan = compose_verification_plan(installation, installed, import_plan, imported, tmp_path / "backends")
    return installation, installed, import_plan, imported, plan

def _run(case):
    installation, installed, import_plan, imported, plan = case
    return verify_runtime_backend(plan, installation, installed, import_plan, imported,
        authorization=authorization_for(plan, operator_confirmed=True), execute=True)

def test_selected_cpu_synthetic_exact_interpreter_backend_verification(tmp_path):
    result = _run(_case(tmp_path))
    assert result["selected_backend"] == "CPU"
    assert result["gpu_offload_supported"] is False
    assert result["runtime_execution_authority_granted"] is False

def test_selected_cpu_can_also_expose_metal(tmp_path):
    result = _run(_case(tmp_path, backend_info="CPU | MTL", gpu=True))
    assert result["selected_backend"] == "CPU"
    assert result["additional_accelerator_registries"] == ["MTL"]

def test_selected_cuda_synthetic_exact_interpreter_backend_verification(tmp_path):
    result = _run(_case(tmp_path, backend_family="cuda", backend_variant="cu124",
                        backend_info="CPU | CUDA", gpu=True))
    assert result["selected_backend"] == "CUDA"
    assert result["backend_runtime_visibility_verified"] is True

def test_accelerator_rpc_cannot_become_local_backend_verified(tmp_path):
    case = _case(tmp_path, backend_family="cuda", backend_variant="cu124",
                 backend_info="CPU | CUDA", gpu=True, rpc=True)
    with pytest.raises(RuntimeBackendVerificationError, match="runtime_backend_rpc_ambiguity"):
        _run(case)

def test_selected_registry_mismatch_fails(tmp_path):
    case = _case(tmp_path, backend_family="cuda", backend_variant="cu124",
                 backend_info="CPU | ROCm", gpu=True)
    with pytest.raises(RuntimeBackendVerificationError, match="runtime_backend_registry_missing"):
        _run(case)

def test_competing_accelerators_fail_ambiguously(tmp_path):
    case = _case(tmp_path, backend_family="cuda", backend_variant="cu124",
                 backend_info="CPU | CUDA | ROCm", gpu=True)
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
    case = _case(tmp_path); installation, installed, import_plan, imported, plan = case
    auth = authorization_for(plan, operator_confirmed=True)
    def timeout(*a, **k): raise subprocess.TimeoutExpired(a[0], 1)
    with pytest.raises(RuntimeBackendVerificationError, match="runtime_backend_verification_timeout"):
        verify_runtime_backend(plan, installation, installed, import_plan, imported,
            authorization=auth, execute=True, runner=timeout)

def test_missing_authorization_fails_before_backend_subprocess(tmp_path):
    installation, installed, import_plan, imported, plan = _case(tmp_path)
    called = False
    def runner(*a, **k):
        nonlocal called; called=True; raise AssertionError
    with pytest.raises(RuntimeBackendVerificationError, match="runtime_backend_authorization_invalid"):
        verify_runtime_backend(plan, installation, installed, import_plan, imported, execute=True, runner=runner)
    assert called is False
