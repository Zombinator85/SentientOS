from __future__ import annotations

from dataclasses import dataclass

from sentientos.forge_daemon import ForgeDaemon
from sentientos.forge_queue import ForgeRequest

from .context import ForgeContext
from .types import print_json


@dataclass(frozen=True)
class GoalArgs:
    goal: str


@dataclass(frozen=True)
class EnqueueArgs:
    goal: str
    priority: int
    requested_by: str


def handle_plan(context: ForgeContext, args: GoalArgs) -> int:
    payload = context.forge.plan(args.goal)
    print_json({"command": "plan", "goal": payload.goal, "generated_at": payload.generated_at})
    return 0


def handle_run(context: ForgeContext, args: GoalArgs) -> int:
    payload = context.forge.run(args.goal)
    print_json(
        {
            "command": "run",
            "goal": payload.goal,
            "goal_id": payload.goal_id,
            "goal_profile": payload.goal_profile,
            "generated_at": payload.generated_at,
            "outcome": payload.outcome,
            "failure_reasons": payload.failure_reasons,
            "ci_commands_run": payload.ci_commands_run,
            "session_root": payload.session.root_path,
            "provenance_run_id": payload.provenance_run_id,
            "provenance_path": payload.provenance_path,
        }
    )
    return 0 if payload.outcome == "success" else 1


def handle_enqueue(context: ForgeContext, args: EnqueueArgs) -> int:
    request_id = context.queue.enqueue(
        ForgeRequest(request_id="", goal=args.goal, requested_by=args.requested_by, priority=args.priority)
    )
    print_json({"command": "enqueue", "request_id": request_id, "goal": args.goal})
    return 0


def handle_queue(context: ForgeContext) -> int:
    pending = context.queue.pending_requests()
    print_json(
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
        }
    )
    return 0


def handle_receipts(context: ForgeContext) -> int:
    receipts = context.queue.recent_receipts()
    print_json(
        {
            "command": "receipts",
            "receipts": [
                {
                    "request_id": item.request_id,
                    "status": item.status,
                    "finished_at": item.finished_at,
                    "report_path": item.report_path,
                    "provenance_run_id": item.provenance_run_id,
                    "provenance_path": item.provenance_path,
                    "publish_status": item.publish_status,
                    "publish_pr_url": item.publish_pr_url,
                    "publish_checks_overall": item.publish_checks_overall,
                }
                for item in receipts
            ],
        }
    )
    return 0


def handle_run_daemon_tick(context: ForgeContext) -> int:
    ForgeDaemon(queue=context.queue).run_tick()
    print_json({"command": "run-daemon-tick", "status": "ok"})
    return 0
