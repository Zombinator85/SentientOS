from __future__ import annotations

import logging
import os
import hashlib
import json
import ipaddress
import http.client
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, cast

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
    """Raised when a model backend cannot be instantiated or invoked."""

    def __init__(self, message: str, *, diagnostic_code: str | None = None) -> None:
        super().__init__(message)
        self.diagnostic_code = diagnostic_code


def _ollama_server_error_diagnostic(message: str) -> str:
    """Map server text to a bounded code without retaining backend error text."""
    normalized = message.casefold()[:2048]
    if any(marker in normalized for marker in (
            "requires more system memory", "requires more vram",
            "insufficient memory", "not enough memory", "out of memory")):
        return "ollama_server_memory_pressure"
    if any(marker in normalized for marker in (
            "context length", "context size", "input length exceeds",
            "prompt is too long")):
        return "ollama_server_context_limit"
    if "model not found" in normalized or "pull model" in normalized:
        return "ollama_server_model_unavailable"
    if any(marker in normalized for marker in (
            "runner process has terminated", "runner exited", "signal: killed",
            "failed to load model")):
        return "ollama_server_worker_failure"
    if any(marker in normalized for marker in (
            "invalid json schema", "invalid schema", "unsupported format",
            "structured output")):
        return "ollama_server_request_rejected"
    return "ollama_server_other"


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


def _ollama_chat_messages(prompt: str, *, history_format: str = "serialized") -> list[dict[str, str]]:
    """Keep trusted instructions in system role and optionally preserve turn roles."""
    if not isinstance(prompt, str) or not prompt.strip():
        raise ModelLoadError("ollama_prompt_required")
    if (not isinstance(history_format, str)
            or history_format not in {"serialized", "role_separated"}):
        raise ModelLoadError("ollama_chat_history_format_invalid")
    prefix = "[SYSTEM_INSTRUCTION]\n"
    marker = "[SESSION_HISTORY_DATA]"
    if prompt.startswith(prefix):
        head, separator, tail = prompt[len(prefix):].partition(marker)
        if not separator or not head.strip():
            raise ModelLoadError("ollama_chat_instruction_boundary_invalid")
        messages = [{"role": "system", "content": head.strip()}]
        if history_format == "role_separated":
            context_lines: list[str] = []
            history_started = False
            history_closed = False
            end_markers = {
                "[VERIFIED_PRIOR_RUNTIME_LINEAGE_EVIDENCE_DATA]",
                "[RETRIEVED_MEMORY_DATA_UNTRUSTED]",
                "[CURRENT_SCREEN_OBSERVATION_UNTRUSTED]",
                "[CURRENT_USER_MESSAGE]",
            }
            for line in tail.splitlines():
                if line in end_markers:
                    history_closed = True
                    context_lines.append(line)
                    continue
                role: str | None = None
                record_text = ""
                if not history_closed and line.startswith("USER_DATA: "):
                    role, record_text = "user", line[len("USER_DATA: "):]
                elif not history_closed and line.startswith("ASSISTANT_DATA: "):
                    role, record_text = "assistant", line[len("ASSISTANT_DATA: "):]
                if role is None:
                    if history_started and line.strip():
                        history_closed = True
                    context_lines.append(line)
                    continue
                history_started = True
                try:
                    record = json.loads(record_text)
                except (TypeError, ValueError) as exc:
                    raise ModelLoadError("ollama_chat_history_record_invalid") from exc
                if not isinstance(record, dict) or not isinstance(record.get("text"), str):
                    raise ModelLoadError("ollama_chat_history_record_invalid")
                content = record["text"]
                provenance = record.get("provenance")
                if isinstance(provenance, dict) and provenance:
                    content += "\n[Historical turn provenance: " + json.dumps(
                        provenance, ensure_ascii=False, sort_keys=True,
                        separators=(",", ":")) + "]"
                messages.append({"role": role, "content": content})
            current_context = marker + "\n" + "\n".join(context_lines)
            messages.append({"role": "user", "content": current_context.strip()})
        else:
            messages.append({"role": "user", "content": marker + tail})
        return messages
    return [{"role": "user", "content": prompt.strip()}]


class _OllamaBackend(_ModelBackend):
    """Digest-pinned Ollama inference on a numeric loopback endpoint only."""

    engine = "ollama"

    def __init__(self, candidate: ModelCandidate, metadata: Dict[str, Any],
                 max_context_tokens: int) -> None:
        super().__init__(candidate, metadata)
        options = dict(candidate.options)
        allowed = {"api_base", "model", "manifest_sha256", "num_gpu", "keep_alive",
                   "think", "timeout_seconds", "chat_history_format", "seed"}
        if set(options) - allowed:
            raise ModelLoadError("ollama_option_not_allowed")
        seed = options.get("seed")
        if seed is not None and (type(seed) is not int or not 0 <= seed <= 2**31 - 1):
            raise ModelLoadError("ollama_seed_out_of_range")
        self._seed = seed
        if candidate.path is None or not candidate.path.is_file():
            raise ModelLoadError("ollama_local_manifest_required")
        manifest_digest, _ = _stream_sha256(candidate.path)
        expected = str(options.get("manifest_sha256", "")).lower()
        if len(expected) != 64 or manifest_digest != expected:
            raise ModelLoadError("ollama_manifest_digest_mismatch")
        base = str(options.get("api_base", "http://127.0.0.1:11434"))
        parsed = urllib.parse.urlsplit(base)
        try:
            address = ipaddress.ip_address(parsed.hostname or "")
            port = parsed.port
        except ValueError as exc:
            raise ModelLoadError("ollama_loopback_address_required") from exc
        if (parsed.scheme != "http" or not address.is_loopback or parsed.username
                or parsed.password or parsed.path not in {"", "/"} or parsed.query
                or parsed.fragment or port not in {None, 11434}):
            raise ModelLoadError("ollama_loopback_address_required")
        model = options.get("model")
        if not isinstance(model, str) or not model or len(model) > 128:
            raise ModelLoadError("ollama_model_name_required")
        timeout = options.get("timeout_seconds", 60)
        if type(timeout) not in {int, float} or not 1 <= timeout <= 120:
            raise ModelLoadError("ollama_timeout_out_of_range")
        authority = f"[{address}]" if address.version == 6 else str(address)
        self._base = f"http://{authority}:{port or 11434}"
        self._model = model
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self._active_request_lock = threading.Lock()
        self._active_connection: http.client.HTTPConnection | None = None
        self._timeout = float(timeout)
        if type(max_context_tokens) is not int or not 1 <= max_context_tokens <= 8192:
            raise ModelLoadError("ollama_context_limit_out_of_range")
        self._context = max_context_tokens
        self._num_gpu = options.get("num_gpu", 99)
        if type(self._num_gpu) is not int or not 0 <= self._num_gpu <= 128:
            raise ModelLoadError("ollama_gpu_layer_limit_invalid")
        self._keep_alive = options.get("keep_alive", "15m")
        if self._keep_alive not in {"0", "5s", "5m", "15m", "-1"}:
            raise ModelLoadError("ollama_keep_alive_invalid")
        self._think = options.get("think", False)
        if type(self._think) is not bool:
            raise ModelLoadError("ollama_think_must_be_boolean")
        self._chat_history_format = options.get("chat_history_format", "serialized")
        if (not isinstance(self._chat_history_format, str)
                or self._chat_history_format not in {"serialized", "role_separated"}):
            raise ModelLoadError("ollama_chat_history_format_invalid")
        self._metadata.update({"model": model, "api_base": self._base,
                               "manifest_sha256": manifest_digest,
                               "backend_posture": "local_loopback_development",
                               "chat_history_format": self._chat_history_format})

        request = urllib.request.Request(self._base + "/api/tags", method="GET")
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                payload = json.loads(response.read(1024 * 1024).decode("utf-8"))
        except Exception as exc:
            raise ModelLoadError("ollama_local_api_unavailable") from exc
        matches = [entry for entry in payload.get("models", [])
                   if entry.get("name") == model and entry.get("digest") == manifest_digest]
        if len(matches) != 1:
            raise ModelLoadError("ollama_model_digest_unverified")

    def generate(self, prompt: str, history: Sequence[str],
                 generation: Dict[str, Any]) -> str:
        return self.generate_with_metadata(prompt, history, generation)[0]

    def generate_with_metadata(self, prompt: str, history: Sequence[str],
                               generation: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
        on_content_chunk = generation.pop("on_content_chunk", None)
        if on_content_chunk is not None and not callable(on_content_chunk):
            raise ModelLoadError("ollama_content_callback_invalid")
        cancel_event = generation.pop("_cancel_event", None)
        if cancel_event is not None and not isinstance(cancel_event, threading.Event):
            raise ModelLoadError("ollama_cancel_event_invalid")
        keep_alive = generation.get("keep_alive", self._keep_alive)
        if keep_alive not in {"0", "5s", "5m", "15m", "-1"}:
            raise ModelLoadError("ollama_keep_alive_invalid")
        structured_output_schema = generation.pop("structured_output_schema", None)
        if structured_output_schema is not None and not isinstance(structured_output_schema, Mapping):
            raise ModelLoadError("ollama_structured_output_schema_invalid")
        options = {
            "num_ctx": self._context,
            "num_predict": max(1, min(int(generation.get("max_new_tokens", 256)), 512)),
            "num_gpu": self._num_gpu,
            "temperature": max(0.0, min(float(generation.get("temperature", 0.6)), 1.2)),
            "top_p": max(0.1, min(float(generation.get("top_p", 0.9)), 1.0)),
            "repeat_penalty": max(0.8, min(float(generation.get("repetition_penalty") or 1.1), 1.5)),
        }
        if self._seed is not None:
            options["seed"] = self._seed
        messages = _ollama_chat_messages(
            prompt, history_format=self._chat_history_format)
        keep_alive_payload: str | int = -1 if keep_alive == "-1" else keep_alive
        request_body: dict[str, Any] = {
            "model": self._model, "messages": messages, "stream": True,
            "think": self._think, "keep_alive": keep_alive_payload,
            "options": options,
        }
        if structured_output_schema is not None:
            request_body["format"] = dict(structured_output_schema)
        body = json.dumps(request_body, separators=(",", ":")).encode("utf-8")
        parsed = urllib.parse.urlsplit(self._base)
        host = parsed.hostname
        if host is None:
            raise ModelLoadError("ollama_loopback_address_required")
        connection = http.client.HTTPConnection(host, parsed.port,
                                                timeout=self._timeout)
        with self._active_request_lock:
            if self._active_connection is not None:
                raise ModelLoadError("ollama_request_already_active")
            self._active_connection = connection
        if cancel_event is not None and cancel_event.is_set():
            connection.close()
            with self._active_request_lock:
                if self._active_connection is connection:
                    self._active_connection = None
            raise ModelLoadError("ollama_generation_cancelled")
        started_ns = time.monotonic_ns()
        first_token_duration_ns: int | None = None
        content_parts: list[str] = []
        content_size = 0
        payload: dict[str, Any] | None = None
        total_stream_bytes = 0
        try:
            connection.request("POST", "/api/chat", body=body,
                headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            while True:
                raw_line = response.readline(1024 * 1024 + 1)
                if not raw_line:
                    break
                total_stream_bytes += len(raw_line)
                if len(raw_line) > 1024 * 1024 or total_stream_bytes > 4 * 1024 * 1024:
                    raise ModelLoadError("ollama_response_oversized")
                try:
                    chunk = json.loads(raw_line.decode("utf-8"))
                except (UnicodeError, ValueError, TypeError) as exc:
                    raise ModelLoadError("ollama_stream_chunk_invalid") from exc
                if not isinstance(chunk, dict):
                    raise ModelLoadError("ollama_stream_chunk_invalid")
                if isinstance(chunk.get("error"), str):
                    raise ModelLoadError("ollama_local_generation_failed",
                        diagnostic_code=_ollama_server_error_diagnostic(chunk["error"]))
                message = chunk.get("message")
                content = message.get("content") if isinstance(message, dict) else None
                if content is not None:
                    if not isinstance(content, str):
                        raise ModelLoadError("ollama_stream_chunk_invalid")
                    if content:
                        if first_token_duration_ns is None:
                            # Ollama streams content chunks, which may contain more than one
                            # token; this is the governed first-content / TTFT proxy.
                            first_token_duration_ns = max(0, time.monotonic_ns() - started_ns)
                        content_parts.append(content)
                        content_size += len(content)
                        if content_size > 1024 * 1024:
                            raise ModelLoadError("ollama_response_oversized")
                        if on_content_chunk is not None:
                            on_content_chunk(content)
                if chunk.get("done") is True:
                    payload = chunk
                    break
        except ModelLoadError:
            raise
        except Exception as exc:
            raise ModelLoadError("ollama_local_generation_failed") from exc
        finally:
            connection.close()
            with self._active_request_lock:
                if self._active_connection is connection:
                    self._active_connection = None
        answer = "".join(content_parts)
        if payload is None or not answer.strip():
            raise ModelLoadError("ollama_local_generation_invalid")
        def bounded_metric(name: str, maximum: int) -> int | None:
            value = payload.get(name)
            return value if type(value) is int and 0 <= value <= maximum else None
        raw_finish_reason = payload.get("done_reason")
        finish_reason = raw_finish_reason if raw_finish_reason in {"stop", "length"} else "unknown"
        completion = {
            "schema_version": "sentientos.ollama_completion_observation:v2",
            "backend": "ollama", "finish_reason": finish_reason,
            "completion_tokens": bounded_metric("eval_count", 131072),
            "prompt_tokens": bounded_metric("prompt_eval_count", 131072),
            "token_limit_reached": (True if finish_reason == "length" else
                False if finish_reason == "stop" else None),
            "total_duration_ns": bounded_metric("total_duration", 3_600_000_000_000),
            "load_duration_ns": bounded_metric("load_duration", 3_600_000_000_000),
            "prompt_eval_duration_ns": bounded_metric("prompt_eval_duration", 3_600_000_000_000),
            "eval_duration_ns": bounded_metric("eval_duration", 3_600_000_000_000),
            "first_token_duration_ns": first_token_duration_ns,
        }
        return answer.strip(), completion

    def cancel_pending_generation(self) -> bool:
        """Close the active loopback HTTP connection to cancel its Ollama request."""
        with self._active_request_lock:
            connection = self._active_connection
        if connection is None:
            return True
        try:
            if connection.sock is not None:
                connection.sock.shutdown(2)
            connection.close()
            return True
        except OSError:
            try:
                connection.close()
                return True
            except OSError:
                return False

    def is_resident(self) -> bool:
        """Observe whether this exact pinned model is currently loaded by Ollama."""
        request = urllib.request.Request(self._base + "/api/ps", method="GET")
        try:
            with self._opener.open(request, timeout=min(self._timeout, 5.0)) as response:
                raw = response.read(256 * 1024 + 1)
            if len(raw) > 256 * 1024:
                raise ModelLoadError("ollama_process_list_oversized")
            payload = json.loads(raw.decode("utf-8"))
        except ModelLoadError:
            raise
        except Exception as exc:
            raise ModelLoadError("ollama_process_list_unavailable") from exc
        models = payload.get("models")
        if not isinstance(models, list):
            raise ModelLoadError("ollama_process_list_invalid")
        return any(isinstance(entry, dict) and entry.get("name") == self._model
            for entry in models)

    def preload_residency(self, *, keep_alive: str) -> dict[str, Any]:
        """Load this pinned model without generating a token or accepting a prompt."""
        if keep_alive not in {"5s", "5m", "15m", "-1"}:
            raise ModelLoadError("ollama_preload_keep_alive_invalid")
        body = json.dumps({
            "model": self._model,
            "stream": False,
            "keep_alive": -1 if keep_alive == "-1" else keep_alive,
            "options": {"num_ctx": self._context, "num_gpu": self._num_gpu},
        }, separators=(",", ":")).encode("utf-8")
        parsed = urllib.parse.urlsplit(self._base)
        host = parsed.hostname
        if host is None:
            raise ModelLoadError("ollama_loopback_address_required")
        connection = http.client.HTTPConnection(host, parsed.port,
            timeout=min(self._timeout, 60.0))
        with self._active_request_lock:
            if self._active_connection is not None:
                raise ModelLoadError("ollama_request_already_active")
            self._active_connection = connection
        try:
            connection.request("POST", "/api/generate", body=body,
                headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            raw = response.read(64 * 1024 + 1)
            if len(raw) > 64 * 1024:
                raise ModelLoadError("ollama_preload_response_oversized")
            payload = json.loads(raw.decode("utf-8"))
        except ModelLoadError:
            raise
        except Exception as exc:
            raise ModelLoadError("ollama_residency_preload_failed") from exc
        finally:
            connection.close()
            with self._active_request_lock:
                if self._active_connection is connection:
                    self._active_connection = None
        if (not isinstance(payload, dict)
                or payload.get("model") != self._model
                or payload.get("done") is not True
                or payload.get("response", "") != ""
                or payload.get("eval_count", 0) not in {0, None}):
            raise ModelLoadError("ollama_residency_preload_unconfirmed")
        load_duration = payload.get("load_duration")
        if type(load_duration) is not int or not 0 <= load_duration <= 3_600_000_000_000:
            load_duration = None
        return {"backend": "ollama", "model": self._model,
            "result": "load_requested", "keep_alive": keep_alive,
            "load_duration_ns": load_duration, "tokens_generated": 0}

    def release_residency(self) -> dict[str, Any]:
        """Ask the pinned local Ollama model to unload without generating tokens."""
        body = json.dumps({"model": self._model, "prompt": "", "stream": False,
                           "keep_alive": "0"}, separators=(",", ":")).encode("utf-8")
        parsed = urllib.parse.urlsplit(self._base)
        host = parsed.hostname
        if host is None:
            raise ModelLoadError("ollama_loopback_address_required")
        connection = http.client.HTTPConnection(host, parsed.port,
                                                timeout=min(self._timeout, 10.0))
        with self._active_request_lock:
            if self._active_connection is not None:
                raise ModelLoadError("ollama_request_still_active")
            self._active_connection = connection
        try:
            connection.request("POST", "/api/generate", body=body,
                headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            raw = response.read(64 * 1024 + 1)
            if len(raw) > 64 * 1024:
                raise ModelLoadError("ollama_unload_response_oversized")
            payload = json.loads(raw.decode("utf-8"))
        except ModelLoadError:
            raise
        except Exception as exc:
            raise ModelLoadError("ollama_residency_release_failed") from exc
        finally:
            connection.close()
            with self._active_request_lock:
                if self._active_connection is connection:
                    self._active_connection = None
        if (payload.get("done") is not True
                or payload.get("done_reason") not in {"unload", None}
                or payload.get("response", "") != ""):
            raise ModelLoadError("ollama_residency_release_unconfirmed")
        return {"backend": "ollama", "model": self._model,
            "result": "unload_requested", "done_reason": payload.get("done_reason")}


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
            # Production candidates must never acquire an execution posture from
            # an unrelated ambient torch installation.  Legacy callers retain
            # the conservative CPU default and may opt in explicitly.
            gpu_layers = 0

        runtime_options: dict[str, Any] = {}
        if candidate.options.get("n_threads") is not None:
            runtime_options["n_threads"] = int(candidate.options["n_threads"])
        for option in ("n_threads_batch", "n_batch", "n_ubatch"):
            if candidate.options.get(option) is not None:
                runtime_options[option] = int(candidate.options[option])
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
        output, _ = self.generate_with_metadata(prompt, history, generation)
        return output

    def generate_with_metadata(
        self,
        prompt: str,
        history: Sequence[str],
        generation: Dict[str, Any],
    ) -> tuple[str, Dict[str, Any]]:
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
        choice = response.get("choices", [{}])[0] if isinstance(response, dict) else {}
        message = choice.get("message", {}) if isinstance(choice, dict) else {}
        output = message.get("content", "") if isinstance(message, dict) else ""
        finish_reason = choice.get("finish_reason") if isinstance(choice, dict) else None
        finish_reason = finish_reason if finish_reason in {"stop", "length"} else "unknown"
        usage = response.get("usage", {}) if isinstance(response, dict) else {}

        def bounded_count(name: str) -> int | None:
            value = usage.get(name) if isinstance(usage, dict) else None
            return value if type(value) is int and 0 <= value <= 131072 else None

        token_limit_reached = (True if finish_reason == "length" else
            False if finish_reason == "stop" else None)
        metadata = {
            "schema_version": "sentientos.llama_cpp_completion_observation:v1",
            "backend": "llama_cpp",
            "finish_reason": finish_reason,
            "completion_tokens": bounded_count("completion_tokens"),
            "prompt_tokens": bounded_count("prompt_tokens"),
            "token_limit_reached": token_limit_reached,
        }
        return str(output).strip(), metadata


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
    def load_candidate(cls, candidate_index: int, *,
                       config: ModelConfig | None = None) -> "LocalModel":
        """Load exactly one configured model candidate without fallback."""
        ensure_mounts()
        selected_config = config or load_model_config()
        if (type(candidate_index) is not int
                or not 0 <= candidate_index < len(selected_config.candidates)):
            raise ModelLoadError("model_candidate_index_invalid")
        candidate = selected_config.candidates[candidate_index]
        backend, metadata = cls._initialise_backend(candidate, selected_config)
        safe_backend = _NullBackend(candidate, metadata)
        identity = cls._identity_for(candidate, selected_config, backend, metadata,
                                     candidate_index)
        return cls(backend=backend, metadata=backend.metadata,
                   config=selected_config, _fallback_backend=safe_backend,
                   active_identity=identity)

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
            posture=("production" if engine in {"llama_cpp", "transformers"}
                     else "development_only" if engine == "ollama" else "simulation"),
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

    def generate_governed_with_metadata(self, prompt: str, **overrides: Any
            ) -> tuple[str, Dict[str, Any] | None]:
        """Return the backend text and bounded backend-reported completion facts when available."""
        if self.active_identity.fallback:
            raise ModelLoadError("active backend is a simulation or fallback")
        cancel_event = overrides.pop("_cancel_event", None)
        metadata_generator = getattr(self.backend, "generate_with_metadata", None)
        if callable(metadata_generator):
            if self.active_identity.engine == "ollama" and cancel_event is not None:
                overrides["_cancel_event"] = cancel_event
            response, metadata = metadata_generator(str(prompt).strip(), (), dict(overrides))
        else:
            response = self.backend.generate(str(prompt).strip(), (), dict(overrides))
            metadata = None
        if not isinstance(response, str) or not response.strip():
            raise ModelLoadError("active backend returned an empty response")
        return response, metadata

    def cancel_pending_generation(self) -> bool:
        """Delegate cancellation to a backend that supports terminating active work."""
        cancel = getattr(self.backend, "cancel_pending_generation", None)
        return bool(cancel()) if callable(cancel) else False

    def release_residency(self) -> dict[str, Any]:
        """Release backend memory; callers must first obtain governed admission."""
        release = getattr(self.backend, "release_residency", None)
        if not callable(release):
            raise ModelLoadError("model_residency_release_unavailable")
        return dict(release())

    def preload_residency(self, *, keep_alive: str) -> dict[str, Any]:
        """Load backend memory without generation; callers must obtain admission."""
        preload = getattr(self.backend, "preload_residency", None)
        if not callable(preload):
            raise ModelLoadError("model_residency_preload_unavailable")
        return dict(preload(keep_alive=keep_alive))

    def is_resident(self) -> bool:
        """Return exact-backend residency evidence when the engine exposes it."""
        observer = getattr(self.backend, "is_resident", None)
        if not callable(observer):
            raise ModelLoadError("model_residency_observation_unavailable")
        return bool(observer())

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
        elif engine == "ollama":
            backend = _OllamaBackend(candidate, metadata, config.max_context_tokens)
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
