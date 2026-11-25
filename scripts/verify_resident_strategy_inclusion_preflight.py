#!/usr/bin/env python3
"""Verify a persisted resident strategy-inclusion preflight without inference."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sentientos.developmental_history_intervention_experiment import (
    DevelopmentalExperimentStore,
)
from sentientos.developmental_model_replacement_experiment import (
    ObjectivePredictionTask,
)
from sentientos.governed_local_model_invocation import validate_receipt
from sentientos.local_model_authority import digest_payload
from sentientos.resident_developmental_writeback import (
    DevelopmentalHistoryStore,
)
from work.historical_examples_intervention import HistoricalExamplesPairJournal
from work.strategy_inclusion_intervention import (
    _digest, validate_strategy_inclusion_protocol,
)


MAX_REPORT_BYTES = 4 * 1024 * 1024
_HEX = frozenset("0123456789abcdef")


def _read_regular_json(path: Path, *, max_bytes: int) -> tuple[dict[str, Any], bytes]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_size > max_bytes):
            raise ValueError("strategy_preflight_input_not_bounded_regular_file")
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after = os.fstat(descriptor)
        if (len(raw) != before.st_size or len(raw) > max_bytes
                or after.st_size != before.st_size
                or after.st_ino != before.st_ino
                or after.st_dev != before.st_dev
                or after.st_mtime_ns != before.st_mtime_ns):
            raise ValueError("strategy_preflight_input_changed_during_read")
    finally:
        os.close(descriptor)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("strategy_preflight_input_invalid_json") from exc
    if not isinstance(value, dict):
        raise ValueError("strategy_preflight_input_not_object")
    return value, raw


def _sha256(value: Any, code: str) -> str:
    if (not isinstance(value, str) or len(value) != 71
            or not value.startswith("sha256:")
            or any(char not in _HEX for char in value[7:])):
        raise ValueError(code)
    return value


def _verify_preflight(*, report_path: Path, journal_root: Path,
        cycle_root: Path) -> dict[str, Any]:
    report_path = report_path.resolve(strict=True)
    if cycle_root.is_symlink():
        raise ValueError("strategy_preflight_cycle_root_invalid")
    cycle_root = cycle_root.resolve(strict=True)
    if not cycle_root.is_dir():
        raise ValueError("strategy_preflight_cycle_root_invalid")
    report, report_raw = _read_regular_json(report_path,
        max_bytes=MAX_REPORT_BYTES)
    if (report.get("schema_version") !=
            "sentientos.resident_strategy_inclusion_cpu_preflight:v3"
            or report.get("cycle_root_id") != cycle_root.name
            or report.get("model_loaded") is not False
            or report.get("model_invoked") is not False
            or report.get("learning_established") is not False
            or report.get("authority") is not False
            or report.get("private_task_plan_persisted") is not True
            or report.get("strategy_protocol_persisted") is not True):
        raise ValueError("strategy_preflight_report_posture_invalid")

    protocol = report.get("strategy_pair_protocol")
    if not isinstance(protocol, Mapping):
        raise ValueError("strategy_preflight_protocol_missing")
    protocol_digest = _sha256(protocol.get("protocol_digest"),
        "strategy_preflight_protocol_digest_invalid")
    task_digest = _sha256(report.get("task_digest"),
        "strategy_preflight_task_digest_invalid")
    private_plan_digest = _sha256(report.get("private_task_plan_digest"),
        "strategy_preflight_private_task_plan_digest_invalid")
    answer_key_digest = _sha256(report.get("answer_key_digest"),
        "strategy_preflight_answer_key_digest_invalid")
    if (protocol_digest != report.get("protocol_digest")
            or task_digest != protocol.get("task_digest")
            or private_plan_digest != protocol.get("private_task_plan_digest")
            or answer_key_digest != protocol.get("answer_key_digest")
            or protocol.get("schema_version") not in {
                "sentientos.strategy_inclusion_intervention_protocol:v4",
                "sentientos.strategy_inclusion_intervention_protocol:v5",
                "sentientos.strategy_inclusion_intervention_protocol:v6"}):
        raise ValueError("strategy_preflight_report_protocol_binding_invalid")
    validate_strategy_inclusion_protocol(protocol=protocol,
        target_model_identity_digest=report.get(
            "source_model_identity_digest"), task_digest=task_digest)

    store = DevelopmentalExperimentStore(journal_root)
    saved_protocol = store.load_strategy_inclusion_protocol(protocol_digest)
    if saved_protocol != dict(protocol):
        raise ValueError("strategy_preflight_saved_protocol_mismatch")
    journal = HistoricalExamplesPairJournal(store=store)
    task = journal.load_private_task_plan(task_digest=task_digest,
        task_plan_digest=private_plan_digest)
    descriptor = task.public_descriptor()
    specification = task.specification()
    if (descriptor.get("task_digest") != task_digest
            or descriptor.get("task_family_id") != report.get("task_family_id")
            or not isinstance(descriptor.get("probe_inputs"), (list, tuple))
            or type(specification.get("multiplier")) is not int
            or type(specification.get("offset")) is not int):
        raise ValueError("strategy_preflight_private_task_binding_invalid")
    answer_key = {_digest({
        "schema_version": "sentientos.objective_probe_binding:v1",
        "task_digest": task_digest,
        "probe_index": index, "probe_input": probe,
    }): specification["multiplier"] * probe + specification["offset"]
        for index, probe in enumerate(descriptor["probe_inputs"])}
    if (set(answer_key) != set(protocol.get("probe_binding_digests", ()))
            or _digest(answer_key) != answer_key_digest):
        raise ValueError("strategy_preflight_answer_key_commitment_mismatch")

    source_receipt_id = report.get("source_receipt_id")
    source_receipt_digest = report.get("source_receipt_digest")
    if (not isinstance(source_receipt_id, str)
            or not source_receipt_id.startswith("lmrec-")
            or not isinstance(source_receipt_digest, str)
            or len(source_receipt_digest) != 64
            or any(char not in _HEX for char in source_receipt_digest)):
        raise ValueError("strategy_preflight_source_receipt_binding_invalid")
    receipt_path = (cycle_root / "inference-custody" / "receipts" /
        (source_receipt_id + ".json"))
    receipt, _receipt_raw = _read_regular_json(receipt_path,
        max_bytes=MAX_REPORT_BYTES)
    valid_receipt, reasons = validate_receipt(receipt)
    request = receipt.get("request")
    identity = request.get("active_model_identity") if isinstance(
        request, Mapping) else None
    if (not valid_receipt or receipt.get("receipt_id") != source_receipt_id
            or receipt.get("receipt_digest") != source_receipt_digest
            or not isinstance(identity, Mapping)
            or "sha256:" + digest_payload(dict(identity)) !=
                report.get("source_model_identity_digest")):
        raise ValueError("strategy_preflight_source_receipt_invalid:" +
            ",".join(reasons))

    history_root = cycle_root / "resident-cognition" / "history"
    records = {record.record_id: record.record_digest
        for record in DevelopmentalHistoryStore(history_root).records()}
    receipts = DevelopmentalHistoryStore(history_root).receipts()
    receipt_records = {receipt.record_id: receipt.record_digest
        for receipt in receipts}
    selected_ids = protocol.get("history_record_ids")
    selected_digests = protocol.get("history_record_digests")
    if (not isinstance(selected_ids, list) or not selected_ids
            or not isinstance(selected_digests, list)
            or len(selected_ids) != len(selected_digests)
            or any(records.get(record_id) != record_digest
                or receipt_records.get(record_id) != record_digest
                for record_id, record_digest in zip(
                    selected_ids, selected_digests, strict=True))):
        raise ValueError("strategy_preflight_selected_history_binding_invalid")

    summary = report.get("strategy_evidence_summary")
    if (not isinstance(summary, Mapping)
            or summary != protocol.get("strategy_evidence_summary")
            or summary.get("relation_withheld") is not True
            or summary.get("supporting_answer_values_withheld") is not True):
        raise ValueError("strategy_preflight_evidence_summary_binding_invalid")
    return {
        "schema_version": "sentientos.strategy_inclusion_preflight_verification:v1",
        "preflight_report_digest": "sha256:" + hashlib.sha256(
            report_raw).hexdigest(),
        "protocol_digest": protocol_digest,
        "task_digest": task_digest,
        "private_task_plan_digest": private_plan_digest,
        "answer_key_digest": answer_key_digest,
        "selected_history_set_digest": protocol["history_set_digest"],
        "selected_history_count": len(selected_ids),
        "strategy_digest": protocol["strategy_digest"],
        "source_receipt_id": source_receipt_id,
        "source_receipt_digest": source_receipt_digest,
        "source_model_identity_digest": report[
            "source_model_identity_digest"],
        "private_task_plan_reloaded": True,
        "strategy_protocol_reloaded": True,
        "answer_key_commitment_verified": True,
        "source_receipt_verified": True,
        "selected_history_records_verified": True,
        "relation_or_answer_values_included": False,
        "model_loaded": False,
        "model_invoked": False,
        "learning_established": False,
        "authority": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--journal-root", type=Path, required=True)
    parser.add_argument("--cycle-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = _verify_preflight(report_path=args.report,
        journal_root=args.journal_root, cycle_root=args.cycle_root)
    if args.output.exists() or args.output.is_symlink():
        raise ValueError("strategy_preflight_verification_output_exists")
    args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    raw = (json.dumps(result, sort_keys=True, indent=2) + "\n").encode("utf-8")
    descriptor = os.open(args.output,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600)
    try:
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short strategy verification artifact write")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, TypeError, ValueError, RuntimeError) as exc:
        print(f"strategy preflight verification failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
