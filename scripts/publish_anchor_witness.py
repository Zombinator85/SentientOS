from __future__ import annotations

import argparse
import json
from pathlib import Path

from sentientos.anchor_witness import maybe_publish_anchor_witness


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish latest anchor witness")
    parser.add_argument("--repo-root", default=".", help="Repository root")
    args = parser.parse_args(argv)

    status, error = maybe_publish_anchor_witness(Path(args.repo_root).resolve())
    payload = {
        "tool": "publish_anchor_witness",
        "status": status,
        "error": error,
    }
    print(json.dumps(payload, sort_keys=True))
    return 1 if error else 0


if __name__ == "__main__":
    raise SystemExit(main())
