from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from sentientos.config import GenerationConfig, ModelCandidate, ModelConfig
from sentientos.local_model import LocalModel, ModelLoadError
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
        return _Response({"done": True, "response": "A real local answer."})


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
    assert backend.generate("Say hello", (), {"max_new_tokens": 96}) == "A real local answer."
    generation_request = opener.requests[-1]
    sent = json.loads(generation_request.data)
    assert sent["model"] == "qwen3:8b"
    assert sent["stream"] is False
    assert sent["options"]["num_ctx"] == 4096
    assert sent["options"]["num_gpu"] == 99

    backend.generate("Say hello", (), {"max_new_tokens": 96, "keep_alive": "0"})
    assert json.loads(opener.requests[-1].data)["keep_alive"] == "0"
    request_count = len(opener.requests)
    with pytest.raises(ModelLoadError, match="ollama_keep_alive_invalid"):
        backend.generate("Say hello", (), {"keep_alive": "unbounded"})
    assert len(opener.requests) == request_count


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
