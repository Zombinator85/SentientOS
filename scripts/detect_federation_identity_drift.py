from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from scripts.capture_federation_identity_baseline import _identity_components

SCHEMA_VERSION = 1
DEFAULT_BASELINE = Path("glow/federation/baseline/federation_identity_baseline.json")
DEFAULT_REPORT = Path("glow/federation/federation_identity_drift_report.json")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _fingerprint(value: object) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def detect_drift(*, baseline_path: Path, output_path: Path) -> dict[str, Any]:
    baseline = _read_json(baseline_path)
    baseline_components = baseline.get("identity_components", {}) if isinstance(baseline.get("identity_components"), dict) else {}
    current_components = _identity_components()

    changed_components: list[dict[str, str]] = []
    keys = sorted(set(baseline_components) | set(current_components))
    for key in keys:
        before = str(baseline_components.get(key, ""))
        after = str(current_components.get(key, ""))
        if before != after:
            changed_components.append({"component": key, "before": before, "after": after})

    baseline_digest = str(baseline.get("identity_digest", ""))
    current_digest = _fingerprint(current_components)
    fingerprint_changed = baseline_digest != current_digest
    tuple_diff_detected = bool(changed_components)

    if tuple_diff_detected and fingerprint_changed:
        drift_type = "tuple_and_fingerprint"
        explanation = "Federation identity components and digest changed."
    elif tuple_diff_detected:
        drift_type = "tuple_only"
        explanation = "Federation identity component tuple changed with stable digest."
    elif fingerprint_changed:
        drift_type = "fingerprint_only"
        explanation = "Federation identity digest changed without component tuple differences."
    else:
        drift_type = "none"
        explanation = "No federation identity drift detected."

    report = {
        "schema_version": SCHEMA_VERSION,
        "drifted": bool(tuple_diff_detected or fingerprint_changed),
        "drift_type": drift_type,
        "explanation": explanation,
        "fingerprint_changed": fingerprint_changed,
        "tuple_diff_detected": tuple_diff_detected,
        "baseline_fingerprint": baseline_digest,
        "current_fingerprint": current_digest,
        "changed_components": changed_components,
        "notes": [f"baseline={baseline_path.as_posix()}"],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect federation identity drift")
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE), help="baseline path")
    parser.add_argument("--output", default=str(DEFAULT_REPORT), help="output report path")
    args = parser.parse_args(argv)

    report = detect_drift(baseline_path=Path(args.baseline), output_path=Path(args.output))
    print(json.dumps({"tool": "detect_federation_identity_drift", "drifted": report["drifted"], "drift_type": report["drift_type"]}, sort_keys=True))
    if os.getenv("SENTIENTOS_CI_FAIL_ON_FEDERATION_IDENTITY_DRIFT") == "1" and report["drift_type"] != "none":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
