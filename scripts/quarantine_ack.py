from __future__ import annotations

import argparse
import json
from pathlib import Path

from sentientos.event_stream import record_forge_event
from sentientos.integrity_quarantine import QuarantineStateError, acknowledge


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Acknowledge integrity quarantine.")
    parser.add_argument("--note", default="acknowledged", help="Operator note")
    args = parser.parse_args(argv)

    root = Path.cwd().resolve()
    try:
        state = acknowledge(root, args.note)
    except QuarantineStateError as exc:
        print(json.dumps({
            "status": "blocked",
            "failure": "quarantine_custody_invalid",
            "quarantine_active": None,
            "quarantine_custody_status": "invalid:" + exc.code,
        }, indent=2, sort_keys=True))
        return 1
    record_forge_event({"event": "integrity_quarantine_acknowledged", "level": "warning", "note": args.note, "active": state.active})
    print(json.dumps({"status": "ok", "quarantine": state.to_dict()}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
