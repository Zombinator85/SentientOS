# mypy: ignore-errors
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.config import GenerationConfig, ModelCandidate, ModelConfig
from sentientos.control_plane_kernel import ControlPlaneKernel, LifecyclePhase
from sentientos.governed_local_model_invocation import GovernedLocalModelInvoker, LocalModelInvocationBudget, validate_receipt
from sentientos.local_model_authority import build_local_model_authority_map

class FakeModel:
    def __init__(self, text: str = "ok") -> None:
        self.calls = 0; self.text = text
    def generate(self, prompt: str, **kwargs: object) -> str:
        self.calls += 1; return self.text


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
