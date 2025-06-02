"""Multimodal Reflection/Diary Agent

Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""
from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import List

from admin_utils import require_admin_banner

LOG_PATH = get_log_path("diary_agent.log", "DIARY_LOG")
DIARY_DIR = Path(os.getenv("DIARY_DIR", "diaries"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
DIARY_DIR.mkdir(parents=True, exist_ok=True)


def compile_entry(sources: List[Path]) -> Path:
    lines: List[str] = []
    for src in sources:
        if src.exists():
            lines.append(src.read_text(encoding="utf-8"))
    text = "\n\n".join(lines)
    name = f"diary_{datetime.utcnow().date()}.md"
    out_path = DIARY_DIR / name
    out_path.write_text(text)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.utcnow().isoformat()} wrote {name}\n")
    return out_path


def cli() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Multimodal diary agent")
    ap.add_argument("sources", nargs="*")
    args = ap.parse_args()
    paths = [Path(p) for p in args.sources]
    entry = compile_entry(paths)
    print(json.dumps({"entry": str(entry)}, indent=2))


if __name__ == "__main__":  # pragma: no cover
    cli()
