#!/usr/bin/env python3
"""Recover exact snapshot rows for a v1 archive binding from its freeze proof."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sentientos.federated_history_source_manifest import (  # noqa: E402
    digest_payload,
    source_id_for_origin,
    validate_federated_history_source_manifest,
)


def _read(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("federated_archive_upgrade_input_invalid")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("federated_archive_upgrade_object_required")
    return value


def _verify_digest(value: dict[str, Any], field: str, code: str) -> None:
    semantic = {key: item for key, item in value.items() if key != field}
    if value.get(field) != digest_payload(semantic):
        raise ValueError(code)


def _publish_new(path: Path, value: dict[str, Any]) -> None:
    target = path.absolute()
    if (target.exists() or target.is_symlink() or not target.parent.is_dir()
            or target.parent.is_symlink()):
        raise ValueError("federated_archive_upgrade_output_exists_or_invalid")
    payload = (json.dumps(value, ensure_ascii=False, sort_keys=True,
        indent=2, allow_nan=False) + "\n").encode("utf-8")
    descriptor = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        try:
            target.unlink()
        except OSError:
            pass
        raise


def upgrade(*, manifest: dict[str, Any], binding_v1: dict[str, Any],
        freeze_binding: dict[str, Any], audit: dict[str, Any],
        verification: dict[str, Any]) -> dict[str, Any]:
    records_by_source = validate_federated_history_source_manifest(manifest)
    _verify_digest(binding_v1, "binding_digest",
        "federated_archive_v1_binding_digest_invalid")
    _verify_digest(freeze_binding, "binding_digest",
        "federated_archive_freeze_binding_digest_invalid")
    _verify_digest(audit, "audit_digest",
        "federated_archive_anchor_audit_digest_invalid")
    _verify_digest(verification, "verification_digest",
        "federated_archive_anchor_verification_digest_invalid")
    if (binding_v1.get("schema_version") !=
            "sentientos.federated_archive_source_binding:v1"
            or freeze_binding.get("schema_version") !=
                "sentientos.federated_retrieval_corpus_freeze_binding:v1"
            or audit.get("schema_version") !=
                "sentientos.federated_experience_anchor_audit:v3"
            or verification.get("schema_version") !=
                "sentientos.federated_experience_anchor_verification:v3"
            or verification.get("status") != "verified"
            or binding_v1.get("federated_manifest_digest") !=
                manifest.get("federated_manifest_digest")
            or binding_v1.get("experience_anchor_audit_digest") !=
                audit.get("audit_digest")
            or binding_v1.get("experience_anchor_verification_digest") !=
                verification.get("verification_digest")
            or verification.get("audit_digest") != audit.get("audit_digest")
            or binding_v1.get("source_snapshot_count") !=
                freeze_binding.get("source_snapshot_count",
                    len(freeze_binding.get("source_snapshots", [])))
            or binding_v1.get("source_snapshot_digest") !=
                freeze_binding.get("source_snapshot_digest")
            or audit.get("source_snapshot_count") !=
                binding_v1.get("source_snapshot_count")
            or audit.get("source_snapshot_digest") !=
                binding_v1.get("source_snapshot_digest")
            or verification.get("source_snapshot_count") !=
                binding_v1.get("source_snapshot_count")
            or verification.get("source_snapshot_digest") !=
                binding_v1.get("source_snapshot_digest")
            or binding_v1.get("model_invoked") is not False
            or binding_v1.get("learning_established") is not False
            or binding_v1.get("authority") is not False):
        raise ValueError("federated_archive_upgrade_binding_chain_invalid")

    snapshots = freeze_binding.get("source_snapshots")
    if (not isinstance(snapshots, list) or not snapshots
            or digest_payload(snapshots) != binding_v1.get("source_snapshot_digest")
            or len(snapshots) != binding_v1.get("source_snapshot_count")):
        raise ValueError("federated_archive_upgrade_snapshot_inventory_invalid")
    snapshots_by_root: dict[str, list[dict[str, Any]]] = {}
    snapshot_keys: set[tuple[str, str]] = set()
    snapshot_fields = {"source_root_id", "cycle_id", "composition_state_sha256",
        "runtime_admission_ledger_sha256", "record_inventory_digest",
        "receipt_inventory_digest"}
    for row in snapshots:
        if (not isinstance(row, dict) or set(row) != snapshot_fields
                or not isinstance(row.get("source_root_id"), str)
                or re.fullmatch(r"[0-9a-f]{64}", row["source_root_id"]) is None
                or not isinstance(row.get("cycle_id"), str)
                or not row["cycle_id"]):
            raise ValueError("federated_archive_upgrade_snapshot_row_invalid")
        key = (row["source_root_id"], row["cycle_id"])
        if key in snapshot_keys:
            raise ValueError("federated_archive_upgrade_snapshot_duplicated")
        snapshot_keys.add(key)
        snapshots_by_root.setdefault(row["source_root_id"], []).append(row)

    audit_rows: dict[str, dict[str, str]] = {}
    for row in audit.get("records", []):
        if (not isinstance(row, dict) or not isinstance(row.get("record_id"), str)
                or not isinstance(row.get("record_digest"), str)
                or not isinstance(row.get("source_root_ids"), list)):
            raise ValueError("federated_archive_upgrade_audit_row_invalid")
        for root_id in row["source_root_ids"]:
            audit_rows.setdefault(root_id, {})[row["record_id"]] = row["record_digest"]

    old_sources = binding_v1.get("sources")
    manifest_sources = {row["source_id"]: row
        for row in manifest.get("sources", []) if isinstance(row, dict)}
    if (not isinstance(old_sources, list)
            or {row.get("source_id") for row in old_sources
                if isinstance(row, dict)} != set(records_by_source)
            or set(manifest_sources) != set(records_by_source)):
        raise ValueError("federated_archive_upgrade_source_partition_invalid")
    for row in old_sources:
        if not isinstance(row, dict):
            raise ValueError("federated_archive_upgrade_source_row_invalid")
        source_id, root_id = row.get("source_id"), row.get("source_root_id")
        expected_records = records_by_source.get(source_id)
        root_snapshots = snapshots_by_root.get(root_id, [])
        expected_origin_id = (source_id_for_origin(
            "sentientos-rootless-archive-source:v1:" + root_id)
            if isinstance(root_id, str) else None)
        record_rows = ([{"record_id": key, "record_digest": expected_records[key]}
            for key in sorted(expected_records)] if expected_records is not None else [])
        if (source_id != expected_origin_id or not root_snapshots
                or row.get("record_count") != len(record_rows)
                or row.get("record_inventory_digest") != digest_payload(record_rows)
                or row.get("source_snapshot_count") != len(root_snapshots)
                or row.get("source_snapshot_digest") != digest_payload(root_snapshots)
                or audit_rows.get(root_id) != dict(expected_records or {})):
            raise ValueError("federated_archive_upgrade_source_binding_mismatch")

    semantic = {key: value for key, value in binding_v1.items()
        if key not in {"binding_digest", "schema_version"}}
    semantic["schema_version"] = "sentientos.federated_archive_source_binding:v2"
    semantic["source_snapshots"] = snapshots
    return {**semantic, "binding_digest": digest_payload(semantic)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "binding-v1", "freeze-binding", "audit",
            "verification", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    upgraded = upgrade(manifest=_read(args.manifest),
        binding_v1=_read(args.binding_v1),
        freeze_binding=_read(args.freeze_binding), audit=_read(args.audit),
        verification=_read(args.verification))
    _publish_new(args.output, upgraded)
    print(json.dumps({"schema_version": upgraded["schema_version"],
        "binding_digest": upgraded["binding_digest"],
        "source_snapshot_count": upgraded["source_snapshot_count"],
        "authority": upgraded["authority"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, TypeError, ValueError) as exc:
        print(json.dumps({"status": "rejected", "reason": str(exc)},
            sort_keys=True), file=sys.stderr)
        raise SystemExit(2) from exc
