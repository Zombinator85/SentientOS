from __future__ import annotations
from logging_config import get_log_path

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from admin_utils import require_admin_banner

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.

LOG_PATH = get_log_path("avatar_lorebook.jsonl")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def compile_lorebook(out: Path) -> Path:
    """Compile simple lorebook from logs."""
    entries = []
    if LOG_PATH.exists():
        for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
            try:
                entries.append(json.loads(line))
            except Exception:
                continue
    out.write_text(json.dumps(entries, indent=2))
    return out


def main() -> None:
    require_admin_banner()
    import argparse

    ap = argparse.ArgumentParser(description="Avatar ritual lorebook generator")
    ap.add_argument("out")
    args = ap.parse_args()
    path = compile_lorebook(Path(args.out))
    print(str(path))


if __name__ == "__main__":
    main()
