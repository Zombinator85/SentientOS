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
        self.identity = identity or {"activation_state_semantic_digest": "state-a", "activation_generation": 1,
            "activation_receipt_id": "activation-a", "model_id": "model-a", "artifact_sha256": "sha-a",
            "runtime_id": "runtime-a", "authority_map_digest": "authority-a",
            "observed_loaded_model_identity": {"posture": "production"}}
        self.calls = []; self.statuses = iter(statuses or ["admitted_completed"] * 10)
    def current_conversation_model_identity(self): return dict(self.identity)
    def generate(self, **kwargs):
        self.calls.append(kwargs); status = next(self.statuses)
        return SimpleNamespace(status=status, output_text="answer" if status == "admitted_completed" else None,
            request={"request_id": kwargs["correlation_id"]}, receipt_digest="receipt")


def service(tmp_path, inference):
    return chat_service.PersistentConversationService(inference=inference,
        session_store=ConversationSessionStore(tmp_path / "conversations"),
        memory_store=CanonicalMemoryStore(tmp_path / "memory"))


def test_explicit_hardened_production_chat_composition_uses_system_custody_and_operation(monkeypatch, tmp_path):
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
    chat_service.configure_production_chat(installation_identity="Install-1", serving_operation_id="serve-explicit")
    assert events[:4] == ["system", ("open", InstallationIdentity.parse("install-1")), "controller", ("establish", "serve-explicit")]
    assert isinstance(chat_service._get_conversation_service(), chat_service.PersistentConversationService)
    chat_service.close_production_chat()
    assert events[-1] == "close"


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
    for call in inference.calls:
        assert set(call["caller_linkage"]) == {"session_id", "user_turn_id", "conversation_context_snapshot_digest", "memory_retrieval_snapshot_digest"}


def test_conversation_identity_change_refuses_existing_but_allows_new(tmp_path):
    inference = Inference(); app = service(tmp_path, inference)
    first = app.chat("one")
    inference.identity = {**inference.identity, "activation_generation": 2, "activation_state_semantic_digest": "state-b"}
    with pytest.raises(ValueError, match="session_model_identity_mismatch"):
        app.chat("two", session_id=first.session_id)
    stored = app.sessions.load(first.session_id)
    assert [turn["role"] for turn in stored["turns"]] == ["user", "assistant"]
    replacement = app.chat("new")
    assert replacement.session_id != first.session_id


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
