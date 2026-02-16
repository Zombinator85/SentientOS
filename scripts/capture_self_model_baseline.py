from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sentientos.glow.self_state import DEFAULT_SELF_STATE

SCHEMA_VERSION = 1
TOOL_VERSION = "1"
DEFAULT_OUTPUT = Path("glow/self/baseline/self_model_baseline.json")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _git_sha() -> str:
    try:
        completed = subprocess.run(["git", "rev-parse", "--verify", "HEAD"], check=True, capture_output=True, text=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""
    return completed.stdout.strip()


def _type_for(value: object) -> str:
    if value is None:
        return "nullable"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return "string"


def _constraints() -> dict[str, Any]:
    return {
        "confidence": {"type": "number"},
        "novelty_score": {"type": "number"},
        "introspection_flag": {"type": "bool"},
        "goal_context": {"type": "object"},
        "last_generated_goal": {"type": "object", "nullable": True},
    }


def _schema() -> dict[str, Any]:
    required_keys = sorted(DEFAULT_SELF_STATE.keys())
    key_types = {key: _type_for(DEFAULT_SELF_STATE[key]) for key in required_keys}
    return {
        "schema_version": "1.0",
        "required_keys": required_keys,
        "key_types": key_types,
        "constraints": _constraints(),
        "allowed_write_back_fields": required_keys,
    }


def _fingerprint(schema: dict[str, Any]) -> str:
    canonical = json.dumps(schema, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def capture_baseline(output: Path) -> dict[str, Any]:
    schema = _schema()
    payload = {
        "schema_version": SCHEMA_VERSION,
        "self_model_schema": schema,
        "schema_fingerprint": _fingerprint(schema),
        "manual_acceptance_required": False,
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
    parser = argparse.ArgumentParser(description="Capture self-model schema baseline")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="output path")
    args = parser.parse_args(argv)
    payload = capture_baseline(Path(args.output))
    print(json.dumps({"tool": "capture_self_model_baseline", "output": args.output, "fingerprint": payload["schema_fingerprint"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
