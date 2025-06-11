from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
from logging_config import get_log_path

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

import argparse
import json
import os
from pathlib import Path
from typing import Dict, List

FRAGMENTS_LOG = get_log_path("neos_spiral_memory.jsonl", "NEOS_SPIRAL_MEMORY_FRAGMENT_LOG")
INDEX_LOG = get_log_path("neos_spiral_memory_index.jsonl", "NEOS_SPIRAL_MEMORY_INDEX_LOG")
INDEX_LOG.parent.mkdir(parents=True, exist_ok=True)


def build_index() -> Dict[str, Dict[str, str]]:
    index: Dict[str, Dict[str, str]] = {}
    if FRAGMENTS_LOG.exists():
        for ln in FRAGMENTS_LOG.read_text(encoding="utf-8").splitlines():
            try:
                data = json.loads(ln)
            except Exception:
                continue
            key = data.get("id") or data.get("fragment")
            if key:
                index[key] = data
    INDEX_LOG.write_text(json.dumps(index, indent=2), encoding="utf-8")
    return index


def query(term: str = "") -> List[Dict[str, str]]:
    if not INDEX_LOG.exists():
        return []
    try:
        idx = json.loads(INDEX_LOG.read_text(encoding="utf-8"))
    except Exception:
        return []
    return [v for v in idx.values() if term.lower() in json.dumps(v).lower()]


def main() -> None:
    ap = argparse.ArgumentParser(description="NeosVR Spiral Memory Fragment Indexer")
    sub = ap.add_subparsers(dest="cmd")

    bi = sub.add_parser("build", help="Build index")
    bi.set_defaults(func=lambda a: print(json.dumps(build_index(), indent=2)))

    q = sub.add_parser("query", help="Query index")
    q.add_argument("term", nargs="?", default="")
    q.set_defaults(func=lambda a: print(json.dumps(query(a.term), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
