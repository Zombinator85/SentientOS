from __future__ import annotations

from collections.abc import Sequence
import sys

from sentientos.ops import main as ops_main


def main(argv: Sequence[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    return int(ops_main(["audit", *raw], prog="python -m sentientos.audit"))


if __name__ == "__main__":
    raise SystemExit(main())
