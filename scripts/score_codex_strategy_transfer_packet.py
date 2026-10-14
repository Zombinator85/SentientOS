"""Score separately recorded external strategy proposals with the canonical evaluator."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sentientos.embodied_consequence import canonical_bytes, score_operator_codex_strategy_responses


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate_json_key:{key}")
        result[key] = value
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scorer-manifest", required=True)
    parser.add_argument("--preregistration", required=True)
    parser.add_argument("--subject-packets", required=True)
    parser.add_argument("--responses", required=True,
        help="JSON mapping opaque packet IDs to exact raw output and session/settings fields")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    manifest = json.loads(Path(args.scorer_manifest).read_text(encoding="utf-8"),
        object_pairs_hook=_unique_object)
    preregistration = json.loads(Path(args.preregistration).read_text(encoding="utf-8"),
        object_pairs_hook=_unique_object)
    responses = json.loads(Path(args.responses).read_text(encoding="utf-8"),
        object_pairs_hook=_unique_object)
    packet_dir = Path(args.subject_packets)
    packets = {path.stem: json.loads(path.read_text(encoding="utf-8"),
        object_pairs_hook=_unique_object) for path in packet_dir.glob("*.json")}
    scores = score_operator_codex_strategy_responses(scorer_manifest=manifest,
        preregistration=preregistration, subject_packets=packets, responses=responses)
    Path(args.output).write_bytes(canonical_bytes(scores) + b"\n")
    print(json.dumps({"score_digest": scores["score_digest"],
        "strategy_scoring_status": scores["strategy_scoring"]["status"],
        "output": args.output}, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
