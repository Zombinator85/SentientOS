from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

"""Helper to sync or replay migration ledger entries across nodes."""

import argparse
import json
import shutil
import hashlib
from pathlib import Path
from typing import List, Dict

LEDGER = Path("logs/migration_ledger.jsonl")


def load_ledger() -> List[Dict[str, str]]:
    if not LEDGER.exists():
        return []
    lines = LEDGER.read_text().splitlines()
    return [json.loads(l) for l in lines if l.strip()]


def verify_entry(entry: Dict[str, str]) -> bool:
    path = Path(entry["path"])
    if not path.exists():
        return False
    last = path.read_text().splitlines()[-1]
    checksum = "sha256:" + hashlib.sha256(last.encode("utf-8")).hexdigest()
    return checksum == entry.get("checksum")


def sync_logs(dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for entry in load_ledger():
        src = Path(entry["path"])
        if src.exists() and verify_entry(entry):
            shutil.copy2(src, dest / src.name)


def main() -> None:  # pragma: no cover - CLI helper
    parser = argparse.ArgumentParser(description="Sync or replay ledger entries")
    parser.add_argument("--sync", type=Path, help="Destination directory for logs", required=True)
    args = parser.parse_args()
    sync_logs(args.sync)


if __name__ == "__main__":
    main()

