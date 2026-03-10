from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sentientos.ops import main as ops_main


def main(argv: list[str] | None = None) -> int:
    forwarded = ["node", "bootstrap", *(argv or [])]
    return int(ops_main(forwarded, prog="node_bootstrap"))


if __name__ == "__main__":
    raise SystemExit(main())
