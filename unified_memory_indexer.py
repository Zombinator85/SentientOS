"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
"""Unified Memory/Knowledge Indexer

"""
from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict


LOG_PATH = get_log_path("memory_index.log", "MEMORY_INDEX_LOG")
INDEX_PATH = get_log_path("memory_index.json", "MEMORY_INDEX")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def build_index(root: Path) -> List[Dict[str, str]]:
    index: List[Dict[str, str]] = []
    for path in root.rglob("*.jsonl"):
        index.append({"path": str(path), "name": path.name})
    INDEX_PATH.write_text(json.dumps(index, indent=2))
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.utcnow().isoformat()} built index\n")
    return index


def query(term: str) -> List[str]:
    if not INDEX_PATH.exists():
        return []
    idx = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    return [it["path"] for it in idx if term.lower() in it["name"].lower()]


def cli() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Memory indexer")
    ap.add_argument("root")
    ap.add_argument("--query")
    args = ap.parse_args()
    root_path = Path(args.root)
    if args.query:
        print(json.dumps(query(args.query), indent=2))
    else:
        print(json.dumps(build_index(root_path), indent=2))


if __name__ == "__main__":  # pragma: no cover
    cli()
