from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from typing import Any


class SchemaName:
    FORGE_INDEX = "forge_index"
    FORGE_REPORT = "forge_report"
    GOVERNANCE_TRACE = "governance_trace"
    INCIDENT = "incident"
    REMEDIATION_PACK = "remediation_pack"
    REMEDIATION_RUN = "remediation_run"
    ORCHESTRATOR_TICK = "orchestrator_tick"
    RISK_BUDGET = "risk_budget"
    INTEGRITY_SNAPSHOT = "integrity_snapshot"
    RECEIPT = "receipt"
    ANCHOR = "anchor"
    AUDIT_CHAIN_REPORT = "audit_chain_report"


AdapterFn = Callable[[dict[str, Any]], dict[str, Any]]

LATEST_VERSIONS: dict[str, int] = {
    SchemaName.FORGE_INDEX: 17,
    SchemaName.FORGE_REPORT: 1,
    SchemaName.GOVERNANCE_TRACE: 1,
    SchemaName.INCIDENT: 1,
    SchemaName.REMEDIATION_PACK: 1,
    SchemaName.REMEDIATION_RUN: 1,
    SchemaName.ORCHESTRATOR_TICK: 1,
    SchemaName.RISK_BUDGET: 1,
    SchemaName.INTEGRITY_SNAPSHOT: 1,
    SchemaName.RECEIPT: 2,
    SchemaName.ANCHOR: 1,
    SchemaName.AUDIT_CHAIN_REPORT: 1,
}

MIN_SUPPORTED_VERSIONS: dict[str, int] = {
    SchemaName.FORGE_INDEX: 14,
    SchemaName.FORGE_REPORT: 1,
    SchemaName.GOVERNANCE_TRACE: 1,
    SchemaName.INCIDENT: 1,
    SchemaName.REMEDIATION_PACK: 1,
    SchemaName.REMEDIATION_RUN: 1,
    SchemaName.ORCHESTRATOR_TICK: 1,
    SchemaName.RISK_BUDGET: 1,
    SchemaName.INTEGRITY_SNAPSHOT: 1,
    SchemaName.RECEIPT: 1,
    SchemaName.ANCHOR: 1,
    SchemaName.AUDIT_CHAIN_REPORT: 1,
}


class SchemaCompatibilityError(ValueError):
    pass


def _forge_index_v14_to_v15(payload: dict[str, Any]) -> dict[str, Any]:
    upgraded = deepcopy(payload)
    upgraded["schema_version"] = 15
    upgraded.setdefault("quarantine_active", False)
    upgraded.setdefault("quarantine_last_incident_id", None)
    upgraded.setdefault("last_incident_summary", {})
    return upgraded


def _forge_index_v15_to_v16(payload: dict[str, Any]) -> dict[str, Any]:
    upgraded = deepcopy(payload)
    upgraded["schema_version"] = 16
    upgraded.setdefault("last_remediation_pack_id", None)
    upgraded.setdefault("last_remediation_pack_status", "unknown")
    upgraded.setdefault("auto_remediation_status", "unknown")
    return upgraded


def _forge_index_v16_to_v17(payload: dict[str, Any]) -> dict[str, Any]:
    upgraded = deepcopy(payload)
    upgraded["schema_version"] = 17
    upgraded.setdefault("artifact_catalog_status", "unknown")
    upgraded.setdefault("artifact_catalog_last_entry_at", None)
    upgraded.setdefault("artifact_catalog_size_estimate", 0)
    return upgraded


def _receipt_v1_to_v2(payload: dict[str, Any]) -> dict[str, Any]:
    upgraded = deepcopy(payload)
    upgraded["schema_version"] = 2
    upgraded.setdefault("prev_receipt_hash", None)
    return upgraded


ADAPTERS: dict[tuple[str, int], AdapterFn] = {
    (SchemaName.FORGE_INDEX, 14): _forge_index_v14_to_v15,
    (SchemaName.FORGE_INDEX, 15): _forge_index_v15_to_v16,
    (SchemaName.FORGE_INDEX, 16): _forge_index_v16_to_v17,
    (SchemaName.RECEIPT, 1): _receipt_v1_to_v2,
}


_REQUIRED_KEYS: dict[str, set[str]] = {
    SchemaName.FORGE_INDEX: {"schema_version", "generated_at"},
    SchemaName.GOVERNANCE_TRACE: {"schema_version", "trace_id", "created_at", "final_decision"},
    SchemaName.INCIDENT: {"schema_version", "incident_id", "created_at", "triggers"},
    SchemaName.REMEDIATION_PACK: {"schema_version", "pack_id", "steps", "status"},
    SchemaName.REMEDIATION_RUN: {"schema_version", "run_id", "pack_id", "status"},
    SchemaName.ORCHESTRATOR_TICK: {"schema_version", "generated_at", "status"},
    SchemaName.RISK_BUDGET: {"schema_version", "created_at", "operating_mode"},
    SchemaName.INTEGRITY_SNAPSHOT: {"schema_version", "created_at", "node_id"},
}


def latest_version(schema_name: str) -> int:
    return LATEST_VERSIONS[schema_name]


def min_supported_version(schema_name: str) -> int:
    return MIN_SUPPORTED_VERSIONS[schema_name]


def normalize(payload: Mapping[str, Any], schema_name: str) -> tuple[dict[str, Any], list[str]]:
    if schema_name not in LATEST_VERSIONS:
        raise SchemaCompatibilityError(f"unknown_schema:{schema_name}")
    normalized = dict(deepcopy(dict(payload)))
    warnings: list[str] = []
    schema_value = normalized.get("schema_version", 1)
    if not isinstance(schema_value, int):
        raise SchemaCompatibilityError(f"schema_version_invalid:{schema_name}:{schema_value}")

    minimum = min_supported_version(schema_name)
    latest = latest_version(schema_name)
    if schema_value < minimum:
        raise SchemaCompatibilityError(f"schema_too_old:{schema_name}:{schema_value}")
    if schema_value > latest:
        raise SchemaCompatibilityError(f"schema_too_new:{schema_name}:{schema_value}")

    while schema_value < latest:
        adapter = ADAPTERS.get((schema_name, schema_value))
        if adapter is None:
            raise SchemaCompatibilityError(f"schema_adapter_missing:{schema_name}:{schema_value}")
        normalized = adapter(normalized)
        schema_value = normalized.get("schema_version") if isinstance(normalized.get("schema_version"), int) else schema_value + 1

    required = _REQUIRED_KEYS.get(schema_name, set())
    missing = sorted(key for key in required if key not in normalized)
    for key in missing:
        warnings.append(f"missing_required_key:{schema_name}:{key}")

    return normalized, warnings


def validate_schema(payload: Mapping[str, Any], schema_name: str) -> tuple[dict[str, Any], list[str]]:
    return normalize(payload, schema_name)


__all__ = [
    "ADAPTERS",
    "LATEST_VERSIONS",
    "MIN_SUPPORTED_VERSIONS",
    "SchemaCompatibilityError",
    "SchemaName",
    "latest_version",
    "min_supported_version",
    "normalize",
    "validate_schema",
]
