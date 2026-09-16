"""Deterministic, read-only architectural disposition inventory.

This module treats repository paths as data.  It never imports a classified target and
its results are not admission, capability, or execution decisions.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Mapping, Sequence, cast

Disposition = Literal[
    "canonical",
    "alternate_runtime",
    "compatibility_only",
    "superseded",
    "operator_legacy",
    "historical_experiment",
    "retired",
    "unknown_disposition",
]

DISPOSITIONS: tuple[str, ...] = (
    "alternate_runtime",
    "canonical",
    "compatibility_only",
    "historical_experiment",
    "operator_legacy",
    "retired",
    "superseded",
    "unknown_disposition",
)
SCHEMA = "sentientos.historical_surface_dispositions:v1"


@dataclass(frozen=True)
class SurfaceRecord:
    surface_id: str
    paths: tuple[str, ...]
    disposition: Disposition
    rationale: str
    owner: str | None
    successor: str | None
    references: tuple[str, ...]


@dataclass(frozen=True)
class Registry:
    schema: str
    inventory_scope: tuple[str, ...]
    records: tuple[SurfaceRecord, ...]


@dataclass(frozen=True)
class InventoryReport:
    schema: str
    valid: bool
    errors: tuple[str, ...]
    classified_surfaces: tuple[str, ...]
    unknown_surfaces: tuple[str, ...]
    unclassified_surfaces: tuple[str, ...]
    missing_targets: tuple[str, ...]
    stale_targets: tuple[str, ...]
    totals_by_disposition: tuple[tuple[str, int], ...]


def _string_tuple(value: object, field: str, errors: list[str]) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        errors.append(f"invalid_field:{field}:expected_nonempty_string_array")
        return ()
    return tuple(cast(list[str], value))


def _safe_path(value: str) -> bool:
    path = PurePosixPath(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts and "*" not in value and "?" not in value


def parse_registry(payload: Mapping[str, object]) -> tuple[Registry, tuple[str, ...]]:
    """Parse untrusted JSON-shaped metadata without consulting repository modules."""
    errors: list[str] = []
    schema = payload.get("schema")
    if schema != SCHEMA:
        errors.append(f"invalid_schema:{schema!r}")
    scope = _string_tuple(payload.get("inventory_scope"), "inventory_scope", errors)
    raw_records = payload.get("records")
    if not isinstance(raw_records, list):
        errors.append("invalid_field:records:expected_array")
        raw_records = []
    records: list[SurfaceRecord] = []
    for index, raw in enumerate(raw_records):
        prefix = f"record[{index}]"
        if not isinstance(raw, dict):
            errors.append(f"invalid_record:{index}:expected_object")
            continue
        surface_id = raw.get("id")
        disposition = raw.get("disposition")
        rationale = raw.get("rationale")
        owner = raw.get("owner")
        successor = raw.get("successor")
        if not isinstance(surface_id, str) or not surface_id:
            errors.append(f"invalid_field:{prefix}.id")
            surface_id = f"<invalid-{index}>"
        if disposition not in DISPOSITIONS:
            errors.append(f"invalid_disposition:{surface_id}:{disposition!r}")
            disposition = "unknown_disposition"
        if not isinstance(rationale, str) or not rationale.strip():
            errors.append(f"invalid_field:{prefix}.rationale")
            rationale = ""
        if owner is not None and (not isinstance(owner, str) or not owner):
            errors.append(f"invalid_field:{prefix}.owner")
            owner = None
        if successor is not None and (not isinstance(successor, str) or not successor):
            errors.append(f"invalid_field:{prefix}.successor")
            successor = None
        paths = _string_tuple(raw.get("paths"), f"{prefix}.paths", errors)
        references = _string_tuple(raw.get("references"), f"{prefix}.references", errors)
        records.append(SurfaceRecord(surface_id, paths, cast(Disposition, disposition), rationale, owner, successor, references))
    return Registry(str(schema), scope, tuple(records)), tuple(sorted(set(errors)))


def load_registry(path: Path) -> tuple[Registry, tuple[str, ...]]:
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return Registry("", (), ()), (f"registry_read_error:{type(exc).__name__}:{exc}",)
    if not isinstance(payload, dict):
        return Registry("", (), ()), ("invalid_registry_root:expected_object",)
    return parse_registry(payload)


def _overlaps(left: str, right: str) -> bool:
    a, b = PurePosixPath(left), PurePosixPath(right)
    return a == b or a in b.parents or b in a.parents


def build_inventory_report(registry: Registry, workspace_root: Path, parse_errors: Sequence[str] = ()) -> InventoryReport:
    errors = list(parse_errors)
    ids = Counter(record.surface_id for record in registry.records)
    errors.extend(f"duplicate_id:{surface_id}" for surface_id, count in ids.items() if count > 1)
    known_ids = set(ids)
    path_records: list[tuple[str, str]] = []
    for record in registry.records:
        if record.disposition == "superseded" and not record.successor:
            errors.append(f"successor_required:{record.surface_id}")
        if record.disposition != "superseded" and record.successor:
            errors.append(f"successor_for_non_superseded:{record.surface_id}")
        if record.successor and record.successor not in known_ids:
            errors.append(f"missing_successor:{record.surface_id}:{record.successor}")
        for value in (*record.paths, *record.references):
            if not _safe_path(value):
                errors.append(f"unsafe_path:{record.surface_id}:{value}")
        path_records.extend((path, record.surface_id) for path in record.paths)
    for index, (left_path, left_id) in enumerate(path_records):
        for right_path, right_id in path_records[index + 1 :]:
            if left_id != right_id and _overlaps(left_path, right_path):
                errors.append(f"overlapping_classification:{left_id}:{left_path}:{right_id}:{right_path}")

    successors = {record.surface_id: record.successor for record in registry.records if record.successor in known_ids}
    for origin in sorted(successors):
        seen: list[str] = []
        node: str | None = origin
        while node is not None and node in successors:
            if node in seen:
                cycle = seen[seen.index(node) :] + [node]
                errors.append(f"successor_cycle:{'->'.join(cycle)}")
                break
            seen.append(node)
            node = successors[node]

    classified_paths = {path for record in registry.records for path in record.paths}
    scope = set(registry.inventory_scope)
    missing = sorted(path for path in classified_paths if not (workspace_root / path).exists())
    stale = sorted(path for path in classified_paths if path not in scope)
    unclassified = sorted(path for path in scope if path not in classified_paths)
    errors.extend(f"missing_target:{path}" for path in missing)
    errors.extend(f"stale_target:{path}:outside_inventory_scope" for path in stale)
    errors.extend(f"unsafe_inventory_path:{path}" for path in scope if not _safe_path(path))
    unknown = sorted(path for record in registry.records if record.disposition == "unknown_disposition" for path in record.paths)
    totals = Counter(record.disposition for record in registry.records)
    return InventoryReport(
        schema=SCHEMA,
        valid=not errors,
        errors=tuple(sorted(set(errors))),
        classified_surfaces=tuple(sorted(classified_paths)),
        unknown_surfaces=tuple(unknown),
        unclassified_surfaces=tuple(unclassified),
        missing_targets=tuple(missing),
        stale_targets=tuple(stale),
        totals_by_disposition=tuple((name, totals[cast(Disposition, name)]) for name in DISPOSITIONS),
    )


def report_to_dict(report: InventoryReport) -> dict[str, object]:
    return {
        "schema": report.schema,
        "valid": report.valid,
        "errors": list(report.errors),
        "classified_surfaces": list(report.classified_surfaces),
        "unknown_surfaces": list(report.unknown_surfaces),
        "unclassified_surfaces": list(report.unclassified_surfaces),
        "missing_targets": list(report.missing_targets),
        "stale_targets": list(report.stale_targets),
        "totals_by_disposition": dict(report.totals_by_disposition),
        "authority_posture": "descriptive_evidence_only",
    }


def dumps_report(report: InventoryReport) -> str:
    return json.dumps(report_to_dict(report), indent=2, sort_keys=True) + "\n"
