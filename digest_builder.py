"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

"""Memory digest construction utilities.

This module consolidates raw memory fragments from ``memory_manager`` into a
single digest file for faster lookup. ``build_digest`` reads ``logs/memory`` and
writes ``logs/memory_digest.jsonl``. The digest is referenced by dashboard tools
and avatar recall scripts.
"""

from pathlib import Path
import json
from logging_config import get_log_path
import memory_manager as mm

DIGEST_PATH = get_log_path("memory_digest.jsonl", "MEMORY_DIGEST")


def build_digest() -> Path:
    """Compile a simple digest of all memory fragments."""
    DIGEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DIGEST_PATH, "w", encoding="utf-8") as out:
        for frag in mm.RAW_PATH.glob("*.json"):
            try:
                data = json.loads(frag.read_text(encoding="utf-8"))
                out.write(json.dumps(data) + "\n")
            except Exception:
                continue
    return DIGEST_PATH


if __name__ == "__main__":
    build_digest()
