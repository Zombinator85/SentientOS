"""Score separately recorded Codex packet responses against the sealed key."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sentientos.codex_transfer_packet import packet_json_bytes, score_codex_transfer_responses


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scorer-manifest", required=True)
    parser.add_argument("--responses", required=True,
        help="JSON mapping packet IDs to raw_output and session/model-setting records")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    manifest = json.loads(Path(args.scorer_manifest).read_text(encoding="utf-8"))
    responses = json.loads(Path(args.responses).read_text(encoding="utf-8"))
    scores = score_codex_transfer_responses(scorer_manifest=manifest, responses=responses)
    Path(args.output).write_bytes(packet_json_bytes(scores))
    print(json.dumps({"score_digest": scores["score_digest"],
        "conditions_scored": len(scores["conditions"]), "output": args.output},
        sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
