#!/usr/bin/env python3
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
"""
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import os
import time
import urllib.request
from logging_config import get_log_path

from sentientos.optional_deps import optional_import

from scripts.auto_approve import prompt_yes_no

# Summarize token usage and post to Slack.


LOG_FILE = get_log_path("usage.jsonl")


def aggregate() -> dict[str, dict[str, int]]:
    data: dict[str, dict[str, int]] = collections.defaultdict(lambda: collections.defaultdict(int))
    if not LOG_FILE.exists():
        return data
    for line in LOG_FILE.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except Exception:
            continue
        ts = entry.get("timestamp")
        model = entry.get("model")
        usage = entry.get("usage", {}).get("total_tokens", 0)
        if not ts or not model:
            continue
        day = ts.split("T")[0]
        data[day][model] += int(usage)
    return data


def format_report(data: dict[str, dict[str, int]]) -> str:
    lines = ["*Daily usage summary*"]
    for day in sorted(data):
        lines.append(f"*{day}*")
        for model, tokens in data[day].items():
            lines.append(f"- {model}: {tokens} tokens")
    return "\n".join(lines)


def post_to_slack(msg: str) -> None:
    url = os.getenv("SLACK_WEBHOOK_URL")
    if not url:
        print("SLACK_WEBHOOK_URL not set")
        return
    while True:
        requests = optional_import("requests", feature="quota_reporter")
        if requests:
            resp = requests.post(url, json={"text": msg})
            status_code = resp.status_code
            retry_after = resp.headers.get("Retry-After")
        else:
            payload = json.dumps({"text": msg}).encode("utf-8")
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req) as response:
                status_code = response.status
                retry_after = response.headers.get("Retry-After")
        if status_code == 429:
            delay = int(retry_after or "1")
            time.sleep(delay)
            continue
        if status_code >= 400:
            raise RuntimeError(f"Slack error {status_code}")
        break


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report usage to Slack")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    data = aggregate()
    msg = format_report(data)
    if args.dry_run:
        print(msg)
        return 0
    if os.getenv("LUMOS_AUTO_APPROVE") != "1" and not prompt_yes_no("Send report to Slack?"):
        print("Aborted")
        return 1
    post_to_slack(msg)
    print("Posted usage summary")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
