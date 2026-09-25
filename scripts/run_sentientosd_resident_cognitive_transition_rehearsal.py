from __future__ import annotations

import argparse
import json
from pathlib import Path

from sentientos.resident_cognitive_model_transition_rehearsal import run


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the synthetic actual-sentientosd-composition resident transition rehearsal")
    parser.add_argument("run", nargs="?", default="run")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    result = run(args.root, live_operator_ingress=True)
    required = ("actual_daemon_composition_helper_exercised",
                "daemon_transition_slot_is_resident_slot",
                "daemon_transition_gate_is_resident_gate",
                "fixed_protocol_custody_loaded")
    if any(result.get(key) is not True for key in required):
        raise RuntimeError("actual_daemon_composition_rehearsal_incomplete")
    if args.summary:
        print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
