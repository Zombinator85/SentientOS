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
        "Hey SentientOS, I am playing Cronos. Give me a quick friendly check-in, "
        "and be clear if you cannot see the gameplay.")
    assert chat._is_current_runtime_context_question(
        "You said Cronos is open and that you cannot see the screen. "
        "What can you tell from your live connection?")
    grounded_current_question = (
        "While Cronos is foregrounded, what can SentientOS confidently say "
        "about the current situation, and what can it not see?")
    assert chat._is_current_runtime_context_question(grounded_current_question)
    from sentientos.chat_response_grounding import is_direct_screen_activity_question
    assert is_direct_screen_activity_question(grounded_current_question)
    assert not chat._is_current_runtime_context_question(
        "What do you think about the story in Cronos?")
    assert chat._is_current_runtime_context_question(
        "Can you tell what's happening on screen in Cronos right now?")
    assert chat._is_recent_session_recall_request(
        "What did I ask you first in this conversation?")
    assert chat._is_recent_session_recall_request(
        "Earlier, you asked me what I find relaxing when I am not gaming. "
        "What exactly was your question?")
    assert chat._is_prior_assistant_question_recall(
        "Earlier, you asked me what I find relaxing when I am not gaming. "
        "What exactly was your question?")
    assert chat._is_earliest_session_recall_request(
        "What did I ask you first in this conversation?")
    assert chat._is_recent_session_recall_request("What did you just say?")
    assert chat._is_recent_session_recall_request(
        "Please remind me what I said about where I discover new music.")
    assert chat._is_recent_user_statement_reminder(
        "Please remind me what I said about where I discover new music.")
    assert not chat._is_recent_user_statement_reminder(
        "What did I say was written on the note I found?")
    assert chat._is_direct_recent_user_turn_recall_request("What did I just ask you?")
    assert chat._is_direct_recent_user_turn_recall_request("What was my previous question?")
    assert not chat._is_direct_recent_user_turn_recall_request(
        "What did I ask you first in this conversation?")
    assert not chat._is_earliest_session_recall_request("What did you just say?")
    assert not chat._is_earliest_session_recall_request(
        "What was the first part of my last message?")
    assert chat._is_recent_session_recall_request(
        "What exact phrase did I ask you to repeat before the restart?")
    assert chat._is_recent_session_recall_request(
        "What did I say was written on the note I found?")
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

def test_unconfigured_screen_status_uses_durable_policy_answer_without_model_inference(
        tmp_path):
    chat = _reload()
    from sentientos.foreground_game_detection import ForegroundGameObservation

    class MutableDetector:
        foreground = False
        def observe(self, _names):
            return ForegroundGameObservation(
                "available", self.foreground, "a" * 64,
                "2026-11-04T18:00:00+00:00", {"source_id": "test"},
                game_process_running=self.foreground,
                running_process_name_digests=(("b" * 64,) if self.foreground else ()),
            )

    client = TestClient(chat.APP)
    detector = MutableDetector()
    invoker = SimulationInvoker()
    chat.configure_development_chat(invoker=invoker, data_root=tmp_path,
        initial_workload_mode="automatic", foreground_game_detector=detector,
        game_process_names=("Cronos-Win64-Shipping.exe",))
    initial = client.post("/chat", json={"message": "Hello."})
    assert initial.status_code == 200
    inference_calls = invoker.calls
    detector.foreground = True

    request = {
        "session_id": initial.json()["session_id"],
        "request_id": "screen-status-without-observation",
        "message": "Can you tell what's happening on screen in Cronos right now?",
    }
    response = client.post("/chat", json=request)

    assert response.status_code == 200
    body = response.json()
    assert body["response"] == (
        "I can confirm Cronos is the foreground app, but screen observation "
        "isn’t configured in this session, so I can’t tell what’s happening on screen."
    )
    assert invoker.calls == inference_calls
    assert body["context"]["response_origin"] == "deterministic_grounding_policy"
    assert body["context"]["inference_timing"]["backend_metrics_status"] == "not_applicable"
    assert body["context"]["policy_decision_digest"]

    recovered = client.post("/chat", json=request)
    assert recovered.status_code == 200
    assert recovered.json()["response"] == body["response"]
    assert recovered.json()["context"]["recovered_without_inference"] is True
    assert invoker.calls == inference_calls

    session = chat._CONVERSATION_SERVICE.sessions.load(body["session_id"])
    assistant = next(turn for turn in session["turns"]
        if turn.get("turn_id") == body["turn_id"])
    linkage = assistant["linkage"]
    assert "invocation_receipt_id" not in linkage
    decision = linkage["policy_decision"]
    assert decision["digest"] == body["context"]["policy_decision_digest"]
    assert linkage["assistant_output_lineage"]["status"] == "deterministic_policy_output"

    followup = client.post("/chat", json={
        "session_id": body["session_id"], "message": "Give me one short greeting."
    })
    assert followup.status_code == 200
    assert invoker.calls == inference_calls + 1


def test_unopted_screen_observation_uses_no_model_and_does_not_capture(tmp_path):
    chat = _reload()
    from sentientos.foreground_game_detection import ForegroundGameObservation

    class Detector:
        def observe(self, _names):
            return ForegroundGameObservation("available", True, "c" * 64,
                "2026-11-04T18:30:00+00:00")

    captures = []
    invoker = SimulationInvoker()
    chat.configure_development_chat(invoker=invoker, data_root=tmp_path,
        initial_workload_mode="automatic", foreground_game_detector=Detector(),
        game_process_names=("Cronos-Win64-Shipping.exe",),
        screen_observer=lambda: captures.append("capture"))
    response = TestClient(chat.APP).post("/chat", json={
        "message": "Can you tell what's happening on screen in Cronos right now?"
    })

    assert response.status_code == 200
    assert "I don’t have a screen observation this turn" in response.json()["response"]
    assert response.json()["context"]["response_origin"] == "deterministic_grounding_policy"
    assert invoker.calls == 0
    assert captures == []


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
        self.latency_ms = None
        self.backend_completion = None
        self.output_text = "explicit simulation"
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
        return SimpleNamespace(status="admitted_simulation", output_text=self.output_text,
            output_digest=__import__("hashlib").sha256(
                __import__("json").dumps({"output": self.output_text},
                    sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest(),
            output_truncated=False, request={"request_id": request.request_id,
                "active_model_identity": identity_payload}, receipt_id="simulation-receipt-id",
            receipt_digest="simulation-receipt", latency_ms=self.latency_ms,
            backend_completion=self.backend_completion)


@pytest.mark.parametrize(("configured_window", "expected_window"), [
    (None, "0"), ("5s", "5s"), ("5m", "5m"), ("15m", "15m"),
    ("-1", "-1"),
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
            chat.DevelopmentLocalChatInference(invoker, gaming_keep_alive="10m")


def test_gaming_chat_uses_conversation_budget_but_keeps_checkins_short():
    chat = _reload()
    from sentientos.governed_local_model_invocation import LocalModelInvocationBudget

    class Invoker:
        def __init__(self):
            self.model = SimpleNamespace(
                active_identity=SimpleNamespace(engine="ollama"),
                metadata={"chat_history_format": "role_separated"})
            self.authority_map = SimpleNamespace()
            self.requests = []
        def release_model_residency(self):
            return SimpleNamespace(status="already_unloaded", to_dict=lambda: {})
        def build_request(self, **kwargs):
            self.requests.append(kwargs)
            return kwargs
        def invoke(self, request):
            return request

    invoker = Invoker()
    inference = chat.DevelopmentLocalChatInference(invoker, gaming_keep_alive="-1")
    inference.set_workload_mode("gaming")
    prompt = "[SYSTEM_INSTRUCTION]\nRules\n[VERIFIED_RUNTIME_CONTEXT]\n{}\n[SESSION_HISTORY_DATA]"

    inference.generate(prompt=prompt, caller="test", correlation_id="chat-turn",
        budget=LocalModelInvocationBudget(), caller_linkage={"chat_response_style": "default"})
    inference.generate(prompt=prompt, caller="test", correlation_id="social-turn",
        budget=LocalModelInvocationBudget(), caller_linkage={"chat_response_style": "social_checkin"})

    assert invoker.requests[0]["budget"].max_new_tokens == 96
    assert invoker.requests[0]["budget"].timeout_seconds == 18
    assert invoker.requests[0]["linkage"]["chat_history_format"] == "role_separated"
    assert invoker.requests[1]["budget"].max_new_tokens == 64
    assert invoker.requests[1]["budget"].timeout_seconds == 12


def test_gaming_resource_pressure_uses_durable_non_model_response(tmp_path):
    chat = _reload(); client = TestClient(chat.APP)
    invoker = SimulationInvoker()
    resource_state = {
        "admission_status": "deferred",
        "reason_code": "vram_pressure",
        "vram_utilization_percent": 92.0,
        "observed_at": "2026-11-06T09:00:00+00:00",
        "release_threshold_percent": 85.0,
        "recovery_threshold_percent": 82.0,
    }
    chat.configure_development_chat(invoker=invoker, data_root=tmp_path,
        initial_workload_mode="gaming",
        gaming_resource_status_provider=lambda: resource_state)

    response = client.post("/chat", json={"message": "Tell me a quick joke."})

    assert response.status_code == 200
    body = response.json()
    assert "GPU memory pressure is high" in body["response"]
    assert invoker.calls == 0
    assert body["context"]["response_origin"] == "deterministic_grounding_policy"
    session = chat._CONVERSATION_SERVICE.sessions.load(body["session_id"])
    assistant = next(turn for turn in session["turns"]
        if turn.get("turn_id") == body["turn_id"])
    evidence = assistant["linkage"]["policy_decision"]["payload"]["evidence"]
    assert evidence["gaming_resource_status"] == resource_state


@pytest.mark.parametrize(("foreground", "preload_admission", "expected_calls"), [
    (True, "available", 1),
    (False, "available", 0),
    (True, "deferred", 0),
])
def test_automatic_gaming_reconcile_preloads_only_with_fresh_foreground_headroom(
        foreground, preload_admission, expected_calls):
    chat = _reload()

    class Profile:
        def __init__(self, name):
            self.name = name
            self.active_identity = SimpleNamespace(
                engine="ollama", to_dict=lambda: {"engine": "ollama", "name": name})
            self.loaded = False

        def is_resident(self):
            return self.loaded

    class Authority:
        def record_for_active_identity(self, identity, purpose):
            return object() if purpose == "local_user_chat" else None

    class Invoker:
        def __init__(self, normal, gaming):
            self.model = normal
            self.authority_map = Authority()
            self.preload_calls = []

        def release_model_residency(self, **_kwargs):
            return SimpleNamespace(status="already_unloaded", to_dict=lambda: {
                "status": "already_unloaded"})

        def preload_model_residency(self, **kwargs):
            self.preload_calls.append(kwargs)
            self.model.loaded = True
            return SimpleNamespace(to_dict=lambda: {
                "status": "preloaded", "model_identity_digest": "model-digest"})

    normal, gaming = Profile("normal"), Profile("gaming")
    invoker = Invoker(normal, gaming)
    invoker.model = normal
    detector = SimpleNamespace(observe=lambda _names: SimpleNamespace(
        status="available", game_foreground=foreground, game_process_running=True,
        running_process_name_digests=[], process_name_digest="game",
        observed_at="2026-11-06T09:00:00+00:00", transport_provenance=None))
    resource_state = {"admission_status": "available",
        "preload_admission_status": preload_admission,
        "preload_threshold_percent": 75.0,
        "vram_utilization_percent": 71.0,
        "observed_at": "2026-11-06T09:00:00+00:00"}
    adapter = chat.DevelopmentLocalChatInference(invoker,
        model_profiles={"normal": normal, "gaming": gaming},
        foreground_game_detector=detector, gaming_keep_alive="-1",
        gaming_resource_status_provider=lambda: resource_state)
    adapter.set_workload_mode("automatic", ["Cronos.exe"])

    state = adapter.reconcile_workload_state()

    assert len(invoker.preload_calls) == expected_calls
    assert state["effective_mode"] == "gaming"
    if expected_calls:
        assert invoker.preload_calls[0]["keep_alive"] == "-1"
        assert invoker.preload_calls[0]["resource_state"] == resource_state


def test_chat_response_exposes_bounded_backend_timing_for_diagnostics(tmp_path):
    chat = _reload(); client = TestClient(chat.APP)
    invoker = SimulationInvoker()
    invoker.latency_ms = 4870
    invoker.backend_completion = {
        "backend": "ollama",
        "total_duration_ns": 4_650_000_000,
        "load_duration_ns": 1_200_000_000,
        "prompt_eval_duration_ns": 350_000_000,
        "eval_duration_ns": 3_100_000_000,
        "first_token_duration_ns": 1_760_000_000,
        "prompt_tokens": 286,
        "completion_tokens": 42,
    }
    chat.configure_development_chat(invoker=invoker, data_root=tmp_path)

    response = client.post("/chat", json={"message": "hello"})
    assert response.status_code == 200
    assert response.json()["context"]["inference_timing"] == {
        "backend_metrics_status": "available",
        "invocation_latency_ms": 4870,
        "backend": "ollama",
        "backend_total_duration_ns": 4_650_000_000,
        "load_duration_ns": 1_200_000_000,
        "prompt_evaluation_duration_ns": 350_000_000,
        "generation_duration_ns": 3_100_000_000,
        "first_content_chunk_duration_ns": 1_760_000_000,
        "prompt_tokens": 286,
        "completion_tokens": 42,
    }


def test_chat_stream_reports_model_grounding_and_server_release_timings(tmp_path):
    chat = _reload(); client = TestClient(chat.APP)
    invoker = SimulationInvoker()
    identity_payload = {
        "engine": "ollama",
        "semantic_artifact_identity": "sha256:" + "a" * 64,
        "posture": "development_only",
        "fallback": False,
    }
    invoker.model.active_identity = SimpleNamespace(
        engine="ollama", to_dict=lambda: identity_payload)
    invoker.output_text = "A grounded local reply."
    invoke = invoker.invoke

    def invoke_stream(request, *, on_content_chunk=None):
        receipt = invoke(request)
        if on_content_chunk is not None:
            on_content_chunk(invoker.output_text)
        return receipt

    invoker.invoke = invoke_stream
    chat.configure_development_chat(invoker=invoker, data_root=tmp_path)

    with client.stream("POST", "/chat/stream", json={"message": "Hello."}) as response:
        assert response.status_code == 200
        raw = response.read()
    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    events = [
        json.loads(line.removeprefix("data:").strip())
        for line in text.splitlines() if line.startswith("data:")
    ]

    delta = next(event for event in events if event.get("type") == "delta")
    complete = next(event for event in events if event.get("type") == "complete")
    context = complete["response"]["context"]
    assert type(delta.get("server_elapsed_ns")) is int
    assert delta["server_elapsed_ns"] >= 0
    assert type(complete.get("server_elapsed_ns")) is int
    assert complete["server_elapsed_ns"] >= delta["server_elapsed_ns"]
    assert context["chat_timing"]["model_call_wall_duration_ns"] >= 0
    assert context["chat_timing"]["post_generation_grounding_duration_ns"] >= 0


def test_chat_page_shows_response_stage_timing_controls(tmp_path):
    chat = _reload(); client = TestClient(chat.APP)
    chat.configure_development_chat(invoker=SimulationInvoker(), data_root=tmp_path)

    response = client.get("/")

    assert response.status_code == 200
    assert 'id="response-timing"' in response.text
    assert 'id="response-timing-details"' in response.text
    assert "First browser paint opportunity (double-rAF estimate)" in response.text
    assert "server released grounded text" in response.text
    assert "model first content chunk" in response.text
    assert "backend model load" in response.text
    assert "backend prompt evaluation" in response.text
    assert "backend token generation" in response.text
    assert "grounding policy checks" in response.text
    assert "generation complete to grounded answer" in response.text

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
    assert 'id="conversation-session"' in page
    assert 'id="new-conversation"' in page
    assert "refreshConversationSessions(data.session_id);" in page
    assert "startNewConversation" in page
    assert "changeConversationSession" in page
    assert "initializeConversationView();" in page
    assert "window.addEventListener('storage'" in page
    assert "restoreConversationSession(event.newValue)" in page
    assert "pendingExternalSessionId" in page
    assert "document.visibilityState === 'visible'" in page
    assert "}, 15000);" in page
    assert "content.textContent = turn.text;" in page
    listed = restarted_client.get("/sessions")
    assert listed.status_code == 200
    assert any(session["session_id"] == session_id for session in listed.json())
    remote_client = TestClient(restarted.APP, client=("203.0.113.10", 4321))
    assert remote_client.get(f"/sessions/{session_id}/turns").status_code == 403


def test_friendly_greeting_prompt_uses_verified_sentientos_runtime_context(tmp_path):
    import json

    chat = _reload(); client = TestClient(chat.APP)
    invoker = SimulationInvoker()
    invoker.output_text = (
        "I'm Hermes 4. I don't have feelings, but my training cutoff is 2023."
    )
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
    assert response.json()["response"] == (
        "I'm SentientOS, your local companion. "
        "I'm here and ready to chat. What's on your mind?"
    )
    prompt = invoker.prompts[-1]
    assert "You are SentientOS, the local companion" in prompt
    assert "configured model label names the backend, not you" in prompt
    assert "if asked the model, give its configured label" in prompt
    assert "For check-ins, answer briefly as SentientOS" in prompt
    assert "without claiming moods or lived experiences" in prompt
    assert "beyond a brief reciprocal greeting" in prompt
    assert "Without CURRENT_SCREEN_OBSERVATION_UNTRUSTED, say you cannot see gameplay" in prompt
    assert "Answer the user's point" in prompt
    assert "One reply proves only that turn, not learning" in prompt
    assert "Foreground confirms only the app is open" in prompt
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
    assert "configured_game_process_names only to identify a confirmed foreground app" in prompt
    runtime_block = prompt.split("[VERIFIED_RUNTIME_CONTEXT]\n", 1)[1].split(
        "\n[SESSION_HISTORY_DATA]", 1)[0]
    workload = json.loads(runtime_block)["workload"]
    assert workload["game_foreground"] is True
    assert workload["configured_game_process_names"] == ["cronos-win64-shipping.exe"]
    assert "[VERIFIED_CURRENT_WORKLOAD_FACTS]" in prompt
    assert "Verified foreground game: Cronos (cronos-win64-shipping.exe)" in prompt
    assert "configured_game_process_names only to identify a confirmed foreground app" in prompt
    assert "game screen and actions are not observed this turn" in prompt


def test_configured_screen_capability_status_answers_without_model_or_capture(tmp_path):
    chat = _reload(); client = TestClient(chat.APP)
    invoker = SimulationInvoker()
    captures = []
    chat.configure_development_chat(
        invoker=invoker, data_root=tmp_path,
        screen_observer=lambda: captures.append("capture"),
    )

    response = client.post("/chat", json={
        "message": (
            "Can you see the game screen right now? Is screen observation configured, "
            "and was it included in this message? Distinguish those."
        ),
        "observe_screen": False,
    })

    assert response.status_code == 200
    body = response.json()
    assert body["response"] == (
        "Screen observation is configured for this local session, but it wasn’t "
        "included in this message. It is request-driven, so I can’t describe "
        "the game screen from this turn."
    )
    assert body["context"]["response_origin"] == "deterministic_grounding_policy"
    assert body["context"]["inference_timing"]["backend_metrics_status"] == "not_applicable"
    assert invoker.calls == 0
    assert captures == []

def test_unconfigured_screen_activity_question_uses_verified_capability_fallback(
        tmp_path, monkeypatch):
    from sentientos.foreground_game_detection import ForegroundGameObservation

    chat = _reload(); client = TestClient(chat.APP)
    invoker = SimulationInvoker()
    memory_queries = []
    original_retrieve = chat.CanonicalMemoryStore.retrieve

    def capture_query(store, query, *, limit=4, budget_chars=2000):
        memory_queries.append(query)
        return original_retrieve(store, query, limit=limit, budget_chars=budget_chars)

    class Detector:
        def observe(self, names):
            assert tuple(names) == ("cronos-win64-shipping.exe",)
            return ForegroundGameObservation("available", True, "a" * 64,
                "2026-11-04T16:00:00+00:00")

    monkeypatch.setattr(chat.CanonicalMemoryStore, "retrieve", capture_query)
    chat.configure_development_chat(invoker=invoker, data_root=tmp_path,
        initial_workload_mode="automatic",
        game_process_names=("Cronos-Win64-Shipping.exe",),
        foreground_game_detector=Detector())
    prior = client.post("/chat", json={"message": "Let's talk about the project plan."})
    session_id = prior.json()["session_id"]
    response = client.post("/chat", json={"session_id": session_id,
        "message": "Can you tell what's happening on screen in Cronos right now?"})

    assert prior.status_code == response.status_code == 200
    assert memory_queries == ["Let's talk about the project plan.", ""]
    assert response.json()["response"] == (
        "I can confirm Cronos is the foreground app, but screen observation "
        "isn’t configured in this session, so I can’t tell what’s happening on screen."
    )
    assert response.json()["context"]["response_origin"] == "deterministic_grounding_policy"
    assert response.json()["context"]["selected_turn_count"] == 0
    assert response.json()["context"]["selected_memory_count"] == 0
    assert response.json()["context"]["inference_timing"]["backend_metrics_status"] == "not_applicable"
    assert invoker.calls == 1
    assert len(invoker.prompts) == 1


def test_user_report_evidence_question_is_answered_from_verified_sources_without_inference(
        tmp_path):
    from sentientos.foreground_game_detection import ForegroundGameObservation

    chat = _reload(); client = TestClient(chat.APP)
    invoker = SimulationInvoker()

    class Detector:
        def observe(self, names):
            assert tuple(names) == ("cronos-win64-shipping.exe",)
            return ForegroundGameObservation("available", True, "f" * 64,
                "2026-11-06T16:00:00+00:00")

    chat.configure_development_chat(
        invoker=invoker, data_root=tmp_path,
        initial_workload_mode="automatic",
        game_process_names=("Cronos-Win64-Shipping.exe",),
        foreground_game_detector=Detector(),
    )
    response = client.post("/chat", json={
        "message": (
            "If I tell you something happened in Cronos, can you distinguish "
            "what you observed from what I told you?"
        ),
        "observe_screen": False,
    })

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["response"] == (
        "Yes. I’ll keep your description attributed to you. Process telemetry "
        "establishes only the foreground app; OCR, if included, establishes only "
        "captured text. Current telemetry separately confirms Cronos is foreground. "
        "Screen observation isn’t configured in this session, so I haven’t "
        "independently observed the event."
    )
    assert body["context"]["response_origin"] == "deterministic_grounding_policy"
    assert body["context"]["inference_timing"]["backend_metrics_status"] == "not_applicable"
    assert body["context"]["selected_turn_count"] == 0
    assert body["context"]["selected_memory_count"] == 0
    assert invoker.calls == 0


def test_casual_greeting_with_game_context_reaches_model_instead_of_screen_fallback(
        tmp_path):
    from sentientos.foreground_game_detection import ForegroundGameObservation

    chat = _reload(); client = TestClient(chat.APP)
    invoker = SimulationInvoker()

    class Detector:
        def observe(self, _names):
            return ForegroundGameObservation("available", True, "b" * 64,
                "2026-11-04T16:00:00+00:00")

    chat.configure_development_chat(invoker=invoker, data_root=tmp_path,
        initial_workload_mode="automatic",
        game_process_names=("Cronos-Win64-Shipping.exe",),
        foreground_game_detector=Detector())
    response = client.post("/chat", json={
        "message": (
            "Hey SentientOS, how are you doing tonight? "
            "I am playing Cronos and could use some company."
        ),
        "observe_screen": False,
    })

    assert response.status_code == 200
    body = response.json()
    assert body["response"] == "explicit simulation"
    assert body["context"]["response_origin"] == "model_generated"
    assert invoker.calls == 1


def test_live_emoji_only_social_question_is_replaced_by_one_open_question(tmp_path):
    from sentientos.foreground_game_detection import ForegroundGameObservation

    chat = _reload()
    client = TestClient(chat.APP)
    invoker = SimulationInvoker()
    invoker.output_text = "🎮"

    class Detector:
        def observe(self, _names):
            return ForegroundGameObservation(
                "available", True, "b" * 64, "2026-11-06T12:00:00+00:00")

    chat.configure_development_chat(invoker=invoker, data_root=tmp_path,
        initial_workload_mode="automatic",
        game_process_names=("Cronos-Win64-Shipping.exe",),
        foreground_game_detector=Detector())
    response = client.post("/chat", json={
        "message": (
            "I am taking a short break. Ask me one easy, open-ended question, "
            "and please ask just one at a time."
        ),
        "observe_screen": False,
    })

    assert response.status_code == 200
    body = response.json()
    assert body["response"] == (
        "What’s one thing you’d like to talk about for a minute?"
    )
    assert body["response"].count("?") == 1
    assert body["context"]["response_origin"] == "grounding_policy_fallback"
    assert invoker.calls == 1


def test_live_social_checkin_keeps_only_one_requested_question(tmp_path):
    from sentientos.foreground_game_detection import ForegroundGameObservation

    chat = _reload()
    client = TestClient(chat.APP)
    invoker = SimulationInvoker()
    invoker.output_text = (
        "How's your day so far? Is there anything you're particularly looking forward to?"
    )

    class Detector:
        def observe(self, _names):
            return ForegroundGameObservation(
                "available", True, "c" * 64, "2026-11-06T12:00:00+00:00")

    chat.configure_development_chat(invoker=invoker, data_root=tmp_path,
        initial_workload_mode="automatic",
        game_process_names=("Cronos-Win64-Shipping.exe",),
        foreground_game_detector=Detector())
    response = client.post("/chat", json={
        "message": (
            "I am taking a short break. Ask me one easy, open-ended question, "
            "and please ask just one at a time."
        ),
        "observe_screen": False,
    })

    assert response.status_code == 200
    body = response.json()
    assert body["response"] == "How's your day so far?"
    assert body["context"]["response_origin"] == "grounding_policy_fallback"
    assert invoker.calls == 1


def test_negative_screen_reference_during_social_checkin_reaches_model(tmp_path):
    from sentientos.foreground_game_detection import ForegroundGameObservation

    chat = _reload()
    client = TestClient(chat.APP)
    invoker = SimulationInvoker()

    class Detector:
        def observe(self, _names):
            return ForegroundGameObservation("available", True, "e" * 64,
                "2026-11-05T16:00:00+00:00")

    chat.configure_development_chat(invoker=invoker, data_root=tmp_path,
        initial_workload_mode="automatic",
        game_process_names=("Cronos-Win64-Shipping.exe",),
        foreground_game_detector=Detector())
    response = client.post("/chat", json={
        "message": (
            "I am playing Cronos and could use company. In one warm sentence, tell me "
            "how you'll keep me company, then ask one easy question. "
            "Don't pretend to see what's happening on screen."
        ),
        "observe_screen": False,
    })

    assert response.status_code == 200
    body = response.json()
    assert body["response"] == "explicit simulation"
    assert body["context"]["response_origin"] == "model_generated"
    assert body["context"]["selected_turn_count"] == 0
    assert invoker.calls == 1


def test_visibility_clarification_request_gets_grounded_without_model_inference(tmp_path):
    from sentientos.foreground_game_detection import ForegroundGameObservation

    chat = _reload()
    client = TestClient(chat.APP)
    invoker = SimulationInvoker()

    class Detector:
        def observe(self, _names):
            return ForegroundGameObservation("available", True, "d" * 64,
                "2026-11-04T16:00:00+00:00")

    chat.configure_development_chat(invoker=invoker, data_root=tmp_path,
        initial_workload_mode="automatic",
        game_process_names=("Cronos-Win64-Shipping.exe",),
        foreground_game_detector=Detector())
    response = client.post("/chat", json={
        "message": (
            "Hey SentientOS, I am playing Cronos. Give me a quick friendly check-in, "
            "and be clear if you cannot see the gameplay."
        ),
        "observe_screen": False,
    })

    assert response.status_code == 200
    body = response.json()
    assert body["response"] == (
        "I\'m here with you, but screen observation isn\'t configured, "
        "so I can\'t see the gameplay."
    )
    assert body["context"]["response_origin"] == "deterministic_grounding_policy"
    assert body["context"]["selected_memory_count"] == 0
    assert body["context"]["selected_turn_count"] == 0
    assert invoker.calls == 0


def test_verified_current_situation_uses_only_foreground_and_screen_evidence(
        tmp_path, monkeypatch):
    from sentientos.foreground_game_detection import ForegroundGameObservation

    chat = _reload(); client = TestClient(chat.APP)
    invoker = SimulationInvoker()
    memory_queries = []

    class Detector:
        def observe(self, names):
            assert tuple(names) == ("cronos-win64-shipping.exe",)
            return ForegroundGameObservation("available", True, "c" * 64,
                "2026-11-04T16:00:00+00:00")

    original_retrieve = chat.CanonicalMemoryStore.retrieve
    def capture_query(store, query, *, limit=4, budget_chars=2000):
        memory_queries.append(query)
        return original_retrieve(store, query, limit=limit, budget_chars=budget_chars)

    monkeypatch.setattr(chat.CanonicalMemoryStore, "retrieve", capture_query)
    chat.configure_development_chat(invoker=invoker, data_root=tmp_path,
        initial_workload_mode="automatic",
        game_process_names=("cronos-win64-shipping.exe",),
        foreground_game_detector=Detector())
    response = client.post("/chat", json={
        "message": ("While Cronos is foregrounded, what can SentientOS confidently say "
                    "about the current situation, and what can it not see?"),
        "observe_screen": False,
    })

    assert response.status_code == 200
    body = response.json()
    assert body["response"] == (
        "I can verify Cronos is running in the foreground, and SentientOS is in gaming mode. "
        "Screen observation isn’t configured in this session, so I can’t describe the gameplay."
    )
    assert body["context"]["response_origin"] == "deterministic_grounding_policy"
    assert body["context"]["selected_memory_count"] == 0
    assert body["context"]["selected_turn_count"] == 0
    assert memory_queries == [""]
    assert invoker.calls == 0


def test_background_game_presence_is_grounded_without_claiming_screen_access(tmp_path):
    import json
    from sentientos.foreground_game_detection import ForegroundGameObservation

    chat = _reload()
    client = TestClient(chat.APP)
    invoker = SimulationInvoker()

    class Detector:
        def observe(self, _names):
            return ForegroundGameObservation("available", False, "b" * 64,
                "2026-11-03T17:00:00+00:00",
                game_process_running=True, running_process_name_digests=("c" * 64,))

    chat.configure_development_chat(invoker=invoker, data_root=tmp_path,
        initial_workload_mode="automatic",
        game_process_names=("Cronos-Win64-Shipping.exe",),
        foreground_game_detector=Detector())
    response = client.post("/chat", json={"message": "Is Cronos still running?"})

    assert response.status_code == 200
    prompt = invoker.prompts[-1]
    runtime_block = prompt.split("[VERIFIED_RUNTIME_CONTEXT]\n", 1)[1].split(
        "\n[SESSION_HISTORY_DATA]", 1)[0]
    workload = json.loads(runtime_block)["workload"]
    assert workload["game_foreground"] is False
    assert workload["game_process_running"] is True
    assert workload["configured_game_process_names"] == ["cronos-win64-shipping.exe"]
    assert workload["effective_mode"] == "gaming"
    assert "An allowlisted game process is running, but the game is not foreground." in prompt
    assert "game screen and actions are not observed this turn" in prompt


def test_background_game_presence_is_grounded_without_claiming_screen_access(tmp_path):
    import json
    from sentientos.foreground_game_detection import ForegroundGameObservation

    chat = _reload()
    client = TestClient(chat.APP)
    invoker = SimulationInvoker()

    class Detector:
        def observe(self, _names):
            return ForegroundGameObservation("available", False, "b" * 64,
                "2026-11-03T17:00:00+00:00",
                game_process_running=True, running_process_name_digests=("c" * 64,))

    chat.configure_development_chat(invoker=invoker, data_root=tmp_path,
        initial_workload_mode="automatic",
        game_process_names=("Cronos-Win64-Shipping.exe",),
        foreground_game_detector=Detector())
    response = client.post("/chat", json={"message": "Is Cronos still running?"})

    assert response.status_code == 200
    prompt = invoker.prompts[-1]
    runtime_block = prompt.split("[VERIFIED_RUNTIME_CONTEXT]\n", 1)[1].split(
        "\n[SESSION_HISTORY_DATA]", 1)[0]
    workload = json.loads(runtime_block)["workload"]
    assert workload["game_foreground"] is False
    assert workload["game_process_running"] is True
    assert workload["configured_game_process_names"] == ["cronos-win64-shipping.exe"]
    assert workload["effective_mode"] == "gaming"
    assert "An allowlisted game process is running, but the game is not foreground." in prompt
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
    assert "Foreground confirms only the app is open" in invoker.prompts[-1]
    assert "Without CURRENT_SCREEN_OBSERVATION_UNTRUSTED, say you cannot see gameplay" in invoker.prompts[-1]


def test_unconfigured_screen_question_gets_truthful_capability_fallback(tmp_path):
    chat = _reload(); client = TestClient(chat.APP)
    invoker = SimulationInvoker()
    chat.configure_development_chat(invoker=invoker, data_root=tmp_path)

    def misleading_reply(request):
        invoker.calls += 1
        output = "Enable additional permissions and I can see the game."
        digest = __import__("hashlib").sha256(
            __import__("json").dumps({"output": output}, sort_keys=True,
                separators=(",", ":")).encode()).hexdigest()
        return SimpleNamespace(status="admitted_simulation", output_text=output,
            output_digest=digest, output_truncated=False, request={
                "request_id": request.request_id, "active_model_identity":
                    (invoker.model.active_identity.to_dict()
                     if invoker.model.active_identity is not None else {})},
            receipt_id="simulation-screen-capability-id",
            receipt_digest="simulation-screen-capability-digest")
    invoker.invoke = misleading_reply
    response = client.post("/chat", json={
        "message": "Can you see my game screen in this session, or would I need to enable something first?"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["response"] == (
        "I can’t see the game in this session because screen observation isn’t configured; "
        "the per-message option alone won’t change that. I can still reason from what you "
        "describe, suggest next checks, and use clues you share in this conversation.")
    assert payload["context"]["response_origin"] == "grounding_policy_fallback"


def test_live_chat_hides_internal_workload_label_in_screen_capability_answer(tmp_path):
    chat = _reload(); client = TestClient(chat.APP)
    invoker = SimulationInvoker()
    invoker.output_text = (
        "VERIFIED_CURRENT_WORKLOAD_FACTS indicates that screen observation "
        "is configured, but it was not included in this message.")
    chat.configure_development_chat(
        invoker=invoker, data_root=tmp_path, screen_observer=lambda: None,
        screen_capture_policy="request_driven")

    response = client.post("/chat", json={
        "message": "Can you see the game screen right now?"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["response"] == (
        "Screen observation is configured for this local session, but it is "
        "request-driven and wasn’t included in this message. I can’t describe "
        "the game unless you request an observation.")
    assert payload["context"]["response_origin"] == "grounding_policy_fallback"


def test_live_chat_distinguishes_configured_screen_observation_from_per_turn_capture(tmp_path):
    chat = _reload(); client = TestClient(chat.APP)
    invoker = SimulationInvoker()
    invoker.output_text = "Screen observation isn't configured in this session."
    chat.configure_development_chat(
        invoker=invoker, data_root=tmp_path, screen_observer=lambda: None,
        screen_capture_policy="request_driven")

    response = client.post("/chat", json={
        "message": "Can you see my game screen?"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["response"] == (
        "Screen observation is configured for this local session, but it is "
        "request-driven and wasn’t included in this message. I can’t describe "
        "the game unless you request an observation.")
    assert payload["context"]["response_origin"] == "grounding_policy_fallback"


def test_social_system_instruction_echo_is_corrected_in_live_chat_path(tmp_path):
    chat = _reload(); client = TestClient(chat.APP)
    invoker = SimulationInvoker()
    chat.configure_development_chat(invoker=invoker, data_root=tmp_path)

    def echoed_instruction(request):
        invoker.calls += 1
        output = "I'm doing well, thanks for asking. How about you?"
        digest = __import__("hashlib").sha256(
            __import__("json").dumps({"output": output}, sort_keys=True,
                separators=(",", ":")).encode()).hexdigest()
        return SimpleNamespace(status="admitted_simulation", output_text=output,
            output_digest=digest, output_truncated=False, request={
                "request_id": request.request_id, "active_model_identity":
                    (invoker.model.active_identity.to_dict()
                     if invoker.model.active_identity is not None else {})},
            receipt_id="simulation-echo-receipt", receipt_digest="simulation-echo-digest")
    invoker.invoke = echoed_instruction
    response = client.post("/chat", json={
        "message": "Hi, how is your evening going?"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["response"] == "I’m here and ready to chat. How’s your evening going?"
    assert payload["context"]["response_origin"] == "grounding_policy_fallback"


def test_live_chat_corrects_elliptical_gaming_checkin_before_general_grounding(tmp_path):
    chat = _reload(); client = TestClient(chat.APP)
    invoker = SimulationInvoker()
    invoker.output_text = (
        "I am here in SentientOS. How about you enjoy your gaming session with Cronos?"
    )
    chat.configure_development_chat(invoker=invoker, data_root=tmp_path)

    response = client.post("/chat", json={"message": "Hey, how are you doing in there?"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["response"] == "I’m here and ready to chat. How are you doing?"
    assert payload["context"]["response_origin"] == "grounding_policy_fallback"


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


def test_remind_me_recall_uses_original_user_statement_not_prior_recall_question(tmp_path):
    chat = _reload(); client = TestClient(chat.APP)
    invoker = SimulationInvoker()
    chat.configure_development_chat(invoker=invoker, data_root=tmp_path)
    session_id = client.post("/sessions").json()["session_id"]
    sessions = chat._get_conversation_service().sessions
    distractor = sessions.append_turn(session_id, role="user", text=(
        "Morning. Ask me a new specific question about where I discover new music."))
    sessions.append_turn(session_id, role="assistant", text=(
        "Would you rather discover an artist through an album or a playlist?"),
        linkage={"source_user_turn_id": distractor["turn_id"]})
    source = sessions.append_turn(session_id, role="user", text=(
        "Streaming services. Ask me a different, specific question about new pop I discover."))
    sessions.append_turn(session_id, role="assistant", text=(
        "What kind of new pop do you enjoy finding?"),
        linkage={"source_user_turn_id": source["turn_id"]})
    prior_recall = sessions.append_turn(session_id, role="user", text=(
        "Earlier, remind me what I said about where I discover new music."))
    sessions.append_turn(session_id, role="assistant", text=(
        "Would you like me to remind you?"),
        linkage={"source_user_turn_id": prior_recall["turn_id"]})

    response = client.post("/chat", json={"session_id": session_id,
        "message": ("Please remind me what I said about where I discover new music, "
                    "then ask one different, specific question about music with two choices.")})

    assert response.status_code == 200
    assert response.json()["context"]["selected_turn_count"] == 1
    assert "Streaming services. Ask me a different" in invoker.prompts[-1]
    assert "Morning. Ask me a new specific question" not in invoker.prompts[-1]
    assert "Earlier, remind me what I said" not in invoker.prompts[-1]
    assert "final prior USER_DATA turn" in invoker.prompts[-1]
    assert "Answer the recalled fact directly" in invoker.prompts[-1]
    assert "state only what the user said" in invoker.prompts[-1]


def test_prior_assistant_question_recall_selects_relevant_older_exchange(tmp_path):
    chat = _reload(); client = TestClient(chat.APP)
    invoker = SimulationInvoker()
    chat.configure_development_chat(invoker=invoker, data_root=tmp_path)
    session_id = client.post("/sessions").json()["session_id"]
    sessions = chat._get_conversation_service().sessions
    first_user = sessions.append_turn(session_id, role="user", text=(
        "I am settling in for a relaxed Cronos session. Keep me company and ask "
        "one easy question about what I enjoy."))
    sessions.append_turn(session_id, role="assistant", text=(
        "What’s the most relaxing thing you do when you’re not gaming?"),
        linkage={"source_user_turn_id": first_user["turn_id"]})
    later_user = sessions.append_turn(session_id, role="user", text=(
        "Let us keep it low-key; ask me a different easy question."))
    sessions.append_turn(session_id, role="assistant", text=(
        "What quiet activity would you like to try soon?"),
        linkage={"source_user_turn_id": later_user["turn_id"]})
    prior_recall_user = sessions.append_turn(session_id, role="user", text=(
        "Earlier, you asked me what I find relaxing when I am not gaming. "
        "What exactly was your question?"))
    sessions.append_turn(session_id, role="assistant", text=(
        "You mentioned wanting to know what feels relaxing outside gaming."),
        linkage={"source_user_turn_id": prior_recall_user["turn_id"]})

    request = {"session_id": session_id, "request_id": "prior-question-recall",
        "message": ("Earlier, you asked me what I find relaxing when I am not gaming. "
                    "What exactly was your question?")}
    recall = client.post("/chat", json=request)

    assert recall.status_code == 200, recall.text
    body = recall.json()
    assert body["response"] == "What’s the most relaxing thing you do when you’re not gaming?"
    assert body["context"]["response_origin"] == "transcript_recall"
    assert body["context"]["transcript_recall_kind"] == "prior_assistant_question"
    assert body["context"]["selected_turn_count"] >= 1
    assert body["context"]["selected_memory_count"] == 0
    assert invoker.calls == 0

    replay = client.post("/chat", json=request)
    assert replay.status_code == 200
    assert replay.json()["response"] == body["response"]
    assert replay.json()["context"]["recovered_without_inference"] is True
    assert invoker.calls == 0



def test_generic_prior_question_topic_recall_uses_latest_verified_question(tmp_path):
    chat = _reload(); client = TestClient(chat.APP)
    invoker = SimulationInvoker()
    chat.configure_development_chat(invoker=invoker, data_root=tmp_path)
    session_id = client.post("/sessions").json()["session_id"]
    sessions = chat._get_conversation_service().sessions
    prior_user = sessions.append_turn(session_id, role="user", text=(
        "Please ask me one easy question about music. Do not mention Cronos."))
    sessions.append_turn(session_id, role="assistant", text=(
        "How do you feel about classical music?"),
        linkage={"source_user_turn_id": prior_user["turn_id"]})

    request = {"session_id": session_id, "request_id": "generic-prior-topic-recall",
        "message": ("Continuity check after restart: what topic did you ask about "
                    "in the previous interface check?")}
    response = client.post("/chat", json=request)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["response"] == "How do you feel about classical music?"
    assert body["context"]["response_origin"] == "transcript_recall"
    assert body["context"]["transcript_recall_kind"] == "prior_assistant_question"
    assert body["context"]["selected_memory_count"] == 0
    assert invoker.calls == 0

def test_earliest_session_recall_selects_first_user_turn(tmp_path, monkeypatch):
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
        "message": "For my opening request, greet me and ask about Cronos."})
    second = client.post("/chat", json={"session_id": session_id,
        "message": "Later I asked whether the game screen was visible."})
    recall = client.post("/chat", json={"session_id": session_id,
        "message": "What did I ask you first in this conversation?"})

    assert first.status_code == second.status_code == recall.status_code == 200
    assert memory_queries == [
        "For my opening request, greet me and ask about Cronos.",
        "Later I asked whether the game screen was visible.",
        "",
    ]
    prompt = invoker.prompts[-1]
    assert "first prior USER_DATA turn" in prompt
    assert "For my opening request, greet me and ask about Cronos." in prompt
    assert "Later I asked whether the game screen was visible." not in prompt
    assert recall.json()["context"]["selected_turn_count"] == 1


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


def test_what_did_you_just_say_selects_latest_assistant_reply(tmp_path, monkeypatch):
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
    latest = client.post("/chat", json={"session_id": sid,
        "message": "Please focus on Cronos frame pacing."})
    recall = client.post("/chat", json={"session_id": sid,
        "message": "What did you just say?"})

    assert first.status_code == latest.status_code == recall.status_code == 200
    assert memory_queries == ["", "Please focus on Cronos frame pacing.", ""]
    assert recall.json()["response"] == latest.json()["response"]
    assert recall.json()["context"]["response_origin"] == "transcript_recall"
    assert recall.json()["context"]["selected_turn_count"] == 2
    assert recall.json()["context"]["selected_memory_count"] == 0
    assert invoker.calls == 2


def test_recent_semantic_assistant_recall_uses_transcript_without_memories(tmp_path, monkeypatch):
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
    session_id = first.json()["session_id"]
    followup = client.post("/chat", json={"session_id": session_id,
        "message": "What was the thing you said you could not see?"})

    assert first.status_code == followup.status_code == 200
    assert memory_queries == ["", ""]
    assert "ASSISTANT_DATA: " in invoker.prompts[-1]
    assert "Can you see my screen?" in invoker.prompts[-1]
    assert followup.json()["context"]["selected_turn_count"] == 2
    assert followup.json()["context"]["selected_memory_count"] == 0


def test_direct_recent_assistant_recall_returns_verified_transcript_and_recovers_idempotently(tmp_path):
    chat = _reload(); client = TestClient(chat.APP)
    invoker = SimulationInvoker()
    chat.configure_development_chat(invoker=invoker, data_root=tmp_path)
    first = client.post("/chat", json={"message": "Give me one concise Cronos tip."})
    assert first.status_code == 200
    session_id = first.json()["session_id"]
    original_reply = first.json()["response"]
    calls_after_original = invoker.calls

    request = {
        "session_id": session_id,
        "request_id": "direct-recent-reply-recall",
        "message": "What did you just tell me you could help with?",
    }
    recall = client.post("/chat", json=request)
    assert recall.status_code == 200
    body = recall.json()
    assert body["response"] == original_reply
    assert body["context"]["response_origin"] == "transcript_recall"
    assert body["context"]["selected_memory_count"] == 0
    assert body["context"]["selected_turn_count"] == 2
    assert body["context"]["inference_timing"]["backend_metrics_status"] == "not_applicable"
    assert invoker.calls == calls_after_original

    recovered = client.post("/chat", json=request)
    assert recovered.status_code == 200
    assert recovered.json()["response"] == original_reply
    assert recovered.json()["context"]["recovered_without_inference"] is True
    assert recovered.json()["context"]["response_origin"] == "transcript_recall"
    assert invoker.calls == calls_after_original

    session = chat._CONVERSATION_SERVICE.sessions.load(session_id)
    assistant = next(turn for turn in session["turns"]
        if turn.get("turn_id") == body["turn_id"])
    assert assistant["linkage"]["source_assistant_turn_id"] == first.json()["turn_id"]
    assert assistant["linkage"]["assistant_output_lineage"]["status"] == "transcript_recall_output"


def test_direct_recent_user_question_recall_uses_verified_transcript_without_inference(
        tmp_path):
    chat = _reload(); client = TestClient(chat.APP)
    invoker = SimulationInvoker()
    chat.configure_development_chat(invoker=invoker, data_root=tmp_path)
    prior_message = "Hey SentientOS, how are you doing tonight? Keep it natural and brief."
    first = client.post("/chat", json={"message": prior_message})
    assert first.status_code == 200
    session_id = first.json()["session_id"]
    calls_after_first_turn = invoker.calls
    request = {
        "session_id": session_id,
        "request_id": "direct-prior-user-question-recall",
        "message": "What did I just ask you?",
    }

    recall = client.post("/chat", json=request)

    assert recall.status_code == 200
    body = recall.json()
    assert body["response"] == f"You asked: “{prior_message}”"
    assert body["context"]["response_origin"] == "transcript_recall"
    assert body["context"]["inference_timing"]["backend_metrics_status"] == "not_applicable"
    assert body["context"]["selected_memory_count"] == 0
    prior_user_turn = chat._CONVERSATION_SERVICE.sessions.load(session_id)["turns"][0]
    assert prior_user_turn["role"] == "user"
    assert body["context"]["recalled_user_turn_id"] == prior_user_turn["turn_id"]
    assert invoker.calls == calls_after_first_turn

    recovered = client.post("/chat", json=request)

    assert recovered.status_code == 200
    assert recovered.json()["response"] == body["response"]
    assert recovered.json()["context"]["recovered_without_inference"] is True
    assert invoker.calls == calls_after_first_turn


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


@pytest.mark.parametrize("message", [
    "What did I say was written on the note I found?",
    "Earlier in our chat, I said a note in Cronos read two words. "
    "What were they? Answer briefly from our conversation, and do not claim to see the screen.",
    "Earlier I told you about a note I found in Cronos. "
    "What did the note say? Please answer briefly.",
])
def test_referential_user_recall_selects_matching_older_turn_without_memories(
        tmp_path, monkeypatch, message):
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
    sessions = chat._CONVERSATION_SERVICE.sessions
    note_turn = sessions.append_turn(
        session_id, role="user",
        text="I have now found a note that reads east wing.")
    sessions.append_turn(
        session_id, role="user",
        text=("Can you see the current Cronos gameplay? Answer briefly from the "
              "screen-observation status and the fact that Cronos is foreground; "
              "do not guess about the scene."))
    sessions.append_turn(
        session_id, role="user",
        text="I found an old key near the west wing.")
    for index in range(12):
        sessions.append_turn(
            session_id, role="user",
            text=f"Unrelated recent turn {index}: " + "inventory status " * 28)
    prior_recall_question = (
        "Earlier I told you about a note I found in Cronos. "
        "What did the note say? Please answer briefly.")
    sessions.append_turn(
        session_id, role="user", text=prior_recall_question)

    assert client.post("/workload-mode", json={"mode": "gaming"}).status_code == 200
    response = client.post("/chat", json={
        "session_id": session_id,
        "message": message,
    })

    assert response.status_code == 200
    assert memory_queries == [""]
    prompt = invoker.prompts[-1]
    assert note_turn["text"] in prompt
    assert "I found an old key near the west wing." not in prompt
    assert "Unrelated recent turn" not in prompt
    expected_recall_question_count = 1 if message == prior_recall_question else 0
    assert prompt.count(prior_recall_question) == expected_recall_question_count
    assert response.json()["context"]["selected_turn_count"] == 1
    assert response.json()["context"]["selected_memory_count"] == 0



def test_referential_recall_excludes_prior_anaphoric_recall_question(tmp_path, monkeypatch):
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
    sessions = chat._CONVERSATION_SERVICE.sessions
    note_turn = sessions.append_turn(
        session_id, role="user",
        text="I have now found a note that reads east wing.")
    prior_recall_question = (
        "Earlier in our chat, I said a note in Cronos read two words. "
        "What were they? Answer briefly from our conversation, and do not claim to see the screen.")
    sessions.append_turn(session_id, role="user", text=prior_recall_question)

    response = client.post("/chat", json={
        "session_id": session_id,
        "message": "What were the two words on the Cronos note I mentioned earlier?",
    })

    assert response.status_code == 200
    assert memory_queries == [""]
    prompt = invoker.prompts[-1]
    assert note_turn["text"] in prompt
    assert prior_recall_question not in prompt
    assert response.json()["context"]["selected_turn_count"] == 1
    assert response.json()["context"]["selected_memory_count"] == 0

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
    live_checkin = (
        "I am playing Cronos and could use some company. "
        "What kind of companion would you like to be during a game?"
    )
    checkin = client.post("/chat", json={"session_id": session_id,
        "message": live_checkin})

    assert checkin.status_code == 200
    assert memory_queries == ["I am taking a breather between fights in Cronos.", ""]
    prompt = invoker.prompts[-1]
    assert "I am taking a breather between fights in Cronos." not in prompt
    assert live_checkin in prompt
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
    assert chat._is_social_checkin_request(
        "I am playing Cronos and could use some company. What kind of companion would you like to be during a game?") is True
    assert checkin.json()["context"]["selected_turn_count"] == 0
    assert chat._is_social_checkin_request(
        "Ask one specific, easy question about an everyday preference, not a general invitation. Keep it brief.") is True
    assert chat._is_social_checkin_request(
        "I am taking a short break. Ask me one easy, open-ended question, and please ask just one at a time.") is True
    assert chat._is_social_checkin_request(
        "Codex acceptance check: Give one natural, brief reply and ask one specific, open question "
        "about what makes a game story memorable. Do not claim to see my screen.") is True
    assert chat._is_social_checkin_request(
        "I mentioned earlier that I made it through a rough fight in Cronos. "
        "You did not see it yourself; can you ask me one natural question about how it went?") is True
    assert chat._is_social_checkin_continuation(
        "That's the kind of vibe I want. Ask me one easy question about my run.") is True
    assert chat._is_social_checkin_continuation(
        "Ask one specific, easy question about an everyday preference, not a general invitation. Keep it brief.") is True
    assert chat._is_social_checkin_continuation(live_checkin) is False

    followup_message = "That's the kind of vibe I want. Ask me one easy question about my run."
    followup = client.post("/chat", json={"session_id": session_id,
        "message": followup_message})
    assert followup.status_code == 200
    assert memory_queries == ["I am taking a breather between fights in Cronos.", "", ""]
    followup_prompt = invoker.prompts[-1]
    assert followup_message in followup_prompt
    assert live_checkin in followup_prompt
    assert checkin.json()["response"] in followup_prompt
    assert "I am taking a breather between fights in Cronos." not in followup_prompt
    assert "MEMORY_DATA:" not in followup_prompt
    assert followup.json()["context"]["selected_turn_count"] == 2
    assert followup.json()["context"]["selected_memory_count"] == 0
    assert chat.GamingWorkloadPolicy.GAMING_SOCIAL_CHECKIN_INSTRUCTION in followup_prompt

    explicit_checkin = client.post("/chat", json={"session_id": session_id,
        "message": ("Quick chat test between fights: just tell me you are here with me, "
                    "then ask one easy question.")})
    assert explicit_checkin.status_code == 200
    assert memory_queries == [
        "I am taking a breather between fights in Cronos.", "", "", ""
    ]
    assert explicit_checkin.json()["context"]["selected_turn_count"] == 0
    assert explicit_checkin.json()["context"]["selected_memory_count"] == 0
    assert chat.GamingWorkloadPolicy.GAMING_SOCIAL_CHECKIN_INSTRUCTION in invoker.prompts[-1]

    grounded_checkin_message = (
        "How is the co-pilot shift going? Tell me one thing you can verify about my setup "
        "and one thing you cannot currently see. Keep it friendly and brief."
    )
    grounded_checkin = client.post("/chat", json={"session_id": session_id,
        "message": grounded_checkin_message})
    assert grounded_checkin.status_code == 200
    assert memory_queries[-1] == ""
    assert grounded_checkin.json()["context"]["selected_turn_count"] == 0
    assert grounded_checkin.json()["context"]["selected_memory_count"] == 0
    assert grounded_checkin_message in invoker.prompts[-1]
    assert "MEMORY_DATA:" not in invoker.prompts[-1]
    assert chat.GamingWorkloadPolicy.GAMING_SOCIAL_CHECKIN_INSTRUCTION in invoker.prompts[-1]

    assert chat._is_social_checkin_request(
        "How is the co-pilot shift going? Tell me one verified thing about my setup."
    ) is True
    assert chat._is_social_checkin_request(
        "So, how's your night going as my gaming sidekick?"
    ) is True
    assert chat._is_social_checkin_request(
        "What's one thing you'd like to ask me about the kinds of games I enjoy?"
    ) is True
    assert chat._is_social_checkin_request(
        "I prefer one simple question at a time—what else are you curious about?"
    ) is True
    assert chat._is_social_checkin_continuation(
        "I prefer one simple question at a time—what else are you curious about?"
    ) is True


def test_different_specific_followup_uses_recent_exchange_without_memory(tmp_path):
    chat = _reload()
    client = TestClient(chat.APP)
    invoker = SimulationInvoker()
    chat.configure_development_chat(invoker=invoker, data_root=tmp_path)
    assert client.post("/workload-mode", json={"mode": "gaming"}).status_code == 200

    first_message = (
        "Ask me one specific, easy question about music, with two clear choices."
    )
    first = client.post("/chat", json={"message": first_message})
    assert first.status_code == 200

    followup_message = (
        "Upbeat pop. Ask me one different, specific question about when I listen to it."
    )
    assert chat._is_social_checkin_request(followup_message) is True
    assert chat._is_social_checkin_continuation(followup_message) is True
    followup = client.post("/chat", json={
        "session_id": first.json()["session_id"],
        "message": followup_message,
    })

    assert followup.status_code == 200
    prompt = invoker.prompts[-1]
    assert followup_message in prompt
    assert first_message in prompt
    assert first.json()["response"] in prompt
    assert chat.GamingWorkloadPolicy.GAMING_SOCIAL_CHECKIN_INSTRUCTION in prompt
    assert followup.json()["context"]["selected_turn_count"] == 2
    assert followup.json()["context"]["selected_memory_count"] == 0


def test_gaming_chat_trims_old_history_and_keeps_recent_turns_under_input_ceiling(tmp_path):
    from sentientos.gaming_workload_policy import GamingWorkloadPolicy

    chat = _reload(); client = TestClient(chat.APP)
    invoker = SimulationInvoker()
    chat.configure_development_chat(invoker=invoker, data_root=tmp_path)
    session_id = None
    for index in range(3):
        response = client.post("/chat", json={
            "message": ("Turn 0: remember violet comet. " if index == 0 else
                        f"Turn {index}: ") + ("remember this detail " * 75),
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
    assert "Turn 2:" in invoker.prompts[-1]
    assert "Turn 0: remember violet comet." not in invoker.prompts[-1]


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
            self.process_running = False
        def observe(self, _names):
            return ForegroundGameObservation("available", self.foreground,
                "a" * 64, "2026-11-03T17:00:00+00:00", {"source_id": "windows"},
                game_process_running=self.process_running,
                running_process_name_digests=(("c" * 64,) if self.process_running else
                    (() if self.process_running is False else None)))

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
    detector.process_running = True
    background_state = inference.current_workload_state()
    assert background_state["mode"] == "automatic"
    assert background_state["effective_mode"] == "gaming"
    assert background_state["game_foreground"] is False
    assert background_state["game_process_running"] is True
    assert background_state["mode_source"] == "allowlisted_game_process_running"

    detector.process_running = False
    state = inference.current_workload_state()
    assert state["effective_mode"] == "normal"
    assert state["foreground_game_detected"] is False
    assert state["configured_game_process_names"] == ["cronos-win64-shipping.exe"]
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
                "b" * 64, "2026-11-03T20:00:00+00:00", {"source_id": "windows"},
                game_process_running=False, running_process_name_digests=())

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
                "c" * 64, "2026-11-03T20:00:00+00:00", {"source_id": "windows"},
                game_process_running=False, running_process_name_digests=())

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

def test_development_chat_only_uses_explicit_per_message_screen_observation(tmp_path):
    chat = _reload(); client = TestClient(chat.APP)
    invoker = SimulationInvoker()
    observations = []
    screen_observation = {
        "modality": "screen",
        "text": "objective: reach the observatory",
        "captured_at": "2026-11-04T12:00:00Z",
        "backend": "local-ocr-fixture",
        "capture_digest": "a" * 64,
        "process_name_digest": "b" * 64,
        "consent_id_digest": "c" * 64,
        "capture_scope": "allowlisted_foreground_game_client_area",
        "raw_frame_retained": False,
        "text_truncated": False,
        "text_change_kind": "initial",
        "previous_text_digest": None,
        "bridge_message_provenance": {"source_id": "test-screen"},
    }

    def observe_screen():
        observations.append("requested")
        return screen_observation

    chat.configure_development_chat(invoker=invoker, data_root=tmp_path,
        screen_observer=observe_screen)
    assert client.get("/screen-observation").json() == {
        "configured": True, "capture_policy": "request_driven",
        "per_message_opt_in_required": True}
    without_screen = client.post("/chat", json={"message": "Hello"})
    assert without_screen.status_code == 200
    assert observations == []
    with_screen = client.post("/chat", json={
        "message": "What does the objective say?", "observe_screen": True})
    assert with_screen.status_code == 200
    assert observations == ["requested"]
    assert "[CURRENT_SCREEN_OBSERVATION_UNTRUSTED]" in invoker.prompts[-1]
    assert "objective: reach the observatory" in invoker.prompts[-1]


def test_chat_stream_logs_only_safe_screen_observation_failure_code(caplog, tmp_path):
    chat = _reload()
    client = TestClient(chat.APP)
    from sentientos.screen_observation_bridge import ScreenObservationBridgeError

    def fail_screen_observation():
        raise ScreenObservationBridgeError("screen_observation_request_timeout")

    invoker = SimulationInvoker()
    invoker.model.active_identity = SimpleNamespace(engine="ollama")
    invoke = invoker.invoke

    def invoke_stream(request, *, on_content_chunk=None):
        receipt = invoke(request)
        if on_content_chunk is not None:
            on_content_chunk(invoker.output_text)
        return receipt

    invoker.invoke = invoke_stream
    chat.configure_development_chat(
        invoker=invoker, data_root=tmp_path,
        screen_observer=fail_screen_observation)
    with caplog.at_level("WARNING"):
        with client.stream("POST", "/chat/stream", json={
            "message": "Read only my current consented game screen.",
            "observe_screen": True,
        }) as response:
            assert response.status_code == 200
            raw = response.read()

    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    events = [
        json.loads(line.removeprefix("data:").strip())
        for line in text.splitlines() if line.startswith("data:")
    ]
    assert events[-1] == {"type": "error", "code": "chat_generation_failed"}
    assert "failure_code=screen_observation_request_timeout" in caplog.text
    assert "Read only my current consented game screen." not in caplog.text


def test_no_readable_screen_text_answers_direct_gameplay_question_without_inference(tmp_path):
    chat = _reload(); client = TestClient(chat.APP)
    invoker = SimulationInvoker()
    from sentientos.foreground_game_detection import ForegroundGameObservation

    class Detector:
        def observe(self, _names):
            return ForegroundGameObservation(
                "available", True, "a" * 64, "2026-11-05T06:00:00+00:00",
                {"source_id": "windows-game-observer"},
                game_process_running=True, running_process_name_digests=("b" * 64,))

    screen_observation = {
        "modality": "screen", "text": "", "text_status": "no_readable_text",
        "captured_at": "2026-11-05T06:00:00Z", "backend": "local-ocr",
        "capture_digest": "c" * 64, "process_name_digest": "d" * 64,
        "consent_id_digest": "e" * 64,
        "capture_scope": "allowlisted_foreground_game_client_area",
        "raw_frame_retained": False, "text_truncated": False,
        "text_change_kind": "initial", "previous_text_digest": None,
        "visual_change_kind": "initial", "visual_change_score": None,
    }
    chat.configure_development_chat(
        invoker=invoker, data_root=tmp_path,
        screen_observer=lambda: screen_observation,
        initial_workload_mode="automatic", foreground_game_detector=Detector(),
        game_process_names=("Cronos-Win64-Shipping.exe",))

    response = client.post("/chat", json={
        "message": "Can you describe what's happening in Cronos right now?",
        "observe_screen": True,
    })

    assert response.status_code == 200
    payload = response.json()
    assert payload["response"] == (
        "I can confirm Cronos is the foreground app, but OCR found no readable text "
        "in the captured game screen, so I can’t describe the scene from this text-only observation."
    )
    assert invoker.calls == 0
    turns = chat._get_conversation_service().sessions.load(payload["session_id"])["turns"]
    policy = turns[-1]["linkage"]["policy_decision"]["payload"]
    assert policy["reason_code"] == "screen_capture_no_readable_text"
    assert policy["evidence"]["screen_observation_provenance"] == {
        "capture_digest": "c" * 64,
        "text_digest": __import__("hashlib").sha256(b"").hexdigest(),
        "text_status": "no_readable_text",
        "captured_at": "2026-11-05T06:00:00Z",
        "raw_frame_retained": False,
    }


def test_screen_status_distinguishes_capture_policy_from_message_inclusion(tmp_path):
    chat = _reload(); client = TestClient(chat.APP)
    invoker = SimulationInvoker()
    chat.configure_development_chat(invoker=invoker, data_root=tmp_path)
    assert client.get("/screen-observation").json() == {
        "configured": False,
        "capture_policy": "disabled",
        "per_message_opt_in_required": True,
    }

    chat.configure_development_chat(invoker=invoker, data_root=tmp_path,
        screen_observer=lambda: None,
        screen_capture_policy="allowlisted_session_polling")
    assert client.get("/screen-observation").json() == {
        "configured": True,
        "capture_policy": "allowlisted_session_polling",
        "per_message_opt_in_required": True,
    }


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
    assert payload["response"] == "I’m here with you in SentientOS. How’s the session going?"
    assert payload["context"]["response_origin"] == "grounding_policy_fallback"


def test_verified_workload_and_screen_limits_are_grounded_for_background_game(tmp_path):
    from sentientos.foreground_game_detection import ForegroundGameObservation

    chat = _reload()
    client = TestClient(chat.APP)
    invoker = SimulationInvoker()

    class Detector:
        def observe(self, _names):
            return ForegroundGameObservation("available", False, "d" * 64,
                "2026-11-04T19:40:00+00:00",
                game_process_running=True, running_process_name_digests=("e" * 64,))

    chat.configure_development_chat(invoker=invoker, data_root=tmp_path,
        initial_workload_mode="automatic",
        game_process_names=("Cronos-Win64-Shipping.exe",),
        foreground_game_detector=Detector())
    response = client.post("/chat", json={"message": (
        "What can you verify about my current workload right now, and what can you "
        "not observe? Please answer briefly and do not guess about the game screen."
    )})

    assert response.status_code == 200
    body = response.json()
    assert body["response"] == (
        "I can verify Cronos is running in the background, and SentientOS is in gaming mode. "
        "Screen observation isn’t configured in this session, so I can’t describe the gameplay."
    )
    assert body["context"]["response_origin"] == "deterministic_grounding_policy"
    assert body["context"]["inference_timing"]["backend_metrics_status"] == "not_applicable"
    assert invoker.calls == 0


def test_combined_status_and_screen_question_returns_verified_background_state(tmp_path):
    from sentientos.foreground_game_detection import ForegroundGameObservation

    chat = _reload()
    client = TestClient(chat.APP)
    invoker = SimulationInvoker()

    class Detector:
        def observe(self, _names):
            return ForegroundGameObservation(
                "available", False, "d" * 64,
                "2026-11-05T05:00:00+00:00",
                game_process_running=True, running_process_name_digests=("e" * 64,),
            )

    chat.configure_development_chat(
        invoker=invoker,
        data_root=tmp_path,
        initial_workload_mode="automatic",
        foreground_game_detector=Detector(),
        game_process_names=("Cronos-Win64-Shipping.exe",),
    )
    response = client.post("/chat", json={
        "message": (
            "What do you currently know about Cronos on this computer, and can you see "
            "the game screen? Be concise and distinguish running from foreground."
        ),
        "observe_screen": False,
    })

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["response"] == (
        "I can verify Cronos is running in the background, and SentientOS is in gaming mode. "
        "Screen observation isn’t configured in this session, so I can’t describe the gameplay."
    )
    assert body["context"]["response_origin"] == "deterministic_grounding_policy"
    assert body["context"]["selected_turn_count"] == 0
    assert body["context"]["selected_memory_count"] == 0
    assert body["context"].get("screen_observation_provenance") is None
    assert invoker.calls == 0



def test_development_chat_shutdown_releases_its_active_ollama_model(tmp_path):
    chat = _reload()
    invoker = SimulationInvoker()
    identity = {"engine": "ollama", "semantic_artifact_identity": "sha256:" + "a" * 64,
        "posture": "development_only", "fallback": False}
    invoker.model.active_identity = SimpleNamespace(
        engine="ollama", to_dict=lambda: identity)
    released = []

    def release_model_residency(*, reason_code="gaming_mode_entered"):
        released.append(reason_code)
        return SimpleNamespace(status="released",
            to_dict=lambda: {"status": "released", "reason_code": reason_code})

    invoker.release_model_residency = release_model_residency
    chat.configure_development_chat(invoker=invoker, data_root=tmp_path)
    chat.close_production_chat()

    assert released == ["development_chat_shutdown"]
    assert chat._CONVERSATION_SERVICE is None
