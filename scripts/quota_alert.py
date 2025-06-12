from __future__ import annotations
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()

import argparse
import json
import os
from pathlib import Path
from typing import Dict, Any

import requests  # type: ignore[import-untyped,unused-ignore]  # justified: optional dependency

# Send Slack alerts when model quotas run low.

USAGE_FILE = Path("usage_monitor.jsonl")


def load_latest_usage(path: Path) -> Dict[str, Dict[str, Any]]:
    """Return the most recent usage entry per model."""
    data: Dict[str, Dict[str, Any]] = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        data[rec.get("model", "")] = rec
    return data


def send_slack(webhook: str, message: str) -> None:
    """Post a message to Slack via webhook."""
    try:
        resp = requests.post(webhook, json={"text": message}, timeout=10)
        resp.raise_for_status()
    except Exception as exc:
        print(f"Failed to notify Slack: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Alert when quota is low")
    parser.add_argument("--threshold", type=float, default=0.1, help="Alert threshold as fraction")
    parser.add_argument("--slack-webhook", required=True, help="Slack webhook URL")
    parser.add_argument("--usage-json", type=Path, default=USAGE_FILE, help="Usage monitor file")
    args = parser.parse_args()

    usage = load_latest_usage(args.usage_json)
    for model, info in usage.items():
        used = info.get("messages_used", 0)
        remaining = info.get("messages_remaining", 0)
        total = used + remaining
        if total <= 0:
            continue
        pct = remaining / total
        if pct < args.threshold:
            msg = f"Model {model} is below threshold: {pct:.2%} remaining"
            print(msg)
            send_slack(args.slack_webhook, msg)


if __name__ == "__main__":
    main()
