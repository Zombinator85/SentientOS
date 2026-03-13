from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sentientos.federated_enforcement_policy import write_policy_snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description="Emit unified federated enforcement profile")
    parser.add_argument("--profile", choices=["local-dev-relaxed", "ci-advisory", "federation-enforce"], required=True)
    parser.add_argument("--output", default="glow/contracts/federated_enforcement_policy.json")
    parser.add_argument("--print-env", action="store_true")
    args = parser.parse_args()

    os.environ["SENTIENTOS_ENFORCEMENT_PROFILE"] = args.profile
    payload = write_policy_snapshot(Path(args.output))
    print(json.dumps(payload, sort_keys=True))
    if args.print_env:
        print(f"export SENTIENTOS_ENFORCEMENT_PROFILE={args.profile}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
