"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()
require_lumos_approval()
from __future__ import annotations
from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

import smtplib
from email.message import EmailMessage

from admin_utils import require_admin_banner, require_lumos_approval

# Generate daily usage summaries and optionally email them.


def load_usage(path: Path, since: datetime) -> Dict[str, List[dict]]:
    """Load usage records within the timeframe grouped by model."""
    result: Dict[str, List[dict]] = defaultdict(list)
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
            ts = datetime.fromisoformat(rec["timestamp"])
        except Exception:
            continue
        if ts >= since:
            result[rec["model"]].append(rec)
    return result


def compute_stats(records: List[dict]) -> Tuple[int, float, str]:
    """Return total used, low water pct, and peak hour."""
    if not records:
        return 0, 1.0, "N/A"
    records.sort(key=lambda r: r["timestamp"])
    total_used = records[-1]["messages_used"] - records[0]["messages_used"]
    low_pct = 1.0
    hourly: Dict[str, int] = defaultdict(int)
    prev = records[0]
    for rec in records[1:]:
        delta = rec["messages_used"] - prev["messages_used"]
        hour = rec["timestamp"][11:13]
        hourly[hour] += max(delta, 0)
        total = rec["messages_used"] + rec["messages_remaining"]
        if total:
            pct = rec["messages_remaining"] / total
            low_pct = min(low_pct, pct)
        prev = rec
    peak = max(hourly.items(), key=lambda x: x[1])[0] if hourly else "N/A"
    return total_used, low_pct, peak


def build_report(data: Dict[str, List[dict]]) -> str:
    """Create a markdown report from usage data."""
    lines = ["# Daily Usage Report", ""]
    lines.append("| Model | Messages Used | Peak Hour (UTC) | Low Water % | Recommendation |")
    lines.append("|-------|---------------|-----------------|-------------|---------------|")
    for model, records in data.items():
        used, low_pct, peak = compute_stats(records)
        recommend = "Increase allocation" if low_pct < 0.15 else "OK"
        lines.append(
            f"| {model} | {used} | {peak} | {low_pct:.1%} | {recommend} |")
    return "\n".join(lines) + "\n"


def send_email(to_addr: str, body: str) -> None:
    """Send report via SMTP using environment variables."""
    host = os.getenv("SMTP_HOST")
    if not host:
        print("SMTP not configured")
        return
    port = int(os.getenv("SMTP_PORT", "25"))
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASS")
    from_addr = os.getenv("SMTP_FROM", user or "noreply@example.com")
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = "Daily Usage Report"
    msg.set_content(body)
    with smtplib.SMTP(host, port) as smtp:
        if user and password:
            smtp.login(user, password)
        smtp.send_message(msg)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate daily usage report")
    parser.add_argument("--usage-path", type=Path, required=True, help="Usage monitor log")
    parser.add_argument("--report-path", type=Path, required=True, help="Output markdown path")
    parser.add_argument("--email-to", help="Email address for sending the report")
    args = parser.parse_args()

    since = datetime.utcnow() - timedelta(days=1)
    usage = load_usage(args.usage_path, since)
    report = build_report(usage)
    args.report_path.write_text(report, encoding="utf-8")
    print(f"Wrote {args.report_path}")
    if args.email_to:
        send_email(args.email_to, report)


if __name__ == "__main__":
    main()
