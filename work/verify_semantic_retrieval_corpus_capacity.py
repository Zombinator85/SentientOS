"""Verify a persisted rootless-history capacity audit against its source tree."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sentientos.local_model_authority import digest_payload  # noqa: E402
from sentientos.rootless_experimental_local_model import (  # noqa: E402
    EXPERIMENT_ROOT,
    _no_symlink_path,
)
from sentientos.windows_handle_custody import (  # noqa: E402
    WindowsHandleCustodyError,
    read_explicit_file,
)

SCHEMA_PATH = (REPO_ROOT / "docs/development/"
    "semantic_retrieval_corpus_capacity_audit.schema.json")
QUERY_SCHEMA_PATH = (REPO_ROOT / "docs/development/"
    "semantic_history_retrieval_query_set.schema.json")
MAX_AUDIT_BYTES = 32 * 1024 * 1024
MAX_RECORD_BYTES = 16 * 1024 * 1024
RECORD_ID = re.compile(r"devrec-[0-9a-f]{24}\Z")
CYCLE_ID = re.compile(r"rootless-cognition-cycle-[0-9a-f]{20}\Z")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


def _read_json(path: Path, *, max_bytes: int) -> dict[str, Any]:
    try:
        raw = read_explicit_file(path, max_bytes=max_bytes)
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError,
            WindowsHandleCustodyError) as exc:
        raise ValueError("retrieval_capacity_json_invalid") from exc
    if not isinstance(value, dict):
        raise ValueError("retrieval_capacity_json_invalid")
    return value


def _family_ids(record: Mapping[str, Any]) -> list[str]:
    candidate = record.get("candidate")
    facts = candidate.get("selected_facts") if isinstance(candidate, Mapping) else None
    if not isinstance(facts, list):
        return []
    result: set[str] = set()
    for fact in facts:
        payload = fact.get("payload") if isinstance(fact, Mapping) else None
        descriptor = (payload.get("objective_task_descriptor")
            if isinstance(payload, Mapping) else None)
        family = (descriptor.get("task_family_id")
            if isinstance(descriptor, Mapping) else None)
        if isinstance(family, str):
            result.add(family)
    return sorted(result)


def _scan_source(root: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]],
        set[str], set[str]]:
    try:
        safe_root = _no_symlink_path(root).resolve(strict=True)
    except (OSError, ValueError, RuntimeError) as exc:
        raise ValueError("retrieval_capacity_source_root_invalid") from exc
    if not safe_root.is_dir():
        raise ValueError("retrieval_capacity_source_root_invalid")
    history_dirs = sorted(safe_root.glob(
        "*/resident-cognition/history"), key=lambda path: path.as_posix())
    for history in history_dirs:
        cycle_root = history.parent.parent
        if (CYCLE_ID.fullmatch(cycle_root.name) is None
                or any(path.is_symlink() for path in (
                    cycle_root, history.parent, history))):
            raise ValueError("retrieval_capacity_history_path_invalid")
    rows: list[dict[str, Any]] = []
    unique: dict[str, dict[str, Any]] = {}
    roots_with_records: set[str] = set()
    for history in history_dirs:
        records_root = history / "records"
        if records_root.is_symlink():
            raise ValueError("retrieval_capacity_records_path_invalid")
        if not records_root.exists():
            continue
        if not records_root.is_dir():
            raise ValueError("retrieval_capacity_records_path_invalid")
        record_paths = sorted(records_root.glob("devrec-*.json"),
            key=lambda path: path.name)
        if not record_paths:
            continue
        cycle_id = history.parent.parent.name
        roots_with_records.add(cycle_id)
        for path in record_paths:
            if (path.is_symlink() or RECORD_ID.fullmatch(path.stem) is None
                    or any(parent.is_symlink() for parent in (
                        path.parent, path.parent.parent, path.parent.parent.parent,
                        path.parent.parent.parent.parent))):
                raise ValueError("retrieval_capacity_record_path_invalid")
            try:
                raw = read_explicit_file(path, max_bytes=MAX_RECORD_BYTES)
                record = json.loads(raw)
            except (OSError, UnicodeError, json.JSONDecodeError,
                    WindowsHandleCustodyError) as exc:
                raise ValueError("retrieval_capacity_record_unreadable") from exc
            if not isinstance(record, Mapping):
                raise ValueError("retrieval_capacity_record_invalid")
            record_id = record.get("record_id")
            record_digest = record.get("record_digest")
            if (record_id != path.stem or RECORD_ID.fullmatch(record_id or "") is None
                    or not isinstance(record_digest, str)
                    or DIGEST.fullmatch(record_digest) is None):
                raise ValueError("retrieval_capacity_record_identity_invalid")
            families = _family_ids(record)
            row = {
                "cycle_id": cycle_id,
                "path": path.relative_to(safe_root).as_posix(),
                "record_id": record_id,
                "record_digest": record_digest,
                "source_file_sha256": hashlib.sha256(raw).hexdigest(),
                "task_family_ids": families,
            }
            rows.append(row)
            existing = unique.get(record_id)
            identity = {"record_digest": record_digest,
                "task_family_ids": families}
            if existing is not None and existing != identity:
                raise ValueError("retrieval_capacity_record_identity_conflict")
            unique[record_id] = identity
    return rows, unique, {path.parent.parent.name for path in history_dirs}, roots_with_records


def _validate_schema(value: Mapping[str, Any], schema_path: Path) -> None:
    schema = _read_json(schema_path, max_bytes=MAX_AUDIT_BYTES)
    try:
        import jsonschema
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(schema).validate(dict(value))
    except ImportError as exc:
        raise ValueError("retrieval_capacity_jsonschema_unavailable") from exc
    except Exception as exc:
        raise ValueError("retrieval_capacity_schema_invalid") from exc


def verify_audit(*, audit_path: Path, schema_path: Path = SCHEMA_PATH,
        query_schema_path: Path = QUERY_SCHEMA_PATH) -> dict[str, Any]:
    audit = _read_json(Path(audit_path), max_bytes=MAX_AUDIT_BYTES)
    _validate_schema(audit, Path(schema_path))
    semantic = {key: value for key, value in audit.items() if key != "audit_digest"}
    if audit.get("audit_digest") != "sha256:" + digest_payload(semantic):
        raise ValueError("retrieval_capacity_audit_digest_mismatch")
    actual_root = Path(EXPERIMENT_ROOT) / "developmental-cognition-cycles"
    rows1, unique1, dirs1, populated1 = _scan_source(actual_root)
    rows2, unique2, dirs2, populated2 = _scan_source(actual_root)
    if (rows1, unique1, dirs1, populated1) != (rows2, unique2, dirs2, populated2):
        raise ValueError("retrieval_capacity_source_changed_during_scan")
    if (audit.get("stable_double_scan") is not True
            or audit.get("atomic_snapshot") is not False
            or audit.get("history_directory_count") != len(dirs1)
            or audit.get("history_roots_with_records") != len(populated1)
            or audit.get("record_file_count") != len(rows1)
            or audit.get("duplicate_snapshot_copy_count") != len(rows1) - len(unique1)
            or audit.get("unique_record_count") != len(unique1)
            or audit.get("unique_record_digest_count") != len({
                row["record_digest"] for row in unique1.values()})
            or audit.get("record_identity_conflict_count") != 0
            or audit.get("source_file_inventory") != rows1
            or audit.get("source_inventory_digest") !=
                "sha256:" + digest_payload(rows1)):
        raise ValueError("retrieval_capacity_source_inventory_mismatch")
    unique_records = [{"record_id": record_id, **value}
        for record_id, value in sorted(unique1.items())]
    family_counts = Counter(family for value in unique1.values()
        for family in value["task_family_ids"])
    family_counts = dict(sorted(family_counts.items()))
    if (audit.get("unique_records") != unique_records
            or audit.get("unique_records_by_task_family") != family_counts
            or audit.get("unique_records_without_task_family") != sum(
                not value["task_family_ids"] for value in unique1.values())):
        raise ValueError("retrieval_capacity_unique_record_summary_mismatch")
    query_schema = _read_json(Path(query_schema_path), max_bytes=MAX_AUDIT_BYTES)
    source_ids = query_schema.get("properties", {}).get(
        "source_experience_record_ids", {})
    queries = query_schema.get("properties", {}).get("questions", {})
    strata = query_schema.get("properties", {}).get("strata", {})
    minimum = min(queries.get("minItems", 0), strata.get("minItems", 0),
        source_ids.get("minItems", 0))
    if (source_ids.get("uniqueItems") is not True or type(minimum) is not int
            or minimum < 1
            or audit.get("phase_a_min_independent_queries") != minimum
            or audit.get("independent_source_reuse_permitted") is not False
            or audit.get("distinct_experience_shortfall") != max(
                0, minimum - len(unique1))):
        raise ValueError("retrieval_capacity_query_gate_binding_invalid")
    return {
        "status": "verified",
        "audit_digest": audit["audit_digest"],
        "source_inventory_digest": audit["source_inventory_digest"],
        "history_directory_count": len(dirs1),
        "history_roots_with_records": len(populated1),
        "record_file_count": len(rows1),
        "unique_record_count": len(unique1),
        "phase_a_min_unique_source_records": minimum,
        "distinct_experience_shortfall": max(0, minimum - len(unique1)),
        "inference_performed": False,
        "learning_established": False,
        "authority": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--schema", type=Path, default=SCHEMA_PATH)
    parser.add_argument("--query-schema", type=Path, default=QUERY_SCHEMA_PATH)
    args = parser.parse_args()
    print(json.dumps(verify_audit(audit_path=args.audit,
        schema_path=args.schema, query_schema_path=args.query_schema),
        sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
