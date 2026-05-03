from __future__ import annotations

import pytest

from sentientos.embodiment_gate_policy import (
    COMPATIBILITY_LEGACY_MODE,
    PROPOSAL_ONLY_MODE,
    gate_mode_receipt_fields,
    is_compatibility_legacy_mode,
    is_proposal_only_mode,
    normalize_embodiment_gate_mode,
    resolve_embodiment_gate_mode,
)

pytestmark = pytest.mark.no_legacy_skip


def test_normalize_mode_is_deterministic() -> None:
    assert normalize_embodiment_gate_mode(" proposal_only ") == PROPOSAL_ONLY_MODE
    assert normalize_embodiment_gate_mode("bad", fallback=COMPATIBILITY_LEGACY_MODE) == COMPATIBILITY_LEGACY_MODE


def test_resolve_explicit_beats_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMBODIMENT_INGRESS_GATE_MODE", COMPATIBILITY_LEGACY_MODE)
    assert resolve_embodiment_gate_mode(PROPOSAL_ONLY_MODE, default_mode=COMPATIBILITY_LEGACY_MODE) == PROPOSAL_ONLY_MODE


def test_resolve_env_override_works(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMBODIMENT_INGRESS_GATE_MODE", PROPOSAL_ONLY_MODE)
    assert resolve_embodiment_gate_mode(None, default_mode=COMPATIBILITY_LEGACY_MODE) == PROPOSAL_ONLY_MODE


def test_receipt_fields_stable() -> None:
    proposal = gate_mode_receipt_fields(PROPOSAL_ONLY_MODE)
    compat = gate_mode_receipt_fields(COMPATIBILITY_LEGACY_MODE)
    assert proposal["decision_power"] == "none"
    assert proposal["legacy_direct_effect_preserved"] is False
    assert compat["legacy_direct_effect_preserved"] is True
    assert is_proposal_only_mode(proposal["ingress_gate_mode"]) is True
    assert is_compatibility_legacy_mode(compat["ingress_gate_mode"]) is True
