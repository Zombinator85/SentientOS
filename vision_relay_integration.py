"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

"""Vision relay hooks integrating OCR output with avatar events."""

from pathlib import Path
from typing import Iterable
import json
from logging_config import get_log_path
from ocr_log_export import OCR_LOG

AVATAR_HOOK_LOG = get_log_path("avatar_vision_hooks.jsonl", "AVATAR_VISION_LOG")


def dispatch_ocr_events(entries: Iterable[dict]) -> None:
    """Forward OCR log entries to the avatar sync bus."""
    AVATAR_HOOK_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(AVATAR_HOOK_LOG, "a", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry) + "\n")


def watch_relay(log_file: Path = OCR_LOG) -> None:
    """Tail the OCR log file and dispatch events as they arrive."""
    if not log_file.exists():
        return
    with open(log_file, "r", encoding="utf-8") as fh:
        for line in fh:
            try:
                dispatch_ocr_events([json.loads(line)])
            except Exception:
                continue


if __name__ == "__main__":
    watch_relay()
