"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import json
import time
import hashlib
from pathlib import Path
from typing import Any

LEDGER_PATH = Path("logs/migration_ledger.jsonl")


def record_ledger(log_id: str, entry_type: str, path: str, line: str) -> None:
    """Append a migration ledger record.

    Args:
        log_id: Identifier for the log entry (e.g. dialogue id).
        entry_type: Type of log entry ("presence", "summary", "federation").
        path: File path where the entry was written.
        line: The JSON line that was written to the log file.
    """
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    checksum = hashlib.sha256(line.encode("utf-8")).hexdigest()
    entry: dict[str, Any] = {
        "id": log_id,
        "type": entry_type,
        "ts": time.time(),
        "path": path,
        "checksum": f"sha256:{checksum}",
    }
    with LEDGER_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


__all__ = ["record_ledger"]

