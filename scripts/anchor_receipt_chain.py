from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sentientos.receipt_anchors import create_anchor
from sentientos.receipt_chain import verify_receipt_chain


def main() -> int:
    repo_root = Path.cwd()
    chain = verify_receipt_chain(repo_root)
    if not chain.ok:
        print(json.dumps({"error": "receipt_chain_broken", "chain": chain.to_dict()}, sort_keys=True))
        return 1
    try:
        anchor = create_anchor(repo_root)
    except RuntimeError as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True))
        return 1
    print(
        json.dumps(
            {
                "status": "anchored",
                "anchor_id": anchor.anchor_id,
                "receipt_chain_tip_hash": anchor.receipt_chain_tip_hash,
                "public_key_id": anchor.public_key_id,
                "algorithm": anchor.algorithm,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
