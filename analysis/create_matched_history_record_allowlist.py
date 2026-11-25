"""Freeze the shared-record intersection from a verified parity audit."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

MAX_INPUT_BYTES = 8 * 1024 * 1024


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("matched_history_allowlist_duplicate_json_key")
        result[key] = value
    return result


def _read_json(path: Path) -> tuple[dict[str, Any], str]:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise ValueError("matched_history_allowlist_input_unreadable") from exc
    try:
        metadata = os.fstat(descriptor)
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
                or metadata.st_size > MAX_INPUT_BYTES):
            raise ValueError("matched_history_allowlist_input_invalid")
        chunks: list[bytes] = []
        remaining = metadata.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                raise ValueError("matched_history_allowlist_input_truncated")
            chunks.append(chunk)
            remaining -= len(chunk)
    finally:
        os.close(descriptor)
    raw = b"".join(chunks)
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
            parse_constant=lambda _: (_ for _ in ()).throw(
                ValueError("matched_history_allowlist_nonstandard_json")))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("matched_history_allowlist_json_invalid") from exc
    if not isinstance(value, dict):
        raise ValueError("matched_history_allowlist_object_required")
    return value, "sha256:" + hashlib.sha256(raw).hexdigest()


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def create_allowlist(*, audit_path: Path) -> dict[str, Any]:
    audit, audit_file_digest = _read_json(audit_path)
    if (audit.get("schema_version") not in {
            "sentientos.matched_task_preflight_prompt_parity:v2",
            "sentientos.matched_task_preflight_prompt_parity:v3",
            "sentientos.matched_task_preflight_prompt_parity:v4"}
            or audit.get("audit_digest") != _digest({key: value
                for key, value in audit.items() if key != "audit_digest"})
            or audit.get("all_shared_record_digests_equal") is not True
            or audit.get("selected_record_source_reconstructed") is not True
            or audit.get("inference_performed") is not False
            or audit.get("learning_established") is not False
            or audit.get("authority") is not False):
        raise ValueError("matched_history_allowlist_parity_audit_invalid")
    ids = audit.get("shared_selected_record_ids")
    digests = audit.get("shared_selected_record_digests")
    if (not isinstance(ids, list) or not ids or len(ids) != len(set(ids))
            or any(not isinstance(item, str) or not item.startswith("devrec-")
                for item in ids)
            or not isinstance(digests, dict) or set(digests) != set(ids)
            or any(not isinstance(value, str) or len(value) != 71
                or not value.startswith("sha256:")
                or any(char not in "0123456789abcdef" for char in value[7:])
                for value in digests.values())):
        raise ValueError("matched_history_allowlist_shared_records_invalid")
    semantic = {
        "schema_version": "sentientos.historical_examples_record_allowlist:v1",
        "cycle_root_id": audit.get("shared_cycle_root_id"),
        "source_receipt_digest": audit.get("shared_source_receipt_digest"),
        "task_digest": audit.get("task_digest"),
        "record_ids": ids,
        "record_digests": digests,
        "basis": "intersection_of_verified_matched_preflight_history_sets",
        "source_parity_audit_sha256": audit_file_digest,
        "inference_performed": False,
        "learning_established": False,
        "authority": False,
    }
    if (not isinstance(semantic["cycle_root_id"], str)
            or not isinstance(semantic["source_receipt_digest"], str)
            or not isinstance(semantic["task_digest"], str)):
        raise ValueError("matched_history_allowlist_source_binding_missing")
    return {**semantic, "allowlist_digest": _digest(semantic)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parity-audit", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = create_allowlist(audit_path=args.parity_audit)
    rendered = json.dumps(report, sort_keys=True, indent=2,
        ensure_ascii=False, allow_nan=False) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(rendered)
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, TypeError, ValueError) as exc:
        print("matched_history_allowlist_error:" + str(exc), file=sys.stderr)
        raise SystemExit(2)
