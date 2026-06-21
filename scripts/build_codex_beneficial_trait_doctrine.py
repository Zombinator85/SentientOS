#!/usr/bin/env python
from __future__ import annotations

import argparse
import json

from sentientos.codex_beneficial_trait_doctrine import (
    build_beneficial_trait_doctrine_map,
    render_beneficial_trait_doctrine_markdown,
    write_beneficial_trait_doctrine_json,
    write_beneficial_trait_doctrine_markdown,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the metadata-only Codex beneficial trait doctrine map.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown-output")
    parser.add_argument("--summary", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    doctrine_map = build_beneficial_trait_doctrine_map()
    write_beneficial_trait_doctrine_json(doctrine_map, args.output)
    if args.markdown_output:
        write_beneficial_trait_doctrine_markdown(render_beneficial_trait_doctrine_markdown(doctrine_map), args.markdown_output)
    if args.summary:
        print(
            json.dumps(
                {
                    "doctrine_map_id": doctrine_map["doctrine_map_id"],
                    "metadata_only": True,
                    "output": args.output,
                    "markdown_output": args.markdown_output,
                    "rail_mapping_count": len(doctrine_map["rail_mappings"]),
                    "trait_count": len(doctrine_map["trait_catalog"]),
                },
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
