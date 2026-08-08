from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sentientos.discernment_trial import BlindTrialCustody


def _load(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict): raise ValueError("JSON input must be an object")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Blind comparative discernment trial (JSON only)")
    parser.add_argument("--root", required=True); commands = parser.add_subparsers(dest="command", required=True)
    for name in ("create-trial", "record-evidence"):
        command = commands.add_parser(name); command.add_argument("--request", required=True)
    register = commands.add_parser("register-participant"); register.add_argument("--opaque-id", required=True); register.add_argument("--identity", required=True)
    submit = commands.add_parser("submit"); submit.add_argument("--opaque-id", required=True); submit.add_argument("--request", required=True)
    commands.add_parser("trial-state"); commands.add_parser("review"); commands.add_parser("compare"); commands.add_parser("reveal")
    inspect = commands.add_parser("inspect"); inspect.add_argument("kind", choices=("trial", "trial-state", "judgment", "evidence", "comparison", "reveal")); inspect.add_argument("--opaque-id")
    args = parser.parse_args(argv); custody = BlindTrialCustody(args.root)
    if args.command == "create-trial": result = custody.create_trial(_load(args.request))
    elif args.command == "register-participant": result = custody.register_participant(args.opaque_id, args.identity)
    elif args.command == "submit": result = custody.submit(args.opaque_id, _load(args.request))
    elif args.command == "trial-state": result = custody.trial_state()
    elif args.command == "record-evidence": result = custody.record_evidence(_load(args.request))
    elif args.command == "review": result = custody.review()
    elif args.command == "compare": result = custody.compare()
    elif args.command == "reveal": result = custody.reveal()
    else: result = custody.inspect(args.kind, args.opaque_id)
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False)); return 0


if __name__ == "__main__": raise SystemExit(main())
