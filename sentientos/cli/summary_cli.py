from __future__ import annotations

import argparse
from typing import Sequence

from sentientos.narrative_synthesis import build_narrative_summary, parse_since
from sentientos.ois import serialize_output


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sentientos summary",
        description="Read-only narrative summary (system activity and authority changes).",
    )
    parser.add_argument(
        "--since",
        dest="since",
        default=None,
        help="ISO timestamp or relative window (e.g. 'yesterday', 'last week').",
    )
    parser.add_argument("--from", dest="source_from", default=None, help="Snapshot source (default: diff log).")
    parser.add_argument("--to", dest="source_to", default=None, help="Snapshot source (default: diff log).")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    since = parse_since(args.since)
    output = build_narrative_summary(since=since, source_from=args.source_from, source_to=args.source_to)
    print(serialize_output(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
