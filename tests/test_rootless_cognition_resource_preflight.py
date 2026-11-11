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


@pytest.mark.parametrize(("arguments", "expected_returncode"), [
    (("--help",), 0),
    (("--unexpected",), 2),
])
def test_runner_cli_arguments_exit_before_experiment_workspace_creation(
        tmp_path, arguments, expected_returncode):
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / (
        "run_rootless_ollama_embodied_cognition_cycle.py")
    workspace = tmp_path / "private-workspace"
    env = os.environ.copy()
    env["SENTIENTOS_ROOTLESS_EXPERIMENT_WORKSPACE"] = str(workspace)
    completed = subprocess.run([sys.executable, str(script_path), *arguments],
        cwd=repo_root, env=env, capture_output=True, text=True, timeout=10)
    assert completed.returncode == expected_returncode
    assert "usage:" in (completed.stdout + completed.stderr).casefold()
    assert not workspace.exists()
    assert '"run_id"' not in (completed.stdout + completed.stderr)


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


def test_rootless_cycle_input_bound_keeps_history_with_large_current_evidence(runner):
    from sentientos.resident_developmental_cognition import (
        EXPERIMENT_CONTEXT_INSTRUCTION,
        _bind_history_and_epistemic_context,
    )

    history_record = {
        "record_id": "record-budget-fixture",
        "record_digest": "sha256:" + "a" * 64,
        "created_at": "2026-11-10T00:00:00+00:00",
        "epistemic_posture": "historical_interpretation_not_current_truth",
        "candidate": {
            "candidate_id": "candidate-budget-fixture",
            "candidate_digest": "sha256:" + "b" * 64,
            "interpretation": "Previously observed task evidence remains uncertain.",
            "uncertainty": "high",
            "epistemic_status": "untrusted_historical_interpretation_candidate",
            "selected_fact_ids": ["fact-budget-fixture"],
        },
    }
    context = {
        "instruction": EXPERIMENT_CONTEXT_INSTRUCTION,
        "current_evidence": {"evidence": "x" * 13_000},
        "prior_self_model": None,
        "prior_epistemic_state": None,
        "developmental_history": [],
        "developmental_history_posture": "historical_interpretation_not_current_truth",
        "developmental_history_task_family_id":
            "rootless_integer_affine_transfer_low_range_v1",
        "developmental_history_target_model_identity": {
            "engine": "ollama",
            "model_content_sha256": "c" * 64,
            "resolved_artifact_path": "x" * 600,
        },
        "developmental_history_retrieval_policy_id":
            "task_family_probe_overlap_then_recency_fill:v2",
    }

    _, _, bounded_prompt, bounded_ids, _ = _bind_history_and_epistemic_context(
        context=context, records=(history_record,), projection=None,
        history_present=True,
        max_input_chars=runner.ROOTLESS_DEVELOPMENTAL_COGNITION_INPUT_CHAR_LIMIT)
    _, _, legacy_prompt, legacy_ids, _ = _bind_history_and_epistemic_context(
        context=context, records=(history_record,), projection=None,
        history_present=True, max_input_chars=16_384)

    assert len(bounded_prompt) > 16_384
    assert len(bounded_prompt) <= runner.ROOTLESS_DEVELOPMENTAL_COGNITION_INPUT_CHAR_LIMIT
    assert (runner.ROOTLESS_DEVELOPMENTAL_COGNITION_INPUT_CHAR_LIMIT
        - len(bounded_prompt)) >= 1_024
    assert bounded_ids == ("record-budget-fixture",)
    assert len(legacy_prompt) <= 16_384
    assert legacy_ids == ()


@pytest.mark.parametrize(("counts", "qualified", "classification"), [
    ((0, 0, 0), False, "baseline_competence_not_demonstrated"),
    ((0, 3, 0), True, "history_associated_acquisition_cost_restored"),
    ((3, 3, 3), True, "no_correct_count_difference"),
    ((2, 3, 1), True, "history_effect_not_restored"),
])
def test_objective_acquisition_summary_reports_withheld_baseline_and_restoration(
        runner, counts, qualified, classification):
    condition_ids = ("history_present", "history_withheld", "history_restored")
    scores = []
    for index, (condition_id, correct_count) in enumerate(zip(condition_ids, counts)):
        score = {
            "status": "correct" if correct_count == 3 else "incorrect",
            "probe_count": 3,
            "correct_count": correct_count,
        }
        if index == 0:
            score["probe_results"] = [
                {"correct": position < correct_count} for position in range(3)]
        scores.append({"condition_id": condition_id, "score": score})

    summary = runner._objective_acquisition_summary({"objective_scores": scores})
    assert summary["condition_correct_counts"] == list(counts)
    assert summary["history_withheld_baseline_correct_count"] == counts[1]
    assert summary["history_restored_correct_count"] == counts[2]
    assert summary["baseline_competence_qualified"] is qualified
    assert summary["baseline_effect_classification"] == classification
    assert summary["history_present_minus_withheld_correct_count"] == (
        counts[0] - counts[1])
    assert summary["restored_minus_present_correct_count"] == (
        counts[2] - counts[0])


@pytest.mark.parametrize(("accurate_count", "expected"), [
    (0, False),
    (1, False),
    (2, True),
    (3, True),
])
def test_affine_transfer_requires_two_accurate_acquisition_examples(
        runner, accurate_count, expected):
    eligibility = runner._objective_transfer_eligibility({
        "retained_accurate_example_count": accurate_count})
    assert eligibility["eligible"] is expected
    assert eligibility["accurate_example_count"] == accurate_count
    assert eligibility["required_accurate_example_count"] == 2
    assert eligibility["reason"] == (
        None if expected else "insufficient_accurate_acquisition_examples")


@pytest.mark.parametrize("value", [True, -1, 1.0, "2", None])
def test_affine_transfer_eligibility_rejects_invalid_accurate_counts(runner, value):
    with pytest.raises(runner.RootlessExperimentalError,
            match="objective_family_acquisition_accuracy_count_invalid"):
        runner._objective_transfer_eligibility({
            "retained_accurate_example_count": value})


def test_experiment_seed_provenance_separates_task_and_backend_seeds(
        runner, monkeypatch):
    monkeypatch.setattr(runner, "EXPERIMENT_SEED", 20261115)
    assert runner._experiment_seed_provenance() == {
        "task_generation_seed": 20261115,
        "requested_backend_seed": 42,
    }

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
    failure = runner.RootlessExperimentalError("gpu_utilization_preflight_busy")
    failure.diagnostic = {
        "schema_version": "sentientos.developmental_evidence_selection_failure:v1",
        "encoded_size_bytes": 12000, "byte_limit": 10240,
        "fact_count": 1, "source_count": 1, "conflict_count": 0,
        "fact_subject_kinds": ["synthetic_fixture"],
        "source_kinds": ["embodiment"], "bounded_objective_trial": False}
    artifact_path = runner._persist_incomplete_run(failure)
    assert artifact_path is not None
    artifact = json.loads(artifact_path.read_text())
    assert artifact["schema_version"] == (
        "sentientos.rootless_ollama_embodied_cognition_failure:v4")
    assert artifact["resource_preflight_samples"] == [sample]
    assert artifact["failure_diagnostic"]["encoded_size_bytes"] == 12000
    assert artifact["failure_diagnostic"]["byte_limit"] == 10240
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
    decision_evidence = {
        "schema_version": "sentientos.pre_action_decision_evidence:v1",
        "classification": "goal_not_met", "response_digest": "f" * 64,
        "response_size_bytes": len("idle->idle"),
        "requested_pose": "idle", "predicted_pose": "idle",
        "prediction_consistent": True, "response_lineage_verified": True,
        "evidence_ids": ["fact-current"], "history_record_ids": [],
        "authority": False, "action_executed": False,
    }
    monkeypatch.setattr(runner, "PRE_ACTION_DECISION_EVIDENCE", decision_evidence)
    request_id = run_id + ":pre-action-decision"
    tick_id = "companion-interaction-" + hashlib.sha256(
        request_id.encode("utf-8")).hexdigest()[:32]
    correlation_id = tick_id + ":resident_developmental_cognition:companion-interaction"
    output_text = json.dumps({"disposition": "answer", "response": "idle->idle"})
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
    assert proposal["pre_action_decision_classification"] == "exact_pair_goal_not_met"
    assert proposal["pre_action_requested_pose"] == "idle"
    assert proposal["pre_action_predicted_pose"] == "idle"
    assert proposal["pre_action_prediction_consistent"] is True
    assert proposal["model_output_text_excluded"] is True
    assert artifact["pre_action_decision_evidence"] == decision_evidence
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


def test_pose_decision_classifier_requires_exact_action_prediction_token(runner):
    assert runner._pose_decision_from_response("reach->reach") == {
        "requested_pose": "reach", "predicted_pose": "reach"}
    assert runner._pose_decision_from_response("idle->reach") == {
        "requested_pose": "idle", "predicted_pose": "reach"}
    for invalid in ("reach", "reach -> reach", "REACH->REACH",
            "reach->reach because the target is clear",
            '{"requested_pose":"reach","predicted_pose":"reach"}', None):
        assert runner._pose_decision_from_response(invalid) is None


@pytest.mark.parametrize(("requested", "predicted", "goal_met"), [
    ("idle", "idle", False),
    ("reach", "reach", False),
])
def test_synthetic_action_consequence_retains_task_goal_outcome(
        runner, requested, predicted, goal_met):
    snapshot, evidence, proprioception = runner._embodied_source(
        requested_pose=requested, predicted_pose=predicted)
    assert snapshot.facts
    assert evidence["consequence_classification"] == (
        "expectation_satisfied" if predicted == "idle"
        else "expectation_contradicted")
    assert evidence["effect_proven"] is False
    assert evidence["task_goal"] == "reach_marked_target"
    assert evidence["task_goal_met"] is goal_met
    assert evidence["task_goal_evaluation_posture"] == (
        "synthetic_fixture_relation_of_observed_pose_to_task_goal")
    assert evidence["independent_observation_pose"]["task_goal_met"] is False
    assert any(fact.payload.get("commanded_value", {}).get("task_goal")
        == "reach_marked_target" for fact in snapshot.facts)
    assert any(fact.payload.get("independently_observed_value", {}).get(
        "task_goal_met") is False for fact in snapshot.facts)
    assert evidence["action_execution_posture"] == "synthetic_fixture_only"
    assert proprioception.freshness == "current"


def test_transfer_decision_prompt_requires_grounded_current_evidence(runner):
    question = runner.TRANSFER_DECISION_QUESTION
    assert len(question) <= 1200
    assert "evidence_ids with the exact current fact ID" in question
    assert "evidence_ids []" not in question
    assert "history_record_ids with the exact cited record ID" in question
    assert "reported_values.predicted_observation.pose" in question
    assert "reported_values.observer_report_field.pose" in question
    assert "not proof of physical effect" in question



def test_seeded_objective_task_pairs_are_reproducible_and_distinct(runner):
    first = runner._objective_task_pair(20261110)
    repeated = runner._objective_task_pair(20261110)
    second = runner._objective_task_pair(20261111)

    assert [task.specification() for task in first] == [
        task.specification() for task in repeated]
    assert [task.specification() for task in first] != [
        task.specification() for task in second]
    acquisition, transfer = first
    assert acquisition.specification()["task_family_id"] == (
        transfer.specification()["task_family_id"])
    assert transfer.specification()["requires_task_family_history"] is True
    assert acquisition.specification()["task_family_id"] == (
        "rootless_integer_affine_transfer_low_range_v1")
    assert set(acquisition.specification()["probe_inputs"]).isdisjoint(
        transfer.specification()["probe_inputs"])
    for task in first:
        specification = task.specification()
        assert specification["multiplier"] in {2, 3}
        assert specification["offset"] in {0, 1, 2}
        inputs = specification["probe_inputs"]
        assert len(inputs) == 3
        if specification["requires_task_family_history"]:
            assert all(6 <= item <= 9 for item in inputs)
            assert max(specification["multiplier"] * item
                + specification["offset"] for item in inputs) <= 29
        else:
            assert all(2 <= item <= 5 for item in inputs)
            assert max(specification["multiplier"] * item
                + specification["offset"] for item in inputs) <= 17


def test_experiment_seed_environment_is_bounded_and_validated(runner, monkeypatch):
    monkeypatch.setenv("SENTIENTOS_HERMES_EXPERIMENT_SEED", "42")
    assert runner._experiment_seed_from_environment() == 42
    for invalid in ("0", "-1", "4294967296", "４２", "nope"):
        monkeypatch.setenv("SENTIENTOS_HERMES_EXPERIMENT_SEED", invalid)
        with pytest.raises(SystemExit, match="hermes_experiment_seed_invalid"):
            runner._experiment_seed_from_environment()



def test_objective_transfer_requires_matching_present_restored_and_withheld_history(
        runner):
    acquisition_id = "devrec-acquisition"
    conditions = [
        {"condition_id": "history_present",
            "retrieved_record_ids": [acquisition_id]},
        {"condition_id": "history_withheld", "retrieved_record_ids": []},
        {"condition_id": "history_restored",
            "retrieved_record_ids": [acquisition_id]},
    ]
    observed = runner._objective_transfer_observations(conditions, acquisition_id)
    assert set(observed) == {
        "history_present", "history_withheld", "history_restored"}

    duplicate = [dict(item) for item in conditions]
    duplicate[2] = {**duplicate[2], "condition_id": "history_present"}
    with pytest.raises(runner.RootlessExperimentalError,
            match="objective_family_transfer_observation_lineage_incomplete"):
        runner._objective_transfer_observations(duplicate, acquisition_id)
    with pytest.raises(runner.RootlessExperimentalError,
            match="objective_family_transfer_observation_lineage_incomplete"):
        runner._objective_transfer_observations(conditions + [None], acquisition_id)

    leaked = [dict(item) for item in conditions]
    leaked[1] = {"condition_id": "history_withheld",
        "retrieved_record_ids": [acquisition_id]}
    with pytest.raises(runner.RootlessExperimentalError,
            match="objective_family_transfer_withheld_history_leaked"):
        runner._objective_transfer_observations(leaked, acquisition_id)

    missing = [dict(item) for item in conditions]
    missing[2] = {"condition_id": "history_restored", "retrieved_record_ids": []}
    with pytest.raises(runner.RootlessExperimentalError,
            match="objective_family_transfer_history_not_retrieved"):
        runner._objective_transfer_observations(missing, acquisition_id)

    decoy_present = [dict(item) for item in conditions]
    decoy_present[0] = {**decoy_present[0],
        "retrieved_record_ids": [acquisition_id, "unrelated-record"]}
    with pytest.raises(runner.RootlessExperimentalError,
            match="objective_family_transfer_history_not_retrieved"):
        runner._objective_transfer_observations(decoy_present, acquisition_id)

    decoy_withheld = [dict(item) for item in conditions]
    decoy_withheld[1] = {**decoy_withheld[1],
        "retrieved_record_ids": ["unrelated-record"]}
    with pytest.raises(runner.RootlessExperimentalError,
            match="objective_family_transfer_withheld_history_leaked"):
        runner._objective_transfer_observations(decoy_withheld, acquisition_id)



def test_objective_transfer_report_preserves_score_and_history_lineage(runner):
    acquisition_id = "devrec-acquisition"
    conditions = [
        {"condition_id": "history_present",
            "retrieved_record_ids": [acquisition_id], "inference_receipt_id": "receipt-0",
            "inference_receipt_digest": "receipt-digest-0", "output_digest": "output-0"},
        {"condition_id": "history_withheld", "retrieved_record_ids": [],
            "inference_receipt_id": "receipt-1", "inference_receipt_digest": "receipt-digest-1",
            "output_digest": "output-1"},
        {"condition_id": "history_restored",
            "retrieved_record_ids": [acquisition_id], "inference_receipt_id": "receipt-2",
            "inference_receipt_digest": "receipt-digest-2", "output_digest": "output-2"},
    ]
    observations = runner._objective_transfer_observations(conditions, acquisition_id)
    scores = [{
        "condition_id": condition_id,
        "score": {"correct_count": 1, "probe_count": 3,
            "status": "partially_correct", "output_digest": f"output-{index}"},
        "inference_receipt_id": f"receipt-{index}",
        "inference_receipt_digest": f"receipt-digest-{index}",
        "invocation_output_digest": f"output-{index}",
    } for index, condition_id in enumerate((
        "history_present", "history_withheld", "history_restored"))]

    summaries = runner._objective_transfer_condition_summaries(
        scores, observations, acquisition_id)

    assert [item["condition_id"] for item in summaries] == [
        "history_present", "history_withheld", "history_restored"]
    assert [item["output_digest"] for item in summaries] == [
        "output-0", "output-1", "output-2"]
    assert [item["retrieved_record_ids"] for item in summaries] == [
        [acquisition_id], [], [acquisition_id]]
    assert [item["task_family_history_record_id_retrieved"]
        for item in summaries] == [True, False, True]
    assert [item["inference_receipt_id"] for item in summaries] == [
        "receipt-0", "receipt-1", "receipt-2"]
    assert [item["inference_receipt_digest"] for item in summaries] == [
        "receipt-digest-0", "receipt-digest-1", "receipt-digest-2"]

    malformed_scores = list(scores)
    malformed_scores[1] = {**malformed_scores[1], "condition_id": "history_restored"}
    with pytest.raises(runner.RootlessExperimentalError,
            match="objective_family_transfer_report_conditions_incomplete"):
        runner._objective_transfer_condition_summaries(
            malformed_scores, observations, acquisition_id)
    with pytest.raises(runner.RootlessExperimentalError,
            match="objective_family_transfer_report_conditions_incomplete"):
        runner._objective_transfer_condition_summaries(
            scores + [None], observations, acquisition_id)

    mismatched_receipt = list(scores)
    mismatched_receipt[1] = {**mismatched_receipt[1],
        "inference_receipt_digest": "different-receipt"}
    with pytest.raises(runner.RootlessExperimentalError,
            match="objective_family_transfer_report_lineage_invalid"):
        runner._objective_transfer_condition_summaries(
            mismatched_receipt, observations, acquisition_id)

    mismatched_output = list(scores)
    mismatched_output[1] = {**mismatched_output[1],
        "invocation_output_digest": "different-output"}
    with pytest.raises(runner.RootlessExperimentalError,
            match="objective_family_transfer_report_lineage_invalid"):
        runner._objective_transfer_condition_summaries(
            mismatched_output, observations, acquisition_id)



def test_objective_acquisition_summary_counts_only_verified_scored_examples(runner):
    run = {"objective_scores": [
        {"condition_id": "history_present", "score": {
            "correct_count": 1, "probe_count": 2, "status": "partially_correct",
            "probe_results": [{"correct": True}, {"correct": False}]}},
        {"condition_id": "history_withheld", "score": {
            "correct_count": 0, "probe_count": 2, "status": "incorrect",
            "probe_results": [{"correct": False}, {"correct": False}]}},
        {"condition_id": "history_restored", "score": {
            "correct_count": 1, "probe_count": 2, "status": "partially_correct",
            "probe_results": [{"correct": True}, {"correct": False}]}},
    ]}
    result = runner._objective_acquisition_summary(run)
    assert result["condition_correct_counts"] == [1, 0, 1]
    assert result["retained_accurate_example_count"] == 1
    assert result["retained_inaccurate_example_count"] == 1

    run["objective_scores"][0]["score"]["correct_count"] = 2
    with pytest.raises(runner.RootlessExperimentalError,
            match="objective_family_acquisition_score_invalid"):
        runner._objective_acquisition_summary(run)



def test_resource_refresh_records_disk_headroom_and_fails_closed(runner, monkeypatch):
    snapshot = SimpleNamespace(cpu_utilization_percent=4.0,
        ram_utilization_percent=35.0, disk_free_bytes=8 * 1024**3,
        disk_utilization_percent=22.0, gpu_utilization_percent=2.0,
        vram_utilization_percent=20.0)
    evaluation = SimpleNamespace(evaluation_id="resource-eval",
        snapshot=snapshot, epoch=SimpleNamespace(observed_at="time"),
        pressure_report=SimpleNamespace(pressure_labels=()))
    coordinator = SimpleNamespace(run_cycle=lambda **kwargs: evaluation)
    monkeypatch.setattr(runner, "validate_evaluation",
        lambda _: SimpleNamespace(ok=True))
    evidence = runner._refresh_resource_evidence(
        coordinator, correlation_id="disk-headroom-test")
    assert evidence["disk_free_bytes"] == 8 * 1024**3
    assert evidence["disk_utilization_percent"] == 22.0

    snapshot.disk_free_bytes = None
    with pytest.raises(runner.RootlessExperimentalError,
            match="host_disk_evidence_incomplete"):
        runner._refresh_resource_evidence(coordinator,
            correlation_id="missing-disk-test")
    snapshot.disk_free_bytes = runner._MIN_EXPERIMENT_DISK_FREE_BYTES - 1
    with pytest.raises(runner.RootlessExperimentalError,
            match="host_disk_headroom_insufficient"):
        runner._refresh_resource_evidence(coordinator,
            correlation_id="low-disk-test")


def test_later_action_probe_has_current_synthetic_target_evidence(runner):
    from sentientos.world_state_board import validate_snapshot

    target = runner._synthetic_current_target_record()
    snapshot = runner.WorldStateBoardBuilder().build([target])

    assert validate_snapshot(snapshot).valid
    assert len(snapshot.facts) == 1
    fact = snapshot.facts[0]
    assert fact.subject.subject_id == "synthetic-target-1"
    assert fact.subject.subject_kind == "target_object"
    assert fact.payload["visible"] is True
    assert fact.payload["distance"] == "within_reach"
    assert fact.payload["hazard_status"] == "unknown"
    assert fact.payload["evidence_posture"] == "synthetic_test"
    assert fact.payload["declared_provenance_class"] == (
        "deterministic_synthetic_fixture")
    assert fact.effect_proven is False
    assert fact.effect_claimed is False


def test_failure_code_keeps_only_bounded_non_output_diagnostics(runner):
    assert runner._failure_code(ValueError("resident_response_schema_invalid")) == (
        "resident_response_schema_invalid")
    assert runner._failure_code(ValueError(
        "raw model text: requested_pose=reach")) == "ValueError"


def test_target_evidence_is_added_only_when_requested_for_later_probe(runner):
    from sentientos.world_state_board import validate_snapshot

    plain, _ = runner._pre_action_source(pose="reach")
    grounded, _ = runner._pre_action_source(
        pose="reach", include_current_target=True)

    assert len(plain.facts) == 1
    assert len(grounded.facts) == 2
    assert {fact.subject.subject_kind for fact in grounded.facts} == {
        "robot_body", "target_object"}
    assert validate_snapshot(plain).valid
    assert validate_snapshot(grounded).valid
