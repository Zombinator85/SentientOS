from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from sentientos.household_presence_camera_event_bridge import (
    HouseholdCameraEventBridgePolicy,
    bridge_event,
    dumps_bridge_result,
)


def _load_json(path: str | None) -> dict[str, object]:
    if not path:
        return {}
    loaded = json.loads(Path(path).read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=("build-default", "normalize-event", "validate", "summarize"))
    p.add_argument("--input")
    p.add_argument("--output")
    p.add_argument("--summary", action="store_true")
    a = p.parse_args(argv)

    if a.command == "build-default":
        payload = dumps_bridge_result(bridge_event({"event_id": "default", "event_type": "generic_perception_event", "zone": "exterior_security_zone", "entity_class": "unknown", "modality": "camera", "confidence": 0.5}, HouseholdCameraEventBridgePolicy()))
    else:
        event = _load_json(a.input)
        result = bridge_event(event, HouseholdCameraEventBridgePolicy())
        if a.command == "validate":
            print("bridge_valid" if result.status in {"bridge_ready", "bridge_ready_with_warnings", "bridge_manual_review_required"} else "bridge_invalid")
            return 0 if result.status != "bridge_failed" else 2
        if a.command == "summarize":
            print(f"status={result.status} decision={result.decision.decision} warnings={len(result.decision.warnings)}")
            return 0
        payload = dumps_bridge_result(result)

    if a.output:
        Path(a.output).write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
