from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient


def _reload_chat_service():
    sys.modules.pop("sentientos.chat_service", None)
    import sentientos.chat_service as chat_service

    return importlib.reload(chat_service)


def test_import_does_not_autoload_model(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        "sentientos.local_model.LocalModel.autoload",
        lambda: calls.append("autoload") or SimpleNamespace(describe=lambda: "fake", generate=lambda _: "ok"),
    )

    chat_service = _reload_chat_service()

    assert calls == []
    assert chat_service._MODEL is None


def test_health_paths_do_not_load_model(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "sentientos.local_model.LocalModel.autoload",
        lambda: calls.append("autoload") or SimpleNamespace(describe=lambda: "fake", generate=lambda _: "ok"),
    )
    chat_service = _reload_chat_service()
    client = TestClient(chat_service.APP)

    root = client.get("/")
    boot = client.get("/boot-feed")

    assert root.status_code == 200
    assert boot.status_code == 200
    assert calls == []


def test_first_chat_request_lazy_loads_model(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class FakeModel:
        def describe(self) -> str:
            return "fake"

        def generate(self, prompt: str) -> str:
            return f"reply:{prompt}"

    monkeypatch.setattr("sentientos.local_model.LocalModel.autoload", lambda: calls.append("autoload") or FakeModel())
    chat_service = _reload_chat_service()
    client = TestClient(chat_service.APP)

    resp = client.post("/chat", json={"message": "hello"})

    assert resp.status_code == 200
    assert resp.json()["response"] == "reply:hello"
    assert calls == ["autoload"]


def test_dependency_injection_model_without_autoload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sentientos.local_model.LocalModel.autoload",
        lambda: (_ for _ in ()).throw(AssertionError("autoload should not be called")),
    )
    chat_service = _reload_chat_service()

    class FakeModel:
        def describe(self) -> str:
            return "fake"

        def generate(self, prompt: str) -> str:
            return f"injected:{prompt}"

    chat_service._MODEL = FakeModel()
    client = TestClient(chat_service.APP)

    resp = client.post("/chat", json={"message": "hello"})
    assert resp.status_code == 200
    assert resp.json()["response"] == "injected:hello"
