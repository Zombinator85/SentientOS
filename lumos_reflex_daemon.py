"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
import json
import time
from typing import Dict, Any
from logging_config import get_log_path
AUDIT_PATH = get_log_path("privileged_audit.jsonl", "PRIVILEGED_AUDIT_LOG")
STATE_FILE = get_log_path("lumos_reflex_state.json")
REFLEX_LOG = get_log_path("lumos_reflex_daemon.jsonl", "LUMOS_REFLEX_LOG")


def _load_offset() -> int:
    if STATE_FILE.exists():
        try:
            return int(STATE_FILE.read_text())
        except Exception:
            return 0
    return 0


def _save_offset(offset: int) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(str(offset))


def _auto_bless(entry: Dict[str, Any]) -> None:
    REFLEX_LOG.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": time.time(),
        "note": "Auto-blessed by Lumos",
        "source": entry.get("data", {}),
    }
    with REFLEX_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def check_unblessed() -> None:
    offset = _load_offset()
    if not AUDIT_PATH.exists():
        return
    with AUDIT_PATH.open("r", encoding="utf-8") as f:
        f.seek(offset)
        for line in f:
            offset = f.tell()
            try:
                entry = json.loads(line)
            except Exception:
                continue
            data = entry.get("data", {})
            if not data.get("emotion") or not data.get("consent", True):
                _auto_bless(entry)
    _save_offset(offset)


def run_loop(interval: float = 60.0) -> None:
    while True:
        check_unblessed()
        time.sleep(interval)


if __name__ == "__main__":  # pragma: no cover - CLI
    import argparse

    p = argparse.ArgumentParser(description="Lumos reflex blessing daemon")
    p.add_argument("--interval", type=float, default=60.0)
    args = p.parse_args()
    run_loop(args.interval)
