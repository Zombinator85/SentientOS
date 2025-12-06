# Sanctuary privilege ritual must appear before any code or imports
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()  # Sanctuary Privilege Ritual
require_lumos_approval()
"""Dynamic model bridge for routing prompts to LLM backends."""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from dotenv import load_dotenv
from llama_cpp import Llama

from logging_config import get_log_path
from sentientos.local_model import ModelLoadError

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

_LOGGER = logging.getLogger(__name__)

_DEFAULT_MODEL_NAME = "Mistral-7B Instruct v0.2 (GGUF)"
_BOUND_MODEL_PATH = Path(
    "C:/SentientOS/sentientos_data/models/mistral-7b/"
    "mistral-7b-instruct-v0.2.Q4_K_M.gguf"
)
_MODEL_POINTER = Path("C:/SentientOS/config/model_path.txt")
_HARDWARE_PROFILE = Path("C:/SentientOS/config/hardware_profile.json")
_DEFAULT_CONTEXT_LENGTH = 32768
_DEFAULT_CHAT_TEMPLATE = "mistral-instruct"

_MODEL_SLUG = os.getenv("MODEL_SLUG", _DEFAULT_MODEL_NAME)
_PROVIDER: str | None = None
_WRAPPER: Callable[[List[Dict[str, str]]], str] | None = None
_LLAMA: Llama | None = None


def _load_hardware_profile() -> dict[str, object]:
    if _HARDWARE_PROFILE.exists():
        try:
            return json.loads(_HARDWARE_PROFILE.read_text(encoding="utf-8"))
        except Exception:  # pragma: no cover - resilience first
            pass
    profile = {
        "gpu": False,
        "cuda_runtime": False,
        "avx": False,
        "model_precision": "Q4_K",
        "mode": "cpu",
    }
    _HARDWARE_PROFILE.parent.mkdir(parents=True, exist_ok=True)
    _HARDWARE_PROFILE.write_text(json.dumps(profile, indent=2))
    return profile


def _detect_model_path() -> Path:
    """Resolve the model path, honoring an explicit override when allowed."""

    explicit = os.getenv("SENTIENTOS_MODEL_PATH") or os.getenv("LOCAL_MODEL_PATH")
    override_allowed = os.getenv("SENTIENTOS_ALLOW_MODEL_OVERRIDE") == "1"
    if explicit and override_allowed:
        _LOGGER.info("Using explicitly provided model path: %s", explicit)
        return Path(explicit)

    if _MODEL_POINTER.exists():
        pointer = _MODEL_POINTER.read_text(encoding="utf-8").strip()
        if pointer:
            candidate = Path(pointer)
            if candidate.exists():
                return candidate
            _LOGGER.warning("model_path.txt pointed to missing file: %s", pointer)

    profile = _load_hardware_profile()
    if not profile.get("avx", True):
        _LOGGER.warning("AVX missing; forcing Q4_K model preference")
    _MODEL_POINTER.parent.mkdir(parents=True, exist_ok=True)
    _MODEL_POINTER.write_text(str(_BOUND_MODEL_PATH), encoding="utf-8")
    return _BOUND_MODEL_PATH


def _detect_gpu_layers() -> int:
    try:
        import torch

        if torch.cuda.is_available():
            return -1
    except Exception:  # pragma: no cover - optional dependency
        _LOGGER.debug("torch unavailable for GPU detection")

    if _has_cuda_runtime():
        return -1
    return 0


def _has_cuda_runtime() -> bool:
    cuda_paths = [
        Path("C:/Windows/System32"),
        Path("C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v12.8/bin"),
    ]
    for path in cuda_paths:
        if not path.exists():
            continue
        if any(path.glob("cudart64*.dll")):
            if os.name == "nt" and hasattr(os, "add_dll_directory"):
                try:
                    os.add_dll_directory(str(path))
                except OSError:
                    pass
            return True
    return False


def _avx_supported() -> bool:
    try:
        from cpuinfo import get_cpu_info

        info = get_cpu_info()
        flags = info.get("flags") or []
        return "avx" in flags or "avx2" in flags
    except Exception:  # pragma: no cover - optional dependency
        _LOGGER.debug("cpuinfo unavailable for AVX detection")
        return False


def _initialise_llama() -> Llama:
    model_path = _detect_model_path()
    if not model_path.exists():
        _LOGGER.fatal("Required model missing: %s", model_path)
        raise ModelLoadError(f"Model file not found at {model_path}")

    stat = model_path.stat()
    if stat.st_size < 3 * 1024 * 1024 * 1024:
        _LOGGER.fatal(
            "Model file too small (%s bytes) at %s", stat.st_size, model_path
        )
        raise ModelLoadError(
            "Model file appears incomplete; expected at least 3GB of weights"
        )

    if not _avx_supported():
        _LOGGER.warning("AVX not reported; performance may degrade")

    try:
        return Llama(
            model_path=str(model_path),
            n_ctx=_DEFAULT_CONTEXT_LENGTH,
            n_gpu_layers=_detect_gpu_layers(),
            chat_format=_DEFAULT_CHAT_TEMPLATE,
        )
    except Exception as exc:
        _LOGGER.fatal("llama.cpp initialisation failed: %s", exc)
        raise ModelLoadError(f"Local Mistral backend unavailable: {exc}") from exc


def load_model() -> Callable[[List[Dict[str, str]]], str]:
    """Return a callable to send prompts to the configured model."""

    global _PROVIDER, _MODEL_SLUG, _WRAPPER, _LLAMA

    if _WRAPPER is not None:
        return _WRAPPER

    load_dotenv()
    provider = os.getenv("MODEL_PROVIDER", "llama_cpp").strip().lower()
    _PROVIDER = provider

    if provider == "openai":
        if openai is None:
            raise RuntimeError("openai package not available")
        openai.api_key = os.getenv("OPENAI_API_KEY", "")
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        _MODEL_SLUG = f"openai/{model}"

        def _call(msgs: List[Dict[str, str]]) -> str:
            resp = openai.ChatCompletion.create(model=model, messages=msgs)
            return str(resp.choices[0].message.content)

    elif provider == "huggingface":
        import requests

    model = os.getenv("HF_MODEL", "mistralai/Mistral-7B-Instruct-v0.2")
        token = os.getenv("HF_API_TOKEN")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        _MODEL_SLUG = f"huggingface/{model}"

        def _call(msgs: List[Dict[str, str]]) -> str:
            resp = requests.post(
                f"https://api-inference.huggingface.co/models/{model}",
                json={"inputs": msgs[-1]["content"]},
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list) and data:
                data = data[0]
            if isinstance(data, dict) and "generated_text" in data:
                return str(data["generated_text"])
            return json.dumps(data)

    else:
        try:
            _LLAMA = _initialise_llama()
        except Exception as exc:  # pragma: no cover - runtime guard
            _LOGGER.fatal("Failed to load GGUF model: %s", exc)
            raise RuntimeError(f"Local Mistral backend unavailable: {exc}") from exc

        _MODEL_SLUG = _DEFAULT_MODEL_NAME

        def _call(msgs: List[Dict[str, str]]) -> str:
            assert _LLAMA is not None
            response = _LLAMA.create_chat_completion(messages=msgs)
            choice = response.get("choices", [{}])[0]
            message = choice.get("message", {}) if isinstance(choice, dict) else {}
            content = message.get("content", "") if isinstance(message, dict) else ""
            if not isinstance(content, str):
                content = json.dumps(content)
            return content

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
