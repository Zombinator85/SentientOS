"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
import os
import json
import datetime
from pathlib import Path
from collections import defaultdict
from typing import Any, Dict, List, Optional

import workflow_controller as wc

EVENT_PATH = wc.EVENT_PATH


def load_events(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    if not EVENT_PATH.exists():
        return []
    lines = EVENT_PATH.read_text(encoding="utf-8").splitlines()
    if limit:
        lines = lines[-limit:]
    events: List[Dict[str, Any]] = []
    for line in lines:
        try:
            events.append(json.loads(line))
        except Exception:
            continue
    return events


def usage_stats(events: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    data: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "runs": 0,
        "failures": 0,
        "denied": 0,
        "duration_total": 0.0,
        "last_ts": None,
        "last_status": None,
    })
    start_times: Dict[str, datetime.datetime] = {}
    for ev in events:
        wf = ev.get("payload", {}).get("workflow")
        if not wf:
            continue
        kind = ev.get("event")
        ts_str_raw = ev.get("timestamp")
        ts: Optional[datetime.datetime] = None
        if isinstance(ts_str_raw, str):
            try:
                ts = datetime.datetime.fromisoformat(ts_str_raw)
            except Exception:
                ts = None
        if kind == "workflow.start":
            start_times[wf] = ts or datetime.datetime.utcnow()
        elif kind == "workflow.end":
            info = data[wf]
            info["runs"] += 1
            status = ev.get("payload", {}).get("status")
            if status != "ok":
                if status == "denied":
                    info["denied"] += 1
                else:
                    info["failures"] += 1
            if wf in start_times and ts:
                delta = (ts - start_times.pop(wf)).total_seconds()
                info["duration_total"] += delta
            info["last_ts"] = ts_str_raw
            info["last_status"] = status
        elif kind == "workflow.step":
            if ev.get("payload", {}).get("status") == "denied":
                data[wf]["denied"] += 1
    for wf, info in data.items():
        runs = info["runs"] or 1
        info["avg_duration"] = info["duration_total"] / runs
        info["fail_rate"] = info["failures"] / runs
    return data


def trend_stats(events: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    trends: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for ev in events:
        if ev.get("event") != "workflow.end":
            continue
        wf = ev.get("payload", {}).get("workflow")
        ts = ev.get("timestamp")
        if not wf or not ts:
            continue
        try:
            dt = datetime.datetime.fromisoformat(ts)
        except Exception:
            continue
        key = dt.strftime("%Y-%m")
        trends[wf][key] += 1
    return trends


def find_bottlenecks(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    failures: Dict[str, int] = defaultdict(int)
    durations: Dict[str, float] = defaultdict(float)
    last_start: Dict[str, datetime.datetime] = {}
    for ev in events:
        wf = ev.get("payload", {}).get("workflow")
        step = ev.get("payload", {}).get("step")
        kind = ev.get("event")
        ts_str_raw = ev.get("timestamp")
        ts = None
        if isinstance(ts_str_raw, str):
            try:
                ts = datetime.datetime.fromisoformat(ts_str_raw)
            except Exception:
                ts = None
        if kind == "workflow.step" and step:
            status = ev.get("payload", {}).get("status")
            if status == "failed":
                failures[step] += 1
        if kind == "workflow.step" and step and ts:
            if status := ev.get("payload", {}).get("status") == "ok":
                if step in last_start:
                    durations[step] += (ts - last_start.pop(step)).total_seconds()
            else:
                last_start.pop(step, None)
        elif kind == "workflow.start":
            last_start.clear()
    longest = sorted(durations.items(), key=lambda x: x[1], reverse=True)[:3]
    common_fail = sorted(failures.items(), key=lambda x: x[1], reverse=True)[:3]
    return {
        "top_failures": common_fail,
        "longest_steps": longest,
    }


def analytics(limit: Optional[int] = None) -> Dict[str, Any]:
    events = load_events(limit)
    return {
        "usage": usage_stats(events),
        "trends": trend_stats(events),
        "bottlenecks": find_bottlenecks(events),
    }


if __name__ == "__main__":  # pragma: no cover - CLI
    import argparse

    parser = argparse.ArgumentParser(description="Workflow analytics")
    parser.add_argument("cmd", choices=["usage", "trends", "bottlenecks", "all"])
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    data = analytics(args.limit)
    if args.cmd == "usage":
        print(json.dumps(data["usage"], indent=2))
    elif args.cmd == "trends":
        print(json.dumps(data["trends"], indent=2))
    elif args.cmd == "bottlenecks":
        print(json.dumps(data["bottlenecks"], indent=2))
    else:
        print(json.dumps(data, indent=2))
