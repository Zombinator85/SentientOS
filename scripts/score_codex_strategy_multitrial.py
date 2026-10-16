"""Score each preregistered strategy situation and report descriptive totals."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sentientos.codex_strategy_multitrial import score_operator_codex_strategy_multitrial
from sentientos.embodied_consequence import canonical_bytes
from sentientos.operator_codex_response_journal import recover_operator_codex_responses


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
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--responses")
    group.add_argument("--response-journal")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    manifest = json.loads(Path(args.scorer_manifest).read_text(encoding="utf-8"),
        object_pairs_hook=_unique_object)
    preregistration = json.loads(Path(args.preregistration).read_text(encoding="utf-8"),
        object_pairs_hook=_unique_object)
    if args.response_journal:
        responses, recovery = recover_operator_codex_responses(
            journal_dir=args.response_journal, preregistration=preregistration)
    else:
        responses = json.loads(Path(args.responses).read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object)
        recovery = None
    packet_dir = Path(args.subject_packets)
    packets = {path.stem: json.loads(path.read_text(encoding="utf-8"),
        object_pairs_hook=_unique_object) for path in packet_dir.glob("*.json")}
    result = score_operator_codex_strategy_multitrial(scorer_manifest=manifest,
        preregistration=preregistration, subject_packets=packets, responses=responses)
    Path(args.output).write_bytes(canonical_bytes(result) + b"\n")
    print(json.dumps({"score_digest": result["score_digest"], "status": result["status"],
        "scoreable_task_fraction": result["scoreable_task_fraction"],
        "response_journal_recovery": recovery, "output": args.output},
        sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
