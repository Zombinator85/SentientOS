import os
import json
import datetime
from pathlib import Path
from typing import List, Dict, Any
from sentient_banner import print_banner, print_closing, ENTRY_BANNER
from admin_utils import require_admin_banner
import support_log as sl

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

MEMORY_DIR = Path(os.getenv("MEMORY_DIR", "logs/memory"))
RAW_PATH = MEMORY_DIR / "raw"
EVENT_PATH = MEMORY_DIR / "events.jsonl"


def load_entries(limit: int | None = None) -> List[Dict[str, Any]]:
    files = sorted(RAW_PATH.glob("*.json"))
    if limit:
        files = files[-limit:]
    out: List[Dict[str, Any]] = []
    for fp in files:
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        out.append(data)
        user = data.get("user", "anon") or "anon"
        sl.add(user, "analysis blessing: memory record")
    return out


def _dominant(emotions: Dict[str, float]) -> tuple[str, float]:
    if not emotions:
        return "none", 0.0
    emo, val = max(emotions.items(), key=lambda x: x[1])
    return emo, val


def emotion_trends(entries: List[Dict[str, Any]]) -> Dict[str, Dict[str, Dict[str, float]]]:
    trends: Dict[str, Dict[str, Dict[str, List[float]]]] = {}
    for e in entries:
        emotions = e.get("emotions", {})
        if not emotions:
            continue
        user = e.get("user", "anon") or "anon"
        ts = e.get("timestamp")
        if not ts:
            continue
        try:
            dt = datetime.datetime.fromisoformat(ts)
        except Exception:
            continue
        day = dt.strftime("%A")
        emo, val = _dominant(emotions)
        bucket = trends.setdefault(user, {}).setdefault(day, {}).setdefault(emo, [])
        bucket.append(val)
    avg: Dict[str, Dict[str, Dict[str, float]]] = {}
    for user, days in trends.items():
        avg[user] = {}
        for day, emos in days.items():
            avg[user][day] = {k: sum(v)/len(v) for k, v in emos.items() if v}
    return avg


def action_stats(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    stats = {"total": 0, "success": 0, "failed": 0, "errors": {}}
    for e in entries:
        if "act" not in e.get("tags", []):
            continue
        stats["total"] += 1
        try:
            data = json.loads(e.get("text", "{}"))
        except Exception:
            continue
        if data.get("status") == "finished":
            stats["success"] += 1
        else:
            stats["failed"] += 1
            err = data.get("error") or "unknown"
            stats["errors"][err] = stats["errors"].get(err, 0) + 1
    return stats


def patch_stats(limit: int | None = None) -> Dict[str, int]:
    if not EVENT_PATH.exists():
        return {"patch_approved": 0, "patch_rejected": 0, "patch_rolled_back": 0}
    lines = EVENT_PATH.read_text(encoding="utf-8").splitlines()
    if limit:
        lines = lines[-limit:]
    counts = {"patch_approved": 0, "patch_rejected": 0, "patch_rolled_back": 0}
    for line in lines:
        try:
            ev = json.loads(line)
        except Exception:
            continue
        evt = ev.get("event")
        if evt in counts:
            counts[evt] += 1
    return counts


def presence_metrics(entries: List[Dict[str, Any]]) -> Dict[str, float]:
    times: List[datetime.datetime] = []
    for e in entries:
        ts = e.get("timestamp")
        if not ts:
            continue
        try:
            times.append(datetime.datetime.fromisoformat(ts))
        except Exception:
            continue
    if not times:
        return {"uptime_hours": 0.0, "presence_score": 0.0}
    times.sort()
    uptime = (times[-1] - times[0]).total_seconds() / 3600.0
    presence_score = len(entries) / uptime if uptime else float(len(entries))
    return {"uptime_hours": uptime, "presence_score": presence_score}


def analytics(limit: int | None = None) -> Dict[str, Any]:
    entries = load_entries(limit)
    return {
        "emotion_trends": emotion_trends(entries),
        "action_stats": action_stats(entries),
        "patch_stats": patch_stats(),
        "presence_metrics": presence_metrics(entries),
    }


def suggest_improvements(analytics_data: Dict[str, Any]) -> List[str]:
    suggestions: List[str] = []
    trends = analytics_data.get("emotion_trends", {})
    for user, days in trends.items():
        for day, emos in days.items():
            sad = emos.get("Sadness", 0)
            if sad > 0.6:
                suggestions.append(
                    f"High sadness for {user} on {day} – consider a positive routine"
                )
    stats = analytics_data.get("action_stats", {})
    total = stats.get("total", 0)
    success = stats.get("success", 0)
    if total and success / total < 0.8:
        suggestions.append("Low action success rate – review failing actions")
    patches = analytics_data.get("patch_stats", {})
    if patches.get("patch_rejected", 0) > patches.get("patch_approved", 0):
        suggestions.append("More patches rejected than approved – review patches")
    return suggestions


def main() -> None:
    require_admin_banner()
    # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
    import argparse
    parser = argparse.ArgumentParser(description=ENTRY_BANNER)
    parser.add_argument("cmd", choices=["analytics", "trends", "suggest"])
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    print_banner()
    sl.add("analytics", f"presence_analytics {args.cmd}")
    entries = load_entries(args.limit)
    if args.cmd == "analytics":
        print(json.dumps(analytics(args.limit), indent=2))
    elif args.cmd == "trends":
        print(json.dumps(emotion_trends(entries), indent=2))
    elif args.cmd == "suggest":
        data = analytics(args.limit)
        for line in suggest_improvements(data):
            print(f"- {line}")
    print_closing()


if __name__ == "__main__":
    main()
