from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts import generate_immutable_manifest

PROVENANCE_PATH = Path("glow/contracts/vow_artifacts_provenance.json")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _git_sha() -> str:
    try:
        completed = subprocess.run(["git", "rev-parse", "--verify", "HEAD"], check=True, capture_output=True, text=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""
    return completed.stdout.strip()


def _resolve_manifest_path() -> Path:
    if Path("/vow").exists():
        return Path("/vow/immutable_manifest.json")
    return Path("vow/immutable_manifest.json")


def _manifest_sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ensure_vow_artifacts(*, manifest_path: Path | None = None) -> dict[str, Any]:
    target = manifest_path or _resolve_manifest_path()
    existed = target.exists()
    if not existed:
        generate_immutable_manifest.generate_manifest(output=target)

    inputs = [item.as_posix() for item in sorted(generate_immutable_manifest.DEFAULT_FILES, key=lambda p: p.as_posix())]
    payload: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": _iso_now(),
        "git_sha": _git_sha(),
        "manifest_path": str(target),
        "manifest_present": target.exists(),
        "manifest_generated": not existed,
        "manifest_sha256": _manifest_sha256(target),
        "manifest_inputs": inputs,
    }
    PROVENANCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROVENANCE_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ensure deterministic vow artifacts are present")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True
    subparsers.add_parser("ensure", help="ensure immutable_manifest exists")

    args = parser.parse_args(argv)
    if args.command == "ensure":
        payload = ensure_vow_artifacts()
        print(json.dumps({"tool": "vow_artifacts", "command": "ensure", "manifest_generated": payload["manifest_generated"], "manifest_path": payload["manifest_path"]}, sort_keys=True))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
