from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sentientos.signed_strategic import verify_latest


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify strategic signatures")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--last", "--last-n", dest="last", type=int, default=20)
    args = parser.parse_args()

    ok, reason = verify_latest(repo_root=Path(args.repo_root).resolve(), last=args.last)
    status = "ok" if ok else "failed"
    print(json.dumps({"tool": "verify_strategic_signatures", "status": status, "reason": reason, "last": args.last}, indent=2, sort_keys=True))
    if ok:
        return 0
    if os.getenv("SENTIENTOS_STRATEGIC_SIG_ENFORCE", "0") == "1":
        return 2
    if os.getenv("SENTIENTOS_STRATEGIC_SIG_WARN", "0") == "1":
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
