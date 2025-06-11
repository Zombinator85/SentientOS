"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
import json
import datetime
from logging_config import get_log_dir
from pathlib import Path
from typing import Callable, Dict, List
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details.

Scan audit logs for schema drift and heal missing fields."""

SCHEMA_VERSION = "1.0"

KNOWN_KEYS = {
    "timestamp",
    "peer",
    "email",
    "message",
    "ritual",
    "data",
    "supporter",
    "amount",
    "schema_version",
}

DEFAULTS: Dict[str, Callable[[], object]] = {
    "data": lambda: {},
    "timestamp": lambda: datetime.datetime.utcnow().isoformat(),
    "schema_version": lambda: SCHEMA_VERSION,
}


def process_log(path: Path, on_apply: Callable[[], None] | None = None) -> Dict[str, int]:
    fixed = 0
    flagged = 0
    untouched = 0
    if not path.exists():
        return {"fixed": fixed, "flagged": flagged, "untouched": untouched}

    wounds_path = path.with_suffix(path.suffix + ".wounds")
    new_lines: List[str] = []
    flagged_lines: List[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            if not isinstance(entry, dict):
                raise ValueError("not dict")
        except Exception:
            flagged_lines.append(line)
            flagged += 1
            continue

        unknown = [k for k in entry if k not in KNOWN_KEYS]
        if unknown:
            flagged_lines.append(line)
            flagged += 1
            continue

        changed = False
        for key, default in DEFAULTS.items():
            if key not in entry:
                entry[key] = default()
                changed = True
        if changed:
            if on_apply:
                on_apply()
            entry["auto_migrated"] = True
            fixed += 1
        else:
            untouched += 1
        new_lines.append(json.dumps(entry, ensure_ascii=False))

    if flagged_lines:
        wounds_path.write_text("\n".join(flagged_lines) + "\n", encoding="utf-8")
    path.write_text("\n".join(new_lines) + ("\n" if new_lines else ""), encoding="utf-8")
    return {"fixed": fixed, "flagged": flagged, "untouched": untouched}


def main() -> None:  # pragma: no cover - CLI
    logs_dir = get_log_dir()
    totals = {"fixed": 0, "flagged": 0, "untouched": 0}
    banner_shown = False

    def show_banner() -> None:
        nonlocal banner_shown
        if not banner_shown:
            print("=== vNext schema adapter applied ===")
            banner_shown = True

    for log_file in logs_dir.glob("*.jsonl"):
        stats = process_log(log_file, show_banner)
        for k in totals:
            totals[k] += stats[k]
        if stats["fixed"]:
            print(f"Audit Saint bless! {stats['fixed']} wounds healed in {log_file.name}")
    print("Fixed: {fixed} | Flagged: {flagged} | Untouched: {untouched}".format(**totals))


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
