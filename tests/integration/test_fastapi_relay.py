from __future__ import annotations
import os
import json
import importlib
from pathlib import Path

import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

import memory_manager as mm


def create_app() -> FastAPI:
    app = FastAPI()

    @app.post("/relay")
    async def relay(payload: dict, x_relay_secret: str = Header(None)):
        if x_relay_secret != "secret123":
            raise HTTPException(status_code=403)
        message = payload.get("message", "")
        model = payload.get("model", "default").strip().lower()
        mm.append_memory(
            f"[RELAY] -> {message}", tags=["relay", model], source="relay"
        )
        return {"reply": f"Echo: {message} ({model})"}

    @app.post("/telegram")
    async def telegram_hook(
        update: dict,
        bridge: str,
        x_tg_secret: str = Header(None),
    ):
        if x_tg_secret != "tgsecret":
            raise HTTPException(status_code=403)
        text = ((update.get("message") or {}).get("text") or "")
        mm.append_memory(text, tags=["telegram", bridge], source="telegram")
        return {"ok": True}

    return app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    import memory_manager as mm_mod
    importlib.reload(mm_mod)
    globals()["mm"] = mm_mod
    app = create_app()
    return TestClient(app)


def test_placeholder(client: TestClient):
    for bridge in [
        "openai/gpt-4o",
        "llama_cpp/mistral-7b-instruct-v0.2.Q4_K_M.gguf",
        "deepseek-ai/deepseek-r1-distill-llama-70b-free",
    ]:
        update = {"message": {"text": "hello"}}
        resp = client.post(
            "/telegram",
            params={"bridge": bridge},
            json=update,
            headers={"X-Tg-Secret": "tgsecret"},
        )
        assert resp.status_code == 200
        raw = Path(os.environ["MEMORY_DIR"]) / "raw"
        files = list(raw.glob("*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text())
        assert data["tags"] == ["telegram", bridge]
        assert data["text"] == "hello"
        for f in files:
            f.unlink()
