from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from scripts.capture_perception_schema_baseline import _schema

SCHEMA_VERSION = 1
DEFAULT_BASELINE = Path("glow/perception/baseline/perception_schema_baseline.json")
DEFAULT_REPORT = Path("glow/perception/perception_schema_drift_report.json")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _fingerprint(schema: dict[str, Any]) -> str:
    canonical = json.dumps(schema, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def detect_drift(*, baseline_path: Path, output_path: Path) -> dict[str, Any]:
    baseline = _read_json(baseline_path)
    baseline_schema = baseline.get("schema", {}) if isinstance(baseline.get("schema"), dict) else {}
    current_schema = _schema()

    baseline_events = baseline_schema.get("events", {}) if isinstance(baseline_schema.get("events"), dict) else {}
    current_events = current_schema.get("events", {}) if isinstance(current_schema.get("events"), dict) else {}

    added_event_types = sorted(set(current_events) - set(baseline_events))
    removed_event_types = sorted(set(baseline_events) - set(current_events))

    added_fields: list[dict[str, str]] = []
    removed_fields: list[dict[str, str]] = []
    type_changes: list[dict[str, str]] = []
    enum_changes: list[dict[str, str]] = []
    required_key_changes: list[dict[str, str]] = []

    for event_type in sorted(set(current_events) & set(baseline_events)):
        base_event = baseline_events[event_type]
        curr_event = current_events[event_type]
        if not isinstance(base_event, dict) or not isinstance(curr_event, dict):
            continue

        base_fields = set(base_event.get("allowed_fields", []) or [])
        curr_fields = set(curr_event.get("allowed_fields", []) or [])

        for field in sorted(curr_fields - base_fields):
            added_fields.append({"event_type": event_type, "field": field})
        for field in sorted(base_fields - curr_fields):
            removed_fields.append({"event_type": event_type, "field": field})

        base_types = base_event.get("field_types", {}) or {}
        curr_types = curr_event.get("field_types", {}) or {}
        for field in sorted(set(base_types) & set(curr_types)):
            if base_types[field] != curr_types[field]:
                type_changes.append({"event_type": event_type, "field": field, "from": str(base_types[field]), "to": str(curr_types[field])})

        base_enums = base_event.get("field_enums", {}) or {}
        curr_enums = curr_event.get("field_enums", {}) or {}
        for field in sorted(set(base_enums) | set(curr_enums)):
            if base_enums.get(field) != curr_enums.get(field):
                enum_changes.append({"event_type": event_type, "field": field, "from": json.dumps(base_enums.get(field), sort_keys=True), "to": json.dumps(curr_enums.get(field), sort_keys=True)})

        base_required = set(base_event.get("required_fields", []) or [])
        curr_required = set(curr_event.get("required_fields", []) or [])
        for field in sorted(curr_required - base_required):
            required_key_changes.append({"event_type": event_type, "field": field, "change": "added_required"})
        for field in sorted(base_required - curr_required):
            required_key_changes.append({"event_type": event_type, "field": field, "change": "removed_required"})

    baseline_fingerprint = str(baseline.get("schema_fingerprint", ""))
    current_fingerprint = _fingerprint(current_schema)
    fingerprint_changed = baseline_fingerprint != current_fingerprint
    schema_diff_detected = bool(added_event_types or removed_event_types or added_fields or removed_fields or type_changes or enum_changes or required_key_changes)

    if schema_diff_detected and fingerprint_changed:
        drift_type = "schema_and_fingerprint"
        explanation = "Perception schema and fingerprint changed."
    elif schema_diff_detected:
        drift_type = "schema_only"
        explanation = "Perception schema changed with stable fingerprint."
    elif fingerprint_changed:
        drift_type = "fingerprint_only"
        explanation = "Perception schema fingerprint changed without structural diff."
    else:
        drift_type = "none"
        explanation = "No perception schema drift detected."

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
        "enum_changes": enum_changes,
        "required_key_changes": required_key_changes,
        "notes": [f"baseline={baseline_path.as_posix()}"],
        "provenance": baseline.get("provenance", {}),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect Perception schema drift")
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE), help="baseline path")
    parser.add_argument("--output", default=str(DEFAULT_REPORT), help="output report path")
    args = parser.parse_args(argv)

    report = detect_drift(baseline_path=Path(args.baseline), output_path=Path(args.output))
    print(json.dumps({"tool": "detect_perception_schema_drift", "drifted": report["drifted"], "drift_type": report["drift_type"]}, sort_keys=True))
    if os.getenv("SENTIENTOS_CI_FAIL_ON_PERCEPTION_SCHEMA_DRIFT") == "1" and report["drift_type"] != "none":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
