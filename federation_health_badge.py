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


def compute_health(hours: int = 24) -> Dict[str, int | str]:
    """Return basic federation health stats."""
    if not LOG_PATH.exists():
        return {"nodes": 0, "recent": 0, "status": "no log"}
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    nodes = set()
    recent = 0
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except Exception:
            continue
        payload = entry.get("data", entry)
        if not isinstance(payload, dict):
            continue
        peer = payload.get("peer", "unknown")
        nodes.add(peer)
        ts = entry.get("timestamp")
        try:
            if ts:
                parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                if parsed > cutoff:
                    recent += 1
        except Exception:
            continue
    status = "healthy" if recent > 0 else "quiet"
    return {"nodes": len(nodes), "recent": recent, "status": status}


def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Federation health badge updater")
    ap.add_argument("--hours", type=int, default=24, help="Look back this many hours")
    ap.add_argument("--output", type=Path, default=Path("docs/FEDERATION_HEALTH.md"))
    args = ap.parse_args()
    stats = compute_health(args.hours)
    content = f"# Federation Health\n\n- Nodes: {stats['nodes']}\n- Recent events: {stats['recent']}\n- Status: {stats['status']}\n"
    args.output.write_text(content, encoding="utf-8")

    print(json.dumps(stats))


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
