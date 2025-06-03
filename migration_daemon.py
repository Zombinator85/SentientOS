from admin_utils import require_admin_banner
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.

"""Automated daemon to apply schema migrations on a schedule.

This tool runs ``fix_audit_schema.process_log`` on every ``.jsonl`` log file
in the given directory. Any healed entries are recorded in
``logs/migration_ledger.jsonl``. Intended to run periodically via ``cron``
or another task scheduler.
"""

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from logging_config import get_log_path
import fix_audit_schema

LEDGER = get_log_path("migration_ledger.jsonl")
LEDGER.parent.mkdir(parents=True, exist_ok=True)


def _record_fix(path: Path, count: int) -> None:
    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "file": str(path),
        "action": f"auto_migrated_entries({count})",
    }
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _run_once(target: Path) -> None:
    files = [target] if target.is_file() else sorted(target.glob("*.jsonl"))
    for fp in files:
        stats = fix_audit_schema.process_log(fp)
        if stats.get("fixed"):
            _record_fix(fp, stats["fixed"])


def run_daemon(target: Path, interval: float) -> None:
    while True:
        _run_once(target)
        time.sleep(interval)


def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Auto-migrate logs on a schedule")
    ap.add_argument("--target", default="logs", help="File or directory to process")
    ap.add_argument("--interval", type=float, default=3600.0, help="Seconds between runs")
    ap.add_argument("--once", action="store_true", help="Run once instead of looping")
    args = ap.parse_args()
    target = Path(args.target)
    if args.once:
        _run_once(target)
    else:
        run_daemon(target, args.interval)


if __name__ == "__main__":
    main()
