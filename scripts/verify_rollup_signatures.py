from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sentientos.signed_rollups import verify_signed_rollups


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify signed rollup envelopes")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--last-weeks", type=int, default=8)
    args = parser.parse_args()

    ok, error = verify_signed_rollups(Path(args.repo_root).resolve(), last_weeks=args.last_weeks)
    payload = {"tool": "verify_rollup_signatures", "ok": ok, "error": error, "last_weeks": args.last_weeks}
    print(json.dumps(payload, indent=2, sort_keys=True))

    warn = os.getenv("SENTIENTOS_ROLLUP_SIG_WARN", "0") == "1"
    enforce = os.getenv("SENTIENTOS_ROLLUP_SIG_ENFORCE", "0") == "1"
    if ok:
        return 0
    if warn and not enforce:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
