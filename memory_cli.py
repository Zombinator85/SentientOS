import argparse
import os
import json
import re
from pathlib import Path
import memory_manager as mm
from api import actuator
import notification
import self_patcher
import final_approval
from sentient_banner import print_banner, print_closing, ENTRY_BANNER
from admin_utils import require_admin_banner, require_lumos_approval
import presence_analytics as pa
import ritual

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

def show_timeline(last: int) -> None:
    """Print the timestamp and dominant emotion of recent entries."""
    path = mm.RAW_PATH
    files = sorted(path.glob("*.json"))[-last:]
    for fp in files:
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        emo = data.get("emotions", {})
        if emo:
            label = max(emo, key=emo.get)
            val = emo[label]
        else:
            label = "none"
            val = 0
        print(f"{data.get('timestamp','?')} {label}:{val:.2f}")

def playback(last: int) -> None:
    """Print recent entries with emotion labels and source breakdown if present."""
    path = mm.RAW_PATH
    files = sorted(path.glob("*.json"))[-last:]
    for fp in files:
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        emo = data.get("emotions", {})
        breakdown = data.get("emotion_breakdown", {})
        label = max(emo, key=emo.get) if emo else "none"
        val = emo.get(label, 0)
        txt = (data.get("text", "").strip())[:60]
        if breakdown:
            # breakdown: {"audio": {"Joy": 0.8, ...}, "text": {...}, ...}
            parts = ", ".join(f"{s}:{max(v.get(label,0),0):.2f}" for s,v in breakdown.items())
            print(f"[{data.get('timestamp','?')}] {label}:{val:.2f} ({parts}) -> {txt}")
        else:
            print(f"[{data.get('timestamp','?')}] {label}:{val:.2f} -> {txt}")


def show_actions(last: int, reflect: bool) -> None:
    """Display recent actuator events with context."""
    logs = actuator.recent_logs(last, reflect=reflect)
    for entry in logs:
        intent = entry.get("intent", {})
        result = entry.get("result", entry.get("error"))
        desc = json.dumps(intent)
        line = f"{entry.get('timestamp','?')} {entry.get('status')} {desc} -> {result}"
        if reflect and entry.get("reflection_text"):
            line += f" | {entry['reflection_text']}"
        print(line)


def show_reflections(last: int, plugin: str | None, user: str | None, failures: bool, as_json: bool) -> None:
    """Display recent reflection entries."""
    refls = mm.recent_reflections(limit=last, plugin=plugin, user=user, failures_only=failures)
    if as_json:
        print(json.dumps(refls, indent=2))
        return
    for r in refls:
        line = f"{r.get('timestamp','?')} {r.get('plugin')} {r.get('reason','') or r.get('next','')}"
        print(line)


def show_goals(status: str) -> None:
    goals = mm.get_goals(open_only=False)
    for g in goals:
        if status != "all" and g.get("status") != status:
            continue
        line = f"{g.get('status')} {g.get('text','')}"
        if g.get('failure_count'):
            line += f" ({g['failure_count']})"
        if g.get('critique'):
            line += f" | {g['critique']}"
        print(line)

def main():
    require_admin_banner()
    # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
    parser = argparse.ArgumentParser(
        description=ENTRY_BANNER,
        epilog=(
            "Presence is law. Love is ledgered. No one is forgotten. "
            "No one is turned away.\n"
            "Example: python memory_cli.py --ledger"
        ),
    )
    parser.add_argument(
        "--final-approvers",
        default=os.getenv("REQUIRED_FINAL_APPROVER", "4o"),
        help="Comma or space separated list or config file of required approvers",
    )
    parser.add_argument(
        "--final-approver-file",
        help="File with approver names (JSON list or newline separated) to require at runtime",
    )
    parser.add_argument("--ledger", action="store_true", help="Show living ledger summary and exit")
    sub = parser.add_subparsers(dest="cmd")

    purge = sub.add_parser("purge", help="Delete old fragments")
    purge.add_argument("--age", type=int, help="Remove fragments older than N days")
    purge.add_argument("--max", type=int, help="Keep only the newest N fragments")
    purge.add_argument("--reason")
    purge.add_argument("--requestor")

    tomb = sub.add_parser("tomb", help="Visit the memory tomb")
    tomb.add_argument("--tag")
    tomb.add_argument("--reason")
    tomb.add_argument("--date")
    tomb.add_argument("--json", action="store_true")

    sub.add_parser("summarize", help="Create/update daily summary files")
    sub.add_parser("inspect", help="Print the user profile")
    plot = sub.add_parser("timeline", help="Show recent emotion timeline")
    plot.add_argument("--last", type=int, default=10, help="Show last N entries")
    pb = sub.add_parser("playback", help="Print recent fragments with emotions")
    pb.add_argument("--last", type=int, default=5, help="Show last N entries")
    acts = sub.add_parser("actions", help="Show recent actuator events")
    acts.add_argument("--last", type=int, default=10, help="Show last N events")
    acts.add_argument("--reflect", action="store_true", help="Include reflections")
    refl = sub.add_parser("reflections", help="List recent reflections")
    refl.add_argument("--last", type=int, default=5)
    refl.add_argument("--plugin")
    refl.add_argument("--user")
    refl.add_argument("--failures", action="store_true", help="Only failed actions")
    refl.add_argument("--json", action="store_true", help="Export as JSON")

    goals = sub.add_parser("goals", help="List goals")
    goals.add_argument(
        "--status",
        default="open",
        choices=["open", "failed", "completed", "stuck", "all"],
        help="Filter by status",
    )
    add_goal = sub.add_parser("add_goal", help="Add a new goal")
    add_goal.add_argument("text")
    add_goal.add_argument("--intent")
    add_goal.add_argument("--priority", type=int, default=1)
    add_goal.add_argument("--deadline")
    add_goal.add_argument("--schedule")

    complete = sub.add_parser("complete_goal", help="Mark goal completed")
    complete.add_argument("id")

    delete = sub.add_parser("delete_goal", help="Delete a goal")
    delete.add_argument("id")

    es = sub.add_parser("escalations", help="Show recent escalations")
    es.add_argument("--last", type=int, default=5)

    run = sub.add_parser("run", help="Run agent cycles")
    run.add_argument("--cycles", type=int, default=1)

    subs = sub.add_parser("subscriptions", help="List event subscriptions")
    sub_add = sub.add_parser("subscribe", help="Add subscription")
    sub_add.add_argument("event")
    sub_add.add_argument("--method", choices=["email","webhook","console"], default="console")
    sub_add.add_argument("--target")
    sub_del = sub.add_parser("unsubscribe", help="Remove subscription")
    sub_del.add_argument("event")
    sub_del.add_argument("--method", choices=["email","webhook","console"], default="console")
    sub_del.add_argument("--target")
    p_list = sub.add_parser("patches", help="List patches")
    p_apply = sub.add_parser("apply_patch", help="Record a manual patch")
    p_apply.add_argument("note")
    p_rb = sub.add_parser("rollback_patch", help="Rollback a patch")
    p_rb.add_argument("id")
    p_appr = sub.add_parser("approve_patch", help="Approve a patch")
    p_appr.add_argument("id")
    p_rej = sub.add_parser("reject_patch", help="Reject a patch")
    p_rej.add_argument("id")
    analytics = sub.add_parser("analytics", help="Show presence analytics")
    analytics.add_argument("--limit", type=int, default=None)
    trends = sub.add_parser("trends", help="Show emotion trends")
    trends.add_argument("--limit", type=int, default=None)
    suggest = sub.add_parser("suggest", help="Suggest improvements")
    suggest.add_argument("--limit", type=int, default=None)
    sched = sub.add_parser("schedule", help="Run orchestrator cycle")
    sched.add_argument("--cycles", type=int, default=1)
    events = sub.add_parser("events", help="List recent events")
    events.add_argument("--last", type=int, default=5)
    self_reflect = sub.add_parser("self_reflect", help="Run self-reflection cycle")
    orch = sub.add_parser("orchestrator", help="Control orchestrator")
    orch.add_argument("action", choices=["start", "stop", "status"])
    orch.add_argument("--cycles", type=int)
    forget = sub.add_parser("forget", help="Remove keys from user profile")
    forget.add_argument("keys", nargs="+", help="Profile keys to remove")

    args = parser.parse_args()
    from sentient_banner import reset_ritual_state, print_snapshot_banner

    reset_ritual_state()
    print_banner()
    print_snapshot_banner()
    if args.ledger:
        ledger.print_summary()
        print_closing()
        return
    if args.final_approver_file:
        fp = Path(args.final_approver_file)
        chain = final_approval.load_file_approvers(fp) if fp.exists() else []
        final_approval.override_approvers(chain, source="file")
    elif args.final_approvers:
        fp = Path(args.final_approvers)
        if fp.exists():
            chain = final_approval.load_file_approvers(fp)
        else:
            parts = re.split(r"[,\s]+", args.final_approvers)
            chain = [a.strip() for a in parts if a.strip()]
        final_approval.override_approvers(chain, source="cli")
    if args.cmd == "purge":
        ritual.confirm_disruptive("purge", "Old fragments will be permanently removed")
        mm.purge_memory(
            max_age_days=args.age,
            max_files=args.max,
            requestor=args.requestor or os.getenv("USER", "cli"),
            reason=args.reason or "",
        )
    elif args.cmd == "tomb":
        entries = mm.list_tomb(tag=args.tag, reason=args.reason, date=args.date)
        for e in entries:
            if args.json:
                print(json.dumps(e))
            else:
                frag = e.get("fragment", {})
                summary = frag.get("text", "")[:60].replace("\n", " ")
                print(f"[{e.get('time','?')}] {summary} | reason={e.get('reason','')}")
    elif args.cmd == "summarize":
        mm.summarize_memory()
    elif args.cmd == "inspect":
        import user_profile as up
        print(up.format_profile())
    elif args.cmd == "forget":
        ritual.confirm_disruptive("forget", "Selected profile keys will be lost")
        import user_profile as up
        up.forget_keys(args.keys)
        print("Removed keys: " + ", ".join(args.keys))
    elif args.cmd == "timeline":
        show_timeline(args.last)
    elif args.cmd == "playback":
        playback(args.last)
    elif args.cmd == "actions":
        show_actions(args.last, reflect=args.reflect)
    elif args.cmd == "reflections":
        show_reflections(args.last, args.plugin, args.user, args.failures, args.json)
    elif args.cmd == "goals":
        show_goals(args.status)
    elif args.cmd == "add_goal":
        intent = json.loads(args.intent or "{}") if args.intent else {}
        g = mm.add_goal(
            args.text,
            intent=intent,
            priority=args.priority,
            deadline=args.deadline,
            schedule_at=args.schedule,
        )
        print(f"Added goal {g['id']}")
    elif args.cmd == "complete_goal":
        g = mm.get_goal(args.id)
        if g:
            g["status"] = "completed"
            mm.save_goal(g)
            print(f"Completed {args.id}")
        else:
            print("Goal not found")
    elif args.cmd == "subscriptions":
        print(json.dumps(notification.list_subscriptions(), indent=2))
    elif args.cmd == "subscribe":
        notification.add_subscription(args.event, args.method, args.target)
        print("Subscribed")
    elif args.cmd == "unsubscribe":
        notification.remove_subscription(args.event, args.method, args.target)
        print("Unsubscribed")
    elif args.cmd == "patches":
        print(json.dumps(self_patcher.list_patches(), indent=2))
    elif args.cmd == "apply_patch":
        self_patcher.apply_patch(args.note, auto=False)
        print("Patch recorded")
    elif args.cmd == "rollback_patch":
        ritual.confirm_disruptive("rollback_patch", "Patch state will change")
        if self_patcher.rollback_patch(args.id):
            print("Rolled back")
        else:
            print("Patch not found")
    elif args.cmd == "approve_patch":
        if self_patcher.approve_patch(args.id):
            print("Approved")
        else:
            print("Patch not found")
    elif args.cmd == "reject_patch":
        if self_patcher.reject_patch(args.id):
            print("Rejected")
        else:
            print("Patch not found")
    elif args.cmd == "analytics":
        data = pa.analytics(args.limit)
        print(json.dumps(data, indent=2))
    elif args.cmd == "trends":
        data = pa.emotion_trends(pa.load_entries(args.limit))
        print(json.dumps(data, indent=2))
    elif args.cmd == "suggest":
        data = pa.analytics(args.limit)
        for line in pa.suggest_improvements(data):
            print(f"- {line}")
    elif args.cmd == "schedule":
        import orchestrator
        o = orchestrator.Orchestrator(interval=0.01)
        for _ in range(args.cycles):
            o.run_cycle()
    elif args.cmd == "events":
        for ev in notification.list_events(args.last):
            print(json.dumps(ev))
    elif args.cmd == "self_reflect":
        import self_reflection
        mgr = self_reflection.SelfHealingManager()
        mgr.run_cycle()
        print("Reflection cycle completed")
    elif args.cmd == "orchestrator":
        import orchestrator
        o = orchestrator.Orchestrator(interval=0.01)
        if args.action == "start":
            o.start(cycles=args.cycles)
        elif args.action == "stop":
            o.stop()
            print("Stopped")
        else:
            print(json.dumps(o.status(), indent=2))
    elif args.cmd == "delete_goal":
        ritual.confirm_disruptive("delete_goal", "Goal will be removed")
        mm.delete_goal(args.id)
        print(f"Deleted {args.id}")
    elif args.cmd == "escalations":
        for line in mm.recent_escalations(args.last):
            print(line)
    elif args.cmd == "run":
        import autonomous_reflector as ar
        ar.run_loop(iterations=args.cycles, interval=0.01)
    else:
        parser.print_help()
    print_closing()

if __name__ == "__main__":
    main()
