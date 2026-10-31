"""Preregister, run, or score a bounded Codex CLI epistemic-response pilot."""
from __future__ import annotations

import argparse
import json
import sys

from sentientos.codex_subject_epistemic_pilot_runner import (
    preregister, run_observations, score_observations,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    seal = commands.add_parser("preregister", help="seal prompt and separate answer-key digests")
    seal.add_argument("--protocol", required=True)
    seal.add_argument("--answer-keys", required=True)
    seal.add_argument("--receipt", required=True)
    run = commands.add_parser("run", help="run or resume sealed prompt observations")
    run.add_argument("--protocol", required=True)
    run.add_argument("--preregistration", required=True)
    run.add_argument("--output", required=True)
    run.add_argument("--codex", default="codex")
    run.add_argument("--resume", action="store_true",
        help="resume an in-progress checkpoint without repeating recorded or interrupted slots")
    score = commands.add_parser("score", help="score captured responses using held-out keys")
    score.add_argument("--protocol", required=True)
    score.add_argument("--answer-keys", required=True)
    score.add_argument("--preregistration", required=True)
    score.add_argument("--observations", required=True)
    score.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "preregister":
            result = preregister(args.protocol, args.answer_keys, args.receipt)
        elif args.command == "run":
            result = run_observations(args.protocol, args.preregistration,
                args.output, codex_command=args.codex, resume=args.resume)
        else:
            result = score_observations(args.protocol, args.answer_keys,
                args.preregistration, args.observations, args.output)
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps({"status": result.get("run_state", result.get("status", "complete")),
        "pilot_id": result.get("pilot_id"), "output": args.receipt if args.command == "preregister"
        else args.output, "attempted_observations": result.get("attempted_observations")}, sort_keys=True))
    return 0 if result.get("status") not in {"series_failed", "insufficient"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
