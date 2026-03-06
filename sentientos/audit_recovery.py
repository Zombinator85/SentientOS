from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Any

RECOVERY_LEDGER_PATH = Path("glow/forge/audit_reports/audit_recovery_checkpoints.jsonl")


@dataclass(frozen=True)
class RecoveryCheckpoint:
    checkpoint_id: str
    created_at: str
    break_fingerprint: str
    break_path: str
    break_line: int
    expected_prev_hash: str
    found_prev_hash: str
    trusted_history_head_hash: str
    continuation_anchor_prev_hash: str
    continuation_log_path: str
    reason: str
    status: str = "active"

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "checkpoint_id": self.checkpoint_id,
            "created_at": self.created_at,
            "break_fingerprint": self.break_fingerprint,
            "break_path": self.break_path,
            "break_line": self.break_line,
            "expected_prev_hash": self.expected_prev_hash,
            "found_prev_hash": self.found_prev_hash,
            "trusted_history_head_hash": self.trusted_history_head_hash,
            "continuation_anchor_prev_hash": self.continuation_anchor_prev_hash,
            "continuation_log_path": self.continuation_log_path,
            "reason": self.reason,
            "status": self.status,
        }


def break_fingerprint(*, path: str, line_number: int, expected_prev_hash: str, found_prev_hash: str) -> str:
    payload = {
        "line_number": int(line_number),
        "path": str(path),
        "expected_prev_hash": str(expected_prev_hash),
        "found_prev_hash": str(found_prev_hash),
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return f"break:{digest}"


def checkpoint_id_from_payload(payload: dict[str, object]) -> str:
    canon = {k: v for k, v in payload.items() if k != "checkpoint_id"}
    digest = hashlib.sha256(json.dumps(canon, sort_keys=True).encode("utf-8")).hexdigest()
    return f"reanchor:{digest[:16]}"


def load_checkpoints(repo_root: Path) -> list[RecoveryCheckpoint]:
    path = repo_root / RECOVERY_LEDGER_PATH
    if not path.exists():
        return []
    rows: list[RecoveryCheckpoint] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(raw, dict):
            continue
        try:
            row = RecoveryCheckpoint(
                checkpoint_id=str(raw.get("checkpoint_id", "")),
                created_at=str(raw.get("created_at", "")),
                break_fingerprint=str(raw.get("break_fingerprint", "")),
                break_path=str(raw.get("break_path", "")),
                break_line=int(raw.get("break_line", 0)),
                expected_prev_hash=str(raw.get("expected_prev_hash", "")),
                found_prev_hash=str(raw.get("found_prev_hash", "")),
                trusted_history_head_hash=str(raw.get("trusted_history_head_hash", "")),
                continuation_anchor_prev_hash=str(raw.get("continuation_anchor_prev_hash", "")),
                continuation_log_path=str(raw.get("continuation_log_path", "")),
                reason=str(raw.get("reason", "")),
                status=str(raw.get("status", "active")),
            )
        except Exception:
            continue
        if row.checkpoint_id and row.break_fingerprint:
            rows.append(row)
    return rows


def append_checkpoint(repo_root: Path, checkpoint: RecoveryCheckpoint) -> Path:
    path = repo_root / RECOVERY_LEDGER_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_CREAT | os.O_APPEND | os.O_WRONLY
    fd = os.open(path, flags, 0o644)
    with os.fdopen(fd, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(checkpoint.to_dict(), sort_keys=True) + "\n")
    return path


def first_continuation_entry(repo_root: Path, log_path: str) -> dict[str, Any] | None:
    path = repo_root / log_path
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(raw, dict):
            return raw
    return None
