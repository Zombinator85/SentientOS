from __future__ import annotations

"""JSON-only CLI for bounded live discernment experiment-session custody."""

import argparse
import json
from pathlib import Path

from sentientos.discernment_experiment_session import (
    calibrate, doctor, plan_session, trial_handoff, verify_load, verify_session,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--commissioning-root", type=Path, required=True)
    plan.add_argument("--session-root", type=Path, required=True)
    plan.add_argument("--calibration-root", type=Path, required=True)
    for name in ("doctor", "verify-load", "verify", "handoff"):
        command = sub.add_parser(name); command.add_argument("--session-root", type=Path, required=True)
    run = sub.add_parser("calibrate")
    run.add_argument("--session-root", type=Path, required=True)
    run.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        if args.command == "plan":
            result = plan_session(args.commissioning_root, args.session_root, args.calibration_root)
        elif args.command == "doctor": result = doctor(args.session_root)
        elif args.command == "verify-load": result = verify_load(args.session_root)
        elif args.command == "calibrate": result = calibrate(args.session_root, repo_root=args.repo_root)
        elif args.command == "verify": result = verify_session(args.session_root)
        else: result = trial_handoff(args.session_root)
    except (OSError, ValueError, FileExistsError, json.JSONDecodeError) as exc:
        result = {"status": "commissioning_blocked", "reason_codes": [str(exc)],
                  "semantic_model_generations": 0, "calibration_cases_run": 0}
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0 if result.get("status") in {"planned", "load_verified", "calibration_eligible",
                                         "calibration_ready", "trial_handoff_ready"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
