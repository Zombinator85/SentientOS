from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentientos.longitudinal_self_model import LongitudinalSelfModelError, LongitudinalSelfModelOwner, load_runtime_config
from sentientos.self_model_intervention_experiment import CONDITION_ORDER, build_answer_key, make_protocol, score_assessment
from tests.test_resident_developmental_cognition import owner as cognition_owner, snapshot as cognition_snapshot
from tests.test_longitudinal_self_model import record, snapshot

pytestmark = pytest.mark.no_legacy_skip


def test_runtime_config_reconstructs_exact_custody_and_rejects_tamper(tmp_path: Path) -> None:
    custody = (tmp_path / "custody").resolve(); owner = LongitudinalSelfModelOwner(custody)
    owner.reconcile(snapshot(record()), tick_id="tick-1")
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"schema":"sentientos.longitudinal_self_model_runtime_config:v1",
        "enabled":True, "custody_root":str(custody), "cognitive_consumption_enabled":True,
        "max_projection_claims":4, "allowed_predicates":["software_generation","cognitive_model_identity"],
        "installation_id":"installation-a"}))
    loaded = load_runtime_config(config)
    assert LongitudinalSelfModelOwner(loaded.custody_root).history()[0].tick_id == "tick-1"
    path = next((custody / "reconciliations").glob("*.json")); raw=json.loads(path.read_text())
    raw["tick_id"]="tampered"; path.write_text(json.dumps(raw))
    with pytest.raises(LongitudinalSelfModelError, match="digest_mismatch"):
        LongitudinalSelfModelOwner(loaded.custody_root).history()


def test_prior_tick_projection_is_bounded_exact_and_same_tick_excluded(tmp_path: Path) -> None:
    owner = LongitudinalSelfModelOwner(tmp_path)
    first = owner.reconcile(snapshot(record()), tick_id="tick-1")
    projection = owner.cognitive_projection(before_tick="tick-2", max_claims=2,
        allowed_predicates=("software_generation", "cognitive_model_identity"))
    assert projection is not None and projection.source_reconciliation_id == first.reconciliation_id
    assert projection.source_tick == "tick-1" and len(projection.selected_claim_ids) == 2
    assert not any(projection.authority.values()) and projection.read_only
    only = LongitudinalSelfModelOwner(tmp_path / "only")
    only.reconcile(snapshot(record()), tick_id="tick-n")
    assert only.cognitive_projection(before_tick="tick-n", max_claims=2,
        allowed_predicates=("software_generation",)) is None


def test_intervention_controls_and_external_scoring_reject_self_certification(tmp_path: Path) -> None:
    owner = LongitudinalSelfModelOwner(tmp_path); owner.reconcile(snapshot(record()), tick_id="tick-1")
    projection = owner.cognitive_projection(before_tick="tick-2", max_claims=2,
        allowed_predicates=("software_generation", "cognitive_model_identity"))
    assert projection is not None
    protocol = make_protocol(model_id="model-a", model_artifact_digest="sha256:artifact",
        current_snapshot_id="snapshot-2", current_snapshot_digest="sha256:snapshot",
        current_projection_id="current-2", developmental_history_boundary="history-1",
        projection=projection, prompt_digest="sha256:prompt", generation_parameters={"temperature":0},
        inference_budget={"max_new_tokens":128})
    assert protocol.condition_order == CONDITION_ORDER and protocol.retries == 0
    key = build_answer_key(projection); question, expected = next(iter(key.items()))
    scored = score_assessment(answer_key=key, answers=[{"question_id":question,
        "answer":expected["answer"], "claim_ids":[expected["claim_id"]],
        "source_evidence_ids":list(expected["source_evidence_ids"]), "self_marked_correct":True}])
    assert scored["counts"]["supported_correct"] == 1 and scored["counts"]["provenance_correct"] == 1
    assert scored["model_answer_has_scoring_authority"] is False
    smuggled = score_assessment(answer_key=key, answers=[{"question_id":"invented", "answer":"current"}])
    assert smuggled["counts"]["unsupported_assertion"] == 1


def test_resident_receipt_binds_exact_prior_projection(tmp_path: Path) -> None:
    factual = LongitudinalSelfModelOwner(tmp_path / "self-model")
    factual.reconcile(snapshot(record()), tick_id="tick-1")
    projection = factual.cognitive_projection(before_tick="tick-2", max_claims=2,
        allowed_predicates=("software_generation", "cognitive_model_identity"))
    assert projection is not None
    cognition, fake = cognition_owner(tmp_path / "cognition")
    result = cognition.run_tick(snapshot=cognition_snapshot(), tick_id="tick-2", prior_self_model=projection)
    assert result.cognition_observation_ids
    request = next(item for item in fake.requests if item.purpose == "resident_developmental_retrieval_cognition")
    assert request.upstream_evidence["self_model_projection_digest"] == projection.projection_digest
    receipt = json.loads((cognition.observations_root / f"{result.cognition_observation_ids[0]}.json").read_text())
    assert receipt["prior_tick_proven"] is True
    assert receipt["self_model_claim_ids"] == list(projection.selected_claim_ids)
