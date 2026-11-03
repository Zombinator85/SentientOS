from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

import pytest

from sentientos.config import GenerationConfig, ModelCandidate, ModelConfig
from sentientos.local_model import LocalModel, ModelLoadError
from sentientos.governed_local_model_invocation import validate_backend_completion_observation
from sentientos.local_model_authority import (
    PRODUCTION_ENGINES, build_local_model_authority_map,
)


class _Response:
    def __init__(self, payload: dict) -> None:
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _size: int = -1) -> bytes:
        return self.payload


class _Opener:
    def __init__(self, digest: str) -> None:
        self.digest = digest
        self.requests = []

    def open(self, request, timeout: float):
        self.requests.append(request)
        if request.full_url.endswith("/api/tags"):
            return _Response({"models": [{"name": "qwen3:8b", "digest": self.digest}]})
        if request.full_url.endswith("/api/ps"):
            return _Response({"models": [{"name": "qwen3:8b"}]})
        return _Response({"done": True, "response": "A real local answer."})


class _HTTPResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = json.dumps(payload).encode()
    def read(self, _size: int = -1) -> bytes:
        return self.payload


class _HTTPConnection:
    last_body = b""
    def __init__(self, *_args, **_kwargs) -> None:
        self.body = b""
        self.sock = None
    def request(self, _method: str, path: str, *, body: bytes, headers: dict) -> None:
        self.body = body
        self.path = path
        type(self).last_body = body
    def getresponse(self):
        request = json.loads(self.body)
        if self.path == "/api/generate" and request.get("prompt") == "" and request.get("keep_alive") == "0":
            return _HTTPResponse({"done": True, "response": "", "done_reason": "unload"})
        return _HTTPResponse({"done": True, "message": {"role": "assistant", "content": "A real local answer."},
            "total_duration": 123, "load_duration": 23,
            "prompt_eval_duration": 34, "eval_duration": 56,
            "eval_count": 7, "prompt_eval_count": 9})
    def close(self) -> None:
        pass


def _candidate(tmp_path: Path, *, endpoint: str = "http://127.0.0.1:11434"):
    manifest = tmp_path / "qwen3-manifest"
    manifest.write_text('{"model":"qwen3:8b"}\n', encoding="utf-8")
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    candidate = ModelCandidate(path=manifest, engine="ollama", name="Qwen3 development",
        options={"api_base": endpoint, "model": "qwen3:8b",
            "manifest_sha256": digest, "num_gpu": 99, "keep_alive": "15m",
            "think": False, "timeout_seconds": 30})
    config = ModelConfig([candidate], default_engine="ollama",
        max_context_tokens=4096, generation=GenerationConfig(max_new_tokens=96))
    return manifest, digest, candidate, config


def test_ollama_backend_is_loopback_pinned_and_development_only(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(tmp_path / "data"))
    manifest, digest, candidate, config = _candidate(tmp_path)
    opener = _Opener(digest)
    monkeypatch.setattr("sentientos.local_model.urllib.request.build_opener",
        lambda *_args: opener)
    monkeypatch.setattr("sentientos.local_model.http.client.HTTPConnection", _HTTPConnection)

    backend, _metadata = LocalModel._initialise_backend(candidate, config)
    identity = LocalModel._identity_for(candidate, config, backend, backend.metadata, 0)
    authority = build_local_model_authority_map(config, allowed_roots=[tmp_path])

    assert identity.engine == "ollama"
    assert "ollama" not in PRODUCTION_ENGINES
    assert identity.posture == "development_only"
    assert identity.fallback is False
    assert authority.records[0].runtime_eligibility_status == "eligible"
    assert authority.records[0].disposition == "development_only"
    assert authority.records[0].allowed_invocation_purposes == ("local_user_chat",)
    assert authority.records[0].provider_network_posture == "loopback_only"
    assert authority.record_for_active_identity(identity, "local_user_chat") is authority.records[0]
    assert authority.record_for_active_identity(identity, "maintenance_implementation") is None
    prompt = ("[SYSTEM_INSTRUCTION]\nKeep this trusted instruction.\n"
        "[VERIFIED_RUNTIME_CONTEXT]\n{}\n[SESSION_HISTORY_DATA]\nUSER_DATA: hello")
    assert backend.generate(prompt, (), {"max_new_tokens": 96}) == "A real local answer."
    sent = json.loads(_HTTPConnection.last_body)
    assert sent["model"] == "qwen3:8b"
    assert sent["stream"] is False
    assert sent["options"]["num_ctx"] == 4096
    assert sent["options"]["num_gpu"] == 99
    assert sent["messages"] == [
        {"role": "system", "content": "Keep this trusted instruction.\n[VERIFIED_RUNTIME_CONTEXT]\n{}"},
        {"role": "user", "content": "[SESSION_HISTORY_DATA]\nUSER_DATA: hello"},
    ]

    text, completion = backend.generate_with_metadata("Say hello", (), {"max_new_tokens": 96})
    assert text == "A real local answer."
    assert completion["total_duration_ns"] == 123
    assert completion["load_duration_ns"] == 23
    assert completion["completion_tokens"] == 7
    assert validate_backend_completion_observation(completion)
    assert backend.is_resident() is True

    released = backend.release_residency()
    assert released == {"backend": "ollama", "model": "qwen3:8b",
        "result": "unload_requested", "done_reason": "unload"}
    unload_request = json.loads(_HTTPConnection.last_body)
    assert unload_request["prompt"] == ""
    assert unload_request["keep_alive"] == "0"

    backend.generate("Say hello", (), {"max_new_tokens": 96, "keep_alive": "0"})
    assert json.loads(_HTTPConnection.last_body)["keep_alive"] == "0"
    request_count = len(opener.requests)
    with pytest.raises(ModelLoadError, match="ollama_keep_alive_invalid"):
        backend.generate("Say hello", (), {"keep_alive": "unbounded"})
    assert len(opener.requests) == request_count


def test_ollama_active_request_can_be_cancelled(monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path) -> None:
    _manifest, digest, candidate, config = _candidate(tmp_path)
    opener = _Opener(digest)
    monkeypatch.setattr("sentientos.local_model.urllib.request.build_opener",
        lambda *_args: opener)
    entered, stopped = threading.Event(), threading.Event()

    class _Socket:
        def shutdown(self, _how: int) -> None:
            stopped.set()

    class _BlockingConnection(_HTTPConnection):
        def __init__(self, *_args, **_kwargs) -> None:
            self.sock = _Socket()
        def getresponse(self):
            entered.set()
            stopped.wait(2)
            raise OSError("request socket closed")

    monkeypatch.setattr("sentientos.local_model.http.client.HTTPConnection", _BlockingConnection)
    backend, _ = LocalModel._initialise_backend(candidate, config)
    failures: list[Exception] = []

    def invoke() -> None:
        try:
            backend.generate("slow", (), {})
        except Exception as exc:
            failures.append(exc)

    worker = threading.Thread(target=invoke)
    worker.start()
    assert entered.wait(1)
    assert backend.cancel_pending_generation() is True
    worker.join(1)
    assert not worker.is_alive()
    assert failures



def test_local_model_load_candidate_selects_exact_model_without_fallback(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(tmp_path / "data"))
    _manifest, digest, candidate, config = _candidate(tmp_path)
    opener = _Opener(digest)
    monkeypatch.setattr("sentientos.local_model.urllib.request.build_opener",
        lambda *_args: opener)

    model = LocalModel.load_candidate(0, config=config)
    assert model.active_identity.candidate_index == 0
    assert model.active_identity.posture == "development_only"
    assert model.active_identity.fallback is False
    with pytest.raises(ModelLoadError, match="candidate_index"):
        LocalModel.load_candidate(1, config=config)

def test_ollama_backend_rejects_non_loopback_and_unpinned_manifest(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(tmp_path / "data"))
    _manifest, _digest, candidate, config = _candidate(tmp_path, endpoint="https://example.com")
    authority = build_local_model_authority_map(config, allowed_roots=[tmp_path])
    assert authority.records[0].runtime_eligibility_status == "blocked"
    assert "development_endpoint_not_loopback" in authority.records[0].reason_codes
    with pytest.raises(ModelLoadError, match="loopback"):
        LocalModel._initialise_backend(candidate, config)

    _manifest, _digest, candidate, config = _candidate(tmp_path)
    candidate.options["manifest_sha256"] = "0" * 64
    with pytest.raises(ModelLoadError, match="manifest_digest"):
        LocalModel._initialise_backend(candidate, config)

    _manifest, _digest, candidate, config = _candidate(
        tmp_path, endpoint="http://127.0.0.1:99999")
    with pytest.raises(ModelLoadError, match="loopback"):
        LocalModel._initialise_backend(candidate, config)
