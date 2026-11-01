from __future__ import annotations

import pytest

pytestmark = pytest.mark.no_legacy_skip

from scripts.remote_probe import _comparison_summary


def test_comparison_summary_handles_missing_and_malformed_payloads() -> None:
    assert _comparison_summary({}) == ({}, [])
    assert _comparison_summary({"compare_remote_to_local": None}) == ({}, [])
    assert _comparison_summary(
        {"compare_remote_to_local": {"status": "diverged", "divergence_reasons": ["policy_hash_mismatch"]}}
    ) == ({"status": "diverged", "divergence_reasons": ["policy_hash_mismatch"]}, ["policy_hash_mismatch"])
    assert _comparison_summary(
        {"compare_remote_to_local": {"divergence_reasons": {"reason": "bad-shape"}}}
    ) == ({"divergence_reasons": {"reason": "bad-shape"}}, [])
