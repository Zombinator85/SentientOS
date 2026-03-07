from __future__ import annotations

import sys
from collections.abc import Sequence


def verify_audits_main(argv: Sequence[str] | None = None) -> int:
    from scripts.verify_audits import main as scripts_main

    forwarded = list(argv) if argv is not None else sys.argv[1:]
    return int(scripts_main(forwarded))


def main(argv: Sequence[str] | None = None) -> int:
    return verify_audits_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
