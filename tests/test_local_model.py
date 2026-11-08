from __future__ import annotations

import hashlib
import json
import sys
import types
from pathlib import Path

import pytest

from sentientos.local_model import (
    LocalModel, ModelLoadError, _OllamaBackend, _ollama_chat_messages,
)
from sentientos.config import GenerationConfig, ModelCandidate, ModelConfig


def _write_config(tmp_path: Path, data: dict) -> Path:
    config_path = tmp_path / "model_config.json"
    config_path.write_text(json.dumps(data), encoding="utf-8")
    return config_path


def _prepare_candidate(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    path.mkdir(parents=True, exist_ok=True)
    (path / "model.json").write_text(json.dumps({"description": name}), encoding="utf-8")
    return path


def test_ollama_history_can_be_supplied_as_native_roles_without_losing_context() -> None:
    prompt = (
        "[SYSTEM_INSTRUCTION]\nTrusted rules.\n"
        "[VERIFIED_RUNTIME_CONTEXT]\n{\"workload\":\"gaming\"}\n"
        "[SESSION_HISTORY_DATA]\n"
        "USER_DATA: {\"text\":\"I got a real companion reply.\"}\n"
        "ASSISTANT_DATA: {\"text\":\"That proves one successful turn.\","
        "\"provenance\":{\"model_identity\":\"sha256:abc\"}}\n"
        "[RETRIEVED_MEMORY_DATA_UNTRUSTED]\nMEMORY_DATA: \"old note\"\n"
        "[CURRENT_USER_MESSAGE]\nWhat did I say happened?"
    )

    serialized = _ollama_chat_messages(prompt)
    native = _ollama_chat_messages(prompt, history_format="role_separated")

    assert [message["role"] for message in serialized] == ["system", "user"]
    assert [message["role"] for message in native] == [
        "system", "user", "assistant", "user"]
    assert native[0]["content"].startswith("Trusted rules.")
    assert "[VERIFIED_RUNTIME_CONTEXT]" in native[0]["content"]
    assert native[1]["content"] == "I got a real companion reply."
    assert "Historical turn provenance" in native[2]["content"]
    assert "MEMORY_DATA: \"old note\"" in native[-1]["content"]
    assert native[-1]["content"].endswith("What did I say happened?")


def test_ollama_native_history_rejects_malformed_serialized_turns() -> None:
    prompt = (
        "[SYSTEM_INSTRUCTION]\nTrusted rules.\n"
        "[VERIFIED_RUNTIME_CONTEXT]\n{}\n[SESSION_HISTORY_DATA]\n"
        "USER_DATA: not-json\n[CURRENT_USER_MESSAGE]\nHello"
    )

    with pytest.raises(ModelLoadError, match="ollama_chat_history_record_invalid"):
        _ollama_chat_messages(prompt, history_format="role_separated")


def test_ollama_role_separation_does_not_treat_current_user_text_as_history() -> None:
    prompt = (
        "[SYSTEM_INSTRUCTION]\nTrusted rules.\n[SESSION_HISTORY_DATA]\n"
        "USER_DATA: {\"text\":\"Prior turn\"}\n[CURRENT_USER_MESSAGE]\n"
        "USER_DATA: {\"text\":\"This is literal user text\"}"
    )

    messages = _ollama_chat_messages(prompt, history_format="role_separated")

    assert [message["role"] for message in messages] == ["system", "user", "user"]
    assert messages[-1]["content"].endswith(
        'USER_DATA: {"text":"This is literal user text"}')


def test_ollama_backend_records_configured_history_format(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import hashlib

    manifest = tmp_path / "model.manifest"
    manifest.write_bytes(b"local-pinned-model")
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()

    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return None
        def read(self, _limit):
            return json.dumps({"models": [{"name": "local:test", "digest": digest}]}).encode()

    class Opener:
        def open(self, _request, *, timeout):
            assert timeout > 0
            return Response()

    monkeypatch.setattr(
        "sentientos.local_model.urllib.request.build_opener",
        lambda _handler: Opener())
    candidate = ModelCandidate(manifest, "ollama", "local-test", {
        "api_base": "http://127.0.0.1:11434", "model": "local:test",
        "manifest_sha256": digest, "chat_history_format": "role_separated",
    })

    backend = _OllamaBackend(candidate, {}, max_context_tokens=1024)

    assert backend.metadata["chat_history_format"] == "role_separated"


def test_local_model_smoke(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    primary_dir = _prepare_candidate(tmp_path, "primary")
    config = {
        "candidates": [
            {
                "path": str(primary_dir),
                "engine": "echo",
                "name": "Echo Primary",
            }
        ]
    }
    config_path = _write_config(tmp_path, config)
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(data_root))
    monkeypatch.setenv("SENTIENTOS_MODEL_CONFIG", str(config_path))

    model = LocalModel.autoload()

    description = model.describe()
    assert "Echo Primary" in description


def test_local_model_inference(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    primary_dir = _prepare_candidate(tmp_path, "primary")
    config = {
        "generation": {"temperature": 0.5, "max_new_tokens": 32},
        "candidates": [
            {
                "path": str(primary_dir),
                "engine": "echo",
                "name": "Echo Primary",
            }
        ],
    }
    config_path = _write_config(tmp_path, config)
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(data_root))
    monkeypatch.setenv("SENTIENTOS_MODEL_CONFIG", str(config_path))

    model = LocalModel.autoload()

    response = model.generate("Hello world", history=["previous message"])
    assert isinstance(response, str)
    assert response


def test_local_model_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    fallback_dir = _prepare_candidate(tmp_path, "fallback")
    config = {
        "candidates": [
            {
                "path": str(tmp_path / "missing"),
                "engine": "echo",
                "name": "Missing Primary",
            },
            {
                "path": str(fallback_dir),
                "engine": "echo",
                "name": "Echo Fallback",
            },
        ]
    }
    config_path = _write_config(tmp_path, config)
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(data_root))
    monkeypatch.setenv("SENTIENTOS_MODEL_CONFIG", str(config_path))

    model = LocalModel.autoload()

    assert model.metadata.get("name") == "Echo Fallback"


def test_local_model_generate_resilient(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    primary_dir = _prepare_candidate(tmp_path, "primary")
    config = {
        "candidates": [
            {
                "path": str(primary_dir),
                "engine": "echo",
                "name": "Echo Primary",
            }
        ]
    }
    config_path = _write_config(tmp_path, config)
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(data_root))
    monkeypatch.setenv("SENTIENTOS_MODEL_CONFIG", str(config_path))

    model = LocalModel.autoload()

    response_empty = model.generate(None, history=None)
    assert isinstance(response_empty, str)
    assert response_empty

    response_malformed = model.generate("", history=["", None, 42])
    assert isinstance(response_malformed, str)
    assert response_malformed


def test_local_model_gguf_mistral_backend(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(data_root))
    monkeypatch.delenv("SENTIENTOS_MODEL_CONFIG", raising=False)
    monkeypatch.delenv("SENTIENTOS_MODEL_PATH", raising=False)
    monkeypatch.delenv("LOCAL_MODEL_PATH", raising=False)

    mistral_path = (
        data_root
        / "models"
        / "mistral-7b"
        / "mistral-7b-instruct-v0.2.Q4_K_M.gguf"
    )
    mistral_path.parent.mkdir(parents=True, exist_ok=True)
    mistral_path.write_bytes(b"gguf")

    calls: list[dict[str, object]] = []

    class DummyLlama:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def create_chat_completion(self, *, messages: list[dict[str, str]], **kwargs: object) -> dict:
            calls.append(kwargs)
            return {"choices": [{"message": {"content": f"Mistral echoes: {messages[0]['content']}"},
                "finish_reason": "length"}],
                "usage": {"completion_tokens": 8, "prompt_tokens": 5}}

    monkeypatch.setitem(sys.modules, "llama_cpp", types.SimpleNamespace(Llama=DummyLlama))
    model = LocalModel.autoload()

    assert "Mistral" in model.metadata.get("name", "")
    response = model.generate("Hello cathedral")
    assert "Mistral echoes" in response
    assert "response_format" not in calls[-1]

    schema = {"type": "object", "properties": {"answer": {"type": "string"}},
              "required": ["answer"], "additionalProperties": False}
    model.generate_governed("structured", structured_output_schema=schema)
    assert calls[-1]["response_format"] == {"type": "json_object", "schema": schema}
    _, completion = model.generate_governed_with_metadata("metadata", max_new_tokens=8)
    assert completion == {"schema_version": "sentientos.llama_cpp_completion_observation:v1",
        "backend": "llama_cpp", "finish_reason": "length", "completion_tokens": 8,
        "prompt_tokens": 5, "token_limit_reached": True}


def test_llama_cpp_passes_complete_resource_profile_to_constructor(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    artifact = tmp_path / "profile.gguf"
    artifact.write_bytes(b"GGUF-profile")
    captured: dict[str, object] = {}

    class DummyLlama:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    monkeypatch.setitem(sys.modules, "llama_cpp", types.SimpleNamespace(Llama=DummyLlama))
    monkeypatch.setattr("sentientos.local_model.optional_import",
        lambda package, *, feature: sys.modules["llama_cpp"])
    candidate = ModelCandidate(artifact, "llama_cpp", "profile-model", {
        "gpu_layers": 0, "n_threads": 4, "n_threads_batch": 2,
        "n_batch": 128, "n_ubatch": 64,
    })
    config = ModelConfig([candidate], default_engine="llama_cpp", max_context_tokens=512,
        generation=GenerationConfig(max_new_tokens=8))

    backend, _ = LocalModel._initialise_backend(candidate, config)

    assert captured == {
        "model_path": str(artifact), "n_ctx": 512, "n_gpu_layers": 0,
        "n_threads": 4, "n_threads_batch": 2, "n_batch": 128,
        "n_ubatch": 64, "logits_all": False,
    }
    assert backend.engine == "llama_cpp"


def test_transformers_backend_defaults_trust_remote_code_false(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    model_dir = _prepare_candidate(tmp_path, "hf-local")
    config = {"candidates": [{"path": str(model_dir), "engine": "transformers", "name": "HF"}]}
    config_path = _write_config(tmp_path, config)
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(data_root))
    monkeypatch.setenv("SENTIENTOS_MODEL_CONFIG", str(config_path))
    monkeypatch.delenv("SENTIENTOS_ALLOW_MODEL_CODE_EXECUTION", raising=False)

    calls: dict[str, object] = {}

    class DummyTorch:
        float16 = object()
        float32 = object()
        class cuda:
            @staticmethod
            def is_available() -> bool:
                return False

    class DummyTokenizer:
        @classmethod
        def from_pretrained(cls, model_location: str, **kwargs: object):
            calls["tokenizer"] = kwargs
            return cls()

    class DummyModel:
        device = "cpu"

        @classmethod
        def from_pretrained(cls, model_location: str, **kwargs: object):
            calls["model"] = kwargs
            return cls()

        def generate(self, **kwargs: object):
            return [[1]]

    class DummyTransformers:
        AutoTokenizer = DummyTokenizer
        AutoModelForCausalLM = DummyModel

    monkeypatch.setattr("sentientos.local_model.optional_import", lambda name, feature=None: DummyTorch if name == "torch" else DummyTransformers)

    LocalModel.autoload()

    assert calls["tokenizer"]["trust_remote_code"] is False
    assert calls["model"]["trust_remote_code"] is False
    assert calls["tokenizer"]["local_files_only"] is True
    assert calls["model"]["local_files_only"] is True


def test_transformers_backend_opt_in_enables_trust_remote_code(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    model_dir = _prepare_candidate(tmp_path, "hf-local")
    config = {"candidates": [{"path": str(model_dir), "engine": "transformers", "name": "HF"}]}
    config_path = _write_config(tmp_path, config)
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(data_root))
    monkeypatch.setenv("SENTIENTOS_MODEL_CONFIG", str(config_path))
    monkeypatch.setenv("SENTIENTOS_ALLOW_MODEL_CODE_EXECUTION", "1")

    calls: dict[str, object] = {}

    class DummyTorch:
        float16 = object()
        float32 = object()
        class cuda:
            @staticmethod
            def is_available() -> bool:
                return False

    class DummyTokenizer:
        @classmethod
        def from_pretrained(cls, model_location: str, **kwargs: object):
            calls["tokenizer"] = kwargs
            return cls()

    class DummyModel:
        device = "cpu"

        @classmethod
        def from_pretrained(cls, model_location: str, **kwargs: object):
            calls["model"] = kwargs
            return cls()

        def generate(self, **kwargs: object):
            return [[1]]

    class DummyTransformers:
        AutoTokenizer = DummyTokenizer
        AutoModelForCausalLM = DummyModel

    monkeypatch.setattr("sentientos.local_model.optional_import", lambda name, feature=None: DummyTorch if name == "torch" else DummyTransformers)

    LocalModel.autoload()

    assert calls["tokenizer"]["trust_remote_code"] is True
    assert calls["model"]["trust_remote_code"] is True


def test_transformers_custom_code_requirement_fails_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    model_dir = _prepare_candidate(tmp_path, "hf-local")
    config = {"candidates": [{"path": str(model_dir), "engine": "transformers", "name": "HF"}]}
    config_path = _write_config(tmp_path, config)
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(data_root))
    monkeypatch.setenv("SENTIENTOS_MODEL_CONFIG", str(config_path))
    monkeypatch.delenv("SENTIENTOS_ALLOW_MODEL_CODE_EXECUTION", raising=False)

    class DummyTorch:
        float16 = object()
        float32 = object()
        class cuda:
            @staticmethod
            def is_available() -> bool:
                return False

    class DummyTokenizer:
        @classmethod
        def from_pretrained(cls, model_location: str, **kwargs: object):
            if kwargs.get("trust_remote_code") is False:
                raise ValueError("requires trust_remote_code=True")
            return cls()

    class DummyTransformers:
        AutoTokenizer = DummyTokenizer
        AutoModelForCausalLM = object

    monkeypatch.setattr("sentientos.local_model.optional_import", lambda name, feature=None: DummyTorch if name == "torch" else DummyTransformers)

    model = LocalModel.autoload()
    assert model.metadata.get("engine") == "null"
    errors = model.metadata.get("errors", [])
    assert any("requires custom code" in err for err in errors)
    assert any("explicit opt-in is absent" in err for err in errors)
    assert any("refusing to enable trust_remote_code=True" in err for err in errors)


def test_ollama_backend_forwards_governed_json_schema(monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"model":"pinned"}', encoding="utf-8")
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    candidate = ModelCandidate(manifest, "ollama", "pinned", {
        "api_base": "http://127.0.0.1:11434",
        "model": "sentientos-hermes4:14b-q4km",
        "manifest_sha256": digest,
    })

    class TagsResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _limit):
            return json.dumps({"models": [{"name": candidate.options["model"],
                "digest": digest}]}).encode()

    class Opener:
        def open(self, *_args, **_kwargs):
            return TagsResponse()

    class StreamResponse:
        def __init__(self):
            self.lines = iter([
                (json.dumps({"message": {"content": '{"answer":2}'},
                    "done": False}) + "\n").encode(),
                (json.dumps({"message": {"content": ""},
                    "done": True, "done_reason": "stop"}) + "\n").encode(),
            ])

        def readline(self, _limit):
            return next(self.lines, b"")

    captured: dict[str, object] = {}

    class Connection:
        sock = None

        def __init__(self, *_args, **_kwargs):
            pass

        def request(self, _method, _path, *, body, headers):
            captured["body"] = json.loads(body.decode())
            captured["headers"] = headers

        def getresponse(self):
            return StreamResponse()

        def close(self):
            pass

    monkeypatch.setattr("sentientos.local_model.urllib.request.build_opener",
        lambda *_args, **_kwargs: Opener())
    monkeypatch.setattr("sentientos.local_model.http.client.HTTPConnection", Connection)
    backend = _OllamaBackend(candidate, {}, 1024)
    schema = {"type": "object", "properties": {"answer": {"type": "integer"}},
        "required": ["answer"], "additionalProperties": False}

    answer, _completion = backend.generate_with_metadata("return JSON", [], {
        "structured_output_schema": schema, "temperature": 0,
    })

    assert answer == '{"answer":2}'
    assert captured["body"]["format"] == schema
    assert "structured_output_schema" not in captured["body"]
    with pytest.raises(ModelLoadError, match="ollama_structured_output_schema_invalid"):
        backend.generate_with_metadata("invalid schema", [], {
            "structured_output_schema": "not-a-schema",
        })
