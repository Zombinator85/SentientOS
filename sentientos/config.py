from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .storage import get_data_root

LOGGER = logging.getLogger(__name__)

_MODEL_CONFIG_ENV = "SENTIENTOS_MODEL_CONFIG"
_MODEL_PATH_ENV = "SENTIENTOS_MODEL_PATH"
_MODEL_FALLBACKS_ENV = "SENTIENTOS_MODEL_FALLBACKS"
_MODEL_ENGINE_ENV = "SENTIENTOS_MODEL_ENGINE"
_MODEL_CTX_ENV = "SENTIENTOS_MODEL_CTX"
_MODEL_MAX_NEW_TOKENS_ENV = "SENTIENTOS_MODEL_MAX_NEW_TOKENS"
_MODEL_TEMPERATURE_ENV = "SENTIENTOS_MODEL_TEMPERATURE"
_MODEL_TOP_P_ENV = "SENTIENTOS_MODEL_TOP_P"
_MODEL_TOP_K_ENV = "SENTIENTOS_MODEL_TOP_K"
_MODEL_REPETITION_ENV = "SENTIENTOS_MODEL_REPETITION_PENALTY"


@dataclass
class GenerationConfig:
    """Default sampling parameters for local generation."""

    max_new_tokens: int = 512
    temperature: float = 0.7
    top_p: float = 0.95
    top_k: Optional[int] = None
    repetition_penalty: Optional[float] = None

    def as_kwargs(self, **overrides: Any) -> Dict[str, Any]:
        """Return a merged dictionary of sampling parameters."""

        params: Dict[str, Any] = {
            "max_new_tokens": self.max_new_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "repetition_penalty": self.repetition_penalty,
        }
        for key, value in overrides.items():
            if value is None:
                continue
            params[key] = value
        return params


@dataclass
class ModelCandidate:
    """A concrete local model candidate that can be loaded."""

    path: Optional[Path]
    engine: str = "auto"
    name: Optional[str] = None
    options: Dict[str, Any] = field(default_factory=dict)

    def display_name(self) -> str:
        if self.name:
            return self.name
        if self.path is not None:
            return str(self.path)
        return self.engine


@dataclass
class ModelConfig:
    """Runtime configuration describing available local language models."""

    candidates: List[ModelCandidate]
    default_engine: str = "auto"
    max_context_tokens: int = 4096
    generation: GenerationConfig = field(default_factory=GenerationConfig)


def load_model_config() -> ModelConfig:
    """Load the runtime model configuration from disk or environment."""

    config_path = os.environ.get(_MODEL_CONFIG_ENV)
    data_root = get_data_root()
    if config_path:
        config_file = Path(config_path)
        if config_file.exists():
            try:
                raw = json.loads(config_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                LOGGER.warning("Invalid model configuration file %s: %s", config_file, exc)
            else:
                return _parse_config_mapping(raw, data_root)
        else:
            LOGGER.warning("Model configuration file %s does not exist", config_file)
    return _default_config(data_root)


def _parse_config_mapping(mapping: Dict[str, Any], data_root: Path) -> ModelConfig:
    candidates = [
        _parse_candidate(candidate, data_root)
        for candidate in mapping.get("candidates", [])
        if isinstance(candidate, dict)
    ]
    if not candidates:
        candidates = _default_candidates(data_root)

    default_engine = str(mapping.get("default_engine", "auto"))
    max_context_tokens = int(mapping.get("max_context_tokens", 4096))
    generation = _parse_generation(mapping.get("generation", {}))

    return ModelConfig(
        candidates=candidates,
        default_engine=default_engine,
        max_context_tokens=max_context_tokens,
        generation=generation,
    )


def _parse_candidate(candidate: Dict[str, Any], data_root: Path) -> ModelCandidate:
    path_value = candidate.get("path")
    path: Optional[Path]
    if path_value is None:
        path = None
    else:
        resolved = Path(path_value)
        if not resolved.is_absolute():
            resolved = data_root / resolved
        path = resolved
    engine = str(candidate.get("engine", "auto"))
    name = candidate.get("name")
    options = candidate.get("options")
    if not isinstance(options, dict):
        options = {}
    return ModelCandidate(path=path, engine=engine, name=name, options=options)


def _parse_generation(mapping: Dict[str, Any]) -> GenerationConfig:
    generation = GenerationConfig()
    if "max_new_tokens" in mapping:
        generation.max_new_tokens = int(mapping["max_new_tokens"])
    if "temperature" in mapping:
        generation.temperature = float(mapping["temperature"])
    if "top_p" in mapping:
        generation.top_p = float(mapping["top_p"])
    if "top_k" in mapping:
        value = mapping["top_k"]
        generation.top_k = None if value is None else int(value)
    if "repetition_penalty" in mapping:
        value = mapping["repetition_penalty"]
        generation.repetition_penalty = None if value is None else float(value)
    return generation


def _default_config(data_root: Path) -> ModelConfig:
    candidates = _default_candidates(data_root)
    default_engine = os.environ.get(_MODEL_ENGINE_ENV, "auto")
    max_context_tokens = _env_int(_MODEL_CTX_ENV, 4096)
    generation = GenerationConfig(
        max_new_tokens=_env_int(_MODEL_MAX_NEW_TOKENS_ENV, 512),
        temperature=_env_float(_MODEL_TEMPERATURE_ENV, 0.7),
        top_p=_env_float(_MODEL_TOP_P_ENV, 0.95),
        top_k=_env_optional_int(_MODEL_TOP_K_ENV),
        repetition_penalty=_env_optional_float(_MODEL_REPETITION_ENV),
    )
    return ModelConfig(
        candidates=candidates,
        default_engine=default_engine,
        max_context_tokens=max_context_tokens,
        generation=generation,
    )


def _default_candidates(data_root: Path) -> List[ModelCandidate]:
    candidates: List[ModelCandidate] = []
    default_path = os.environ.get(_MODEL_PATH_ENV) or os.environ.get("LOCAL_MODEL_PATH")
    if default_path:
        base_path = Path(default_path)
        if not base_path.is_absolute():
            base_path = data_root / base_path
    else:
        base_path = (
            data_root
            / "models"
            / "mixtral-8x7b"
            / "mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf"
        )
    candidates.append(
        ModelCandidate(
            path=base_path,
            engine=os.environ.get(_MODEL_ENGINE_ENV, "auto"),
            name="Mixtral-8x7B Instruct (GGUF)",
        )
    )

    fallback_env = os.environ.get(_MODEL_FALLBACKS_ENV)
    if fallback_env:
        for entry in fallback_env.split(os.pathsep):
            entry = entry.strip()
            if not entry:
                continue
            fallback_path = Path(entry)
            if not fallback_path.is_absolute():
                fallback_path = data_root / fallback_path
            candidates.append(
                ModelCandidate(
                    path=fallback_path,
                    engine="auto",
                )
            )

    default_fallback = data_root / "models" / "gpt-oss-13b"
    if all(candidate.path != default_fallback for candidate in candidates):
        candidates.append(ModelCandidate(path=default_fallback, engine="auto", name="gpt-oss-13b"))
    # Legacy GPT-OSS 120B builds require extreme hardware and must be configured manually.
    return candidates


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        LOGGER.warning("Invalid integer for %s: %s", name, value)
        return default


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        LOGGER.warning("Invalid float for %s: %s", name, value)
        return default


def _env_optional_int(name: str) -> Optional[int]:
    value = os.environ.get(name)
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        LOGGER.warning("Invalid integer for %s: %s", name, value)
        return None


def _env_optional_float(name: str) -> Optional[float]:
    value = os.environ.get(name)
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        LOGGER.warning("Invalid float for %s: %s", name, value)
        return None
