from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import requests

from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()
require_lumos_approval()
# Monitor OpenAI model usage and log remaining quotas.

MODELS = ["o3", "o4-mini", "o4-mini-high", "GPT-4.1"]
API_URL = "https://api.openai.com/dashboard/billing/usage"


def fetch_usage(model: str) -> Optional[Dict[str, Any]]:
    """Fetch usage statistics for a given model."""
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        print("OPENAI_API_KEY not set")
        return None
    headers = {"Authorization": f"Bearer {key}"}
    try:
        resp = requests.get(API_URL, params={"model": model}, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        used = data.get("messages_used") or data.get("total_usage", 0)
        remaining = data.get("messages_remaining") or data.get("messages_limit", 0) - used
        return {"messages_used": used, "messages_remaining": remaining}
    except Exception as exc:
        print(f"Failed to fetch usage for {model}: {exc}")
        return None


def monitor(interval: int, output: Path) -> None:
    """Periodically record usage for each model."""
    while True:
        entries = []
        for model in MODELS:
            usage = fetch_usage(model)
            if usage is None:
                continue
            total = usage["messages_used"] + usage["messages_remaining"]
            remaining_pct = usage["messages_remaining"] / total if total else 0
            if remaining_pct < 0.10:
                print(f"Warning: {model} below 10% quota")
            entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "model": model,
                "messages_used": usage["messages_used"],
                "messages_remaining": usage["messages_remaining"],
            }
            entries.append(entry)
        if entries:
            with output.open("a", encoding="utf-8") as fh:
                for entry in entries:
                    fh.write(json.dumps(entry) + "\n")
        time.sleep(interval * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="Monitor OpenAI usage")
    parser.add_argument("--interval", type=int, default=60, help="Polling interval in minutes")
    parser.add_argument("--output", type=Path, required=True, help="Path for usage log")
    args = parser.parse_args()

    monitor(args.interval, args.output)


if __name__ == "__main__":
    main()
