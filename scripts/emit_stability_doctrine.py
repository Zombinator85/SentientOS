from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sentientos.vow_artifacts import _resolve_manifest_path

OUTPUT_PATH = Path("glow/contracts/stability_doctrine.json")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _git_sha() -> str:
    try:
        completed = subprocess.run(["git", "rev-parse", "--verify", "HEAD"], check=True, capture_output=True, text=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""
    return completed.stdout.strip()


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(command: list[str]) -> tuple[bool, str]:
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    out = (completed.stdout or "").strip() or (completed.stderr or "").strip()
    return (completed.returncode == 0, out)


def emit_stability_doctrine(output: Path = OUTPUT_PATH) -> dict[str, Any]:
    verify_ok, verify_info = _run(["python", "-m", "sentientos.verify_audits", "--strict"])
    manifest_path = _resolve_manifest_path()
    manifest_present = manifest_path.exists()
    manifest_sha = _sha256(manifest_path) if manifest_present else None
    mypy_ok, _ = _run(["make", "mypy-forge"])
    tests_ok, _ = _run(["make", "forge-ci"])

    payload: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": _iso_now(),
        "git_sha": _git_sha(),
        "toolchain": {
            "verify_audits_module": "python -m sentientos.verify_audits --strict",
            "verify_audits_available": verify_ok,
            "verify_audits_info": verify_info,
        },
        "vow_artifacts": {
            "immutable_manifest_path": str(manifest_path),
            "immutable_manifest_present": manifest_present,
            "immutable_manifest_sha256": manifest_sha,
        },
        "mypy_baseline": {"target": "mypy-forge", "passed": mypy_ok},
        "tests_baseline": {"target": "forge-ci", "passed": tests_ok},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    _ = argv
    payload = emit_stability_doctrine()
    print(json.dumps({"tool": "emit_stability_doctrine", "output": str(OUTPUT_PATH), "ok": payload["toolchain"]["verify_audits_available"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
