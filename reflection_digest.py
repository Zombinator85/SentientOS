"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
"""Generate daily reflection summary digest."""
from logging_config import get_log_path
import datetime
import os
from pathlib import Path

DIGEST_FILE = get_log_path("reflection_digest.txt", "REFLECTION_DIGEST_FILE")
LOG_DIR = get_log_path("self_reflections", "REFLECTION_LOG_DIR")
DIGEST_FILE.parent.mkdir(parents=True, exist_ok=True)


def generate_digest(period_hours: int = 24) -> str:
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(hours=period_hours)
    texts: list[str] = []
    for fp in sorted(LOG_DIR.glob("*.log")):
        day = fp.stem
        try:
            dt = datetime.date.fromisoformat(day)
        except Exception:
            continue
        if dt < cutoff.date():
            continue
        texts.extend(fp.read_text(encoding="utf-8").splitlines())
    if not texts:
        return ""
    summary = f"Reflection Digest {datetime.date.today().isoformat()}\n\n" + "\n".join(texts)
    DIGEST_FILE.write_text(summary, encoding="utf-8")
    return str(DIGEST_FILE)


if __name__ == "__main__":  # pragma: no cover - manual
    print(generate_digest())
