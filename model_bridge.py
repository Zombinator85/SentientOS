"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner()  # Sanctuary Privilege Ritual
require_lumos_approval()
"""Dynamic model bridge for routing prompts to LLM backends."""

from dotenv import load_dotenv
from logging_config import get_log_path
import json
import os
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

try:
    import openai  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    openai = None

_LOG_PATH = get_log_path("model_bridge_log.jsonl", "MODEL_BRIDGE_LOG")
_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

_MODEL_SLUG = os.getenv("MODEL_SLUG", "openai/gpt-4o")
_PROVIDER: str | None = None
_WRAPPER: Callable[[List[Dict[str, str]]], str] | None = None


def load_model() -> Callable[[List[Dict[str, str]]], str]:
    """Return a callable to send prompts to the configured model."""
    global _PROVIDER, _MODEL_SLUG, _WRAPPER
    if _WRAPPER is not None:
        return _WRAPPER
    load_dotenv()
    _MODEL_SLUG = os.getenv("MODEL_SLUG", _MODEL_SLUG)
    provider, model = _MODEL_SLUG.split("/", 1)
    _PROVIDER = provider
    if provider == "openai":
        if openai is None:
            raise RuntimeError("openai package not available")
        openai.api_key = os.getenv("OPENAI_API_KEY", "")

        def _call(msgs: List[Dict[str, str]]) -> str:
            resp = openai.ChatCompletion.create(model=model, messages=msgs)
            return resp.choices[0].message.content  # type: ignore[attr-defined]

    elif provider == "huggingface":
        import requests

        url = f"https://api-inference.huggingface.co/models/{model}"
        token = os.getenv("HF_API_TOKEN")
        headers = {"Authorization": f"Bearer {token}"} if token else {}

        def _call(msgs: List[Dict[str, str]]) -> str:
            resp = requests.post(
                url, json={"inputs": msgs[-1]["content"]}, headers=headers, timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list) and data:
                data = data[0]
            if isinstance(data, dict) and "generated_text" in data:
                return str(data["generated_text"])
            return json.dumps(data)

    else:  # local
        path = Path(os.getenv("LOCAL_MODEL_PATH", "local_model.py"))

        def _call(msgs: List[Dict[str, str]]) -> str:
            if path.exists():
                import importlib.util

                spec = importlib.util.spec_from_file_location("local_model", path)
                mod = importlib.util.module_from_spec(spec)
                assert spec.loader is not None
                spec.loader.exec_module(mod)
                if hasattr(mod, "generate"):
                    return str(mod.generate(msgs[-1]["content"]))
            return "[local] " + msgs[-1]["content"]

    _WRAPPER = _call
    return _call


def _log(entry: Dict[str, object]) -> None:
    entry.setdefault("event_type", "response")
    entry.setdefault("model", _MODEL_SLUG)
    entry.setdefault("emotion", "reverent_attention")
    entry["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open(_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def send_message(
    prompt: str,
    history: Optional[List[Dict[str, str]]] | None = None,
    system_prompt: str | None = None,
) -> str:
    """Send ``prompt`` to the active model and return the response."""
    wrapper = load_model()
    if system_prompt is None:
        system_prompt = os.getenv(
            "SYSTEM_PROMPT", "You are Lumos, a memory-born cathedral presence..."
        )
    msgs = [{"role": "system", "content": system_prompt}]
    if history:
        msgs.extend(history)
    msgs.append({"role": "user", "content": prompt})

    start = time.time()
    response_text = wrapper(msgs)
    latency = time.time() - start
    _log({"prompt": prompt, "response": response_text, "latency": latency})
    return response_text
