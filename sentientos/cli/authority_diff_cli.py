from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from sentientos.authority_surface import build_authority_surface_snapshot
from sentientos.ois import build_authority_surface_diff


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sentientos diff",
        description="Deterministic authority surface diffing.",
    )
    parser.add_argument(
        "--from",
        dest="source_from",
        default=None,
        help="Snapshot source (runtime, snapshot:path, config:path, git:ref[:path]).",
    )
    parser.add_argument(
        "--to",
        dest="source_to",
        default=None,
        help="Snapshot source (runtime, snapshot:path, config:path, git:ref[:path]).",
    )
    parser.add_argument(
        "--write-snapshot",
        dest="snapshot_path",
        help="Write the current authority surface snapshot to a path and exit.",
    )
    return parser


def _write_snapshot(path: Path) -> None:
    snapshot = build_authority_surface_snapshot()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.snapshot_path:
        _write_snapshot(Path(args.snapshot_path))
        return 0

    source_from = args.source_from
    source_to = args.source_to

    if source_from is None and source_to is None:
        output = build_authority_surface_diff()
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0

    if source_from is None:
        source_from = "runtime"

    output = build_authority_surface_diff(source_from=source_from, source_to=source_to)
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
