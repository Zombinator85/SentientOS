from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))


import requests

from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()
require_lumos_approval()
from scripts.auto_approve import is_auto_approve

# Send a Slack message and optional file snippet.


def post_message(webhook: str, text: str) -> bool:
    """Post a text message to Slack."""
    try:
        resp = requests.post(webhook, json={"text": text}, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as exc:
        print(f"Slack post failed: {exc}")
        return False


def upload_file(webhook: str, path: Path) -> None:
    """Upload file content as snippet."""
    content = path.read_text(encoding="utf-8")
    snippet = f"```{content}```"
    post_message(webhook, snippet)


def main() -> None:
    parser = argparse.ArgumentParser(description="Send Slack notifications")
    parser.add_argument("--webhook", required=True, help="Slack webhook URL")
    parser.add_argument("--message", required=True, help="Message text")
    parser.add_argument("--file", type=Path, help="Optional file to upload")
    args = parser.parse_args()

    if post_message(args.webhook, args.message) and args.file:
        if args.file.exists():
            upload_file(args.webhook, args.file)
        else:
            print(f"File not found: {args.file}")


if __name__ == "__main__":
    main()
