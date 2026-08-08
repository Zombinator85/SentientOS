from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sentientos.discernment_synthesis import (DiscernmentCustody, compare_packets,
    contribution_from_mapping, synthesize_packet)


def _read(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict): raise ValueError("input must be a JSON object")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="discernment-packet")
    parser.add_argument("--custody", required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("synthesize"); create.add_argument("--input", required=True)
    inspect = sub.add_parser("inspect"); inspect.add_argument("--digest", required=True)
    compare = sub.add_parser("compare"); compare.add_argument("--earlier", required=True); compare.add_argument("--later", required=True)
    args = parser.parse_args(argv); custody = DiscernmentCustody(args.custody)
    if args.command == "synthesize":
        source = _read(args.input); source["contributions"] = [contribution_from_mapping(v) for v in source.get("contributions", [])]
        prior = custody.packets_for_subject(str(source["subject_id"])); source["prior_packet_digest"] = prior[-1]["packet_digest"] if prior else None
        packet = synthesize_packet(**source); custody.append(packet); output: Any = packet
    elif args.command == "inspect": output = custody.inspect(args.digest)
    else: output = compare_packets(custody.inspect(args.earlier), custody.inspect(args.later))
    print(json.dumps(output, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__": raise SystemExit(main())
