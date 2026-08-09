from __future__ import annotations

import logging
import os
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, cast

from .config import GenerationConfig, ModelCandidate, ModelConfig, load_model_config
from .optional_deps import dependency_available, optional_import
from .storage import ensure_mounts, get_data_root

LOGGER = logging.getLogger(__name__)

_MODEL_META_NAME = "model.json"
_ALLOW_MODEL_CODE_EXEC_ENV = "SENTIENTOS_ALLOW_MODEL_CODE_EXECUTION"


__all__ = ["ActiveModelIdentity", "LocalModel"]


def _canonical_digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def _stream_sha256(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return digest.hexdigest(), size


@dataclass(frozen=True)
class ActiveModelIdentity:
    """Read-only identity of the backend which was actually instantiated."""

    engine: str
    resolved_artifact_path: str | None
    semantic_artifact_identity: str
    model_content_sha256: str | None
    artifact_size_bytes: int | None
    sidecar_metadata_digest: str | None
    configuration_digest: str
    candidate_index: int | None
    posture: str
    fallback: bool

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def candidate_configuration_digest(candidate: ModelCandidate, config: ModelConfig, engine: str) -> str:
    payload = {
        "engine": engine.lower(),
        "options": {key: value for key, value in sorted(candidate.options.items()) if key != "path"},
        "max_context_tokens": config.max_context_tokens,
        "generation": config.generation.as_kwargs(),
    }
    return _canonical_digest(payload)


def candidate_artifact_identity(candidate: ModelCandidate, metadata: Dict[str, Any]) -> tuple[str | None, str, str | None, int | None, str | None]:
    if candidate.path is None:
        return None, "pathless_model", None, None, None
    resolved = candidate.path.resolve(strict=False)
    content_digest: str | None = None
    size: int | None = None
    if candidate.path.is_file():
        content_digest, size = _stream_sha256(candidate.path)
    elif candidate.path.is_dir():
        size = 0
        content_digest = _canonical_digest({"directory_model": metadata, "name": candidate.display_name()})
    meta_path = LocalModel._candidate_meta_path(candidate.path)
    sidecar_digest = hashlib.sha256(meta_path.read_bytes()).hexdigest() if meta_path.is_file() else None
    semantic = f"sha256:{content_digest}" if content_digest else f"unverified:{candidate.display_name()}"
    return str(resolved), semantic, content_digest, size, sidecar_digest


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
        torch = optional_import("torch", feature="local_model_transformers")
        transformers = optional_import("transformers", feature="local_model_transformers")
        if torch is None or transformers is None:
            raise ModelLoadError("transformers is not installed")

        AutoModelForCausalLM = transformers.AutoModelForCausalLM
        AutoTokenizer = transformers.AutoTokenizer

        model_location = self._resolve_model_location(candidate)
        if candidate.path is not None and not Path(model_location).exists():
            raise ModelLoadError(f"Model path {model_location} does not exist")

        self._torch = torch
        trust_remote_code = _allow_model_code_execution(candidate, metadata)
        try:
            self._tokenizer = AutoTokenizer.from_pretrained(
                model_location,
                trust_remote_code=trust_remote_code,
                local_files_only=True,
            )
        except Exception as exc:
            raise _model_load_error_for_transformers_exception(
                exc,
                trust_remote_code=trust_remote_code,
                phase="tokenizer",
            ) from exc
        device_map: Optional[str]
        torch_dtype: Any
        if torch.cuda.is_available():
            device_map = "auto"
            torch_dtype = torch.float16
        else:
            device_map = None
            torch_dtype = torch.float32
        try:
            self._model = AutoModelForCausalLM.from_pretrained(
                model_location,
                device_map=device_map,
                torch_dtype=torch_dtype,
                trust_remote_code=trust_remote_code,
                local_files_only=True,
            )
        except Exception as exc:
            raise _model_load_error_for_transformers_exception(
                exc,
                trust_remote_code=trust_remote_code,
                phase="model",
            ) from exc
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
        generation.pop("structured_output_schema", None)
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


def _model_load_error_for_transformers_exception(
    exc: Exception,
    *,
    trust_remote_code: bool,
    phase: str,
) -> ModelLoadError:
    message = str(exc) or exc.__class__.__name__
    if not trust_remote_code and _requires_custom_model_code(message):
        return ModelLoadError(
            "transformers model requires custom code but explicit opt-in is absent; "
            "refusing to enable trust_remote_code=True. "
            f"Set {_ALLOW_MODEL_CODE_EXEC_ENV}=1 only for audited local weights. "
            f"Original {phase} loader error: {message}"
        )
    return ModelLoadError(f"transformers {phase} loader failed: {message}")


def _requires_custom_model_code(message: str) -> bool:
    normalized = message.lower().replace("-", "_")
    return (
        "trust_remote_code" in normalized
        or "custom code" in normalized
        or "remote code" in normalized
    )


def _allow_model_code_execution(candidate: ModelCandidate, metadata: Dict[str, Any]) -> bool:
    allow_env = os.getenv(_ALLOW_MODEL_CODE_EXEC_ENV, "").strip().lower() in {"1", "true", "yes", "on"}
    allow_option = bool(candidate.options.get("allow_model_code_execution"))
    allow_metadata = bool(metadata.get("allow_model_code_execution"))
    allow = allow_env or allow_option or allow_metadata
    if allow:
        manifest_hash = _candidate_manifest_hash(candidate)
        if manifest_hash is not None:
            LOGGER.warning(
                "Model code execution enabled for %s with manifest hash %s",
                candidate.display_name(),
                manifest_hash,
            )
        else:
            LOGGER.warning(
                "Model code execution enabled for %s without escrow manifest hash",
                candidate.display_name(),
            )
        return True
    return False


def _candidate_manifest_hash(candidate: ModelCandidate) -> Optional[str]:
    if candidate.path is None:
        return None
    manifest_path = LocalModel._candidate_meta_path(candidate.path)
    if not manifest_path.exists():
        return None
    try:
        payload = manifest_path.read_bytes()
    except OSError:
        return None
    return hashlib.sha256(payload).hexdigest()


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
        llama_module = optional_import("llama-cpp-python", feature="local_model_llama_cpp")
        if llama_module is None:
            raise ModelLoadError("llama_cpp is not installed")
        Llama = llama_module.Llama

        if candidate.path is None:
            raise ModelLoadError("No GGUF path provided for llama.cpp backend")
        model_path = candidate.path
        if not model_path.exists():
            raise ModelLoadError(f"Quantized model {model_path} does not exist")

        gpu_layers = candidate.options.get("gpu_layers")
        if gpu_layers is None:
            gpu_layers = -1 if _cuda_available() else 0

        runtime_options: dict[str, Any] = {}
        if candidate.options.get("n_threads") is not None:
            runtime_options["n_threads"] = int(candidate.options["n_threads"])
        self._llama = Llama(
            model_path=str(model_path),
            n_ctx=max_context_tokens,
            n_gpu_layers=gpu_layers,
            logits_all=False,
            **runtime_options,
        )
        self._generation = generation

    def generate(
        self,
        prompt: str,
        history: Sequence[str],
        generation: Dict[str, Any],
    ) -> str:
        structured_output_schema = generation.pop("structured_output_schema", None)
        params = self._generation.as_kwargs(**generation)
        completion_params: dict[str, Any] = {
            "max_tokens": params.get("max_new_tokens"),
            "temperature": params.get("temperature"),
            "top_p": params.get("top_p"),
        }
        if params.get("top_k") is not None:
            completion_params["top_k"] = params["top_k"]
        if params.get("repetition_penalty") is not None:
            completion_params["repeat_penalty"] = params["repetition_penalty"]
        if structured_output_schema is not None:
            completion_params["response_format"] = {
                "type": "json_object", "schema": structured_output_schema,
            }
        response = self._llama.create_chat_completion(
            messages=[{"role": "user", "content": prompt}], **completion_params,
        )
        output = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        return str(output).strip()


def _cuda_available() -> bool:
    if not dependency_available("torch"):
        return False
    torch = optional_import("torch", feature="local_model_cuda")
    if torch is None:
        return False
    return bool(torch.cuda.is_available())


@dataclass
class LocalModel:
    """Wrapper around the configured local language model backend."""

    backend: _ModelBackend
    metadata: Dict[str, Any]
    config: ModelConfig
    _fallback_backend: _ModelBackend
    active_identity: ActiveModelIdentity

    @classmethod
    def autoload(cls) -> "LocalModel":
        if os.getenv("SENTIENTOS_NODE_ONLY") == "1":
            ensure_mounts()
            config = load_model_config()
            placeholder_metadata = {
                "name": "SentientOS Node Placeholder",
                "engine": "null",
                "mode": "node_only",
            }
            placeholder_dir = get_data_root() / "models"
            placeholder_dir.mkdir(parents=True, exist_ok=True)
            backend: _ModelBackend = _NullBackend(ModelCandidate(path=placeholder_dir, engine="null"), placeholder_metadata)
            LOGGER.info("Node-only mode active; skipped heavy local model load.")
            identity = cls._fallback_identity(backend, config, posture="node_only")
            return cls(backend=backend, metadata=backend.metadata, config=config, _fallback_backend=backend, active_identity=identity)
        ensure_mounts()
        config = load_model_config()
        errors: List[str] = []
        for candidate_index, candidate in enumerate(config.candidates):
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
            identity = cls._identity_for(candidate, config, backend, metadata, candidate_index)
            return cls(backend=backend, metadata=backend.metadata, config=config, _fallback_backend=safe_backend, active_identity=identity)

        fallback_metadata: Dict[str, Any] = {
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
        backend = _NullBackend(ModelCandidate(path=placeholder_dir, engine="null"), fallback_metadata)
        LOGGER.warning("Using placeholder language model backend")
        identity = cls._fallback_identity(backend, config, posture="null_fallback")
        return cls(backend=backend, metadata=backend.metadata, config=config, _fallback_backend=backend, active_identity=identity)

    @classmethod
    def _identity_for(cls, candidate: ModelCandidate, config: ModelConfig, backend: _ModelBackend,
                      metadata: Dict[str, Any], candidate_index: int) -> ActiveModelIdentity:
        engine = backend.engine.lower()
        resolved, semantic, content, size, sidecar = candidate_artifact_identity(candidate, metadata)
        return ActiveModelIdentity(
            engine=engine, resolved_artifact_path=resolved, semantic_artifact_identity=semantic,
            model_content_sha256=content, artifact_size_bytes=size, sidecar_metadata_digest=sidecar,
            configuration_digest=candidate_configuration_digest(candidate, config, engine),
            candidate_index=candidate_index,
            posture="production" if engine in {"llama_cpp", "transformers"} else "simulation",
            fallback=engine in {"null", "echo"},
        )

    @classmethod
    def _fallback_identity(cls, backend: _ModelBackend, config: ModelConfig, *, posture: str) -> ActiveModelIdentity:
        candidate = backend._candidate
        resolved, semantic, content, size, sidecar = candidate_artifact_identity(candidate, backend.metadata)
        return ActiveModelIdentity(
            engine=backend.engine, resolved_artifact_path=resolved, semantic_artifact_identity=semantic,
            model_content_sha256=content, artifact_size_bytes=size, sidecar_metadata_digest=sidecar,
            configuration_digest=candidate_configuration_digest(candidate, config, backend.engine),
            candidate_index=None, posture=posture, fallback=True,
        )

    def generate_governed(self, prompt: str, **overrides: Any) -> str:
        """Generate without the conversational fallback used by ``generate``."""
        if self.active_identity.fallback:
            raise ModelLoadError("active backend is a simulation or fallback")
        response = self.backend.generate(str(prompt).strip(), (), dict(overrides))
        if not isinstance(response, str) or not response.strip():
            raise ModelLoadError("active backend returned an empty response")
        return response

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
            return cast(Dict[str, Any], json.loads(meta_path.read_text(encoding="utf-8")))
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
