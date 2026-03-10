from __future__ import annotations

import argparse
from pathlib import Path

import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sentientos.attestation import canonical_json_bytes
from sentientos.node_operations import node_health


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Unified local node health surface")
    parser.add_argument("--json", action="store_true", help="print canonical JSON health report")
    args = parser.parse_args(argv)

    payload = node_health(Path.cwd().resolve())
    if args.json:
        print(canonical_json_bytes(payload).decode("utf-8"), end="")
    else:
        print(
            f"health_state={payload.get('health_state')} constitution_state={payload.get('constitution_state')} "
            f"integrity={payload.get('integrity_overall')}"
        )
    return int(payload.get("exit_code", 3))


if __name__ == "__main__":
    raise SystemExit(main())
