from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from scripts.capture_self_model_baseline import _schema

SCHEMA_VERSION = 1
DEFAULT_BASELINE = Path("glow/self/baseline/self_model_baseline.json")
DEFAULT_REPORT = Path("glow/self/self_model_drift_report.json")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _fingerprint(schema: dict[str, Any]) -> str:
    canonical = json.dumps(schema, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def detect_drift(*, baseline_path: Path, output_path: Path) -> dict[str, Any]:
    baseline = _read_json(baseline_path)
    baseline_schema = baseline.get("self_model_schema", {}) if isinstance(baseline.get("self_model_schema"), dict) else {}
    current_schema = _schema()

    baseline_keys = set(baseline_schema.get("required_keys", []) or [])
    current_keys = set(current_schema.get("required_keys", []) or [])
    added_keys = sorted(current_keys - baseline_keys)
    removed_keys = sorted(baseline_keys - current_keys)

    key_type_changes: list[dict[str, str]] = []
    baseline_types = baseline_schema.get("key_types", {}) or {}
    current_types = current_schema.get("key_types", {}) or {}
    for key in sorted(set(baseline_types) & set(current_types)):
        if baseline_types[key] != current_types[key]:
            key_type_changes.append({"key": key, "from": str(baseline_types[key]), "to": str(current_types[key])})

    baseline_write_back = set(baseline_schema.get("allowed_write_back_fields", []) or [])
    current_write_back = set(current_schema.get("allowed_write_back_fields", []) or [])
    write_back_added = sorted(current_write_back - baseline_write_back)
    write_back_removed = sorted(baseline_write_back - current_write_back)

    baseline_fingerprint = str(baseline.get("schema_fingerprint", ""))
    current_fingerprint = _fingerprint(current_schema)
    fingerprint_changed = baseline_fingerprint != current_fingerprint
    schema_diff_detected = bool(added_keys or removed_keys or key_type_changes or write_back_added or write_back_removed)

    if schema_diff_detected and fingerprint_changed:
        drift_type = "schema_and_fingerprint"
        explanation = "Self-model schema and fingerprint changed."
    elif schema_diff_detected:
        drift_type = "schema_only"
        explanation = "Self-model schema changed with stable fingerprint."
    elif fingerprint_changed:
        drift_type = "fingerprint_only"
        explanation = "Self-model fingerprint changed without schema tuple deltas."
    else:
        drift_type = "none"
        explanation = "No self-model drift detected."

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "drifted": bool(schema_diff_detected or fingerprint_changed),
        "drift_type": drift_type,
        "explanation": explanation,
        "fingerprint_changed": fingerprint_changed,
        "tuple_diff_detected": schema_diff_detected,
        "schema_diff_detected": schema_diff_detected,
        "baseline_fingerprint": baseline_fingerprint,
        "current_fingerprint": current_fingerprint,
        "added_required_keys": added_keys,
        "removed_required_keys": removed_keys,
        "key_type_changes": key_type_changes,
        "write_back_added": write_back_added,
        "write_back_removed": write_back_removed,
        "notes": [f"baseline={baseline_path.as_posix()}"],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect self-model schema drift")
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE), help="baseline path")
    parser.add_argument("--output", default=str(DEFAULT_REPORT), help="output report path")
    args = parser.parse_args(argv)

    report = detect_drift(baseline_path=Path(args.baseline), output_path=Path(args.output))
    print(json.dumps({"tool": "detect_self_model_drift", "drifted": report["drifted"], "drift_type": report["drift_type"]}, sort_keys=True))
    if os.getenv("SENTIENTOS_CI_FAIL_ON_SELF_MODEL_DRIFT") == "1" and report["drift_type"] != "none":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
