"""Create or verify a content-free inventory across explicit rootless-history roots."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sentientos.local_model_authority import digest_payload  # noqa: E402
from work.verify_semantic_retrieval_corpus_capacity import (  # noqa: E402
    MAX_AUDIT_BYTES,
    QUERY_SCHEMA_PATH,
    _read_json,
    _no_symlink_path,
    _scan_source,
)

SCHEMA_PATH = (REPO_ROOT / "docs/development/"
    "semantic_retrieval_multi_root_capacity_audit.schema.json")
MIN_SOURCE_ROOTS = 2


def _validated_roots(values: Sequence[Path]) -> list[Path]:
    if len(values) < MIN_SOURCE_ROOTS:
        raise ValueError("retrieval_multi_root_source_count_invalid")
    roots: list[Path] = []
    for value in values:
        try:
            candidate = _no_symlink_path(value.expanduser())
            root = candidate.resolve(strict=True)
        except (OSError, RuntimeError, ValueError) as exc:
            raise ValueError("retrieval_multi_root_source_invalid") from exc
        if not root.is_dir():
            raise ValueError("retrieval_multi_root_source_invalid")
        roots.append(root)
    if len(set(roots)) != len(roots):
        raise ValueError("retrieval_multi_root_source_duplicated")
    return sorted(roots, key=lambda item: item.as_posix())


def _root_id(root: Path) -> str:
    return hashlib.sha256(root.as_posix().encode("utf-8")).hexdigest()


def _scan_roots(roots: Sequence[Path]) -> tuple[
        list[dict[str, Any]], dict[str, dict[str, Any]],
        list[dict[str, Any]], int, int]:
    rows: list[dict[str, Any]] = []
    unique: dict[str, dict[str, Any]] = {}
    root_summaries: list[dict[str, Any]] = []
    history_directory_count = 0
    populated_history_directory_count = 0
    for root in roots:
        first = _scan_source(root)
        second = _scan_source(root)
        if first != second:
            raise ValueError("retrieval_multi_root_source_changed_during_scan")
        root_rows, root_unique, history_dirs, populated_dirs = first
        root_id = _root_id(root)
        for row in root_rows:
            rows.append({"source_root_id": root_id, **row})
        for record_id, identity in root_unique.items():
            prior = unique.get(record_id)
            if prior is not None and prior != identity:
                raise ValueError("retrieval_multi_root_record_identity_conflict")
            unique[record_id] = identity
        history_directory_count += len(history_dirs)
        populated_history_directory_count += len(populated_dirs)
        root_summaries.append({
            "source_root_id": root_id,
            "history_directory_count": len(history_dirs),
            "history_roots_with_records": len(populated_dirs),
            "record_file_count": len(root_rows),
            "unique_record_count": len(root_unique),
        })
    rows.sort(key=lambda row: (row["source_root_id"], row["path"]))
    root_summaries.sort(key=lambda row: row["source_root_id"])
    return (rows, unique, root_summaries, history_directory_count,
        populated_history_directory_count)


def _minimum_query_count(query_schema_path: Path) -> int:
    schema = _read_json(query_schema_path, max_bytes=MAX_AUDIT_BYTES)
    properties = schema.get("properties", {})
    source_ids = properties.get("source_experience_record_ids", {})
    questions = properties.get("questions", {})
    strata = properties.get("strata", {})
    minimum = min(questions.get("minItems", 0), strata.get("minItems", 0),
        source_ids.get("minItems", 0))
    if (source_ids.get("uniqueItems") is not True or type(minimum) is not int
            or minimum < 1):
        raise ValueError("retrieval_multi_root_query_gate_invalid")
    return minimum


def build_audit(*, source_roots: Sequence[Path],
        query_schema_path: Path = QUERY_SCHEMA_PATH) -> dict[str, Any]:
    roots = _validated_roots(source_roots)
    rows, unique, root_summaries, history_dirs, populated_dirs = _scan_roots(roots)
    unique_records = [{"record_id": record_id, **identity}
        for record_id, identity in sorted(unique.items())]
    family_counts = Counter(family for identity in unique.values()
        for family in identity["task_family_ids"])
    family_counts = dict(sorted(family_counts.items()))
    minimum = _minimum_query_count(query_schema_path)
    semantic = {
        "schema_version": "sentientos.semantic_retrieval_multi_root_capacity_audit:v1",
        "supersedes": "artifacts/experiments/semantic-retrieval-capacity-20261123/corpus_capacity_audit_v3.json",
        "scope": "structural_record_inventory_upper_bound_only",
        "source_root_count": len(roots),
        "source_roots": root_summaries,
        "atomic_snapshot": False,
        "stable_double_scan": True,
        "history_directory_count": history_dirs,
        "history_roots_with_records": populated_dirs,
        "record_file_count": len(rows),
        "duplicate_snapshot_copy_count": len(rows) - len(unique),
        "unique_record_count": len(unique),
        "unique_record_digest_count": len({
            identity["record_digest"] for identity in unique.values()}),
        "record_identity_conflict_count": 0,
        "unique_records_by_task_family": family_counts,
        "unique_records_without_task_family": sum(
            not identity["task_family_ids"] for identity in unique.values()),
        "phase_a_min_independent_queries": minimum,
        "independent_source_reuse_permitted": False,
        "distinct_experience_shortfall": max(0, minimum - len(unique)),
        "capacity_is_upper_bound": True,
        "owner_admission_verified": False,
        "phase_a_eligible_record_count": None,
        "unique_records": unique_records,
        "source_file_inventory": rows,
        "source_inventory_digest": "sha256:" + digest_payload(rows),
        "inference_performed": False,
        "learning_established": False,
        "authority": False,
    }
    return {**semantic, "audit_digest": "sha256:" + digest_payload(semantic)}


def _validate_schema(value: Mapping[str, Any], schema_path: Path) -> None:
    schema = _read_json(schema_path, max_bytes=MAX_AUDIT_BYTES)
    try:
        import jsonschema
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(schema).validate(dict(value))
    except ImportError as exc:
        raise ValueError("retrieval_multi_root_jsonschema_unavailable") from exc
    except Exception as exc:
        raise ValueError("retrieval_multi_root_schema_invalid") from exc


def verify_audit(*, audit_path: Path, source_roots: Sequence[Path],
        schema_path: Path = SCHEMA_PATH,
        query_schema_path: Path = QUERY_SCHEMA_PATH) -> dict[str, Any]:
    audit = _read_json(audit_path, max_bytes=MAX_AUDIT_BYTES)
    _validate_schema(audit, schema_path)
    semantic = {key: value for key, value in audit.items() if key != "audit_digest"}
    if audit.get("audit_digest") != "sha256:" + digest_payload(semantic):
        raise ValueError("retrieval_multi_root_audit_digest_mismatch")
    expected = build_audit(source_roots=source_roots,
        query_schema_path=query_schema_path)
    if audit != expected:
        raise ValueError("retrieval_multi_root_source_inventory_mismatch")
    return {
        "status": "verified",
        "audit_digest": audit["audit_digest"],
        "source_inventory_digest": audit["source_inventory_digest"],
        "source_root_count": audit["source_root_count"],
        "history_directory_count": audit["history_directory_count"],
        "record_file_count": audit["record_file_count"],
        "unique_record_count": audit["unique_record_count"],
        "unique_record_digest_count": audit["unique_record_digest_count"],
        "task_family_attributed_count": audit["unique_record_count"] -
            audit["unique_records_without_task_family"],
        "phase_a_min_unique_source_records": audit[
            "phase_a_min_independent_queries"],
        "distinct_experience_shortfall": audit["distinct_experience_shortfall"],
        "inference_performed": False,
        "learning_established": False,
        "authority": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    verify = commands.add_parser("verify")
    for command in (create, verify):
        command.add_argument("--source-root", type=Path, action="append",
            required=True, help="canonical-cycle root; repeat for each workspace")
        command.add_argument("--query-schema", type=Path,
            default=QUERY_SCHEMA_PATH)
    create.add_argument("--output", type=Path, required=True)
    verify.add_argument("--audit", type=Path, required=True)
    verify.add_argument("--schema", type=Path, default=SCHEMA_PATH)
    args = parser.parse_args()
    if args.command == "create":
        value = build_audit(source_roots=args.source_root,
            query_schema_path=args.query_schema)
        _validate_schema(value, SCHEMA_PATH)
        if (args.output.exists() or args.output.is_symlink()
                or args.output.parent.is_symlink()
                or not args.output.parent.is_dir()):
            raise SystemExit("retrieval_multi_root_output_exists")
        try:
            with args.output.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(value, sort_keys=True, indent=2) + "\n")
        except FileExistsError as exc:
            raise SystemExit("retrieval_multi_root_output_exists") from exc
        print(json.dumps({"status": "created", "audit_digest": value[
            "audit_digest"], "source_root_count": value["source_root_count"],
            "unique_record_count": value["unique_record_count"],
            "distinct_experience_shortfall": value[
                "distinct_experience_shortfall"],
            "inference_performed": False, "authority": False}, sort_keys=True))
        return 0
    print(json.dumps(verify_audit(audit_path=args.audit,
        source_roots=args.source_root, schema_path=args.schema,
        query_schema_path=args.query_schema), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
