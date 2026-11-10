# mypy: disable-error-code="no-untyped-def"
from importlib.util import module_from_spec, spec_from_file_location
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pytestmark = pytest.mark.no_legacy_skip


def test_runner_scopes_governance_roots_before_governor_import(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / (
        "run_rootless_ollama_embodied_cognition_cycle.py")
    workspace = tmp_path / "private-workspace"
    code = """
import importlib.util
from pathlib import Path
script = Path(r"RUNNER_SCRIPT")
spec = importlib.util.spec_from_file_location("isolated_runner", script)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
from sentientos.federated_governance import get_controller
controller = get_controller()
expected = module.RUN_ROOT / "resource-governance"
assert controller._governor_root == expected / "governor"
assert controller._federation_root == expected / "federation"
"""
    code = code.replace("RUNNER_SCRIPT", str(script_path))
    env = os.environ.copy()
    env["SENTIENTOS_ROOTLESS_EXPERIMENT_WORKSPACE"] = str(workspace)
    completed = subprocess.run([sys.executable, "-c", code], cwd=repo_root,
        env=env, capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stderr


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


def test_task_family_acquisition_requires_complete_typed_probe_results(runner):
    descriptor = {"probe_inputs": [7, 8, 9]}
    invalid = {"protocol": {"objective_task_descriptor": descriptor},
        "objective_scores": [{"condition_id": "history_present", "score": {
            "status": "invalid_answer", "probe_count": 3, "probe_results": []}}]}
    invalid_result = runner._objective_family_acquisition_readiness(invalid)
    assert invalid_result == {
        "eligible": False,
        "classification": "acquisition_output_not_eligible_for_task_family_history",
        "score_status": "invalid_answer",
        "probe_result_count": 0,
        "required_probe_count": 3,
    }

    # Incorrect but well-formed answers remain valid acquisition evidence:
    # the evaluator's false labels are useful for measuring later transfer.
    incorrect = {"protocol": {"objective_task_descriptor": descriptor},
        "objective_scores": [{"condition_id": "history_present", "score": {
            "status": "incorrect", "probe_count": 3,
            "probe_results": [
                {"probe_input": 7, "observed_answer": 20, "correct": False},
                {"probe_input": 8, "observed_answer": 23, "correct": False},
                {"probe_input": 9, "observed_answer": 26, "correct": False},
            ]}}]}
    assert runner._objective_family_acquisition_readiness(incorrect)["eligible"] is True

    reordered = {"protocol": {"objective_task_descriptor": descriptor},
        "objective_scores": [{"condition_id": "history_present", "score": {
            "status": "incorrect", "probe_count": 3,
            "probe_results": [
                {"probe_input": 8, "observed_answer": 23, "correct": False},
                {"probe_input": 7, "observed_answer": 20, "correct": False},
                {"probe_input": 9, "observed_answer": 26, "correct": False},
            ]}}]}
    assert runner._objective_family_acquisition_readiness(reordered)["eligible"] is False

    malformed = {"protocol": {"objective_task_descriptor": descriptor},
        "objective_scores": [{"condition_id": "history_present", "score": {
            "status": "incorrect", "probe_count": 3,
            "probe_results": [
                {"probe_input": 7, "observed_answer": 20, "correct": False},
                {"probe_input": 8, "observed_answer": "23", "correct": False},
                {"probe_input": 9, "observed_answer": 26, "correct": False},
            ]}}]}
    assert runner._objective_family_acquisition_readiness(malformed)["eligible"] is False
def test_source_provenance_records_revision_and_hashes_worktree_paths_only(
        runner, monkeypatch, tmp_path):
    dirty_status = b" M private-session.json\0?? screenshots/frame.png\0"
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        if args[1] == "rev-parse":
            return SimpleNamespace(stdout=b"a" * 40 + b"\n")
        if args[1] == "status":
            return SimpleNamespace(stdout=dirty_status)
        if args[1] == "diff":
            return SimpleNamespace(stdout=b"tracked source diff")
        if args[1] == "ls-files":
            return SimpleNamespace(stdout=b"screenshots/frame.png\0")
        raise AssertionError(args)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    provenance = runner._source_provenance(tmp_path)

    assert provenance["observation_status"] == "observed"
    assert provenance["repository_revision"] == "a" * 40
    assert provenance["worktree_clean"] is False
    assert provenance["worktree_status_entry_count"] == 2
    assert provenance["worktree_status_digest"] == hashlib.sha256(
        dirty_status).hexdigest()
    assert provenance["worktree_content_status"] == "untracked_paths_present"
    assert provenance["worktree_content_digest"] is None
    assert provenance["worktree_paths_retained"] is False
    assert "private-session.json" not in repr(provenance)
    assert "screenshots/frame.png" not in repr(provenance)
    assert calls[0][1]["cwd"] == tmp_path
    assert calls[1][1]["cwd"] == tmp_path


def test_source_provenance_fingerprints_tracked_diff_without_storing_it(
        runner, monkeypatch, tmp_path):
    diff = {"value": b"first tracked edit"}

    def fake_run(args, **kwargs):
        if args[1] == "rev-parse":
            return SimpleNamespace(stdout=b"b" * 40 + b"\n")
        if args[1] == "status":
            return SimpleNamespace(stdout=b" M private-source.py\0")
        if args[1] == "diff":
            return SimpleNamespace(stdout=diff["value"])
        if args[1] == "ls-files":
            return SimpleNamespace(stdout=b"")
        raise AssertionError(args)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    first = runner._source_provenance(tmp_path)
    diff["value"] = b"second tracked edit"
    second = runner._source_provenance(tmp_path)

    assert first["worktree_content_status"] == "complete"
    assert first["worktree_content_digest"] == hashlib.sha256(
        b"first tracked edit").hexdigest()
    assert second["worktree_content_digest"] == hashlib.sha256(
        b"second tracked edit").hexdigest()
    assert first["worktree_content_digest"] != second["worktree_content_digest"]
    assert "first tracked edit" not in repr(first)
    assert "private-source.py" not in repr(first)


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
    ({"memory_free_mib": 10000, "temperature_celsius": 45},
        "gpu_memory_headroom_insufficient"),
])
def test_vram_preflight_fails_closed(runner, snapshot, reason):
    with pytest.raises(runner.RootlessExperimentalError, match=reason):
        runner._require_gpu_headroom(snapshot, 9 * 1024**3)


def test_vram_preflight_requires_model_weights_plus_runtime_reserve(runner):
    free_mib = (9 * 1024**3 + runner._GPU_RUNTIME_RESERVE_BYTES) // 1024**2
    runner._require_gpu_headroom(
        {"memory_free_mib": free_mib, "temperature_celsius": 45},
        9 * 1024**3)


def test_vram_preflight_uses_runtime_reserve_for_already_resident_model(runner):
    snapshot = {"memory_free_mib": 1693, "temperature_celsius": 58}
    runner._require_gpu_headroom(snapshot, 9 * 1024**3, model_resident=True)
    with pytest.raises(runner.RootlessExperimentalError,
            match="gpu_memory_headroom_insufficient"):
        runner._require_gpu_headroom(snapshot, 9 * 1024**3)


def test_guard_does_not_enter_model_backend_without_headroom(runner, monkeypatch):
    class Delegate:
        called = False

        def invoke(self, request, **kwargs):
            self.called = True
            return "inference"

    delegate = Delegate()
    coordinator = SimpleNamespace()
    evidence: list[dict[str, Any]] = []
    guarded = runner._ResourceGuardedInvoker(
        delegate, coordinator, 9 * 1024**3, evidence)
    monkeypatch.setattr(runner, "_refresh_resource_evidence",
        lambda *args, **kwargs: {"gpu_utilization_percent": 0})
    monkeypatch.setattr(runner, "_gpu_snapshot",
        lambda: {"memory_free_mib": 10000, "gpu_utilization_percent": 0,
            "temperature_celsius": 45})
    with pytest.raises(runner.RootlessExperimentalError,
            match="gpu_memory_headroom_insufficient"):
        guarded.invoke(object())
    assert delegate.called is False
    assert evidence[0]["gate_status"] == "blocked"
    assert evidence[0]["gate_reason"] == "gpu_memory_headroom_insufficient"
    assert evidence[0]["gpu_memory_free_mib"] == 10000


def test_guard_does_not_enter_model_backend_when_host_evidence_is_missing(
        runner, monkeypatch):
    class Delegate:
        called = False

        def invoke(self, request, **kwargs):
            self.called = True
            return "inference"

    delegate = Delegate()
    coordinator = SimpleNamespace()
    evidence: list[dict[str, Any]] = []
    guarded = runner._ResourceGuardedInvoker(
        delegate, coordinator, 9 * 1024**3, evidence)
    monkeypatch.setattr(runner, "_gpu_snapshot",
        lambda: {"memory_free_mib": 12000, "memory_total_mib": 12288,
            "gpu_utilization_percent": 0, "temperature_celsius": 45,
            "sampled_at": "2026-11-09T00:00:00+00:00",
            "source": "nvidia-smi",
            "scope": "host_wide_invocation_boundary_sample_not_process_attributed"})
    def unavailable(*args, **kwargs):
        raise runner.RootlessExperimentalError("host_resource_evidence_unavailable")
    monkeypatch.setattr(runner, "_refresh_resource_evidence", unavailable)
    with pytest.raises(runner.RootlessExperimentalError,
            match="host_resource_evidence_unavailable"):
        guarded.invoke(object())
    assert delegate.called is False
    assert evidence[0]["gate_status"] == "blocked"
    assert evidence[0]["gate_reason"] == "host_resource_evidence_unavailable"


def test_gpu_snapshot_accepts_normal_wsl_reserved_memory_gap(runner, monkeypatch):
    monkeypatch.setattr(runner.shutil, "which", lambda _: "nvidia-smi")
    monkeypatch.setattr(runner.subprocess, "run", lambda *args, **kwargs:
        SimpleNamespace(stdout="NVIDIA GeForce RTX 3060, 12288, 8783, 3331, 0, 44.5\n"))
    snapshot = runner._gpu_snapshot()
    assert snapshot is not None
    assert snapshot["memory_free_mib"] == 3331
    assert snapshot["gpu_utilization_percent"] == 0
    assert snapshot["temperature_celsius"] == 44.5
    assert snapshot["sampled_at"]
    assert "not_process_attributed" in snapshot["scope"]


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
        lambda: {"memory_free_mib": 12000, "memory_total_mib": 12288,
            "gpu_utilization_percent": 0, "temperature_celsius": 45,
            "sampled_at": "2026-11-09T00:00:00+00:00",
            "source": "nvidia-smi",
            "scope": "host_wide_invocation_boundary_sample_not_process_attributed"})
    assert guarded.invoke(object()) == "inference"
    assert delegate.called is True
    assert len(evidence) == 1
    record = evidence[0]
    assert record["inference_sequence"] == 1
    assert record["gate_status"] == "passed"
    assert record["evaluation_id"] == "fresh"
    assert record["gpu_utilization_percent"] == 0
    assert record["nvidia_smi_gpu_utilization_percent"] == 0
    assert record["gpu_memory_free_mib"] == 12000
    assert record["gpu_memory_total_mib"] == 12288
    assert record["preinference_gpu_utilization_limit_percent"] == (
        runner._MAX_PREINFERENCE_GPU_UTILIZATION_PERCENT)
    assert record["invocation_started_at"]
    assert record["invocation_finished_at"]
    assert record["post_inference_gpu_sample"]["gpu_utilization_percent"] == 0


def test_guard_blocks_when_direct_gpu_sample_is_busy_even_if_coordinator_is_quiet(
        runner, monkeypatch):
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
    monkeypatch.setattr(runner, "_MAX_PREINFERENCE_GPU_ATTEMPTS", 1)
    monkeypatch.setattr(runner, "_gpu_snapshot",
        lambda: {"memory_free_mib": 12000, "memory_total_mib": 12288,
            "gpu_utilization_percent": 80, "temperature_celsius": 45,
            "sampled_at": "2026-11-09T00:00:00+00:00",
            "source": "nvidia-smi",
            "scope": "host_wide_invocation_boundary_sample_not_process_attributed"})

    with pytest.raises(runner.RootlessExperimentalError,
            match="gpu_utilization_preflight_busy"):
        guarded.invoke(object())

    assert delegate.called is False
    assert evidence[0]["nvidia_smi_gpu_utilization_percent"] == 80
    assert evidence[0]["gpu_sampled_at"] == "2026-11-09T00:00:00+00:00"
    assert evidence[0]["gate_reason"] == "gpu_utilization_preflight_busy"


def test_guard_waits_for_transient_gpu_tail_without_relaxing_thresholds(
        runner, monkeypatch):
    class Delegate:
        called = False

        def invoke(self, request, **kwargs):
            self.called = True
            return "inference"

    delegate = Delegate()
    evidence: list[dict[str, Any]] = []
    guarded = runner._ResourceGuardedInvoker(
        delegate, SimpleNamespace(), 9 * 1024**3, evidence)
    host = iter((90, 0))
    direct = iter((80, 0))
    monkeypatch.setattr(runner, "_refresh_resource_evidence",
        lambda *args, **kwargs: {"evaluation_id": "fresh",
            "gpu_utilization_percent": next(host)})
    monkeypatch.setattr(runner, "_gpu_snapshot",
        lambda: {"memory_free_mib": 12000, "memory_total_mib": 12288,
            "gpu_utilization_percent": next(direct, 0), "temperature_celsius": 45,
            "sampled_at": "2026-11-10T00:00:00+00:00", "source": "nvidia-smi",
            "scope": "host_wide_invocation_boundary_sample_not_process_attributed"})
    monkeypatch.setattr(runner, "_PREINFERENCE_GPU_RETRY_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(runner, "_INFERENCE_GPU_SAMPLE_INTERVAL_SECONDS", 0)

    assert guarded.invoke(object()) == "inference"
    assert delegate.called is True
    assert len(evidence[0]["preinference_gpu_samples"]) == 2
    assert evidence[0]["preinference_gpu_samples"][0][
        "direct_gpu_utilization_percent"] == 80
    assert evidence[0]["preinference_gpu_samples"][1][
        "direct_gpu_utilization_percent"] == 0
    assert evidence[0]["preinference_gpu_utilization_limit_percent"] == 25.0


def test_guard_fails_closed_after_bounded_busy_gpu_wait(runner, monkeypatch):
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
        lambda *args, **kwargs: {"gpu_utilization_percent": 90})
    monkeypatch.setattr(runner, "_gpu_snapshot",
        lambda: {"memory_free_mib": 12000, "memory_total_mib": 12288,
            "gpu_utilization_percent": 80, "temperature_celsius": 45,
            "sampled_at": "2026-11-10T00:00:00+00:00", "source": "nvidia-smi",
            "scope": "host_wide_invocation_boundary_sample_not_process_attributed"})
    monkeypatch.setattr(runner, "_PREINFERENCE_GPU_RETRY_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(runner, "_MAX_PREINFERENCE_GPU_ATTEMPTS", 3)

    with pytest.raises(runner.RootlessExperimentalError,
            match="gpu_utilization_preflight_busy"):
        guarded.invoke(object())
    assert delegate.called is False
    assert len(evidence[0]["preinference_gpu_samples"]) == 3


@pytest.mark.parametrize("temperature,reason", [
    (None, "gpu_temperature_telemetry_unavailable"),
    (83, "gpu_temperature_limit_exceeded"),
])
def test_gpu_temperature_gate_fails_closed(runner, temperature, reason):
    snapshot = {"memory_free_mib": 12000, "temperature_celsius": temperature}
    with pytest.raises(runner.RootlessExperimentalError, match=reason):
        runner._require_gpu_headroom(snapshot, 9 * 1024**3)


def test_guard_keeps_loading_reserve_for_nonresident_model_and_runtime_floor_when_resident(
        runner, monkeypatch):
    class Delegate:
        called = False

        def invoke(self, request, **kwargs):
            self.called = True
            return "inference"

    delegate = Delegate()
    evidence: list[dict[str, Any]] = []
    guarded = runner._ResourceGuardedInvoker(
        delegate, SimpleNamespace(), 9 * 1024**3, evidence, model_name="hermes")
    monkeypatch.setattr(runner, "_model_residency_observed", lambda name: True)
    monkeypatch.setattr(runner, "_refresh_resource_evidence",
        lambda *args, **kwargs: {"evaluation_id": "fresh", "gpu_utilization_percent": 0})
    monkeypatch.setattr(runner, "_gpu_snapshot",
        lambda: {"memory_free_mib": 1693, "memory_total_mib": 12288,
            "gpu_utilization_percent": 0, "temperature_celsius": 58,
            "sampled_at": "2026-11-10T00:00:00+00:00", "source": "nvidia-smi",
            "scope": "host_wide_invocation_boundary_sample_not_process_attributed"})
    monkeypatch.setattr(runner, "_INFERENCE_GPU_SAMPLE_INTERVAL_SECONDS", 0.01)

    assert guarded.invoke(object()) == "inference"
    assert delegate.called is True
    assert evidence[0]["model_resident_at_preflight"] is True
    assert evidence[0]["required_gpu_headroom_bytes"] == (
        runner._GPU_RESIDENT_INFERENCE_RESERVE_BYTES)

def test_guard_preserves_post_inference_resource_sample_when_backend_fails(
        runner, monkeypatch):
    class Delegate:
        def invoke(self, request, **kwargs):
            raise RuntimeError("backend_failed")

    evidence: list[dict[str, Any]] = []
    guarded = runner._ResourceGuardedInvoker(
        Delegate(), SimpleNamespace(), 9 * 1024**3, evidence)
    monkeypatch.setattr(runner, "_refresh_resource_evidence",
        lambda *args, **kwargs: {"evaluation_id": "fresh",
            "gpu_utilization_percent": 0})
    samples = iter((
        {"memory_free_mib": 12000, "memory_total_mib": 12288,
            "gpu_utilization_percent": 0, "temperature_celsius": 45,
            "sampled_at": "2026-11-09T00:00:00+00:00",
            "source": "nvidia-smi", "scope": "host_wide_invocation_boundary_sample_not_process_attributed"},
        {"memory_free_mib": 6000, "memory_total_mib": 12288,
            "gpu_utilization_percent": 82,
            "sampled_at": "2026-11-09T00:00:02+00:00",
            "source": "nvidia-smi", "scope": "host_wide_invocation_boundary_sample_not_process_attributed"},
    ))
    monkeypatch.setattr(runner, "_gpu_snapshot", lambda: next(samples))

    with pytest.raises(RuntimeError, match="backend_failed"):
        guarded.invoke(object())

    record = evidence[0]
    assert record["gate_status"] == "passed"
    assert record["invocation_started_at"]
    assert record["invocation_finished_at"]
    assert record["post_inference_gpu_sample"]["gpu_utilization_percent"] == 82
    assert record["post_inference_gpu_sample"]["memory_free_mib"] == 6000
    assert record["post_inference_gpu_sample"]["sampled_at"] == (
        "2026-11-09T00:00:02+00:00")


def test_guard_collects_bounded_host_samples_during_inference(
        runner, monkeypatch):
    class Delegate:
        def invoke(self, request, **kwargs):
            time.sleep(0.03)
            return "inference"

    evidence: list[dict[str, Any]] = []
    guarded = runner._ResourceGuardedInvoker(
        Delegate(), SimpleNamespace(), 9 * 1024**3, evidence)
    monkeypatch.setattr(runner, "_INFERENCE_GPU_SAMPLE_INTERVAL_SECONDS", 0.001)
    monkeypatch.setattr(runner, "_refresh_resource_evidence",
        lambda *args, **kwargs: {"evaluation_id": "fresh",
            "gpu_utilization_percent": 0})
    calls = 0

    def snapshot():
        nonlocal calls
        calls += 1
        return {"memory_free_mib": 12000, "memory_total_mib": 12288,
            "gpu_utilization_percent": min(calls, 100), "temperature_celsius": 45,
            "sampled_at": f"2026-11-09T00:00:{calls:02d}+00:00",
            "source": "nvidia-smi",
            "scope": "host_wide_invocation_boundary_sample_not_process_attributed"}

    monkeypatch.setattr(runner, "_gpu_snapshot", snapshot)

    assert guarded.invoke(object()) == "inference"

    record = evidence[0]
    assert record["during_inference_gpu_sampling_status"] == "sampled"
    assert record["during_inference_gpu_sampling_interval_seconds"] == 0.001
    assert 1 <= len(record["during_inference_gpu_samples"]) <= (
        runner._MAX_DURING_INFERENCE_GPU_SAMPLES)
    assert all("not_process_attributed" in sample["scope"]
        for sample in record["during_inference_gpu_samples"])



def test_guard_stops_after_sustained_inference_temperature_pressure(
        runner, monkeypatch):
    class Delegate:
        def invoke(self, request, **kwargs):
            time.sleep(0.03)
            return "inference"

    evidence: list[dict[str, Any]] = []
    guarded = runner._ResourceGuardedInvoker(
        Delegate(), SimpleNamespace(), 9 * 1024**3, evidence)
    monkeypatch.setattr(runner, "_refresh_resource_evidence",
        lambda *args, **kwargs: {"gpu_utilization_percent": 0})
    calls = 0

    def snapshot():
        nonlocal calls
        calls += 1
        temperature = 45 if calls == 1 else 83
        return {"memory_free_mib": 12000, "memory_total_mib": 12288,
            "gpu_utilization_percent": 0, "temperature_celsius": temperature,
            "sampled_at": "2026-11-10T00:00:00+00:00", "source": "nvidia-smi",
            "scope": "host_wide_invocation_boundary_sample_not_process_attributed"}

    monkeypatch.setattr(runner, "_gpu_snapshot", snapshot)
    monkeypatch.setattr(runner, "_INFERENCE_GPU_SAMPLE_INTERVAL_SECONDS", 0.001)
    with pytest.raises(runner.RootlessExperimentalError,
            match="gpu_temperature_limit_sustained"):
        guarded.invoke(object())
    assert evidence[0]["thermal_abort_after_call"] is True
    assert evidence[0]["thermal_hot_sample_streak"] >= 2

def test_guard_stops_sampling_at_the_configured_attempt_limit(
        runner, monkeypatch):
    class Delegate:
        def invoke(self, request, **kwargs):
            time.sleep(0.03)
            return "inference"

    evidence: list[dict[str, Any]] = []
    guarded = runner._ResourceGuardedInvoker(
        Delegate(), SimpleNamespace(), 9 * 1024**3, evidence)
    monkeypatch.setattr(runner, "_INFERENCE_GPU_SAMPLE_INTERVAL_SECONDS", 0.001)
    monkeypatch.setattr(runner, "_MAX_DURING_INFERENCE_GPU_SAMPLES", 2)
    monkeypatch.setattr(runner, "_refresh_resource_evidence",
        lambda *args, **kwargs: {"evaluation_id": "fresh",
            "gpu_utilization_percent": 0})
    monkeypatch.setattr(runner, "_gpu_snapshot",
        lambda: {"memory_free_mib": 12000, "memory_total_mib": 12288,
            "gpu_utilization_percent": 0, "temperature_celsius": 45,
            "sampled_at": "2026-11-09T00:00:00+00:00",
            "source": "nvidia-smi",
            "scope": "host_wide_invocation_boundary_sample_not_process_attributed"})

    assert guarded.invoke(object()) == "inference"

    record = evidence[0]
    assert record["during_inference_gpu_sample_attempt_count"] == 2
    assert len(record["during_inference_gpu_samples"]) == 2
    assert record["during_inference_gpu_sampling_status"] == (
        "sampling_window_exhausted")


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
    evidence: list[dict[str, Any]] = []
    guarded = runner._ResourceGuardedInvoker(
        delegate, SimpleNamespace(), 9 * 1024**3, evidence)
    sampled_utilization = (resource_record.get("gpu_utilization_percent")
        if type(resource_record.get("gpu_utilization_percent")) is int else 0)
    monkeypatch.setattr(runner, "_MAX_PREINFERENCE_GPU_ATTEMPTS", 1)
    monkeypatch.setattr(runner, "_gpu_snapshot",
        lambda: {"memory_free_mib": 12000, "memory_total_mib": 12288,
            "gpu_utilization_percent": sampled_utilization, "temperature_celsius": 45})
    monkeypatch.setattr(runner, "_refresh_resource_evidence",
        lambda *args, **kwargs: resource_record)
    with pytest.raises(runner.RootlessExperimentalError, match=reason):
        guarded.invoke(object())
    assert delegate.called is False
    assert evidence[0]["gate_status"] == "blocked"
    assert evidence[0]["gate_reason"] == reason



def test_guard_uses_valid_direct_gpu_sample_when_host_gpu_collector_is_unavailable(
        runner, monkeypatch):
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
            "gpu_utilization_percent": None})
    samples = iter((0, 0))
    monkeypatch.setattr(runner, "_gpu_snapshot",
        lambda: {"memory_free_mib": 12000, "memory_total_mib": 12288,
            "gpu_utilization_percent": next(samples, 0), "temperature_celsius": 45,
            "sampled_at": "2026-11-10T00:00:00+00:00", "source": "nvidia-smi",
            "scope": "host_wide_invocation_boundary_sample_not_process_attributed"})
    monkeypatch.setattr(runner, "_INFERENCE_GPU_SAMPLE_INTERVAL_SECONDS", 0.01)

    assert guarded.invoke(object()) == "inference"
    assert delegate.called is True
    assert evidence[0]["host_gpu_utilization_telemetry_missing"] is True
    assert evidence[0]["effective_preinference_gpu_utilization_percent"] == 0

def test_incomplete_run_artifact_preserves_blocked_resource_sample(
        runner, monkeypatch, tmp_path):
    run_root = tmp_path / "run"
    run_root.mkdir()
    sample = {"inference_sequence": 1, "gpu_utilization_percent": 80, "temperature_celsius": 45,
        "gate_status": "blocked", "gate_reason": "gpu_utilization_preflight_busy"}
    monkeypatch.setattr(runner, "RUN_ROOT", run_root)
    monkeypatch.setattr(runner, "RESOURCE_PREFLIGHT_EVIDENCE", [sample])
    monkeypatch.setattr(runner, "_verify_model_released",
        lambda _: {"status": "target_model_not_resident"})
    monkeypatch.setattr(runner, "_gpu_snapshot", lambda: None)
    artifact_path = runner._persist_incomplete_run(
        runner.RootlessExperimentalError("gpu_utilization_preflight_busy"))
    assert artifact_path is not None
    artifact = json.loads(artifact_path.read_text())
    assert artifact["schema_version"] == (
        "sentientos.rootless_ollama_embodied_cognition_failure:v3")
    assert artifact["resource_preflight_samples"] == [sample]
    assert artifact["source_provenance"] == runner.RUN_SOURCE_PROVENANCE
    assert "process attribution" in artifact["resource_preflight_sample_scope"]


def test_incomplete_run_artifact_classifies_pre_action_without_model_text(
        runner, monkeypatch, tmp_path):
    run_root = tmp_path / "run"
    receipt_root = run_root / "inference-custody" / "receipts"
    receipt_root.mkdir(parents=True)
    run_id = "rootless-cognition-cycle-fixture"
    monkeypatch.setattr(runner, "RUN_ROOT", run_root)
    monkeypatch.setattr(runner, "RUN_ID", run_id)
    monkeypatch.setattr(runner, "RESOURCE_PREFLIGHT_EVIDENCE", [])
    monkeypatch.setattr(runner, "_verify_model_released",
        lambda _: {"status": "target_model_not_resident"})
    monkeypatch.setattr(runner, "_gpu_snapshot", lambda: None)
    request_id = run_id + ":pre-action-decision"
    tick_id = "companion-interaction-" + hashlib.sha256(
        request_id.encode("utf-8")).hexdigest()[:32]
    correlation_id = tick_id + ":resident_developmental_cognition:companion-interaction"
    output_text = json.dumps({"disposition": "answer", "response": json.dumps({
        "requested_pose": "idle", "predicted_pose": "idle"})})
    receipt = {"receipt_id": "fixture-receipt", "receipt_digest": "d" * 64,
        "purpose": "resident_developmental_companion_interaction",
        "output_digest": "e" * 64, "reason_codes": [], "output_text": output_text,
        "request": {"correlation_id": correlation_id,
            "upstream_evidence": {"record_ids": []}}}
    (receipt_root / "lmrec-fixture.json").write_text(json.dumps(receipt))

    artifact_path = runner._persist_incomplete_run(
        runner.RootlessExperimentalError("pre_action_goal_not_met"))

    assert artifact_path is not None
    artifact_text = artifact_path.read_text()
    artifact = json.loads(artifact_text)
    proposal = artifact["inference_receipts"][0]
    assert proposal["pre_action_decision_classification"] == "exact_schema_goal_not_met"
    assert proposal["pre_action_requested_pose"] == "idle"
    assert proposal["pre_action_predicted_pose"] == "idle"
    assert proposal["pre_action_prediction_consistent"] is True
    assert proposal["model_output_text_excluded"] is True
    assert output_text not in artifact_text

    timeout_root = tmp_path / "timeout-run"
    timeout_receipt_root = timeout_root / "inference-custody" / "receipts"
    timeout_receipt_root.mkdir(parents=True)
    timeout_receipt = {**receipt, "output_digest": None,
        "reason_codes": ["timeout_worker_terminated", "timeout"]}
    timeout_receipt.pop("output_text")
    (timeout_receipt_root / "lmrec-timeout.json").write_text(
        json.dumps(timeout_receipt))
    monkeypatch.setattr(runner, "RUN_ROOT", timeout_root)
    timeout_artifact_path = runner._persist_incomplete_run(
        runner.RootlessExperimentalError("timeout"))

    assert timeout_artifact_path is not None
    timeout_artifact = json.loads(timeout_artifact_path.read_text())
    timeout_proposal = timeout_artifact["inference_receipts"][0]
    assert timeout_proposal["pre_action_decision_classification"] == (
        "no_completed_model_output")
    assert timeout_proposal["pre_action_requested_pose"] is None
    assert timeout_proposal["pre_action_prediction_consistent"] is None


def test_pose_decision_classifier_requires_exact_json_schema(runner):
    assert runner._pose_decision_from_response(
        '{"requested_pose":"reach","predicted_pose":"reach"}') == {
            "requested_pose": "reach", "predicted_pose": "reach"}
    assert runner._pose_decision_from_response(
        'requested_pose: reach; predicted_pose: reach') is None
    assert runner._pose_decision_from_response(
        '{"requested_pose":"reach","predicted_pose":"reach","extra":"x"}') is None
