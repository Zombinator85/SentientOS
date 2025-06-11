from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List

from sentientos.privilege import require_admin_banner, require_lumos_approval
import audit_immutability as ai

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()


def _load(path: Path) -> List[ai.AuditEntry]:
    return ai.read_entries(path)


def merge_logs(ours: Path, theirs: Path, dest: Path) -> Path:
    """Merge two audit logs by common prefix."""
    a = _load(ours)
    b = _load(theirs)
    i = 0
    while i < min(len(a), len(b)) and a[i].rolling_hash == b[i].rolling_hash:
        i += 1
    merged = a[:i] + b[i:]
    prev = "0" * 64
    out: List[ai.AuditEntry] = []
    for e in merged:
        digest = ai._hash_entry(e.timestamp, e.data, prev)
        out.append(ai.AuditEntry(e.timestamp, e.data, prev, digest))
        prev = digest
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8") as f:
        for e in out:
            f.write(json.dumps(e.__dict__) + "\n")
    return dest


def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Federated ledger conflict resolver")
    ap.add_argument("ours")
    ap.add_argument("theirs")
    ap.add_argument("dest")
    args = ap.parse_args()
    out = merge_logs(Path(args.ours), Path(args.theirs), Path(args.dest))
    print(out)


if __name__ == "__main__":  # pragma: no cover
    main()
