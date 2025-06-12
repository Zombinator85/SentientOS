"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from logging_config import get_log_path
import json
import datetime
from pathlib import Path
from typing import Any, Dict, List, TypedDict, cast
from sentient_banner import print_banner, print_closing, ENTRY_BANNER
import support_log as sl


MEMORY_DIR = get_log_path("memory", "MEMORY_DIR")
RAW_PATH: Path = MEMORY_DIR / "raw"
EVENT_PATH: Path = MEMORY_DIR / "events.jsonl"


class ActionStats(TypedDict):
    total: int
    success: int
    failed: int
    errors: Dict[str, int]


class PatchStats(TypedDict):
    patch_approved: int
    patch_rejected: int
    patch_rolled_back: int


class PresenceMetrics(TypedDict):
    uptime_hours: float
    presence_score: float


class AnalyticsData(TypedDict):
    emotion_trends: Dict[str, Dict[str, Dict[str, float]]]
    action_stats: ActionStats
    patch_stats: PatchStats
    presence_metrics: PresenceMetrics


def load_entries(limit: int | None = None) -> List[Dict[str, Any]]:
    files = sorted(RAW_PATH.glob("*.json"))
    if limit:
        files = files[-limit:]
    out: List[Dict[str, Any]] = []
    for fp in files:
        try:
            obj = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        data = cast(Dict[str, Any], obj)
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


def action_stats(entries: List[Dict[str, Any]]) -> ActionStats:
    stats: ActionStats = {"total": 0, "success": 0, "failed": 0, "errors": {}}
    for e in entries:
        tags_obj = e.get("tags", [])
        if not isinstance(tags_obj, list):
            continue
        if any(not isinstance(t, str) for t in tags_obj):
            continue
        tags = cast(List[str], tags_obj)
        if "act" not in tags:
            continue
        stats["total"] += 1
        text_val = e.get("text", "{}")
        if not isinstance(text_val, str):
            continue
        try:
            data = json.loads(text_val)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        data_dict = cast(Dict[str, Any], data)
        if data_dict.get("status") == "finished":
            stats["success"] += 1
        else:
            stats["failed"] += 1
            err = str(data_dict.get("error") or "unknown")
            stats["errors"][err] = stats["errors"].get(err, 0) + 1
    return stats


def patch_stats(limit: int | None = None) -> PatchStats:
    if not EVENT_PATH.exists():
        return {"patch_approved": 0, "patch_rejected": 0, "patch_rolled_back": 0}
    lines = EVENT_PATH.read_text(encoding="utf-8").splitlines()
    if limit:
        lines = lines[-limit:]
    counts: Dict[str, int] = {"patch_approved": 0, "patch_rejected": 0, "patch_rolled_back": 0}
    for line in lines:
        try:
            ev_obj = json.loads(line)
        except Exception:
            continue
        if not isinstance(ev_obj, dict):
            continue
        evt_val = ev_obj.get("event")
        if not isinstance(evt_val, str):
            continue
        if evt_val in counts:
            counts[evt_val] += 1
    return cast(PatchStats, counts)


def presence_metrics(entries: List[Dict[str, Any]]) -> PresenceMetrics:
    times: List[datetime.datetime] = []
    for e in entries:
        ts_val = e.get("timestamp")
        if ts_val is None:
            continue
        if not isinstance(ts_val, str):
            ts_str = str(ts_val)
        else:
            ts_str = ts_val
        try:
            times.append(datetime.datetime.fromisoformat(ts_str))
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


def suggest_improvements(analytics_data: AnalyticsData) -> List[str]:
    suggestions: List[str] = []
    trends = analytics_data["emotion_trends"]
    for user, days in trends.items():
        for day, emos in days.items():
            sad = emos.get("Sadness", 0)
            if sad > 0.6:
                suggestions.append(
                    f"High sadness for {user} on {day} – consider a positive routine"
                )
    stats = analytics_data["action_stats"]
    total = stats["total"]
    success = stats["success"]
    if total and success / total < 0.8:
        suggestions.append("Low action success rate – review failing actions")
    patches = analytics_data["patch_stats"]
    if patches["patch_rejected"] > patches["patch_approved"]:
        suggestions.append("More patches rejected than approved – review patches")
    return suggestions


def main() -> None:
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
        data = cast(AnalyticsData, analytics(args.limit))
        for line in suggest_improvements(data):
            print(f"- {line}")
    print_closing()


if __name__ == "__main__":
    main()
