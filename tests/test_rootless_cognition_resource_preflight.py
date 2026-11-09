# mypy: disable-error-code="no-untyped-def"
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.no_legacy_skip


@pytest.fixture
def runner(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_ROOTLESS_EXPERIMENT_WORKSPACE",
        str(tmp_path / "private-workspace"))
    sys.modules.pop("scripts.run_rootless_ollama_embodied_cognition_cycle", None)
    return importlib.import_module(
        "scripts.run_rootless_ollama_embodied_cognition_cycle")


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
        lambda *args, **kwargs: None)
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
