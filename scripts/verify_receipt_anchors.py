from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sentientos.receipt_anchors import verify_receipt_anchors


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify signed receipt epoch anchors")
    parser.add_argument("--last", type=int, default=None, help="Verify only the last N anchors")
    parser.add_argument("--require-tip", action="store_true", help="Require latest anchor to match current receipt chain tip")
    args = parser.parse_args()

    result = verify_receipt_anchors(Path.cwd(), last=args.last, require_tip=args.require_tip)
    print(json.dumps(result.to_dict(), sort_keys=True))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
