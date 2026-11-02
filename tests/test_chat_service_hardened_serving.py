# mypy: ignore-errors
from __future__ import annotations

from types import SimpleNamespace
import json
import time

import pytest

from sentientos import chat_service
from avatar_state import AvatarStateEmitter
from control_plane import Decision, ReasonCode, RequestType
from control_plane.records import AuthorizationRecord
from control_plane.task_admission import AdmissionResponse
from sentientos.canonical_memory import CanonicalMemoryStore
from sentientos.chat_avatar_output import ChatAvatarOutputController
from sentientos.conversation_session import ConversationSessionStore
from sentientos.governed_local_model_invocation import LocalModelInvocationReceipt
from sentientos.installation_state import InstallationIdentity
from speech_emitter import SpeechEmitter

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
        self.workload_mode = "normal"
        self.game_process_names = ()
    def set_workload_mode(self, mode, game_process_names=()):
        self.workload_mode = mode; self.game_process_names = tuple(game_process_names); return mode
    def current_workload_mode(self): return self.workload_mode
    def current_workload_state(self):
        return {"mode": self.workload_mode, "effective_mode": self.workload_mode,
            "observation_status": "not_requested"}
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
                **self.identity, "workload_mode": self.workload_mode, "caller_context": {
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


def service(tmp_path, inference, avatar_output=None, speech_output=None):
    return chat_service.PersistentConversationService(inference=inference,
        session_store=ConversationSessionStore(tmp_path / "conversations"),
        memory_store=CanonicalMemoryStore(tmp_path / "memory"),
        avatar_output=avatar_output, speech_output=speech_output)


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


def test_chat_workload_mode_is_process_local_and_operator_switchable(tmp_path):
    inference = Inference()
    app = service(tmp_path, inference)

    assert app.current_workload_mode() == "normal"
    assert app.set_workload_mode("gaming") == "gaming"
    assert app.current_workload_mode() == "gaming"
    assert app.set_workload_mode("normal") == "normal"


def test_chat_workload_mode_api_rejects_unsupported_mode(tmp_path):
    from fastapi.testclient import TestClient

    inference = Inference()
    chat_service._CONVERSATION_SERVICE = service(tmp_path, inference)
    try:
        with TestClient(chat_service.APP) as client:
            page = client.get("/")
            assert page.status_code == 200
            assert 'id="workload-mode"' in page.text
            assert 'id="game-process-names"' in page.text
            assert "async function refreshWorkloadStatus()" in page.text
            assert "setInterval(refreshWorkloadStatus, 5000)" in page.text
            assert "sentientos_workload_preference_v1" in page.text
            assert "function readWorkloadPreference()" in page.text
            assert "function saveWorkloadPreference(mode, gameProcessNames)" in page.text
            assert "preference.mode === control.value" in page.text
            assert client.get("/avatar-output").json()=={"configured":False,"enabled":False}
            assert client.get("/workload-mode").json()["mode"] == "normal"
            assert client.post("/workload-mode", json={"mode": "gaming"}).json()["mode"] == "gaming"
            automatic = client.post("/workload-mode", json={"mode": "automatic",
                "game_process_names": ["ExampleGame.exe"]})
            response = client.post("/workload-mode", json={"mode": "other"})
        assert automatic.status_code == 200
        assert inference.game_process_names == ("ExampleGame.exe",)
        assert response.status_code == 400
        assert inference.workload_mode == "automatic"
    finally:
        chat_service._CONVERSATION_SERVICE = None


def test_local_chat_can_explicitly_enable_session_scoped_visual_avatar_output(tmp_path):
    from fastapi.testclient import TestClient

    admission_calls=[]
    def approve(**kwargs):
        admission_calls.append(dict(kwargs))
        record=AuthorizationRecord.create(request_type=kwargs["request_type"],
            requester_id=kwargs["requester_id"],intent_hash=kwargs["intent_hash"],
            context_hash=kwargs["context_hash"],policy_version=kwargs["policy_version"],
            decision=Decision.ALLOW,reason=ReasonCode.OK,metadata=kwargs["metadata"])
        return AdmissionResponse(Decision.ALLOW,ReasonCode.OK,record)

    target=tmp_path/"avatar_state.json"
    avatar_output=ChatAvatarOutputController(SpeechEmitter(AvatarStateEmitter(target)),
        admission_provider=approve)
    inference=Inference()
    app=service(tmp_path,inference,avatar_output)
    session_id=app.create_session()
    chat_service._CONVERSATION_SERVICE=app
    try:
        with TestClient(chat_service.APP) as client:
            page=client.get("/")
            assert page.status_code==200
            assert "Show replies in companion" in page.text
            assert "Visual text and a nod only; no audio." in page.text
            assert client.get("/avatar-output").json()=={"configured":True,"enabled":False}
            assert client.post("/avatar-output",json={"session_id":session_id,"enabled":True}).json()["enabled"] is True
            assert client.get("/avatar-output",params={"session_id":session_id}).json()["enabled"] is True
            response=client.post("/chat",json={"message":"hello","session_id":session_id,"request_id":"chat-1"})
            assert response.status_code==200,response.text
            data=response.json()
            state=json.loads(target.read_text(encoding="utf-8"))
            assert state["current_phrase"]==data["response"]=="answer"
            assert state["speaking"] is False
            assert state["viseme_timeline"]==[]
            assert state["metadata"]["session_id"]==session_id
            assert state["metadata"]["turn_id"]==data["turn_id"]
            assert state["metadata"]["output_digest"]==chat_service.digest_payload({"text":"answer"})
            assert state["metadata"]["workload_mode"]=="normal"
            assert client.post("/avatar-output",json={"session_id":session_id,"enabled":False}).json()["enabled"] is False
        assert len(admission_calls)==3
        assert all(call["request_type"] is RequestType.AVATAR_EMISSION for call in admission_calls)
    finally:
        chat_service._CONVERSATION_SERVICE=None


def test_verified_gaming_workload_mode_reaches_enabled_avatar_state(tmp_path):
    def approve(**kwargs):
        record = AuthorizationRecord.create(request_type=kwargs["request_type"],
            requester_id=kwargs["requester_id"], intent_hash=kwargs["intent_hash"],
            context_hash=kwargs["context_hash"], policy_version=kwargs["policy_version"],
            decision=Decision.ALLOW, reason=ReasonCode.OK, metadata=kwargs["metadata"])
        return AdmissionResponse(Decision.ALLOW, ReasonCode.OK, record)

    target = tmp_path / "avatar_state.json"
    avatar_output = ChatAvatarOutputController(SpeechEmitter(AvatarStateEmitter(target)),
        admission_provider=approve)
    inference = Inference()
    inference.workload_mode = "gaming"
    app = service(tmp_path, inference, avatar_output)
    session_id = app.create_session()
    try:
        assert avatar_output.set_enabled(session_id, True)["enabled"] is True
        response = app.chat("hello", session_id=session_id)
        state = json.loads(target.read_text(encoding="utf-8"))
        assert state["current_phrase"] == response.response == "answer"
        assert state["metadata"]["workload_mode"] == "gaming"
    finally:
        avatar_output.close()


def test_enabled_avatar_tracks_live_workload_changes_without_another_chat_turn(tmp_path):
    def approve(**kwargs):
        record = AuthorizationRecord.create(request_type=kwargs["request_type"],
            requester_id=kwargs["requester_id"], intent_hash=kwargs["intent_hash"],
            context_hash=kwargs["context_hash"], policy_version=kwargs["policy_version"],
            decision=Decision.ALLOW, reason=ReasonCode.OK, metadata=kwargs["metadata"])
        return AdmissionResponse(Decision.ALLOW, ReasonCode.OK, record)

    target = tmp_path / "avatar_state.json"
    avatar_output = ChatAvatarOutputController(SpeechEmitter(AvatarStateEmitter(target)),
        admission_provider=approve)
    inference = Inference()
    app = service(tmp_path, inference, avatar_output)
    session_id = app.create_session()
    try:
        assert app.set_avatar_output_enabled(session_id, True)["enabled"] is True
        response = app.chat("hello", session_id=session_id)
        assert response.response == "answer"

        for mode in ("gaming", "normal"):
            inference.workload_mode = mode
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                state = json.loads(target.read_text(encoding="utf-8"))
                if state.get("metadata", {}).get("workload_mode") == mode:
                    break
                time.sleep(0.05)
            else:
                pytest.fail(f"avatar workload mode did not update to {mode}")
            assert state["current_phrase"] == "answer"

        assert app.set_avatar_output_enabled(session_id, False)["enabled"] is False
        assert not app._avatar_workload_sync
    finally:
        app.close_outputs()


def test_chat_reply_cannot_restore_stale_workload_mode_after_foreground_change(tmp_path):
    def approve(**kwargs):
        record = AuthorizationRecord.create(request_type=kwargs["request_type"],
            requester_id=kwargs["requester_id"], intent_hash=kwargs["intent_hash"],
            context_hash=kwargs["context_hash"], policy_version=kwargs["policy_version"],
            decision=Decision.ALLOW, reason=ReasonCode.OK, metadata=kwargs["metadata"])
        return AdmissionResponse(Decision.ALLOW, ReasonCode.OK, record)

    class ForegroundChangesDuringGeneration(Inference):
        def generate(self, **kwargs):
            receipt = super().generate(**kwargs)
            self.workload_mode = "gaming"
            return receipt

    target = tmp_path / "avatar_state.json"
    avatar_output = ChatAvatarOutputController(SpeechEmitter(AvatarStateEmitter(target)),
        admission_provider=approve)
    inference = ForegroundChangesDuringGeneration()
    app = service(tmp_path, inference, avatar_output)
    session_id = app.create_session()
    try:
        assert app.set_avatar_output_enabled(session_id, True)["enabled"] is True
        assert app.chat("hello", session_id=session_id).response == "answer"
        state = json.loads(target.read_text(encoding="utf-8"))
        assert state["metadata"]["workload_mode"] == "gaming"
    finally:
        app.close_outputs()


def test_chat_speech_output_is_published_only_through_configured_controller(tmp_path):
    class SpeechOutput:
        def __init__(self): self.calls = []; self.enabled = set()
        def set_enabled(self, session_id, enabled):
            if enabled: self.enabled.add(session_id)
            else: self.enabled.discard(session_id)
            return {"session_id": session_id, "enabled": enabled}
        def state(self, session_id): return {"configured": True, "backend_available": True,
            "enabled": session_id in self.enabled, "playback_status": "idle"}
        def publish_response(self, **kwargs): self.calls.append(kwargs); return {"status": "queued"}
        def close(self): pass

    from fastapi.testclient import TestClient

    inference = Inference()
    speech = SpeechOutput()
    app = service(tmp_path, inference, speech_output=speech)
    session_id = app.create_session()
    chat_service._CONVERSATION_SERVICE = app
    try:
        with TestClient(chat_service.APP) as client:
            page = client.get("/")
            assert "Speak replies with local voice" in page.text
            assert client.get("/speech-output", params={"session_id": session_id}).json()["enabled"] is False
            enabled = client.post("/speech-output", json={"session_id": session_id, "enabled": True})
            assert enabled.status_code == 200 and enabled.json()["enabled"] is True
            response = client.post("/chat", json={
                "message": "hello", "session_id": session_id, "request_id": "speech-chat-1"})
            assert response.status_code == 200, response.text
            data = response.json()
            assert len(speech.calls) == 1
            call = speech.calls[0]
            assert call["session_id"] == session_id
            assert call["turn_id"] == data["turn_id"]
            assert call["text"] == data["response"]
            assert len(call["output_digest"]) == 64
            assert client.post("/speech-output", json={
                "session_id": session_id, "enabled": False}).json()["enabled"] is False
    finally:
        chat_service._CONVERSATION_SERVICE = None


def test_avatar_output_server_requires_loopback_binding(monkeypatch):
    monkeypatch.setattr(chat_service, "_CONVERSATION_SERVICE",
        SimpleNamespace(avatar_output_state=lambda _session_id: {"configured": True},
                        speech_output_state=lambda _session_id: {"configured": False}))
    assert chat_service._is_loopback_host("127.0.0.1") is True
    assert chat_service._is_loopback_host("::1") is True
    assert chat_service._is_loopback_host("localhost") is True
    assert chat_service._is_loopback_host("0.0.0.0") is False
    assert chat_service._is_loopback_host("192.168.1.12") is False
    with pytest.raises(RuntimeError, match="chat_avatar_output_requires_loopback_host"):
        chat_service.run(host="0.0.0.0")


def test_speech_output_server_requires_loopback_binding(monkeypatch):
    monkeypatch.setattr(chat_service, "_CONVERSATION_SERVICE", SimpleNamespace(
        avatar_output_state=lambda _session_id: {"configured": False},
        speech_output_state=lambda _session_id: {"configured": True}))
    with pytest.raises(RuntimeError, match="chat_speech_output_requires_loopback_host"):
        chat_service.run(host="0.0.0.0")


def test_production_composition_closes_avatar_before_serving_and_resource_owner():
    events=[]
    service=SimpleNamespace(close_outputs=lambda: events.append("outputs"))
    serving=SimpleNamespace(close=lambda: events.append("serving"))
    owner=SimpleNamespace(close=lambda: events.append("resource_owner"))
    chat_service.ProductionChatComposition(service, serving, owner).close()
    assert events == ["outputs", "serving", "resource_owner"]


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
