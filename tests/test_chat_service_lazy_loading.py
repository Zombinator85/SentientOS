# mypy: ignore-errors
from __future__ import annotations

import importlib
import json
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


def test_current_game_observation_question_skips_lexical_memory_retrieval():
    chat = _reload()
    assert chat._is_current_runtime_context_question(
        "In one concise sentence, tell me what you can observe about the current game and what you cannot.")
    assert chat._is_current_runtime_context_question(
        "Hey, how is your evening going? What can you verify about the game that is currently open, and what details can you not observe? Keep it natural and brief.")
    assert chat._is_current_runtime_context_question(
        "Which game is open, and can you see its screen?")
    assert chat._is_current_runtime_context_question(
        "You said Cronos is open and that you cannot see the screen. "
        "What can you tell from your live connection?")
    assert not chat._is_current_runtime_context_question(
        "What do you think about the story in Cronos?")
    assert chat._is_recent_session_recall_request(
        "What exact phrase did I ask you to repeat before the restart?")
    assert chat._is_self_contained_text_echo_request(
        "Please repeat this exact test phrase once: cobalt lantern 73.")


def test_mixed_greeting_and_verified_game_question_skips_memory(tmp_path, monkeypatch):
    chat = _reload(); client = TestClient(chat.APP)
    invoker = SimulationInvoker()
    chat.configure_development_chat(invoker=invoker, data_root=tmp_path)
    memory_queries = []
    original_retrieve = chat.CanonicalMemoryStore.retrieve

    def capture_query(store, query, *, limit=4, budget_chars=2000):
        memory_queries.append(query)
        return original_retrieve(store, query, limit=limit, budget_chars=budget_chars)

    monkeypatch.setattr(chat.CanonicalMemoryStore, "retrieve", capture_query)
    response = client.post("/chat", json={
        "message": ("Hey, how is your evening going? What can you verify about the game "
                    "that is currently open, and what details can you not observe? "
                    "Keep it natural and brief.")
    })

    assert response.status_code == 200
    assert memory_queries == [""]
    assert response.json()["context"]["selected_memory_count"] == 0
    assert "MEMORY_DATA:" not in invoker.prompts[-1]

def test_self_contained_exact_echo_skips_lexical_memory(tmp_path, monkeypatch):
    chat = _reload(); client = TestClient(chat.APP)
    invoker = SimulationInvoker()
    chat.configure_development_chat(invoker=invoker, data_root=tmp_path)
    memory_queries = []
    original_retrieve = chat.CanonicalMemoryStore.retrieve

    def capture_query(store, query, *, limit=4, budget_chars=2000):
        memory_queries.append(query)
        return original_retrieve(store, query, limit=limit, budget_chars=budget_chars)

    monkeypatch.setattr(chat.CanonicalMemoryStore, "retrieve", capture_query)
    prior = client.post("/chat", json={
        "message": "This is an older unrelated Cronos question."
    })
    assert prior.status_code == 200
    response = client.post("/chat", json={
        "session_id": prior.json()["session_id"],
        "message": "Please repeat this exact test phrase once: cobalt lantern 73."
    })

    assert response.status_code == 200
    assert memory_queries == ["This is an older unrelated Cronos question.", ""]
    assert response.json()["context"]["selected_memory_count"] == 0
    assert response.json()["context"]["selected_turn_count"] == 0
    assert "This is an older unrelated Cronos question." not in invoker.prompts[-1]
    assert "MEMORY_DATA:" not in invoker.prompts[-1]

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
        self.requests = []
    def build_request(self, **kwargs):
        self.prompts.append(kwargs["prompt"])
        self.requests.append(kwargs)
        return SimpleNamespace(request_id="simulation-request", **kwargs)
    def release_model_residency(self):
        return SimpleNamespace(status="released", to_dict=lambda: {"status": "released"})
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


@pytest.mark.parametrize(("configured_window", "expected_window"), [
    (None, "0"), ("5s", "5s"),
])
def test_development_gaming_residency_window_is_opt_in(
        tmp_path, configured_window, expected_window):
    chat = _reload(); client = TestClient(chat.APP)
    invoker = SimulationInvoker()
    identity = {"engine": "ollama", "semantic_artifact_identity": "sha256:" + "a" * 64,
        "posture": "development_only", "fallback": False}
    invoker.model.active_identity = SimpleNamespace(engine="ollama",
        to_dict=lambda: identity)
    options = {} if configured_window is None else {
        "gaming_keep_alive": configured_window}
    chat.configure_development_chat(invoker=invoker, data_root=tmp_path, **options)
    mode = client.post("/workload-mode", json={"mode": "gaming"})
    response = client.post("/chat", json={"message": "hello"})

    assert mode.status_code == 200
    assert response.status_code == 200
    assert invoker.requests[-1]["linkage"]["ollama_keep_alive"] == expected_window
    if configured_window is not None:
        with pytest.raises(ValueError, match="unsupported_development_gaming_keep_alive"):
            chat.DevelopmentLocalChatInference(invoker, gaming_keep_alive="5m")


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
    assert "You are the active local conversational model inside SentientOS" in prompt
    assert "use the configured model label when asked" in prompt
    assert "without generic limitations; do not claim feelings or personal experiences" in prompt
    assert "do not claim feelings or personal experiences" in prompt
    assert "Without CURRENT_SCREEN_OBSERVATION_UNTRUSTED, answer no to visibility questions" in prompt
    assert "Answer the current message directly and cover every requested part" in prompt
    assert "A foreground process confirms only the app is open" in prompt
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


def test_verified_workload_context_names_only_confirmed_allowlisted_game(tmp_path):
    import json
    from sentientos.foreground_game_detection import ForegroundGameObservation

    chat = _reload(); client = TestClient(chat.APP)
    invoker = SimulationInvoker()

    class Detector:
        def observe(self, names):
            assert tuple(names) == ("cronos-win64-shipping.exe",)
            return ForegroundGameObservation("available", True, "a" * 64,
                "2026-11-03T17:00:00+00:00")

    chat.configure_development_chat(invoker=invoker, data_root=tmp_path,
        initial_workload_mode="automatic",
        game_process_names=("Cronos-Win64-Shipping.exe",),
        foreground_game_detector=Detector())
    response = client.post("/chat", json={
        "message": "What do you know about my current Cronos session?"
    })

    assert response.status_code == 200
    prompt = invoker.prompts[-1]
    assert "Use configured_game_process_names only to identify the foreground app" in prompt
    runtime_block = prompt.split("[VERIFIED_RUNTIME_CONTEXT]\n", 1)[1].split(
        "\n[SESSION_HISTORY_DATA]", 1)[0]
    workload = json.loads(runtime_block)["workload"]
    assert workload["game_foreground"] is True
    assert workload["configured_game_process_names"] == ["cronos-win64-shipping.exe"]
    assert "[VERIFIED_CURRENT_WORKLOAD_FACTS]" in prompt
    assert "Verified foreground game: Cronos (cronos-win64-shipping.exe)" in prompt
    assert "Use configured_game_process_names only to identify the foreground app" in prompt
    assert "game screen and actions are not observed this turn" in prompt


def test_live_screen_question_skips_cross_session_memories(tmp_path, monkeypatch):
    chat = _reload(); client = TestClient(chat.APP)
    invoker = SimulationInvoker()
    chat.configure_development_chat(invoker=invoker, data_root=tmp_path)
    memory_queries = []
    original_retrieve = chat.CanonicalMemoryStore.retrieve

    def capture_query(store, query, *, limit=4, budget_chars=2000):
        memory_queries.append(query)
        return original_retrieve(store, query, limit=limit, budget_chars=budget_chars)

    monkeypatch.setattr(chat.CanonicalMemoryStore, "retrieve", capture_query)
    response = client.post("/chat", json={
        "message": "Can you see my screen right now? If not, say what you can confirm."
    })

    assert response.status_code == 200
    assert memory_queries == [""]
    assert "MEMORY_DATA:" not in invoker.prompts[-1]
    assert "A foreground process confirms only the app is open" in invoker.prompts[-1]
    assert "Without CURRENT_SCREEN_OBSERVATION_UNTRUSTED, answer no to visibility questions" in invoker.prompts[-1]


def test_live_connection_question_skips_unrelated_cross_session_memories(tmp_path, monkeypatch):
    chat = _reload(); client = TestClient(chat.APP)
    invoker = SimulationInvoker()
    chat.configure_development_chat(invoker=invoker, data_root=tmp_path)
    memory_queries = []
    original_retrieve = chat.CanonicalMemoryStore.retrieve

    def capture_query(store, query, *, limit=4, budget_chars=2000):
        memory_queries.append(query)
        return original_retrieve(store, query, limit=limit, budget_chars=budget_chars)

    monkeypatch.setattr(chat.CanonicalMemoryStore, "retrieve", capture_query)
    response = client.post("/chat", json={
        "message": ("You said Cronos is open and that you cannot see the screen. "
                    "What can you tell from your live connection?")
    })

    assert response.status_code == 200
    assert memory_queries == [""]
    assert response.json()["context"]["selected_memory_count"] == 0
    assert "MEMORY_DATA:" not in invoker.prompts[-1]
    assert "configured_game_process_names" in invoker.prompts[-1]
    assert "screen_observation" in invoker.prompts[-1]


def test_recent_session_recall_uses_transcript_without_cross_session_memory(tmp_path, monkeypatch):
    chat = _reload(); client = TestClient(chat.APP)
    invoker = SimulationInvoker()
    chat.configure_development_chat(invoker=invoker, data_root=tmp_path)
    memory_queries = []
    original_retrieve = chat.CanonicalMemoryStore.retrieve

    def capture_query(store, query, *, limit=4, budget_chars=2000):
        memory_queries.append(query)
        return original_retrieve(store, query, limit=limit, budget_chars=budget_chars)

    monkeypatch.setattr(chat.CanonicalMemoryStore, "retrieve", capture_query)
    session_id = client.post("/sessions").json()["session_id"]
    first = client.post("/chat", json={"session_id": session_id,
        "message": ("I am taking a breather between fights in Cronos. Say something "
                    "friendly, then ask me one easy question to keep me company.")})
    assert first.status_code == 200
    recall = client.post("/chat", json={"session_id": session_id,
        "message": "When I was taking a breather between fights earlier, what did I ask you to do?"})
    assert recall.status_code == 200

    assert memory_queries == ["", ""]
    assert "I am taking a breather between fights in Cronos." in invoker.prompts[-1]
    assert "ask me one easy question to keep me company" in invoker.prompts[-1]
    assert "USER_DATA:" in invoker.prompts[-1]
    assert "ASSISTANT_DATA:" not in invoker.prompts[-1]
    assert "MEMORY_DATA:" not in invoker.prompts[-1]
    assert "final prior USER_DATA turn" in invoker.prompts[-1]
    assert "Do not substitute older turns" in invoker.prompts[-1]


def test_recent_assistant_reply_recall_includes_same_session_answer_only(tmp_path, monkeypatch):
    chat = _reload(); client = TestClient(chat.APP)
    invoker = SimulationInvoker()
    chat.configure_development_chat(invoker=invoker, data_root=tmp_path)
    memory_queries = []
    original_retrieve = chat.CanonicalMemoryStore.retrieve

    def capture_query(store, query, *, limit=4, budget_chars=2000):
        memory_queries.append(query)
        return original_retrieve(store, query, limit=limit, budget_chars=budget_chars)

    monkeypatch.setattr(chat.CanonicalMemoryStore, "retrieve", capture_query)
    first = client.post("/chat", json={"message": "Can you see my screen?"})
    sid = first.json()["session_id"]
    recent = client.post("/chat", json={"session_id": sid,
        "message": "What is the immediate game focus? Cronos."})
    second = client.post("/chat", json={"session_id": sid,
        "message": "What did I ask, and what did you answer?"})

    assert recent.status_code == second.status_code == 200
    assert memory_queries == ["", "What is the immediate game focus? Cronos.", ""]
    prompt = invoker.prompts[-1]
    assert "USER_DATA: " in prompt and "What is the immediate game focus? Cronos." in prompt
    assert "Can you see my screen?" not in prompt
    assert "ASSISTANT_DATA: " in prompt and "explicit simulation" in prompt
    assert "final prior USER_DATA turn" in prompt
    assert "Do not substitute older turns" in prompt
    assert "MEMORY_DATA:" not in prompt
    assert second.json()["context"]["selected_turn_count"] == 2
    assert second.json()["context"]["selected_memory_count"] == 0


def test_recent_user_recall_uses_only_immediately_previous_user_turn(tmp_path):
    chat = _reload(); client = TestClient(chat.APP)
    invoker = SimulationInvoker()
    chat.configure_development_chat(invoker=invoker, data_root=tmp_path)
    first = client.post("/chat", json={"message": "Can you see my screen?"})
    sid = first.json()["session_id"]
    recent = client.post("/chat", json={"session_id": sid,
        "message": "Please focus on Cronos frame pacing."})
    recall = client.post("/chat", json={"session_id": sid,
        "message": "What did I ask you about just before this?"})

    assert recent.status_code == recall.status_code == 200
    prompt = invoker.prompts[-1]
    assert "Please focus on Cronos frame pacing." in prompt
    assert "Can you see my screen?" not in prompt
    assert "final prior USER_DATA turn" in prompt
    assert recall.json()["context"]["selected_turn_count"] == 1
    assert recall.json()["context"]["selected_memory_count"] == 0


def test_social_checkin_uses_only_current_message_without_stale_context(
        tmp_path, monkeypatch):
    chat = _reload(); client = TestClient(chat.APP)
    invoker = SimulationInvoker()
    identity = {
        "engine": "test",
        "semantic_artifact_identity": "qwen2.5-3b-test-digest",
        "posture": "development_only",
        "fallback": False,
    }
    invoker.model.active_identity = SimpleNamespace(**identity,
        to_dict=lambda: dict(identity))
    invoker.authority_map = SimpleNamespace(
        record_for_active_identity=lambda _identity, _purpose:
            SimpleNamespace(name="Qwen2.5 3B Instruct"))
    chat.configure_development_chat(invoker=invoker, data_root=tmp_path)
    memory_queries = []
    original_retrieve = chat.CanonicalMemoryStore.retrieve

    def capture_query(store, query, *, limit=4, budget_chars=2000):
        memory_queries.append(query)
        return original_retrieve(store, query, limit=limit, budget_chars=budget_chars)

    monkeypatch.setattr(chat.CanonicalMemoryStore, "retrieve", capture_query)
    session_id = client.post("/sessions").json()["session_id"]
    first = client.post("/chat", json={"session_id": session_id,
        "message": "I am taking a breather between fights in Cronos."})
    assert first.status_code == 200
    assert client.post("/workload-mode", json={"mode": "gaming"}).status_code == 200
    checkin = client.post("/chat", json={"session_id": session_id,
        "message": "How are you doing? I am just taking a breather."})

    assert checkin.status_code == 200
    assert memory_queries == ["I am taking a breather between fights in Cronos.", ""]
    prompt = invoker.prompts[-1]
    assert "I am taking a breather between fights in Cronos." not in prompt
    assert "How are you doing? I am just taking a breather." in prompt
    assert "USER_DATA:" not in prompt
    assert "ASSISTANT_DATA:" not in prompt
    assert "MEMORY_DATA:" not in prompt
    runtime_block = prompt.split("[VERIFIED_RUNTIME_CONTEXT]\n", 1)[1].split(
        "\n[SESSION_HISTORY_DATA]", 1)[0]
    runtime = json.loads(runtime_block)
    assert runtime["system"]["name"] == "SentientOS"
    assert runtime["assistant_role"] == (
        "the active local model providing conversation inside SentientOS")
    assert runtime["active_model"]["configured_candidate_label"] == "Qwen2.5 3B Instruct"
    assert runtime["workload"]["effective_mode"] == "gaming"
    assert runtime["capabilities"]["conversation_history"]["prior_turns_included"] == 0
    assert runtime["capabilities"]["retrieved_memories_included"] == 0
    assert runtime["capabilities"]["screen_observation"]["included_this_turn"] is False
    assert chat.GamingWorkloadPolicy.GAMING_SOCIAL_CHECKIN_INSTRUCTION in prompt
    assert len(prompt) <= chat.GamingWorkloadPolicy.GAMING_MAX_INPUT_CHARS
    assert chat._is_social_checkin_request(
        "I am saving healing items. Keep me company.") is True
    assert checkin.json()["context"]["selected_turn_count"] == 0

    explicit_checkin = client.post("/chat", json={"session_id": session_id,
        "message": ("Quick chat test between fights: just tell me you are here with me, "
                    "then ask one easy question.")})
    assert explicit_checkin.status_code == 200
    assert memory_queries == [
        "I am taking a breather between fights in Cronos.", "", ""
    ]
    assert explicit_checkin.json()["context"]["selected_turn_count"] == 0
    assert explicit_checkin.json()["context"]["selected_memory_count"] == 0
    assert chat.GamingWorkloadPolicy.GAMING_SOCIAL_CHECKIN_INSTRUCTION in invoker.prompts[-1]


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
    assert active_state["configured_game_process_names"] == ["cronos-win64-shipping.exe"]
    detector.foreground = False
    state = inference.current_workload_state()
    assert state["mode"] == "automatic"
    assert state["effective_mode"] == "normal"
    assert state["foreground_game_detected"] is False
    assert "configured_game_process_names" not in state
    assert state["workload_evidence"]["process_name_digest"] == "a" * 64

    inference.generate(prompt="[SYSTEM_INSTRUCTION]\nrole\n[VERIFIED_RUNTIME_CONTEXT]\n{}\n[SESSION_HISTORY_DATA]\nhello",
        caller="test", correlation_id="automatic-mode",
        budget=LocalModelInvocationBudget(), caller_linkage={})
    assert invoker.model is normal


def test_automatic_workload_poll_releases_previous_model_when_game_enters_foreground(tmp_path):
    chat = _reload()
    from sentientos.foreground_game_detection import ForegroundGameObservation

    class MutableDetector:
        def __init__(self):
            self.foreground = False
        def observe(self, _names):
            return ForegroundGameObservation("available", self.foreground,
                "b" * 64, "2026-11-03T20:00:00+00:00", {"source_id": "windows"})

    class Invoker:
        def __init__(self, model):
            self.model = model
            self.authority_map = SimpleNamespace(
                record_for_active_identity=lambda identity, purpose: object()
                if purpose == "local_user_chat" and identity is not None else None)
            self.release_calls = 0
            self.resident = False
        def release_model_residency(self):
            self.release_calls += 1
            self.resident = False
            return SimpleNamespace(status="released",
                to_dict=lambda: {"status": "released"})

    normal = SimpleNamespace(active_identity=SimpleNamespace(engine="ollama"))
    gaming = SimpleNamespace(active_identity=SimpleNamespace(engine="ollama"))
    detector = MutableDetector()
    invoker = Invoker(normal)
    chat.configure_development_chat(invoker=invoker, data_root=tmp_path,
        model_profiles={"normal": normal, "gaming": gaming},
        initial_workload_mode="automatic", foreground_game_detector=detector,
        game_process_names=("Cronos-Win64-Shipping.exe",))
    client = TestClient(chat.APP)

    idle = client.post("/workload-mode/reconcile")
    assert idle.status_code == 200
    assert idle.json()["effective_mode"] == "normal"
    assert invoker.model is normal

    invoker.resident = True
    release_calls_before_game = invoker.release_calls
    detector.foreground = True
    observed = client.get("/workload-mode")
    assert observed.status_code == 200
    assert observed.json()["effective_mode"] == "gaming"
    assert invoker.model is normal
    assert invoker.resident is True
    assert invoker.release_calls == release_calls_before_game

    reconciled = client.post("/workload-mode/reconcile")
    assert reconciled.status_code == 200
    assert reconciled.json()["effective_mode"] == "gaming"
    assert invoker.model is gaming
    assert invoker.resident is False
    assert invoker.release_calls == release_calls_before_game + 1

    assert client.post("/workload-mode", json={"mode": "normal"}).status_code == 200
    invoker.resident = True
    release_calls_in_manual_mode = invoker.release_calls
    reconciled = client.post("/workload-mode/reconcile")
    assert reconciled.status_code == 200
    assert reconciled.json()["effective_mode"] == "normal"
    assert invoker.model is normal
    assert invoker.resident is True
    assert invoker.release_calls == release_calls_in_manual_mode


def test_failed_automatic_model_release_is_visible_and_does_not_switch_profiles(tmp_path):
    chat = _reload()
    from sentientos.foreground_game_detection import ForegroundGameObservation

    class MutableDetector:
        foreground = False
        def observe(self, _names):
            return ForegroundGameObservation("available", self.foreground,
                "c" * 64, "2026-11-03T20:00:00+00:00", {"source_id": "windows"})

    class Invoker:
        def __init__(self, model):
            self.model = model
            self.authority_map = SimpleNamespace(
                record_for_active_identity=lambda identity, purpose: object()
                if purpose == "local_user_chat" and identity is not None else None)
            self.release_statuses = ["released", "released", "release_failed"]
            self.resident = True
        def release_model_residency(self):
            status = self.release_statuses.pop(0)
            if status == "released":
                self.resident = False
            return SimpleNamespace(status=status,
                to_dict=lambda: {"status": status})

    normal = SimpleNamespace(active_identity=SimpleNamespace(engine="ollama"))
    gaming = SimpleNamespace(active_identity=SimpleNamespace(engine="ollama"))
    detector = MutableDetector()
    invoker = Invoker(normal)
    chat.configure_development_chat(invoker=invoker, data_root=tmp_path,
        model_profiles={"normal": normal, "gaming": gaming},
        initial_workload_mode="automatic", foreground_game_detector=detector,
        game_process_names=("Cronos-Win64-Shipping.exe",))
    client = TestClient(chat.APP)
    assert client.post("/workload-mode/reconcile").status_code == 200
    assert invoker.model is normal
    invoker.resident = True
    detector.foreground = True

    response = client.post("/workload-mode/reconcile")

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Automatic game transition blocked because model residency release was not confirmed.")
    assert invoker.model is normal
    assert invoker.resident is True
    assert "Game detected; model release unconfirmed, gaming profile not switched" in client.get("/").text


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
    inference.generate(prompt="[SYSTEM_INSTRUCTION]\nrole\n[VERIFIED_RUNTIME_CONTEXT]\n{}\n[SESSION_HISTORY_DATA]\nhello",
        caller="test", correlation_id="stale-automatic-mode",
        budget=LocalModelInvocationBudget(), caller_linkage={})
    assert invoker.model is gaming


def test_unobserved_gaming_companion_claim_is_corrected_and_attributed(tmp_path):
    chat = _reload(); client = TestClient(chat.APP)
    invoker = SimulationInvoker()
    chat.configure_development_chat(invoker=invoker, data_root=tmp_path)
    assert client.post("/workload-mode", json={"mode": "gaming"}).status_code == 200

    def unsupported_reply(request):
        invoker.calls += 1
        output = "Sure, keeping an eye on your gaming session."
        digest = __import__("hashlib").sha256(
            __import__("json").dumps({"output": output}, sort_keys=True,
                separators=(",", ":")).encode()).hexdigest()
        return SimpleNamespace(status="admitted_simulation", output_text=output,
            output_digest=digest, output_truncated=False, request={
                "request_id": request.request_id, "active_model_identity":
                    (invoker.model.active_identity.to_dict()
                     if invoker.model.active_identity is not None else {})},
            receipt_id="simulation-receipt-id", receipt_digest="simulation-receipt")
    invoker.invoke = unsupported_reply
    response = client.post("/chat", json={"message": "Keep me company while I play."})

    assert response.status_code == 200
    payload = response.json()
    assert payload["response"].startswith("SentientOS correction:")
    assert payload["context"]["response_origin"] == "grounding_policy_fallback"
