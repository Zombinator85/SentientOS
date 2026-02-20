from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sentientos.event_stream import record_forge_event
from sentientos.receipt_chain import rebuild_receipts_index, verify_receipt_chain


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify forge receipt hash chain")
    parser.add_argument("--last", type=int, default=None, help="Verify only the last N receipts")
    parser.add_argument("--repair-index", action="store_true", help="Rebuild receipts_index.jsonl from receipt files")
    args = parser.parse_args()

    repo_root = Path.cwd()
    if args.repair_index:
        rows = rebuild_receipts_index(repo_root)
        print(json.dumps({"repaired": True, "rows": len(rows)}, sort_keys=True))

    result = verify_receipt_chain(repo_root, last=args.last)
    payload = result.to_dict()
    print(json.dumps(payload, sort_keys=True))

    if result.ok:
        return 0

    enforce = os.getenv("SENTIENTOS_RECEIPT_CHAIN_ENFORCE", "0") == "1"
    warn = os.getenv("SENTIENTOS_RECEIPT_CHAIN_WARN", "0") == "1"
    if warn:
        print("WARNING: receipt chain is broken", flush=True)
        if (repo_root / "glow/forge").exists():
            record_forge_event({"event": "receipt_chain_warning", "level": "warning", "chain": payload})
    return 1 if enforce else 0


if __name__ == "__main__":
    raise SystemExit(main())
