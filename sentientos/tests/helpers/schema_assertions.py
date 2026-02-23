from __future__ import annotations

from typing import Any

from sentientos.schema_registry import LATEST_VERSIONS, normalize


def assert_normalizes(schema_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    normalized, warnings = normalize(payload, schema_name)
    assert normalized["schema_version"] == LATEST_VERSIONS[schema_name]
    assert isinstance(warnings, list)
    return normalized


def forge_index_v14_fixture() -> dict[str, Any]:
    return {"schema_version": 14, "generated_at": "2026-01-01T00:00:00Z", "legacy": True}


def forge_index_v15_fixture() -> dict[str, Any]:
    return {"schema_version": 15, "generated_at": "2026-01-01T00:00:00Z", "quarantine_active": True}


def forge_index_v16_fixture() -> dict[str, Any]:
    return {"schema_version": 16, "generated_at": "2026-01-01T00:00:00Z"}


def forge_index_v23_fixture() -> dict[str, Any]:
    return {"schema_version": 23, "generated_at": "2026-01-01T00:00:00Z"}
