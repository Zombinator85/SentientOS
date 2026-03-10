from __future__ import annotations

import argparse
from pathlib import Path

import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sentientos.attestation import canonical_json_bytes
from sentientos.node_operations import run_bootstrap


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap local SentientOS node and generate cockpit artifacts")
    parser.add_argument("--reason", default="operator_node_bootstrap", help="operator reason included in restoration provenance")
    parser.add_argument("--seed-minimal", action="store_true", help="seed minimal local-node prerequisites like immutable manifest if missing")
    parser.add_argument("--no-restore", action="store_true", help="skip restoration/re-anchor flow")
    parser.add_argument("--json", action="store_true", help="print canonical JSON report")
    args = parser.parse_args(argv)

    payload = run_bootstrap(Path.cwd().resolve(), reason=str(args.reason), seed_minimal=bool(args.seed_minimal), allow_restore=not bool(args.no_restore))
    if args.json:
        print(canonical_json_bytes(payload).decode("utf-8"), end="")
    else:
        print(
            f"health_state={payload.get('health_state')} constitution_state={payload.get('constitution_state')} "
            f"report_path={payload.get('report_path')}"
        )
    return int(payload.get("exit_code", 3))


if __name__ == "__main__":
    raise SystemExit(main())
