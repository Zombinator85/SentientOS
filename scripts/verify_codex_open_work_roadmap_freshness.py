from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sentientos.codex_open_work_roadmap_freshness_verifier import (
    DEFAULT_ROADMAP_PATH,
    VERIFIED,
    dumps_report,
    render_markdown,
    verify_roadmap_file,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify current Codex open-work roadmap freshness metadata.")
    parser.add_argument("--roadmap-path", type=Path, default=DEFAULT_ROADMAP_PATH)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)

    try:
        report = verify_roadmap_file(args.roadmap_path)
        if args.output:
            _write(args.output, dumps_report(report))
        if args.markdown_output:
            _write(args.markdown_output, render_markdown(report))
    except (OSError, UnicodeDecodeError, ValueError, TypeError) as exc:
        print(json.dumps({"status": "input_output_error", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2

    if args.summary:
        print(json.dumps({
            "verification_status": report["verification_status"],
            "violation_count": report["violation_summary"]["violation_count"],
            "roadmap_path": report["roadmap_path"],
        }, sort_keys=True))
    return 0 if report["verification_status"] == VERIFIED else 1


if __name__ == "__main__":
    raise SystemExit(main())
