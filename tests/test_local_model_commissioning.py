from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.config import GenerationConfig, ModelCandidate, ModelConfig
from sentientos.local_model import LocalModel
from sentientos.local_model_authority import build_local_model_authority_map
from sentientos.local_model_commissioning import FILES, doctor, inspect_artifact, render_bundle, verify_bundle


def _artifact(root: Path, content: bytes = b"GGUF-local-test-bytes") -> Path:
    root.mkdir()
    path = root / "operator.gguf"
    path.write_bytes(content)
    return path


def test_deterministic_commissioning_uses_existing_config_and_authority(tmp_path: Path) -> None:
    models = tmp_path / "models"; model = _artifact(models)
    first = inspect_artifact(model, allowed_root=models, name="operator model")
    second = inspect_artifact(model, allowed_root=models, name="operator model")
    assert first == second
    state = tmp_path / "external-state"
    rendered = render_bundle(model, allowed_root=models, state_root=state, name="operator model")
    config = json.loads((state / FILES["config"]).read_text())
    assert config["candidates"][0]["path"] == str(model.resolve())
    authority = rendered["authority_preview"]
    assert authority["record"]["configuration_digest"] == first["configuration_digest"]
    assert authority["record"]["runtime_eligibility_status"] == "eligible"
    assert verify_bundle(state)["status"] == "verified"
    assert not any(path.read_bytes() == model.read_bytes() for path in state.iterdir())


def test_provider_simulation_missing_and_symlink_are_rejected(tmp_path: Path) -> None:
    models = tmp_path / "models"; model = _artifact(models)
    with pytest.raises(ValueError, match="provider_engine_blocked"):
        inspect_artifact(model, allowed_root=models, engine="openai")
    with pytest.raises(ValueError, match="production_engine_required"):
        inspect_artifact(model, allowed_root=models, engine="echo")
    with pytest.raises((ValueError, FileNotFoundError)):
        inspect_artifact(models / "missing.gguf", allowed_root=models)
    link = models / "link.gguf"; link.symlink_to(model)
    with pytest.raises(ValueError, match="artifact_symlink_blocked"):
        inspect_artifact(link, allowed_root=models)
    outside = tmp_path / "outside"; outside.mkdir(); escaped = outside / "e.gguf"; escaped.write_bytes(b"GGUF")
    with pytest.raises(ValueError, match="artifact_root_escape"):
        inspect_artifact(escaped, allowed_root=models)


def test_artifact_substitution_and_config_mutation_fail_closed(tmp_path: Path) -> None:
    models = tmp_path / "models"; model = _artifact(models)
    state = tmp_path / "state"; render_bundle(model, allowed_root=models, state_root=state)
    model.write_bytes(b"GGUF-replaced")
    result = verify_bundle(state)
    assert result["status"] == "blocked"
    assert any("artifact_identity_substituted" in reason for reason in result["reason_codes"])
    model.write_bytes(b"GGUF-local-test-bytes")
    config_path = state / FILES["config"]
    config = json.loads(config_path.read_text()); config["max_context_tokens"] = 99
    config_path.write_text(json.dumps(config))
    result = verify_bundle(state)
    assert "config_digest_mismatch" in result["reason_codes"]


def test_authority_tampering_candidate_path_sidecar_and_digest_are_rejected(tmp_path: Path) -> None:
    models = tmp_path / "models"; model = _artifact(models)
    state = tmp_path / "state"; render_bundle(model, allowed_root=models, state_root=state)
    preview_path = state / FILES["authority"]
    for field, value in (("configuration_digest", "bad"), ("sidecar_metadata_digest", "bad")):
        preview = json.loads(preview_path.read_text()); preview["record"][field] = value
        preview_path.write_text(json.dumps(preview))
        assert verify_bundle(state)["status"] == "blocked"
        render = tmp_path / ("fresh-" + field)
        render_bundle(model, allowed_root=models, state_root=render)
        preview_path = render / FILES["authority"]
    preview = json.loads(preview_path.read_text()); preview["record"]["observed_metadata"]["candidate_index"] = 1
    preview_path.write_text(json.dumps(preview))
    assert verify_bundle(preview_path.parent)["status"] == "blocked"


def test_controlled_loader_identity_exact_map_call_path(monkeypatch: pytest.MonkeyPatch,
                                                        tmp_path: Path) -> None:
    models = tmp_path / "models"; artifact = _artifact(models)
    config = ModelConfig([ModelCandidate(artifact, "llama_cpp")], generation=GenerationConfig())
    authority = build_local_model_authority_map(config, allowed_roots=[models],
                                                observed_at="1970-01-01T00:00:00+00:00")
    class Backend:
        engine = "llama_cpp"
        metadata: dict[str, object] = {}
    identity = LocalModel._identity_for(config.candidates[0], config, Backend(), {}, 0)  # type: ignore[arg-type]
    assert authority.record_for_active_identity(identity, "discernment_judgment") is not None


def test_doctor_is_zero_generation_and_handoff_never_runs_calibration(tmp_path: Path,
                                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    models = tmp_path / "models"; model = _artifact(models)
    state = tmp_path / "state"; render_bundle(model, allowed_root=models, state_root=state)
    report = doctor(state)
    assert report["semantic_model_generations"] == 0
    assert report["calibration_cases_run"] == 0
    handoff = json.loads((state / FILES["handoff"]).read_text())
    assert handoff["target_subsystem"] == "sentientos.discernment_calibration"
    assert handoff["automatic_calibration_run"] is False and handoff["trial_enrolled"] is False
    assert not any(handoff["authority_effect_posture"].values())


def test_real_verification_never_labels_unavailable_dependency_as_production(tmp_path: Path,
                                                                             monkeypatch: pytest.MonkeyPatch) -> None:
    models = tmp_path / "models"; model = _artifact(models)
    state = tmp_path / "state"; render_bundle(model, allowed_root=models, state_root=state)
    monkeypatch.setattr("sentientos.local_model_commissioning.importlib.util.find_spec", lambda name: None)
    proof = verify_bundle(state, load=True)["load_verification"]
    assert proof["status"] == "external_prerequisite_unavailable"
    assert proof["process_real"] is False
