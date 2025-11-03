"""SentientOS operations control CLI."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from sentientos.autonomy import AutonomyRuntime, run_rehearsal
from sentientos.config import load_runtime_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sosctl", description="SentientOS autonomy control")
    sub = parser.add_subparsers(dest="command")

    rehearse = sub.add_parser("rehearse", help="Execute autonomy rehearsal")
    rehearse.add_argument("--cycles", type=int, default=1, help="Number of rehearsal cycles")

    goals = sub.add_parser("goals", help="Goal curator helpers")
    goals_sub = goals.add_subparsers(dest="goals_command")
    enqueue = goals_sub.add_parser("enqueue", help="Enqueue an autonomous goal")
    enqueue.add_argument("--title", required=True)
    enqueue.add_argument("--support", type=int, default=1)
    enqueue.add_argument("--ttl", default="3d")

    council = sub.add_parser("council", help="Council operations")
    council_sub = council.add_subparsers(dest="council_command")
    vote = council_sub.add_parser("vote", help="Record a council vote")
    vote.add_argument("--amendment", required=True)
    vote.add_argument("--for", dest="votes_for", type=int, default=1)
    vote.add_argument("--against", dest="votes_against", type=int, default=0)

    reflexion = sub.add_parser("reflexion", help="Manage reflexion notes")
    reflexion_sub = reflexion.add_subparsers(dest="reflexion_command")
    run_reflexion = reflexion_sub.add_parser("run", help="Record a reflexion note")
    run_reflexion.add_argument("--since", default="1d")

    hungry = sub.add_parser("hungry-eyes", help="HungryEyes operations")
    hungry_sub = hungry.add_subparsers(dest="hungry_command")
    hungry_sub.add_parser("retrain", help="Force a HungryEyes retrain")

    metrics = sub.add_parser("metrics", help="Metrics utilities")
    metrics_sub = metrics.add_subparsers(dest="metrics_command")
    metrics_sub.add_parser("snapshot", help="Persist a metrics snapshot")

    return parser


def handle(args: argparse.Namespace) -> int:
    config = load_runtime_config()
    runtime = AutonomyRuntime.from_config(config)
    if args.command == "rehearse":
        result = run_rehearsal(cycles=args.cycles, runtime=runtime)
        print(json.dumps(result["report"], indent=2))
        return 0
    if args.command == "goals" and args.goals_command == "enqueue":
        created = runtime.goal_curator.consider(
            {"title": args.title, "ttl": args.ttl},
            corr_id="cli",
            support_count=args.support,
        )
        status = runtime.goal_curator.status()
        active = status.get("active", 0)
        print(json.dumps({"created": created, "active": active}))
        return 0
    if args.command == "council" and args.council_command == "vote":
        decision = runtime.council.vote(
            args.amendment,
            corr_id="cli",
            votes_for=args.votes_for,
            votes_against=args.votes_against,
        )
        print(json.dumps({
            "outcome": decision.outcome.value,
            "quorum_met": decision.quorum_met,
            "votes_for": decision.votes_for,
            "votes_against": decision.votes_against,
        }))
        return 0
    if args.command == "reflexion" and args.reflexion_command == "run":
        note = runtime.reflexion.run(f"Reflexion since {args.since}", corr_id="cli")
        print(json.dumps({"note": note}))
        return 0
    if args.command == "hungry-eyes" and args.hungry_command == "retrain":
        payload = {"status": "VALID", "support": 1}
        report = runtime.hungry_eyes.observe(payload)
        print(json.dumps(report))
        return 0
    if args.command == "metrics" and args.metrics_command == "snapshot":
        runtime.metrics.persist_snapshot()
        runtime.metrics.persist_prometheus()
        print(json.dumps({"status": "ok"}))
        return 0
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 1
    return handle(args)


if __name__ == "__main__":
    sys.exit(main())
