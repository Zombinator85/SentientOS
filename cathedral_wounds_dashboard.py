from __future__ import annotations
import datetime
import json
from pathlib import Path
from typing import Dict

from sentientos.privilege import require_admin_banner, require_lumos_approval
from logging_config import get_log_path

"""Privilege validation sequence: do not remove. See doctrine for details."""

require_admin_banner()  # Enforced: privilege validation sequence—do not remove. See doctrine.
require_lumos_approval()


def gather_integrity_issues() -> Dict[str, int]:
    """Return a mapping of integrity issue files to entry counts."""
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

    history_file = Path("docs/integrity_issue_history.json")
    history = []
    if history_file.exists():
        history = json.loads(history_file.read_text(encoding="utf-8"))
    total = sum(counts.values())
    history.append({"date": str(datetime.date.today()), "total": total})
    history_file.write_text(json.dumps(history, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Integrity Issue Dashboard",
        "",
        f"Updated: {datetime.date.today()}",
        "",
        "## Current Integrity Issue Counts",
        "",
        "| Log | Integrity issues |",
        "|-----|-----------------|",
    ]
    for log, cnt in sorted(counts.items()):
        lines.append(f"| {log} | {cnt} |")
    lines.extend(
        [
            "",
            "## Repair Progress",
            "",
            "| Date | Total Integrity Issues |",
            "|------|-----------------------|",
        ]
    )
    for entry in history:
        lines.append(f"| {entry['date']} | {entry['total']} |")
    lines.extend(["", "## Audit Contributors", ""])
    contributors = parse_contributors()
    for s in contributors:
        lines.append(f"- {s}")
    dash.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_contributors() -> list[str]:
    text = Path("CONTRIBUTORS.md").read_text(encoding="utf-8").splitlines()
    names: list[str] = []
    start = False
    for line in text:
        if line.strip() == "## Audit Contributors":
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
    counts = gather_integrity_issues()
    update_dashboard(counts)


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
