from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict

from admin_utils import require_admin_banner, require_lumos_approval
from logging_config import get_log_path
import audit_immutability as ai

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()


def _read_legacy(path: Path) -> List[Dict[str, object]]:
    """Parse legacy log entries that may span multiple lines."""
    raw_lines = path.read_text(encoding="utf-8").splitlines()
    entries: List[Dict[str, object]] = []
    buf = ""
    for line in raw_lines:
        if not line.strip():
            continue
        buf += line.strip()
        try:
            entry = json.loads(buf)
        except json.JSONDecodeError:
            buf += " "
            continue
        entries.append(entry)
        buf = ""
    if buf:
        try:
            entries.append(json.loads(buf))
        except Exception:
            pass
    return entries


def convert(path: Path, dest: Path | None = None) -> Path:
    """Convert a legacy audit log into rolling-hash format."""
    entries = _read_legacy(path)
    prev = "0" * 64
    converted: List[Dict[str, object]] = []
    for e in entries:
        ts = str(e.get("timestamp")) if "timestamp" in e else datetime.utcnow().isoformat()
        data = {k: v for k, v in e.items() if k != "timestamp"}
        digest = ai._hash_entry(ts, data, prev)
        converted.append(
            {
                "timestamp": ts,
                "data": data,
                "prev_hash": prev,
                "rolling_hash": digest,
            }
        )
        prev = digest
    dest = dest or path.with_suffix(path.suffix + ".converted")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8") as f:
        for entry in converted:
            f.write(json.dumps(entry) + "\n")
    mig = get_log_path("migration_ledger.jsonl")
    with mig.open("a", encoding="utf-8") as mf:
        mf.write(
            json.dumps({
                "timestamp": datetime.utcnow().isoformat(),
                "converted": str(path),
                "output": str(dest),
            })
            + "\n"
        )
    return dest


def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Legacy log converter")
    ap.add_argument("log", help="legacy log file")
    ap.add_argument("--out", help="destination path")
    args = ap.parse_args()
    out = convert(Path(args.log), Path(args.out) if args.out else None)
    print(out)


if __name__ == "__main__":  # pragma: no cover
    main()
