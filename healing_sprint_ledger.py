"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations


import json
import re
import datetime
from pathlib import Path
from typing import Dict, List

from logging_config import get_log_path
from cathedral_wounds_dashboard import gather_wounds, parse_saints

"""Generate a healing sprint ledger with community metrics."""


def logs_healed_count() -> int:
    """Return the total number of log lines healed according to AUDIT_LOG_FIXES.md."""
    path = Path("AUDIT_LOG_FIXES.md")
    if not path.exists():
        return 0
    total = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if "repaired" in line.lower():
            # look for a number directly before the word "malformed"
            m = re.search(r"(\d+)\s+malformed", line.lower())
            if m:
                total += int(m.group(1))
            else:
                m = re.search(r"repaired[^\d]*(\d+)", line.lower())
                if m:
                    total += int(m.group(1))
                else:
                    total += 1
    return total


def federation_nodes_synced() -> int:
    """Return the number of unique federation peers."""
    path = get_log_path("federation_log.jsonl")
    peers = set()
    if path.exists():
        for ln in path.read_text(encoding="utf-8").splitlines():
            try:
                peers.add(json.loads(ln).get("peer", ""))
            except Exception:
                continue
    peers.discard("")
    return len(peers)


def read_stories() -> List[Dict[str, str]]:
    """Return saint stories from the optional log."""
    stories_path = get_log_path("saint_stories.jsonl")
    out: List[Dict[str, str]] = []
    if stories_path.exists():
        for ln in stories_path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(ln))
            except Exception:
                continue
    return out


def gather_metrics() -> Dict[str, int]:
    wounds = sum(gather_wounds().values())
    saints_list = [s for s in parse_saints() if not s.lower().startswith("first-timers")]
    saints = len(saints_list)
    logs_healed = logs_healed_count()
    nodes = federation_nodes_synced()
    return {
        "logs_healed": logs_healed,
        "saints": saints,
        "wounds": wounds,
        "nodes": nodes,
    }


def write_dashboard(metrics: Dict[str, int], stories: List[Dict[str, str]]) -> None:
    dash = Path("docs/SPRINT_LEDGER.md")
    dash.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Cathedral Healing Sprint Ledger",
        "",
        f"Updated: {datetime.date.today()}",
        "",
        "## Sprint Metrics",
        "",
        "| Metric | Count |",
        "|--------|-------|",
        f"| Logs healed | {metrics['logs_healed']} |",
        f"| Saints inducted | {metrics['saints']} |",
        f"| Wounds remaining | {metrics['wounds']} |",
        f"| Federation nodes synced | {metrics['nodes']} |",
        "",
        "## Saint Stories",
        "",
    ]
    for s in stories:
        saint = s.get("saint", "Unknown")
        story = s.get("story", "")
        lines.append(f"- **{saint}**: {story}")
    dash.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:  # pragma: no cover - CLI
    metrics = gather_metrics()
    stories = read_stories()
    write_dashboard(metrics, stories)


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
