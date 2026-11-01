# mypy: ignore-errors
from __future__ import annotations

from pathlib import Path
from threading import Event
from time import monotonic

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.config import GenerationConfig, ModelCandidate, ModelConfig
from sentientos.control_plane_kernel import ControlPlaneKernel, LifecyclePhase
from sentientos.governed_local_model_invocation import (
    GovernedLocalModelInvoker, LocalModelInvocationBudget, validate_receipt,
    RESIDENT_COGNITION_LESSON_OUTPUT_SCHEMA,
    RESIDENT_EPISTEMIC_REVISION_OUTPUT_SCHEMA,
)
from sentientos.local_model_authority import build_local_model_authority_map
from sentientos.local_model import ActiveModelIdentity

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

    def cancel_pending_generation(self) -> None:
        self.cancelled.set()


def _invoker(tmp_path: Path, text: str = "ok"):
    model_path = tmp_path / "m.gguf"; model_path.write_bytes(b"bytes")
    cfg = ModelConfig(candidates=[ModelCandidate(path=model_path, engine="llama_cpp", name="m")], generation=GenerationConfig(max_new_tokens=8))
    authority = build_local_model_authority_map(cfg, allowed_roots=[tmp_path])
    fake = FakeModel(text)
    kernel = ControlPlaneKernel(phase=LifecyclePhase.RUNTIME, decisions_path=tmp_path / "decisions.jsonl")
    return fake, GovernedLocalModelInvoker(model=fake, authority_map=authority, kernel=kernel, runtime_root=tmp_path / "runtime")


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
    assert model.cancelled.is_set()
    assert monotonic() - started < 0.5


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
