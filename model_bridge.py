# Sanctuary privilege ritual must appear before any code or imports
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
from typing import Any, Callable, Dict, List, Optional

from sentientos.local_model import LocalModel, ModelLoadError

_GUI_BUS: Any | None
try:
    from parliament_bus import bus as _GUI_BUS
except Exception:  # pragma: no cover - optional dependency
    _GUI_BUS = None

try:
    import openai
except Exception:  # pragma: no cover - optional dependency
    openai = None

_LOG_PATH = get_log_path("model_bridge_log.jsonl", "MODEL_BRIDGE_LOG")
_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

_MODEL_SLUG = os.getenv("MODEL_SLUG", "sentientos/mixtral-8x7b-instruct")
_PROVIDER: str | None = None
_WRAPPER: Callable[[List[Dict[str, str]]], str] | None = None


def load_model() -> Callable[[List[Dict[str, str]]], str]:
    """Return a callable to send prompts to the configured model."""
    global _PROVIDER, _MODEL_SLUG, _WRAPPER
    if _WRAPPER is not None:
        return _WRAPPER
    load_dotenv()
    raw_slug = os.getenv("MODEL_SLUG", _MODEL_SLUG)
    if not raw_slug:
        raw_slug = "sentientos/mixtral-8x7b-instruct"
    if "/" in raw_slug:
        provider, model = raw_slug.split("/", 1)
    else:
        provider, model = "sentientos", raw_slug
        raw_slug = f"{provider}/{model}"
    _MODEL_SLUG = raw_slug
    _PROVIDER = provider
    if provider == "openai":
        if openai is None:
            raise RuntimeError("openai package not available")
        openai.api_key = os.getenv("OPENAI_API_KEY", "")

        def _call(msgs: List[Dict[str, str]]) -> str:
            resp = openai.ChatCompletion.create(model=model, messages=msgs)
            return str(resp.choices[0].message.content)

    elif provider == "mixtral":
        import requests

        url = os.getenv("OLLAMA_URL", "http://localhost:11434")

        def _call(msgs: List[Dict[str, str]]) -> str:
            resp = requests.post(
                f"{url}/api/chat",
                json={"model": model, "messages": msgs},
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                msg = data.get("message") or data.get("choices", [{}])[0].get("message")
                if isinstance(msg, dict) and "content" in msg:
                    return str(msg["content"])
            return json.dumps(data)

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

    elif provider == "sentientos":
        try:
            local_model = LocalModel.autoload()
        except ModelLoadError as exc:
            raise RuntimeError(f"Local model unavailable: {exc}") from exc

        def _call(msgs: List[Dict[str, str]]) -> str:
            return local_model.generate(msgs[-1]["content"])

    else:  # local python shim
        path = Path(os.getenv("LOCAL_MODEL_PATH", "local_model.py"))

        def _call(msgs: List[Dict[str, str]]) -> str:
            if path.exists():
                import importlib.util

                spec = importlib.util.spec_from_file_location("local_model", path)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
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
    *,
    emotion: str = "reverent_attention",
    emit: bool = True,
) -> Dict[str, object]:
    """Send ``prompt`` to the active model and return a result dict."""
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
    latency = int((time.time() - start) * 1000)
    result = {
        "response": response_text,
        "model": _MODEL_SLUG,
        "latency_ms": latency,
        "emotion": emotion,
    }
    entry = {"prompt": prompt, **result}
    _log(entry)

    if emit and _GUI_BUS is not None:
        try:
            import asyncio

            async def _pub() -> None:
                await _GUI_BUS.publish(entry)

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(_pub())
            except RuntimeError:
                asyncio.run(_pub())
        except Exception:
            pass

    return result
