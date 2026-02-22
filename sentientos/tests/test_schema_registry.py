from __future__ import annotations

from sentientos.schema_registry import SchemaName, normalize
from sentientos.tests.helpers.schema_assertions import (
    assert_normalizes,
    forge_index_v14_fixture,
)


def test_normalize_forge_index_from_v14() -> None:
    normalized = assert_normalizes(SchemaName.FORGE_INDEX, forge_index_v14_fixture())
    assert "quarantine_active" in normalized
    assert "last_remediation_pack_id" in normalized


def test_normalize_remediation_pack_from_latest() -> None:
    payload = {"schema_version": 1, "pack_id": "pack_1", "steps": [], "status": "proposed", "custom": "x"}
    normalized, _warnings = normalize(payload, SchemaName.REMEDIATION_PACK)
    assert normalized["custom"] == "x"


def test_normalize_remediation_run_from_latest() -> None:
    payload = {"schema_version": 1, "run_id": "run_1", "pack_id": "pack_1", "status": "completed", "steps": []}
    normalized = assert_normalizes(SchemaName.REMEDIATION_RUN, payload)
    assert normalized["status"] == "completed"


def test_normalize_governance_trace_from_latest() -> None:
    payload = {"schema_version": 1, "trace_id": "trace_1", "created_at": "2026-01-01T00:00:00Z", "final_decision": "hold", "foo": "bar"}
    normalized, _warnings = normalize(payload, SchemaName.GOVERNANCE_TRACE)
    assert normalized["foo"] == "bar"
