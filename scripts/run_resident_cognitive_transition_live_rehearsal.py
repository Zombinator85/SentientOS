from __future__ import annotations

import argparse
import json
from pathlib import Path

from sentientos.resident_cognitive_model_transition_rehearsal import run


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the live-daemon-composition synthetic resident transition rehearsal")
    parser.add_argument("run", nargs="?"); parser.add_argument("--root", required=True); parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    result = run(Path(args.root), live_operator_ingress=True)
    print(json.dumps(result, sort_keys=True) if args.summary else json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
