"""Score separately recorded Codex packet responses against the sealed key."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sentientos.codex_transfer_packet import packet_json_bytes, score_codex_transfer_responses


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
    parser.add_argument("--subject-packets", required=True,
        help="Directory containing the five original subject packet JSON files")
    parser.add_argument("--responses", required=True,
        help="JSON mapping packet IDs to raw_output and session/model-setting records")
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
        object_pairs_hook=_unique_object)
        for path in packet_dir.glob("*.json")}
    scores = score_codex_transfer_responses(scorer_manifest=manifest,
        preregistration=preregistration, subject_packets=packets, responses=responses)
    Path(args.output).write_bytes(packet_json_bytes(scores))
    print(json.dumps({"score_digest": scores["score_digest"],
        "conditions_scored": len(scores["conditions"]), "output": args.output},
        sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
