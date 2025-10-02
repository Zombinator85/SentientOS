from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .config import GenerationConfig, ModelCandidate, ModelConfig, load_model_config
from .storage import ensure_mounts, get_data_root

LOGGER = logging.getLogger(__name__)

_MODEL_META_NAME = "model.json"

__all__ = ["LocalModel"]


class ModelLoadError(RuntimeError):
    """Raised when a model backend cannot be instantiated."""


class _ModelBackend:
    """Abstract backend interface."""

    engine: str = "unknown"

    def __init__(self, candidate: ModelCandidate, metadata: Dict[str, Any]) -> None:
        self._candidate = candidate
        self._metadata = dict(metadata)
        self._metadata.setdefault("engine", self.engine)

    @property
    def metadata(self) -> Dict[str, Any]:
        return dict(self._metadata)

    def describe(self) -> str:
        location: str
        if self._candidate.path is not None:
            location = str(self._candidate.path)
        else:
            location = "<unspecified>"
        return f"{self.engine} backend ({location})"

    def generate(
        self,
        prompt: str,
        history: Sequence[str],
        generation: Dict[str, Any],
    ) -> str:
        raise NotImplementedError


class _NullBackend(_ModelBackend):
    engine = "null"

    def generate(
        self,
        prompt: str,
        history: Sequence[str],
        generation: Dict[str, Any],
    ) -> str:
        summary = self._metadata.get("name", "SentientOS Placeholder")
        if prompt.strip():
            return (
                f"[{summary}] Received: '{prompt}'. "
                "This placeholder backend is waiting for local weights to be provisioned."
            )
        return f"[{summary}] I am online and ready once a local language model is installed."


class _EchoBackend(_ModelBackend):
    engine = "echo"

    def generate(
        self,
        prompt: str,
        history: Sequence[str],
        generation: Dict[str, Any],
    ) -> str:
        name = self._metadata.get("name", "Echo Model")
        history_text = " | ".join(history)
        if history_text:
            return f"[{name}] {history_text} => {prompt}"
        return f"[{name}] {prompt}"


class _TransformersBackend(_ModelBackend):
    engine = "transformers"

    def __init__(
        self,
        candidate: ModelCandidate,
        metadata: Dict[str, Any],
        generation: GenerationConfig,
        max_context_tokens: int,
    ) -> None:
        super().__init__(candidate, metadata)
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:  # pragma: no cover - import guard
            raise ModelLoadError("transformers is not installed") from exc

        model_location = self._resolve_model_location(candidate)
        if candidate.path is not None and not Path(model_location).exists():
            raise ModelLoadError(f"Model path {model_location} does not exist")

        self._torch = torch
        self._tokenizer = AutoTokenizer.from_pretrained(model_location, trust_remote_code=True, local_files_only=True)
        device_map: Optional[str]
        torch_dtype: Optional[torch.dtype]
        if torch.cuda.is_available():
            device_map = "auto"
            torch_dtype = torch.float16
        else:
            device_map = None
            torch_dtype = torch.float32
        self._model = AutoModelForCausalLM.from_pretrained(
            model_location,
            device_map=device_map,
            torch_dtype=torch_dtype,
            trust_remote_code=True,
            local_files_only=True,
        )
        self._generation = generation
        self._max_context_tokens = max_context_tokens

    def _resolve_model_location(self, candidate: ModelCandidate) -> str:
        model_id = candidate.options.get("model_id")
        if model_id:
            return str(model_id)
        if candidate.path is None:
            raise ModelLoadError("No path provided for transformers backend")
        return str(candidate.path)

    def generate(
        self,
        prompt: str,
        history: Sequence[str],
        generation: Dict[str, Any],
    ) -> str:
        params = self._generation.as_kwargs(**generation)
        tokenizer_inputs = self._tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=self._max_context_tokens,
        )
        tokenizer_inputs = {key: value.to(self._model.device) for key, value in tokenizer_inputs.items()}
        try:
            output = self._model.generate(**tokenizer_inputs, **params)
        except Exception as exc:  # pragma: no cover - runtime safety net
            raise ModelLoadError(f"transformers generation failed: {exc}") from exc
        decoded = self._tokenizer.decode(output[0], skip_special_tokens=True)
        if decoded.startswith(prompt):
            decoded = decoded[len(prompt) :]
        return decoded.strip() or ""


class _LlamaCppBackend(_ModelBackend):
    engine = "llama_cpp"

    def __init__(
        self,
        candidate: ModelCandidate,
        metadata: Dict[str, Any],
        generation: GenerationConfig,
        max_context_tokens: int,
    ) -> None:
        super().__init__(candidate, metadata)
        try:
            from llama_cpp import Llama
        except ImportError as exc:  # pragma: no cover - import guard
            raise ModelLoadError("llama_cpp is not installed") from exc

        if candidate.path is None:
            raise ModelLoadError("No GGUF path provided for llama.cpp backend")
        model_path = candidate.path
        if not model_path.exists():
            raise ModelLoadError(f"Quantized model {model_path} does not exist")

        gpu_layers = candidate.options.get("gpu_layers")
        if gpu_layers is None:
            gpu_layers = -1 if _cuda_available() else 0

        self._llama = Llama(
            model_path=str(model_path),
            n_ctx=max_context_tokens,
            n_gpu_layers=gpu_layers,
            logits_all=False,
        )
        self._generation = generation

    def generate(
        self,
        prompt: str,
        history: Sequence[str],
        generation: Dict[str, Any],
    ) -> str:
        params = self._generation.as_kwargs(**generation)
        response = self._llama(
            prompt,
            max_tokens=params.get("max_new_tokens"),
            temperature=params.get("temperature"),
            top_p=params.get("top_p"),
            top_k=params.get("top_k"),
            repeat_penalty=params.get("repetition_penalty"),
        )
        output = response.get("choices", [{}])[0].get("text", "")
        return str(output).strip()


def _cuda_available() -> bool:
    try:
        import torch
    except ImportError:  # pragma: no cover - optional dependency
        return False
    return bool(torch.cuda.is_available())


@dataclass
class LocalModel:
    """Wrapper around the configured local language model backend."""

    backend: _ModelBackend
    metadata: Dict[str, Any]
    config: ModelConfig
    _fallback_backend: _ModelBackend

    @classmethod
    def autoload(cls) -> "LocalModel":
        ensure_mounts()
        config = load_model_config()
        errors: List[str] = []
        for candidate in config.candidates:
            try:
                backend, metadata = cls._initialise_backend(candidate, config)
            except ModelLoadError as exc:
                errors.append(f"{candidate.display_name()}: {exc}")
                LOGGER.warning("Failed to load model candidate %s: %s", candidate.display_name(), exc)
                continue
            LOGGER.info(
                "Loaded local model '%s' using %s",
                metadata.get("name", candidate.display_name()),
                backend.describe(),
            )
            safe_backend = _NullBackend(candidate, metadata)
            return cls(backend=backend, metadata=backend.metadata, config=config, _fallback_backend=safe_backend)

        placeholder_metadata = {
            "name": "SentientOS Placeholder Model",
            "engine": "null",
            "errors": errors,
        }
        placeholder_dir = get_data_root() / "models"
        placeholder_dir.mkdir(parents=True, exist_ok=True)
        meta_path = placeholder_dir / _MODEL_META_NAME
        if not meta_path.exists():
            try:
                meta_path.write_text("{\"name\": \"placeholder\"}", encoding="utf-8")
            except OSError:
                LOGGER.debug("Unable to write placeholder metadata", exc_info=True)
        backend = _NullBackend(ModelCandidate(path=placeholder_dir, engine="null"), placeholder_metadata)
        LOGGER.warning("Using placeholder language model backend")
        return cls(backend=backend, metadata=backend.metadata, config=config, _fallback_backend=backend)

    @classmethod
    def _initialise_backend(
        cls,
        candidate: ModelCandidate,
        config: ModelConfig,
    ) -> tuple[_ModelBackend, Dict[str, Any]]:
        if candidate.path is not None and not candidate.path.exists():
            raise ModelLoadError(f"Model path {candidate.path} not found")
        metadata = cls._load_metadata(candidate)
        if candidate.name and "name" not in metadata:
            metadata["name"] = candidate.name
        engine = candidate.engine or config.default_engine
        if engine == "auto":
            engine = cls._guess_engine(candidate)
        if engine == "echo":
            backend: _ModelBackend = _EchoBackend(candidate, metadata)
        elif engine == "llama_cpp":
            backend = _LlamaCppBackend(candidate, metadata, config.generation, config.max_context_tokens)
        elif engine == "transformers":
            backend = _TransformersBackend(candidate, metadata, config.generation, config.max_context_tokens)
        else:
            raise ModelLoadError(f"Unknown backend engine '{engine}'")
        metadata.setdefault("engine", engine)
        return backend, backend.metadata

    @classmethod
    def _load_metadata(cls, candidate: ModelCandidate) -> Dict[str, Any]:
        if candidate.path is None:
            return {}
        meta_path = cls._candidate_meta_path(candidate.path)
        if not meta_path.exists():
            return {}
        try:
            import json

            return json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            LOGGER.warning("Failed to read metadata for %s", candidate.display_name(), exc_info=True)
            return {}

    @staticmethod
    def _candidate_meta_path(path: Path) -> Path:
        if path.is_dir():
            return path / _MODEL_META_NAME
        return path.with_suffix(".json")

    @staticmethod
    def _guess_engine(candidate: ModelCandidate) -> str:
        if candidate.path is None:
            return "transformers"
        suffix = candidate.path.suffix.lower()
        if suffix in {".gguf", ".ggml"}:
            return "llama_cpp"
        return "transformers"

    def generate(
        self,
        prompt: Optional[str],
        history: Optional[Iterable[Any]] = None,
        **overrides: Any,
    ) -> str:
        safe_prompt = "" if prompt is None else str(prompt)
        safe_prompt = safe_prompt.strip()
        history_list: List[str] = []
        if isinstance(history, str):
            history_list = [history]
        elif history is not None:
            try:
                for entry in history:
                    if entry is None:
                        continue
                    history_list.append(str(entry).strip())
            except TypeError:
                history_list = [str(history)]
        history_list = [item for item in history_list if item]
        generation_params = dict(overrides)
        if not safe_prompt and not history_list:
            return self._fallback_backend.generate("", history_list, generation_params)

        combined_prompt = "\n".join(history_list + ([safe_prompt] if safe_prompt else []))
        try:
            response = self.backend.generate(combined_prompt, history_list, generation_params)
        except Exception:  # pragma: no cover - runtime guard
            LOGGER.exception("Local model backend crashed; returning fallback response")
            response = self._fallback_backend.generate(combined_prompt, history_list, generation_params)
        if not isinstance(response, str) or not response.strip():
            response = self._fallback_backend.generate(combined_prompt, history_list, generation_params)
        return response

    def describe(self) -> str:
        name = self.metadata.get("name")
        engine = self.metadata.get("engine", getattr(self.backend, "engine", "unknown"))
        if name:
            return f"Local model '{name}' via {engine}"
        return f"Local model via {engine}"
