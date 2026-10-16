"""Read-only verifier for repository-owned audit log hash chains."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sentientos.audit_chain_gate import verify_audit_chain


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)

    result = verify_audit_chain(args.repo_root)
    print(
        f"audit_chain status={result.status} checked_files={result.checked_files} "
        f"break_count={result.break_count}"
    )
    return 0 if result.ok and result.checked_files > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
