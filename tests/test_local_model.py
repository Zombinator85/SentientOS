from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

from sentientos.local_model import LocalModel


def _write_config(tmp_path: Path, data: dict) -> Path:
    config_path = tmp_path / "model_config.json"
    config_path.write_text(json.dumps(data), encoding="utf-8")
    return config_path


def _prepare_candidate(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    path.mkdir(parents=True, exist_ok=True)
    (path / "model.json").write_text(json.dumps({"description": name}), encoding="utf-8")
    return path


def test_local_model_smoke(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    primary_dir = _prepare_candidate(tmp_path, "primary")
    config = {
        "candidates": [
            {
                "path": str(primary_dir),
                "engine": "echo",
                "name": "Echo Primary",
            }
        ]
    }
    config_path = _write_config(tmp_path, config)
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(data_root))
    monkeypatch.setenv("SENTIENTOS_MODEL_CONFIG", str(config_path))

    model = LocalModel.autoload()

    description = model.describe()
    assert "Echo Primary" in description


def test_local_model_inference(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    primary_dir = _prepare_candidate(tmp_path, "primary")
    config = {
        "generation": {"temperature": 0.5, "max_new_tokens": 32},
        "candidates": [
            {
                "path": str(primary_dir),
                "engine": "echo",
                "name": "Echo Primary",
            }
        ],
    }
    config_path = _write_config(tmp_path, config)
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(data_root))
    monkeypatch.setenv("SENTIENTOS_MODEL_CONFIG", str(config_path))

    model = LocalModel.autoload()

    response = model.generate("Hello world", history=["previous message"])
    assert isinstance(response, str)
    assert response


def test_local_model_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    fallback_dir = _prepare_candidate(tmp_path, "fallback")
    config = {
        "candidates": [
            {
                "path": str(tmp_path / "missing"),
                "engine": "echo",
                "name": "Missing Primary",
            },
            {
                "path": str(fallback_dir),
                "engine": "echo",
                "name": "Echo Fallback",
            },
        ]
    }
    config_path = _write_config(tmp_path, config)
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(data_root))
    monkeypatch.setenv("SENTIENTOS_MODEL_CONFIG", str(config_path))

    model = LocalModel.autoload()

    assert model.metadata.get("name") == "Echo Fallback"


def test_local_model_generate_resilient(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    primary_dir = _prepare_candidate(tmp_path, "primary")
    config = {
        "candidates": [
            {
                "path": str(primary_dir),
                "engine": "echo",
                "name": "Echo Primary",
            }
        ]
    }
    config_path = _write_config(tmp_path, config)
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(data_root))
    monkeypatch.setenv("SENTIENTOS_MODEL_CONFIG", str(config_path))

    model = LocalModel.autoload()

    response_empty = model.generate(None, history=None)
    assert isinstance(response_empty, str)
    assert response_empty

    response_malformed = model.generate("", history=["", None, 42])
    assert isinstance(response_malformed, str)
    assert response_malformed


def test_local_model_gguf_mixtral_backend(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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

    class DummyLlama:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def __call__(self, prompt: str, **_: object) -> dict:
            return {"choices": [{"text": f"Mixtral echoes: {prompt}"}]}

    monkeypatch.setitem(sys.modules, "llama_cpp", types.SimpleNamespace(Llama=DummyLlama))

    model = LocalModel.autoload()

    assert "Mixtral" in model.metadata.get("name", "")
    response = model.generate("Hello cathedral")
    assert "Mixtral echoes" in response
