# mypy: ignore-errors
from __future__ import annotations

from types import SimpleNamespace

import pytest

from sentientos import chat_service
from sentientos.canonical_memory import CanonicalMemoryStore
from sentientos.conversation_session import ConversationSessionStore
from sentientos.governed_local_model_invocation import LocalModelInvocationReceipt
from sentientos.installation_state import InstallationIdentity

pytestmark = pytest.mark.no_legacy_skip


class Inference:
    def __init__(self, identity=None, statuses=None):
        self.identity = identity or {"installation_identity": "install-1",
            "activation_state_semantic_digest": "state-a", "activation_generation": 1,
            "activation_receipt_id": "activation-a", "model_id": "model-a", "artifact_sha256": "sha-a",
            "runtime_id": "runtime-a", "authority_map_digest": "authority-a",
            "observed_loaded_model_identity": {"posture": "production"}}
        self.calls = []; self.statuses = iter(statuses or ["admitted_completed"] * 10)
        self.receipts = {}
    def current_conversation_model_identity(self): return dict(self.identity)
    def generate(self, **kwargs):
        self.calls.append(kwargs); status = next(self.statuses)
        if status != "admitted_completed":
            return SimpleNamespace(status=status, output_text=None)
        output = "answer"
        loaded_identity = dict(self.identity.get("observed_loaded_model_identity", self.identity))
        runtime = {"status": "fixture_not_runtime_observation",
            "reason_code": "unit_service_contract_only"}
        linkage = {**kwargs["caller_linkage"], "software_generation_attribution": runtime}
        request_id = kwargs["correlation_id"]
        receipt_id = f"receipt-{len(self.receipts) + 1}"
        receipt_digest = f"digest-{len(self.receipts) + 1}"
        output_lineage = {"status": "exact_invocation_output_match",
            "invocation_output_digest": chat_service.digest_payload({"output": output}),
            "transcript_text_digest": chat_service.digest_payload({"text": output}),
            "output_truncated": False}
        request = {"request_id": request_id, "active_model_identity": loaded_identity,
            "upstream_evidence": {"current_serving_lifetime": {
                **self.identity, "caller_context": {
                    "session_id": kwargs["caller_linkage"]["session_id"],
                    "user_turn_id": kwargs["caller_linkage"]["user_turn_id"]}}},
            "linkage": linkage}
        self.receipts[receipt_id] = {"receipt_id": receipt_id,
            "receipt_digest": receipt_digest, "request_id": request_id,
            "serving_identity": dict(self.identity), "loaded_model_identity": loaded_identity,
            "software_generation_attribution": runtime,
            "caller_linkage": dict(kwargs["caller_linkage"]),
            "assistant_output_lineage": output_lineage, "output": output}
        return SimpleNamespace(status=status, output_text=output,
            output_digest=chat_service.digest_payload({"output": output}), output_truncated=False,
            request=request, receipt_id=receipt_id, receipt_digest=receipt_digest)

    def verify_stored_chat_invocation(self, *, receipt_id, receipt_digest, session_id,
                                      user_turn_id, assistant_text=None, **_kwargs):
        saved = self.receipts[receipt_id]
        if (saved["receipt_digest"] != receipt_digest
                or saved["caller_linkage"].get("session_id") != session_id
                or saved["caller_linkage"].get("user_turn_id") != user_turn_id
                or (assistant_text is not None and saved["output"] != assistant_text)):
            raise ValueError("fixture_receipt_binding_mismatch")
        return dict(saved)


def service(tmp_path, inference):
    return chat_service.PersistentConversationService(inference=inference,
        session_store=ConversationSessionStore(tmp_path / "conversations"),
        memory_store=CanonicalMemoryStore(tmp_path / "memory"))


def test_production_chat_requires_process_generation_handoff_before_custody(monkeypatch, tmp_path):
    events = []
    handle = object()
    class Registry:
        def open(self, identity): events.append(("open", identity)); return handle
    monkeypatch.setattr(chat_service.InstallationStateRegistry, "system", classmethod(lambda cls: events.append("system") or Registry()))
    class Serving:
        def __init__(self, actual_handle, kernel): assert actual_handle is handle; events.append("controller")
        def establish(self, *, operation_id): events.append(("establish", operation_id))
        def close(self): events.append("close")
    class Bridge(Inference):
        def __init__(self, serving): super().__init__(); events.append("bridge")
    monkeypatch.setattr(chat_service, "ProductionServingController", Serving)
    monkeypatch.setattr(chat_service, "ProductionServingInferenceController", Bridge)
    monkeypatch.setattr(chat_service, "sentientos_data_dir", lambda: tmp_path)
    chat_service.close_production_chat()
    with pytest.raises(RuntimeError, match="chat_process_generation_handoff_required"):
        chat_service.configure_production_chat(installation_identity="Install-1", serving_operation_id="serve-explicit")
    assert events == []


def test_invalid_installation_identity_fails_before_custody(monkeypatch):
    monkeypatch.setattr(chat_service.InstallationStateRegistry, "system", classmethod(lambda cls: pytest.fail("custody opened")))
    with pytest.raises(ValueError, match="invalid_installation_identity"):
        chat_service.configure_production_chat(installation_identity="../bad", serving_operation_id="serve-1")


def test_successful_turn_and_second_turn_have_distinct_inference_correlations(tmp_path):
    inference = Inference(); app = service(tmp_path, inference)
    first = app.chat("one")
    second = app.chat("two", session_id=first.session_id)
    assert first.response == second.response == "answer"
    assert len(inference.calls) == 2
    correlations = [call["correlation_id"] for call in inference.calls]
    assert correlations[0] != correlations[1]
    assert all(value.startswith(f"chat:{first.session_id}:") for value in correlations)
    base_linkage = {"session_id", "user_turn_id", "conversation_context_snapshot_digest",
        "memory_retrieval_snapshot_digest"}
    assert set(inference.calls[0]["caller_linkage"]) == base_linkage
    assert set(inference.calls[1]["caller_linkage"]) == base_linkage | {
        "verified_predecessor_invocation", "verified_predecessor_runtime_handoff_digest",
        "verified_predecessor_runtime_software_generation_digest"}


def test_conversation_identity_change_uses_verified_predecessor_lineage(tmp_path):
    inference = Inference(); app = service(tmp_path, inference)
    first = app.chat("one")
    inference.identity = {**inference.identity, "activation_generation": 2,
        "activation_state_semantic_digest": "state-b", "activation_predecessor_state_digest": "state-a",
        "observed_loaded_model_identity": {"posture": "successor"}}
    second = app.chat("two", session_id=first.session_id)
    assert second.session_id == first.session_id
    stored = app.sessions.load(first.session_id)
    assistants = [turn for turn in stored["turns"] if turn["role"] == "assistant"]
    assert len(assistants) == 2
    assert assistants[-1]["linkage"]["model_identity_continuity_posture"] == (
        "activation_predecessor_bound_to_prior_observed_invocation")


@pytest.mark.parametrize("status", ["denied", "deferred", "quarantined", "serving_lifetime_stale_after_generation", "backend_failure"])
def test_failure_preserves_user_turn_without_assistant_or_fallback(tmp_path, status):
    inference = Inference(statuses=[status]); app = service(tmp_path, inference)
    with pytest.raises(RuntimeError, match="governed_inference_not_completed"):
        app.chat("important")
    sessions = app.sessions.list_recent(); assert len(sessions) == 1
    stored = app.sessions.load(sessions[0]["session_id"])
    assert [turn["role"] for turn in stored["turns"]] == ["user"]
    assert len(inference.calls) == 1


def test_conversation_service_has_no_raw_execution_escape_hatch(tmp_path):
    app = service(tmp_path, Inference())
    assert not any(hasattr(app, name) for name in ("model", "invoker", "backend", "process", "serving"))
