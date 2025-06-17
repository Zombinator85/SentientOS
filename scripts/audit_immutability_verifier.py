from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

"""Verify immutability of audit logs under given paths."""

import sys
from pathlib import Path
import audit_immutability as ai


def verify_paths(paths: list[Path]) -> bool:
    ok = True
    for base in paths:
        if base.is_file():
            files = [base]
        else:
            files = list(base.rglob("*.jsonl"))
        for f in files:
            if not ai.verify(f):
                print(f"Integrity failure: {f}")
                ok = False
    return ok


def main(args: list[str] | None = None) -> None:
    paths = [Path(p) for p in (args or sys.argv[1:] or ["logs"])]
    if not verify_paths(paths):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
