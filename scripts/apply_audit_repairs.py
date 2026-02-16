from __future__ import annotations

"""Apply safe audit repairs from a pre-generated plan with receipts."""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from scripts.provenance_hash_chain import GENESIS_PREV_HASH

DEFAULT_PLAN_PATH = Path("glow/audits/audit_repair_plan.json")
DEFAULT_RESULT_PATH = Path("glow/audits/audit_repair_result.json")
REPAIR_CHAIN_PATH = Path("glow/audits/repairs/repair_receipts.jsonl")
SCHEMA_VERSION = 1


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 128), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _append_receipt(kind: str, artifact_path: Path, payload: dict[str, Any]) -> None:
    REPAIR_CHAIN_PATH.parent.mkdir(parents=True, exist_ok=True)
    artifact_hash = _file_sha256(artifact_path)
    prev_hash = GENESIS_PREV_HASH
    if REPAIR_CHAIN_PATH.exists():
        lines = [line for line in REPAIR_CHAIN_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
        if lines:
            prev_entry = json.loads(lines[-1])
            prev_hash = str(prev_entry.get("receipt_hash", GENESIS_PREV_HASH))

    receipt_core = {
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "created_at": _utc_now(),
        "artifact": str(artifact_path),
        "artifact_sha256": artifact_hash,
        "prev_receipt_hash": prev_hash,
        "summary": {
            "issues": len(payload.get("issues", [])),
            "repairs": len(payload.get("repairs", [])),
            "applied": len(payload.get("applied", [])),
            "skipped": len(payload.get("skipped", [])),
            "errors": len(payload.get("errors", [])),
        },
    }
    chained = dict(receipt_core)
    chained["receipt_hash"] = hashlib.sha256(_canonical_json_bytes(receipt_core)).hexdigest()
    with REPAIR_CHAIN_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(chained, sort_keys=True) + "\n")


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(content, encoding="utf-8")
    os.replace(temp_path, path)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_entries(path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        payload = json.loads(raw_line)
        if not isinstance(payload, dict):
            raise ValueError(f"{path} contains non-object JSON line")
        entries.append(payload)
    return entries


def _entry_hash(timestamp: str, data: dict[str, Any], prev_hash: str) -> str:
    digest = hashlib.sha256()
    digest.update(timestamp.encode("utf-8"))
    digest.update(json.dumps(data, sort_keys=True).encode("utf-8"))
    digest.update(prev_hash.encode("utf-8"))
    return digest.hexdigest()


def _rebuild_chain_atomic(path: Path, start_prev: str) -> tuple[str, bool, int]:
    entries = _read_entries(path)
    prev = start_prev
    changed = False
    fixed = 0
    rebuilt: list[dict[str, Any]] = []

    for entry in entries:
        if "timestamp" not in entry or "data" not in entry or not isinstance(entry["data"], dict):
            raise ValueError(f"{path} contains non-rebuildable entry")

        expected_hash = _entry_hash(entry["timestamp"], entry["data"], prev)
        new_entry = dict(entry)

        if new_entry.get("prev_hash") != prev:
            new_entry["prev_hash"] = prev
            changed = True
            fixed += 1

        current = new_entry.get("rolling_hash") or new_entry.get("hash")
        if current != expected_hash:
            new_entry["rolling_hash"] = expected_hash
            if "hash" in new_entry:
                new_entry.pop("hash", None)
            changed = True
            fixed += 1

        rebuilt.append(new_entry)
        prev = expected_hash

    if changed:
        rendered = "\n".join(json.dumps(item, sort_keys=True) for item in rebuilt) + "\n"
        _atomic_write_text(path, rendered)

    return prev, changed, fixed


def _last_hash(path: Path, start_prev: str) -> str:
    prev = start_prev
    for entry in _read_entries(path):
        if not isinstance(entry, dict):
            continue
        prev = str(entry.get("rolling_hash") or entry.get("hash") or prev)
    return prev


def _build_result() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "applied": [],
        "skipped": [],
        "errors": [],
        "before_hashes": {},
        "after_hashes": {},
    }


def apply_repairs(plan: dict[str, Any], plan_path: Path) -> dict[str, Any]:
    result = _build_result()
    safe_repairs = [repair for repair in plan.get("repairs", []) if repair.get("safe") is True]
    safe_paths = {str(path) for repair in safe_repairs for path in repair.get("paths", []) if repair.get("action") == "rebuild_chain"}

    target_dir = Path(str(plan.get("target", "logs/")))
    if not target_dir.exists():
        result["errors"].append({"plan": str(plan_path), "error": f"target not found: {target_dir}"})
        return result

    prev = "0" * 64
    for path in sorted(p for p in target_dir.iterdir() if p.is_file()):
        path_key = str(path)
        if path_key not in safe_paths:
            try:
                prev = _last_hash(path, prev)
            except Exception:
                # if a skipped file is unreadable, preserve chain input so subsequent safe files are skipped safely
                result["skipped"].append({"path": path_key, "reason": "manual_required_unreadable"})
            continue

        result["before_hashes"][path_key] = _file_sha256(path)
        try:
            prev, changed, fixed = _rebuild_chain_atomic(path, prev)
        except Exception as exc:
            result["errors"].append({"path": path_key, "error": str(exc)})
            continue

        result["after_hashes"][path_key] = _file_sha256(path)
        if changed:
            result["applied"].append({"path": path_key, "action": "rebuild_chain", "fixed": fixed})
        else:
            result["skipped"].append({"path": path_key, "reason": "already_clean"})

    for repair in plan.get("repairs", []):
        if not repair.get("safe"):
            result["skipped"].append(
                {
                    "repair_id": repair.get("repair_id"),
                    "paths": repair.get("paths", []),
                    "reason": "unsafe_manual_required",
                }
            )

    return result


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Apply safe audit repairs from a plan")
    parser.add_argument("--plan", default=str(DEFAULT_PLAN_PATH), help="path to repair plan")
    parser.add_argument("--output", default=str(DEFAULT_RESULT_PATH), help="path to write result JSON")
    parser.add_argument("--apply", action="store_true", help="execute safe repairs")
    args = parser.parse_args(argv)

    if not (args.apply or os.getenv("SENTIENTOS_APPLY_AUDIT_REPAIRS") == "1"):
        print("Refusing to apply repairs without --apply or SENTIENTOS_APPLY_AUDIT_REPAIRS=1")
        return 2

    plan_path = Path(args.plan)
    output_path = Path(args.output)
    plan = _load_json(plan_path)
    result = apply_repairs(plan, plan_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _append_receipt("result", output_path, result)
    print(json.dumps({"tool": "apply_audit_repairs", "path": str(output_path), "applied": len(result["applied"])}, sort_keys=True))
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
