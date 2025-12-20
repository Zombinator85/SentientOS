from __future__ import annotations

import argparse
import sys
from pathlib import Path

from hf_intake.manifest import ManifestError, validate_manifest


DEFAULT_MANIFEST_DIR = Path("manifests")


def _validate_path(path: Path) -> None:
    validate_manifest(path)
    data = path.read_text(encoding="utf-8")
    if "huggingface.co" in data:
        raise ManifestError(f"Manifest leaks HF URLs: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate deterministic model manifests")
    parser.add_argument("paths", nargs="*", help="Manifest files to validate; defaults to manifests/* if empty")
    args = parser.parse_args()

    manifest_paths = [Path(p) for p in args.paths] if args.paths else sorted(DEFAULT_MANIFEST_DIR.glob("*.json"))
    if not manifest_paths:
        print("No manifests to validate; skipping.")
        return 0

    for manifest_path in manifest_paths:
        print(f"Validating {manifest_path}...")
        _validate_path(manifest_path)
    print("All manifests validated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
