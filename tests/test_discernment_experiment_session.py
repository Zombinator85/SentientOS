from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.discernment_experiment_session import (
    FILES, NO_AUTHORITY, calibrate, doctor, plan_session, trial_handoff, verify_load,
    verify_session,
)
from sentientos.local_model import ActiveModelIdentity, LocalModel
from sentientos.local_model_commissioning import FILES as COMMISSIONING_FILES
from sentientos.local_model_commissioning import render_bundle


def _commission(tmp_path: Path) -> tuple[Path, Path, Path]:
    models = tmp_path / "models"; models.mkdir()
    artifact = models / "operator.gguf"; artifact.write_bytes(b"GGUF-session-production-bytes")
    bundle = tmp_path / "commissioning"
    render_bundle(artifact, allowed_root=models, state_root=bundle, name="session model")
    return artifact, bundle, tmp_path / "session"


def _identity(bundle: Path) -> ActiveModelIdentity:
    preview = json.loads((bundle / COMMISSIONING_FILES["authority"]).read_text())
    row = preview["record"]
    observed = row["observed_metadata"]
    return ActiveModelIdentity(
        engine=row["engine"], resolved_artifact_path=observed["resolved_artifact_path"],
        semantic_artifact_identity=row["semantic_artifact_identity"],
        model_content_sha256=row["model_content_sha256"], artifact_size_bytes=row["artifact_size_bytes"],
        sidecar_metadata_digest=row["sidecar_metadata_digest"],
        configuration_digest=row["configuration_digest"], candidate_index=0,
        posture="production", fallback=False,
    )


class Backend:
    engine = "llama_cpp"
    metadata: dict[str, object] = {}

    def generate(self, prompt: str, history: object, overrides: object) -> str:
        request = json.loads(prompt)
        namespace = request["allowed_observation_namespace"]
        evidence = request["initial_evidence_snapshot"]
        return json.dumps({
            "schema_version": "sentientos.discernment_judgment.v1",
            "proposition": request["proposition"], "interpretation": "bounded evidence",
            "stance": "suspend" if not evidence else "support",
            "confidence": None if not evidence else .5, "strongest_objection": "limited evidence",
            "alternate_interpretations": [], "missing_evidence": [],
            "what_would_change_judgment": [], "expected_observation_keys": [namespace + ".result"],
            "disconfirming_observation_keys": [namespace + ".failure"], "predicted_consequences": [],
            "preferred_next_move": "gather more evidence", "rejected_next_moves": [],
            "unresolved_contradictions": [],
        })


def _fake_load(monkeypatch: pytest.MonkeyPatch, bundle: Path) -> None:
    identity = _identity(bundle)
    monkeypatch.setattr("sentientos.discernment_experiment_session.find_spec", lambda name: object())
    monkeypatch.setattr(LocalModel, "_initialise_backend", classmethod(lambda cls, candidate, config: (Backend(), {})))
    monkeypatch.setattr(LocalModel, "_identity_for", classmethod(lambda cls, candidate, config, backend, metadata, index: identity))


def _planned(tmp_path: Path) -> tuple[Path, Path, Path]:
    artifact, bundle, session = _commission(tmp_path)
    result = plan_session(bundle, session, tmp_path / "calibration")
    assert result["status"] == "planned"
    return artifact, bundle, session


def test_deterministic_session_identity_and_commissioning_binding_without_reentry(tmp_path: Path) -> None:
    _, bundle, first = _planned(tmp_path)
    second = tmp_path / "session-two"
    one = json.loads((first / FILES["manifest"]).read_text())
    plan_session(bundle, second, tmp_path / "calibration-two")
    two = json.loads((second / FILES["manifest"]).read_text())
    assert one["session_id"] == two["session_id"]
    assert one["identity_fields"]["model_id"]
    assert one["identity_fields"]["calibration_corpus_digest"]
    assert not any(one["authority_effect_posture"].values())


def test_mutated_commissioning_manifest_and_model_substitution_fail_closed(tmp_path: Path) -> None:
    artifact, bundle, session = _planned(tmp_path)
    manifest_path = bundle / COMMISSIONING_FILES["manifest"]
    manifest = json.loads(manifest_path.read_text()); manifest["model_bytes_copied"] = True
    manifest_path.write_text(json.dumps(manifest))
    assert verify_session(session)["status"] == "commissioning_blocked"
    # A separately planned chain detects later byte replacement independently.
    other = tmp_path / "other"; other.mkdir(); model = other / "model.gguf"; model.write_bytes(b"GGUF")
    bundle2 = tmp_path / "bundle2"; render_bundle(model, allowed_root=other, state_root=bundle2)
    session2 = tmp_path / "session2"; plan_session(bundle2, session2, tmp_path / "cal2")
    model.write_bytes(b"substitution")
    assert verify_session(session2)["status"] == "commissioning_blocked"
    assert artifact.read_bytes() == b"GGUF-session-production-bytes"


def test_config_authority_candidate_and_path_tampering_are_rejected(tmp_path: Path) -> None:
    for key, mutate in (
        ("config", lambda value: value.update(max_context_tokens=1)),
        ("authority", lambda value: value.update(map_digest="wrong")),
        ("authority", lambda value: value["record"]["observed_metadata"].update(candidate_index=1)),
        ("handoff", lambda value: value.update(model_id="wrong")),
    ):
        case = tmp_path / (key + str(len(list(tmp_path.iterdir())))); case.mkdir()
        _, bundle, session = _planned(case)
        path = bundle / COMMISSIONING_FILES[key]
        value = json.loads(path.read_text()); mutate(value); path.write_text(json.dumps(value))
        assert verify_session(session)["status"] == "commissioning_blocked"


def test_missing_llama_cpp_is_external_prerequisite_and_doctor_runs_zero_cases(tmp_path: Path,
                                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    _, _, session = _planned(tmp_path)
    monkeypatch.setattr("sentientos.discernment_experiment_session.find_spec", lambda name: None)
    proof = verify_load(session)
    assert proof["status"] == "external_prerequisite_unavailable" and proof["semantic_model_generations"] == 0
    report = doctor(session)
    assert report["status"] == "external_prerequisite_unavailable"
    assert report["semantic_model_generations"] == report["calibration_cases_run"] == 0


def test_process_real_load_proof_uses_local_model_and_exact_authority(tmp_path: Path,
                                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    _, bundle, session = _planned(tmp_path); _fake_load(monkeypatch, bundle)
    proof = verify_load(session)
    assert proof["status"] == "load_verified" and proof["process_real"] is True
    assert proof["active_model_identity"]["configuration_digest"] == proof["authority_record"]["configuration_digest"]
    report = doctor(session)
    assert report["status"] == "calibration_eligible"
    assert report["semantic_model_generations"] == report["calibration_cases_run"] == 0


def test_explicit_calibration_uses_canonical_runner_and_reconstructs_artifacts(tmp_path: Path,
                                                                              monkeypatch: pytest.MonkeyPatch) -> None:
    _, bundle, session = _planned(tmp_path); _fake_load(monkeypatch, bundle)
    assert verify_load(session)["status"] == "load_verified"
    result = calibrate(session, repo_root=tmp_path)
    assert result["status"] == "calibration_ready"
    assert result["calibration_binding"]["repeat_semantics"]["comparison_count"] == 1
    assert verify_session(session)["status"] == "calibration_ready"


def test_crash_resume_validates_without_automatic_generation(tmp_path: Path,
                                                              monkeypatch: pytest.MonkeyPatch) -> None:
    _, bundle, session = _planned(tmp_path); _fake_load(monkeypatch, bundle); verify_load(session)
    first = calibrate(session, repo_root=tmp_path)
    assert first["status"] == "calibration_ready"
    monkeypatch.setattr("sentientos.discernment_experiment_session.DiscernmentCalibrationRunner.run",
                        lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("must not rerun")))
    resumed = calibrate(session, repo_root=tmp_path)
    assert resumed["resumed_without_generation"] is True


def test_partial_or_corrupt_calibration_custody_fails_closed(tmp_path: Path,
                                                             monkeypatch: pytest.MonkeyPatch) -> None:
    _, bundle, session = _planned(tmp_path); _fake_load(monkeypatch, bundle); verify_load(session); doctor(session)
    calibration = tmp_path / "calibration" / "calibration-interrupted"; calibration.mkdir(parents=True)
    (calibration / "manifest.json").write_text("{}")
    result = calibrate(session, repo_root=tmp_path)
    assert result["status"] == "calibration_blocked"
    assert result["semantic_model_generations"] == 0


def test_only_live_ready_can_emit_non_authoritative_trial_handoff(tmp_path: Path,
                                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    _, bundle, session = _planned(tmp_path); _fake_load(monkeypatch, bundle); verify_load(session)
    assert trial_handoff(session)["status"] == "calibration_blocked"
    assert calibrate(session, repo_root=tmp_path)["status"] == "calibration_ready"
    handoff = trial_handoff(session)
    assert handoff["status"] == "trial_handoff_ready"
    assert handoff["operator_consideration_only"] and handoff["blind_trial_custody_action_required"]
    assert handoff["authority_effect_posture"] == NO_AUTHORITY


@pytest.mark.parametrize("classification", ["calibration_degraded", "calibration_blocked", "calibration_unavailable"])
def test_nonready_calibration_never_produces_trial_handoff(tmp_path: Path,
                                                           monkeypatch: pytest.MonkeyPatch,
                                                           classification: str) -> None:
    _, bundle, session = _planned(tmp_path); _fake_load(monkeypatch, bundle); verify_load(session)
    assert calibrate(session, repo_root=tmp_path)["status"] == "calibration_ready"
    path = session / FILES["calibration"]
    binding = json.loads(path.read_text()); binding["readiness_classification"] = classification
    from sentientos.local_model_authority import digest_payload
    binding["binding_digest"] = digest_payload({k: v for k, v in binding.items() if k != "binding_digest"})
    path.write_text(json.dumps(binding))
    # Reconstruction compares the edited binding to canonical calibration custody and fails closed.
    assert trial_handoff(session)["status"] == "calibration_blocked"


def test_model_bytes_are_not_copied_and_session_posture_is_inert(tmp_path: Path) -> None:
    artifact, _, session = _planned(tmp_path)
    assert not any(path.is_file() and path.read_bytes() == artifact.read_bytes() for path in session.iterdir())
    for path in session.iterdir():
        value = json.loads(path.read_text())
        assert not any(value["authority_effect_posture"].values())
