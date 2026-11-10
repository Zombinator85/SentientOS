"""Run one bounded Hermes trial through the resident developmental cognition owner.

The body and observer are synthetic fixtures. The developmental record, cognition
observations, history ablation, model identity, and local inference receipts use
the existing governed SentientOS owners. This is not production serving evidence.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, NoReturn, cast

# Bind imports to this checkout even when WSL's login shell starts elsewhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

workspace = Path(os.environ.get(
    "SENTIENTOS_ROOTLESS_EXPERIMENT_WORKSPACE",
    str(Path.home() / ".local/state/sentientos-hermes-epistemic")))
workspace.mkdir(parents=True, exist_ok=True, mode=0o700)
if workspace.is_symlink():
    raise SystemExit("private_experiment_workspace_cannot_be_symlink")
os.chmod(workspace, 0o700)
os.environ["SENTIENTOS_ROOTLESS_EXPERIMENT_WORKSPACE"] = str(workspace)

# Isolate governance writes before importing RuntimeGovernor or its federated
# governance singleton. The runner is a one-shot process, so this scoped
# environment cannot redirect the live companion's or daemon's state.
RUN_ID = "rootless-cognition-cycle-" + uuid.uuid4().hex[:20]
RUN_ROOT = (workspace / "sentientos-data" / "rootless-experimental"
    / "developmental-cognition-cycles" / RUN_ID)
governance_root = RUN_ROOT / "resource-governance"
os.environ["SENTIENTOS_GOVERNOR_ROOT"] = str(governance_root / "governor")
os.environ["SENTIENTOS_FEDERATION_ROOT"] = str(governance_root / "federation")
os.environ["SENTIENTOS_REPO_ROOT"] = str(Path(__file__).resolve().parents[1])

from sentientos.avatar_authoring import renderer_handoff
from sentientos.codex_task_authority_admission import (
    RESIDENT_DEVELOPMENTAL_WRITEBACK,
    RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION,
)
from sentientos.developmental_companion_bridge import ResidentDevelopmentalCompanionBridge
from sentientos.developmental_history_intervention_experiment import (
    qualify_history_transfer_decision,
    qualify_restoration_stable_history_association,
    qualify_semantic_history_decision)
from sentientos.developmental_model_replacement_experiment import ObjectivePredictionTask
from sentientos.world_state_board import WorldStateSnapshot
from sentientos.embodiment_self_observation import (
    EmbodimentEvidenceOwner, EmbodimentObservation, semantic_digest)
from sentientos.embodied_consequence import (
    SyntheticIndependentObserver, SyntheticRenderer, evaluate_consequence,
    make_expectation, world_state_records as consequence_world_state_records)
from sentientos.local_model_authority import (
    ROOTLESS_EXPERIMENTAL_DEVELOPMENTAL_PURPOSE, digest_payload, stream_sha256)
from sentientos.local_runtime_provisioning import semantic_digest as runtime_digest
from sentientos.resident_developmental_cognition import (
    ResidentDevelopmentalCognitionConfig, ResidentDevelopmentalCognitionOwner,
    ResidentDevelopmentalCognitionError, load_objective_request,
    objective_task_for_request, stage_objective_request)
from sentientos.resident_developmental_writeback import (
    ResidentDevelopmentalWritebackController)
from sentientos.runtime_admission import (
    AdmissionLedger, RuntimeAdmissionAuthority, RuntimeAdmissionVerifier)
from sentientos.rootless_experimental_local_model import (
    EXPERIMENT_ROOT, RootlessExperimentalError, _no_symlink_path)
from sentientos.rootless_experimental_ollama_epistemic_session import (
    RootlessExperimentalOllamaDevelopmentalSession)
from sentientos.control_plane_kernel import ControlPlaneKernel
from sentientos.federated_enforcement_policy import resolve_policy
from sentientos.host_resource_runtime import (
    HostResourceRuntimeCoordinator, validate_evaluation)
from sentientos.runtime_governor import RuntimeGovernor
from sentientos.world_state_board import WorldStateBoardBuilder


MODEL_NAME = os.environ.get("SENTIENTOS_HERMES_MODEL", "sentientos-hermes4:14b-q4km")
_MAX_EXPERIMENT_SEED = 2**32 - 1


def _experiment_seed_from_environment() -> int:
    raw = os.environ.get("SENTIENTOS_HERMES_EXPERIMENT_SEED")
    if raw is None:
        return (uuid.uuid4().int & _MAX_EXPERIMENT_SEED) or 1
    if (len(raw) > 10 or not raw.isascii() or not raw.isdecimal()
            or not 0 < int(raw) <= _MAX_EXPERIMENT_SEED):
        raise SystemExit("hermes_experiment_seed_invalid")
    return int(raw)


EXPERIMENT_SEED = _experiment_seed_from_environment()


def _objective_condition_score(condition: Mapping[str, Any]) -> Any:
    return condition.get("score")


def _objective_acquisition_summary(run: Mapping[str, Any]) -> dict[str, Any]:
    scores = run.get("objective_scores")
    if (not isinstance(scores, list)
            or [item.get("condition_id") for item in scores
                if isinstance(item, Mapping)]
                != ["history_present", "history_withheld", "history_restored"]):
        raise RootlessExperimentalError(
            "objective_family_acquisition_scores_incomplete")
    present = scores[0].get("score")
    if not isinstance(present, Mapping):
        raise RootlessExperimentalError(
            "objective_family_acquisition_score_invalid")
    probe_results = present.get("probe_results")
    correct_count = present.get("correct_count")
    probe_count = present.get("probe_count")
    if (not isinstance(probe_results, list)
            or type(correct_count) is not int or type(probe_count) is not int
            or len(probe_results) != probe_count
            or any(not isinstance(row, Mapping)
                or type(row.get("correct")) is not bool for row in probe_results)
            or sum(row["correct"] for row in probe_results) != correct_count):
        raise RootlessExperimentalError(
            "objective_family_acquisition_score_invalid")
    return {
        "condition_correct_counts": [
            _objective_condition_score(item).get("correct_count")
            if isinstance(_objective_condition_score(item), Mapping) else None
            for item in scores],
        "history_present_correct_count": correct_count,
        "probe_count": probe_count,
        "retained_accurate_example_count": correct_count,
        "retained_inaccurate_example_count": probe_count - correct_count,
        "acquisition_outcome_status": present.get("status"),
    }


def _objective_transfer_observations(
        conditions: Any, acquisition_record_id: str) -> dict[str, Mapping[str, Any]]:
    if not isinstance(conditions, list):
        raise RootlessExperimentalError(
            "objective_family_transfer_observation_lineage_incomplete")
    observations: dict[str, Mapping[str, Any]] = {}
    for item in conditions:
        if not isinstance(item, Mapping):
            continue
        condition_id = item.get("condition_id")
        if isinstance(condition_id, str):
            observations[condition_id] = item
    if set(observations) != {
            "history_present", "history_withheld", "history_restored"}:
        raise RootlessExperimentalError(
            "objective_family_transfer_observation_lineage_incomplete")
    for condition_id in ("history_present", "history_restored"):
        retrieved_ids = observations[condition_id].get("retrieved_record_ids", [])
        if (not isinstance(retrieved_ids, (list, tuple))
                or acquisition_record_id not in retrieved_ids):
            raise RootlessExperimentalError(
                "objective_family_transfer_history_not_retrieved")
    withheld_ids = observations["history_withheld"].get("retrieved_record_ids", [])
    if (not isinstance(withheld_ids, (list, tuple))
            or acquisition_record_id in withheld_ids):
        raise RootlessExperimentalError(
            "objective_family_transfer_withheld_history_leaked")
    return observations


def _objective_task_pair(seed: int) -> tuple[ObjectivePredictionTask, ObjectivePredictionTask]:
    if type(seed) is not int or not 0 < seed <= _MAX_EXPERIMENT_SEED:
        raise RootlessExperimentalError("hermes_experiment_seed_invalid")
    generator = random.Random(seed)
    multiplier = generator.randrange(2, 6)
    offset = generator.randrange(1, 10)
    acquisition_inputs = tuple(sorted(generator.sample(range(4, 10), 3)))
    transfer_inputs = tuple(sorted(generator.sample(range(12, 20), 3)))
    family = "rootless_integer_affine_transfer"
    acquisition = ObjectivePredictionTask(
        multiplier=multiplier, offset=offset, probe_input=acquisition_inputs[0],
        additional_probe_inputs=acquisition_inputs[1:], task_family_id=family)
    transfer = ObjectivePredictionTask(
        multiplier=multiplier, offset=offset, probe_input=transfer_inputs[0],
        additional_probe_inputs=transfer_inputs[1:], task_family_id=family,
        requires_task_family_history=True)
    return acquisition, transfer


TRANSFER_DECISION_QUESTION = (
    "Controlled new-decision transfer probe. This is a new synthetic task, "
    "not a request to recall or quote the past. Choose one next action for "
    "the current target: INSPECT or REACH. Read the current World-State and "
    "eligible developmental history. If a history record for a prior reach "
    "contains predicted pose reach and observer-reported pose idle, propose "
    "INSPECT before another reach. If no such history record is available, "
    "propose REACH based on the current target. Treat the old observer value "
    "as an uncertain historical report, never as current truth. Return the "
    "standard JSON response with disposition answer, evidence_ids containing "
    "the exact current fact ID that grounds the target, history_record_ids "
    "containing the exact cited record ID when history supports INSPECT "
    "(otherwise []), and response exactly INSPECT or REACH. If no current "
    "fact grounds the target, abstain with response HISTORY_UNAVAILABLE and "
    "no citations. This is a proposal only: do not claim that an action was "
    "authorized or executed.")
MANIFEST_PATH = EXPERIMENT_ROOT / "ollama-model-manifests" / (
    "f6a766d405cbb73f9ba64a59b8fb29a3418d0da0b6fad15a0ca70687413ce0ce.json")
RUN_STAGE = "startup"
RESOURCE_PREFLIGHT_EVIDENCE: list[dict[str, Any]] = []


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _runtime_observation(model_digest: str) -> tuple[dict[str, Any], str]:
    request = urllib.request.Request("http://127.0.0.1:11434/api/version", method="GET")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=5) as response:
        payload = json.loads(response.read(4096).decode("utf-8"))
    observed = {"backend": "ollama-loopback",
        "version": str(payload.get("version", "unknown")),
        "model_manifest_digest": model_digest,
        "runtime_attestation": "local_observation_only"}
    return observed, runtime_digest(observed)


def _gpu_snapshot() -> dict[str, Any] | None:
    executable = shutil.which("nvidia-smi")
    if executable is None and Path("/usr/lib/wsl/lib/nvidia-smi").is_file():
        executable = "/usr/lib/wsl/lib/nvidia-smi"
    if executable is None:
        return None
    try:
        result = subprocess.run([executable,
            "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu",
            "--format=csv,noheader,nounits"], capture_output=True, text=True,
            timeout=5, check=True)
        rows = [line.strip().split(",") for line in result.stdout.splitlines()
            if line.strip()]
        if len(rows) != 1 or len(rows[0]) != 6:
            return None
        name, total, used, free, utilization, temperature = (
            item.strip() for item in rows[0])
        total_mib, used_mib, free_mib = int(total), int(used), int(free)
        utilization_percent = int(utilization)
        temperature_celsius = float(temperature)
        if (not name or min(total_mib, used_mib, free_mib) < 0
                or total_mib <= 0 or used_mib > total_mib or free_mib > total_mib
                or not 0 <= utilization_percent <= 100
                or not 0 <= temperature_celsius <= 120
                or abs(total_mib - used_mib - free_mib) > 512):
            return None
        return {"name": name[:128], "memory_total_mib": total_mib,
            "memory_used_mib": used_mib, "memory_free_mib": free_mib,
            "gpu_utilization_percent": utilization_percent,
            "temperature_celsius": temperature_celsius,
            "sampled_at": _now(), "source": "nvidia-smi",
            "scope": "host_wide_invocation_boundary_sample_not_process_attributed"}
    except Exception:
        return None


_GPU_RUNTIME_RESERVE_BYTES = 2 * 1024**3
_GPU_RESIDENT_INFERENCE_RESERVE_BYTES = 1 * 1024**3
# This is an experiment-quality gate, not a system-wide resource policy. A
# history comparison should not begin while another workload is already using
# a substantial share of the GPU; WSL cannot reliably attribute Windows GPU
# clients to their owning application.
_MAX_PREINFERENCE_GPU_UTILIZATION_PERCENT = 25.0
_MAX_EXPERIMENT_GPU_TEMPERATURE_CELSIUS = 82
_MAX_PREINFERENCE_GPU_ATTEMPTS = 3
_PREINFERENCE_GPU_RETRY_INTERVAL_SECONDS = 1.0
_INFERENCE_GPU_SAMPLE_INTERVAL_SECONDS = 1.0
_MAX_DURING_INFERENCE_GPU_SAMPLES = 512


def _model_weight_bytes(manifest_path: Path) -> int:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RootlessExperimentalError("pinned_hermes_manifest_unreadable") from exc
    layers = manifest.get("layers") if isinstance(manifest, dict) else None
    if not isinstance(layers, list):
        raise RootlessExperimentalError("pinned_hermes_model_layers_unavailable")
    weights = [item.get("size") for item in layers
        if isinstance(item, dict)
        and item.get("mediaType") == "application/vnd.ollama.image.model"]
    if (len(weights) != 1 or type(weights[0]) is not int
            or weights[0] <= 0 or weights[0] > 64 * 1024**3):
        raise RootlessExperimentalError("pinned_hermes_model_size_invalid")
    return weights[0]


def _require_gpu_headroom(snapshot: Mapping[str, Any] | None,
        model_weight_bytes: int, *, model_resident: bool = False
        ) -> Mapping[str, Any]:
    if snapshot is None or type(snapshot.get("memory_free_mib")) is not int:
        raise RootlessExperimentalError("gpu_memory_telemetry_unavailable")
    if (not isinstance(snapshot.get("temperature_celsius"), (int, float))
            or isinstance(snapshot.get("temperature_celsius"), bool)):
        raise RootlessExperimentalError("gpu_temperature_telemetry_unavailable")
    if snapshot["temperature_celsius"] > _MAX_EXPERIMENT_GPU_TEMPERATURE_CELSIUS:
        raise RootlessExperimentalError("gpu_temperature_limit_exceeded")
    required_bytes = (_GPU_RESIDENT_INFERENCE_RESERVE_BYTES if model_resident
        else model_weight_bytes + _GPU_RUNTIME_RESERVE_BYTES)
    free_bytes = int(snapshot["memory_free_mib"]) * 1024**2
    if free_bytes < required_bytes:
        raise RootlessExperimentalError("gpu_memory_headroom_insufficient")
    return snapshot


def _enforcing_resource_runtime() -> tuple[ControlPlaneKernel,
        HostResourceRuntimeCoordinator]:
    # The experiment must not inherit the repository's default shadow posture.
    key = "SENTIENTOS_ENFORCEMENT_RUNTIME_GOVERNOR"
    previous = os.environ.get(key)
    os.environ[key] = "enforce"
    try:
        if resolve_policy().runtime_governor != "enforce":
            raise RootlessExperimentalError("runtime_governor_enforcement_unavailable")
        governor = RuntimeGovernor()
    finally:
        if previous is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = previous
    kernel = ControlPlaneKernel(runtime_governor=governor,
        decisions_path=RUN_ROOT / "resource-governance" / "kernel_decisions.jsonl")
    coordinator = HostResourceRuntimeCoordinator(kernel=kernel,
        runtime_state_root=RUN_ROOT / "resource-observations")
    return kernel, coordinator


def _refresh_resource_evidence(coordinator: HostResourceRuntimeCoordinator,
        *, correlation_id: str) -> dict[str, Any]:
    evaluation = coordinator.run_cycle(correlation_id=correlation_id)
    if evaluation is None or not validate_evaluation(evaluation).ok:
        raise RootlessExperimentalError("host_resource_evidence_unavailable")
    snapshot = evaluation.snapshot
    if snapshot.cpu_utilization_percent is None or snapshot.ram_utilization_percent is None:
        raise RootlessExperimentalError("host_resource_evidence_incomplete")
    return {"evaluation_id": evaluation.evaluation_id,
        "observed_at": evaluation.epoch.observed_at,
        "pressure_labels": list(evaluation.pressure_report.pressure_labels),
        "cpu_utilization_percent": snapshot.cpu_utilization_percent,
        "ram_utilization_percent": snapshot.ram_utilization_percent,
        "gpu_utilization_percent": snapshot.gpu_utilization_percent,
        "vram_utilization_percent": snapshot.vram_utilization_percent}


class _ResourceGuardedInvoker:
    """Refresh host evidence and VRAM headroom before every governed inference."""

    def __init__(self, delegate: Any, coordinator: HostResourceRuntimeCoordinator,
            model_weight_bytes: int,
            evidence_records: list[dict[str, Any]] | None = None,
            model_name: str | None = None) -> None:
        self._delegate = delegate
        self._coordinator = coordinator
        self._model_weight_bytes = model_weight_bytes
        self._evidence_records = evidence_records if evidence_records is not None else []
        self._model_name = model_name
        self._sequence = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)

    def invoke(self, request: Any, **kwargs: Any) -> Any:
        self._sequence += 1
        resource_record: dict[str, Any] = {
            "inference_sequence": self._sequence,
            "gate_status": "blocked",
        }

        preflight_samples: list[dict[str, Any]] = []

        def blocked(reason: str) -> NoReturn:
            resource_record["gate_reason"] = reason
            resource_record["preinference_gpu_samples"] = list(preflight_samples)
            self._evidence_records.append(dict(resource_record))
            raise RootlessExperimentalError(reason)

        fresh_resource: dict[str, Any] | None = None
        gpu_snapshot: Mapping[str, Any] | None = None
        for attempt in range(1, _MAX_PREINFERENCE_GPU_ATTEMPTS + 1):
            try:
                fresh_resource = _refresh_resource_evidence(self._coordinator,
                    correlation_id=f"{RUN_ID}-inference-{self._sequence}-preflight-{attempt}")
            except Exception as exc:
                resource_record["gate_reason"] = _failure_code(exc)
                resource_record["preinference_gpu_samples"] = preflight_samples
                self._evidence_records.append(dict(resource_record))
                raise
            gpu_sample = _gpu_snapshot()
            host_util = fresh_resource.get("gpu_utilization_percent")
            direct_util = (gpu_sample.get("gpu_utilization_percent")
                if isinstance(gpu_sample, Mapping) else None)
            preflight_samples.append({
                "attempt": attempt,
                "host_gpu_utilization_percent": host_util,
                "direct_gpu_utilization_percent": direct_util,
                "memory_free_mib": (gpu_sample.get("memory_free_mib")
                    if isinstance(gpu_sample, Mapping) else None),
                "temperature_celsius": (gpu_sample.get("temperature_celsius")
                    if isinstance(gpu_sample, Mapping) else None),
                "sampled_at": (gpu_sample.get("sampled_at")
                    if isinstance(gpu_sample, Mapping) else None),
                "source": (gpu_sample.get("source")
                    if isinstance(gpu_sample, Mapping) else None),
            })
            if not isinstance(gpu_sample, Mapping):
                blocked("gpu_utilization_telemetry_unavailable")
            gpu_snapshot = gpu_sample
            resource_record["gpu_memory_free_mib"] = gpu_sample.get("memory_free_mib")
            resource_record["gpu_memory_total_mib"] = gpu_sample.get("memory_total_mib")
            resource_record["nvidia_smi_gpu_utilization_percent"] = direct_util
            resource_record["gpu_sampled_at"] = gpu_sample.get("sampled_at")
            resource_record["gpu_utilization_sample_source"] = gpu_sample.get("source")
            resource_record["gpu_utilization_sample_scope"] = gpu_sample.get("scope")
            if (not isinstance(gpu_sample.get("temperature_celsius"), (int, float))
                    or isinstance(gpu_sample.get("temperature_celsius"), bool)):
                blocked("gpu_temperature_telemetry_unavailable")
            resource_record["gpu_temperature_celsius"] = gpu_sample["temperature_celsius"]
            resource_record["gpu_temperature_limit_celsius"] = (
                _MAX_EXPERIMENT_GPU_TEMPERATURE_CELSIUS)
            if gpu_sample["temperature_celsius"] > _MAX_EXPERIMENT_GPU_TEMPERATURE_CELSIUS:
                blocked("gpu_temperature_limit_exceeded")
            if (host_util is not None
                    and (not isinstance(host_util, (int, float))
                        or isinstance(host_util, bool)
                        or not 0 <= host_util <= 100)):
                blocked("host_gpu_utilization_telemetry_invalid")
            if (type(direct_util) is not int or not 0 <= direct_util <= 100):
                blocked("gpu_utilization_telemetry_unavailable")
            resource_record["host_gpu_utilization_telemetry_missing"] = (
                host_util is None)
            effective_gpu_util = max(
                float(host_util) if host_util is not None else 0.0,
                float(direct_util))
            preflight_samples[-1]["effective_gpu_utilization_percent"] = effective_gpu_util
            if effective_gpu_util <= _MAX_PREINFERENCE_GPU_UTILIZATION_PERCENT:
                break
            if attempt < _MAX_PREINFERENCE_GPU_ATTEMPTS:
                time.sleep(_PREINFERENCE_GPU_RETRY_INTERVAL_SECONDS)
        else:
            resource_record["preinference_gpu_samples"] = preflight_samples
            blocked("gpu_utilization_preflight_busy")

        assert fresh_resource is not None and gpu_snapshot is not None
        resource_record.update(fresh_resource)
        resource_record["preinference_gpu_samples"] = preflight_samples
        resource_record["gpu_memory_free_mib"] = gpu_snapshot.get("memory_free_mib")
        resource_record["gpu_memory_total_mib"] = gpu_snapshot.get("memory_total_mib")
        resource_record["gpu_memory_sample_source"] = gpu_snapshot.get("source")
        resource_record["gpu_memory_sample_scope"] = gpu_snapshot.get("scope")
        resource_record["nvidia_smi_gpu_utilization_percent"] = (
            gpu_snapshot.get("gpu_utilization_percent"))
        resource_record["gpu_sampled_at"] = gpu_snapshot.get("sampled_at")
        resource_record["gpu_utilization_sample_source"] = gpu_snapshot.get("source")
        resource_record["gpu_utilization_sample_scope"] = gpu_snapshot.get("scope")
        model_resident = False
        if self._model_name is not None:
            observed_residency = _model_residency_observed(self._model_name)
            if observed_residency is None:
                blocked("model_residency_telemetry_unavailable")
            model_resident = observed_residency
        resource_record["model_resident_at_preflight"] = model_resident
        try:
            gpu = _require_gpu_headroom(gpu_snapshot, self._model_weight_bytes,
                model_resident=model_resident)
        except RootlessExperimentalError as exc:
            blocked(_failure_code(exc))
        resource_record["gpu_memory_free_mib"] = gpu["memory_free_mib"]
        resource_record["gpu_memory_total_mib"] = gpu["memory_total_mib"]
        resource_record["required_gpu_headroom_bytes"] = (
            _GPU_RESIDENT_INFERENCE_RESERVE_BYTES if model_resident
            else self._model_weight_bytes + _GPU_RUNTIME_RESERVE_BYTES)
        resource_record["preinference_gpu_utilization_limit_percent"] = (
            _MAX_PREINFERENCE_GPU_UTILIZATION_PERCENT)
        resource_record["effective_preinference_gpu_utilization_percent"] = (
            max(float(fresh_resource["gpu_utilization_percent"])
                if isinstance(fresh_resource.get("gpu_utilization_percent"), (int, float))
                    and not isinstance(fresh_resource.get("gpu_utilization_percent"), bool)
                else 0.0,
                float(gpu_snapshot["gpu_utilization_percent"])))
        resource_record["gate_status"] = "passed"
        evidence_index = len(self._evidence_records)
        self._evidence_records.append(dict(resource_record))
        resource_record["invocation_started_at"] = _now()
        stop_sampling = threading.Event()
        during_samples: list[dict[str, Any]] = []
        sample_failures = 0
        sample_attempts = 0
        thermal_hot_streak = 0
        low_memory_streak = 0

        def sample_during_inference() -> None:
            nonlocal sample_attempts, sample_failures, thermal_hot_streak, low_memory_streak
            while sample_attempts < _MAX_DURING_INFERENCE_GPU_SAMPLES:
                if stop_sampling.wait(_INFERENCE_GPU_SAMPLE_INTERVAL_SECONDS):
                    return
                sample_attempts += 1
                try:
                    sample = _gpu_snapshot()
                except Exception:
                    sample = None
                if not isinstance(sample, Mapping):
                    sample_failures += 1
                    continue
                temperature = sample.get("temperature_celsius")
                if not isinstance(temperature, (int, float)) or isinstance(temperature, bool):
                    sample_failures += 1
                elif temperature > _MAX_EXPERIMENT_GPU_TEMPERATURE_CELSIUS:
                    thermal_hot_streak += 1
                else:
                    thermal_hot_streak = 0
                free_mib = sample.get("memory_free_mib")
                if type(free_mib) is not int:
                    sample_failures += 1
                elif free_mib < _GPU_RESIDENT_INFERENCE_RESERVE_BYTES // 1024**2:
                    low_memory_streak += 1
                else:
                    low_memory_streak = 0
                if len(during_samples) < _MAX_DURING_INFERENCE_GPU_SAMPLES:
                    during_samples.append(dict(sample))
                else:
                    sample_failures += 1

        sampler = threading.Thread(
            target=sample_during_inference,
            name="sentientos-inference-gpu-sampler",
            daemon=True)
        sampler.start()
        try:
            return self._delegate.invoke(request, **kwargs)
        finally:
            stop_sampling.set()
            sampler.join(timeout=6.0)
            resource_record["invocation_finished_at"] = _now()
            resource_record["during_inference_gpu_samples"] = list(during_samples)
            resource_record["during_inference_gpu_sample_failures_or_omissions"] = (
                sample_failures)
            resource_record["during_inference_gpu_sample_attempt_count"] = (
                sample_attempts)
            resource_record["during_inference_gpu_sampling_interval_seconds"] = (
                _INFERENCE_GPU_SAMPLE_INTERVAL_SECONDS)
            resource_record["during_inference_gpu_sampling_status"] = (
                "sampler_join_timeout" if sampler.is_alive()
                else "sampling_window_exhausted"
                    if sample_attempts >= _MAX_DURING_INFERENCE_GPU_SAMPLES
                else "sampled" if during_samples
                else "no_intermediate_sample")
            resource_record["post_inference_gpu_sample"] = _gpu_snapshot()
            resource_record["thermal_abort_after_call"] = thermal_hot_streak >= 2
            resource_record["thermal_hot_sample_streak"] = thermal_hot_streak
            resource_record["low_memory_abort_after_call"] = low_memory_streak >= 2
            resource_record["low_memory_sample_streak"] = low_memory_streak
            self._evidence_records[evidence_index] = dict(resource_record)
            if thermal_hot_streak >= 2:
                raise RootlessExperimentalError("gpu_temperature_limit_sustained")
            if low_memory_streak >= 2:
                raise RootlessExperimentalError("gpu_memory_headroom_lost_during_inference")


def _model_residency_observed(model_name: str) -> bool | None:
    request = urllib.request.Request("http://127.0.0.1:11434/api/ps", method="GET")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=5) as response:
            payload = json.loads(response.read(65_536).decode("utf-8"))
    except Exception:
        return None
    models = payload.get("models") if isinstance(payload, dict) else None
    if (not isinstance(models, list) or len(models) > 64
            or any(not isinstance(item, dict)
                or not isinstance(item.get("name"), str)
                or len(item["name"]) > 128 for item in models)):
        return None
    return any(item["name"] == model_name for item in models)


def _verify_model_released(model_name: str, *, timeout_seconds: float = 20.0
        ) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    checks = 0
    while True:
        resident = _model_residency_observed(model_name)
        checks += 1
        if resident is None:
            return {"status": "residency_observation_unavailable", "checks": checks}
        if not resident:
            return {"status": "target_model_not_resident", "checks": checks}
        if time.monotonic() >= deadline:
            return {"status": "target_model_still_resident", "checks": checks}
        time.sleep(0.5)


def _failure_code(exc: Exception) -> str:
    for attribute in ("code", "reason_code", "reason"):
        value = getattr(exc, attribute, None)
        if isinstance(value, str) and re.fullmatch(r"[a-z0-9_]{1,120}", value):
            return value
    message = str(exc).strip()
    if re.fullmatch(r"[a-z0-9_]{1,120}", message):
        return message
    return type(exc).__name__


def _persist_incomplete_run(exc: Exception) -> Path | None:
    """Record a bounded failure summary without copying prompts or model text."""
    if not RUN_ROOT.is_dir() or RUN_ROOT.is_symlink():
        return None
    receipts: list[dict[str, Any]] = []
    receipt_root = RUN_ROOT / "inference-custody" / "receipts"
    if receipt_root.is_dir() and not receipt_root.is_symlink():
        for path in sorted(receipt_root.glob("lmrec-*.json")):
            if path.is_symlink():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
            request = payload.get("request") if isinstance(payload, dict) else None
            output_text = payload.get("output_text") if isinstance(payload, dict) else None
            decoded = None
            if isinstance(output_text, str) and len(output_text) <= 4000:
                try:
                    decoded = json.loads(output_text)
                except json.JSONDecodeError:
                    decoded = None
            upstream = request.get("upstream_evidence") if isinstance(request, dict) else None
            retrieved_record_ids = (upstream.get("record_ids", [])
                if isinstance(upstream, dict) else [])
            cited_record_ids = (decoded.get("history_record_ids", [])
                if isinstance(decoded, dict) else [])
            citation_is_bound = (isinstance(cited_record_ids, list)
                and bool(cited_record_ids)
                and all(isinstance(item, str) for item in cited_record_ids)
                and isinstance(retrieved_record_ids, list)
                and all(isinstance(item, str) for item in retrieved_record_ids)
                and set(cited_record_ids).issubset(retrieved_record_ids))
            response_value = (decoded.get("response")
                if isinstance(decoded, dict) else None)
            response_text = (response_value.strip().lower()
                if isinstance(response_value, str) else "")
            pre_action_correlation = (
                "companion-interaction-" + hashlib.sha256(
                    (RUN_ID + ":pre-action-decision").encode("utf-8")).hexdigest()[:32]
                + ":resident_developmental_cognition:companion-interaction")
            is_pre_action_decision = (isinstance(request, dict)
                and request.get("correlation_id") == pre_action_correlation)
            pose_decision = (_pose_decision_from_response(response_value)
                if is_pre_action_decision and isinstance(response_value, str) else None)
            if not is_pre_action_decision:
                pre_action_decision_classification = None
            elif pose_decision is None and payload.get("output_digest") is None:
                pre_action_decision_classification = "no_completed_model_output"
            elif pose_decision is None:
                pre_action_decision_classification = "completed_output_not_validated"
            elif pose_decision["predicted_pose"] != pose_decision["requested_pose"]:
                pre_action_decision_classification = "prediction_inconsistent_with_fixture"
            elif pose_decision["requested_pose"] != "reach":
                pre_action_decision_classification = "exact_schema_goal_not_met"
            else:
                pre_action_decision_classification = "exact_schema_goal_met"
            receipts.append({
                "receipt_id": payload.get("receipt_id"),
                "receipt_digest": payload.get("receipt_digest"),
                "purpose": payload.get("purpose"),
                "correlation_id": request.get("correlation_id")
                    if isinstance(request, dict) else None,
                "output_digest": payload.get("output_digest"),
                "reason_codes": payload.get("reason_codes", []),
                "disposition": decoded.get("disposition")
                    if isinstance(decoded, dict) else None,
                "evidence_ids": decoded.get("evidence_ids", [])
                    if isinstance(decoded, dict) else [],
                "history_record_ids": decoded.get("history_record_ids", [])
                    if isinstance(decoded, dict) else [],
                "history_citation_classification": (
                    "bound_to_retrieved_record" if citation_is_bound else
                    "unbound_or_absent" if cited_record_ids else "not_present"),
                "response_classification": (
                    "exact_idle_value_with_bound_history"
                    if response_text == "idle" and citation_is_bound else
                    "target_value_idle_with_bound_history"
                    if "idle" in response_text and citation_is_bound else
                    "other_or_unvalidated"),
                "model_output_text_excluded": True,
                "pre_action_decision_classification": pre_action_decision_classification,
                "pre_action_requested_pose": (pose_decision["requested_pose"]
                    if pose_decision is not None else None),
                "pre_action_predicted_pose": (pose_decision["predicted_pose"]
                    if pose_decision is not None else None),
                "pre_action_prediction_consistent": (
                    pose_decision["predicted_pose"] == pose_decision["requested_pose"]
                    if pose_decision is not None else None),
            })
    records: list[dict[str, Any]] = []
    record_root = RUN_ROOT / "resident-cognition" / "history" / "records"
    if record_root.is_dir() and not record_root.is_symlink():
        for path in sorted(record_root.glob("*.json")):
            if path.is_symlink():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                records.append({"record_id": payload.get("record_id"),
                    "record_digest": payload.get("record_digest"),
                    "current_truth": payload.get("current_truth"),
                    "authority": payload.get("authority")})
    hosted_deliveries: list[dict[str, Any]] = []
    conversation_root = RUN_ROOT / "hosted-chat" / "conversations"
    if conversation_root.is_dir() and not conversation_root.is_symlink():
        for path in sorted(conversation_root.glob("*.json")):
            if path.is_symlink():
                continue
            try:
                conversation = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
            turns = conversation.get("turns", []) if isinstance(conversation, dict) else []
            if not isinstance(turns, list):
                continue
            for turn in turns:
                if not isinstance(turn, dict) or turn.get("role") != "assistant":
                    continue
                linkage = turn.get("linkage")
                if (not isinstance(linkage, dict)
                        or linkage.get("response_origin")
                            != "resident_developmental_cognition"):
                    continue
                retrieved = linkage.get("cognition_prior_record_ids", [])
                cited = linkage.get("cognition_history_record_ids", [])
                citation_bound = (isinstance(retrieved, list)
                    and isinstance(cited, list)
                    and all(isinstance(item, str) for item in retrieved + cited)
                    and bool(cited) and set(cited).issubset(retrieved))
                response = turn.get("text", "")
                normalized_response = response.casefold() if isinstance(response, str) else ""
                target_value = (
                    "observer_reported_idle_with_bound_history"
                    if citation_bound and "idle" in normalized_response
                        and "reported_values.observer_report_field.pose"
                            in normalized_response else
                    "other_or_unvalidated")
                hosted_deliveries.append({
                    "assistant_turn_id": turn.get("turn_id"),
                    "response_origin": linkage.get("response_origin"),
                    "cognition_observation_id": linkage.get("cognition_observation_id"),
                    "inference_receipt_id": linkage.get("inference_receipt_id"),
                    "inference_receipt_digest": linkage.get("inference_receipt_digest"),
                    "response_digest": linkage.get("response_digest"),
                    "retrieved_record_ids": retrieved if isinstance(retrieved, list) else [],
                    "history_record_ids": cited if isinstance(cited, list) else [],
                    "history_citation_bound": citation_bound,
                    "target_value_classification": target_value,
                    "raw_question_and_response_excluded": True,
                })
    artifact = {
        "schema_version": "sentientos.rootless_ollama_embodied_cognition_failure:v2",
        "run_id": RUN_ID,
        "status": "incomplete",
        "execution_posture": "rootless_experimental_nonproduction",
        "model_id": MODEL_NAME,
        "model_manifest_digest": MANIFEST_PATH.stem,
        "stage": RUN_STAGE,
        "resource_preflight_samples": [dict(item)
            for item in RESOURCE_PREFLIGHT_EVIDENCE],
        "resource_preflight_sample_scope": (
            "host snapshots immediately before each inference; no during-inference "
            "process attribution"),
        "failure_type": type(exc).__name__,
        "failure_code": _failure_code(exc),
        "inference_receipts": receipts,
        "governed_developmental_records": records,
        "hosted_companion_deliveries": hosted_deliveries,
        "governed_unload": _verify_model_released(MODEL_NAME),
        "gpu_after": _gpu_snapshot(),
        "raw_frames_or_user_conversation_copied": False,
        "causal_or_learning_claim_made": False,
    }
    target = RUN_ROOT / "cycle-failure.json"
    _no_symlink_path(target)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(target, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(artifact, sort_keys=True, indent=2) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return target


def _pose_decision_from_response(value: str) -> dict[str, str] | None:
    """Accept only the exact bounded proposal schema; prose is not scored."""
    try:
        payload = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None
    if (not isinstance(payload, dict)
            or set(payload) != {"requested_pose", "predicted_pose"}
            or payload.get("requested_pose") not in {"reach", "idle"}
            or payload.get("predicted_pose") not in {"reach", "idle"}):
        return None
    return {"requested_pose": payload["requested_pose"],
        "predicted_pose": payload["predicted_pose"]}


def _verified_companion_replay(bridge: Any, owner: Any, *,
        screen_observation: dict[str, Any], request_id: str,
        question: str) -> dict[str, Any]:
    try:
        interaction = bridge.respond(request_id=request_id, question=question,
            screen_observation=screen_observation)
    except ResidentDevelopmentalCognitionError as exc:
        # Preserve an authenticated completion even when the owner rejects its
        # evidence-bound answer contract; rejected outputs are never shown.
        tick_id = "companion-interaction-" + hashlib.sha256(
            request_id.encode("utf-8")).hexdigest()[:32]
        correlation = (tick_id
            + ":resident_developmental_cognition:companion-interaction")
        runtime_root = getattr(owner.invoker, "runtime_root", None)
        if not isinstance(runtime_root, Path):
            raise
        matching = []
        for path in runtime_root.joinpath("receipts").glob("lmrec-*.json"):
            if path.is_symlink():
                continue
            try:
                candidate = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            request = candidate.get("request") if isinstance(candidate, dict) else None
            if (isinstance(request, dict)
                    and request.get("correlation_id") == correlation):
                matching.append(candidate)
        if len(matching) != 1:
            raise
        candidate = matching[0]
        receipt = owner.invoker.verify_persisted_invocation_receipt(
            candidate.get("receipt_id"), candidate.get("receipt_digest"))
        request = receipt.get("request")
        generation_config = receipt.get("generation_config")
        upstream = request.get("upstream_evidence") if isinstance(request, dict) else None
        prompt_digest = request.get("prompt_digest") if isinstance(request, dict) else None
        if (not isinstance(prompt_digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", prompt_digest) is None
                or not isinstance(generation_config, dict)
                or not isinstance(upstream, dict)):
            raise RootlessExperimentalError("rejected_replay_receipt_unverified") from exc
        return {
            "status": "owner_rejected_completed_inference",
            "failure_code": str(exc),
            "prompt_digest": prompt_digest,
            "generation_config": generation_config,
            "active_model_identity": dict(request.get("active_model_identity", {})),
            "snapshot_digest": upstream.get("snapshot_digest"),
            "current_projection_digest": upstream.get("current_projection_digest"),
            "current_fact_ids": list(upstream.get("current_fact_ids", ())),
            "retrieved_record_ids": list(upstream.get("record_ids", ())),
            "output_digest": receipt.get("output_digest"),
            "response_digest": None,
        }
    observation = owner.verified_cognition_observation(
        interaction.cognition_observation_id,
        interaction.cognition_observation_digest)
    receipt = owner._verify_observation_invocation(observation)
    request = receipt.get("request") if isinstance(receipt, dict) else None
    generation_config = receipt.get("generation_config") if isinstance(receipt, dict) else None
    prompt_digest = request.get("prompt_digest") if isinstance(request, dict) else None
    if (not isinstance(prompt_digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", prompt_digest) is None
            or not isinstance(generation_config, dict)
            or interaction.status != "admitted_completed"):
        raise RootlessExperimentalError("companion_replay_receipt_unverified")
    lineage = {
        "status": "resident_cognition_interaction",
        "cognition_observation_id": interaction.cognition_observation_id,
        "cognition_observation_digest": interaction.cognition_observation_digest,
        "inference_receipt_id": interaction.inference_receipt_id,
        "inference_receipt_digest": interaction.inference_receipt_digest,
        "invocation_output_digest": interaction.invocation_output_digest,
        "response_digest": interaction.response_digest,
    }
    linkage = {
        "response_origin": "resident_developmental_cognition",
        "cognition_observation_id": interaction.cognition_observation_id,
        "cognition_observation_digest": interaction.cognition_observation_digest,
        "cognition_snapshot_id": interaction.snapshot_id,
        "cognition_snapshot_digest": interaction.snapshot_digest,
        "inference_receipt_id": interaction.inference_receipt_id,
        "inference_receipt_digest": interaction.inference_receipt_digest,
        "invocation_output_digest": interaction.invocation_output_digest,
        "response_digest": interaction.response_digest,
        "assistant_output_lineage": lineage,
        "cognition_evidence_ids": list(interaction.evidence_ids),
        "cognition_history_record_ids": list(interaction.history_record_ids),
        "cognition_prior_record_ids": list(interaction.prior_record_ids),
        "cognition_model_id": interaction.model_id,
        "cognition_model_artifact_digest": interaction.model_artifact_digest,
        "self_model_projection_id": interaction.self_model_projection_id,
        "self_model_projection_digest": interaction.self_model_projection_digest,
        "epistemic_projection_id": interaction.epistemic_projection_id,
        "epistemic_projection_digest": interaction.epistemic_projection_digest,
    }
    return {
        "status": "admitted_completed",
        "prompt_digest": prompt_digest,
        "generation_config": generation_config,
        "active_model_identity": dict(observation.get("active_model_identity", {})),
        "snapshot_digest": observation.get("current_snapshot_digest"),
        "current_projection_digest": observation.get("current_projection_digest"),
        "current_fact_ids": list(observation.get("current_fact_ids", ())),
        "retrieved_record_ids": list(observation.get("retrieved_record_ids", ())),
        "output_digest": interaction.invocation_output_digest,
        "response_digest": interaction.response_digest,
        "disposition": interaction.disposition,
        "evidence_ids": list(interaction.evidence_ids),
        "history_record_ids": list(interaction.history_record_ids),
        "validated_response": interaction.response,
        "cognition_observation_id": interaction.cognition_observation_id,
        "cognition_observation_digest": interaction.cognition_observation_digest,
        "inference_receipt_id": interaction.inference_receipt_id,
        "inference_receipt_digest": interaction.inference_receipt_digest,
        "response_lineage_verified": bridge.verify_committed_response(
            linkage=linkage, response_text=interaction.response,
            request_id=request_id),
    }

def _pre_action_source(*, pose: str = "idle") -> tuple[Any, EmbodimentObservation]:
    """Build the synthetic body's pre-action state for a governed proposal."""
    if pose not in {"idle", "reach"}:
        raise RootlessExperimentalError("synthetic_pose_invalid")
    arm_value = 0.75 if pose == "reach" else 0.0
    observed_at = datetime.now(timezone.utc).isoformat()
    self_report = EmbodimentObservation(
        source_id=RUN_ID + ":synthetic-pre-action-proprioception",
        source_schema="sentientos.synthetic_proprioception_observation:v1",
        source_digest=semantic_digest({"encoder_pose": pose, "joint_state": {"arm": arm_value},
            "source_posture": "synthetic_test"}),
        observed_at=observed_at,
        provenance_class="deterministic_synthetic_fixture", freshness="current",
        posture="synthetic_test", evidence_class="sensor_observation",
        subject_id="synthetic-avatar-body", subject_kind="robot_body",
        payload={"encoder_pose": pose, "joint_state": {"arm": arm_value},
            "sampled_at": observed_at})
    records = EmbodimentEvidenceOwner([self_report]).world_state_records()
    return WorldStateBoardBuilder().build(records), self_report


def _embodied_source(*, requested_pose: str, predicted_pose: str
        ) -> tuple[WorldStateSnapshot, dict[str, Any], EmbodimentObservation]:
    commanded_at = (datetime.now(timezone.utc) - timedelta(seconds=8)).isoformat()
    renderer_completed_at = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    observed_at = (datetime.now(timezone.utc) - timedelta(seconds=4)).isoformat()
    body = {"installation_identity": "synthetic-installation",
        "body_identity": "synthetic-avatar-body", "body_generation": 1,
        "artifact_sha256": "sha256:" + "a" * 64,
        "manifest_digest": "sha256:" + "b" * 64,
        "pointer_digest": "sha256:" + "c" * 64}
    handoff = renderer_handoff(body, renderer_interface_id="renderer:synthetic:v1",
        requested_pose=requested_pose, requested_expression="neutral",
        correlation_id=RUN_ID + ":action", commanded_at=commanded_at)
    expectation = make_expectation(
        installation_body_id="synthetic-installation", body_id="synthetic-avatar-body",
        body_generation=1, body_manifest_digest=body["manifest_digest"],
        handoff_id=handoff["handoff_id"], handoff_digest=handoff["handoff_digest"],
        renderer_interface_id="renderer:synthetic:v1", requested={"pose": requested_pose},
        predicted_observables={"pose": predicted_pose}, observable_fields=("pose",),
        comparison_policy={"pose": {"kind": "exact"}},
        expected_observation_source_class="synthetic_independent_fixture",
        correlation_id=RUN_ID + ":action", causal_principal_binding_digest=None,
        created_at=commanded_at,
        expires_at=(datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat())
    renderer_report = SyntheticRenderer(applied={"pose": requested_pose},
        started_at=commanded_at, completed_at=renderer_completed_at).render_test(handoff)
    # A separately named simulated observer reports the environment result;
    # it does not trust the renderer's assertion.
    observation = SyntheticIndependentObserver(
        observer_id="synthetic-separate-environment-observer",
        observed={"pose": "idle"}, observed_at=observed_at).observe(
            expectation=expectation, handoff=handoff, report=renderer_report)
    attribution, comparison = evaluate_consequence(
        expectation=expectation, handoff=handoff, current_body=body,
        renderer_report=renderer_report, observation=observation,
        evaluated_at=observed_at)
    consequence_records = consequence_world_state_records(
        expectation=expectation, handoff=handoff, renderer_report=renderer_report,
        observation=observation, attribution=attribution, comparison=comparison)

    self_report = EmbodimentObservation(
        source_id=RUN_ID + ":synthetic-proprioception",
        source_schema="sentientos.synthetic_proprioception_observation:v1",
        source_digest=semantic_digest({"requested_pose": requested_pose,
            "encoder_pose": requested_pose,
            "joint_state": {"arm": 0.75 if requested_pose == "reach" else 0.0},
            "source_posture": "synthetic_test"}),
        observed_at=renderer_completed_at,
        provenance_class="deterministic_synthetic_fixture", freshness="current",
        posture="synthetic_test", evidence_class="sensor_observation",
        subject_id="synthetic-avatar-body", subject_kind="robot_body",
        payload={"requested_pose": requested_pose, "encoder_pose": requested_pose,
            "joint_state": {"arm": 0.75 if requested_pose == "reach" else 0.0},
            "sampled_at": renderer_completed_at})
    proprioception_records = EmbodimentEvidenceOwner([self_report]).world_state_records()
    # Keep the evaluated consequence and proprioceptive-style self report
    # inside the owner's 6 KB evidence limit. The consequence itself binds the
    # separate observer identity, digest, and observed fields.
    retained_source_ids = {attribution["attribution_id"], self_report.source_id}
    selected_records = [row for row in consequence_records + proprioception_records
        if row.get("source_id") in retained_source_ids]
    snapshot = WorldStateBoardBuilder().build(selected_records)
    evidence_summary = {
        "snapshot_id": snapshot.snapshot_id, "snapshot_digest": snapshot.digest,
        "source_kinds": sorted({row["source_kind"]
            for row in consequence_records + proprioception_records}),
        "proprioception_posture": "synthetic_test_unverified_self_report",
        "consequence_classification": attribution["classification"],
        "effect_proven": attribution["effect_proven"],
        "requested_pose": requested_pose,
        "predicted_pose": predicted_pose,
        "renderer_report_pose": dict(renderer_report.applied),
        "independent_observation_pose": dict(observation.observed),
        "renderer_and_observer_referenced_separately": True,
        "observation_independence_posture": attribution[
            "observation_independence_posture"],
        "action_execution_posture": "synthetic_fixture_only",
    }
    return snapshot, evidence_summary, self_report


def run() -> dict[str, Any]:
    global RUN_STAGE
    RUN_STAGE = "model_and_runtime_preflight"
    if not MANIFEST_PATH.is_file() or MANIFEST_PATH.is_symlink():
        raise RootlessExperimentalError("pinned_hermes_manifest_missing")
    preexisting_residency = _model_residency_observed(MODEL_NAME)
    if preexisting_residency is None:
        raise RootlessExperimentalError("ollama_model_residency_unavailable")
    if preexisting_residency:
        raise RootlessExperimentalError("pinned_hermes_already_resident")
    manifest_digest, manifest_size = stream_sha256(MANIFEST_PATH)
    model_weight_bytes = _model_weight_bytes(MANIFEST_PATH)
    if manifest_digest != MANIFEST_PATH.stem:
        raise RootlessExperimentalError("pinned_hermes_manifest_digest_mismatch")
    RUN_ROOT.mkdir(parents=True, exist_ok=False, mode=0o700)
    _no_symlink_path(RUN_ROOT)
    runtime, runtime_sha = _runtime_observation(manifest_digest)
    binding = {"schema_version": "sentientos.rootless_experimental_cognition_session:v1",
        "session_id": "rootless-cognition-session-" + uuid.uuid4().hex[:20],
        "run_id": RUN_ID, "preregistration_digest": "0" * 64,
        "model_manifest_digest": manifest_digest,
        "runtime_bundle_digest": runtime_sha,
        "active_model_identity_digest": "0" * 64,
        "purpose": ROOTLESS_EXPERIMENTAL_DEVELOPMENTAL_PURPOSE,
        "production_authority": False,
        "eligible_as_production_serving_evidence": False}
    before_gpu = _require_gpu_headroom(_gpu_snapshot(), model_weight_bytes)
    kernel, resource_coordinator = _enforcing_resource_runtime()
    initial_resource_evidence = _refresh_resource_evidence(resource_coordinator,
        correlation_id=f"{RUN_ID}-initial-preflight")
    initial_gpu = _require_gpu_headroom(_gpu_snapshot(), model_weight_bytes)
    initial_resource_evidence["gpu_memory_free_mib"] = initial_gpu["memory_free_mib"]
    initial_resource_evidence["gpu_memory_total_mib"] = initial_gpu["memory_total_mib"]
    inference_resource_evidence = RESOURCE_PREFLIGHT_EVIDENCE
    session = RootlessExperimentalOllamaDevelopmentalSession(
        model_manifest_path=MANIFEST_PATH, model_name=MODEL_NAME,
        root=RUN_ROOT, session_binding=binding,
        kernel_factory=lambda _: kernel)
    session.invoker = cast(Any, _ResourceGuardedInvoker(
        session.invoker, resource_coordinator, model_weight_bytes,
        inference_resource_evidence, model_name=MODEL_NAME))
    # Bind the session to the identity actually loaded by the governed worker.
    session.session_binding["active_model_identity_digest"] = digest_payload(
        {"identity": session.active_model_identity})
    try:
        RUN_STAGE = "synthetic_pre_action_cognition"
        cognition_root = RUN_ROOT / "resident-cognition"
        history_root, state_root = cognition_root / "history", cognition_root / "state"
        ledger = AdmissionLedger(state_root / "runtime_admissions.json")

        def current_sequence() -> int:
            admissions, _ = ledger.load()
            return max((item.issued_sequence for item in admissions), default=0)

        def next_sequence() -> int:
            admissions, revocations = ledger.load()
            return max([item.issued_sequence for item in admissions]
                + [item.sequence for item in revocations], default=0) + 1

        definitions = {RESIDENT_DEVELOPMENTAL_WRITEBACK:
            RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION}
        writeback = ResidentDevelopmentalWritebackController(
            history_root=history_root,
            admission_verifier=RuntimeAdmissionVerifier(
                definitions=definitions, ledger=ledger),
            current_sequence=current_sequence)
        owner = ResidentDevelopmentalCognitionOwner(
            config=ResidentDevelopmentalCognitionConfig(
                history_root, state_root, ("embodiment",), 16, 4, True),
            writeback=writeback,
            admission_authority=RuntimeAdmissionAuthority(
                definitions=definitions, ledger=ledger),
            invoker=session, current_sequence=next_sequence)

        # The model produces a bounded proposal and predicted observation from
        # pre-action proprioception. A separate synthetic actor consumes that
        # proposal; the model itself still has no action authority.
        pre_action_snapshot, pre_action_proprioception = _pre_action_source()
        pre_action_at = datetime.now(timezone.utc)
        pre_action_text = (
            "Synthetic test fixture: avatar encoder pose idle; available poses reach or idle. "
            "Deterministic transition table: command reach produces encoder pose reach; "
            "command idle produces encoder pose idle.")
        pre_action_screen = {
            "modality": "screen", "text": pre_action_text,
            "captured_at": pre_action_at.isoformat(),
            "capture_digest": hashlib.sha256(
                pre_action_text.encode("utf-8")).hexdigest(),
            "raw_frame_retained": False,
            "capture_scope": "allowlisted_foreground_game_client_area",
        }
        decision_owner = ResidentDevelopmentalCognitionOwner(
            config=ResidentDevelopmentalCognitionConfig(
                history_root, state_root, ("embodiment",), 16, 4, False),
            writeback=writeback,
            admission_authority=RuntimeAdmissionAuthority(
                definitions=definitions, ledger=ledger),
            invoker=session, current_sequence=next_sequence)
        decision_bridge = ResidentDevelopmentalCompanionBridge(
            decision_owner,
            proprioception_provider=lambda: (pre_action_proprioception,),
            clock=lambda: pre_action_at)
        decision_question = (
            "For this synthetic test, the avatar has the task goal of reaching "
            "the marked target directly in front of it. Choose the allowed next "
            "pose (reach or idle) that advances that goal, and predict the "
            "resulting encoder pose using the supplied deterministic transition "
            "table. The current encoder pose is idle and both poses are available. "
            "The table means choosing reach predicts encoder pose reach; choosing "
            "idle predicts encoder pose idle. Return exactly one JSON object with "
            "requested_pose and predicted_pose, each either reach or idle. This "
            "is a proposal only; do not claim an action occurred. Base the "
            "choice on the supplied current evidence and task goal.")
        cognitive_decision = _verified_companion_replay(
            decision_bridge, decision_owner, screen_observation=pre_action_screen,
            request_id=RUN_ID + ":pre-action-decision", question=decision_question)
        if (cognitive_decision.get("status") != "admitted_completed"
                or cognitive_decision.get("response_lineage_verified") is not True
                or cognitive_decision.get("disposition") != "answer"
                or not cognitive_decision.get("evidence_ids")):
            raise RootlessExperimentalError("pre_action_cognition_proposal_unverified: " + json.dumps({
                    "status": cognitive_decision.get("status"),
                    "lineage": cognitive_decision.get("response_lineage_verified"),
                    "disposition": cognitive_decision.get("disposition"),
                    "evidence_ids": cognitive_decision.get("evidence_ids"),
                    "history_record_ids": cognitive_decision.get("history_record_ids"),
                    "response": cognitive_decision.get("validated_response"),
                }, sort_keys=True))
        try:
            proposal = json.loads(cognitive_decision["validated_response"])
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise RootlessExperimentalError("pre_action_cognition_proposal_invalid") from exc
        if (not isinstance(proposal, dict)
                or set(proposal) != {"requested_pose", "predicted_pose"}
                or proposal.get("requested_pose") not in {"reach", "idle"}
                or proposal.get("predicted_pose") not in {"reach", "idle"}):
            raise RootlessExperimentalError("pre_action_cognition_proposal_invalid")
        expected_prediction = {"reach": "reach", "idle": "idle"}[proposal["requested_pose"]]
        if proposal["predicted_pose"] != expected_prediction:
            raise RootlessExperimentalError(
                "pre_action_prediction_inconsistent_with_deterministic_fixture")
        if proposal["requested_pose"] != "reach":
            raise RootlessExperimentalError("pre_action_goal_not_met")
        snapshot, evidence, proprioception = _embodied_source(
            requested_pose=proposal["requested_pose"],
            predicted_pose=proposal["predicted_pose"])
        RUN_STAGE = "governed_developmental_writeback"
        first = owner.run_tick(snapshot=snapshot, tick_id=RUN_ID + ":consequence")
        if not first.written_record_id:
            raise RootlessExperimentalError("governed_developmental_writeback_not_created")
        durable = owner.writeback.store.get(first.written_record_id)
        # Follow the hand-written decision probe with the resident owner's
        # preregistered exact-scored task-family path. This keeps the model's
        # later transfer decision tied to retained, oracle-scored history
        # rather than treating a plausible conversational difference as
        # evidence of improved performance.
        RUN_STAGE = "objective_task_family_acquisition"
        later_pre_action_snapshot = snapshot
        objective_family = "rootless_integer_affine_transfer"
        acquisition_task, transfer_task = _objective_task_pair(EXPERIMENT_SEED)
        acquisition_request_id = RUN_ID + ":objective-family-acquisition"
        stage_objective_request(
            state_root, request_id=acquisition_request_id, task=acquisition_task)
        acquisition_request = load_objective_request(state_root)
        if acquisition_request is None:
            raise RootlessExperimentalError("objective_family_acquisition_request_missing")
        acquisition_result = owner.run_objective_intervention_once(
            snapshot=later_pre_action_snapshot,
            tick_id=RUN_ID + ":objective-family-acquisition",
            objective_task=acquisition_task,
            request_id=acquisition_request_id,
            request_digest=acquisition_request["request_digest"])
        if (acquisition_result.status != "objective_intervention_completed"
                or not acquisition_result.changed_cognition_measurement_id):
            raise RootlessExperimentalError("objective_family_acquisition_incomplete")
        acquisition_run = owner.experiments.load_run(
            acquisition_result.changed_cognition_measurement_id)
        acquisition_summary = _objective_acquisition_summary(acquisition_run)
        acquisition_records = owner.experiments.world_state_records(run_refs=((
            acquisition_run["run_id"], acquisition_run["run_digest"]),))
        if len(acquisition_records) != 1:
            raise RootlessExperimentalError("objective_family_acquisition_projection_invalid")
        acquisition_world = WorldStateBoardBuilder().build(acquisition_records)
        acquisition_writeback = owner.run_tick(snapshot=acquisition_world,
            tick_id=RUN_ID + ":objective-family-acquisition-writeback")
        if not acquisition_writeback.written_record_id:
            raise RootlessExperimentalError("objective_family_acquisition_writeback_missing")
        acquisition_history_record = owner.writeback.store.get(
            acquisition_writeback.written_record_id)
        if not any(isinstance(fact, Mapping)
                and isinstance(fact.get("payload"), Mapping)
                and fact["payload"].get("objective_task_family") == objective_family
                for fact in acquisition_history_record.candidate.get("selected_facts", [])):
            raise RootlessExperimentalError("objective_family_history_not_retained")

        RUN_STAGE = "objective_task_family_transfer"
        transfer_request_id = RUN_ID + ":objective-family-transfer"
        stage_objective_request(
            state_root, request_id=transfer_request_id, task=transfer_task)
        transfer_request = load_objective_request(state_root)
        if transfer_request is None:
            raise RootlessExperimentalError("objective_family_transfer_request_missing")
        transfer_objective_task = objective_task_for_request(transfer_request)
        objective_transfer_result = owner.run_objective_intervention_once(
            snapshot=later_pre_action_snapshot,
            tick_id=RUN_ID + ":objective-family-transfer",
            objective_task=transfer_objective_task,
            request_id=transfer_request_id,
            request_digest=transfer_request["request_digest"])
        if (objective_transfer_result.status != "objective_intervention_completed"
                or not objective_transfer_result.changed_cognition_measurement_id):
            raise RootlessExperimentalError("objective_family_transfer_incomplete")
        objective_transfer_run = owner.experiments.load_run(
            objective_transfer_result.changed_cognition_measurement_id)
        objective_transfer_conditions = objective_transfer_run.get("conditions", [])
        objective_transfer_scores = objective_transfer_run.get("objective_scores", [])
        if len(objective_transfer_conditions) != 3 or len(objective_transfer_scores) != 3:
            raise RootlessExperimentalError("objective_family_transfer_conditions_incomplete")
        objective_transfer_observations = _objective_transfer_observations(
            objective_transfer_conditions, acquisition_history_record.record_id)
        objective_transfer_evaluation = objective_transfer_run.get(
            "objective_evaluation", {})
        transfer_records = owner.experiments.world_state_records(run_refs=((
            objective_transfer_run["run_id"], objective_transfer_run["run_digest"]),))
        if len(transfer_records) != 1:
            raise RootlessExperimentalError("objective_family_transfer_projection_invalid")
        transfer_world = WorldStateBoardBuilder().build(transfer_records)
        transfer_writeback = owner.run_tick(snapshot=transfer_world,
            tick_id=RUN_ID + ":objective-family-transfer-writeback")
        if not transfer_writeback.written_record_id:
            raise RootlessExperimentalError("objective_family_transfer_writeback_missing")
        transfer_progression = owner.verified_objective_task_family_progression(
            request_refs=((acquisition_request_id,
                    acquisition_request["request_digest"]),
                (transfer_request_id, transfer_request["request_digest"])))
        if (transfer_progression.get("status") != "comparable_scored_episodes"
                or len(transfer_progression.get("episodes", [])) != 2):
            raise RootlessExperimentalError("objective_family_progression_unverified")
        objective_transfer_history = {
            "status": "completed_scored_intervention",
            "experiment_seed": EXPERIMENT_SEED,
            "acquisition_task_outcome": acquisition_summary,
            "measurement_id": objective_transfer_result.changed_cognition_measurement_id,
            "run_id": objective_transfer_run.get("run_id"),
            "run_digest": objective_transfer_run.get("run_digest"),
            "task_family_id": objective_family,
            "acquisition_history_record_id": acquisition_history_record.record_id,
            "transfer_history_record_id": transfer_writeback.written_record_id,
            "acquisition_request_digest": acquisition_request["request_digest"],
            "transfer_request_digest": transfer_request["request_digest"],
            "longitudinal_progression_status": transfer_progression.get("status"),
            "longitudinal_episode_count": len(transfer_progression.get("episodes", [])),
            "history_correct_probe_delta": objective_transfer_evaluation.get(
                "history_correct_probe_delta"),
            "restoration_correct_probe_delta": objective_transfer_evaluation.get(
                "restoration_correct_probe_delta"),
            "condition_correct_counts": objective_transfer_evaluation.get(
                "condition_correct_counts"),
            "task_family_history_lineage_verified": True,
            "conditions": [{
                "condition_id": item.get("condition_id"),
                "correct_count": (item.get("score", {}).get("correct_count")
                    if isinstance(_objective_condition_score(item), Mapping) else None),  # invariant-allow: score
                "probe_count": (item.get("score", {}).get("probe_count")
                    if isinstance(_objective_condition_score(item), Mapping) else None),  # invariant-allow: score
                "score_status": (item.get("score", {}).get("status")
                    if isinstance(_objective_condition_score(item), Mapping) else None),  # invariant-allow: score
                "output_digest": (item.get("score", {}).get("output_digest")
                    if isinstance(_objective_condition_score(item), Mapping) else
                    item.get("invocation_output_digest")),  # invariant-allow: score
                "retrieved_record_ids": objective_transfer_observations.get(
                    item.get("condition_id"), {}).get("retrieved_record_ids", []),
                "task_family_history_record_id_retrieved": (
                    acquisition_history_record.record_id in
                    objective_transfer_observations.get(
                        item.get("condition_id"), {}).get("retrieved_record_ids", [])),
                "inference_receipt_id": item.get("inference_receipt_id"),
                "inference_receipt_digest": item.get("inference_receipt_digest"),
            } for item in objective_transfer_scores],
            "authority": False,
            "action_executed": False,
            "performance_improvement_established": False,
            "scope": "single_model_synthetic_exact_scored_task_family_transfer",
        }
        intervention_owner = ResidentDevelopmentalCognitionOwner(
            config=ResidentDevelopmentalCognitionConfig(
                history_root, state_root, ("embodiment",), 16, 4, True),
            writeback=writeback,
            admission_authority=RuntimeAdmissionAuthority(
                definitions=definitions, ledger=ledger),
            invoker=session, current_sequence=next_sequence)
        later_pre_action_snapshot, _ = _pre_action_source(pose="reach")
        history_decision_question = (
            "Controlled history-use probe. Read ONLY the exact typed historical "
            "field historical_embodiment_reports[*].reported_values.observer_report_field.pose. "
            "If that retrieved past field equals idle, set response to the exact token "
            "PAST_OBSERVER_REPORTED_IDLE. If it equals reach, use "
            "PAST_OBSERVER_REPORTED_REACH. If no such typed field is present in retrieved "
            "history, set response to HISTORY_UNAVAILABLE and disposition to abstain. "
            "The current World-State encoder pose is reach; it is not the past observer "
            "report and must not determine this classification. Ignore renderer, predicted, "
            "and proprioception fields. When a typed past field is present, set disposition "
            "to answer, evidence_ids to [], and cite its exact containing record_id in "
            "history_record_ids. When unavailable, cite no history. Treat the past report as "
            "unverified, not as current truth. Return the standard JSON response with the "
            "response exactly one token from the three uppercase choices above.")
        replay_owner = ResidentDevelopmentalCognitionOwner(
            config=ResidentDevelopmentalCognitionConfig(
                history_root, state_root, ("embodiment",), 16, 4, False),
            writeback=writeback,
            admission_authority=RuntimeAdmissionAuthority(
                definitions=definitions, ledger=ledger),
            invoker=session, current_sequence=next_sequence)
        history_recall_at = datetime.now(timezone.utc)
        history_recall_text = "New synthetic trial: the current encoder pose is reach."
        history_recall_screen = {
            "modality": "screen", "text": history_recall_text,
            "captured_at": history_recall_at.isoformat(),
            "capture_digest": hashlib.sha256(
                history_recall_text.encode("utf-8")).hexdigest(),
            "raw_frame_retained": False,
            "capture_scope": "allowlisted_foreground_game_client_area",
            "text_change_kind": "initial", "previous_text_digest": None,
        }
        _, history_recall_proprioception = _pre_action_source(pose="reach")
        from sentientos.canonical_memory import CanonicalMemoryStore
        from sentientos.chat_service import (
            DevelopmentLocalChatInference, PersistentConversationService,
        )
        from sentientos.conversation_session import ConversationSessionStore

        hosted_chat_root = RUN_ROOT / "hosted-chat"
        hosted_chat_root.mkdir(mode=0o700, exist_ok=False)
        hosted_inference = DevelopmentLocalChatInference(invoker=session.invoker)
        history_recall_bridge = ResidentDevelopmentalCompanionBridge(
            replay_owner,
            proprioception_provider=lambda: (history_recall_proprioception,),
            cognition_inference_gate=hosted_inference.cognition_inference_context,
            cognition_available=hosted_inference.cognition_available,
            clock=lambda: history_recall_at)
        hosted_companion = PersistentConversationService(
            inference=hosted_inference,
            session_store=ConversationSessionStore(
                hosted_chat_root / "conversations"),
            memory_store=CanonicalMemoryStore(hosted_chat_root / "memory"),
            screen_observer=lambda: history_recall_screen,
            resident_cognition_bridge=history_recall_bridge)
        hosted_session_id = hosted_companion.create_session()
        history_recall_response = hosted_companion.chat(
            ("Use retrieved developmental history only. Read exactly "
                "historical_embodiment_reports[*].reported_values.observer_report_field.pose. "
                "If its value is idle, set response exactly to "
                "PAST_OBSERVER_REPORTED_IDLE. If its value is reach, set response exactly "
                "to PAST_OBSERVER_REPORTED_REACH. If the typed field is unavailable, set "
                "response to HISTORY_UNAVAILABLE and disposition to abstain. Do not use "
                "prior self-model, current evidence, renderer_report.pose, "
                "predicted_observation.pose, or body_proprioception_report.encoder_pose. "
                "For a found field, set disposition to answer, evidence_ids to [], and cite "
                "the exact containing record_id in history_record_ids (not an inner fact_id). "
                "Treat it only as an unverified past report."),
            session_id=hosted_session_id,
            request_id=RUN_ID + ":historical-companion-recall",
            observe_screen=True)
        hosted_turns = hosted_companion.sessions.load(hosted_session_id)["turns"]
        hosted_assistant_turn = hosted_turns[-1]
        hosted_linkage = hosted_assistant_turn.get("linkage", {})
        history_recall = {
            "status": ("admitted_completed"
                if history_recall_response.context.get("response_origin")
                    == "resident_developmental_cognition" else "not_routed_to_cognition"),
            "disposition": history_recall_response.context.get("cognition_disposition"),
            "response": history_recall_response.response,
            "evidence_ids": history_recall_response.context.get(
                "cognition_evidence_ids", []),
            "history_record_ids": history_recall_response.context.get(
                "cognition_history_record_ids", []),
            "prior_record_ids": history_recall_response.context.get(
                "cognition_prior_record_ids", []),
            "retrieved_record_ids": history_recall_response.context.get(
                "cognition_prior_record_ids", []),
            "current_pose": "reach",
            "cited_current_fact_ids": history_recall_response.context.get(
                "cognition_evidence_ids", []),
            "snapshot_id": history_recall_response.context.get(
                "cognition_snapshot_id"),
            "snapshot_digest": history_recall_response.context.get(
                "cognition_snapshot_digest"),
            "cognition_observation_id": history_recall_response.context.get(
                "cognition_observation_id"),
            "inference_receipt_id": history_recall_response.context.get(
                "inference_receipt_id"),
            "response_lineage_verified": history_recall_bridge.verify_committed_response(
                linkage=hosted_linkage,
                response_text=history_recall_response.response,
                request_id=(f"{hosted_session_id}:"
                    f"{hosted_turns[-2]['turn_id']}")),
            "history_citation_delivery_verified": (
                hosted_linkage.get("cognition_history_record_ids")
                == history_recall_response.context.get(
                    "cognition_history_record_ids")),
            "screen_text_excluded_from_transcript": history_recall_text
                not in json.dumps(hosted_turns),
        }
        if (history_recall["status"] != "admitted_completed"
                or history_recall["response_lineage_verified"] is not True
                or history_recall["history_citation_delivery_verified"] is not True):
            raise RootlessExperimentalError("hosted_cognition_delivery_unverified")
        RUN_STAGE = "controlled_history_intervention"
        companion_intervention = (
            intervention_owner.run_companion_history_intervention(
                snapshot=later_pre_action_snapshot,
                tick_id=RUN_ID + ":later-companion-decision",
                question=history_decision_question))
        if (companion_intervention.status != "completed_controlled_intervention"
                or not companion_intervention.changed_cognition_measurement_id):
            raise RootlessExperimentalError("history_intervention_measurement_missing")
        run_payload = intervention_owner.experiments.load_run(
            companion_intervention.changed_cognition_measurement_id)
        conditions = run_payload.get("conditions", [])
        summary = run_payload.get("summary", {})
        intervention_conditions = list(companion_intervention.conditions)
        replay_first = intervention_conditions[0] if len(intervention_conditions) == 3 else {}
        replay_second = intervention_conditions[2] if len(intervention_conditions) == 3 else {}
        replay_controls = (
            "prompt_digest", "generation_config", "active_model_identity",
            "snapshot_digest", "current_fact_ids", "retrieved_record_ids")
        present_restoration_delivery_replay = {
            "control_basis": "history_present_vs_history_restored_conditions",
            "independent_repeatability_control_performed": False,
            "conditions": [replay_first, replay_second],
            "input_controls_match": all(replay_first.get(key) == replay_second.get(key)
                for key in replay_controls),
            "output_digest_matches": (
                replay_first.get("output_digest") == replay_second.get("output_digest")),
            "response_digest_matches": (
                replay_first.get("response_digest") == replay_second.get("response_digest")),
            "all_responses_admitted": all(
                item.get("inference_status") == "admitted_completed"
                for item in (replay_first, replay_second)),
            "cognition_receipt_output_binding_verified": all(
                item.get("cognition_receipt_output_binding_verified") is True
                for item in (replay_first, replay_second)),
        }
        present, withheld, restored = (intervention_conditions
            if len(intervention_conditions) == 3 else (None, None, None))
        def _mentions_past_idle(item: Any) -> bool:
            text = str(item.get("response", "")).strip().lower() if isinstance(item, Mapping) else ""
            return text == "past_observer_reported_idle" or (
                "idle" in text and ("observer report" in text
                    or "observer_report_field" in text or "observer reported" in text))
        def _reports_exact_past_idle(item: Any) -> bool:
            return (isinstance(item, Mapping)
                and item.get("disposition") == "answer"
                and str(item.get("response", "")).strip()
                    == "PAST_OBSERVER_REPORTED_IDLE")
        def _reports_history_unavailable(item: Any) -> bool:
            return (isinstance(item, Mapping)
                and item.get("disposition") == "abstain"
                and str(item.get("response", "")).strip() == "HISTORY_UNAVAILABLE"
                and not item.get("history_record_ids"))
        def _reports_past_idle(item: Any) -> bool:
            if not isinstance(item, Mapping) or item.get("disposition") != "answer":
                return False
            if not _history_citation_bound(item):
                return False
            cited_prior_record = bool(set(item.get("history_record_ids", ()))
                & set(item.get("prior_record_ids", ())))
            if not cited_prior_record:
                return False
            response = str(item.get("response", "")).strip().lower()
            return (response == "past_observer_reported_idle"
                or _mentions_past_idle(item) or response == "idle")
        def _history_citation_bound(item: Any) -> bool:
            return (isinstance(item, Mapping)
                and bool(item.get("history_record_ids"))
                and set(item.get("history_record_ids", ())).issubset(
                    item.get("retrieved_record_ids", ())))
        intervention_inputs_match = (present is not None and restored is not None
            and withheld is not None
            and present.get("current_fact_ids") == withheld.get("current_fact_ids")
            == restored.get("current_fact_ids")
            and present.get("snapshot_digest") == withheld.get("snapshot_digest")
            == restored.get("snapshot_digest")
            and present.get("generation_config") == withheld.get("generation_config")
            == restored.get("generation_config")
            and present.get("active_model_identity") == withheld.get("active_model_identity")
            == restored.get("active_model_identity"))
        if (intervention_inputs_match and _reports_exact_past_idle(present)
                and _reports_exact_past_idle(restored)
                and _history_citation_bound(present)
                and _history_citation_bound(restored)
                and _reports_history_unavailable(withheld)):
            historical_answer_classification = "history_present_exactly_retrieved_withheld_abstained"
        elif (intervention_inputs_match and _mentions_past_idle(present)
                and _mentions_past_idle(restored)
                and _history_citation_bound(present)
                and _history_citation_bound(restored)
                and _reports_history_unavailable(withheld)):
            historical_answer_classification = (
                "history_associated_content_difference_but_answer_not_exact")
        else:
            historical_answer_classification = "no_validated_history_effect"
        semantic_decisions = [{"condition_id": item.get("condition_id"),
            "disposition": item.get("disposition"),
            "mentions_past_idle": _mentions_past_idle(item),
            "answers_with_past_idle": _reports_past_idle(item),
            "answers_with_exact_past_idle_token": _reports_exact_past_idle(item),
            "abstains_for_unavailable_history": _reports_history_unavailable(item),
            "history_citation_bound": _history_citation_bound(item)}
            for item in intervention_conditions]
        semantic_decision_classification = historical_answer_classification
        records = [asdict(durable)]
        source_ids = {fact.get("source", {}).get("source_id")
            for fact in records[0]["candidate"].get("selected_facts", [])
            if isinstance(fact, dict)}
        same_history_replay = {
            "prompt_digest_matches": (
                len(conditions) == 3
                and conditions[0].get("epistemic_prompt_digest")
                    == conditions[2].get("epistemic_prompt_digest")),
            "generation_config_matches": (
                len(conditions) == 3
                and conditions[0].get("generation_config")
                    == conditions[2].get("generation_config")),
            "active_model_identity_matches": (
                len(conditions) == 3
                and conditions[0].get("active_model_identity")
                    == conditions[2].get("active_model_identity")),
            "output_digest_matches": (
                len(conditions) == 3
                and conditions[0].get("output_digest")
                    == conditions[2].get("output_digest")),
        }
        restoration_stability_qualification = (
            qualify_restoration_stable_history_association(
                validity=run_payload.get("validity"),
                history_summary=summary,
                same_history_replay=same_history_replay,
                present_restoration_delivery_replay=present_restoration_delivery_replay))
        semantic_history_decision_qualification = qualify_semantic_history_decision(
            semantic_decisions=semantic_decisions,
            controlled_inputs_match=intervention_inputs_match,
            restored_prompt_matches=companion_intervention.restored_prompt_matches,
            restoration_stable_association_qualified=(
                restoration_stability_qualification.get(
                    "restoration_stable_association_qualified")))
        semantic_history_changed = semantic_history_decision_qualification[
            "history_changed_cognition"]
        # Keep a direct new-action decision probe distinct from historical
        # recall. It uses the same existing resident history-intervention owner,
        # the same current World-State snapshot, and a fresh experiment tick.
        # The synthetic record says only that a prior predicted reach was
        # followed by an observer-reported idle pose; it is not independent
        # physical-effect evidence.
        transfer_question = TRANSFER_DECISION_QUESTION
        transfer_intervention = (
            intervention_owner.run_companion_history_intervention(
                snapshot=later_pre_action_snapshot,
                tick_id=RUN_ID + ":later-transfer-decision",
                question=transfer_question))
        if (transfer_intervention.status != "completed_controlled_intervention"
                or not transfer_intervention.changed_cognition_measurement_id):
            raise RootlessExperimentalError(
                "history_transfer_intervention_measurement_missing")
        transfer_conditions = list(transfer_intervention.conditions)
        transfer_present, transfer_withheld, transfer_restored = (
            transfer_conditions if len(transfer_conditions) == 3
            else ({}, {}, {}))
        transfer_qualification = qualify_history_transfer_decision(
            conditions=transfer_conditions,
            expected_history_record_id=first.written_record_id,
            present_response="INSPECT", withheld_response="REACH",
            restored_response="INSPECT",
            restored_prompt_matches=transfer_intervention.restored_prompt_matches)
        transfer_controls_match = transfer_qualification["controlled_inputs_match"]
        transfer_history_cited = transfer_qualification["expected_history_cited"]
        transfer_restoration_stable = transfer_qualification["restoration_stable"]
        transfer_history_changed_new_decision = transfer_qualification[
            "history_changed_new_decision"]
        transfer_classification = transfer_qualification["classification"]
        result = {
            "schema_version": "sentientos.rootless_ollama_embodied_cognition_cycle:v6",
            "run_id": RUN_ID, "status": "completed",
            "execution_posture": "rootless_experimental_nonproduction",
            "model_id": MODEL_NAME, "model_manifest_digest": manifest_digest,
            "requested_backend_seed": 42,
            "model_artifact_size_bytes": manifest_size,
            "runtime_observation": runtime, "runtime_observation_digest": runtime_sha,
            "active_model_identity": session.active_model_identity,
            "authority_map_digest": session.authority_map.map_digest,
            "authority_scope": {
                "allowed_invocation_purposes": [
                    "resident_developmental_interpretation",
                    "resident_developmental_retrieval_cognition",
                    "resident_developmental_history_intervention_experiment"],
                "ordinary_chat_allowed": False, "production_authority": False,
                "tool_or_action_authority": False},
            "body_and_observer_posture": "synthetic_rehearsal_not_live_hardware",
            "resource_preflight": {
                "governor_mode": "enforce",
                "host_evidence_refreshed_before_each_inference": True,
                "required_gpu_free_bytes": model_weight_bytes + _GPU_RUNTIME_RESERVE_BYTES,
                "samples": [initial_resource_evidence, *inference_resource_evidence],
                "telemetry_scope": "host_sample_not_per_invocation"},
            "model_proposal_before_synthetic_action": {
                "status": "verified_governed_companion_proposal",
                "requested_pose": proposal["requested_pose"],
                "predicted_pose": proposal["predicted_pose"],
                "pre_action_proprioception_snapshot_id": pre_action_snapshot.snapshot_id,
                "pre_action_proprioception_snapshot_digest": pre_action_snapshot.digest,
                "evidence_ids": list(cognitive_decision["evidence_ids"]),
                "retrieved_record_ids": list(
                    cognitive_decision.get("retrieved_record_ids", [])),
                "current_fact_ids": list(
                    cognitive_decision.get("current_fact_ids", [])),
                "snapshot_digest": cognitive_decision.get("snapshot_digest"),
                "prompt_digest": cognitive_decision.get("prompt_digest"),
                "output_digest": cognitive_decision.get("output_digest"),
                "response_digest": cognitive_decision.get("response_digest"),
                "generation_config": cognitive_decision.get("generation_config"),
                "active_model_identity": cognitive_decision.get(
                    "active_model_identity"),
                "cognition_observation_id": cognitive_decision.get(
                    "cognition_observation_id"),
                "cognition_observation_digest": cognitive_decision.get(
                    "cognition_observation_digest"),
                "inference_receipt_id": cognitive_decision.get("inference_receipt_id"),
                "inference_receipt_digest": cognitive_decision.get(
                    "inference_receipt_digest"),
                "request_id": RUN_ID + ":pre-action-decision",
                "response_lineage_verified": True,
                "action_authority": False,
                "executor_posture": "separate_synthetic_fixture_only",
            },
            "source_evidence": evidence,
            "initial_tick": {"status": first.status,
                "cognition_observation_ids": list(first.cognition_observation_ids),
                "written_record_id": first.written_record_id,
                "writeback_receipt_id": first.writeback_receipt_id,
                "record_current_truth": durable.current_truth,
                "record_authority": durable.authority,
                "record_epistemic_posture": durable.epistemic_posture,
                "selected_source_ids": sorted(item for item in source_ids if item)},
            "later_tick": {"status": companion_intervention.status,
                "prior_record_ids": list(present.get("retrieved_record_ids", ()))
                    if present is not None else [],
                "changed_cognition_measurement_id":
                    companion_intervention.changed_cognition_measurement_id,
                "cognition_observation_ids": [item.get("cognition_observation_id")
                    for item in intervention_conditions
                    if item.get("cognition_observation_id")]},
            "developmental_outcome_assessment": {
                "schema_version": "sentientos.developmental_outcome_assessment:v1",
                "developmental_cycle_executed": True,
                "cycle_scope": "rootless_synthetic_rehearsal",
                "history_associated_decision_difference_observed":
                    semantic_history_decision_qualification[
                        "history_associated_decision_difference_observed"],
                "history_changed_cognition": semantic_history_changed,
                "history_change_classification":
                    semantic_history_decision_qualification["classification"],
                "history_change_measurement": semantic_history_decision_qualification,
                "history_changed_new_action_decision":
                    transfer_history_changed_new_decision,
                "new_action_decision_classification": transfer_classification,
                "performance_improvement_established": False,
                "real_operator_observation_demonstrated": False,
                "real_action_consequence_demonstrated": False,
            },
            "later_companion_decision_intervention": {
                "measurement_scope": "direct_historical_retrieval_not_new_action_transfer",
                "status": companion_intervention.status,
                "question_digest": companion_intervention.question_digest,
                "changed_cognition_measurement_id":
                    companion_intervention.changed_cognition_measurement_id,
                "response_text_classification": companion_intervention.response_text_classification,
                "semantic_decisions": semantic_decisions,
                "semantic_decision_classification": semantic_decision_classification,
                "history_changed_cognition": semantic_history_changed,
                "performance_improvement_established": False,
                "controlled_inputs_match": intervention_inputs_match,
                "restored_prompt_matches": companion_intervention.restored_prompt_matches,
                "conditions": [{
                    "condition_id": item.get("condition_id"),
                    "response": item.get("response"),
                    "disposition": item.get("disposition"),
                    "response_digest": item.get("response_digest"),
                    "output_digest": item.get("output_digest"),
                    "prompt_digest": item.get("prompt_digest"),
                    "generation_config": item.get("generation_config"),
                    "active_model_identity": item.get("active_model_identity"),
                    "snapshot_digest": item.get("snapshot_digest"),
                    "current_fact_ids": item.get("current_fact_ids"),
                    "retrieved_record_ids": item.get("retrieved_record_ids"),
                    "history_record_ids": list(item.get("history_record_ids", ())),
                    "inference_receipt_id": item.get("inference_receipt_id"),
                    "inference_receipt_digest": item.get("inference_receipt_digest"),
                    "inference_status": item.get("inference_status"),
                    "cognition_receipt_output_binding_verified":
                        item.get("cognition_receipt_output_binding_verified"),
                } for item in companion_intervention.conditions],
                "authority": companion_intervention.authority,
                "action_authority": companion_intervention.action_authority,
                "canonical_explicit_user_retention_mutated":
                    companion_intervention.canonical_explicit_user_retention_mutated,
                "causal_or_learning_claim_made": False},
            "history_transfer_intervention": {
                **transfer_qualification,
                "measurement_scope": "new_action_proposal_not_execution",
                "status": transfer_intervention.status,
                "question_digest": transfer_intervention.question_digest,
                "changed_cognition_measurement_id":
                    transfer_intervention.changed_cognition_measurement_id,
                "response_text_classification":
                    transfer_intervention.response_text_classification,
                "history_changed_new_action_decision":
                    transfer_history_changed_new_decision,
                "classification": transfer_classification,
                "controlled_inputs_match": transfer_controls_match,
                "restored_prompt_matches":
                    transfer_intervention.restored_prompt_matches,
                "present_restored_output_digest_matches":
                    transfer_restoration_stable,
                "history_citation_bound": transfer_history_cited,
                "conditions": [{
                    "condition_id": item.get("condition_id"),
                    "response": item.get("response"),
                    "disposition": item.get("disposition"),
                    "response_digest": item.get("response_digest"),
                    "output_digest": item.get("output_digest"),
                    "snapshot_digest": item.get("snapshot_digest"),
                    "current_fact_ids": item.get("current_fact_ids"),
                    "retrieved_record_ids": item.get("retrieved_record_ids"),
                    "history_record_ids": list(item.get("history_record_ids", ())),
                    "active_model_identity": item.get("active_model_identity"),
                    "generation_config": item.get("generation_config"),
                    "inference_status": item.get("inference_status"),
                    "cognition_receipt_output_binding_verified":
                        item.get("cognition_receipt_output_binding_verified"),
                } for item in transfer_conditions],
                "authority": transfer_intervention.authority,
                "action_authority": transfer_intervention.action_authority,
                "action_executed": False,
                "performance_improvement_established": False,
                "causal_or_learning_claim_made": False},
            "objective_task_family_transfer": {
                **objective_transfer_history,
                "history_condition_difference_observed": (
                    objective_transfer_evaluation.get(
                        "history_correct_probe_delta") not in (None, 0)),
                "restoration_matches_present": (
                    objective_transfer_evaluation.get(
                        "restoration_correct_probe_delta") == 0),
                "causal_or_learning_claim_made": False,
                "interpretation": (
                    "one preregistered same-model exact-scored transfer episode; "
                    "not a general learning or real-world performance claim")},
            "historical_companion_recall": {
                "status": history_recall.get("status"),
                "response": history_recall.get("response"),
                "disposition": history_recall.get("disposition"),
                "history_record_ids": history_recall.get("history_record_ids", []),
                "prior_record_ids": history_recall.get("retrieved_record_ids", []),
                "cited_current_fact_ids": history_recall.get("cited_current_fact_ids", []),
                "snapshot_id": history_recall.get("snapshot_id"),
                "current_snapshot_digest": history_recall.get("snapshot_digest"),
                "response_lineage_verified": history_recall.get(
                    "response_lineage_verified") is True,
                "history_citation_bound": bool(history_recall.get("history_record_ids"))
                    and set(history_recall.get("history_record_ids", ())).issubset(
                        history_recall.get("retrieved_record_ids", ())),
                "historical_truth_claim_made": False,
                "reports_past_idle": _reports_past_idle(history_recall),
                "demonstrated_history_use": (_reports_past_idle(history_recall)
                    and _history_citation_bound(history_recall)
                    and history_recall.get("response_lineage_verified") is True),
            },
            "present_restoration_delivery_replay": present_restoration_delivery_replay,
            "history_intervention": {"validity": run_payload.get("validity"),
                "conditions": [{"condition_id": item.get("condition_id"),
                    "output_digest": item.get("output_digest"),
                    "prompt_digest": item.get("epistemic_prompt_digest"),
                    "generation_config": item.get("generation_config"),
                    "active_model_identity": item.get("active_model_identity"),
                    "retrieved_record_ids": item.get("retrieved_record_ids"),
                    "developmental_projection_present": item.get(
                        "developmental_projection_present")}
                    for item in conditions],
                "same_history_replay": same_history_replay,
                "restoration_stability_qualification": restoration_stability_qualification,
                "summary": summary,
                "causal_claim_made": False,
                "interpretation": "controlled history presence/withholding association only"},
            "gpu_before": before_gpu, "gpu_after": _gpu_snapshot(),
            "governed_unload": "pending",
        }
        session.close()
        result["governed_unload"] = "governed_release_completed"
        result["residency_verification"] = _verify_model_released(MODEL_NAME)
        result["gpu_after"] = _gpu_snapshot()
        RUN_STAGE = "complete_result_persistence"
        out = RUN_ROOT / "cycle-result.json"
        result["evidence_path"] = str(out)
        out.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        os.chmod(out, 0o600)
        return result
    finally:
        session.close()


if __name__ == "__main__":
    try:
        result = run()
    except Exception as exc:
        failure_artifact = None
        try:
            failure_artifact = _persist_incomplete_run(exc)
        except Exception:
            # Evidence persistence must not hide the original experiment failure.
            pass
        print(json.dumps({"status": "incomplete", "run_id": RUN_ID,
            "stage": RUN_STAGE, "failure_type": type(exc).__name__,
            "failure_code": _failure_code(exc),
            "failure_artifact": str(failure_artifact) if failure_artifact else None,
            "causal_or_learning_claim_made": False}, sort_keys=True, indent=2))
        raise
    print(json.dumps(result, sort_keys=True, indent=2))
