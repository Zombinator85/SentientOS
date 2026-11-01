from __future__ import annotations

import argparse
import json
from pathlib import Path

from sentientos.formal_verification import run_formal_verification


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run SentientOS bounded formal model checks")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--spec", action="append", default=[])
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = run_formal_verification(Path(args.repo_root).resolve(), selected_specs=list(args.spec or []))
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        artifact_paths = payload.get("artifact_paths")
        summary_path = artifact_paths.get("summary") if isinstance(artifact_paths, dict) else None
        print(
            f"status={payload.get('status')} spec_count={payload.get('spec_count')} "
            f"summary={summary_path}"
        )
    return 0 if payload.get("status") == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
