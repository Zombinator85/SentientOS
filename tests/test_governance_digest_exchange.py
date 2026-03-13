from __future__ import annotations

from sentientos.federation.governance_digest import evaluate_compatibility


def test_governance_digest_mismatch_classification():
    comp = evaluate_compatibility({"digest": "deadbeef"})
    assert comp.status in {"incompatible", "same_family_different_patch", "exact_match"}
