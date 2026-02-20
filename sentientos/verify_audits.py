from __future__ import annotations

"""Portable verify_audits module entrypoint."""

import sys
from typing import Sequence

from scripts.verify_audits import main as scripts_main


def main(argv: Sequence[str] | None = None) -> int:
    forwarded = list(argv) if argv is not None else sys.argv[1:]
    return int(scripts_main(forwarded))


if __name__ == "__main__":
    raise SystemExit(main())
