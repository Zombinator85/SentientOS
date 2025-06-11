"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
require_admin_banner()
require_lumos_approval()
from admin_utils import require_admin_banner, require_lumos_approval

from logging_config import get_log_path
import json
from pathlib import Path
import os
import daily_theme
import ledger
def generate_recap(limit: int = 20) -> dict:
    support = ledger.summarize_log(get_log_path("support_log.jsonl"), limit)
    federation = ledger.summarize_log(get_log_path("federation_log.jsonl"), limit)
    heresy = ledger.summarize_log(get_log_path("heresy_log.jsonl", "HERESY_LOG"), limit)
    theme = daily_theme.latest()
    return {
        "theme": theme,
        "support_recent": support["recent"],
        "federation_recent": federation["recent"],
        "heresy_recent": heresy["recent"],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Federation recap generator")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--out")
    args = ap.parse_args()
    recap = generate_recap(args.limit)
    text = json.dumps(recap, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(args.out)
    else:
        print(text)


if __name__ == "__main__":
    main()
