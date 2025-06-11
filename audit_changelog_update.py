"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
require_admin_banner()
require_lumos_approval()
from admin_utils import require_admin_banner, require_lumos_approval

import argparse
import json
from datetime import datetime
from pathlib import Path

CHANGELOG = Path("docs/CHANGELOG.md")
LEDGER = Path("docs/AUDIT_LEDGER.md")


def append_entry(message: str) -> dict[str, str]:
    now = datetime.utcnow()
    month = now.strftime("%Y-%m")
    cl_lines = CHANGELOG.read_text(encoding="utf-8").splitlines()
    heading = f"## {month}"
    if heading not in cl_lines:
        cl_lines.extend(["", heading])
    idx = cl_lines.index(heading) + 1
    cl_lines.insert(idx, f"- {message}")
    CHANGELOG.write_text("\n".join(cl_lines), encoding="utf-8")

    ld_lines = LEDGER.read_text(encoding="utf-8").splitlines()
    ld_lines.append(f"- {now.isoformat()} {message}")
    LEDGER.write_text("\n".join(ld_lines), encoding="utf-8")
    return {"timestamp": now.isoformat(), "message": message}


def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Append changelog and ledger entry")
    ap.add_argument("message", help="summary message")
    args = ap.parse_args()
    entry = append_entry(args.message)
    print(json.dumps(entry, indent=2))


if __name__ == "__main__":  # pragma: no cover
    main()
