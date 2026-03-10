from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse

from sentientos.ops import main as ops_main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic System Constitution surface")
    parser.add_argument("--repo-root", help="repository root (defaults to current working directory)")
    parser.add_argument("--json", action="store_true", help="compose/write constitution and print canonical JSON")
    parser.add_argument("--latest", action="store_true", help="print latest constitution summary")
    parser.add_argument("--verify", action="store_true", help="verify constitution composition and return constitutional exit code")
    args = parser.parse_args(argv)

    selected = int(args.json) + int(args.latest) + int(args.verify)
    if selected != 1:
        parser.error("choose exactly one of --json, --latest, or --verify")

    forwarded = []
    if args.repo_root:
        forwarded.extend(["--repo-root", args.repo_root])
    if args.verify:
        forwarded.extend(["constitution", "verify"])
    elif args.latest:
        forwarded.extend(["constitution", "latest"])
    else:
        forwarded.extend(["constitution", "json", "--json"])
    return int(ops_main(forwarded, prog="system_constitution"))


if __name__ == "__main__":
    raise SystemExit(main())
