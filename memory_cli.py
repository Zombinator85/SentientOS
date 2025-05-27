import argparse
import json
from pathlib import Path
import memory_manager as mm
from api import actuator

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

def main():
    parser = argparse.ArgumentParser(description="Manage memory fragments")
    sub = parser.add_subparsers(dest="cmd")

    purge = sub.add_parser("purge", help="Delete old fragments")
    purge.add_argument("--age", type=int, help="Remove fragments older than N days")
    purge.add_argument("--max", type=int, help="Keep only the newest N fragments")

    sub.add_parser("summarize", help="Create/update daily summary files")
    sub.add_parser("inspect", help="Print the user profile")
    plot = sub.add_parser("timeline", help="Show recent emotion timeline")
    plot.add_argument("--last", type=int, default=10, help="Show last N entries")
    pb = sub.add_parser("playback", help="Print recent fragments with emotions")
    pb.add_argument("--last", type=int, default=5, help="Show last N entries")
    acts = sub.add_parser("actions", help="Show recent actuator events")
    acts.add_argument("--last", type=int, default=10, help="Show last N events")
    acts.add_argument("--reflect", action="store_true", help="Include reflections")
    forget = sub.add_parser("forget", help="Remove keys from user profile")
    forget.add_argument("keys", nargs="+", help="Profile keys to remove")

    args = parser.parse_args()
    if args.cmd == "purge":
        mm.purge_memory(max_age_days=args.age, max_files=args.max)
    elif args.cmd == "summarize":
        mm.summarize_memory()
    elif args.cmd == "inspect":
        import user_profile as up
        print(up.format_profile())
    elif args.cmd == "forget":
        import user_profile as up
        up.forget_keys(args.keys)
        print("Removed keys: " + ", ".join(args.keys))
    elif args.cmd == "timeline":
        show_timeline(args.last)
    elif args.cmd == "playback":
        playback(args.last)
    elif args.cmd == "actions":
        show_actions(args.last, reflect=args.reflect)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
