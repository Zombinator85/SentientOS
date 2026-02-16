from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

DEFAULT_MANIFEST = Path("vow/immutable_manifest.json")
DEFAULT_FILES = (
    Path("NEWLEGACY.txt"),
    Path("vow/config.yaml"),
    Path("vow/invariants.yaml"),
    Path("vow/init.py"),
    Path("scripts/audit_immutability_verifier.py"),
    Path("scripts/verify_audits.py"),
)
SCHEMA_VERSION = 1
TOOL_VERSION = "1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_sha() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""
    return completed.stdout.strip()


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def generate_manifest(
    *,
    output: Path,
    files: tuple[Path, ...] = DEFAULT_FILES,
    allow_missing_files: bool = False,
) -> dict[str, Any]:
    manifest_files: dict[str, dict[str, Any]] = {}
    missing: list[str] = []

    for path in sorted(files, key=lambda item: item.as_posix()):
        normalized = path.as_posix()
        if not path.exists():
            missing.append(normalized)
            continue
        manifest_files[normalized] = {
            "sha256": _sha256(path),
            "size": path.stat().st_size,
        }

    if missing and not allow_missing_files:
        raise FileNotFoundError(f"immutable manifest inputs missing: {', '.join(missing)}")

    manifest_hash = hashlib.sha256(_canonical_json(manifest_files).encode("utf-8")).hexdigest()
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "manifest_type": "sentientos_immutable",
        "generated_by": "scripts.generate_immutable_manifest",
        "tool_version": TOOL_VERSION,
        "captured_by": _git_sha(),
        "manifest_sha256": manifest_hash,
        "canonical_serialization": {
            "sort_keys": True,
            "separators": [",", ":"],
            "path_normalization": "posix_relative",
        },
        "files": manifest_files,
    }
    if missing:
        payload["degraded_mode"] = {
            "active": True,
            "reason": "manifest_inputs_missing",
            "missing_files": missing,
        }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic immutable manifest")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="manifest output path")
    parser.add_argument(
        "--allow-missing-files",
        action="store_true",
        help="allow degraded mode when one or more manifest input files are missing",
    )
    args = parser.parse_args(argv)

    payload = generate_manifest(
        output=Path(args.manifest),
        allow_missing_files=args.allow_missing_files,
    )
    print(
        json.dumps(
            {
                "tool": "generate_immutable_manifest",
                "output": args.manifest,
                "degraded": bool(payload.get("degraded_mode", {}).get("active", False)),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
