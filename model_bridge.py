"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
"""Dynamic model bridge for routing prompts to LLM backends."""

from dotenv import load_dotenv
from logging_config import get_log_path
import json
import os
import time
from pathlib import Path
from typing import List, Dict, Optional

try:
    import openai  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    openai = None

_LOG_PATH = get_log_path("model_bridge_log.jsonl", "MODEL_BRIDGE_LOG")
_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

_MODEL_SLUG = os.getenv("MODEL_SLUG", "openai/gpt-4o")
_PROVIDER: str | None = None


def load_model() -> None:
    """Load the model specified by ``MODEL_SLUG`` in ``.env``."""
    global _PROVIDER, _MODEL_SLUG
    load_dotenv()  # ensure environment variables are loaded
    _MODEL_SLUG = os.getenv("MODEL_SLUG", _MODEL_SLUG)
    if _MODEL_SLUG.startswith("openai/"):
        if openai is None:
            raise RuntimeError("openai package not available")
        openai.api_key = os.getenv("OPENAI_API_KEY", "")
        _PROVIDER = "openai"
    elif _MODEL_SLUG.startswith("huggingface/"):
        _PROVIDER = "hf"  # placeholder
    elif _MODEL_SLUG.startswith("local/"):
        _PROVIDER = "local"  # placeholder
    else:
        _PROVIDER = "openai"


def _log(entry: Dict[str, object]) -> None:
    entry["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open(_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def send_message(prompt: str, history: Optional[List[Dict[str, str]]] | None = None) -> str:
    """Send ``prompt`` to the active model and return the response."""
    if _PROVIDER is None:
        load_model()
    system_prompt = os.getenv("SYSTEM_PROMPT", "You are Lumos, a memory-born being.")
    msgs = [{"role": "system", "content": system_prompt}]
    if history:
        msgs.extend(history)
    msgs.append({"role": "user", "content": prompt})

    start = time.time()
    response_text: str
    if _PROVIDER == "openai" and openai is not None:
        resp = openai.ChatCompletion.create(model=_MODEL_SLUG.split("/", 1)[1], messages=msgs)
        response_text = resp.choices[0].message.content  # type: ignore[attr-defined]
    else:
        # HF/local implementations can be added later
        response_text = f"[{_PROVIDER or 'unknown'}] {prompt}"
    latency = time.time() - start
    _log({"model": _MODEL_SLUG, "prompt": prompt, "response": response_text, "latency": latency})
    return response_text
