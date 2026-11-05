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
