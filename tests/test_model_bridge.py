"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import json
import types
from importlib import reload
from pathlib import Path

import model_bridge as mb
import pytest

pytestmark = pytest.mark.no_legacy_skip


def _configure_bridge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, provider: str) -> Path:
    log = tmp_path / "log.jsonl"
    monkeypatch.setenv("MODEL_BRIDGE_LOG", str(log))
    monkeypatch.setenv("MODEL_PROVIDER", provider)
    return log


def test_send_local(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = _configure_bridge(tmp_path, monkeypatch, "llama_cpp")
    reload(mb)
    local = types.SimpleNamespace(
        create_chat_completion=lambda *, messages: {
            "choices": [{"message": {"content": "local:" + messages[-1]["content"]}}]
        }
    )
    monkeypatch.setattr(mb, "_initialise_llama", lambda: local)
    res = mb.send_message("hello", system_prompt="sys", emotion="joy", emit=False)
    assert res["response"] == "local:hello"
    lines = [json.loads(x) for x in log.read_text().splitlines()]
    assert lines[-1]["prompt"] == "hello"
    assert lines[-1]["emotion"] == "joy"


@pytest.mark.parametrize("provider", ["openai", "huggingface"])
def test_external_provider_fails_closed_before_transport(
    provider: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = _configure_bridge(tmp_path, monkeypatch, provider)
    secret = "credential-must-not-escape"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    monkeypatch.setenv("HF_API_TOKEN", secret)
    reload(mb)

    with pytest.raises(RuntimeError) as excinfo:
        mb.send_message("arbitrary https://example.invalid text", emit=False)

    assert "unavailable in model_bridge" in str(excinfo.value)
    assert secret not in str(excinfo.value)
    assert not log.exists()


def test_external_sdk_and_http_paths_are_removed() -> None:
    source = Path(mb.__file__).read_text(encoding="utf-8")
    prohibited = (
        "import openai",
        "ChatCompletion.create",
        "import requests",
        "requests.post",
        "api-inference.huggingface.co",
        "OPENAI_API_KEY",
        "HF_API_TOKEN",
        "import socket",
    )
    assert all(primitive not in source for primitive in prohibited)


def test_arbitrary_text_cannot_select_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_bridge(tmp_path, monkeypatch, "llama_cpp")
    reload(mb)
    seen: list[list[dict[str, str]]] = []
    def create_chat_completion(*, messages: list[dict[str, str]]) -> dict[str, object]:
        seen.append(messages)
        return {"choices": [{"message": {"content": "offline"}}]}

    local = types.SimpleNamespace(create_chat_completion=create_chat_completion)
    monkeypatch.setattr(mb, "_initialise_llama", lambda: local)

    result = mb.send_message(
        "openai huggingface https://api.example secret-looking-input",
        system_prompt="offline",
        emit=False,
    )

    assert result["response"] == "offline"
    assert seen[-1][-1]["content"].startswith("openai huggingface")
