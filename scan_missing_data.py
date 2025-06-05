from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

require_admin_banner()
require_lumos_approval()

import argparse
import json
from pathlib import Path


def scan_logs(root: Path) -> int:
    missing = 0
    for path in root.rglob("*.json"):
        if not path.is_file():
            continue
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            if "data" not in data:
                print(f"Missing data in: {path}")
                missing += 1
        except Exception as e:
            print(f"Error in {path}: {e}")
    return missing


def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Scan logs for missing 'data' field")
    ap.add_argument("target", nargs="?", default="logs", help="Directory to scan")
    args = ap.parse_args()
    count = scan_logs(Path(args.target))
    print(f"files missing data: {count}")


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
