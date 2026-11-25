"""Verify exact planned-transfer input reuse against a frozen history boundary.

This is a read-only CPU audit. It binds the owner-preflight report, recomputes
its referenced history boundary, and checks the actual binder-selected records
using the resident owner's task-family example projection. It never invokes a
model or writes developmental history.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any


def _read_json_object(path: Path) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink():
        raise ValueError("probe_reuse_input_file_invalid")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("probe_reuse_input_file_invalid")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            raw = stream.read()
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    try:
        path_stat = path.stat(follow_symlinks=False)
    except OSError as exc:
        raise ValueError("probe_reuse_input_file_changed") from exc
    identity_before = (before.st_dev, before.st_ino, before.st_size,
        before.st_mtime_ns)
    identity_after = (after.st_dev, after.st_ino, after.st_size,
        after.st_mtime_ns)
    identity_path = (path_stat.st_dev, path_stat.st_ino, path_stat.st_size,
        path_stat.st_mtime_ns)
    if (identity_before != identity_after or identity_after != identity_path
            or len(raw) != after.st_size or path.is_symlink()):
        raise ValueError("probe_reuse_input_file_changed")
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("probe_reuse_input_object_invalid")
    return value, raw


def _digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def build_audit(*, source_root: Path, history_root: Path,
        preflight_path: Path) -> dict[str, Any]:
    source_root = source_root.resolve(strict=True)
    if not source_root.is_dir():
        raise ValueError("probe_reuse_source_root_invalid")
    sys.path.insert(0, str(source_root))

    from work.rootless_history_boundary_campaign import _history_boundary
    from sentientos.resident_developmental_cognition import (
        _task_family_history_examples,
    )

    report, report_raw = _read_json_object(preflight_path)
    report_digest = report.get("audit_digest")
    expected_report_digest = _digest({key: value for key, value in report.items()
        if key != "audit_digest"})
    if report_digest != expected_report_digest:
        raise ValueError("probe_reuse_preflight_digest_invalid")
    probe_inputs = report.get("transfer_probe_inputs")
    selected_ids = report.get("binder_selected_record_ids")
    selected_digests = report.get("binder_selected_record_digests")
    family = report.get("task_family_id")
    if (not isinstance(probe_inputs, list) or not probe_inputs
            or any(type(value) is not int for value in probe_inputs)
            or len(set(probe_inputs)) != len(probe_inputs)
            or not isinstance(selected_ids, list) or not selected_ids
            or not isinstance(selected_digests, list)
            or len(selected_ids) != len(selected_digests)
            or len(set(selected_ids)) != len(selected_ids)
            or not isinstance(family, str) or not family
            or report.get("inference_performed") is not False):
        raise ValueError("probe_reuse_preflight_binding_invalid")

    boundary = _history_boundary(history_root)
    if boundary.get("boundary_digest") != report.get(
            "prior_history_boundary_digest"):
        raise ValueError("probe_reuse_history_boundary_mismatch")
    boundary_files = {row["path"]: row for row in boundary["files"]}
    rows: list[dict[str, Any]] = []
    for record_id, record_digest in zip(selected_ids, selected_digests):
        record_path = history_root / "records" / f"{record_id}.json"
        record, record_raw = _read_json_object(record_path)
        relative_path = f"records/{record_id}.json"
        boundary_row = boundary_files.get(relative_path)
        file_sha256 = hashlib.sha256(record_raw).hexdigest()
        if (boundary_row is None or boundary_row.get("sha256") != file_sha256
                or record.get("record_id") != record_id
                or record.get("record_digest") != record_digest):
            raise ValueError("probe_reuse_selected_record_binding_invalid")
        candidate = record.get("candidate")
        if not isinstance(candidate, dict):
            raise ValueError("probe_reuse_selected_candidate_invalid")
        examples = _task_family_history_examples(candidate,
            task_family_id=family)
        available: set[int] = set()
        for experience in examples:
            for example in experience.get("examples", ()):
                value = example.get("probe_input") if isinstance(example, dict) else None
                if type(value) is int:
                    available.add(value)
        overlap = sorted(available & set(probe_inputs))
        rows.append({"record_id": record_id,
            "record_digest": record_digest,
            "record_file_sha256": file_sha256,
            "projected_experience_count": len(examples),
            "available_probe_inputs": sorted(available),
            "overlap_inputs": overlap,
            "overlap_count": len(overlap)})

    aggregate_overlap = sorted(set().union(*(
        set(row["overlap_inputs"]) for row in rows)))
    qualified = not aggregate_overlap
    return {
        "schema_version": "sentientos.planned_cycle_probe_reuse_audit:v1",
        "campaign_id": report.get("campaign_id"),
        "cycle_id": report.get("cycle_id"),
        "plan_digest": report.get("plan_digest"),
        "task_generation_seed": report.get("task_generation_seed"),
        "task_family_id": family,
        "transfer_probe_inputs": probe_inputs,
        "source_preflight": {
            "artifact": preflight_path.name,
            "file_sha256": hashlib.sha256(report_raw).hexdigest(),
            "audit_digest": report_digest,
            "plan_digest": report.get("plan_digest"),
            "prior_history_boundary_digest": boundary["boundary_digest"],
            "binder_selected_record_ids": selected_ids,
            "binder_selected_record_digests": selected_digests},
        "recomputed_history_boundary": {
            "boundary_digest": boundary["boundary_digest"],
            "file_count": boundary["file_count"],
            "atomic_snapshot": boundary["atomic_snapshot"],
            "selected_record_files_match_boundary": True},
        "selected_prompt_records": rows,
        "aggregate_overlap_inputs": aggregate_overlap,
        "held_out_transfer_qualified": qualified,
        "classification": ("held_out_transfer_candidate"
            if qualified else "reused_input_recall_not_held_out_transfer"),
        "inference_performed": False,
        "learning_established": False,
        "authority": False,
        "limitations": [
            "The source preflight does not establish model attention or use.",
            "The history boundary is not an atomic filesystem snapshot.",
            "This audit does not reconstruct a prompt or execute inference."]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--history-root", type=Path, required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise ValueError("probe_reuse_output_already_exists")
    audit = build_audit(source_root=args.source_root,
        history_root=args.history_root, preflight_path=args.preflight)
    audit["audit_digest"] = _digest(audit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(audit, sort_keys=True, indent=2) + "\n").encode("utf-8")
    descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(encoded)
    print(json.dumps({"output": str(args.output),
        "audit_digest": audit["audit_digest"],
        "classification": audit["classification"],
        "aggregate_overlap_inputs": audit["aggregate_overlap_inputs"]},
        sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
