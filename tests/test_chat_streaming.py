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


def test_chat_stream_emits_provisional_deltas_then_governed_completion(monkeypatch):
    chat = _reload()

    class StreamingService:
        def streaming_available(self):
            return True

        def cancel_active_generation(self):
            return True

        def chat(self, message, *, session_id=None, retain=False, request_id=None,
                 observe_screen=False, on_content_chunk=None):
            assert message == "hello"
            on_content_chunk("Hello ")
            on_content_chunk("there.")
            return chat.ChatResponse(response="Hello there.", session_id="session-1",
                turn_id="turn-1", context={"inference_timing": {"backend_metrics_status": "available"}},
                retention={"status": "not_requested"})

    monkeypatch.setattr(chat, "_get_conversation_service", lambda: StreamingService())
    monkeypatch.setattr(chat, "_CHANGE_NARRATOR", None)

    response = TestClient(chat.APP).post("/chat/stream", json={"message": "hello"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert body.index('"type":"delta","text":"Hello "') < body.index('"type":"delta","text":"there."')
    assert body.index('"type":"delta","text":"there."') < body.index('"type":"complete"')
    assert '"response":"Hello there."' in body


def test_development_adapter_does_not_advertise_streaming_for_non_ollama_model(
        tmp_path, monkeypatch):
    chat = _reload()

    class NonStreamingInvoker:
        model = SimpleNamespace(active_identity=None)

    chat.configure_development_chat(invoker=NonStreamingInvoker(), data_root=tmp_path)
    monkeypatch.setattr(chat, "_CHANGE_NARRATOR", None)

    response = TestClient(chat.APP).post("/chat/stream", json={"message": "hello"})

    assert response.status_code == 503
    assert response.json()["detail"] == "Streaming is unavailable for this model backend"


def test_chat_stream_rejects_backend_without_streaming_support(monkeypatch):
    chat = _reload()
    monkeypatch.setattr(chat, "_get_conversation_service",
        lambda: SimpleNamespace(streaming_available=lambda: False))
    monkeypatch.setattr(chat, "_CHANGE_NARRATOR", None)

    response = TestClient(chat.APP).post("/chat/stream", json={"message": "hello"})
    assert response.status_code == 503
    assert response.json()["detail"] == "Streaming is unavailable for this model backend"


def test_companion_page_renders_streamed_deltas_and_keeps_backend_fallback():
    chat = _reload()

    response = TestClient(chat.APP).get("/")

    assert response.status_code == 200
    assert "fetch('/chat/stream'" in response.text
    assert "responseTextEl.textContent += chunk" in response.text
    assert "fetch('/chat'," in response.text



def test_grounded_stream_never_publishes_rejected_model_text():
    import sentientos.chat_service as chat

    published = []
    chat._publish_grounded_model_stream(
        published.append, ["I'm doing great! ", "How are you?"],
        generated_text="I'm doing great! How are you?",
        response_text="I’m here and ready to chat. How are you doing?",
        response_origin="grounding_policy_fallback",
    )

    assert published == ["I’m here and ready to chat. How are you doing?"]


def test_grounded_stream_preserves_chunks_for_accepted_model_text():
    import sentientos.chat_service as chat

    published = []
    chat._publish_grounded_model_stream(
        published.append, ["Hello ", "there."],
        generated_text="Hello there.", response_text="Hello there.",
        response_origin="model_generated",
    )

    assert published == ["Hello ", "there."]


def test_stream_publishes_only_final_text_when_grounding_replaces_model_draft(
        tmp_path, monkeypatch):
    import hashlib
    import json
    from types import SimpleNamespace

    chat = _reload()
    identity_payload = {
        "engine": "ollama",
        "semantic_artifact_identity": "sha256:" + "a" * 64,
        "posture": "development_only",
        "fallback": False,
    }

    class StreamingInvoker:
        def __init__(self):
            self.model = SimpleNamespace(active_identity=SimpleNamespace(
                engine="ollama", to_dict=lambda: identity_payload
            ))

        def build_request(self, **kwargs):
            return {
                "request_id": "stream-grounding-test",
                "active_model_identity": identity_payload,
                **kwargs,
            }

        def release_model_residency(self):
            return SimpleNamespace(status="already_unloaded",
                to_dict=lambda: {"status": "already_unloaded"})

        def invoke(self, request, *, on_content_chunk=None):
            output = "Enable permissions and I can see the game."
            if on_content_chunk is not None:
                on_content_chunk("Enable permissions ")
                on_content_chunk("and I can see the game.")
            return SimpleNamespace(
                status="admitted_simulation",
                output_text=output,
                output_digest=hashlib.sha256(json.dumps(
                    {"output": output}, sort_keys=True,
                    separators=(",", ":")).encode()).hexdigest(),
                output_truncated=False,
                request={
                    "request_id": request["request_id"],
                    "active_model_identity": identity_payload,
                    "linkage": request.get("linkage", {}),
                },
                receipt_id="stream-grounding-receipt",
                receipt_digest="stream-grounding-receipt-digest",
            )

    chat.configure_development_chat(invoker=StreamingInvoker(), data_root=tmp_path)
    monkeypatch.setattr(chat, "_CHANGE_NARRATOR", None)
    response = TestClient(chat.APP).post("/chat/stream", json={
        "message": "Can you see my game screen in this session?",
    })

    assert response.status_code == 200
    events = []
    for block in response.text.strip().split("\n\n"):
        lines = block.splitlines()
        event = next((line[7:] for line in lines if line.startswith("event: ")), None)
        data = next((json.loads(line[6:]) for line in lines
                     if line.startswith("data: ")), None)
        if event and data:
            events.append((event, data))
    deltas = [data["text"] for event, data in events if event == "delta"]
    complete = next(data["response"] for event, data in events if event == "complete")

    assert deltas == [complete["response"]]
    assert complete["response"] == (
        "I can’t see the game in this session because screen observation isn’t configured; "
        "the per-message option alone won’t change that. I can still reason from what you "
        "describe, suggest next checks, and use clues you share in this conversation.")
    assert "Enable permissions" not in "".join(deltas)
    assert complete["context"]["response_origin"] == "grounding_policy_fallback"
