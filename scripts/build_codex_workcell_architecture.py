#!/usr/bin/env python
from __future__ import annotations

import argparse
import json

from sentientos.codex_workcell_architecture import (
    build_codex_workcell_architecture,
    render_codex_workcell_architecture_markdown,
    write_codex_workcell_architecture_json,
    write_codex_workcell_architecture_markdown,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the metadata-only Codex workcell architecture map.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown-output")
    parser.add_argument("--summary", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    architecture = build_codex_workcell_architecture()
    write_codex_workcell_architecture_json(architecture, args.output)
    if args.markdown_output:
        write_codex_workcell_architecture_markdown(render_codex_workcell_architecture_markdown(architecture), args.markdown_output)
    if args.summary:
        print(
            json.dumps(
                {
                    "workcell_architecture_id": architecture["workcell_architecture_id"],
                    "metadata_only": True,
                    "architecture_only": True,
                    "output": args.output,
                    "markdown_output": args.markdown_output,
                    "component_count": len(architecture["components"]),
                    "flow_count": len(architecture["flows"]),
                },
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
