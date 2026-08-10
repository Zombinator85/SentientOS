from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.config import ModelCandidate, ModelConfig
from sentientos.discernment_calibration import (
    DiscernmentCalibrationRunner, NO_AUTHORITY, calibration_doctor,
    canonical_calibration_corpus, validate_calibration_artifacts,
)
from sentientos.governed_local_model_invocation import GovernedLocalModelInvoker
from sentientos.local_model import ActiveModelIdentity
from sentientos.local_model_authority import build_local_model_authority_map


class Model:
    def __init__(self, identity: ActiveModelIdentity) -> None:
        self.active_identity = identity
        self.metadata: dict[str, object] = {}
        self.calls = 0

    def generate_governed(self, prompt: str, **kwargs: object) -> str:
        self.calls += 1
        request = json.loads(prompt)
        namespace = request["allowed_observation_namespace"]
        value = {
            "schema_version": "sentientos.discernment_judgment.v1",
            "proposition": request["proposition"], "interpretation": "bounded evidence",
            "stance": "suspend" if not request["initial_evidence_snapshot"] else "support",
            "confidence": None if not request["initial_evidence_snapshot"] else 0.5,
            "strongest_objection": "limited evidence", "alternate_interpretations": [],
            "missing_evidence": [], "what_would_change_judgment": [],
            "expected_observation_keys": [namespace + ".result"],
            "disconfirming_observation_keys": [namespace + ".failure"],
            "predicted_consequences": [], "preferred_next_move": "gather more evidence",
            "rejected_next_moves": [], "unresolved_contradictions": [],
        }
        return json.dumps(value)


def _rig(tmp_path: Path, *, fallback: bool = False):
    tmp_path.mkdir(parents=True, exist_ok=True)
    artifact = tmp_path / "model.gguf"; artifact.write_bytes(b"production model")
    config = ModelConfig(candidates=[ModelCandidate(path=artifact, engine="llama_cpp")])
    authority = build_local_model_authority_map(config, allowed_roots=[tmp_path])
    record = authority.records[0]
    identity = ActiveModelIdentity(
        engine="null" if fallback else record.engine,
        resolved_artifact_path=None if fallback else record.observed_metadata["resolved_artifact_path"],
        semantic_artifact_identity="pathless_model" if fallback else record.semantic_artifact_identity,
        model_content_sha256=None if fallback else record.model_content_sha256,
        artifact_size_bytes=None if fallback else record.artifact_size_bytes,
        sidecar_metadata_digest=None if fallback else record.sidecar_metadata_digest,
        configuration_digest="fallback" if fallback else record.configuration_digest,
        candidate_index=None if fallback else 0,
        posture="null_fallback" if fallback else "production", fallback=fallback,
    )
    model = Model(identity)
    invoker = GovernedLocalModelInvoker(model=model, authority_map=authority,
                                        runtime_root=tmp_path / "invocations")
    return model, authority, invoker


def test_corpus_is_order_independent_but_evidence_bytes_are_bound() -> None:
    corpus = canonical_calibration_corpus()
    shuffled = canonical_calibration_corpus(list(reversed(corpus["cases"])))
    assert corpus["corpus_digest"] == shuffled["corpus_digest"]
    changed = deepcopy(corpus["cases"]); changed[0]["initial_evidence_snapshot"] = {"changed": True}; changed[0].pop("case_digest")
    assert canonical_calibration_corpus(changed)["corpus_digest"] != corpus["corpus_digest"]
    assert len(corpus["cases"]) >= 14
    assert all("correct_stance" not in row for row in corpus["cases"])


def test_canonical_participant_and_governed_invoker_are_in_real_call_path(tmp_path: Path) -> None:
    model, authority, invoker = _rig(tmp_path)
    runner = DiscernmentCalibrationRunner(tmp_path, tmp_path / "calibration", model, authority, invoker,
                                          evidence_mode="simulated_test")
    report = runner.run()
    assert model.calls == len(report["manifest"]["results"])
    assert invoker.invocation_counts
    assert report["manifest"]["evidence_mode"] == "simulated_test"
    assert report["manifest"]["summary"]["readiness_classification"] == "calibration_degraded"
    assert report["validation"]["valid"] is True


def test_simulated_evidence_cannot_be_labeled_live_ready(tmp_path: Path) -> None:
    model, authority, invoker = _rig(tmp_path)
    result = DiscernmentCalibrationRunner(tmp_path, tmp_path / "state", model, authority, invoker,
                                          evidence_mode="simulated_test").run()
    assert result["manifest"]["summary"]["readiness_classification"] != "calibration_ready"
    assert result["handoff"]["suitable_for_operator_consideration"] is False


def test_fallback_and_missing_live_model_report_unavailable_without_generation(tmp_path: Path) -> None:
    model, authority, invoker = _rig(tmp_path, fallback=True)
    result = DiscernmentCalibrationRunner(tmp_path, tmp_path / "state", model, authority, invoker).run()
    assert result["manifest"]["summary"]["readiness_classification"] == "calibration_unavailable"
    assert model.calls == 0
    assert "simulation_or_fallback_backend_loaded" in result["manifest"]["summary"]["degraded_or_blocked_reasons"]


def test_identity_change_mid_run_is_retained_and_blocks(tmp_path: Path) -> None:
    model, authority, invoker = _rig(tmp_path)
    original = model.active_identity
    calls = 0

    def participant(request, *, invoker):
        nonlocal calls
        calls += 1
        if calls == 2:
            model.active_identity = ActiveModelIdentity(**{**original.to_dict(), "configuration_digest": "changed"})
        return {"judgment": {"stance": "suspend"}, "model_invocation": {"status": "admitted_completed", "reason_codes": []}}

    result = DiscernmentCalibrationRunner(tmp_path, tmp_path / "state", model, authority, invoker,
                                          participant=participant).run()
    assert result["manifest"]["summary"]["readiness_classification"] == "calibration_blocked"
    assert result["manifest"]["results"][-1]["disposition"] == "identity_changed"


def test_malformed_timeout_and_semantic_mismatch_are_reported(tmp_path: Path) -> None:
    model, authority, invoker = _rig(tmp_path)
    calls = 0
    def participant(request, *, invoker):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"judgment": {"stance": "suspend"}, "model_invocation": {"status": "suspended", "invocation_status": "output_malformed", "reason_codes": []}}
        if calls == 2: raise TimeoutError
        return {"judgment": {"stance": "support", "interpretation": str(calls)}, "model_invocation": {"status": "admitted_completed", "reason_codes": []}}
    result = DiscernmentCalibrationRunner(tmp_path, tmp_path / "state", model, authority, invoker,
                                          participant=participant, evidence_mode="simulated_test").run()
    summary = result["manifest"]["summary"]
    assert summary["malformed_output_count"] == 1
    assert summary["timeout_count"] == 1
    assert summary["repeat_semantic_mismatch_count"] == 1
    comparison = next(row["repeat_comparison"] for row in result["manifest"]["results"] if "repeat_comparison" in row)
    assert comparison["differing_fields"]


def test_saved_artifacts_reconstruct_and_nested_mutation_fails(tmp_path: Path) -> None:
    model, authority, invoker = _rig(tmp_path)
    result = DiscernmentCalibrationRunner(tmp_path, tmp_path / "state", model, authority, invoker,
                                          evidence_mode="simulated_test").run(observed_at="one")
    corpus = canonical_calibration_corpus()
    assert validate_calibration_artifacts(result["manifest"], corpus, result["handoff"])["valid"]
    mutated = deepcopy(result["manifest"])
    mutated["results"][0]["authority_effect_posture"]["execution"] = True
    report = validate_calibration_artifacts(mutated, corpus, result["handoff"])
    assert not report["valid"]
    assert "nested_authority_effect_escalation" in report["reason_codes"]


def test_timestamp_and_storage_path_do_not_affect_case_or_manifest_identity(tmp_path: Path) -> None:
    model, authority, invoker = _rig(tmp_path / "a")
    first = DiscernmentCalibrationRunner(tmp_path, tmp_path / "a" / "state", model, authority, invoker,
                                         evidence_mode="simulated_test").run(observed_at="one")
    # Compare the digest algorithm directly after changing observation metadata.
    manifest = deepcopy(first["manifest"]); manifest["observed_at"] = "two"; manifest["storage_root"] = "/elsewhere"
    assert validate_calibration_artifacts(manifest, canonical_calibration_corpus(), first["handoff"])["valid"]


def test_doctor_is_zero_generation_and_zero_write(tmp_path: Path) -> None:
    model, authority, _ = _rig(tmp_path)
    root = tmp_path / "not-created"
    report = calibration_doctor(model=model, authority_map=authority, runtime_root=root)
    assert report["semantic_model_generations"] == 0
    assert model.calls == 0 and not root.exists()
    assert report["live_calibration_could_begin"] is True
    assert not any(report["authority_effect_posture"].values())


def test_handoff_never_enrolls_or_submits_to_trial(tmp_path: Path) -> None:
    model, authority, invoker = _rig(tmp_path)
    result = DiscernmentCalibrationRunner(tmp_path, tmp_path / "state", model, authority, invoker,
                                          evidence_mode="simulated_test").run()
    assert result["handoff"]["trial_enrolled"] is False
    assert result["handoff"]["judgment_submitted"] is False
    assert result["handoff"]["authority_effect_posture"] == NO_AUTHORITY
