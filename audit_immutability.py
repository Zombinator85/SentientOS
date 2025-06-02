from __future__ import annotations
import hashlib
import json
import os
import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import List

from admin_utils import require_admin_banner

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

@dataclass
class AuditEntry:
    timestamp: str
    data: dict
    prev_hash: str
    hash: str


def _hash_entry(timestamp: str, data: dict, prev_hash: str) -> str:
    h = hashlib.sha256()
    h.update(timestamp.encode("utf-8"))
    h.update(json.dumps(data, sort_keys=True).encode("utf-8"))
    h.update(prev_hash.encode("utf-8"))
    return h.hexdigest()


def append_entry(path: Path, data: dict) -> AuditEntry:
    entries = read_entries(path)
    prev = entries[-1].hash if entries else "0" * 64
    ts = datetime.datetime.utcnow().isoformat()
    digest = _hash_entry(ts, data, prev)
    entry = AuditEntry(ts, data, prev, digest)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry.__dict__) + "\n")
    return entry


def read_entries(path: Path) -> List[AuditEntry]:
    if not path.exists():
        return []
    out: List[AuditEntry] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        out.append(AuditEntry(**raw))
    return out


def verify(path: Path) -> bool:
    entries = read_entries(path)
    prev = "0" * 64
    for e in entries:
        expect = _hash_entry(e.timestamp, e.data, prev)
        if e.hash != expect:
            return False
        prev = e.hash
    return True


def cli() -> None:
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Audit log verifier")
    ap.add_argument("log")
    args = ap.parse_args()
    path = Path(args.log)
    ok = verify(path)
    print("valid" if ok else "tampered")

if __name__ == "__main__":
    cli()
