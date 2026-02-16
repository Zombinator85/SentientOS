from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sentientos.streams import schema_registry

SCHEMA_VERSION = 1
TOOL_VERSION = "1"
DEFAULT_OUTPUT = Path("glow/pulse/baseline/pulse_schema_baseline.json")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _git_sha() -> str:
    try:
        completed = subprocess.run(["git", "rev-parse", "--verify", "HEAD"], check=True, capture_output=True, text=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""
    return completed.stdout.strip()


def _extract_schema() -> dict[str, Any]:
    registry = schema_registry._STREAM_REGISTRY  # noqa: SLF001
    streams: dict[str, Any] = {}
    for stream_name in sorted(registry.keys()):
        stream_registry = registry[stream_name]
        version = int(stream_registry.current_version)
        version_schema = stream_registry.versions[version]
        event_types = sorted(version_schema.required_payload_keys.keys())
        events: dict[str, Any] = {}
        for event_type in event_types:
            required_fields = sorted(version_schema.required_payload_keys[event_type])
            allowed_fields = sorted(version_schema.allowed_payload_keys[event_type])
            events[event_type] = {
                "required_fields": required_fields,
                "allowed_fields": allowed_fields,
                "field_types": {field: "any" for field in allowed_fields},
                "field_enums": {},
            }
        streams[stream_name] = {
            "schema_version": version,
            "required_envelope_fields": sorted(version_schema.required_envelope_keys),
            "envelope_field_types": {
                "stream": "str",
                "schema_version": "int",
                "event_id": "str",
                "event_type": "str",
                "timestamp": "str",
                "payload": "mapping",
            },
            "event_type_enum": event_types,
            "events": events,
        }
    return streams


def _fingerprint(schema: dict[str, Any]) -> str:
    canonical = json.dumps(schema, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def capture_baseline(output: Path) -> dict[str, Any]:
    schema = _extract_schema()
    payload = {
        "schema_version": SCHEMA_VERSION,
        "schema": schema,
        "schema_fingerprint": _fingerprint(schema),
        "canonical_serialization": {
            "json_sort_keys": True,
            "json_separators": [",", ":"],
            "fingerprint_excludes": ["captured_at", "captured_by", "tool_version"],
        },
        "provenance": {
            "captured_at": _iso_now(),
            "captured_by": _git_sha(),
            "tool_version": TOOL_VERSION,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture Pulse schema baseline")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="output path")
    args = parser.parse_args(argv)
    payload = capture_baseline(Path(args.output))
    print(json.dumps({"tool": "capture_pulse_schema_baseline", "output": args.output, "fingerprint": payload["schema_fingerprint"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
