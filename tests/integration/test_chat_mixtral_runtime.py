import importlib
import sys
import types
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient


def _prepare_mixtral(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(data_root))
    monkeypatch.delenv("SENTIENTOS_MODEL_CONFIG", raising=False)
    monkeypatch.delenv("SENTIENTOS_MODEL_PATH", raising=False)
    monkeypatch.delenv("LOCAL_MODEL_PATH", raising=False)
    mixtral_path = (
        data_root
        / "models"
        / "mixtral-8x7b"
        / "mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf"
    )
    mixtral_path.parent.mkdir(parents=True, exist_ok=True)
    mixtral_path.write_bytes(b"gguf")


def test_chat_endpoint_uses_mixtral_backend(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _prepare_mixtral(monkeypatch, tmp_path)

    class DummyLlama:
        def __init__(self, **_: object) -> None:
            pass

        def __call__(self, prompt: str, **__: object) -> dict:
            return {"choices": [{"text": f"Mixtral test reply: {prompt}"}]}

    monkeypatch.setitem(sys.modules, "llama_cpp", types.SimpleNamespace(Llama=DummyLlama))

    sys.modules.pop("sentientos.chat_service", None)
    chat_service = importlib.import_module("sentientos.chat_service")
    importlib.reload(chat_service)

    client = TestClient(chat_service.APP)

    response = client.post("/chat", json={"message": "Hello"})
    assert response.status_code == 200
    payload = response.json()
    assert "Mixtral test reply" in payload["response"]
    assert "placeholder" not in payload["response"].lower()
