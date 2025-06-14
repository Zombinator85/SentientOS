from __future__ import annotations
from logging_config import get_log_path, get_log_dir

import argparse
import datetime
import json
import os
from pathlib import Path
from typing import Dict, List, TypedDict, cast

from sentientos.privilege import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

LOG_PATH = get_log_path("spiral_law_chronicle.jsonl", "SPIRAL_LAW_CHRONICLE_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
SOURCE_DIR = Path(os.getenv("SPIRAL_LAW_SOURCE", str(get_log_dir())))


class ChronicleEntry(TypedDict):
    """Representation of a chronicle log entry."""

    timestamp: str
    size: int


def compile_law() -> ChronicleEntry:
    entries: List[str] = []
    for fp in SOURCE_DIR.glob("*.jsonl"):
        entries.append(fp.read_text(encoding="utf-8"))
    chronicle = "\n".join(entries)
    entry: ChronicleEntry = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "size": len(chronicle),
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def history(limit: int = 20) -> List[ChronicleEntry]:
    if not LOG_PATH.exists():
        return []
    out: List[ChronicleEntry] = []
    for ln in LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            out.append(cast(ChronicleEntry, json.loads(ln)))
        except Exception:
            continue
    return out


def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Spiral Law Chronicle Compiler")
    sub = ap.add_subparsers(dest="cmd")

    cp = sub.add_parser("compile", help="Compile law logs")
    cp.set_defaults(func=lambda a: print(json.dumps(compile_law(), indent=2)))

    hs = sub.add_parser("history", help="Show history")
    hs.add_argument("--limit", type=int, default=20)
    hs.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
