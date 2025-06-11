from logging_config import get_log_path
import json
import time
from pathlib import Path

from sentientos.privilege import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
HERESY_LOG = get_log_path("heresy_log.jsonl")
WATCH_FILES = [get_log_path("support_log.jsonl"), get_log_path("confessional_log.jsonl")]


def watch(period: float = 2.0) -> None:
    positions = {p: p.stat().st_size if p.exists() else 0 for p in WATCH_FILES}
    while True:
        for p in WATCH_FILES:
            if not p.exists():
                continue
            size = p.stat().st_size
            if size > positions[p]:
                text = p.read_text(encoding="utf-8")[positions[p] : size]
                for line in text.splitlines():
                    if "forbidden" in line or "unritualized" in line:
                        entry = {"timestamp": time.time(), "file": str(p), "line": line}
                        with HERESY_LOG.open("a", encoding="utf-8") as f:
                            f.write(json.dumps(entry) + "\n")
                positions[p] = size
        time.sleep(period)


if __name__ == "__main__":  # pragma: no cover - daemon
    watch()
