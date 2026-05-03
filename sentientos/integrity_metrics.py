from __future__ import annotations

"""Neutral formal integrity metrics helpers.

These parsers are pure data extraction primitives for formal/reporting modules,
without dashboard or symbolic dependencies.
"""

from pathlib import Path
from typing import Dict

from logging_config import get_log_path


def gather_integrity_issues() -> Dict[str, int]:
    """Return mapping of integrity issue files to entry counts."""
    log_dir = get_log_path("dummy").parent
    counts: Dict[str, int] = {}
    for file in log_dir.glob("*.wounds"):
        lines = [ln for ln in file.read_text(encoding="utf-8").splitlines() if ln.strip()]
        counts[file.name] = len(lines)
    for log in log_dir.glob("*.jsonl"):
        if log.with_suffix(log.suffix + ".wounds") not in counts:
            counts[log.name + ".wounds"] = 0
    return counts


def parse_contributors(path: Path | None = None) -> list[str]:
    """Parse CONTRIBUTORS.md audit contributor section."""
    contributors_path = path or Path("CONTRIBUTORS.md")
    text = contributors_path.read_text(encoding="utf-8").splitlines()
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
