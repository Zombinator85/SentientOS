# mypy: disable-error-code="no-untyped-def"
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pytestmark = pytest.mark.no_legacy_skip


@pytest.fixture
def runner(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_ROOTLESS_EXPERIMENT_WORKSPACE",
        str(tmp_path / "private-workspace"))
    script_path = (Path(__file__).resolve().parents[1] / "scripts"
        / "run_rootless_ollama_embodied_cognition_cycle.py")
    spec = spec_from_file_location("rootless_cognition_cycle_test_module",
        script_path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_model_weight_size_is_read_from_pinned_ollama_manifest(runner, tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"layers": [
        {"mediaType": "application/vnd.ollama.image.model", "size": 9000},
        {"mediaType": "application/vnd.ollama.image.template", "size": 10},
    ]}))
    assert runner._model_weight_bytes(manifest) == 9000


def test_model_weight_size_rejects_ambiguous_manifest(runner, tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"layers": [
        {"mediaType": "application/vnd.ollama.image.model", "size": 9000},
        {"mediaType": "application/vnd.ollama.image.model", "size": 500},
    ]}))
    with pytest.raises(runner.RootlessExperimentalError,
            match="pinned_hermes_model_size_invalid"):
        runner._model_weight_bytes(manifest)


@pytest.mark.parametrize("snapshot,reason", [
    (None, "gpu_memory_telemetry_unavailable"),
    ({}, "gpu_memory_telemetry_unavailable"),
    ({"memory_free_mib": 10000}, "gpu_memory_headroom_insufficient"),
])
def test_vram_preflight_fails_closed(runner, snapshot, reason):
    with pytest.raises(runner.RootlessExperimentalError, match=reason):
        runner._require_gpu_headroom(snapshot, 9 * 1024**3)


def test_vram_preflight_requires_model_weights_plus_runtime_reserve(runner):
    free_mib = (9 * 1024**3 + runner._GPU_RUNTIME_RESERVE_BYTES) // 1024**2
    runner._require_gpu_headroom({"memory_free_mib": free_mib}, 9 * 1024**3)


def test_guard_does_not_enter_model_backend_without_headroom(runner, monkeypatch):
    class Delegate:
        called = False

        def invoke(self, request, **kwargs):
            self.called = True
            return "inference"

    delegate = Delegate()
    coordinator = SimpleNamespace()
    guarded = runner._ResourceGuardedInvoker(delegate, coordinator, 9 * 1024**3)
    monkeypatch.setattr(runner, "_refresh_resource_evidence",
        lambda *args, **kwargs: {"gpu_utilization_percent": 0})
    monkeypatch.setattr(runner, "_gpu_snapshot",
        lambda: {"memory_free_mib": 10000})
    with pytest.raises(runner.RootlessExperimentalError,
            match="gpu_memory_headroom_insufficient"):
        guarded.invoke(object())
    assert delegate.called is False


def test_guard_does_not_enter_model_backend_when_host_evidence_is_missing(
        runner, monkeypatch):
    class Delegate:
        called = False

        def invoke(self, request, **kwargs):
            self.called = True
            return "inference"

    delegate = Delegate()
    coordinator = SimpleNamespace()
    guarded = runner._ResourceGuardedInvoker(delegate, coordinator, 9 * 1024**3)
    monkeypatch.setattr(runner, "_gpu_snapshot",
        lambda: {"memory_free_mib": 12000, "memory_total_mib": 12288})
    def unavailable(*args, **kwargs):
        raise runner.RootlessExperimentalError("host_resource_evidence_unavailable")
    monkeypatch.setattr(runner, "_refresh_resource_evidence", unavailable)
    with pytest.raises(runner.RootlessExperimentalError,
            match="host_resource_evidence_unavailable"):
        guarded.invoke(object())
    assert delegate.called is False


def test_gpu_snapshot_accepts_normal_wsl_reserved_memory_gap(runner, monkeypatch):
    monkeypatch.setattr(runner.shutil, "which", lambda _: "nvidia-smi")
    monkeypatch.setattr(runner.subprocess, "run", lambda *args, **kwargs:
        SimpleNamespace(stdout="NVIDIA GeForce RTX 3060, 12288, 8783, 3331\n"))
    snapshot = runner._gpu_snapshot()
    assert snapshot is not None
    assert snapshot["memory_free_mib"] == 3331


def test_guard_calls_backend_only_after_both_preflights(runner, monkeypatch):
    class Delegate:
        called = False

        def invoke(self, request, **kwargs):
            self.called = True
            return "inference"

    delegate = Delegate()
    evidence: list[dict[str, Any]] = []
    guarded = runner._ResourceGuardedInvoker(
        delegate, SimpleNamespace(), 9 * 1024**3, evidence)
    monkeypatch.setattr(runner, "_refresh_resource_evidence",
        lambda *args, **kwargs: {"evaluation_id": "fresh",
            "gpu_utilization_percent": 0})
    monkeypatch.setattr(runner, "_gpu_snapshot",
        lambda: {"memory_free_mib": 12000, "memory_total_mib": 12288})
    assert guarded.invoke(object()) == "inference"
    assert delegate.called is True
    assert evidence == [{"evaluation_id": "fresh",
        "gpu_utilization_percent": 0,
        "gpu_memory_free_mib": 12000, "gpu_memory_total_mib": 12288,
        "preinference_gpu_utilization_limit_percent":
            runner._MAX_PREINFERENCE_GPU_UTILIZATION_PERCENT}]


def test_resource_governor_enforcement_is_scoped_and_restored(
        runner, monkeypatch, tmp_path):
    observed_modes = []

    class Governor:
        def __init__(self):
            observed_modes.append(runner.os.environ.get(
                "SENTIENTOS_ENFORCEMENT_RUNTIME_GOVERNOR"))

    class Kernel:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class Coordinator:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "shadow")
    monkeypatch.delenv("SENTIENTOS_ENFORCEMENT_RUNTIME_GOVERNOR",
        raising=False)
    monkeypatch.setattr(runner, "RuntimeGovernor", Governor)
    monkeypatch.setattr(runner, "ControlPlaneKernel", Kernel)
    monkeypatch.setattr(runner, "HostResourceRuntimeCoordinator", Coordinator)
    monkeypatch.setattr(runner, "RUN_ROOT", tmp_path / "run")
    kernel, coordinator = runner._enforcing_resource_runtime()
    assert observed_modes == ["enforce"]
    assert runner.os.environ.get("SENTIENTOS_ENFORCEMENT_RUNTIME_GOVERNOR") is None
    assert coordinator.kwargs["kernel"] is kernel


@pytest.mark.parametrize("resource_record,reason", [
    ({"gpu_utilization_percent": None}, "gpu_utilization_telemetry_unavailable"),
    ({"gpu_utilization_percent": 80}, "gpu_utilization_preflight_busy"),
])
def test_guard_blocks_inference_without_quiet_gpu_preflight(
        runner, monkeypatch, resource_record, reason):
    class Delegate:
        called = False

        def invoke(self, request, **kwargs):
            self.called = True
            return "inference"

    delegate = Delegate()
    guarded = runner._ResourceGuardedInvoker(delegate, SimpleNamespace(), 9 * 1024**3)
    monkeypatch.setattr(runner, "_refresh_resource_evidence",
        lambda *args, **kwargs: resource_record)
    with pytest.raises(runner.RootlessExperimentalError, match=reason):
        guarded.invoke(object())
    assert delegate.called is False
