# mypy: ignore-errors
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import time
from types import SimpleNamespace

import pytest

from sentientos import chat_service
from avatar_state import AvatarStateEmitter
from control_plane import Decision, ReasonCode, RequestType
from control_plane.records import AuthorizationRecord
from control_plane.task_admission import AdmissionResponse
from sentientos.canonical_memory import CanonicalMemoryStore
from sentientos.chat_avatar_output import ChatAvatarOutputController
from sentientos.gaming_companion_core_runtime import WSLCoreAvatarOutputSession
from sentientos.foreground_game_bridge import BridgeForegroundGameDetector
from sentientos.gaming_companion_bridge import CompanionBridgeReceiver
from sentientos.gaming_companion_bridge_runtime import CompanionBridgeLoopbackRuntime
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
            "invocation_output_text_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
            "transcript_text_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
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


def service(tmp_path, inference, avatar_output=None, speech_output=None, screen_observer=None):
    return chat_service.PersistentConversationService(inference=inference,
        session_store=ConversationSessionStore(tmp_path / "conversations"),
        memory_store=CanonicalMemoryStore(tmp_path / "memory"),
        avatar_output=avatar_output, speech_output=speech_output,
        screen_observer=screen_observer)


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


def test_production_chat_owns_wsl_core_avatar_session_and_uses_its_emitter(monkeypatch, tmp_path):
    events = []

    class Handle:
        root = tmp_path / "installation"
        def fixed_object(self, _name):
            return SimpleNamespace(path=self.root / "chat" / "conversations")
        def ensure_directory(self, _directory): events.append("conversation_custody_ready")

    handle = Handle()
    monkeypatch.setattr(chat_service, "open_chat_process_handoff",
        lambda **_kwargs: (handle, {}))

    class Serving:
        def __init__(self, _handle, _kernel): pass
        def establish(self, **_kwargs): events.append("serving_established")
        def close(self): events.append("serving_closed")
        def serving_is_current(self): return True

    class InferenceBridge:
        def __init__(self, *_args, **_kwargs): pass

    class AdmissionOwner:
        def observe_verified_game_performance(self, _observation): return True

    admission_owner = AdmissionOwner()
    bridge_runtime = CompanionBridgeLoopbackRuntime(
        receiver=CompanionBridgeReceiver(source_keys={"windows-edge": b"x" * 32},
            expected_generations={"windows-edge": "generation-1"}),
        acknowledgment_source_id="core", acknowledgment_generation_id="core-1",
        acknowledgment_key=b"y" * 32)
    detector = BridgeForegroundGameDetector(runtime=bridge_runtime,
        source_id="windows-edge", generation_id="generation-1")

    monkeypatch.setattr(chat_service, "ProductionServingController", Serving)
    monkeypatch.setattr(chat_service, "ProductionServingInferenceController", InferenceBridge)
    monkeypatch.setattr(chat_service, "sentientos_data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(chat_service, "sentientos_memory_dir", lambda _root=None: tmp_path / "memory")

    class Sender:
        def close(self): events.append("avatar_session_closed")

    session = WSLCoreAvatarOutputSession.__new__(WSLCoreAvatarOutputSession)
    session.emitter = SimpleNamespace(
        emit_display_text=lambda *_args, **_kwargs: {},
        emit_phrase=lambda *_args, **_kwargs: {},
        emit_idle=lambda *_args, **_kwargs: {})
    session._sender = Sender()
    session._closed = False

    chat_service.close_production_chat()
    chat_service.configure_production_chat(
        installation_identity="Install-1", serving_operation_id="serve-1",
        runtime_handoff_id="handoff-1", avatar_output_session=session,
        foreground_game_detector=detector, control_plane_kernel=admission_owner)
    composition = chat_service._PRODUCTION_COMPOSITION
    assert composition is not None
    assert composition.service._avatar_output is not None
    assert isinstance(composition.service._avatar_output, ChatAvatarOutputController)
    assert composition._avatar_output_owner is session
    assert detector._game_performance_observer.__self__ is admission_owner
    chat_service.close_production_chat()
    assert events[-1] == "avatar_session_closed"


def test_invalid_installation_identity_fails_before_custody(monkeypatch):
    monkeypatch.setattr(chat_service.InstallationStateRegistry, "system", classmethod(lambda cls: pytest.fail("custody opened")))
    with pytest.raises(ValueError, match="invalid_installation_identity"):
        chat_service.configure_production_chat(installation_identity="../bad", serving_operation_id="serve-1")


def test_successful_turn_and_second_turn_have_distinct_inference_correlations(tmp_path):
    inference = Inference(); app = service(tmp_path, inference)
    first = app.chat("one")
    second = app.chat("two", session_id=first.session_id)
    assert first.response == second.response == "answer"
    expected_text_digest = hashlib.sha256(b"answer").hexdigest()
    assert first.response_diagnostics["invocation_output_text_sha256"] == expected_text_digest
    assert first.response_diagnostics["transcript_text_sha256"] == expected_text_digest
    assert first.response_diagnostics["delivery_text_sha256"] == expected_text_digest
    assert len(inference.calls) == 2
    correlations = [call["correlation_id"] for call in inference.calls]
    assert correlations[0] != correlations[1]
    assert all(value.startswith(f"chat:{first.session_id}:") for value in correlations)
    base_linkage = {"session_id", "user_turn_id", "chat_response_style",
        "recent_session_recall", "conversation_context_snapshot_digest",
        "memory_retrieval_snapshot_digest"}
    assert set(inference.calls[0]["caller_linkage"]) == base_linkage
    assert inference.calls[0]["caller_linkage"]["chat_response_style"] == "default"
    assert set(inference.calls[1]["caller_linkage"]) == base_linkage | {
        "verified_predecessor_invocation", "verified_predecessor_runtime_handoff_digest",
        "verified_predecessor_runtime_software_generation_digest"}


def test_idempotent_replay_preserves_verified_answer_lineage(tmp_path):
    inference = Inference()
    app = service(tmp_path, inference)
    session_id = app.create_session()
    first = app.chat("same request", session_id=session_id, request_id="lineage-replay")
    replay = app.chat("same request", session_id=session_id, request_id="lineage-replay")
    assert replay.turn_id == first.turn_id
    assert replay.response == first.response
    assert replay.response_diagnostics == first.response_diagnostics
    assert len(inference.calls) == 1



def test_nonstreaming_inference_keeps_runtime_status_responsive(monkeypatch):
    import asyncio
    import threading

    entered = threading.Event()
    release = threading.Event()
    status_checks = []

    class BlockingService:
        _inference = object()

        def chat(self, message, **kwargs):
            entered.set()
            assert release.wait(2)
            return chat_service.ChatResponse(
                response="answer", session_id="session", turn_id="turn",
                context={}, retention={})

        def current_workload_state(self):
            return {"effective_mode": "gaming"}

        def screen_observation_configured(self):
            return False

        def speech_output_state(self, session_id):
            return {"configured": True, "backend_available": True}

    monkeypatch.setattr(chat_service, "_get_conversation_service",
                        lambda: BlockingService())
    monkeypatch.setattr(chat_service, "production_chat_ready", lambda: True)

    async def exercise_concurrent_runtime_status():
        async def monitor():
            while not release.is_set():
                if entered.is_set():
                    status = await chat_service.runtime_status_endpoint()
                    status_checks.append(status)
                await asyncio.sleep(0.01)

        monitor_task = asyncio.create_task(monitor())
        release_timer = threading.Timer(0.25, release.set)
        release_timer.start()
        try:
            response = await chat_service.chat_endpoint(
                chat_service.ChatRequest(message="hold inference"))
            assert response.response == "answer"
        finally:
            release.set()
            release_timer.cancel()
            await monitor_task

    asyncio.run(exercise_concurrent_runtime_status())
    assert len(status_checks) >= 3


def test_saved_transcript_turns_include_display_safe_answer_lineage(
        monkeypatch, tmp_path):
    import asyncio

    inference = Inference()
    app = service(tmp_path, inference)
    first = app.chat("show saved answer")
    monkeypatch.setattr(chat_service, "_get_conversation_service", lambda: app)
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
    payload = asyncio.run(chat_service.inspect_session_turns(
        first.session_id, request))

    assert payload["total_turns"] == 2
    user_turn, assistant_turn = payload["turns"]
    assert "response_diagnostics" not in user_turn
    assert "linkage" not in assistant_turn
    diagnostics = assistant_turn["response_diagnostics"]
    expected = hashlib.sha256(b"answer").hexdigest()
    assert diagnostics["status"] == "exact_invocation_output_match"
    assert diagnostics["invocation_output_text_sha256"] == expected
    assert diagnostics["transcript_text_sha256"] == expected
    assert diagnostics["saved_transcript_text_sha256"] == expected
    assert diagnostics["delivery_text_sha256"] == expected
    assert diagnostics["delivery_text_digest_source"] == "computed_from_saved_transcript"
    assert diagnostics["transcript_text_digest_source"] == "stored_invocation_lineage"

    legacy = chat_service._saved_transcript_response_diagnostics({
        "role": "assistant", "text": "historical answer", "linkage": {}})
    legacy_digest = hashlib.sha256(b"historical answer").hexdigest()
    assert legacy["status"] == "historical_lineage_unavailable"
    assert legacy["transcript_text_sha256"] == legacy_digest
    assert legacy["transcript_text_digest_source"] == "computed_from_saved_transcript"
    assert legacy["delivery_text_sha256"] == legacy_digest
    assert legacy["delivery_text_digest_source"] == "computed_from_saved_transcript"
    assert "invocation_output_text_sha256" not in legacy

    screen = chat_service._saved_transcript_response_diagnostics({
        "role": "assistant", "text": "answer", "linkage": {
            "screen_observation_provenance": {
                "captured_at": "2026-11-07T13:05:21Z",
                "text_status": "available", "backend": "tesseract+local_vision",
                "component_statuses": {
                    "ocr": "unavailable", "vision": "available"},
                "component_failure_codes": {"ocr": "game_screen_ocr_timeout"},
                "raw_frame_retained": False,
                "text": "must not be exposed",
            },
        },
    })
    assert screen["screen_observation"]["component_statuses"] == {
        "ocr": "unavailable", "vision": "available"}
    assert screen["screen_observation"]["component_failure_codes"] == {
        "ocr": "game_screen_ocr_timeout"}
    assert screen["screen_observation"]["raw_frame_retained"] is False
    assert "text" not in screen["screen_observation"]
    resident_with_evidence = chat_service._saved_transcript_response_diagnostics({
        "role": "assistant", "text": "answer", "linkage": {
            "response_origin": "resident_developmental_cognition",
            "cognition_observation_id": "observation-1",
            "cognition_observation_digest": "a" * 64,
            "response_digest": "b" * 64,
            "screen_observation_provenance": {"capture_digest": "c" * 64},
        },
    })
    assert resident_with_evidence["operator_feedback_available"] is True
    resident_without_capture = chat_service._saved_transcript_response_diagnostics({
        "role": "assistant", "text": "answer", "linkage": {
            "response_origin": "resident_developmental_cognition",
            "cognition_observation_id": "observation-1",
            "cognition_observation_digest": "a" * 64,
            "response_digest": "b" * 64,
        },
    })
    assert resident_without_capture["operator_feedback_available"] is False


def test_new_chat_turn_interrupts_previous_local_speech(tmp_path):
    class SpeechOutput:
        def __init__(self): self.interrupted = []; self.published = []
        def interrupt(self, session_id):
            self.interrupted.append(session_id); return {"status": "interrupted"}
        def publish_response(self, **kwargs):
            self.published.append(kwargs); return {"status": "queued"}
    speech = SpeechOutput()
    app = service(tmp_path, Inference(), speech_output=speech)
    first = app.chat("first message")
    second = app.chat("follow-up", session_id=first.session_id)
    assert second.session_id == first.session_id
    assert speech.interrupted == [first.session_id, first.session_id]
    assert [item["turn_id"] for item in speech.published] == [first.turn_id, second.turn_id]


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
        assert [call["metadata"].get("approval_method") for call in admission_calls] == [
            "local_chat_ui", "session_grant_workload_sync", "session_grant",
            "local_chat_ui_revoke"]
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


def test_gaming_companion_vertical_fixture_survives_forwarding_and_restart(tmp_path):
    from godot_avatar_receiver import AvatarStateForwarder

    def approve(**kwargs):
        record = AuthorizationRecord.create(request_type=kwargs["request_type"],
            requester_id=kwargs["requester_id"], intent_hash=kwargs["intent_hash"],
            context_hash=kwargs["context_hash"], policy_version=kwargs["policy_version"],
            decision=Decision.ALLOW, reason=ReasonCode.OK, metadata=kwargs["metadata"])
        return AdmissionResponse(Decision.ALLOW, ReasonCode.OK, record)

    target = tmp_path / "avatar_state.json"
    avatar_output = ChatAvatarOutputController(
        SpeechEmitter(AvatarStateEmitter(target)), admission_provider=approve)
    inference = Inference()
    app = service(tmp_path, inference, avatar_output)
    session_id = app.create_session()
    try:
        assert app.set_workload_mode("gaming") == "gaming"
        assert app.set_avatar_output_enabled(session_id, True)["enabled"] is True
        response = app.chat("Quick check-in", session_id=session_id)
        assert response.response == "answer"

        state = json.loads(target.read_text(encoding="utf-8"))
        assert state["current_phrase"] == response.response
        assert state["metadata"]["workload_mode"] == "gaming"
        assert state["metadata"]["output_mode"] == "chat_response_visual_only"

        forwarded = AvatarStateForwarder(target)._read_state()
        assert forwarded is not None
        assert forwarded["workload_mode"] == "gaming"
        assert forwarded["phrase"]["text"] == response.response

        app.set_workload_mode("normal")
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            state = json.loads(target.read_text(encoding="utf-8"))
            if state.get("metadata", {}).get("workload_mode") == "normal":
                break
            time.sleep(0.05)
        else:
            pytest.fail("avatar did not receive normal workload mode")
        assert state["current_phrase"] == response.response
    finally:
        app.close_outputs()

    restarted = service(tmp_path, Inference())
    try:
        restored = restarted.sessions.load(session_id)
        assert [turn["role"] for turn in restored["turns"]] == ["user", "assistant"]
        assert restored["turns"][-1]["text"] == response.response
    finally:
        restarted.close_outputs()


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
            assert 'id="local-runtime-status"' in page.text
            assert 'id="response-integrity"' in page.text
            assert "Answer lineage details" in page.text
            assert "Saved answer integrity" in page.text
            assert "saved_transcript_text_sha256" in page.text
            assert "API-delivered text SHA-256" in page.text
            assert "Local visual description" in page.text
            assert "Local visual-description failure" in page.text
            assert "Local OCR" in page.text
            assert "Local OCR failure" in page.text
            assert "delivery_text_digest_source" in page.text
            assert 'displayedDigest === transcriptDigest' in page.text
            assert 'displayedDigest === deliveryDigest' in page.text
            assert "API-delivered transcript text differs" in page.text
            assert "event.failure_code" in page.text
            assert "return focus to the approved application within the configured foreground wait" in page.text
            assert "The approved application must already be foreground when you send." in page.text
            assert "Uncheck the screen option for text only" in page.text
            assert "String.fromCharCode(13)" in page.text
            assert "new URLSearchParams(window.location.search)" in page.text
            assert "requestedSessionIdIsValid" in page.text
            assert "Watched game is foreground; low-work mode active" in page.text
            assert "Watched game is running in background; focus it and verify the screen-capture executable allowlist" in page.text
            assert "No watched game process found; check the executable names" in page.text
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
    avatar_owner=SimpleNamespace(close=lambda: events.append("avatar_output_owner"))
    chat_service.ProductionChatComposition(service, serving, owner,
        avatar_output_owner=avatar_owner).close()
    assert events == ["outputs", "serving", "resource_owner", "avatar_output_owner"]


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


def test_developmental_cycle_adds_current_consequence_to_existing_bridge(tmp_path):
    events = []
    screen = {"modality": "screen", "capture_digest": "sha256:" + "a" * 64}
    consequence = {"source_kind": "embodiment", "digest": "sha256:" + "b" * 64}
    record = {
        "role": "assistant", "turn_id": "turn-" + "1" * 24,
        "text": "I will nod.", "linkage": {
            "response_origin": "resident_developmental_cognition",
            "source_user_turn_id": "turn-" + "2" * 24,
            "response_digest": "c" * 64,
        },
    }
    source = {"role": "user", "turn_id": "turn-" + "2" * 24, "text": "Hello."}

    class Sessions:
        @contextmanager
        def serialize_chat_requests(self, _session_id):
            yield
        def load(self, _session_id):
            return {"turns": [source, record]}

    class Observer:
        def observe_question(self, question):
            events.append(("screen", question))
            return screen

    class Bridge:
        def respond(self, **_kwargs):
            pass
        def developmental_cycle_available(self):
            return True
        def verify_committed_response(self, **_kwargs):
            return True
        def run_developmental_cycle(self, **kwargs):
            events.append(("cycle", kwargs))
            return SimpleNamespace(status="completed", tick_id=kwargs["tick_id"],
                snapshot_id="snapshot", selected_fact_ids=(), prior_record_ids=(),
                written_record_id=None, writeback_receipt_id=None,
                cognition_observation_ids=(),
                epistemic_development_status="state_advanced",
                epistemic_development_evidence_receipt_ids=("evidence-1",),
                epistemic_development_state_receipt_ids=("state-1",),
                epistemic_development_successor_state_ids=("epistemic-state-2",),
                epistemic_development_generations=(2,),
                epistemic_development_next_tick_only=True,
                epistemic_development_error_type=None)

    svc = service(tmp_path, Inference(), screen_observer=Observer())
    svc.sessions = Sessions()
    svc._resident_cognition_bridge = Bridge()
    class AvatarOutput:
        def publish_consequence_probe(self, **kwargs):
            events.append(("probe", kwargs))
            return {"status": "emitted", "action": "one_shot_visual_nod"}
    svc._avatar_output = AvatarOutput()
    svc._live_consequence_cycle_provider = lambda *_args: (
        events.append(("consequence", None))
        or {"status": "completed", "world_state_records": (consequence,),
            "chain_id": "chain-1", "classification": "indeterminate",
            "confidence": "unknown", "quality": "partial",
            "observer_transport_authenticated": True})

    result = svc.run_developmental_cycle(
        session_id="session-1", assistant_turn_id=record["turn_id"],
        request_id="cycle-1", avatar_nod_confirmed=True)

    assert [event[0] for event in events] == [
        "probe", "consequence", "screen", "cycle"]
    assert result["epistemic_development_status"] == "state_advanced"
    assert result["epistemic_development_evidence_receipt_ids"] == ["evidence-1"]
    assert result["epistemic_development_state_receipt_ids"] == ["state-1"]
    assert result["epistemic_development_successor_state_ids"] == [
        "epistemic-state-2"]
    assert result["epistemic_development_generations"] == [2]
    assert result["epistemic_development_next_tick_only"] is True
    assert events[0][1]["assistant_response_digest"] == "c" * 64
    assert events[-1][1]["current_consequence_records"] == (consequence,)
    assert result["consequence_measurement"] == {
        "status": "completed", "error_type": None, "chain_id": "chain-1",
        "classification": "indeterminate", "confidence": "unknown",
        "quality": "partial", "effect_proven": False,
        "renderer_effect_proven": False,
        "observer_transport_authenticated": True,
        "observation_accuracy_established": False,
    }


def test_developmental_cycle_does_not_send_avatar_action_when_cognition_is_deferred(
        tmp_path):
    class BlockedInference(Inference):
        def cognition_available(self):
            return False

    events = []
    class Observer:
        def observe_question(self, _question):
            events.append("screen")
            return {"modality": "screen", "capture_digest": "sha256:" + "a" * 64}

    class Bridge:
        def respond(self, **_kwargs):
            pass
        def developmental_cycle_available(self):
            return True

    class AvatarOutput:
        def publish_consequence_probe(self, **_kwargs):
            events.append("avatar_action")
            return {"status": "emitted"}

    svc = service(tmp_path, BlockedInference(), screen_observer=Observer())
    svc._resident_cognition_bridge = Bridge()
    svc._avatar_output = AvatarOutput()
    with pytest.raises(chat_service.CognitionWorkloadUnavailable):
        svc.run_developmental_cycle(session_id="session-1",
            assistant_turn_id="turn-" + "1" * 24, request_id="deferred-cycle",
            avatar_nod_confirmed=True)
    assert events == []


def test_developmental_cycle_keeps_screen_writeback_path_when_optional_measurement_fails(
        tmp_path):
    record = {
        "role": "assistant", "turn_id": "turn-" + "1" * 24, "text": "A reply.",
        "linkage": {"response_origin": "resident_developmental_cognition",
            "source_user_turn_id": "turn-" + "2" * 24,
        "response_digest": "d" * 64},
    }
    source = {"role": "user", "turn_id": "turn-" + "2" * 24, "text": "Hello."}

    class Sessions:
        @contextmanager
        def serialize_chat_requests(self, _session_id):
            yield
        def load(self, _session_id):
            return {"turns": [source, record]}

    class Observer:
        def observe_question(self, _question):
            return {"modality": "screen", "capture_digest": "sha256:" + "a" * 64}

    class Bridge:
        def respond(self, **_kwargs):
            pass
        def developmental_cycle_available(self):
            return True
        def verify_committed_response(self, **_kwargs):
            return True
        def run_developmental_cycle(self, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(status="completed", tick_id=kwargs["tick_id"],
                snapshot_id="snapshot", selected_fact_ids=(), prior_record_ids=(),
                written_record_id=None, writeback_receipt_id=None,
                cognition_observation_ids=())

    svc = service(tmp_path, Inference(), screen_observer=Observer())
    svc.sessions = Sessions()
    bridge = Bridge()
    svc._resident_cognition_bridge = bridge
    class AvatarOutput:
        def publish_consequence_probe(self, **_kwargs):
            return {"status": "emitted", "action": "one_shot_visual_nod"}
    svc._avatar_output = AvatarOutput()
    def unavailable(*_args):
        raise TimeoutError("observer timeout")
    svc._live_consequence_cycle_provider = unavailable

    result = svc.run_developmental_cycle(
        session_id="session-1", assistant_turn_id=record["turn_id"],
        request_id="cycle-2", avatar_nod_confirmed=True)

    assert "current_consequence_records" not in bridge.kwargs
    assert result["status"] == "completed_without_writeback"
    assert result["consequence_measurement"]["status"] == "unavailable"
    assert result["consequence_measurement"]["effect_proven"] is False
