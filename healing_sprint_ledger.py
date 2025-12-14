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
from cathedral_wounds_dashboard import gather_integrity_issues, parse_contributors

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
    """Return contributor stories from the optional log."""
    stories_path = get_log_path("contributor_stories.jsonl")
    out: List[Dict[str, str]] = []
    if stories_path.exists():
        for ln in stories_path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(ln))
            except Exception:
                continue
    return out


def gather_metrics() -> Dict[str, int]:
    integrity_issues = sum(gather_integrity_issues().values())
    contributors_list = [
        s for s in parse_contributors() if not s.lower().startswith("first-timers")
    ]
    contributors = len(contributors_list)
    logs_healed = logs_healed_count()
    nodes = federation_nodes_synced()
    return {
        "logs_healed": logs_healed,
        "contributors": contributors,
        "integrity_issues": integrity_issues,
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
        f"| Contributors added | {metrics['contributors']} |",
        f"| Integrity issues remaining | {metrics['integrity_issues']} |",
        f"| Federation nodes synced | {metrics['nodes']} |",
        "",
        "## Contributor Stories",
        "",
    ]
    for s in stories:
        contributor_name = s.get("contributor", s.get("saint", "Unknown"))
        story = s.get("story", "")
        lines.append(f"- **{contributor_name}**: {story}")
    dash.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:  # pragma: no cover - CLI
    metrics = gather_metrics()
    stories = read_stories()
    write_dashboard(metrics, stories)


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
