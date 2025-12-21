"""Bootstrap helpers for preparing the SentientOS runtime environment."""

from __future__ import annotations

import json
import os
import platform
from pathlib import Path
from typing import Dict, Mapping, Optional

try:
    from sentientos.consciousness.integration import run_consciousness_cycle
except Exception:  # pragma: no cover - optional dependency path
    run_consciousness_cycle = None

from sentientos.cathedral.digest import DEFAULT_CATHEDRAL_CONFIG
from sentientos.memory.mounts import ensure_memory_mounts

_CONFIG_FILENAME = "runtime.json"
_BASE_ENV_VAR = "SENTIENTOS_BASE_DIR"
_DEFAULT_MODEL_SUBPATH = Path(
    "sentientos_data/models/mistral-7b/mistral-7b-instruct-v0.2.Q4_K_M.gguf"
)
_DEFAULT_LLAMA_EXECUTABLE = Path("bin/llama_server.exe")


def get_base_dir() -> Path:
    """Return the root directory for SentientOS assets."""

    override = os.getenv(_BASE_ENV_VAR)
    if override:
        return Path(override).expanduser()
    if platform.system().lower() == "windows":
        return Path("C:/SentientOS")
    return Path.home() / "SentientOS"


def ensure_runtime_dirs(base_dir: Optional[Path] = None) -> Dict[str, Path]:
    """Ensure the expected runtime directory structure exists."""

    base_path = Path(base_dir) if base_dir is not None else get_base_dir()
    logs_dir = base_path / "logs"
    data_dir = base_path / "sentientos_data"
    models_dir = data_dir / "models"
    config_dir = data_dir / "config"
    memory_dir = base_path / "memory"

    for directory in (base_path, logs_dir, data_dir, models_dir, config_dir, memory_dir):
        directory.mkdir(parents=True, exist_ok=True)

    ensure_memory_mounts(base_path)

    return {
        "base": base_path,
        "logs": logs_dir,
        "data": data_dir,
        "models": models_dir,
        "config": config_dir,
        "memory": memory_dir,
    }


def optional_consciousness_cycle(system_context: Mapping[str, object]) -> Optional[Dict[str, object]]:
    """Expose the Consciousness Layer integration for opt-in callers."""

    if run_consciousness_cycle is None:
        return None
    if not isinstance(system_context, Mapping):
        return None
    return run_consciousness_cycle(system_context)


def build_default_config(base_dir: Optional[Path] = None) -> Dict[str, object]:
    """Construct a default configuration mapping for SentientOS."""

    base_path = Path(base_dir) if base_dir is not None else get_base_dir()
    data_dir = base_path / "sentientos_data"
    models_dir = data_dir / "models"
    config_dir = data_dir / "config"
    logs_dir = base_path / "logs"

    runtime_defaults: Dict[str, object] = {
        "root": str(base_path),
        "logs_dir": str(logs_dir),
        "data_dir": str(data_dir),
        "models_dir": str(models_dir),
        "config_dir": str(config_dir),
        "llama_server_path": str(base_path / _DEFAULT_LLAMA_EXECUTABLE),
        "model_path": str(base_path / _DEFAULT_MODEL_SUBPATH),
        "relay_host": "127.0.0.1",
        "relay_port": 3928,
        "watchdog_interval": 5,
        "windows_mode": True,
    }

    persona_defaults: Dict[str, object] = {
        "enabled": True,
        "tick_interval_seconds": 60,
        "max_message_length": 200,
    }

    world_defaults: Dict[str, object] = {
        "enabled": True,
        "poll_interval_seconds": 2.0,
        "idle_pulse_interval_seconds": 60,
        "scripted_timeline_enabled": False,
        "scripted_timeline": [],
        "demo_trigger": {
            "enabled": False,
            "demo_name": "demo_simple_success",
            "trigger_after_seconds": 60,
        },
    }

    dashboard_defaults: Dict[str, object] = {
        "enabled": True,
        "refresh_interval_seconds": 2.0,
    }

    voice_defaults: Dict[str, object] = {
        "enabled": False,
        "asr": {
            "whisper_binary_path": str(base_path / "bin" / "whisper.exe"),
            "model_path": str(
                base_path
                / "sentientos_data"
                / "models"
                / "whisper"
                / "base.en.gguf"
            ),
            "language": "en",
            "max_segment_ms": 30000,
        },
        "tts": {
            "enabled": False,
            "rate": 180,
            "volume": 1.0,
            "voice_name": None,
        },
    }

    cathedral_defaults: Dict[str, object] = dict(DEFAULT_CATHEDRAL_CONFIG)

    federation_state_dir = base_path / "federation" / "state"
    federation_defaults: Dict[str, object] = {
        "enabled": False,
        "node_name": "local-node",
        "state_file": str(federation_state_dir / "local-node.json"),
        "poll_interval_seconds": 10,
        "peers": [],
        "indexes": {
            "max_cathedral_ids": 64,
            "max_experiment_ids": 32,
        },
    }

    dream_loop_defaults: Dict[str, object] = {
        "enabled": True,
        "interval_seconds": 60,
        "max_recent_shards": 5,
    }

    return {
        "runtime": runtime_defaults,
        "persona": persona_defaults,
        "world": world_defaults,
        "dashboard": dashboard_defaults,
        "voice": voice_defaults,
        "cathedral": cathedral_defaults,
        "federation": federation_defaults,
        "dream_loop": dream_loop_defaults,
    }


def ensure_default_config(config_dir: Path) -> Path:
    """Ensure a default configuration file exists within *config_dir*."""

    config_directory = Path(config_dir)
    config_directory.mkdir(parents=True, exist_ok=True)
    config_path = config_directory / _CONFIG_FILENAME

    if not config_path.exists():
        if len(config_directory.parents) >= 2:
            base_dir = config_directory.parents[1]
        else:
            base_dir = get_base_dir()
        defaults = build_default_config(base_dir)
        config_path.write_text(json.dumps(defaults, indent=2), encoding="utf-8")

    return config_path


def _resolve_path(value: object, base_dir: Path) -> Optional[Path]:
    if isinstance(value, str) and value:
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = base_dir / candidate
        return candidate
    return None


def validate_model_paths(config: Mapping[str, object], base_dir: Path) -> list[str]:
    """Validate the configured model paths and return warnings when missing."""

    warnings: list[str] = []
    runtime_section = config.get("runtime")
    if not isinstance(runtime_section, Mapping):
        return warnings

    base_path = Path(base_dir)

    model_path = _resolve_path(runtime_section.get("model_path"), base_path)
    if model_path is not None and not model_path.exists():
        warnings.append(
            f"Expected model file not found at {model_path}. "
            "Place the Mistral GGUF in this location before running the demo."
        )

    llama_server_path = _resolve_path(
        runtime_section.get("llama_server_path"), base_path
    )
    if llama_server_path is not None and not llama_server_path.exists():
        warnings.append(
            f"llama.cpp server executable not found at {llama_server_path}. "
            "Update runtime.llama_server_path if the binary lives elsewhere."
        )

    voice_section = config.get("voice")
    if isinstance(voice_section, Mapping):
        asr_section = voice_section.get("asr")
        if isinstance(asr_section, Mapping):
            model_candidate = _resolve_path(asr_section.get("model_path"), base_path)
            if model_candidate is not None and not model_candidate.exists():
                warnings.append(
                    f"Whisper model not found at {model_candidate}. "
                    "Download a GGUF model and update voice.asr.model_path if necessary."
                )
    tts_section = voice_section.get("tts") if isinstance(voice_section, Mapping) else None
    if isinstance(tts_section, Mapping):
        voice_name = tts_section.get("voice_name")
        if voice_name is None:
            warnings.append("TTS voice is unset; offline deployments must configure a local voice_name.")
        if tts_section.get("enabled") and not voice_name:
            warnings.append("TTS enabled without voice_name; disabling or configuring is required.")

    return warnings


__all__ = [
    "build_default_config",
    "ensure_default_config",
    "ensure_runtime_dirs",
    "get_base_dir",
    "validate_model_paths",
]
