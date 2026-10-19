from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict

from sentientos.privilege import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

LOG_PATH = get_log_path("federation_log.jsonl")


def compute_health(hours: int = 24) -> Dict[str, int | str | bool | None]:
    """Return basic federation health stats."""
    if hours <= 0:
        raise ValueError("hours must be positive")
    source = "configured_local_log_snapshot"
    if not LOG_PATH.exists():
        return {
            "nodes": 0,
            "recent": 0,
            "status": "no log",
            "source": source,
            "window_hours": hours,
            "latest_event_at": None,
            "live_telemetry": False,
        }
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)
    nodes = set()
    recent = 0
    latest_event_at: datetime | None = None
    with LOG_PATH.open("rb") as log_file:
        for raw_line in log_file:
            try:
                line = raw_line.decode("utf-8")
            except UnicodeDecodeError:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(entry, dict):
                continue
            payload = entry.get("data", entry)
            if not isinstance(payload, dict):
                continue
            peer = payload.get("peer", "unknown")
            try:
                nodes.add(peer)
            except TypeError:
                continue
            ts = entry.get("timestamp")
            try:
                if isinstance(ts, str) and ts:
                    parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    if latest_event_at is None or parsed > latest_event_at:
                        latest_event_at = parsed
                    if cutoff <= parsed <= now:
                        recent += 1
            except (TypeError, ValueError):
                continue
    status = "healthy" if recent > 0 else "quiet"
    latest = (
        latest_event_at.isoformat().replace("+00:00", "Z")
        if latest_event_at is not None
        else None
    )
    return {
        "nodes": len(nodes),
        "recent": recent,
        "status": status,
        "source": source,
        "window_hours": hours,
        "latest_event_at": latest,
        "live_telemetry": False,
    }


def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Federation health badge updater")
    ap.add_argument("--hours", type=int, default=24, help="Look back this many hours")
    ap.add_argument("--output", type=Path, default=Path("docs/FEDERATION_HEALTH.md"))
    args = ap.parse_args()
    stats = compute_health(args.hours)
    content = (
        "# Federation Health\n\n"
        f"- Nodes in configured log: {stats['nodes']}\n"
        f"- Events in last {stats['window_hours']} hours: {stats['recent']}\n"
        f"- Latest event in log: {stats['latest_event_at'] or 'none'}\n"
        "- Data source: configured local log snapshot (not live federation telemetry)\n"
        f"- Status: {stats['status']}\n"
    )
    args.output.write_text(content, encoding="utf-8")

    print(json.dumps(stats))


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
