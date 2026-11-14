# mypy: ignore-errors
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from threading import Event, Thread
from time import monotonic

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.config import GenerationConfig, ModelCandidate, ModelConfig
from sentientos.control_plane_kernel import (
    AdmissionOutcome, AuthorityClass, ControlActionRequest,
    ControlPlaneKernel, LifecyclePhase,
)
from sentientos.governed_local_model_invocation import (
    GovernedLocalModelInvoker, LocalModelInvocationBudget, validate_receipt,
    validate_llama_completion_observation,
    RESIDENT_COGNITION_LESSON_OUTPUT_SCHEMA,
    RESIDENT_EPISTEMIC_REVISION_OUTPUT_SCHEMA, RESIDENT_COMPANION_INTERACTION_OUTPUT_SCHEMA,
    RESIDENT_COMPANION_HISTORY_INTERVENTION_OUTPUT_SCHEMA,
    RESIDENT_COMPANION_HISTORY_WITHHELD_OUTPUT_SCHEMA,
    RESIDENT_OBJECTIVE_TASK_ANSWER_OUTPUT_SCHEMA,
)
from sentientos.local_model_authority import build_local_model_authority_map, digest_payload
from sentientos.local_model import ActiveModelIdentity, ModelLoadError

class FakeModel:
    def __init__(self, text: str = "ok") -> None:
        self.calls = 0; self.text = text
    def generate(self, prompt: str, **kwargs: object) -> str:
        self.calls += 1; return self.text


class BackendMetadataModel(FakeModel):
    def __init__(self, text: str, completion: dict[str, object]) -> None:
        super().__init__(text)
        self.completion = completion

    def generate_governed_with_metadata(self, prompt: str, **kwargs: object):
        self.calls += 1
        return self.text, self.completion


class CancellableBlockingModel(FakeModel):
    def __init__(self) -> None:
        super().__init__()
        self.cancelled = Event()

    def generate(self, prompt: str, **kwargs: object) -> str:
        self.calls += 1
        if not self.cancelled.wait(timeout=2):
            raise TimeoutError("test worker was not cancelled")
        raise RuntimeError("test worker stopped")

    def cancel_pending_generation(self) -> bool:
        self.cancelled.set()
        return True


class NonCancellableBlockingModel(FakeModel):
    def __init__(self) -> None:
        super().__init__()
        self.release = Event()

    def generate(self, prompt: str, **kwargs: object) -> str:
        self.calls += 1
        self.release.wait(timeout=3)
        return "released"

    def cancel_pending_generation(self) -> bool:
        return False


def _invoker(tmp_path: Path, text: str = "ok"):
    model_path = tmp_path / "m.gguf"; model_path.write_bytes(b"bytes")
    cfg = ModelConfig(candidates=[ModelCandidate(path=model_path, engine="llama_cpp", name="m")], generation=GenerationConfig(max_new_tokens=8))
    authority = build_local_model_authority_map(cfg, allowed_roots=[tmp_path])
    fake = FakeModel(text)
    kernel = ControlPlaneKernel(phase=LifecyclePhase.RUNTIME, decisions_path=tmp_path / "decisions.jsonl")
    return fake, GovernedLocalModelInvoker(model=fake, authority_map=authority, kernel=kernel, runtime_root=tmp_path / "runtime")



def test_model_profile_change_during_admission_fails_closed_before_generation(
        tmp_path: Path) -> None:
    import hashlib
    from sentientos.control_plane_kernel import AuthorityClass

    manifest = tmp_path / "ollama-manifest.json"
    manifest.write_text('{"model":"qwen3:8b"}\n', encoding="utf-8")
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    candidate = ModelCandidate(path=manifest, engine="ollama", name="Qwen profile",
        options={"api_base": "http://127.0.0.1:11434", "model": "qwen3:8b",
            "manifest_sha256": digest, "num_gpu": 24, "keep_alive": "15m"})
    config = ModelConfig([candidate], default_engine="ollama",
        generation=GenerationConfig(max_new_tokens=8))
    authority = build_local_model_authority_map(config, allowed_roots=[tmp_path])
    record = authority.records[0]
    identity = ActiveModelIdentity(engine=record.engine,
        resolved_artifact_path=str(manifest.resolve()),
        semantic_artifact_identity=record.semantic_artifact_identity,
        model_content_sha256=record.model_content_sha256,
        artifact_size_bytes=record.artifact_size_bytes,
        sidecar_metadata_digest=record.sidecar_metadata_digest,
        configuration_digest=record.configuration_digest, candidate_index=0,
        posture="development_only", fallback=False)

    class IdentifiedModel(FakeModel):
        def __init__(self, active_identity):
            super().__init__()
            self.active_identity = active_identity

    active = IdentifiedModel(identity)
    replacement_identity = ActiveModelIdentity(**{
        **identity.to_dict(),
        "semantic_artifact_identity": "sha256:" + "a" * 64,
        "candidate_index": 1,
        "configuration_digest": "b" * 64,
    })
    replacement = IdentifiedModel(replacement_identity)
    kernel = ControlPlaneKernel(phase=LifecyclePhase.RUNTIME,
        decisions_path=tmp_path / "decisions.jsonl")
    invoker = GovernedLocalModelInvoker(model=active, authority_map=authority,
        kernel=kernel, runtime_root=tmp_path / "runtime")
    original_admit = kernel.admit

    def swap_after_admission(request):
        if request.authority_class is AuthorityClass.LOCAL_MODEL_INFERENCE:
            invoker.model = replacement
        return original_admit(request)

    kernel.admit = swap_after_admission
    request = invoker.build_request(purpose="local_user_chat", prompt="hello",
        caller="test", correlation_id="profile-transition-race")
    receipt = invoker.invoke(request)

    assert receipt.status == "backend_failure"
    assert "active_model_request_identity_mismatch" in receipt.reason_codes
    assert active.calls == replacement.calls == 0
    assert receipt.effects["local_model_inference"] is False

def test_governed_receipt_preserves_only_allowlisted_backend_diagnostic(
        tmp_path: Path) -> None:
    _, inv = _invoker(tmp_path)

    class DiagnosticFailureModel(FakeModel):
        def generate(self, prompt: str, **kwargs: object) -> str:
            self.calls += 1
            raise ModelLoadError("ollama_local_generation_failed",
                diagnostic_code="ollama_server_memory_pressure")

    inv.model = DiagnosticFailureModel()
    request = inv.build_request(purpose="local_user_chat", prompt="hello",
        caller="test", correlation_id="backend-diagnostic")

    receipt = inv.invoke(request)

    assert receipt.status == "backend_failure"
    assert receipt.reason_codes == ("backend_failure:ollama_server_memory_pressure",)
    assert validate_receipt(receipt.to_dict())[0]


def test_admitted_chat_receipt_is_digest_bound(tmp_path: Path) -> None:
    fake, inv = _invoker(tmp_path, "hello")
    req = inv.build_request(purpose="local_user_chat", prompt="hi", caller="test", correlation_id="c1")
    receipt = inv.invoke(req)
    assert fake.calls == 1
    assert receipt.status == "admitted_completed"
    assert receipt.effects["provider_network"] is False
    payload = receipt.to_dict()
    ok, reasons = validate_receipt(payload)
    assert ok, reasons
    payload["effects"]["tool"] = True
    ok, reasons = validate_receipt(payload)
    assert not ok


@pytest.mark.parametrize("thread_limit,expected_reason", [
    (2, "backend_thread_limit_unavailable"),
    (True, "backend_thread_ceiling_invalid"),
])
def test_backend_thread_ceiling_fails_closed_before_unsupported_generation(
        tmp_path: Path, thread_limit: object, expected_reason: str) -> None:
    fake, inv = _invoker(tmp_path)
    req = inv.build_request(purpose="local_user_chat", prompt="hi", caller="test",
        correlation_id="thread-ceiling-unsupported",
        linkage={"max_backend_threads": thread_limit})

    receipt = inv.invoke(req)

    assert fake.calls == 0
    assert expected_reason in receipt.reason_codes


@pytest.mark.parametrize("residency", ["0", "5s", "5m", "15m", "-1"])
def test_gaming_ollama_keep_alive_is_governed_and_forwarded(
        tmp_path: Path, residency: str) -> None:
    import hashlib

    manifest = tmp_path / "ollama-manifest.json"
    manifest.write_text('{"model":"qwen3:8b"}\n', encoding="utf-8")
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    candidate = ModelCandidate(path=manifest, engine="ollama", name="Qwen3 development",
        options={"api_base": "http://127.0.0.1:11434", "model": "qwen3:8b",
            "manifest_sha256": digest, "num_gpu": 99, "keep_alive": "15m"})
    config = ModelConfig(candidates=[candidate], default_engine="ollama",
        max_context_tokens=4096, generation=GenerationConfig(max_new_tokens=8))
    authority = build_local_model_authority_map(config, allowed_roots=[tmp_path])

    class CapturingModel(FakeModel):
        def __init__(self) -> None:
            super().__init__()
            self.generation = {}

        def generate(self, prompt: str, **kwargs: object) -> str:
            self.generation = kwargs
            return super().generate(prompt, **kwargs)

    model = CapturingModel()
    invoker = GovernedLocalModelInvoker(model=model, authority_map=authority,
        kernel=ControlPlaneKernel(phase=LifecyclePhase.RUNTIME,
            decisions_path=tmp_path / "decisions.jsonl"),
        runtime_root=tmp_path / "runtime")
    request = invoker.build_request(purpose="local_user_chat", prompt="hello",
        caller="test", correlation_id="gaming-unload",
        linkage={"workload_mode": "gaming", "ollama_keep_alive": residency})

    receipt = invoker.invoke(request)

    assert receipt.status == "admitted_completed"
    assert model.generation["keep_alive"] == residency


def test_ollama_keep_alive_override_is_rejected_for_other_engines(tmp_path: Path) -> None:
    fake, invoker = _invoker(tmp_path)
    request = invoker.build_request(purpose="local_user_chat", prompt="hello",
        caller="test", correlation_id="reject-ollama-residency",
        linkage={"ollama_keep_alive": "0"})

    receipt = invoker.invoke(request)

    assert fake.calls == 0
    assert receipt.status == "blocked_invalid"
    assert "ollama_keep_alive_override_invalid" in receipt.reason_codes


def test_invocation_timeout_cancels_cooperative_model_worker(tmp_path: Path) -> None:
    model_path = tmp_path / "m.gguf"
    model_path.write_bytes(b"bytes")
    config = ModelConfig(candidates=[ModelCandidate(
        path=model_path, engine="llama_cpp", name="m")],
        generation=GenerationConfig(max_new_tokens=8))
    authority = build_local_model_authority_map(config, allowed_roots=[tmp_path])
    model = CancellableBlockingModel()
    invoker = GovernedLocalModelInvoker(model=model, authority_map=authority,
        kernel=ControlPlaneKernel(phase=LifecyclePhase.RUNTIME,
            decisions_path=tmp_path / "decisions.jsonl"),
        runtime_root=tmp_path / "runtime")
    request = invoker.build_request(purpose="local_user_chat", prompt="wait",
        caller="test", correlation_id="bounded-timeout",
        budget=LocalModelInvocationBudget(timeout_seconds=0.02))

    started = monotonic()
    receipt = invoker.invoke(request)

    assert receipt.status == "timeout"
    assert "timeout" in receipt.reason_codes
    assert "timeout_worker_terminated" in receipt.reason_codes
    assert receipt.effects["local_model_inference"] is True
    assert model.cancelled.is_set()
    assert monotonic() - started < 0.5



def test_governed_cancellation_admission_is_bound_to_receipt(
        tmp_path: Path, monkeypatch) -> None:
    model_path = tmp_path / "m.gguf"
    model_path.write_bytes(b"bytes")
    config = ModelConfig(candidates=[ModelCandidate(
        path=model_path, engine="llama_cpp", name="m")],
        generation=GenerationConfig(max_new_tokens=8))
    authority = build_local_model_authority_map(config, allowed_roots=[tmp_path])
    model = CancellableBlockingModel()
    kernel = ControlPlaneKernel(phase=LifecyclePhase.RUNTIME,
        decisions_path=tmp_path / "decisions.jsonl")
    invoker = GovernedLocalModelInvoker(model=model, authority_map=authority,
        kernel=kernel,
        runtime_root=tmp_path / "runtime")
    published_receipts = []
    invoker.register_evidence_sink(published_receipts.append)
    request = invoker.build_request(purpose="local_user_chat", prompt="wait",
        caller="test", correlation_id="client-disconnect",
        budget=LocalModelInvocationBudget(timeout_seconds=2))
    result = []
    worker = Thread(target=lambda: result.append(invoker.invoke(request)))
    worker.start()
    deadline = monotonic() + 1
    while model.calls == 0 and monotonic() < deadline:
        Event().wait(0.005)
    assert model.calls == 1
    # The invocation-owner unit test uses an allow object emitted by its kernel;
    # serving integration tests cover the actual host and game admission paths.
    active_reference = invoker.active_invocation_request_reference()
    assert active_reference is not None
    decision = kernel._finalize(ControlActionRequest(
        action_kind="local_model_inference_preemption",
        authority_class=AuthorityClass.LOCAL_MODEL_INFERENCE,
        actor="production_chat_game_workload_governor",
        target_subsystem="governed_local_model_invocation",
        requested_phase=LifecyclePhase.RUNTIME,
        metadata={"correlation_id": "active-inference-preemption:"
            + digest_payload(dict(active_reference)) + ":governed-test"}),
        AdmissionOutcome.ALLOW, ["admitted"], {})
    with pytest.raises(ValueError, match="admission_decision_unverified"):
        invoker.cancel_pending_generation(reason="workload_transition",
            cancellation_admission_decision="kernel_decision:forged")
    with pytest.raises(ValueError, match="admission_decision_unverified"):
        invoker.cancel_pending_generation(reason="workload_transition",
            cancellation_admission_decision=replace(decision))

    def fail_decision_append(_payload):
        raise OSError("synthetic_decision_log_failure")

    with monkeypatch.context() as patcher:
        patcher.setattr(kernel, "_append", fail_decision_append)
        unpersisted_decision = kernel._finalize(ControlActionRequest(
            action_kind="local_model_inference_preemption",
            authority_class=AuthorityClass.LOCAL_MODEL_INFERENCE,
            actor="production_chat_game_workload_governor",
            target_subsystem="governed_local_model_invocation",
            requested_phase=LifecyclePhase.RUNTIME,
            metadata={"correlation_id": "unpersisted-preemption"}),
            AdmissionOutcome.ALLOW, ["admitted"], {})
    with pytest.raises(ValueError, match="admission_decision_unverified"):
        invoker.cancel_pending_generation(reason="workload_transition",
            cancellation_admission_decision=unpersisted_decision)
    mismatched_decision = kernel._finalize(ControlActionRequest(
        action_kind="local_model_inference_preemption",
        authority_class=AuthorityClass.LOCAL_MODEL_INFERENCE,
        actor="production_chat_game_workload_governor",
        target_subsystem="governed_local_model_invocation",
        requested_phase=LifecyclePhase.RUNTIME,
        metadata={"correlation_id": "active-inference-preemption:"
            + digest_payload({**dict(active_reference), "request_id": "another-invocation"})
            + ":governed-test"}), AdmissionOutcome.ALLOW, ["admitted"], {})
    assert invoker.cancel_pending_generation(reason="workload_transition",
        cancellation_admission_decision=mismatched_decision) is False
    assert model.cancelled.is_set() is False
    mismatched_release_decision = kernel._finalize(ControlActionRequest(
        action_kind="local_model_resource_release",
        authority_class=AuthorityClass.LOCAL_MODEL_RESOURCE_RELEASE,
        actor="production_chat_game_resource_governor",
        target_subsystem="production_chat",
        requested_phase=LifecyclePhase.RUNTIME,
        metadata={"correlation_id": "active-resource-release:"
            + digest_payload({**dict(active_reference), "request_id": "another-invocation"})
            + ":governed-test"}), AdmissionOutcome.ALLOW, ["admitted"], {})
    assert invoker.cancel_pending_generation(reason="workload_transition",
        cancellation_admission_decision=mismatched_release_decision) is False
    assert model.cancelled.is_set() is False
    assert invoker.cancel_pending_generation(reason="workload_transition",
        cancellation_admission_decision=decision) is True
    worker.join(1)

    assert not worker.is_alive()
    assert result[0].status == "cancelled"
    assert "cancelled_for_workload_transition" in result[0].reason_codes
    assert result[0].cancellation_admission_decision_ref == (
        decision.admission_decision_ref)
    assert result[0].schema_version == "sentientos.local_model_invocation_receipt:v4"
    valid, reasons = validate_receipt(result[0].to_dict())
    assert valid, reasons
    persisted = json.loads((tmp_path / "runtime" / "receipts" /
        f"{result[0].receipt_id}.json").read_text(encoding="utf-8"))
    assert validate_receipt(persisted)[0]
    assert persisted["cancellation_admission_decision_ref"] == (
        decision.admission_decision_ref)
    assert published_receipts[0]["receipt_digest"] == result[0].receipt_digest
    assert model.cancelled.is_set()


def test_unconfirmed_timeout_is_bounded_and_blocks_overlapping_generation(
        tmp_path: Path) -> None:
    model_path = tmp_path / "m.gguf"
    model_path.write_bytes(b"bytes")
    config = ModelConfig(candidates=[ModelCandidate(
        path=model_path, engine="llama_cpp", name="m")],
        generation=GenerationConfig(max_new_tokens=8))
    authority = build_local_model_authority_map(config, allowed_roots=[tmp_path])
    model = NonCancellableBlockingModel()
    invoker = GovernedLocalModelInvoker(model=model, authority_map=authority,
        kernel=ControlPlaneKernel(phase=LifecyclePhase.RUNTIME,
            decisions_path=tmp_path / "decisions.jsonl"),
        runtime_root=tmp_path / "runtime")
    first = invoker.build_request(purpose="local_user_chat", prompt="wait",
        caller="test", correlation_id="unconfirmed-timeout-one",
        budget=LocalModelInvocationBudget(timeout_seconds=0.02))

    started = monotonic()
    receipt = invoker.invoke(first)
    assert receipt.status == "timeout"
    assert "timeout_worker_cancellation_failed" in receipt.reason_codes
    assert receipt.effects["local_model_inference"] is True
    assert monotonic() - started < 0.8

    second = invoker.build_request(purpose="local_user_chat", prompt="overlap",
        caller="test", correlation_id="unconfirmed-timeout-two")
    blocked = invoker.invoke(second)
    assert blocked.status == "backend_failure"
    assert "backend_failure:RuntimeError" in blocked.reason_codes
    assert model.calls == 1
    model.release.set()


def test_backend_reported_token_limit_is_bound_and_makes_output_unscoreable(tmp_path: Path) -> None:
    model_path = tmp_path / "m.gguf"; model_path.write_bytes(b"bytes")
    cfg = ModelConfig(candidates=[ModelCandidate(path=model_path, engine="llama_cpp", name="m")],
        generation=GenerationConfig(max_new_tokens=8))
    authority = build_local_model_authority_map(cfg, allowed_roots=[tmp_path])
    completion = {"schema_version":"sentientos.llama_cpp_completion_observation:v1",
        "backend":"llama_cpp", "finish_reason":"length", "completion_tokens":8,
        "prompt_tokens":20, "token_limit_reached":True}
    fake = BackendMetadataModel('{"answer":23}', completion)
    inv = GovernedLocalModelInvoker(model=fake, authority_map=authority,
        kernel=ControlPlaneKernel(phase=LifecyclePhase.RUNTIME,
            decisions_path=tmp_path / "decisions.jsonl"), runtime_root=tmp_path / "runtime")
    request = inv.build_request(purpose="local_user_chat", prompt="predict",
        caller="test", correlation_id="backend-token-limit",
        budget=LocalModelInvocationBudget(max_new_tokens=8))
    receipt = inv.invoke(request)
    assert receipt.schema_version == "sentientos.local_model_invocation_receipt:v3"
    assert receipt.output_truncated is True
    assert "backend_token_limit_reached" in receipt.reason_codes
    payload = receipt.to_dict()
    assert payload["backend_completion"] == completion
    valid, reasons = validate_receipt(payload)
    assert valid, reasons
    payload["backend_completion"]["token_limit_reached"] = False
    valid, reasons = validate_receipt(payload)
    assert not valid
    assert "receipt_digest_mismatch" in reasons


def test_worker_resource_measurements_are_bound_to_invocation_receipt(tmp_path: Path) -> None:
    model_path = tmp_path / "m.gguf"
    model_path.write_bytes(b"bytes")
    config = ModelConfig(candidates=[ModelCandidate(
        path=model_path, engine="llama_cpp", name="m")],
        generation=GenerationConfig(max_new_tokens=8))
    authority = build_local_model_authority_map(config, allowed_roots=[tmp_path])
    completion = {
        "schema_version": "sentientos.llama_cpp_completion_observation:v3",
        "backend": "llama_cpp",
        "finish_reason": "unknown",
        "completion_tokens": None,
        "prompt_tokens": None,
        "token_limit_reached": None,
        "invocation_resources": {
            "schema_version": "sentientos.llama_cpp_invocation_resource_observation:v1",
            "user_cpu_seconds": 0.14,
            "system_cpu_seconds": 0.02,
            "wall_seconds": 0.18,
            "process_peak_rss_bytes": 7_340_032,
        },
        "backend_thread_limit_control": {
            "schema_version": "sentientos.llama_cpp_backend_thread_limit_control:v1",
            "requested_ceiling": 2,
            "setter_function": "llama_set_n_threads",
            "n_threads_argument": 2,
            "n_threads_batch_argument": 2,
        },
    }
    model = BackendMetadataModel("answer", completion)
    model.supports_per_invocation_thread_limit = True
    invoker = GovernedLocalModelInvoker(model=model, authority_map=authority,
        kernel=ControlPlaneKernel(phase=LifecyclePhase.RUNTIME,
            decisions_path=tmp_path / "decisions.jsonl"), runtime_root=tmp_path / "runtime")
    request = invoker.build_request(purpose="local_user_chat", prompt="hello",
        caller="test", correlation_id="worker-resource-observation",
        linkage={"max_backend_threads": 2})

    receipt = invoker.invoke(request)

    assert receipt.status == "admitted_completed"
    payload = receipt.to_dict()
    assert payload["backend_completion"] == completion
    assert payload["generation_config"]["actual_generation_parameters"][
        "max_backend_threads"] == 2
    valid, reasons = validate_receipt(payload)
    assert valid, reasons
    payload["request"]["linkage"]["max_backend_threads"] = 1
    valid, reasons = validate_receipt(payload)
    assert not valid and "backend_thread_limit_control_unbound" in reasons
    payload["request"]["linkage"]["max_backend_threads"] = 2
    payload["backend_completion"]["invocation_resources"]["user_cpu_seconds"] = -1
    valid, reasons = validate_receipt(payload)
    assert not valid
    assert "receipt_digest_mismatch" in reasons


@pytest.mark.parametrize("field,value", [
    ("user_cpu_seconds", -0.01),
    ("system_cpu_seconds", float("inf")),
    ("user_cpu_seconds", 10 ** 1000),
    ("wall_seconds", True),
    ("process_peak_rss_bytes", -1),
    ("process_peak_rss_bytes", 1_099_511_627_777),
])
def test_worker_resource_observation_rejects_invalid_measurements(field: str, value: object) -> None:
    completion = {
        "schema_version": "sentientos.llama_cpp_completion_observation:v2",
        "backend": "llama_cpp",
        "finish_reason": "unknown",
        "completion_tokens": None,
        "prompt_tokens": None,
        "token_limit_reached": None,
        "invocation_resources": {
            "schema_version": "sentientos.llama_cpp_invocation_resource_observation:v1",
            "user_cpu_seconds": 0.1,
            "system_cpu_seconds": 0.01,
            "wall_seconds": 0.11,
            "process_peak_rss_bytes": 8_388_608,
        },
    }
    completion["invocation_resources"][field] = value

    assert not validate_llama_completion_observation(completion)


def test_backend_thread_limit_control_observation_is_bounded_and_exact() -> None:
    completion = {
        "schema_version": "sentientos.llama_cpp_completion_observation:v3",
        "backend": "llama_cpp", "finish_reason": "unknown",
        "completion_tokens": None, "prompt_tokens": None,
        "token_limit_reached": None,
        "invocation_resources": {
            "schema_version": "sentientos.llama_cpp_invocation_resource_observation:v1",
            "user_cpu_seconds": 0.1, "system_cpu_seconds": 0.01,
            "wall_seconds": 0.11, "process_peak_rss_bytes": 8_388_608,
        },
        "backend_thread_limit_control": {
            "schema_version": "sentientos.llama_cpp_backend_thread_limit_control:v1",
            "requested_ceiling": 2, "setter_function": "llama_set_n_threads",
            "n_threads_argument": 2, "n_threads_batch_argument": 2,
        },
    }
    assert validate_llama_completion_observation(completion)

    completion["backend_thread_limit_control"]["n_threads_argument"] = 3

    assert not validate_llama_completion_observation(completion)


def test_denied_duplicate_does_not_call_backend_twice(tmp_path: Path) -> None:
    fake, inv = _invoker(tmp_path, "hello")
    req = inv.build_request(purpose="local_user_chat", prompt="hi", caller="test", correlation_id="dup")
    assert inv.invoke(req).status == "admitted_completed"
    second = inv.invoke(req)
    assert second.status in {"blocked_invalid", "deferred"}
    assert fake.calls == 1


def test_malformed_genesis_advice_records_failure(tmp_path: Path) -> None:
    fake, inv = _invoker(tmp_path, "import os")
    req = inv.build_request(purpose="genesis_proposal_advice", prompt="advise", caller="genesis", correlation_id="g1", lifecycle_phase="runtime", expected_output_format="json", budget=LocalModelInvocationBudget(max_output_chars=100))
    receipt = inv.invoke(req, include_output_in_receipt=True)
    assert fake.calls == 0
    assert receipt.status in {"blocked_invalid", "denied"}
    assert "genesis_review_evidence_missing_or_invalid" in receipt.reason_codes


def test_production_identity_mismatch_is_blocked(tmp_path: Path) -> None:
    fake, inv = _invoker(tmp_path)
    record = inv.authority_map.records[0]
    fake.active_identity = ActiveModelIdentity(
        engine=record.engine, resolved_artifact_path=str(tmp_path / "other.gguf"),
        semantic_artifact_identity="sha256:" + "0" * 64,
        model_content_sha256="0" * 64, artifact_size_bytes=1,
        sidecar_metadata_digest=None, configuration_digest=record.configuration_digest,
        candidate_index=0, posture="production", fallback=False)
    with pytest.raises(ValueError, match="exact_production_authority_record_required"):
        inv.build_request(purpose="local_user_chat", prompt="hi", caller="test", correlation_id="mismatch")
    assert fake.calls == 0


@pytest.mark.parametrize(
    "engine,gpu_layers,device_type,expected_route,profile_layers,config_changes_after_request", [
    ("llama_cpp", 0, None, "cpu", 0, False),
    ("llama_cpp", 16, None, "gpu", 16, False),
    ("transformers", None, "cpu", "cpu", None, False),
    ("transformers", None, "cuda", "gpu", None, False),
    ("transformers", None, None, "unknown", None, False),
    ("llama_cpp", 16, None, "unknown", None, True),
])
def test_verified_loaded_model_accelerator_profile_reaches_inference_admission(
        tmp_path: Path, engine: str, gpu_layers: int | None, device_type: str | None,
        expected_route: str, profile_layers: int | None, config_changes_after_request: bool,
        monkeypatch) -> None:
    from sentientos.local_model import LocalModel
    from sentientos.host_resource_runtime import (
        HostObservationCollectorSpec, HostResourceRuntimeCoordinator,
        build_observation_plan,
    )
    from sentientos.host_collectors import HostCollectorResult
    from sentientos.runtime_governor import RuntimeGovernor

    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.0")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.0")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.0")

    class Backend:
        def __init__(self):
            self.engine = engine
            self.metadata = {"engine": engine, "name": "profile-fixture"}
            self.calls = 0
            if engine == "transformers":
                from types import SimpleNamespace
                self._model = SimpleNamespace(
                    device=SimpleNamespace(type=device_type))

        def generate(self, prompt: str, history: list[str], generation: dict[str, object]) -> str:
            self.calls += 1
            return "answer"

    class RecordingKernel(ControlPlaneKernel):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.requests = []

        def admit(self, request):
            self.requests.append(request)
            return super().admit(request)

    artifact = tmp_path / "profile.gguf"
    artifact.write_bytes(b"verified fixture model")
    candidate_options = {"gpu_layers": gpu_layers} if engine == "llama_cpp" else {}
    candidate = ModelCandidate(path=artifact, engine=engine, name="profile-fixture",
                               options=candidate_options)
    config = ModelConfig(candidates=[candidate],
        generation=GenerationConfig(max_new_tokens=8))
    backend = Backend()
    model = LocalModel.__new__(LocalModel)
    model.backend = backend
    model.metadata = dict(backend.metadata)
    model.config = config
    model._fallback_backend = backend
    model.active_identity = LocalModel._identity_for(candidate, config, backend,
                                                      model.metadata, 0)
    authority = build_local_model_authority_map(config, allowed_roots=[tmp_path])
    kernel = RecordingKernel(runtime_governor=RuntimeGovernor(),
        phase=LifecyclePhase.MAINTENANCE,
        decisions_path=tmp_path / "decisions.jsonl")
    plan = build_observation_plan(specs=[
        HostObservationCollectorSpec("cpu", True, ("linux", "unknown"), 1,
            lambda observed_at=None: HostCollectorResult("cpu", "available", observed_at or "", "fixture",
                                                          values={"utilization_percent": 20.0})),
        HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2,
            lambda observed_at=None: HostCollectorResult("memory", "available", observed_at or "", "fixture",
                values={"used_percent": 40.0})),
        HostObservationCollectorSpec("disk", True, ("linux", "unknown"), 3,
            lambda observed_at=None: HostCollectorResult("disk", "available", observed_at or "", "fixture",
                values={"used_percent": 30.0, "free_bytes": 1000})),
    ])
    evaluation = HostResourceRuntimeCoordinator(kernel=kernel,
        runtime_state_root=tmp_path / "resource-state", plan=plan).run_cycle(
            correlation_id=f"gpu-profile-{gpu_layers}")
    assert evaluation is not None
    assert kernel.observe_host_resource_evaluation(evaluation)
    kernel.set_phase(LifecyclePhase.RUNTIME)
    invoker = GovernedLocalModelInvoker(model=model, authority_map=authority,
        kernel=kernel, runtime_root=tmp_path / "runtime")
    request = invoker.build_request(purpose="maintenance_implementation", prompt="hello",
        caller="test", correlation_id=f"loaded-profile-{gpu_layers}")
    if config_changes_after_request:
        model.config.generation = GenerationConfig(max_new_tokens=9)

    receipt = invoker.invoke(request)

    if expected_route != "cpu":
        assert receipt.status == "deferred"
        assert "runtime_governor:deferred_gpu_offload_telemetry_incomplete" in receipt.reason_codes
        assert backend.calls == 0
    else:
        assert receipt.status == "admitted_completed"
        assert backend.calls == 1
    invocation_request = next(item for item in kernel.requests
                              if item.action_kind == "local_model_inference")
    profile = invocation_request.metadata.get("model_execution_profile")
    assert profile == {
        "schema_version": "sentientos.model_execution_profile:v1",
        "engine": engine,
        "accelerator_route": expected_route,
        "gpu_layers": profile_layers,
        "configuration_digest": model.active_identity.configuration_digest,
    }


def test_resident_cognition_json_schema_is_exactly_purpose_scoped(tmp_path: Path) -> None:
    fake, inv = _invoker(tmp_path)
    request = inv.build_request(
        purpose="resident_developmental_retrieval_cognition",
        prompt="bounded history-conditioned reasoning",
        caller="resident_developmental_cognition",
        correlation_id="cognition-json",
        expected_output_format="json",
        structured_output_schema=RESIDENT_COGNITION_LESSON_OUTPUT_SCHEMA,
    )
    receipt = inv.invoke(request)
    assert receipt.status == "admitted_completed"
    assert receipt.generation_config["actual_generation_parameters"]["temperature"] == 0
    assert fake.calls == 1

    altered = {**RESIDENT_COGNITION_LESSON_OUTPUT_SCHEMA,
               "properties": {**RESIDENT_COGNITION_LESSON_OUTPUT_SCHEMA["properties"],
                              "unexpected": {"type": "string"}}}
    with pytest.raises(ValueError, match="structured_output_schema_not_canonical"):
        inv.build_request(
            purpose="resident_developmental_retrieval_cognition",
            prompt="bounded history-conditioned reasoning",
            caller="resident_developmental_cognition",
            correlation_id="cognition-json-altered",
            expected_output_format="json",
            structured_output_schema=altered,
        )
    assert fake.calls == 1



def test_companion_interaction_schema_is_canonical_and_purpose_scoped(tmp_path: Path) -> None:
    fake, inv = _invoker(tmp_path)
    request = inv.build_request(
        purpose="resident_developmental_retrieval_cognition",
        prompt="bounded companion decision",
        caller="resident_developmental_cognition",
        correlation_id="companion-json",
        expected_output_format="json",
        structured_output_schema=RESIDENT_COMPANION_INTERACTION_OUTPUT_SCHEMA,
    )
    receipt = inv.invoke(request)
    assert receipt.status == "admitted_completed"
    assert fake.calls == 1

    altered = {**RESIDENT_COMPANION_INTERACTION_OUTPUT_SCHEMA,
        "properties": {**RESIDENT_COMPANION_INTERACTION_OUTPUT_SCHEMA["properties"],
            "authority": {"type": "boolean"}}}
    with pytest.raises(ValueError, match="structured_output_schema_not_canonical"):
        inv.build_request(
            purpose="resident_developmental_retrieval_cognition",
            prompt="bounded companion decision",
            caller="resident_developmental_cognition",
            correlation_id="companion-json-altered",
            expected_output_format="json", structured_output_schema=altered)
    assert fake.calls == 1


def test_history_intervention_allows_only_canonical_companion_json(tmp_path: Path) -> None:
    fake, inv = _invoker(tmp_path)
    request = inv.build_request(
        purpose="resident_developmental_history_intervention_experiment",
        prompt="controlled companion decision comparison",
        caller="resident_developmental_cognition",
        correlation_id="companion-intervention-json",
        expected_output_format="json",
        structured_output_schema=RESIDENT_COMPANION_HISTORY_INTERVENTION_OUTPUT_SCHEMA,
    )
    assert request.structured_output_schema == RESIDENT_COMPANION_HISTORY_INTERVENTION_OUTPUT_SCHEMA
    assert request.expected_output_format == "json"

    withheld = inv.build_request(
        purpose="resident_developmental_history_intervention_experiment",
        prompt="history-withheld companion decision",
        caller="resident_developmental_cognition",
        correlation_id="companion-intervention-withheld-json",
        expected_output_format="json",
        structured_output_schema=RESIDENT_COMPANION_HISTORY_INTERVENTION_OUTPUT_SCHEMA,
        linkage={"condition_id": "history_withheld"})
    assert withheld.structured_output_schema == request.structured_output_schema
    withheld_only_schema = {
        **RESIDENT_COMPANION_HISTORY_WITHHELD_OUTPUT_SCHEMA,
        "properties": {
            **RESIDENT_COMPANION_HISTORY_WITHHELD_OUTPUT_SCHEMA["properties"],
            "history_record_ids": {
                **RESIDENT_COMPANION_HISTORY_WITHHELD_OUTPUT_SCHEMA["properties"]["history_record_ids"],
                "maxItems": 0,
            },
        },
    }
    with pytest.raises(ValueError, match="structured_output_schema_not_canonical"):
        inv.build_request(
            purpose="resident_developmental_history_intervention_experiment",
            prompt="history-withheld companion decision",
            caller="resident_developmental_cognition",
            correlation_id="companion-intervention-withheld-schema",
            expected_output_format="json",
            structured_output_schema=withheld_only_schema,
            linkage={"condition_id": "history_withheld"})

    altered = {**RESIDENT_COMPANION_HISTORY_INTERVENTION_OUTPUT_SCHEMA,
        "properties": {**RESIDENT_COMPANION_HISTORY_INTERVENTION_OUTPUT_SCHEMA["properties"],
            "action": {"type": "string"}}}
    with pytest.raises(ValueError, match="structured_output_schema_not_canonical"):
        inv.build_request(
            purpose="resident_developmental_history_intervention_experiment",
            prompt="controlled companion decision comparison",
            caller="resident_developmental_cognition",
            correlation_id="companion-intervention-json-altered",
            expected_output_format="json", structured_output_schema=altered)
    with pytest.raises(ValueError, match="structured_output_schema_not_canonical"):
        inv.build_request(
            purpose="resident_developmental_history_intervention_experiment",
            prompt="controlled companion decision comparison",
            caller="resident_developmental_cognition",
            correlation_id="companion-intervention-lesson-json",
            expected_output_format="json",
            structured_output_schema=RESIDENT_COGNITION_LESSON_OUTPUT_SCHEMA)
    assert fake.calls == 0


def test_objective_history_intervention_allows_only_canonical_scored_answer_json(
        tmp_path: Path) -> None:
    fake, inv = _invoker(tmp_path)
    request = inv.build_request(
        purpose="resident_developmental_history_intervention_experiment",
        prompt="predict the preregistered held-out objective probes",
        caller="resident_developmental_cognition",
        correlation_id="objective-intervention-json",
        expected_output_format="json",
        upstream_evidence={"objective_task_plan_digest": "sha256:" + "a" * 64},
        linkage={"condition_id": "history_present"},
        structured_output_schema=RESIDENT_OBJECTIVE_TASK_ANSWER_OUTPUT_SCHEMA)
    assert request.structured_output_schema == RESIDENT_OBJECTIVE_TASK_ANSWER_OUTPUT_SCHEMA
    assert request.expected_output_format == "json"

    with pytest.raises(ValueError, match="structured_output_schema_not_canonical"):
        inv.build_request(
            purpose="resident_developmental_history_intervention_experiment",
            prompt="arbitrary output schema",
            caller="resident_developmental_cognition",
            correlation_id="objective-intervention-json-altered",
            expected_output_format="json",
            upstream_evidence={"objective_task_plan_digest": "sha256:" + "a" * 64},
            linkage={"condition_id": "history_present"},
            structured_output_schema={"type": "object", "additionalProperties": True})
    # An objective answer schema cannot be smuggled into a conversational
    # history intervention without the owner-bound preregistered plan digest.
    with pytest.raises(ValueError, match="structured_output_schema_not_canonical"):
        inv.build_request(
            purpose="resident_developmental_history_intervention_experiment",
            prompt="unbound objective output",
            caller="resident_developmental_cognition",
            correlation_id="objective-intervention-json-unbound",
            expected_output_format="json",
            linkage={"condition_id": "history_present"},
            structured_output_schema=RESIDENT_OBJECTIVE_TASK_ANSWER_OUTPUT_SCHEMA)
    assert fake.calls == 0


def test_epistemic_revision_json_schema_is_canonical_and_purpose_scoped(tmp_path: Path) -> None:
    fake, inv = _invoker(tmp_path)
    request = inv.build_request(
        purpose="resident_developmental_retrieval_cognition",
        prompt="bounded epistemic revision probe",
        caller="resident_developmental_cognition",
        correlation_id="epistemic-revision-json",
        expected_output_format="json",
        structured_output_schema=RESIDENT_EPISTEMIC_REVISION_OUTPUT_SCHEMA,
    )
    receipt = inv.invoke(request)
    assert receipt.status == "admitted_completed"
    assert request.structured_output_schema == RESIDENT_EPISTEMIC_REVISION_OUTPUT_SCHEMA
    assert fake.calls == 1

    altered = {**RESIDENT_EPISTEMIC_REVISION_OUTPUT_SCHEMA,
        "properties": {**RESIDENT_EPISTEMIC_REVISION_OUTPUT_SCHEMA["properties"],
            "unexpected": {"type": "string"}}}
    with pytest.raises(ValueError, match="structured_output_schema_not_canonical"):
        inv.build_request(
            purpose="resident_developmental_retrieval_cognition",
            prompt="bounded epistemic revision probe",
            caller="resident_developmental_cognition",
            correlation_id="epistemic-revision-json-altered",
            expected_output_format="json", structured_output_schema=altered)
    assert fake.calls == 1

def test_mutating_cognition_schema_after_request_build_cannot_widen_invocation(tmp_path: Path) -> None:
    fake, inv = _invoker(tmp_path)
    request = inv.build_request(
        purpose="resident_developmental_retrieval_cognition",
        prompt="bounded context",
        caller="resident_developmental_cognition",
        correlation_id="cognition-schema-mutated",
        expected_output_format="json",
        structured_output_schema=RESIDENT_COGNITION_LESSON_OUTPUT_SCHEMA,
    )
    request.structured_output_schema["properties"]["conclusion"]["maxLength"] = 1
    assert RESIDENT_COGNITION_LESSON_OUTPUT_SCHEMA["properties"]["conclusion"]["maxLength"] == 2500
    receipt = inv.invoke(request)
    assert receipt.status == "blocked_invalid"
    assert "structured_output_schema_not_canonical" in receipt.reason_codes
    assert fake.calls == 0
