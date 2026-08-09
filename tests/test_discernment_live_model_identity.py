from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentientos.config import GenerationConfig, ModelCandidate, ModelConfig
from sentientos.control_plane_kernel import ControlPlaneKernel, LifecyclePhase
from sentientos.discernment_participant import live_discernment_readiness
from sentientos.governed_local_model_invocation import GovernedLocalModelInvoker
from sentientos.local_model import ActiveModelIdentity
from sentientos.local_model_authority import build_local_model_authority_map

pytestmark = pytest.mark.no_legacy_skip


class LoadedModel:
    def __init__(self, identity: ActiveModelIdentity, output: str = "{}") -> None:
        self.active_identity = identity
        self.output = output
        self.calls = 0
        self.metadata: dict[str, object] = {}

    def generate_governed(self, prompt: str, **kwargs: object) -> str:
        self.calls += 1
        return self.output


def _identity(record: object, *, index: int, fallback: bool = False) -> ActiveModelIdentity:
    rec = record
    return ActiveModelIdentity(
        engine=rec.engine, resolved_artifact_path=rec.observed_metadata["resolved_artifact_path"],
        semantic_artifact_identity=rec.semantic_artifact_identity,
        model_content_sha256=rec.model_content_sha256, artifact_size_bytes=rec.artifact_size_bytes,
        sidecar_metadata_digest=rec.sidecar_metadata_digest, configuration_digest=rec.configuration_digest,
        candidate_index=index, posture="simulation" if fallback else "production", fallback=fallback,
    )


def _invoker(tmp_path: Path, model: LoadedModel, authority: object) -> GovernedLocalModelInvoker:
    kernel = ControlPlaneKernel(phase=LifecyclePhase.RUNTIME, decisions_path=tmp_path / "decisions.jsonl")
    return GovernedLocalModelInvoker(model=model, authority_map=authority, kernel=kernel,
                                     runtime_root=tmp_path / "runtime")


def test_second_loaded_candidate_is_bound_instead_of_first_eligible_candidate(tmp_path: Path) -> None:
    first = tmp_path / "a.gguf"; second = tmp_path / "b.gguf"
    first.write_bytes(b"candidate-a"); second.write_bytes(b"candidate-b")
    config = ModelConfig(candidates=[ModelCandidate(path=first, engine="llama_cpp"),
                                     ModelCandidate(path=second, engine="llama_cpp")])
    authority = build_local_model_authority_map(config)
    model = LoadedModel(_identity(authority.records[1], index=1))
    request = _invoker(tmp_path, model, authority).build_request(
        purpose="discernment_judgment", prompt="bounded", caller="test", correlation_id="candidate-b")
    assert request.model_id == authority.records[1].model_id
    assert request.model_id != authority.records[0].model_id
    assert request.active_model_identity["candidate_index"] == 1


def test_fallback_and_tampered_identity_fail_before_generation(tmp_path: Path) -> None:
    artifact = tmp_path / "production.gguf"; artifact.write_bytes(b"production")
    authority = build_local_model_authority_map(ModelConfig(candidates=[ModelCandidate(path=artifact, engine="llama_cpp")]))
    production = _identity(authority.records[0], index=0)
    fallback = LoadedModel(ActiveModelIdentity(
        engine="null", resolved_artifact_path=None, semantic_artifact_identity="pathless_model",
        model_content_sha256=None, artifact_size_bytes=None, sidecar_metadata_digest=None,
        configuration_digest="fallback", candidate_index=None, posture="null_fallback", fallback=True))
    invoker = _invoker(tmp_path / "fallback", fallback, authority)
    receipt = invoker.invoke(invoker.build_request(purpose="discernment_judgment", prompt="bounded",
                                                   caller="test", correlation_id="fallback"), persist=False)
    assert receipt.status == "blocked_invalid"
    assert "active_model_not_production" in receipt.reason_codes
    assert fallback.calls == 0

    tampered = LoadedModel(ActiveModelIdentity(**{**production.to_dict(), "model_content_sha256": "tampered"}))
    invoker = _invoker(tmp_path / "tampered", tampered, authority)
    receipt = invoker.invoke(invoker.build_request(purpose="discernment_judgment", prompt="bounded",
                                                   caller="test", correlation_id="tampered"), persist=False)
    assert "active_model_authority_mismatch" in receipt.reason_codes
    assert tampered.calls == 0


def test_configured_external_parent_is_safe_but_symlink_escape_is_rejected(tmp_path: Path) -> None:
    external = tmp_path / "external-models"; external.mkdir()
    artifact = external / "model.gguf"; artifact.write_bytes(b"local-only")
    authority = build_local_model_authority_map(ModelConfig(candidates=[ModelCandidate(path=artifact, engine="llama_cpp")]),
                                                allowed_roots=[tmp_path / "unrelated-repo"])
    assert authority.records[0].runtime_eligibility_status == "eligible"
    assert "artifact_root_escape" not in authority.records[0].reason_codes

    unrelated = tmp_path / "unrelated"; unrelated.mkdir()
    secret = unrelated / "secret.gguf"; secret.write_bytes(b"not-trusted")
    link = external / "escape.gguf"
    try:
        link.symlink_to(secret)
    except OSError:
        pytest.skip("symlinks unavailable")
    escaped = build_local_model_authority_map(ModelConfig(candidates=[ModelCandidate(path=link, engine="llama_cpp")]),
                                              allowed_roots=[external])
    assert escaped.records[0].runtime_eligibility_status == "blocked"
    assert "artifact_root_escape" in escaped.records[0].reason_codes


def test_doctor_is_read_only_and_never_generates(tmp_path: Path) -> None:
    artifact = tmp_path / "model.gguf"; artifact.write_bytes(b"production")
    authority = build_local_model_authority_map(ModelConfig(
        candidates=[ModelCandidate(path=artifact, engine="llama_cpp")],
        generation=GenerationConfig(max_new_tokens=16)))
    model = LoadedModel(_identity(authority.records[0], index=0))
    report = live_discernment_readiness(model, authority)
    assert report["ready_for_live_discernment"] is True
    assert report["matching_model_id"] == authority.records[0].model_id
    assert report["semantic_model_generations"] == 0
    assert model.calls == 0
    assert not any(report["effects"].values())
    json.dumps(report)
