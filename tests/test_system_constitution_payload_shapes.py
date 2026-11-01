from __future__ import annotations

import pytest

from sentientos.attestation import read_json
from sentientos.system_constitution import _peer_rollup, write_constitution_artifacts


pytestmark = pytest.mark.no_legacy_skip


def test_peer_rollup_uses_peer_length_when_count_is_malformed() -> None:
    result = _peer_rollup(
        {
            "peer_count": "many",
            "peer_states": [{"peer_id": "peer-a", "trust_reasons": "not-a-list"}],
        }
    )

    assert result["peer_count"] == 1
    assert result["peers"] == [
        {
            "peer_id": "peer-a",
            "trust_state": None,
            "trust_reasons": [],
            "reconciliation_needed": False,
        }
    ]


def test_constitution_summary_bounds_only_actual_lists(tmp_path) -> None:
    write_constitution_artifacts(
        tmp_path,
        payload={
            "constitution_version": 1,
            "constitution_state": "degraded",
            "constitutional_digest": "digest",
            "runtime_posture": "malformed",
            "degraded_modes": "not-a-list",
            "missing_required_artifacts": None,
            "restoration_hints": {"hint": "not iterable"},
            "exit_code": "invalid",
        },
    )

    summary = read_json(tmp_path / "glow/constitution/constitution_summary.json")
    assert summary["effective_posture"] is None
    assert summary["governor_mode"] is None
    assert summary["degraded_modes"] == []
    assert summary["missing_required_artifacts"] == []
    assert summary["restoration_hints"] == []
