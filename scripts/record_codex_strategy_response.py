"""Record one operator-collected Codex strategy response without overwriting."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sentientos.operator_codex_response_journal import record_operator_codex_response


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate_json_key:{key}")
        result[key] = value
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregistration", required=True)
    parser.add_argument("--packet-id", required=True)
    parser.add_argument("--response", required=True,
        help="one operator-recorded response JSON, including exact raw_output")
    parser.add_argument("--journal-dir", required=True,
        help="existing private directory; packet entries are create-once")
    args = parser.parse_args()
    preregistration = json.loads(Path(args.preregistration).read_text(encoding="utf-8"),
        object_pairs_hook=_unique_object)
    response = json.loads(Path(args.response).read_text(encoding="utf-8"),
        object_pairs_hook=_unique_object)
    envelope = record_operator_codex_response(journal_dir=args.journal_dir,
        preregistration=preregistration, packet_id=args.packet_id, response=response)
    print(json.dumps({"packet_id": args.packet_id,
        "response_digest": envelope["response_digest"],
        "preregistration_digest": envelope["preregistration_digest"],
        "provenance_posture": "operator_recorded_unverified_external_output"},
        sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
