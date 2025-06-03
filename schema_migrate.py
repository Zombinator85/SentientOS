from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Callable

from admin_utils import require_admin_banner

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details.

SentientOS Schema Migrator.

This ritual upgrades data files to the latest schema and logs each action in the
cathedral ledger. It may be invoked directly or as part of a federation
onboarding ceremony.

Example:
    python schema_migrate.py logs/example.jsonl
"""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.

SCHEMA_VERSION = "2.0"
MIGRATION_LOG = get_log_path("schema_migrate.jsonl", "SCHEMA_MIGRATION_LOG")
MIGRATION_LOG.parent.mkdir(parents=True, exist_ok=True)

DEFAULTS: Dict[str, Callable[[], Any]] = {
    "schema_version": lambda: SCHEMA_VERSION,
    "data": lambda: {},
    "timestamp": lambda: datetime.utcnow().isoformat(),
}


def log_migration(path: Path, original: str) -> None:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "file": str(path),
        "from_version": original,
        "to_version": SCHEMA_VERSION,
    }
    with MIGRATION_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def migrate_file(path: Path) -> Dict[str, int]:
    migrated = 0
    untouched = 0
    if not path.exists():
        return {"migrated": migrated, "untouched": untouched}
    new_lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except Exception:
            new_lines.append(line)
            continue
        version = str(entry.get("schema_version", "1.0"))
        changed = False
        if version != SCHEMA_VERSION:
            entry["previous_schema_version"] = version
            entry["schema_version"] = SCHEMA_VERSION
            changed = True
        for key, func in DEFAULTS.items():
            if key not in entry:
                entry[key] = func()
                changed = True
        if changed:
            migrated += 1
            log_migration(path, version)
        else:
            untouched += 1
        new_lines.append(json.dumps(entry, ensure_ascii=False))
    path.write_text("\n".join(new_lines) + ("\n" if new_lines else ""), encoding="utf-8")
    return {"migrated": migrated, "untouched": untouched}


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Upgrade data files to latest schema")
    ap.add_argument("target", help="File or directory to migrate")
    args = ap.parse_args()
    target = Path(args.target)
    stats = {"migrated": 0, "untouched": 0}
    paths = [target]
    if target.is_dir():
        paths = list(target.glob("*.jsonl"))
    for p in paths:
        res = migrate_file(p)
        for k in stats:
            stats[k] += res[k]
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()

# May memory be healed and preserved.
