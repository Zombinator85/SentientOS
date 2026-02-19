from __future__ import annotations

import argparse
from collections.abc import Sequence

from . import commands_canary, commands_env_cache, commands_observatory, commands_provenance, commands_queue, commands_sentinel, commands_train
from .context import build_context


def build_parser() -> argparse.ArgumentParser:
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
    subparsers.add_parser("status", help="Show live forge daemon status")
    subparsers.add_parser("index", help="Rebuild and print forge observability index")

    subparsers.add_parser("sentinel-status", help="Show Contract Sentinel state")
    subparsers.add_parser("sentinel-enable", help="Enable Contract Sentinel policy")
    subparsers.add_parser("sentinel-disable", help="Disable Contract Sentinel policy")
    subparsers.add_parser("sentinel-run-tick", help="Run a single Contract Sentinel tick")

    show_report_parser = subparsers.add_parser("show-report", help="Pretty-print a forge report by path or id")
    show_report_parser.add_argument("target", help="report path or timestamp id")
    show_docket_parser = subparsers.add_parser("show-docket", help="Pretty-print a forge docket by path or id")
    show_docket_parser.add_argument("target", help="docket path or timestamp id")
    subparsers.add_parser("quarantines", help="List recent quarantines")
    show_quarantine_parser = subparsers.add_parser("show-quarantine", help="Show quarantine by path or id")
    show_quarantine_parser.add_argument("target", help="quarantine path or timestamp id")

    replay_parser = subparsers.add_parser("replay", help="Replay a forge provenance run")
    replay_parser.add_argument("target", help="run_id or provenance bundle path")
    replay_parser.add_argument("--dry-run", action="store_true", help="Print replay plan without executing")

    pr_checks_parser = subparsers.add_parser("pr-checks", help="Show current PR canary checks")
    pr_checks_parser.add_argument("target", help="PR URL or number")
    wait_checks_parser = subparsers.add_parser("wait-checks", help="Wait for PR canary checks")
    wait_checks_parser.add_argument("target", help="PR URL or number")
    wait_checks_parser.add_argument("--timeout", type=int, default=1800, help="Timeout in seconds")

    subparsers.add_parser("train-status", help="Show merge train status")
    subparsers.add_parser("train-enable", help="Enable merge train")
    subparsers.add_parser("train-disable", help="Disable merge train")
    subparsers.add_parser("train-tick", help="Run merge train tick")
    hold_parser = subparsers.add_parser("train-hold", help="Hold a PR in merge train")
    hold_parser.add_argument("pr", type=int, help="PR number")
    release_parser = subparsers.add_parser("train-release", help="Release a held PR in merge train")
    release_parser.add_argument("pr", type=int, help="PR number")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    command = str(args.command)
    context = build_context()

    if command == "plan":
        return commands_queue.handle_plan(context, commands_queue.GoalArgs(goal=str(args.goal)))
    if command == "run":
        return commands_queue.handle_run(context, commands_queue.GoalArgs(goal=str(args.goal)))
    if command == "enqueue":
        return commands_queue.handle_enqueue(
            context,
            commands_queue.EnqueueArgs(goal=str(args.goal), priority=int(args.priority), requested_by=str(args.requested_by)),
        )
    if command == "queue":
        return commands_queue.handle_queue(context)
    if command == "receipts":
        return commands_queue.handle_receipts(context)
    if command == "run-daemon-tick":
        return commands_queue.handle_run_daemon_tick(context)

    if command == "env-cache":
        return commands_env_cache.handle_list(context)
    if command == "env-cache-prune":
        return commands_env_cache.handle_prune(context)
    if command == "status":
        return commands_observatory.handle_status(context)
    if command == "index":
        return commands_observatory.handle_index(context)

    if command == "sentinel-status":
        return commands_sentinel.handle_status(context)
    if command == "sentinel-enable":
        return commands_sentinel.handle_enable(context)
    if command == "sentinel-disable":
        return commands_sentinel.handle_disable(context)
    if command == "sentinel-run-tick":
        return commands_sentinel.handle_tick(context)

    if command == "show-report":
        return commands_provenance.handle_show_artifact(context, commands_provenance.TargetArgs(target=str(args.target)), kind="report")
    if command == "show-docket":
        return commands_provenance.handle_show_artifact(context, commands_provenance.TargetArgs(target=str(args.target)), kind="docket")
    if command == "quarantines":
        return commands_observatory.handle_quarantines(context)
    if command == "show-quarantine":
        return commands_provenance.handle_show_artifact(context, commands_provenance.TargetArgs(target=str(args.target)), kind="quarantine")
    if command == "replay":
        return commands_provenance.handle_replay(context, commands_provenance.ReplayArgs(target=str(args.target), dry_run=bool(args.dry_run)))

    if command == "pr-checks":
        return commands_canary.handle_pr_canary(context, commands_canary.CanaryTargetArgs(target=str(args.target)))
    if command == "wait-checks":
        return commands_canary.handle_wait_canary(context, commands_canary.CanaryWaitArgs(target=str(args.target), timeout=int(args.timeout)))

    if command == "train-status":
        return commands_train.handle_status(context)
    if command == "train-enable":
        return commands_train.handle_enable(context)
    if command == "train-disable":
        return commands_train.handle_disable(context)
    if command == "train-tick":
        return commands_train.handle_tick(context)
    if command == "train-hold":
        return commands_train.handle_hold(context, commands_train.PrArgs(pr=int(args.pr)))
    if command == "train-release":
        return commands_train.handle_release(context, commands_train.PrArgs(pr=int(args.pr)))

    parser.error(f"unsupported command: {command}")
    return 2
