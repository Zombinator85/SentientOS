from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

from sentientos.artifact_catalog import append_catalog_entry

RECEIPTS_DIR = Path("glow/forge/receipts")
RECEIPTS_INDEX_PATH = RECEIPTS_DIR / "receipts_index.jsonl"


@dataclass(slots=True)
class ChainBreak:
    receipt_id: str
    reason: str
    expected: str | None = None
    found: str | None = None


@dataclass(slots=True)
class ReceiptChainVerification:
    status: str
    checked_at: str
    checked_count: int
    break_info: ChainBreak | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "status": self.status,
            "checked_at": self.checked_at,
            "checked_count": self.checked_count,
        }
        if self.break_info is not None:
            payload["break"] = {
                "receipt_id": self.break_info.receipt_id,
                "reason": self.break_info.reason,
                "expected": self.break_info.expected,
                "found": self.break_info.found,
            }
        return payload


def canonical_receipt_bytes(payload: dict[str, object]) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def compute_receipt_hash(payload_without_hash: dict[str, object]) -> str:
    return hashlib.sha256(canonical_receipt_bytes(payload_without_hash)).hexdigest()


def verify_receipt_chain(repo_root: Path, *, last: int | None = None) -> ReceiptChainVerification:
    records = _load_receipt_records(repo_root)
    checked_at = _iso_now()
    if not records:
        return ReceiptChainVerification(status="unknown", checked_at=checked_at, checked_count=0)

    start = max(0, len(records) - last) if isinstance(last, int) and last > 0 else 0
    prior_hash = records[start - 1].get("receipt_hash") if start > 0 else None
    if start > 0 and not isinstance(prior_hash, str):
        prior_hash = None

    for idx in range(start, len(records)):
        record = records[idx]
        receipt_id = _as_str(record.get("receipt_id")) or f"index-{idx}"
        found_hash = _as_str(record.get("receipt_hash"))
        if not found_hash:
            return ReceiptChainVerification(
                status="broken",
                checked_at=checked_at,
                checked_count=idx - start + 1,
                break_info=ChainBreak(receipt_id=receipt_id, reason="receipt_hash_missing", expected=None, found=None),
            )

        unsigned = dict(record)
        unsigned.pop("receipt_hash", None)
        expected_hash = compute_receipt_hash(unsigned)
        if expected_hash != found_hash:
            return ReceiptChainVerification(
                status="broken",
                checked_at=checked_at,
                checked_count=idx - start + 1,
                break_info=ChainBreak(receipt_id=receipt_id, reason="receipt_hash_mismatch", expected=expected_hash, found=found_hash),
            )

        found_prev = _as_str(record.get("prev_receipt_hash"))
        expected_prev = prior_hash if isinstance(prior_hash, str) and prior_hash else None
        if found_prev != expected_prev:
            return ReceiptChainVerification(
                status="broken",
                checked_at=checked_at,
                checked_count=idx - start + 1,
                break_info=ChainBreak(receipt_id=receipt_id, reason="prev_receipt_hash_mismatch", expected=expected_prev, found=found_prev),
            )
        prior_hash = found_hash

    return ReceiptChainVerification(status="ok", checked_at=checked_at, checked_count=len(records) - start)


def maybe_verify_receipt_chain(repo_root: Path, *, context: str, last: int = 25) -> tuple[ReceiptChainVerification | None, bool, bool]:
    enforce = os.getenv("SENTIENTOS_RECEIPT_CHAIN_ENFORCE", "0") == "1"
    warn = os.getenv("SENTIENTOS_RECEIPT_CHAIN_WARN", "0") == "1"
    if not enforce and not warn:
        return None, False, False
    result = verify_receipt_chain(repo_root, last=last)
    return result, enforce and not result.ok, warn and not enforce and not result.ok


def append_receipt(repo_root: Path, payload: dict[str, object]) -> dict[str, object]:
    receipts_dir = repo_root / RECEIPTS_DIR
    receipts_dir.mkdir(parents=True, exist_ok=True)
    previous_hash = latest_receipt_hash(repo_root)
    payload_with_prev = dict(payload)
    payload_with_prev["prev_receipt_hash"] = previous_hash
    payload_with_prev["receipt_hash"] = compute_receipt_hash(payload_with_prev)

    receipt_id = _as_str(payload_with_prev.get("receipt_id")) or "receipt"
    safe_id = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in receipt_id)
    receipt_path = receipts_dir / f"merge_receipt_{safe_id}.json"
    _write_json_atomic(receipt_path, payload_with_prev)

    index_row = {
        "receipt_id": payload_with_prev.get("receipt_id"),
        "created_at": payload_with_prev.get("created_at"),
        "receipt_hash": payload_with_prev.get("receipt_hash"),
        "prev_receipt_hash": payload_with_prev.get("prev_receipt_hash"),
        "pr_number": payload_with_prev.get("pr_number"),
        "head_sha": payload_with_prev.get("head_sha"),
        "bundle_sha256": _extract_bundle_sha(payload_with_prev),
    }
    _append_jsonl_atomic(repo_root / RECEIPTS_INDEX_PATH, index_row)
    append_catalog_entry(
        repo_root,
        kind="receipt",
        artifact_id=_as_str(payload_with_prev.get("receipt_id")) or safe_id,
        relative_path=str(receipt_path.relative_to(repo_root)),
        schema_name="receipt",
        schema_version=int(payload_with_prev.get("schema_version") or 1),
        links={"pr_number": payload_with_prev.get("pr_number"), "head_sha": payload_with_prev.get("head_sha"), "receipt_hash": payload_with_prev.get("receipt_hash")},
        summary={"status": "recorded"},
        ts=_as_str(payload_with_prev.get("created_at")) or _iso_now(),
    )
    return payload_with_prev


def rebuild_receipts_index(repo_root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for record in _load_receipt_records(repo_root):
        rows.append(
            {
                "receipt_id": record.get("receipt_id"),
                "created_at": record.get("created_at"),
                "receipt_hash": record.get("receipt_hash"),
                "prev_receipt_hash": record.get("prev_receipt_hash"),
                "pr_number": record.get("pr_number"),
                "head_sha": record.get("head_sha"),
                "bundle_sha256": _extract_bundle_sha(record),
            }
        )
    _write_jsonl_atomic(repo_root / RECEIPTS_INDEX_PATH, rows)
    return rows


def latest_receipt_hash(repo_root: Path) -> str | None:
    index_path = repo_root / RECEIPTS_INDEX_PATH
    if index_path.exists():
        rows = _read_jsonl(index_path)
        for row in reversed(rows):
            value = _as_str(row.get("receipt_hash"))
            if value:
                return value
    for record in reversed(_load_receipt_records(repo_root)):
        value = _as_str(record.get("receipt_hash"))
        if value:
            return value
    return None


def latest_receipt(repo_root: Path) -> dict[str, object] | None:
    records = _load_receipt_records(repo_root)
    return records[-1] if records else None


def _load_receipt_records(repo_root: Path) -> list[dict[str, object]]:
    receipts_dir = repo_root / RECEIPTS_DIR
    records: list[dict[str, object]] = []
    for path in sorted(receipts_dir.glob("merge_receipt_*.json"), key=lambda item: item.name):
        payload = _load_json(path)
        if not payload:
            continue
        if "created_at" not in payload and isinstance(payload.get("merged_at"), str):
            payload["created_at"] = payload.get("merged_at")
        if "receipt_id" not in payload:
            payload["receipt_id"] = path.stem.replace("merge_receipt_", "")
        records.append(payload)
    records.sort(key=lambda item: (str(item.get("created_at", "")), str(item.get("receipt_id", ""))))
    return records


def _extract_bundle_sha(payload: dict[str, object]) -> str | None:
    doctrine = payload.get("doctrine_identity")
    if not isinstance(doctrine, dict):
        return None
    value = doctrine.get("bundle_sha256")
    return value if isinstance(value, str) and value else None


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows: list[dict[str, object]] = []
    for line in lines:
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def _append_jsonl_atomic(path: Path, row: dict[str, object]) -> None:
    existing = _read_jsonl(path)
    existing.append(row)
    _write_jsonl_atomic(path, existing)


def _write_jsonl_atomic(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    body = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    tmp_path.write_text(body, encoding="utf-8")
    tmp_path.replace(path)


def _load_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _as_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
