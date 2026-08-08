from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sentientos.discernment_outcome_review import (OutcomeReviewCustody, create_commitment,
    create_longitudinal_report, create_outcome_evidence, create_review)


def _load(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict): raise ValueError("JSON input must be an object")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Append-only prospective discernment outcome review")
    parser.add_argument("--root", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    commit = commands.add_parser("commit"); commit.add_argument("--packet", required=True); commit.add_argument("--request", required=True)
    outcome = commands.add_parser("record-outcome"); outcome.add_argument("--commitment", required=True); outcome.add_argument("--request", required=True)
    review = commands.add_parser("review"); review.add_argument("--commitment", required=True); review.add_argument("--outcome", required=True); review.add_argument("--source-packet"); review.add_argument("--later-packet")
    longitudinal = commands.add_parser("longitudinal"); longitudinal.add_argument("--reviews", nargs="+", required=True); longitudinal.add_argument("--generated-at", required=True)
    inspect = commands.add_parser("inspect"); inspect.add_argument("digest")
    args = parser.parse_args(argv); custody = OutcomeReviewCustody(args.root)
    if args.command == "commit": artifact = create_commitment(_load(args.packet), **_load(args.request)); custody.append(artifact)
    elif args.command == "record-outcome": artifact = create_outcome_evidence(_load(args.commitment), **_load(args.request)); custody.append(artifact)
    elif args.command == "review": artifact = create_review(_load(args.commitment), _load(args.outcome), source_packet=_load(args.source_packet) if args.source_packet else None, later_packet=_load(args.later_packet) if args.later_packet else None); custody.append(artifact)
    elif args.command == "longitudinal": artifact = create_longitudinal_report([_load(path) for path in args.reviews], generated_at=args.generated_at)
    else: artifact = custody.inspect(args.digest)
    print(json.dumps(artifact, sort_keys=True, separators=(",", ":"), ensure_ascii=False)); return 0


if __name__ == "__main__": raise SystemExit(main())
