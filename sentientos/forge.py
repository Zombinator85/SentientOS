"""CLI entrypoint for CathedralForge and daemon queue operations."""

from __future__ import annotations

import argparse
import json

from sentientos.cathedral_forge import CathedralForge
from sentientos.contract_sentinel import ContractSentinel
from sentientos.forge_daemon import ForgeDaemon
from sentientos.forge_env_cache import list_cache_entries, prune_cache
from sentientos.forge_index import rebuild_index
from sentientos.forge_queue import ForgeQueue, ForgeRequest
from sentientos.forge_status import compute_status


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

    args = parser.parse_args(argv)
    forge = CathedralForge()
    queue = ForgeQueue()
    sentinel = ContractSentinel(repo_root=forge.repo_root, queue=ForgeQueue(pulse_root=forge.repo_root / "pulse"))

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

    if args.command == "status":
        status = compute_status(forge.repo_root)
        print(json.dumps({"command": "status", "status": status.to_dict()}, indent=2, sort_keys=True))
        return 0

    if args.command == "index":
        index_payload = rebuild_index(forge.repo_root)
        print(
            json.dumps(
                {
                    "command": "index",
                    "generated_at": index_payload.get("generated_at"),
                    "reports": len(index_payload.get("latest_reports", [])),
                    "dockets": len(index_payload.get("latest_dockets", [])),
                    "receipts": len(index_payload.get("latest_receipts", [])),
                    "queue_pending": len(index_payload.get("latest_queue", [])),
                    "corrupt_count": index_payload.get("corrupt_count"),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if args.command == "sentinel-status":
        print(json.dumps({"command": "sentinel-status", "status": sentinel.summary()}, indent=2, sort_keys=True))
        return 0

    if args.command == "sentinel-enable":
        policy = sentinel.load_policy()
        policy.enabled = True
        sentinel.save_policy(policy)
        print(json.dumps({"command": "sentinel-enable", "enabled": True}, sort_keys=True))
        return 0

    if args.command == "sentinel-disable":
        policy = sentinel.load_policy()
        policy.enabled = False
        sentinel.save_policy(policy)
        print(json.dumps({"command": "sentinel-disable", "enabled": False}, sort_keys=True))
        return 0

    if args.command == "sentinel-run-tick":
        print(json.dumps({"command": "sentinel-run-tick", "result": sentinel.tick()}, indent=2, sort_keys=True))
        return 0

    if args.command == "show-report":
        payload = _load_artifact(forge, args.target, kind="report")
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if args.command == "show-docket":
        payload = _load_artifact(forge, args.target, kind="docket")
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if args.command == "quarantines":
        index_payload = rebuild_index(forge.repo_root)
        print(json.dumps({"command": "quarantines", "rows": index_payload.get("latest_quarantines", [])}, indent=2, sort_keys=True))
        return 0

    if args.command == "show-quarantine":
        payload = _load_artifact(forge, args.target, kind="quarantine")
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    daemon = ForgeDaemon(queue=queue)
    daemon.run_tick()
    print(json.dumps({"command": "run-daemon-tick", "status": "ok"}, sort_keys=True))
    return 0


def _load_artifact(forge: CathedralForge, target: str, *, kind: str) -> dict[str, object]:
    from pathlib import Path

    if target.endswith(".json"):
        path = Path(target)
    else:
        suffix = target.replace(":", "-")
        prefix = "report" if kind == "report" else ("docket" if kind == "docket" else "quarantine")
        path = forge.forge_dir / f"{prefix}_{suffix}.json"
    if not path.is_absolute():
        path = forge.repo_root / path
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"error": f"unreadable {kind}", "path": str(path)}
    if not isinstance(payload, dict):
        return {"error": f"invalid {kind} payload", "path": str(path)}
    return _truncate_large_fields(payload)


def _truncate_large_fields(payload: dict[str, object], *, max_chars: int = 2000) -> dict[str, object]:
    trimmed: dict[str, object] = {}
    for key, value in payload.items():
        if isinstance(value, str) and len(value) > max_chars:
            trimmed[key] = value[:max_chars] + "...<truncated>"
            continue
        trimmed[key] = value
    return trimmed


if __name__ == "__main__":
    raise SystemExit(main())
