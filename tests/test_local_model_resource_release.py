from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from sentientos.config import GenerationConfig, ModelCandidate, ModelConfig
from sentientos.control_plane_kernel import ControlPlaneKernel, LifecyclePhase
from sentientos.governed_local_model_invocation import GovernedLocalModelInvoker
from sentientos.local_model import LocalModel
from sentientos.local_model_authority import build_local_model_authority_map


class _AllowingGovernor:
    def __init__(self) -> None:
        self.requests = []

    def admit_action(self, action_class, actor, correlation_id, metadata=None):
        self.requests.append({"action_class": action_class, "actor": actor,
            "correlation_id": correlation_id, "metadata": dict(metadata or {})})
        return SimpleNamespace(allowed=True, reason="allowed",
            to_dict=lambda: {"allowed": True, "reason": "allowed"})


class _ResidencyModel:
    def __init__(self, identity, *, resident: bool) -> None:
        self.active_identity = identity
        self.resident = resident
        self.release_calls = 0

    def is_resident(self) -> bool:
        return self.resident

    def release_residency(self) -> dict[str, str]:
        self.release_calls += 1
        self.resident = False
        return {"backend": "ollama", "result": "unload_requested"}


def _configured(tmp_path: Path, *, resident: bool):
    manifest = tmp_path / "model-manifest.json"
    manifest.write_text('{"model":"qwen3:8b"}\n', encoding="utf-8")
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    candidate = ModelCandidate(path=manifest, engine="ollama", name="Qwen3",
        options={"api_base": "http://127.0.0.1:11434", "model": "qwen3:8b",
            "manifest_sha256": digest, "num_gpu": 99})
    config = ModelConfig(candidates=[candidate], default_engine="ollama",
        generation=GenerationConfig(max_new_tokens=8))
    backend = SimpleNamespace(engine="ollama", metadata={"engine": "ollama"})
    identity = LocalModel._identity_for(candidate, config, backend,
        backend.metadata, 0)
    authority = build_local_model_authority_map(config, allowed_roots=[tmp_path])
    model = _ResidencyModel(identity, resident=resident)
    governor = _AllowingGovernor()
    kernel = ControlPlaneKernel(runtime_governor=governor,
        phase=LifecyclePhase.RUNTIME, decisions_path=tmp_path / "decisions.jsonl")
    invoker = GovernedLocalModelInvoker(model=model, authority_map=authority,
        kernel=kernel, runtime_root=tmp_path / "runtime")
    return model, governor, invoker


def test_gaming_transition_resource_release_is_admitted_and_receipted(
        tmp_path: Path) -> None:
    model, governor, invoker = _configured(tmp_path, resident=True)

    receipt = invoker.release_model_residency()

    assert receipt.status == "released"
    assert receipt.reason_codes == ("local_model_residency_released",)
    assert receipt.backend_result == {"backend": "ollama", "result": "unload_requested"}
    assert model.resident is False and model.release_calls == 1
    assert governor.requests[0]["action_class"] == "local_model_resource_release"
    assert governor.requests[0]["metadata"]["purpose"] == "local_model_resource_release"
    stored = next((tmp_path / "runtime" / "resource_release_receipts").glob("*.json"))
    payload = json.loads(stored.read_text(encoding="utf-8"))
    assert payload["receipt_digest"] == receipt.receipt_digest


def test_pressure_release_defers_without_interrupting_active_inference(
        tmp_path: Path) -> None:
    model, _, invoker = _configured(tmp_path, resident=True)
    assert invoker._active_invocation_lock.acquire(blocking=False)
    try:
        receipt = invoker.release_model_residency(
            reason_code="vram_pressure_observed", cancel_active=False)
    finally:
        invoker._active_invocation_lock.release()

    assert receipt.status == "deferred"
    assert receipt.reason_codes == ("active_inference_in_progress",)
    assert model.resident is True
    assert model.release_calls == 0


def test_unloaded_model_is_not_reloaded_by_release_transition(tmp_path: Path) -> None:
    model, governor, invoker = _configured(tmp_path, resident=False)

    receipt = invoker.release_model_residency()

    assert receipt.status == "already_unloaded"
    assert model.release_calls == 0
    assert governor.requests[0]["action_class"] == "local_model_resource_release"


def test_release_receipt_does_not_claim_unload_without_residency_confirmation(
        tmp_path: Path) -> None:
    model, _, invoker = _configured(tmp_path, resident=True)

    def leave_resident() -> dict[str, str]:
        model.release_calls += 1
        return {"backend": "ollama", "result": "unload_requested"}

    model.release_residency = leave_resident  # type: ignore[method-assign]
    receipt = invoker.release_model_residency()

    assert receipt.status == "release_unconfirmed"
    assert receipt.reason_codes == ("model_remained_resident_after_release",)
    assert model.resident is True
