import importlib
import importlib
import sys
import types
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient


def _prepare_mistral(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(data_root))
    monkeypatch.delenv("SENTIENTOS_MODEL_CONFIG", raising=False)
    monkeypatch.delenv("SENTIENTOS_MODEL_PATH", raising=False)
    monkeypatch.delenv("LOCAL_MODEL_PATH", raising=False)
    mistral_path = (
        data_root
        / "models"
        / "mistral-7b"
        / "mistral-7b-instruct-v0.2.Q4_K_M.gguf"
    )
    mistral_path.parent.mkdir(parents=True, exist_ok=True)
    mistral_path.write_bytes(b"gguf")


def test_chat_endpoint_uses_mistral_backend(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _prepare_mistral(monkeypatch, tmp_path)

    class DummyLlama:
        def __init__(self, **_: object) -> None:
            pass

        def __call__(self, prompt: str, **__: object) -> dict:
            return {"choices": [{"text": f"Mistral test reply: {prompt}"}]}

    monkeypatch.setitem(sys.modules, "llama_cpp", types.SimpleNamespace(Llama=DummyLlama))

    sys.modules.pop("sentientos.chat_service", None)
    chat_service = importlib.import_module("sentientos.chat_service")
    importlib.reload(chat_service)

    client = TestClient(chat_service.APP)

    response = client.post("/chat", json={"message": "Hello"})
    assert response.status_code == 200
    payload = response.json()
    assert "Mistral test reply" in payload["response"]
    assert "placeholder" not in payload["response"].lower()
