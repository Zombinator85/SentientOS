from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

SCHEMA_VERSION = 1
REQUIRED_FILES = [
    "stability_doctrine.json",
    "contract_status.json",
    "artifact_metadata.json",
    "contract_manifest.json",
]
OPTIONAL_FILES = [
    "ci_baseline.json",
    "forge_progress_baseline.json",
]


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stable_json(path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def emit_manifest(contract_dir: Path, *, git_sha: str, created_at: str) -> Path:
    file_hashes: dict[str, str] = {}
    for rel_path in [*REQUIRED_FILES, *OPTIONAL_FILES]:
        target = contract_dir / rel_path
        if not target.exists():
            continue
        if target.suffix == ".json":
            _stable_json(target)
        file_hashes[rel_path] = _sha256(target)

    canonical = "".join(f"{path}\n{digest}\n" for path, digest in sorted(file_hashes.items()))
    bundle_sha256 = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "git_sha": git_sha,
        "created_at": created_at,
        "required_files": REQUIRED_FILES,
        "optional_files": OPTIONAL_FILES,
        "file_sha256": file_hashes,
        "bundle_sha256": bundle_sha256,
    }
    target = contract_dir / "contract_manifest.json"
    target.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Emit deterministic doctrine bundle manifest")
    parser.add_argument("--contract-dir", default="glow/contracts")
    parser.add_argument("--git-sha", default="")
    parser.add_argument("--created-at", default="")
    args = parser.parse_args()

    contract_dir = Path(args.contract_dir)
    created_at = args.created_at or _iso_now()
    emit_manifest(contract_dir, git_sha=args.git_sha, created_at=created_at)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
