#!/usr/bin/env python
"""Emit a versioned, read-only snapshot of the local checkout."""

from __future__ import annotations

import argparse
import json
import sys

from sentientos.codex_fresh_chat_orientation import SCHEMA_VERSION, OrientationError, observe_orientation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Observe local SentientOS checkout context without granting authority.")
    parser.add_argument("--repository", default=".", help="path inside the local Git checkout (default: current directory)")
    args = parser.parse_args(argv)
    try:
        payload = observe_orientation(args.repository)
        code = 0
    except OrientationError as exc:
        payload = {"schema_version": SCHEMA_VERSION, "status": "orientation_failed", "error": str(exc)}
        code = 2
    print(json.dumps(payload, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
