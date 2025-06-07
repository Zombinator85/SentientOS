from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
import os
from datetime import date
from typing import Any, Dict

from admin_utils import require_admin_banner, require_lumos_approval

try:
    import requests  # type: ignore  # HTTP client optional
except Exception:  # pragma: no cover - optional
    requests = None

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

LOG_PATH = get_log_path("steward_rotation.jsonl")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_result(data: Dict[str, Any]) -> None:
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(data) + "\n")


def create_issue(repo: str, token: str, new_steward: str) -> Dict[str, Any]:
    if requests is None:
        raise RuntimeError("requests not available")
    url = f"https://api.github.com/repos/{repo}/issues"
    headers = {"Authorization": f"token {token}"}
    body = {
        "title": f"Steward Rotation {date.today().isoformat()}",
        "body": f"Proposed new steward: {new_steward}",
        "labels": ["steward"],
    }
    r = requests.post(url, headers=headers, json=body, timeout=10)
    result = {"status_code": r.status_code, "url": r.json().get("html_url")}
    log_result(result)
    return result


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Create steward rotation issue")
    ap.add_argument("repo", help="owner/repo")
    ap.add_argument("new_steward")
    ap.add_argument("--token", default=os.getenv("GITHUB_TOKEN"))
    ap.add_argument("--dry", action="store_true", help="Don't post, just log")
    args = ap.parse_args()
    data = {"repo": args.repo, "steward": args.new_steward, "dry": args.dry}
    if args.dry:
        log_result({"dry": True, **data})
        print(json.dumps({"dry": True}))
        return
    if not args.token:
        raise RuntimeError("GITHUB_TOKEN not provided")
    try:
        res = create_issue(args.repo, args.token, args.new_steward)
        print(json.dumps(res, indent=2))
    except Exception as e:  # pragma: no cover - network
        log_result({"error": str(e), **data})
        print(f"Error: {e}")


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
