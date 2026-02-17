from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _bounded(value: float) -> float:
    return max(0.0, min(1.0, value))


def _infer_affect(payload: dict[str, Any]) -> dict[str, Any] | None:
    event_type = payload.get("event_type")
    if event_type not in {"perception.audio", "perception.vision"}:
        return None

    confidence = float(payload.get("confidence", 0.0) or 0.0)
    features = payload.get("features") if isinstance(payload.get("features"), dict) else {}

    if event_type == "perception.audio":
        energy = float(features.get("rms_energy", 0.0) or 0.0)
        speech_prob = float(features.get("speech_prob", 0.0) or 0.0)
        expressivity = _bounded((energy * 0.7) + (speech_prob * 0.3))
    else:
        motion = float(payload.get("motion_score", 0.0) or 0.0)
        gaze_conf = float(features.get("gaze_confidence", 0.0) or 0.0)
        expressivity = _bounded((motion * 0.7) + (gaze_conf * 0.3))

    return {
        "event_type": "affect.telemetry",
        "timestamp": _iso_now(),
        "mode": "expression_only",
        "bounded_influence": "phrasing_telemetry_only",
        "action_selection_influence": False,
        "source_event_type": event_type,
        "affect_confidence": _bounded(confidence * 0.8),
        "expression_intensity": expressivity,
        "provenance": {
            "derived_from": "perception",
            "consumer": "affect_inference_consumer",
            "consumer_version": "1",
        },
    }


def run(*, input_path: Path, output_path: Path) -> int:
    if os.getenv("ENABLE_AFFECT_INFERENCE") != "1":
        print(json.dumps({"enabled": False, "reason": "ENABLE_AFFECT_INFERENCE!=1"}, sort_keys=True))
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    emitted = 0
    with input_path.open("r", encoding="utf-8") as src, output_path.open("a", encoding="utf-8") as dst:
        for line in src:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            payload = event.get("payload") if isinstance(event, dict) else None
            if not isinstance(payload, dict):
                continue
            inferred = _infer_affect(payload)
            if inferred is None:
                continue
            dst.write(json.dumps(inferred, sort_keys=True) + "\n")
            emitted += 1
    print(json.dumps({"enabled": True, "emitted": emitted, "output": str(output_path)}, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Derive bounded affect telemetry from perception events")
    parser.add_argument("--input", default="glow/perception/perception_events.jsonl")
    parser.add_argument("--output", default="glow/perception/affect_telemetry.jsonl")
    args = parser.parse_args(argv)
    return run(input_path=Path(args.input), output_path=Path(args.output))


if __name__ == "__main__":
    raise SystemExit(main())
