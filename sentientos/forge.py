"""CLI entrypoint for CathedralForge."""

from __future__ import annotations

import argparse
import json

from sentientos.cathedral_forge import CathedralForge


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m sentientos.forge", description="CathedralForge repo-wide orchestrator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan", help="Generate a forge plan")
    plan_parser.add_argument("goal", help="Forge goal description")

    run_parser = subparsers.add_parser("run", help="Execute forge preflight and test gates")
    run_parser.add_argument("goal", help="Forge goal description")

    args = parser.parse_args(argv)
    forge = CathedralForge()

    if args.command == "plan":
        payload = forge.plan(args.goal)
        print(json.dumps({"command": "plan", "goal": payload.goal, "generated_at": payload.generated_at}, sort_keys=True))
        return 0

    payload = forge.run(args.goal)
    print(
        json.dumps(
            {
                "command": "run",
                "goal": payload.goal,
                "generated_at": payload.generated_at,
                "outcome": payload.outcome,
                "failure_reasons": payload.failure_reasons,
            },
            sort_keys=True,
        )
    )
    return 0 if payload.outcome == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
