# mypy: ignore-errors
from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.no_legacy_skip
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient


def _reload():
    sys.modules.pop("sentientos.chat_service", None)
    import sentientos.chat_service as module
    return importlib.reload(module)


def test_import_does_not_autoload_model(monkeypatch):
    calls = []
    monkeypatch.setattr("sentientos.local_model.LocalModel.autoload", lambda: calls.append("autoload"))
    chat = _reload()
    assert calls == []
    assert chat._CONVERSATION_SERVICE is None


def test_health_paths_do_not_load_model(monkeypatch):
    calls = []
    monkeypatch.setattr("sentientos.local_model.LocalModel.autoload", lambda: calls.append("autoload"))
    chat = _reload(); client = TestClient(chat.APP)
    assert client.get("/").status_code == 200
    assert client.get("/boot-feed").status_code == 200
    assert calls == []


class SimulationInvoker:
    def __init__(self):
        self.model = SimpleNamespace(active_identity=None)
        self.calls = 0
        self.prompts = []
    def build_request(self, **kwargs):
        self.prompts.append(kwargs["prompt"])
        return SimpleNamespace(request_id="simulation-request", **kwargs)
    def invoke(self, request):
        self.calls += 1
        identity = self.model.active_identity
        identity_payload = identity.to_dict() if identity is not None else {}
        return SimpleNamespace(status="admitted_simulation", output_text="explicit simulation",
            output_digest=__import__("hashlib").sha256(
                __import__("json").dumps({"output": "explicit simulation"},
                    sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            output_truncated=False, request={"request_id": request.request_id,
                "active_model_identity": identity_payload}, receipt_id="simulation-receipt-id",
            receipt_digest="simulation-receipt")


def test_model_work_requires_explicit_simulation_composition(tmp_path):
    chat = _reload(); client = TestClient(chat.APP)
    assert client.post("/chat", json={"message": "hello"}).status_code == 503
    invoker = SimulationInvoker()
    chat.configure_development_chat(invoker=invoker, data_root=tmp_path)
    response = client.post("/chat", json={"message": "hello"})
    assert response.status_code == 200
    assert response.json()["response"] == "explicit simulation"
    gaming = client.post("/workload-mode", json={"mode": "gaming"})
    assert gaming.status_code == 200
    assert gaming.json()["effective_mode"] == "gaming"
    assert invoker.calls == 1



def test_development_workload_mode_switches_authorized_model_profiles(tmp_path):
    chat = _reload()

    class ProfileAuthority:
        def record_for_active_identity(self, identity, purpose):
            return object() if purpose == "local_user_chat" and identity is not None else None

    class ProfileInvoker:
        def __init__(self, model):
            self.model = model
            self.authority_map = ProfileAuthority()
            self.release_calls = 0

        def release_model_residency(self):
            self.release_calls += 1
            return SimpleNamespace(status="released",
                to_dict=lambda: {"status": "released"})

    normal = SimpleNamespace(active_identity=SimpleNamespace(
        engine="ollama", semantic_artifact_identity="hermes",
        to_dict=lambda: {"engine": "ollama", "semantic_artifact_identity": "hermes"}))
    gaming = SimpleNamespace(active_identity=SimpleNamespace(
        engine="ollama", semantic_artifact_identity="qwen3",
        to_dict=lambda: {"engine": "ollama", "semantic_artifact_identity": "qwen3"}))
    invoker = ProfileInvoker(normal)
    inference = chat.DevelopmentLocalChatInference(invoker,
        {"normal": normal, "gaming": gaming})

    assert inference.current_conversation_model_identity() == {
        "engine": "ollama", "semantic_artifact_identity": "hermes"}
    inference.set_workload_mode("gaming")
    assert invoker.model is gaming
    assert inference.current_workload_mode() == "gaming"
    assert inference.current_conversation_model_identity()["semantic_artifact_identity"] == "qwen3"
    inference.set_workload_mode("normal")
    assert invoker.model is normal
    assert inference.current_workload_mode() == "normal"
    assert invoker.release_calls == 2


def test_development_profile_switch_fails_closed_if_residency_release_fails():
    chat = _reload()

    class ProfileAuthority:
        def record_for_active_identity(self, _identity, _purpose):
            return object()

    class ProfileInvoker:
        def __init__(self, model):
            self.model = model
            self.authority_map = ProfileAuthority()

        def release_model_residency(self):
            return SimpleNamespace(status="release_failed",
                to_dict=lambda: {"status": "release_failed"})

    normal = SimpleNamespace(active_identity=SimpleNamespace(engine="ollama"))
    gaming = SimpleNamespace(active_identity=SimpleNamespace(engine="ollama"))
    invoker = ProfileInvoker(normal)
    inference = chat.DevelopmentLocalChatInference(invoker,
        {"normal": normal, "gaming": gaming})

    with pytest.raises(RuntimeError, match="local_model_profile_release_unconfirmed"):
        inference.set_workload_mode("gaming")
    assert invoker.model is normal
    assert inference.current_workload_mode() == "normal"

def test_local_ui_recovers_session_transcript_after_service_restart(tmp_path):
    chat = _reload(); client = TestClient(chat.APP, client=("127.0.0.1", 1234))
    invoker = SimulationInvoker()
    chat.configure_development_chat(invoker=invoker, data_root=tmp_path)

    created = client.post("/sessions")
    assert created.status_code == 200
    session_id = created.json()["session_id"]
    for message in ("Remember violet comet.", "What phrase did I ask you to remember?"):
        response = client.post("/chat", json={"session_id": session_id, "message": message})
        assert response.status_code == 200

    # Re-loading the ASGI module simulates a service restart while retaining the
    # same private development state directory and browser session identity.
    restarted = _reload(); restarted_client = TestClient(restarted.APP, client=("127.0.0.1", 1234))
    restarted.configure_development_chat(invoker=invoker, data_root=tmp_path)
    transcript = restarted_client.get(f"/sessions/{session_id}/turns")

    assert transcript.status_code == 200
    payload = transcript.json()
    assert payload["total_turns"] == 4
    assert payload["truncated"] is False
    assert [(turn["role"], turn["text"]) for turn in payload["turns"]] == [
        ("user", "Remember violet comet."),
        ("assistant", "explicit simulation"),
        ("user", "What phrase did I ask you to remember?"),
        ("assistant", "explicit simulation"),
    ]
    assert set(payload["turns"][0]) == {"turn_id", "sequence", "role", "timestamp", "text"}

    page = restarted_client.get("/").text
    assert 'id="conversation"' in page
    assert "refreshConversationTranscript();" in page
    assert "content.textContent = turn.text;" in page
    remote_client = TestClient(restarted.APP, client=("203.0.113.10", 4321))
    assert remote_client.get(f"/sessions/{session_id}/turns").status_code == 403


def test_friendly_greeting_prompt_uses_verified_sentientos_runtime_context(tmp_path):
    import json

    chat = _reload(); client = TestClient(chat.APP)
    invoker = SimulationInvoker()
    identity = {
        "engine": "ollama",
        "semantic_artifact_identity": "sha256:" + "a" * 64,
        "posture": "development_only",
        "fallback": False,
    }
    invoker.model.active_identity = SimpleNamespace(to_dict=lambda: identity)
    invoker.authority_map = SimpleNamespace(
        record_for_active_identity=lambda observed, purpose: SimpleNamespace(
            name="Nous Hermes 4 14B local development model")
        if observed.to_dict() == identity and purpose == "local_user_chat" else None)
    chat.configure_development_chat(invoker=invoker, data_root=tmp_path)

    response = client.post("/chat", json={"message": "How are you doing in there?"})

    assert response.status_code == 200
    prompt = invoker.prompts[-1]
    assert "You are the currently active conversational model within SentientOS" in prompt
    assert "use the configured model label from VERIFIED_RUNTIME_CONTEXT" in prompt
    assert "Do not add a generic model/AI limitations preamble or unrelated self-description" in prompt
    runtime_block = prompt.split("[VERIFIED_RUNTIME_CONTEXT]\n", 1)[1].split(
        "\n[SESSION_HISTORY_DATA]", 1)[0]
    runtime = json.loads(runtime_block)
    assert runtime["assistant_role"] == "the active local model providing conversation inside SentientOS"
    assert runtime["active_model"]["configured_candidate_label"] == "Nous Hermes 4 14B local development model"
    assert runtime["active_model"]["semantic_artifact_identity"] == identity["semantic_artifact_identity"]
    assert runtime["workload"]["mode"] == "normal"
    assert runtime["workload"]["foreground_game_observation"] == "not_observed"
    assert runtime["capabilities"]["conversation_history"]["persisted_locally"] is True
    assert runtime["capabilities"]["local_speech_output"]["configured"] is False
    assert runtime["capabilities"]["screen_observation"]["configured"] is False
    assert "How are you doing in there?" in prompt


def test_gaming_chat_trims_history_to_the_complete_input_ceiling(tmp_path):
    from sentientos.gaming_workload_policy import GamingWorkloadPolicy

    chat = _reload(); client = TestClient(chat.APP)
    invoker = SimulationInvoker()
    chat.configure_development_chat(invoker=invoker, data_root=tmp_path)
    session_id = None
    for index in range(3):
        response = client.post("/chat", json={
            "message": ("Turn 0: remember violet comet. " if index == 0 else
                        f"Turn {index}: ") + ("remember this detail " * 18),
            "session_id": session_id,
        })
        assert response.status_code == 200
        session_id = response.json()["session_id"]
    assert client.post("/workload-mode", json={"mode": "gaming"}).status_code == 200

    response = client.post("/chat", json={
        "session_id": session_id, "message": "Continue briefly."
    })

    assert response.status_code == 200
    assert len(invoker.prompts[-1]) <= GamingWorkloadPolicy.GAMING_MAX_INPUT_CHARS
    assert "Turn 0: remember violet comet." in invoker.prompts[-1]


def test_development_automatic_mode_switches_profiles_from_fresh_observations():
    chat = _reload()
    from sentientos.foreground_game_detection import ForegroundGameObservation
    from sentientos.governed_local_model_invocation import LocalModelInvocationBudget

    class ProfileAuthority:
        def record_for_active_identity(self, identity, purpose):
            return object() if purpose == "local_user_chat" and identity is not None else None

    class ProfileInvoker:
        def __init__(self, model):
            self.model = model
            self.authority_map = ProfileAuthority()
            self.release_calls = 0
            self.requests = []
        def release_model_residency(self):
            self.release_calls += 1
            return SimpleNamespace(status="already_unloaded",
                to_dict=lambda: {"status": "already_unloaded"})
        def build_request(self, **kwargs):
            self.requests.append(kwargs)
            return {**kwargs, "active_model_identity": self.model.active_identity}
        def invoke(self, request):
            return SimpleNamespace(status="admitted_simulation", output_text="ok",
                request={"active_model_identity": request["active_model_identity"]})

    class MutableDetector:
        def __init__(self):
            self.foreground = True
        def observe(self, _names):
            return ForegroundGameObservation("available", self.foreground,
                "a" * 64, "2026-11-03T17:00:00+00:00", {"source_id": "windows"})

    normal = SimpleNamespace(active_identity=SimpleNamespace(
        engine="ollama", semantic_artifact_identity="hermes"))
    gaming = SimpleNamespace(active_identity=SimpleNamespace(
        engine="ollama", semantic_artifact_identity="qwen3"))
    detector = MutableDetector()
    invoker = ProfileInvoker(normal)
    inference = chat.DevelopmentLocalChatInference(invoker,
        {"normal": normal, "gaming": gaming}, foreground_game_detector=detector)

    inference.set_workload_mode("automatic", ("Cronos-Win64-Shipping.exe",))
    assert invoker.model is gaming
    active_state = inference.current_workload_state()
    assert active_state["mode_source"] == "foreground_allowlist_match"
    assert active_state["observation_status"] == "available"
    assert active_state["game_foreground"] is True
    detector.foreground = False
    state = inference.current_workload_state()
    assert state["mode"] == "automatic"
    assert state["effective_mode"] == "normal"
    assert state["foreground_game_detected"] is False
    assert state["workload_evidence"]["process_name_digest"] == "a" * 64

    inference.generate(prompt="[SYSTEM_INSTRUCTION]\nrole\n[SESSION_HISTORY_DATA]\nhello",
        caller="test", correlation_id="automatic-mode",
        budget=LocalModelInvocationBudget(), caller_linkage={})
    assert invoker.model is normal


def test_development_automatic_mode_falls_back_to_gaming_when_observation_stale():
    chat = _reload()
    from sentientos.foreground_game_detection import ForegroundGameObservation
    from sentientos.governed_local_model_invocation import LocalModelInvocationBudget

    class Detector:
        def observe(self, _names):
            return ForegroundGameObservation("bridge_observation_expired", None, None,
                "2026-11-03T17:00:00+00:00")

    class Invoker:
        def __init__(self, model):
            self.model = model
            self.authority_map = SimpleNamespace(
                record_for_active_identity=lambda identity, purpose: object())
            self.release_calls = 0
        def release_model_residency(self):
            self.release_calls += 1
            return SimpleNamespace(status="released", to_dict=lambda: {"status": "released"})
        def build_request(self, **kwargs):
            return {"active_model_identity": self.model.active_identity, **kwargs}
        def invoke(self, request):
            return SimpleNamespace(request={"active_model_identity":
                request["active_model_identity"]})

    normal = SimpleNamespace(active_identity=SimpleNamespace(engine="ollama"))
    gaming = SimpleNamespace(active_identity=SimpleNamespace(engine="ollama"))
    invoker = Invoker(normal)
    inference = chat.DevelopmentLocalChatInference(invoker,
        {"normal": normal, "gaming": gaming}, foreground_game_detector=Detector())
    inference.set_workload_mode("automatic", ("Cronos-Win64-Shipping.exe",))
    with inference._workload_lock:
        inference._select_profile_locked("normal")

    state = inference.current_workload_state()
    assert state["effective_mode"] == "gaming"
    assert state["mode_source"] == "foreground_observation_unavailable_conservative_gaming"
    inference.generate(prompt="[SYSTEM_INSTRUCTION]\nrole\n[SESSION_HISTORY_DATA]\nhello",
        caller="test", correlation_id="stale-automatic-mode",
        budget=LocalModelInvocationBudget(), caller_linkage={})
    assert invoker.model is gaming
