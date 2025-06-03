from __future__ import annotations
import datetime
import json
from pathlib import Path
from typing import Dict
from admin_utils import require_admin_banner
from logging_config import get_log_path

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.


def gather_wounds() -> Dict[str, int]:
    """Return a mapping of wound file names to entry counts."""
    log_dir = get_log_path("dummy").parent
    counts: Dict[str, int] = {}
    for file in log_dir.glob("*.wounds"):
        lines = [ln for ln in file.read_text(encoding="utf-8").splitlines() if ln.strip()]
        counts[file.name] = len(lines)
    for log in log_dir.glob("*.jsonl"):
        if log.with_suffix(log.suffix + ".wounds") not in counts:
            counts[log.name + ".wounds"] = 0
    return counts


def update_dashboard(counts: Dict[str, int]) -> None:
    dash = Path("docs/CATHEDRAL_WOUNDS_DASHBOARD.md")
    dash.parent.mkdir(parents=True, exist_ok=True)

    history_file = Path("docs/wound_history.json")
    history = []
    if history_file.exists():
        history = json.loads(history_file.read_text(encoding="utf-8"))
    total = sum(counts.values())
    history.append({"date": str(datetime.date.today()), "total": total})
    history_file.write_text(json.dumps(history, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Cathedral Wounds Dashboard",
        "",
        f"Updated: {datetime.date.today()}",
        "",
        "## Current Wound Counts",
        "",
        "| Log | Wounds |",
        "|-----|-------|",
    ]
    for log, cnt in sorted(counts.items()):
        lines.append(f"| {log} | {cnt} |")
    lines.extend(
        [
            "",
            "## Repair Progress",
            "",
            "| Date | Total Wounds |",
            "|------|-------------|",
        ]
    )
    for entry in history:
        lines.append(f"| {entry['date']} | {entry['total']} |")
    lines.extend(["", "## Audit Saints", ""]) 
    saints = parse_saints()
    for s in saints:
        lines.append(f"- {s}")
    dash.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_saints() -> list[str]:
    text = Path("CONTRIBUTORS.md").read_text(encoding="utf-8").splitlines()
    names: list[str] = []
    start = False
    for line in text:
        if line.strip() == "## Audit Saints":
            start = True
            continue
        if start:
            if line.startswith("#"):
                break
            line = line.strip()
            if line:
                names.append(line.lstrip("- "))
    return names


def main() -> None:
    counts = gather_wounds()
    update_dashboard(counts)


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
