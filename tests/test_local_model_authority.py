from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.config import GenerationConfig, ModelCandidate, ModelConfig
from sentientos.local_model import ActiveModelIdentity
from sentientos.local_model_authority import (build_local_model_authority_map,
    build_developmental_companion_authority_map,
    build_rootless_experimental_developmental_companion_authority_map,
    ROOTLESS_EXPERIMENTAL_DEVELOPMENTAL_COMPANION_INVOCATION_PURPOSES,
    validate_authority_map, render_authority_map_markdown)


def test_authority_map_verifies_local_gguf_and_stable_when_moved(tmp_path: Path) -> None:
    root1 = tmp_path / "a"; root2 = tmp_path / "b"; root1.mkdir(); root2.mkdir()
    one = root1 / "m.gguf"; two = root2 / "m.gguf"
    one.write_bytes(b"model-bytes"); two.write_bytes(b"model-bytes")
    cfg1 = ModelConfig(candidates=[ModelCandidate(path=one, engine="llama_cpp", name="m")], generation=GenerationConfig(max_new_tokens=32))
    cfg2 = ModelConfig(candidates=[ModelCandidate(path=two, engine="llama_cpp", name="m")], generation=GenerationConfig(max_new_tokens=32))
    m1 = build_local_model_authority_map(cfg1, allowed_roots=[root1])
    m2 = build_local_model_authority_map(cfg2, allowed_roots=[root2])
    assert m1.records[0].model_id == m2.records[0].model_id
    assert m1.records[0].runtime_eligibility_status == "eligible"
    ok, reasons = validate_authority_map(m1.to_dict())
    assert ok, reasons
    assert "no-network" not in render_authority_map_markdown(m1).lower()


def test_authority_map_blocks_provider_and_tampering(tmp_path: Path) -> None:
    model = tmp_path / "m.gguf"; model.write_bytes(b"abc")
    cfg = ModelConfig(candidates=[ModelCandidate(path=model, engine="openai", options={"api_key": "x"})])
    authority = build_local_model_authority_map(cfg, allowed_roots=[tmp_path])
    assert authority.records[0].runtime_eligibility_status == "blocked"
    assert "provider_engine_blocked" in authority.records[0].reason_codes
    payload = authority.to_dict(); payload["records"][0]["engine"] = "llama_cpp"
    ok, reasons = validate_authority_map(payload)
    assert not ok and "map_digest_mismatch" in reasons


def test_authority_map_rejects_digest_mismatch_and_oversized_candidate_count(tmp_path: Path) -> None:
    model = tmp_path / "m.gguf"; model.write_bytes(b"abc")
    cfg = ModelConfig(candidates=[ModelCandidate(path=model, engine="llama_cpp", options={"sha256": "0" * 64})] + [ModelCandidate(path=model, engine="echo") for _ in range(40)])
    authority = build_local_model_authority_map(cfg, allowed_roots=[tmp_path])
    assert "content_digest_mismatch" in authority.records[0].reason_codes
    assert any("candidate_count_exceeded" in r.reason_codes for r in authority.records)


def test_developmental_companion_authority_is_local_chat_and_cognition_only(
        tmp_path: Path) -> None:
    model = tmp_path / "ollama-model.gguf"
    model.write_bytes(b"verified local development model")
    import hashlib
    digest = hashlib.sha256(model.read_bytes()).hexdigest()
    config = ModelConfig(candidates=[ModelCandidate(path=model, engine="ollama",
        name="local", options={"manifest_sha256": digest})])
    authority = build_developmental_companion_authority_map(
        config, allowed_roots=[tmp_path])
    record = authority.records[0]
    assert record.runtime_eligibility_status == "eligible"
    assert record.allowed_invocation_purposes == (
        "local_user_chat", "resident_developmental_retrieval_cognition")
    assert record.tool_posture == record.memory_posture == record.action_posture == "blocked"
    identity = ActiveModelIdentity(engine=record.engine,
        resolved_artifact_path=record.observed_metadata["resolved_artifact_path"],
        semantic_artifact_identity=record.semantic_artifact_identity,
        model_content_sha256=record.model_content_sha256,
        artifact_size_bytes=record.artifact_size_bytes,
        sidecar_metadata_digest=record.sidecar_metadata_digest,
        configuration_digest=record.configuration_digest, candidate_index=0,
        posture="development_only", fallback=False)
    assert authority.record_for_active_identity(
        identity, "local_user_chat") == record
    assert authority.record_for_active_identity(
        identity, "resident_developmental_retrieval_cognition") == record
    assert authority.record_for_active_identity(
        identity, "resident_developmental_interpretation") is None
    valid, reasons = validate_authority_map(authority.to_dict())
    assert valid, reasons


def test_rootless_developmental_companion_authority_is_explicit_and_bounded(
        tmp_path: Path) -> None:
    model = tmp_path / "ollama-model.gguf"
    model.write_bytes(b"verified local development model")
    import hashlib
    digest = hashlib.sha256(model.read_bytes()).hexdigest()
    config = ModelConfig(candidates=[ModelCandidate(path=model, engine="ollama",
        name="local", options={"manifest_sha256": digest})])
    normal = build_developmental_companion_authority_map(
        config, allowed_roots=[tmp_path])
    experimental = build_rootless_experimental_developmental_companion_authority_map(
        config, allowed_roots=[tmp_path])
    normal_record = normal.records[0]
    record = experimental.records[0]

    assert normal_record.allowed_invocation_purposes == (
        "local_user_chat", "resident_developmental_retrieval_cognition")
    assert record.runtime_eligibility_status == "eligible"
    assert record.allowed_invocation_purposes == (
        ROOTLESS_EXPERIMENTAL_DEVELOPMENTAL_COMPANION_INVOCATION_PURPOSES)
    assert record.disposition == (
        "rootless_experimental_developmental_companion_candidate")
    assert record.tool_posture == record.memory_posture == record.action_posture == "blocked"
    identity = ActiveModelIdentity(engine=record.engine,
        resolved_artifact_path=record.observed_metadata["resolved_artifact_path"],
        semantic_artifact_identity=record.semantic_artifact_identity,
        model_content_sha256=record.model_content_sha256,
        artifact_size_bytes=record.artifact_size_bytes,
        sidecar_metadata_digest=record.sidecar_metadata_digest,
        configuration_digest=record.configuration_digest, candidate_index=0,
        posture="development_only", fallback=False)
    for purpose in ROOTLESS_EXPERIMENTAL_DEVELOPMENTAL_COMPANION_INVOCATION_PURPOSES:
        assert experimental.record_for_active_identity(identity, purpose) == record
    assert normal.record_for_active_identity(
        identity, "resident_developmental_interpretation") is None
    assert experimental.record_for_active_identity(
        identity, "avatar_renderer_command") is None
    valid, reasons = validate_authority_map(experimental.to_dict())
    assert valid, reasons
