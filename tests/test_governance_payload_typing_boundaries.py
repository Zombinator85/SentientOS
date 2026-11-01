from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos import federation_mutation_control_preflight as federation_preflight
from sentientos.runtime_governor import RuntimeGovernor
from sentientos.truth.stance_preflight import validate_planned_claim_against_stance


def test_merge_train_feedback_accepts_null_entries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = tmp_path / "repo"
    state_path = repo_root / "glow" / "forge" / "merge_train.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(json.dumps({"entries": None}), encoding="utf-8")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(repo_root))

    feedback = RuntimeGovernor()._load_evolution_feedback_signal()

    assert feedback["reason"] == "merge_train_state_empty"
    assert feedback["degraded"] is False


def test_federation_preflight_ignores_malformed_nested_diagnostic_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        federation_preflight,
        "federation_typed_action_diagnostic",
        lambda: {"chosen_intents": [], "untyped_out_of_scope_intents": []},
    )
    monkeypatch.setattr(
        federation_preflight,
        "_canonical_execution_diagnostic",
        lambda _intents: {"typed_vs_canonical_by_intent": None},
    )
    monkeypatch.setattr(
        federation_preflight,
        "_bounded_federation_lifecycle_diagnostic",
        lambda _root: {"lifecycle_trace_coherence": {"trace_coherence_map": {"bad": "shape"}}},
    )

    report = federation_preflight.build_federation_mutation_control_preflight()

    note = report["typed_onboarding_pass_note"]
    assert note["coherent_lifecycle_intents"] == []
    assert note["typed_but_not_yet_canonical_observed"] == []


def test_stance_preflight_accepts_immutable_mapping_claims() -> None:
    from types import MappingProxyType

    prior = MappingProxyType(
        {
            "topic_id": "topic-a",
            "claim_id": "claim-1",
            "epistemic_status": "directly_supported",
            "evidence_ids": ["evidence-1"],
        }
    )
    planned = {
        "topic_id": "topic-a",
        "claim_id": "claim-2",
        "epistemic_status": "plausible_but_unverified",
        "evidence_ids": ["evidence-1"],
    }

    result = validate_planned_claim_against_stance(
        planned_claim=planned,
        prior_claims=[prior],
        stance_receipts=[],
        transition_type="weaken_with_new_evidence",
    )

    assert result["contradiction_receipt"]["contradiction_type"] == "no_new_evidence_reversal"
