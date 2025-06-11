from __future__ import annotations
from logging_config import get_log_path

from sentientos.privilege import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
"""Avatar Heirloom Transmission Ritual."""

import argparse
import json
import os
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("avatar_heirloom_transmissions.jsonl", "AVATAR_HEIRLOOM_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def transmit_heirlooms(source: str, target: str, files: List[Path]) -> Dict[str, str]:
    archive = Path(f"{source}_to_{target}_{int(datetime.utcnow().timestamp())}.tar.gz")
    with tarfile.open(archive, "w:gz") as tar:
        for fp in files:
            tar.add(fp, arcname=fp.name)
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "source": source,
        "target": target,
        "archive": str(archive),
        "files": [str(f) for f in files],
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def list_transmissions() -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    out: List[Dict[str, str]] = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Avatar Heirloom Transmission")
    sub = ap.add_subparsers(dest="cmd")

    tr = sub.add_parser("transmit", help="Transmit heirlooms")
    tr.add_argument("source")
    tr.add_argument("target")
    tr.add_argument("files", nargs="+")
    tr.set_defaults(func=lambda a: print(json.dumps(transmit_heirlooms(a.source, a.target, [Path(f) for f in a.files]), indent=2)))

    ls = sub.add_parser("list", help="List transmissions")
    ls.set_defaults(func=lambda a: print(json.dumps(list_transmissions(), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
