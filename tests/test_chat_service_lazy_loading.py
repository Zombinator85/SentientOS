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
        return SimpleNamespace(status="admitted_simulation", output_text="explicit simulation",
            output_digest=__import__("hashlib").sha256(
                __import__("json").dumps({"output": "explicit simulation"},
                    sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            output_truncated=False, request={"request_id": request.request_id,
                "active_model_identity": {}}, receipt_id="simulation-receipt-id",
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
