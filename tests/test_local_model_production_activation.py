from __future__ import annotations

from sentientos.local_model_production_activation import (
    ABSENT, APPROVAL_SCHEMA, EFFECTS, INTENT_SCHEMA, PRINCIPAL, STATE_SCHEMA,
    _expected_prior, effect_set_digest, verify_activation_state,
)
from sentientos.local_runtime_provisioning import semantic_digest

import pytest

pytestmark = pytest.mark.no_legacy_skip


def test_activation_contract_is_exact_and_selection_only() -> None:
    assert PRINCIPAL == "deterministic_local_model_activation_controller"
    assert len(EFFECTS) == len(set(EFFECTS)) == 8
    assert INTENT_SCHEMA.endswith("activation_intent:v1")
    assert APPROVAL_SCHEMA.endswith("activation_approval:v1")
    assert effect_set_digest() == semantic_digest({"effects": sorted(EFFECTS)})


def test_hardened_state_v2_is_selection_only() -> None:
    state = {"schema_version": STATE_SCHEMA, "status": "commissioned_model_selected_active",
             "generation": 1, "model_loaded": False, "serving_started": False,
             "inference_performed": False}
    state["state_semantic_digest"] = semantic_digest(state)
    assert verify_activation_state(state)
    for field in ("model_loaded", "serving_started", "inference_performed"):
        changed = dict(state); changed[field] = True
        body = dict(changed); body.pop("state_semantic_digest")
        changed["state_semantic_digest"] = semantic_digest(body)
        assert not verify_activation_state(changed)


@pytest.mark.parametrize("value", ("", "*", "current", "latest", "any", "wildcard", "0" * 63))
def test_prior_state_rejects_wildcards(value: str) -> None:
    with pytest.raises(Exception, match="exact_expected_prior"):
        _expected_prior(value)
    assert _expected_prior(ABSENT) == ABSENT
