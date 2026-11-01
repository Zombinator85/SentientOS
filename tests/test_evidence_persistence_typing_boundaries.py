from __future__ import annotations

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.integrity_snapshot import _match_key, _string_values


def test_integrity_reason_rows_ignore_non_string_json_values() -> None:
    assert _string_values(["attestation_snapshot_tip_mismatch", None, 7]) == [
        "attestation_snapshot_tip_mismatch"
    ]
    assert _string_values({"unexpected": "object"}) == []


def test_integrity_snapshot_mapping_comparison_keeps_canonical_json_behavior() -> None:
    assert _match_key({"digest": {"b": 2, "a": 1}}, {"digest": {"a": 1, "b": 2}}, "digest")
    assert not _match_key({"digest": {"a": 1}}, {"digest": {"a": 2}}, "digest")
