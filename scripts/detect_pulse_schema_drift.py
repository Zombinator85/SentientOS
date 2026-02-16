from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from scripts.capture_pulse_schema_baseline import _extract_schema

SCHEMA_VERSION = 1
DEFAULT_BASELINE = Path("glow/pulse/baseline/pulse_schema_baseline.json")
DEFAULT_REPORT = Path("glow/pulse/pulse_schema_drift_report.json")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _fingerprint(schema: dict[str, Any]) -> str:
    canonical = json.dumps(schema, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def detect_drift(*, baseline_path: Path, output_path: Path) -> dict[str, Any]:
    baseline = _read_json(baseline_path)
    baseline_schema = baseline.get("schema", {}) if isinstance(baseline.get("schema"), dict) else {}
    current_schema = _extract_schema()

    baseline_events = {
        (stream, event): payload
        for stream, stream_payload in baseline_schema.items()
        if isinstance(stream_payload, dict)
        for event, payload in (stream_payload.get("events", {}) or {}).items()
        if isinstance(payload, dict)
    }
    current_events = {
        (stream, event): payload
        for stream, stream_payload in current_schema.items()
        if isinstance(stream_payload, dict)
        for event, payload in (stream_payload.get("events", {}) or {}).items()
        if isinstance(payload, dict)
    }

    added_event_types = sorted([{"stream": s, "event_type": e} for (s, e) in (set(current_events) - set(baseline_events))])
    removed_event_types = sorted([{"stream": s, "event_type": e} for (s, e) in (set(baseline_events) - set(current_events))])

    added_fields: list[dict[str, str]] = []
    removed_fields: list[dict[str, str]] = []
    type_changes: list[dict[str, str]] = []
    for key in sorted(set(current_events) & set(baseline_events)):
        stream, event = key
        base_fields = set((baseline_events[key].get("allowed_fields") or []))
        curr_fields = set((current_events[key].get("allowed_fields") or []))
        for field in sorted(curr_fields - base_fields):
            added_fields.append({"stream": stream, "event_type": event, "field": field})
        for field in sorted(base_fields - curr_fields):
            removed_fields.append({"stream": stream, "event_type": event, "field": field})

        base_types = baseline_events[key].get("field_types", {}) or {}
        curr_types = current_events[key].get("field_types", {}) or {}
        for field in sorted(set(base_types) & set(curr_types)):
            if base_types[field] != curr_types[field]:
                type_changes.append(
                    {
                        "stream": stream,
                        "event_type": event,
                        "field": field,
                        "from": str(base_types[field]),
                        "to": str(curr_types[field]),
                    }
                )

    baseline_fingerprint = str(baseline.get("schema_fingerprint", ""))
    current_fingerprint = _fingerprint(current_schema)
    fingerprint_changed = baseline_fingerprint != current_fingerprint
    schema_diff_detected = bool(added_event_types or removed_event_types or added_fields or removed_fields or type_changes)

    if schema_diff_detected and fingerprint_changed:
        drift_type = "schema_and_fingerprint"
        explanation = "Pulse schema structure and fingerprint changed."
    elif schema_diff_detected:
        drift_type = "schema_only"
        explanation = "Pulse schema structure changed with stable fingerprint."
    elif fingerprint_changed:
        drift_type = "fingerprint_only"
        explanation = "Pulse schema fingerprint changed without structural diff."
    else:
        drift_type = "none"
        explanation = "No Pulse schema drift detected."

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "drifted": bool(schema_diff_detected or fingerprint_changed),
        "drift_type": drift_type,
        "explanation": explanation,
        "baseline_fingerprint": baseline_fingerprint,
        "current_fingerprint": current_fingerprint,
        "fingerprint_changed": fingerprint_changed,
        "schema_diff_detected": schema_diff_detected,
        "tuple_diff_detected": schema_diff_detected,
        "added_event_types": added_event_types,
        "removed_event_types": removed_event_types,
        "added_fields": added_fields,
        "removed_fields": removed_fields,
        "type_changes": type_changes,
        "notes": [f"baseline={baseline_path.as_posix()}"],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect Pulse schema drift")
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE), help="baseline path")
    parser.add_argument("--output", default=str(DEFAULT_REPORT), help="output report path")
    args = parser.parse_args(argv)

    report = detect_drift(baseline_path=Path(args.baseline), output_path=Path(args.output))
    print(json.dumps({"tool": "detect_pulse_schema_drift", "drifted": report["drifted"], "drift_type": report["drift_type"]}, sort_keys=True))

    if os.getenv("SENTIENTOS_CI_FAIL_ON_PULSE_DRIFT") == "1" and report["drift_type"] != "none":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
