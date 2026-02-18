"""CLI entrypoint for CathedralForge and daemon queue operations."""

from __future__ import annotations

import argparse
import json

from sentientos.cathedral_forge import CathedralForge
from sentientos.forge_daemon import ForgeDaemon
from sentientos.forge_env_cache import list_cache_entries, prune_cache
from sentientos.forge_queue import ForgeQueue, ForgeRequest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m sentientos.forge", description="CathedralForge repo-wide orchestrator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan", help="Generate a forge plan")
    plan_parser.add_argument("goal", help="Forge goal description")

    run_parser = subparsers.add_parser("run", help="Execute forge preflight and test gates")
    run_parser.add_argument("goal", help="Forge goal description")

    enqueue_parser = subparsers.add_parser("enqueue", help="Queue a forge request")
    enqueue_parser.add_argument("goal", help="Forge goal description")
    enqueue_parser.add_argument("--priority", type=int, default=100, help="Lower number is higher priority")
    enqueue_parser.add_argument("--requested-by", default="operator", help="Requester identity")

    subparsers.add_parser("queue", help="List pending queue entries")
    subparsers.add_parser("receipts", help="List recent forge receipts")
    subparsers.add_parser("run-daemon-tick", help="Run a single daemon tick")
    subparsers.add_parser("env-cache", help="List shared ForgeEnv cache entries")
    subparsers.add_parser("env-cache-prune", help="Prune shared ForgeEnv cache entries")

    args = parser.parse_args(argv)
    forge = CathedralForge()
    queue = ForgeQueue()

    if args.command == "plan":
        plan_payload = forge.plan(args.goal)
        print(json.dumps({"command": "plan", "goal": plan_payload.goal, "generated_at": plan_payload.generated_at}, sort_keys=True))
        return 0

    if args.command == "run":
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

    if args.command == "enqueue":
        request_id = queue.enqueue(
            ForgeRequest(
                request_id="",
                goal=args.goal,
                requested_by=args.requested_by,
                priority=args.priority,
            )
        )
        print(json.dumps({"command": "enqueue", "request_id": request_id, "goal": args.goal}, sort_keys=True))
        return 0

    if args.command == "queue":
        pending = queue.pending_requests()
        print(
            json.dumps(
                {
                    "command": "queue",
                    "pending": [
                        {
                            "request_id": item.request_id,
                            "goal": item.goal,
                            "priority": item.priority,
                            "requested_at": item.requested_at,
                        }
                        for item in pending
                    ],
                },
                sort_keys=True,
            )
        )
        return 0

    if args.command == "receipts":
        receipts = queue.recent_receipts()
        print(
            json.dumps(
                {
                    "command": "receipts",
                    "receipts": [
                        {
                            "request_id": item.request_id,
                            "status": item.status,
                            "finished_at": item.finished_at,
                            "report_path": item.report_path,
                        }
                        for item in receipts
                    ],
                },
                sort_keys=True,
            )
        )
        return 0


    if args.command == "env-cache":
        entries = list_cache_entries(forge.repo_root)
        print(
            json.dumps(
                {
                    "command": "env-cache",
                    "entries": [
                        {
                            "venv_path": item.venv_path,
                            "last_used_at": item.last_used_at,
                            "created_at": item.created_at,
                            "extras_tag": item.key.extras_tag,
                            "python_version": item.key.python_version,
                        }
                        for item in entries
                    ],
                },
                sort_keys=True,
            )
        )
        return 0

    if args.command == "env-cache-prune":
        removed = prune_cache(forge.repo_root)
        print(json.dumps({"command": "env-cache-prune", "removed": removed, "removed_count": len(removed)}, sort_keys=True))
        return 0

    daemon = ForgeDaemon(queue=queue)
    daemon.run_tick()
    print(json.dumps({"command": "run-daemon-tick", "status": "ok"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
