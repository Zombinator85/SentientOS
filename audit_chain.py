"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import argparse
import datetime
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List
from cathedral_const import validate_log_entry
@dataclass
class AuditEntry:
    timestamp: str
    data: dict[str, object]
    prev_hash: str
    rolling_hash: str

    @property
    def hash(self) -> str:  # backward compatibility
        return self.rolling_hash


def _hash_entry(timestamp: str, data: dict[str, object], prev_hash: str) -> str:
    h = hashlib.sha256()
    h.update(timestamp.encode("utf-8"))
    h.update(json.dumps(data, sort_keys=True).encode("utf-8"))
    h.update(prev_hash.encode("utf-8"))
    return h.hexdigest()


def append_entry(
    path: Path,
    data: dict[str, object],
    emotion: str = "neutral",
    consent: bool | str = True,
) -> AuditEntry:
    """Append an entry enforcing chain integrity and metadata."""
    entries = read_entries(path)
    if entries:
        last = entries[-1]
        expected = _hash_entry(last.timestamp, last.data, last.prev_hash)
        if expected != last.rolling_hash:
            raise ValueError("audit chain broken before append")
        prev = last.rolling_hash
    else:
        prev = "0" * 64

    data = dict(data)
    data["emotion"] = emotion
    data["consent"] = consent
    ts = datetime.datetime.utcnow().isoformat()
    digest = _hash_entry(ts, data, prev)
    entry = AuditEntry(ts, data, prev, digest)

    # enforce schema
    validate_log_entry({"timestamp": entry.timestamp, "data": entry.data})

    # atomic append
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    with tmp_path.open("w", encoding="utf-8") as f:
        if existing:
            f.write(existing)
            if not existing.endswith("\n"):
                f.write("\n")
        f.write(json.dumps(entry.__dict__) + "\n")
    os.replace(tmp_path, path)
    return entry


def read_entries(path: Path) -> List[AuditEntry]:
    if not path.exists():
        return []
    out: List[AuditEntry] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "rolling_hash" not in raw and "hash" in raw:
            raw["rolling_hash"] = raw["hash"]
        out.append(AuditEntry(**raw))
    return out


def verify(path: Path) -> bool:
    entries = read_entries(path)
    prev = "0" * 64
    for e in entries:
        expect = _hash_entry(e.timestamp, e.data, prev)
        current = e.rolling_hash
        if current != expect:
            return False
        prev = current
    return True


def cli() -> None:
    ap = argparse.ArgumentParser(description="Audit log verifier")
    ap.add_argument("log")
    args = ap.parse_args()
    path = Path(args.log)
    ok = verify(path)
    print("valid" if ok else "tampered")

if __name__ == "__main__":
    cli()
