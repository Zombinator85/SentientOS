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
        plan_payload = forge.plan(args.goal)
        print(json.dumps({"command": "plan", "goal": plan_payload.goal, "generated_at": plan_payload.generated_at}, sort_keys=True))
        return 0

    run_payload = forge.run(args.goal)
    print(
        json.dumps(
            {
                "command": "run",
                "goal": run_payload.goal,
                "goal_id": run_payload.goal_id,
                "goal_profile": run_payload.goal_profile,
                "generated_at": run_payload.generated_at,
                "outcome": run_payload.outcome,
                "failure_reasons": run_payload.failure_reasons,
                "ci_commands_run": run_payload.ci_commands_run,
                "session_root": run_payload.session.root_path,
            },
            sort_keys=True,
        )
    )
    return 0 if run_payload.outcome == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
