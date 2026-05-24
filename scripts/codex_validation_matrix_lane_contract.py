from __future__ import annotations

import argparse
import json
from pathlib import Path

from sentientos.codex_validation_matrix_lane_contract import LANE_CONTRACT, summarize_lane_contract, verify_lane_contract


def _read(path: str) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list")
    verify = sub.add_parser("verify")
    verify.add_argument("--matrix-json-path", required=True)
    verify.add_argument("--fail-on-unknown-lanes", action="store_true")

    summary = sub.add_parser("summary")
    summary.add_argument("--matrix-json-path", required=True)

    args = p.parse_args(argv)
    if args.cmd == "list":
        print(json.dumps([lane.__dict__ for lane in LANE_CONTRACT], indent=2, sort_keys=True))
        return 0
    if args.cmd == "verify":
        out = verify_lane_contract(_read(args.matrix_json_path), fail_on_unknown_lanes=args.fail_on_unknown_lanes)
        print(json.dumps(out.to_dict(), indent=2, sort_keys=True))
        return 0 if out.status.endswith("ready") else 1

    print(json.dumps(summarize_lane_contract(_read(args.matrix_json_path)), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
