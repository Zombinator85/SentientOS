from __future__ import annotations
from logging_config import get_log_path

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

LOG_PATH = get_log_path("avatar_feedback_ritual.jsonl")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_feedback(data: dict[str, Any]) -> dict[str, Any]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        **data,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def adapt_ritual(feedback: str) -> dict[str, Any]:
    """Log feedback and return simple trend analysis."""
    history: list[dict[str, Any]] = []
    if LOG_PATH.exists():
        for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
            try:
                history.append(json.loads(line))
            except Exception:
                continue
    positive = sum(1 for e in history if str(e.get("feedback", "")).lower() in {"love", "like", "joy", "good"})
    negative = sum(1 for e in history if str(e.get("feedback", "")).lower() in {"dislike", "anger", "bad"})
    trend = "neutral"
    if positive > negative:
        trend = "positive"
    elif negative > positive:
        trend = "negative"
    info = {"feedback": feedback, "trend": trend}
    return log_feedback(info)


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Avatar feedback-driven ritual engine")
    ap.add_argument("feedback")
    args = ap.parse_args()
    entry = adapt_ritual(args.feedback)
    print(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
