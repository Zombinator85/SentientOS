"""Verify plan binding and integrity of a prepared v7 owner preflight artifact.

This audit can reopen the original history source. It independently checks the
report digest, campaign/seed/task bindings, deterministic probes, selected
history overlap, and non-inference posture.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Mapping

from sentientos.developmental_model_replacement_experiment import (
    ROOTLESS_INTEGER_AFFINE_WIDE_TRANSFER_TASK_FAMILY,
    rootless_integer_affine_transfer_task_pair,
)
from sentientos.local_model_authority import digest_payload
from sentientos.resident_developmental_cognition import (
    _task_family_history_examples,
)
from work.rootless_history_boundary_campaign import _history_boundary

_LOW_FAMILY = "rootless_integer_affine_transfer_low_range_v6"
_WIDE_FAMILY = ROOTLESS_INTEGER_AFFINE_WIDE_TRANSFER_TASK_FAMILY
_RECORD_ID = re.compile(r"devrec-[0-9a-f]{24}", flags=re.ASCII)


def _canonical_digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _selected_records_are_transfer_disjoint(report: Mapping[str, Any],
        reuse: Mapping[str, Any]) -> bool:
    owner_ids = report.get("owner_selected_record_ids")
    binder_ids = report.get("binder_selected_record_ids")
    owner_rows = reuse.get("owner_selected_record_overlaps")
    binder_rows = reuse.get("binder_selected_prompt_record_overlaps")
    if (not isinstance(owner_ids, list) or not isinstance(binder_ids, list)
            or not isinstance(owner_rows, list) or not isinstance(binder_rows, list)
            or any(not isinstance(value, str) or _RECORD_ID.fullmatch(value) is None
                for value in (*owner_ids, *binder_ids))
            or len(set(owner_ids)) != len(owner_ids)
            or len(set(binder_ids)) != len(binder_ids)):
        return False
    for ids, rows in ((owner_ids, owner_rows), (binder_ids, binder_rows)):
        row_ids = []
        for row in rows:
            if (not isinstance(row, Mapping)
                    or not isinstance(row.get("record_id"), str)
                    or _RECORD_ID.fullmatch(row["record_id"]) is None
                    or type(row.get("current_probe_overlap_count")) is not int
                    or row["current_probe_overlap_count"] != 0
                    or row.get("current_probe_overlap_inputs") != []):
                return False
            row_ids.append(row["record_id"])
        if row_ids != ids:
            return False
    return True


def _read_canonical_json(path: Path) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("prepared_preflight_input_not_regular_file")
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    canonical_forms = (() if not isinstance(value, dict) else (
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
            + b"\n",
        json.dumps(value, sort_keys=True, indent=2).encode("utf-8") + b"\n"))
    if raw not in canonical_forms:
        raise ValueError("prepared_preflight_input_noncanonical")
    return value, raw


def _verify_boundary_manifest(plan: Mapping[str, Any]) -> tuple[bool, int]:
    boundary = plan.get("initial_history_boundary")
    if not isinstance(boundary, Mapping):
        return False, 0
    files = boundary.get("files")
    if not isinstance(files, list):
        return False, 0
    paths: list[str] = []
    total_bytes = 0
    for row in files:
        if not isinstance(row, Mapping):
            return False, len(files)
        path = row.get("path")
        size = row.get("size_bytes")
        file_digest = row.get("sha256")
        if (not isinstance(path, str)
                or re.fullmatch(r"(?:records/devrec-[0-9a-f]{24}|"
                    r"receipts/devreceipt-[0-9a-f]{24})\.json", path,
                    flags=re.ASCII) is None
                or type(size) is not int or size < 0
                or not isinstance(file_digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", file_digest,
                    flags=re.ASCII) is None):
            return False, len(files)
        paths.append(path)
        total_bytes += size
    semantic = {key: value for key, value in boundary.items()
        if key != "boundary_digest"}
    valid = (
        boundary.get("schema_version") == "sentientos.rootless_history_boundary:v1"
        and boundary.get("atomic_snapshot") is False
        and type(boundary.get("file_count")) is int
        and boundary.get("file_count") == len(files)
        and type(boundary.get("total_size_bytes")) is int
        and boundary.get("total_size_bytes") == total_bytes
        and paths == sorted(paths)
        and len(set(paths)) == len(paths)
        and boundary.get("boundary_digest") == digest_payload(semantic))
    return valid, len(files)


def _reopen_source_history(history_root: Path, *,
        expected_boundary: Mapping[str, Any], transfer_inputs: list[int]
        ) -> dict[str, Any]:
    before = _history_boundary(history_root)
    if before != dict(expected_boundary):
        raise ValueError("prepared_preflight_source_history_boundary_mismatch")
    root = history_root.resolve(strict=True)
    record_count = 0
    example_counts = {_LOW_FAMILY: 0, _WIDE_FAMILY: 0}
    family_inputs: dict[str, set[int]] = {
        _LOW_FAMILY: set(), _WIDE_FAMILY: set()}
    for row in before["files"]:
        if not row["path"].startswith("records/"):
            continue
        path = root / Path(row["path"])
        raw = path.read_bytes()
        if (len(raw) != row["size_bytes"]
                or hashlib.sha256(raw).hexdigest() != row["sha256"]):
            raise ValueError("prepared_preflight_source_record_changed")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("prepared_preflight_source_record_invalid") from exc
        if (not isinstance(payload, dict)
                or payload.get("record_id") != path.stem):
            raise ValueError("prepared_preflight_source_record_identity_invalid")
        candidate = payload.get("candidate")
        candidate = candidate if isinstance(candidate, dict) else payload
        record_count += 1
        for family in (_LOW_FAMILY, _WIDE_FAMILY):
            experiences = _task_family_history_examples(candidate,
                task_family_id=family)
            example_counts[family] += sum(len(experience.get("examples", []))
                for experience in experiences)
            for experience in experiences:
                for example in experience.get("examples", []):
                    value = (example.get("probe_input")
                        if isinstance(example, dict) else None)
                    if type(value) is int:
                        family_inputs[family].add(value)
    after = _history_boundary(history_root)
    if after != before:
        raise ValueError("prepared_preflight_source_history_changed_during_read")
    return {
        "source_history_record_count": record_count,
        "source_family_example_counts": example_counts,
        "source_family_probe_inputs": {
            family: sorted(values) for family, values in family_inputs.items()},
        "source_transfer_probe_overlaps": {
            family: sorted(family_inputs[family] & set(transfer_inputs))
            for family in (_LOW_FAMILY, _WIDE_FAMILY)},
        "source_history_boundary_digest": before["boundary_digest"],
        "source_history_file_count": before["file_count"],
        "source_history_total_size_bytes": before["total_size_bytes"],
        "source_history_boundary_reopened_and_matched": True,
        "source_history_stable_during_read": True,
        "projection_implementation_sha256": hashlib.sha256(
            Path(__file__).resolve().parents[1].joinpath(
                "sentientos", "resident_developmental_cognition.py").read_bytes()
            ).hexdigest(),
    }


def create_audit(*, plan_path: Path, report_path: Path,
        history_root: Path | None = None) -> dict[str, Any]:
    plan, _ = _read_canonical_json(plan_path)
    report, _ = _read_canonical_json(report_path)
    claimed_plan_digest = plan.get("plan_digest")
    plan_semantic = {key: value for key, value in plan.items()
        if key != "plan_digest"}
    plan_digest_verified = claimed_plan_digest == digest_payload(plan_semantic)
    if not plan_digest_verified:
        raise ValueError("prepared_preflight_plan_digest_mismatch")
    boundary_manifest_verified, boundary_file_count = _verify_boundary_manifest(plan)
    if not boundary_manifest_verified:
        raise ValueError("prepared_preflight_boundary_manifest_invalid")
    if plan.get("task_family_id") != ROOTLESS_INTEGER_AFFINE_WIDE_TRANSFER_TASK_FAMILY:
        raise ValueError("prepared_preflight_plan_family_mismatch")
    cycle_ids = plan.get("ordered_cycle_ids")
    if not isinstance(cycle_ids, list):
        raise ValueError("prepared_preflight_plan_cycle_list_invalid")
    cycle_id = report.get("cycle_id")
    if cycle_ids.count(cycle_id) != 1:
        raise ValueError("prepared_preflight_cycle_not_in_plan")
    index = cycle_ids.index(cycle_id)
    seed = plan["ordered_task_generation_seeds"][index]
    acquisition, transfer = rootless_integer_affine_transfer_task_pair(
        seed, task_family_id=ROOTLESS_INTEGER_AFFINE_WIDE_TRANSFER_TASK_FAMILY,
        transfer_probe_count=plan.get("transfer_probe_count", 3))
    acquisition_inputs = [acquisition.probe_input,
        *acquisition.additional_probe_inputs]
    transfer_inputs = [transfer.probe_input, *transfer.additional_probe_inputs]
    claimed_digest = report.get("audit_digest")
    report_semantic = {key: value for key, value in report.items()
        if key != "audit_digest"}
    if claimed_digest != _canonical_digest(report_semantic):
        raise ValueError("prepared_preflight_report_digest_mismatch")
    reuse = report.get("planned_seed_probe_reuse")
    expected_probe_digest = "sha256:" + digest_payload({
        "probe_inputs": transfer_inputs})
    checks = {
        "report_digest_verified": True,
        "plan_digest_verified": plan_digest_verified,
        "initial_history_boundary_digest_verified": boundary_manifest_verified,
        "plan_digest_matches": report.get("plan_digest") == plan.get("plan_digest"),
        "cycle_seed_matches": report.get("task_generation_seed") == seed,
        "task_family_matches": report.get("task_family_id") ==
            ROOTLESS_INTEGER_AFFINE_WIDE_TRANSFER_TASK_FAMILY,
        "initial_history_boundary_matches": report.get(
            "prior_history_boundary_digest") ==
            plan.get("initial_history_boundary", {}).get("boundary_digest"),
        "model_identity_matches_plan": report.get(
            "target_model_identity_digest") ==
            plan.get("ordered_model_identity_digests", [])[index],
        "deterministic_acquisition_probes_match": report.get(
            "acquisition_probe_inputs") == acquisition_inputs,
        "deterministic_transfer_probes_match": report.get(
            "transfer_probe_inputs") == transfer_inputs,
        "probe_reuse_report_matches": (
            isinstance(reuse, Mapping)
            and reuse.get("transfer_probe_inputs") == transfer_inputs
            and reuse.get("transfer_probe_input_digest") == expected_probe_digest
            and reuse.get("posture") ==
                "planned_transfer_probe_set_disjoint_from_selected_history"
            and reuse.get("held_out_transfer_qualified") is True
            and reuse.get("prompt_projection_overlap_measurement_complete") is True
            and reuse.get("prompt_projection_overlap_input_count") == 0
            and reuse.get("prompt_projection_overlap_example_count") == 0
            and _selected_records_are_transfer_disjoint(report, reuse)),
        "selected_history_is_transfer_disjoint": (
            isinstance(reuse, Mapping)
            and _selected_records_are_transfer_disjoint(report, reuse)),
        "non_inference_posture": (
            report.get("inference_performed") is False
            and report.get("model_attention_established") is False
            and report.get("learning_established") is False
            and report.get("authority") is False),
    }
    source_history = (_reopen_source_history(history_root,
        expected_boundary=plan["initial_history_boundary"],
        transfer_inputs=transfer_inputs) if history_root is not None else None)
    if source_history is not None:
        checks["source_history_boundary_reopened_and_matched"] = (
            source_history["source_history_boundary_reopened_and_matched"])
        checks["source_history_stable_during_read"] = (
            source_history["source_history_stable_during_read"])
    if not all(checks.values()):
        failed = sorted(key for key, value in checks.items() if not value)
        raise ValueError("prepared_preflight_check_failed:" + ",".join(failed))
    semantic = {
        "schema_version": ("sentientos.rootless_prepared_v7_owner_preflight_audit:v5"
            if source_history is not None else
            "sentientos.rootless_prepared_v7_owner_preflight_audit:v4"),
        "campaign_id": plan["campaign_id"],
        "plan_digest": plan["plan_digest"],
        "cycle_id": cycle_id,
        "cycle_index": index,
        "task_family_id": plan["task_family_id"],
        "task_generation_seed": seed,
        "source_history_boundary_digest": report[
            "prior_history_boundary_digest"],
        "source_history_file_count": boundary_file_count,
        "source_history_boundary_manifest_verified": boundary_manifest_verified,
        "source_history_records_reopened": source_history is not None,
        "model_inference_performed": False,
        "checks": checks,
        "verification_posture": (
            "report_integrity_plan_binding_and_source_overlap_recomputed"
            if source_history is not None else
            "report_integrity_and_plan_binding_verified; source_history_bytes_not_reopened"),
        "report_claimed_held_out_transfer_qualified": reuse[
            "held_out_transfer_qualified"],
        "held_out_transfer_independently_verified": (
            source_history is not None and all(not overlaps for overlaps in
                source_history["source_transfer_probe_overlaps"].values())),
        "model_attention_established": False,
        "learning_established": False,
        "authority": False,
        "source_report_digest": claimed_digest,
    }
    if source_history is not None:
        semantic.update(source_history)
    return {**semantic, "audit_digest": _canonical_digest(semantic)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--history-root", type=Path,
        help="reopen the frozen source history and recompute input overlap")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--verify-existing", action="store_true")
    args = parser.parse_args()
    audit = create_audit(plan_path=args.plan, report_path=args.report,
        history_root=args.history_root)
    raw = (json.dumps(audit, sort_keys=True, indent=2) + "\n").encode("utf-8")
    if args.verify_existing:
        existing, existing_raw = _read_canonical_json(args.output)
        if existing_raw != raw or existing.get("audit_digest") != audit["audit_digest"]:
            raise ValueError("prepared_preflight_audit_existing_mismatch")
        status = "verified_existing"
    else:
        if args.output.exists() or args.output.is_symlink():
            raise ValueError("prepared_preflight_audit_output_already_exists")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        status = "created"
    print(json.dumps({"status": status, "audit_digest": audit["audit_digest"],
        "cycle_id": audit["cycle_id"], "checks": audit["checks"],
        "report_claimed_held_out_transfer_qualified": audit[
            "report_claimed_held_out_transfer_qualified"],
        "held_out_transfer_independently_verified": audit[
            "held_out_transfer_independently_verified"],
        "source_history_records_reopened": audit[
            "source_history_records_reopened"],
        "model_inference_performed": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
