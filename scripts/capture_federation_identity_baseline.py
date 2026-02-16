from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.capture_pulse_schema_baseline import _extract_schema as pulse_schema
from scripts.capture_self_model_baseline import _schema as self_schema

SCHEMA_VERSION = 1
TOOL_VERSION = "1"
DEFAULT_OUTPUT = Path("glow/federation/baseline/federation_identity_baseline.json")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _git_sha() -> str:
    try:
        completed = subprocess.run(["git", "rev-parse", "--verify", "HEAD"], check=True, capture_output=True, text=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""
    return completed.stdout.strip()


def _read_vow_digest() -> str:
    env_manifest = os.getenv("IMMUTABILITY_MANIFEST_PATH")
    candidates = []
    if env_manifest:
        candidates.append(Path(env_manifest))
    candidates.extend([Path("/vow/immutable_manifest.json"), Path("vow/immutable_manifest.json")])
    for path in candidates:
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            digest = payload.get("manifest_sha256")
            if isinstance(digest, str):
                return digest
    raise FileNotFoundError("immutable manifest not found at /vow/immutable_manifest.json or vow/immutable_manifest.json")


def _fingerprint(value: object) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _identity_components() -> dict[str, str]:
    vow_digest = _read_vow_digest()
    pulse_digest = _fingerprint(pulse_schema())
    self_digest = _fingerprint(self_schema())
    code_version = _git_sha()
    return {
        "vow_digest": vow_digest,
        "pulse_schema_fingerprint": pulse_digest,
        "self_model_schema_fingerprint": self_digest,
        "code_version": code_version,
    }


def capture_baseline(output: Path) -> dict[str, Any]:
    components = _identity_components()
    payload = {
        "schema_version": SCHEMA_VERSION,
        "identity_components": components,
        "identity_digest": _fingerprint(components),
        "canonical_serialization": {
            "json_sort_keys": True,
            "json_separators": [",", ":"],
            "fingerprint_excludes": ["captured_at", "captured_by", "tool_version"],
        },
        "provenance": {
            "captured_at": _iso_now(),
            "captured_by": components["code_version"],
            "tool_version": TOOL_VERSION,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture federation identity baseline")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="output path")
    args = parser.parse_args(argv)
    payload = capture_baseline(Path(args.output))
    print(json.dumps({"tool": "capture_federation_identity_baseline", "output": args.output, "fingerprint": payload["identity_digest"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
