"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from logging_config import get_log_path
import datetime
import json
import os
import time
from pathlib import Path

import memory_manager as mm

QUESTION = os.getenv("SELF_REFLECTION_QUESTION", "What have you learned recently?")
LOG_DIR = get_log_path("self_reflections", "REFLECTION_LOG_DIR")
LOG_DIR.mkdir(parents=True, exist_ok=True)


def ask_ai(question: str) -> str:
    """Placeholder for an AI call. Returns a canned response if no model."""
    try:
        from relay_app import app  # type: ignore[import-untyped]  # local web app may be absent
        # Example call; in practice you'd POST to /relay
        return f"Reflection on: {question}"
    except Exception:
        return f"Reflection on: {question}"


def log_reflection(text: str) -> None:
    day_file = LOG_DIR / f"{datetime.date.today().isoformat()}.log"
    with open(day_file, "a", encoding="utf-8") as f:
        f.write(text + "\n")


def run_once() -> None:
    reply = ask_ai(QUESTION)
    log_reflection(reply)
    mm.append_memory(reply, tags=["self_reflection"], source="self_reflection_logger")


def run_forever(interval_hours: int = 6) -> None:
    while True:
        run_once()
        time.sleep(interval_hours * 3600)


if __name__ == "__main__":  # pragma: no cover - manual execution
    run_forever()
