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
    def build_request(self, **kwargs):
        return SimpleNamespace(request_id="simulation-request", **kwargs)
    def invoke(self, request):
        self.calls += 1
        return SimpleNamespace(status="admitted_simulation", output_text="explicit simulation",
            request={"request_id": request.request_id}, receipt_digest="simulation-receipt")


def test_model_work_requires_explicit_simulation_composition(tmp_path):
    chat = _reload(); client = TestClient(chat.APP)
    assert client.post("/chat", json={"message": "hello"}).status_code == 503
    invoker = SimulationInvoker()
    chat.configure_development_chat(invoker=invoker, data_root=tmp_path)
    response = client.post("/chat", json={"message": "hello"})
    assert response.status_code == 200
    assert response.json()["response"] == "explicit simulation"
    assert invoker.calls == 1
