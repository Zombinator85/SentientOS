#!/usr/bin/env python3
"""Freeze a source-qualified manifest from verified rootless history archives.

This path uses persisted, admission-verified developmental-history roots. It
does not require a live resident owner or serving configuration and never
invokes a model. Its source IDs are stable opaque IDs derived from source-root
identities; a separate binding artifact connects those IDs to the verified
archive snapshots used to construct the manifest.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sentientos.federated_developmental_history import (
    FederatedDevelopmentalHistoryReadView,
)
from sentientos.federated_history_source_manifest import (
    digest_payload,
    make_federated_history_source_manifest,
    source_id_for_origin,
    validate_federated_history_source_manifest,
)
from sentientos.semantic_history_retrieval_evaluation import (
    make_retrieval_corpus_manifest,
)
from work.audit_federated_experience_anchors import (
    _expand_cycle_roots,
    verify_report,
)


def _read_object(path: Path, *, code: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError(code + "_file_invalid")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(code + "_object_required")
    return value


def _write_new(path: Path, value: dict[str, Any]) -> None:
    target = path.absolute()
    if (target.exists() or target.is_symlink()
            or not target.parent.is_dir() or target.parent.is_symlink()):
        raise ValueError("federated_archive_output_exists_or_invalid")
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


def freeze(*, cycle_roots: list[Path], experiment_root: Path,
        freeze_export: Path, anchor_audit_path: Path,
        manifest_output: Path, binding_output: Path
        ) -> tuple[dict[str, Any], dict[str, Any]]:
    audit = _read_object(anchor_audit_path,
        code="federated_archive_anchor_audit")
    if audit.get("schema_version") != "sentientos.federated_experience_anchor_audit:v3":
        raise ValueError("federated_archive_anchor_audit_schema_invalid")

    # Verify the source-backed audit before using its record-to-root claims.
    verification = verify_report(cycle_roots=cycle_roots,
        experiment_root=experiment_root, freeze_export=freeze_export,
        audit_path=anchor_audit_path)
    view = FederatedDevelopmentalHistoryReadView(cycle_roots)
    snapshots = list(view.source_snapshots)
    if (len(snapshots) != audit.get("source_snapshot_count")
            or digest_payload(snapshots) != audit.get("source_snapshot_digest")):
        raise ValueError("federated_archive_snapshot_binding_mismatch")

    audit_rows = {(row.get("record_id"), row.get("record_digest")):
        row.get("source_root_ids") for row in audit.get("records", [])
        if isinstance(row, dict)}
    source_records: dict[str, dict[str, str]] = {}
    for record, _receipt in view.inspect_completed_records():
        key = (record.record_id, record.record_digest)
        root_ids = audit_rows.get(key)
        if not isinstance(root_ids, list) or not root_ids:
            raise ValueError("federated_archive_record_anchor_missing")
        view_root_ids = view.source_provenance[record.record_id]["source_root_ids"]
        if sorted(root_ids) != sorted(view_root_ids):
            raise ValueError("federated_archive_record_roots_mismatch")
        for root_id in root_ids:
            source_records.setdefault(root_id, {})[record.record_id] = record.record_digest

    snapshot_groups: dict[str, list[dict[str, Any]]] = {}
    for row in snapshots:
        snapshot_groups.setdefault(row["source_root_id"], []).append(row)
    sources = []
    binding_rows = []
    for root_id in sorted(source_records):
        records = source_records[root_id]
        source_snapshots = snapshot_groups.get(root_id, [])
        if not source_snapshots:
            raise ValueError("federated_archive_root_snapshot_missing")
        record_rows = [{"record_id": record_id,
            "record_digest": records[record_id]}
            for record_id in sorted(records)]
        history_state_digest = digest_payload({
            "schema_version": "sentientos.federated_archive_source_state:v1",
            "source_root_id": root_id,
            "records": record_rows,
            "source_snapshots": source_snapshots})
        corpus = make_retrieval_corpus_manifest(
            history_state_digest=history_state_digest, records=record_rows)
        origin_key = "sentientos-rootless-archive-source:v1:" + root_id
        source_id = source_id_for_origin(origin_key)
        sources.append({"origin_key": origin_key,
            "corpus_manifest": corpus})
        binding_rows.append({"source_id": source_id,
            "source_root_id": root_id,
            "record_count": len(records),
            "record_inventory_digest": digest_payload(record_rows),
            "source_snapshot_count": len(source_snapshots),
            "source_snapshot_digest": digest_payload(source_snapshots)})

    manifest = make_federated_history_source_manifest(sources=sources)
    validated_records = validate_federated_history_source_manifest(manifest)
    if {row["source_id"] for row in binding_rows} != set(validated_records):
        raise ValueError("federated_archive_source_partition_mismatch")
    semantic = {"schema_version": "sentientos.federated_archive_source_binding:v2",
        "federated_manifest_digest": manifest["federated_manifest_digest"],
        "experience_anchor_audit_digest": audit["audit_digest"],
        "experience_anchor_verification_digest":
            verification["verification_digest"],
        "source_snapshot_count": len(snapshots),
        "source_snapshot_digest": digest_payload(snapshots),
        "source_snapshots": snapshots,
        "sources": sorted(binding_rows, key=lambda row: row["source_id"]),
        "model_invoked": False, "learning_established": False,
        "authority": False}
    binding = {**semantic, "binding_digest": digest_payload(semantic)}
    view.verify_sources_unchanged()

    manifest_target, binding_target = manifest_output.absolute(), binding_output.absolute()
    for target in (manifest_target, binding_target):
        if (target.exists() or target.is_symlink()
                or not target.parent.is_dir() or target.parent.is_symlink()):
            raise ValueError("federated_archive_output_exists_or_invalid")
    _write_new(manifest_target, manifest)
    try:
        _write_new(binding_target, binding)
    except Exception:
        try:
            manifest_target.unlink()
        except OSError:
            pass
        raise
    return manifest, binding


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycle-root", type=Path, action="append")
    parser.add_argument("--cycle-parent", type=Path, action="append")
    parser.add_argument("--experiment-root", type=Path, required=True)
    parser.add_argument("--freeze-export", type=Path, required=True)
    parser.add_argument("--experience-anchor-audit", type=Path, required=True)
    parser.add_argument("--manifest-output", type=Path, required=True)
    parser.add_argument("--binding-output", type=Path, required=True)
    args = parser.parse_args(argv)
    roots = _expand_cycle_roots(args.cycle_root, args.cycle_parent)
    manifest, binding = freeze(cycle_roots=roots,
        experiment_root=args.experiment_root,
        freeze_export=args.freeze_export,
        anchor_audit_path=args.experience_anchor_audit,
        manifest_output=args.manifest_output,
        binding_output=args.binding_output)
    print(json.dumps({"federated_manifest_digest":
        manifest["federated_manifest_digest"],
        "binding_digest": binding["binding_digest"],
        "source_count": len(manifest["sources"]),
        "record_count": sum(len(row["records"]) for row in manifest["sources"]),
        "source_snapshot_count": binding["source_snapshot_count"],
        "model_invoked": False, "learning_established": False,
        "authority": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, TypeError, ValueError) as exc:
        print(json.dumps({"status": "rejected", "reason": str(exc)},
            sort_keys=True), file=sys.stderr)
        raise SystemExit(2) from exc
