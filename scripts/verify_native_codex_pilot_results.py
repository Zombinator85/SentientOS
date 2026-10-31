from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sentientos.native_codex_pilot_results import (
    DEFAULT_PILOT_PATH,
    verify_native_codex_pilot_results,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify captured native pilot hashes and result-summary consistency "
            "without opening the held-out answer key."
        )
    )
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--pilot-path", type=Path, default=DEFAULT_PILOT_PATH)
    args = parser.parse_args(argv)

    try:
        report = verify_native_codex_pilot_results(args.repository_root, args.pilot_path)
    except (OSError, UnicodeDecodeError, ValueError, TypeError) as exc:
        print(
            json.dumps({"status": "integrity_error", "error": str(exc)}, sort_keys=True),
            file=sys.stderr,
        )
        return 1

    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
