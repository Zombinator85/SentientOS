from __future__ import annotations
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()

import argparse
import os
import sys
import time
from typing import Optional

import requests  # type: ignore[import-untyped,unused-ignore]  # justified: optional dependency


def wait_for(url: str, timeout: float = 60.0, interval: float = 2.0) -> None:
    """Poll ``url`` until an HTTP 200 is received or ``timeout`` seconds pass."""
    end = time.time() + timeout
    while time.time() < end:
        try:
            response = requests.get(url, timeout=interval)
            if response.ok:
                return
        except Exception:
            pass
        time.sleep(interval)
    raise RuntimeError(f"service at {url} not healthy after {timeout} seconds")


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Wait for a service health endpoint")
    parser.add_argument("--url", required=True, help="URL of the status endpoint")
    parser.add_argument(
        "--max-wait",
        type=float,
        default=float(os.getenv("WAIT_TIMEOUT", "60")),
        help="Maximum time in seconds to wait for service health",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> None:
    args = parse_args(argv or sys.argv[1:])
    wait_for(args.url, timeout=args.max_wait)


if __name__ == "__main__":  # pragma: no cover
    try:
        main()
    except Exception as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
