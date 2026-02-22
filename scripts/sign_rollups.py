from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sentientos.signed_rollups import sign_existing_unsigned_rollups


def main() -> int:
    parser = argparse.ArgumentParser(description="Sign existing rollups")
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()

    if os.getenv("SENTIENTOS_ROLLUP_SIGN_EXISTING", "0") != "1":
        print(json.dumps({"tool": "sign_rollups", "status": "blocked", "reason": "set SENTIENTOS_ROLLUP_SIGN_EXISTING=1"}, indent=2, sort_keys=True))
        return 1

    signed = sign_existing_unsigned_rollups(Path(args.repo_root).resolve())
    print(json.dumps({"tool": "sign_rollups", "status": "ok", "signed_count": len(signed), "last_rollup_id": signed[-1].rollup_id if signed else None}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
