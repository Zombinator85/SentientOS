from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sentientos.attestation_snapshot import verify_recent_snapshots


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify attestation snapshot signatures")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--last", "--last-n", dest="last", type=int, default=10)
    args = parser.parse_args()

    result = verify_recent_snapshots(Path(args.repo_root).resolve(), last=args.last)
    print(
        json.dumps(
            {
                "tool": "verify_attestation_snapshots",
                "status": result.status,
                "ok": result.ok,
                "reason": result.reason,
                "checked_n": result.checked_n,
                "last_ok_hash": result.last_ok_hash,
            },
            indent=2,
            sort_keys=True,
        )
    )
    if result.status in {"ok", "skipped"}:
        return 0
    if os.getenv("SENTIENTOS_ATTESTATION_SNAPSHOT_ENFORCE", "0") == "1":
        return 2
    if os.getenv("SENTIENTOS_ATTESTATION_SNAPSHOT_WARN", "0") == "1":
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

