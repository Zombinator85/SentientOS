import json
from pathlib import Path

import os
import daily_theme
import ledger
from admin_utils import require_admin_banner


"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
def generate_recap(limit: int = 20) -> dict:
    support = ledger.summarize_log(Path("logs/support_log.jsonl"), limit)
    federation = ledger.summarize_log(Path("logs/federation_log.jsonl"), limit)
    heresy = ledger.summarize_log(Path(os.getenv("HERESY_LOG", "logs/heresy_log.jsonl")), limit)
    theme = daily_theme.latest()
    return {
        "theme": theme,
        "support_recent": support["recent"],
        "federation_recent": federation["recent"],
        "heresy_recent": heresy["recent"],
    }


def main() -> None:
    require_admin_banner()
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
