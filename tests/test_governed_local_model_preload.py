from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.config import GenerationConfig, ModelCandidate, ModelConfig
from sentientos.control_plane_kernel import AuthorityClass, LifecyclePhase
from sentientos.governed_local_model_invocation import GovernedLocalModelInvoker
from sentientos.local_model import ActiveModelIdentity
from sentientos.local_model_authority import build_local_model_authority_map


class _PreloadModel:
    def __init__(self, identity: ActiveModelIdentity, *, confirms_load: bool = True) -> None:
        self.active_identity = identity
        self.loaded = False
        self.confirms_load = confirms_load
        self.preload_calls: list[str] = []
        self.generation_calls = 0

    def is_resident(self) -> bool:
        return self.loaded

    def preload_residency(self, *, keep_alive: str) -> dict[str, object]:
        self.preload_calls.append(keep_alive)
        if self.confirms_load:
            self.loaded = True
        return {"backend": "ollama", "result": "load_requested",
            "keep_alive": keep_alive, "tokens_generated": 0}

    def generate(self, _prompt: str, **_kwargs: object) -> str:
        self.generation_calls += 1
        return "answer"


class _AdmissionKernel:
    phase = LifecyclePhase.RUNTIME

    def __init__(self, *, allowed: bool = True) -> None:
        self.allowed = allowed
        self.requests = []

    def admit(self, request):
        self.requests.append(request)
        return SimpleNamespace(allowed=self.allowed,
            admission_decision_ref="kernel_decision:preload",
            reason_codes=("local_model_preload_deferred",))


def _authority_and_identity(tmp_path: Path):
    manifest = tmp_path / "qwen-manifest.json"
    manifest.write_text('{"model":"qwen2.5:3b"}\n', encoding="utf-8")
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    candidate = ModelCandidate(path=manifest, engine="ollama", name="Qwen gaming",
        options={"api_base": "http://127.0.0.1:11434", "model": "qwen2.5:3b",
            "manifest_sha256": digest, "num_gpu": 12, "keep_alive": "0",
            "think": False, "timeout_seconds": 30})
    config = ModelConfig(candidates=[candidate], default_engine="ollama",
        max_context_tokens=4096, generation=GenerationConfig(max_new_tokens=96))
    authority = build_local_model_authority_map(config, allowed_roots=[tmp_path])
    record = authority.records[0]
    identity = ActiveModelIdentity(engine=record.engine,
        resolved_artifact_path=record.observed_metadata["resolved_artifact_path"],
        semantic_artifact_identity=record.semantic_artifact_identity,
        model_content_sha256=record.model_content_sha256,
        artifact_size_bytes=record.artifact_size_bytes,
        sidecar_metadata_digest=record.sidecar_metadata_digest,
        configuration_digest=record.configuration_digest,
        candidate_index=record.observed_metadata["candidate_index"],
        posture="development_only", fallback=False)
    return authority, identity


def _evidence(*, foreground: bool = True, utilization: float = 71.0,
              age_seconds: int = 0):
    observed = datetime.now(timezone.utc).timestamp() - age_seconds
    observed_at = datetime.fromtimestamp(observed, timezone.utc).isoformat()
    workload = {"mode": "automatic", "effective_mode": "gaming",
        "game_foreground": foreground,
        "workload_evidence": {"status": "available",
            "game_foreground": foreground, "game_process_running": True}}
    resources = {"admission_status": "available",
        "preload_admission_status": "available",
        "preload_threshold_percent": 75.0,
        "vram_utilization_percent": utilization,
        "observed_at": observed_at}
    return workload, resources


def test_preload_uses_governed_no_generation_path_and_exact_gaming_evidence(
        tmp_path: Path) -> None:
    authority, identity = _authority_and_identity(tmp_path)
    model = _PreloadModel(identity)
    kernel = _AdmissionKernel()
    invoker = GovernedLocalModelInvoker(model=model, authority_map=authority,
        kernel=kernel, runtime_root=tmp_path / "runtime")
    workload, resources = _evidence()

    receipt = invoker.preload_model_residency(keep_alive="-1",
        workload_state=workload, resource_state=resources)

    assert receipt.status == "preloaded"
    assert model.preload_calls == ["-1"]
    assert model.generation_calls == 0
    assert model.loaded is True
    assert kernel.requests[0].action_kind == "local_model_residency_preload"
    assert kernel.requests[0].authority_class is AuthorityClass.LOCAL_MODEL_INFERENCE
    assert kernel.requests[0].metadata["purpose"] == "local_model_preload"
    receipt_path = next((tmp_path / "runtime" / "resource_preload_receipts").glob("*.json"))
    assert receipt_path.is_file()


@pytest.mark.parametrize("workload,resources", [
    (_evidence(foreground=False)[0], _evidence(foreground=False)[1]),
    (_evidence()[0], _evidence(utilization=75.0)[1]),
    (_evidence()[0], _evidence(age_seconds=46)[1]),
])
def test_preload_fails_closed_without_exact_fresh_headroom(
        tmp_path: Path, workload, resources) -> None:
    authority, identity = _authority_and_identity(tmp_path)
    model = _PreloadModel(identity)
    kernel = _AdmissionKernel()
    invoker = GovernedLocalModelInvoker(model=model, authority_map=authority,
        kernel=kernel, runtime_root=tmp_path / "runtime")

    receipt = invoker.preload_model_residency(keep_alive="-1",
        workload_state=workload, resource_state=resources)

    assert receipt.status == "deferred"
    assert model.preload_calls == []
    assert kernel.requests == []


def test_preload_does_not_run_when_control_plane_defers(tmp_path: Path) -> None:
    authority, identity = _authority_and_identity(tmp_path)
    model = _PreloadModel(identity)
    kernel = _AdmissionKernel(allowed=False)
    invoker = GovernedLocalModelInvoker(model=model, authority_map=authority,
        kernel=kernel, runtime_root=tmp_path / "runtime")
    workload, resources = _evidence()

    receipt = invoker.preload_model_residency(keep_alive="-1",
        workload_state=workload, resource_state=resources)

    assert receipt.status == "deferred"
    assert model.preload_calls == []
    assert len(kernel.requests) == 1


def test_preload_yields_to_active_chat_invocation(tmp_path: Path) -> None:
    authority, identity = _authority_and_identity(tmp_path)
    model = _PreloadModel(identity)
    kernel = _AdmissionKernel()
    invoker = GovernedLocalModelInvoker(model=model, authority_map=authority,
        kernel=kernel, runtime_root=tmp_path / "runtime")
    workload, resources = _evidence()
    assert invoker._active_invocation_lock.acquire(blocking=False)
    try:
        receipt = invoker.preload_model_residency(keep_alive="-1",
            workload_state=workload, resource_state=resources)
    finally:
        invoker._active_invocation_lock.release()

    assert receipt.status == "deferred"
    assert "active_inference_or_model_transition" in receipt.reason_codes
    assert model.preload_calls == []
