from __future__ import annotations
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()

import os
import sys
import time
from typing import Optional

import requests


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


def main(argv: Optional[list[str]] = None) -> None:
    argv = argv or sys.argv[1:]
    if not argv:
        print("usage: wait_for_health.py <url> [timeout]", file=sys.stderr)
        sys.exit(2)
    url = argv[0]
    timeout = float(argv[1]) if len(argv) > 1 else float(os.getenv("WAIT_TIMEOUT", "60"))
    wait_for(url, timeout=timeout)


if __name__ == "__main__":  # pragma: no cover
    try:
        main()
    except Exception as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
