from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
from logging_config import get_log_path

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

"""Compile lorebook entries from Neos activity logs.

The permission council log is read from ``logs/neos_permission_council.jsonl``
or the path provided by ``NEOS_PERMISSION_COUNCIL_LOG``. See
``docs/ENVIRONMENT.md`` for details.
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

ORIGIN_LOG = get_log_path("neos_origin_stories.jsonl", "NEOS_ORIGIN_LOG")
CEREMONY_LOG = get_log_path("avatar_ceremony_log.jsonl", "AVATAR_CEREMONY_LOG")
TEACHING_LOG = get_log_path("neos_teach_content.jsonl", "NEOS_TEACH_CONTENT_LOG")
COUNCIL_LOG = get_log_path("neos_permission_council.jsonl", "NEOS_PERMISSION_COUNCIL_LOG")

LOREBOOK_LOG = get_log_path("neos_lorebook.jsonl", "NEOS_LOREBOOK_LOG")
LOREBOOK_LOG.parent.mkdir(parents=True, exist_ok=True)


def _load(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def compile_entries() -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for e in _load(ORIGIN_LOG):
        e["source"] = "origin"
        entries.append(e)
    for e in _load(CEREMONY_LOG):
        e["source"] = "ceremony"
        entries.append(e)
    for e in _load(TEACHING_LOG):
        e["source"] = "teaching"
        entries.append(e)
    for e in _load(COUNCIL_LOG):
        e["source"] = "council"
        entries.append(e)
    entries.sort(key=lambda x: x.get("timestamp", ""))
    return entries


def log_generation(count: int, out: str) -> None:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "count": count,
        "out": out,
    }
    with LOREBOOK_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def run_compile(path: Path) -> Path:
    entries = compile_entries()
    path.write_text(json.dumps(entries, indent=2))
    log_generation(len(entries), str(path))
    return path


def export_markdown(entries: List[Dict[str, Any]]) -> str:
    blocks = []
    for e in entries:
        src = e.get("source", "")
        ts = e.get("timestamp", "")
        block = (
            f"### {src.capitalize()} - {ts}\n" +
            "```\n" +
            json.dumps(e, indent=2) +
            "\n```"
        )
        blocks.append(block)
    return "\n\n".join(blocks)


def main() -> None:
    ap = argparse.ArgumentParser(description="NeosVR Autonomous Lorebook Writer")
    sub = ap.add_subparsers(dest="cmd")

    cp = sub.add_parser("compile", help="Compile lorebook to path")
    cp.add_argument("out")
    cp.set_defaults(func=lambda a: print(run_compile(Path(a.out))))

    gl = sub.add_parser("gallery", help="Show compiled entries")
    gl.set_defaults(func=lambda a: print(json.dumps(compile_entries(), indent=2)))

    ex = sub.add_parser("export", help="Export lorebook as markdown")
    ex.set_defaults(func=lambda a: print(export_markdown(compile_entries())))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
