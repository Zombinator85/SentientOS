from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Mapping


class ConsentMemoryVault:
    """Persist explicit permissions, denials, and revisions for downstream privilege checks."""

    def __init__(self, storage_path: str | Path) -> None:
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

    def log_consent(
        self,
        capability: str,
        *,
        status: str,
        context: str | None = None,
        timestamp: str | None = None,
    ) -> dict:
        record = {
            "capability": capability,
            "status": status,
            "timestamp": timestamp or datetime.utcnow().isoformat() + "Z",
            "context": context,
        }
        self._append(record)
        return record

    def withdraw(self, capability: str, *, context: str | None = None, timestamp: str | None = None) -> dict:
        return self.log_consent(capability, status="denied", context=context or "retroactive withdrawal", timestamp=timestamp)

    def ever_granted(self, capability: str) -> bool:
        return any(entry for entry in self._load_entries() if entry.get("capability") == capability and entry.get("status") in {"granted", "approved", "allowed"})

    def query(self, capability: str) -> dict | None:
        entries = [entry for entry in self._load_entries() if entry.get("capability") == capability]
        if not entries:
            return None
        latest = entries[-1]
        return {
            "capability": capability,
            "status": latest.get("status"),
            "timestamp": latest.get("timestamp"),
            "context": latest.get("context"),
        }

    def has_active_consent(self, capability: str) -> bool:
        latest = self.query(capability)
        if latest is None:
            return False
        return str(latest.get("status", "")).lower() not in {"denied", "withdrawn"}

    def snapshot(self) -> list[dict]:
        return self._load_entries()

    def _load_entries(self) -> list[dict]:
        if not self.storage_path.exists():
            return []
        entries: list[dict] = []
        with self.storage_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, Mapping):
                    entries.append(dict(parsed))
        return entries

    def _append(self, record: Mapping[str, object]) -> None:
        with self.storage_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


__all__ = ["ConsentMemoryVault"]
