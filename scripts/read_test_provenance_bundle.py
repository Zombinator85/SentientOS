from __future__ import annotations

import argparse
import json
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.provenance_hash_chain import HASH_ALGO, compute_provenance_hash
from scripts.verify_test_provenance_bundle import _validate_manifest_schema


@dataclass(frozen=True)
class BundleReadResult:
    bundle_path: Path
    manifest: dict[str, Any]
    runs: list[dict[str, Any]]


def _load_member_json(archive: tarfile.TarFile, name: str) -> dict[str, Any]:
    member = archive.getmember(name)
    extracted = archive.extractfile(member)
    if extracted is None:
        raise ValueError(f"unable to read {name}")
    payload = json.loads(extracted.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected object JSON in {name}")
    return payload


def _verify_manifest_chain(
    manifest: dict[str, Any],
    archive: tarfile.TarFile,
    bundle_path: Path,
) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    runs: list[dict[str, Any]] = []
    previous_hash: str | None = None

    files = manifest.get("files", [])
    if not isinstance(files, list):
        return [], ["manifest.files missing/invalid"]

    for index, entry in enumerate(files):
        if not isinstance(entry, dict):
            errors.append(f"manifest.files[{index}] not object")
            continue
        relative_name = entry.get("name")
        if not isinstance(relative_name, str):
            errors.append(f"manifest.files[{index}].name missing/invalid")
            continue

        payload = _load_member_json(archive, relative_name)
        hash_algo = payload.get("hash_algo")
        prev_hash = payload.get("prev_provenance_hash")
        actual_hash = payload.get("provenance_hash")
        if hash_algo != HASH_ALGO:
            errors.append(f"{relative_name}: bad hash_algo")
        if not isinstance(prev_hash, str):
            errors.append(f"{relative_name}: missing prev_provenance_hash")
        if not isinstance(actual_hash, str):
            errors.append(f"{relative_name}: missing provenance_hash")
            continue

        if index > 0 and prev_hash != previous_hash:
            errors.append(f"{relative_name}: chain discontinuity")

        expected_hash = compute_provenance_hash(payload, prev_hash if isinstance(prev_hash, str) else None)
        if expected_hash != actual_hash:
            errors.append(f"{relative_name}: payload hash mismatch")
        if actual_hash != entry.get("provenance_hash"):
            errors.append(f"{relative_name}: manifest hash mismatch")

        run = dict(payload)
        run["_source"] = f"{relative_name}@{bundle_path.name}"
        runs.append(run)
        previous_hash = actual_hash

    if runs:
        first_hash = str(runs[0].get("provenance_hash", ""))
        last_hash = str(runs[-1].get("provenance_hash", ""))
        if first_hash != manifest.get("first_provenance_hash"):
            errors.append("manifest first_provenance_hash mismatch")
        if last_hash != manifest.get("last_provenance_hash"):
            errors.append("manifest last_provenance_hash mismatch")
    return runs, errors


def read_bundle_runs(bundle_path: Path) -> BundleReadResult:
    with tarfile.open(bundle_path, mode="r:gz") as archive:
        names = set(archive.getnames())
        if "manifest.json" not in names:
            raise ValueError(f"manifest.json missing from {bundle_path}")

        manifest = _load_member_json(archive, "manifest.json")
        schema_errors = _validate_manifest_schema(manifest)
        if schema_errors:
            raise ValueError(f"invalid bundle manifest for {bundle_path}: {'; '.join(schema_errors)}")

        runs, chain_errors = _verify_manifest_chain(manifest, archive, bundle_path)
        if chain_errors:
            raise ValueError(f"bundle verification failed for {bundle_path}: {'; '.join(chain_errors)}")
        return BundleReadResult(bundle_path=bundle_path, manifest=manifest, runs=runs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read and verify provenance bundle runs without extracting to disk.")
    parser.add_argument("bundle", type=Path, help="Path to provenance bundle archive (tar.gz).")
    args = parser.parse_args(argv)

    result = read_bundle_runs(args.bundle)
    print(
        f"Bundle read OK: {args.bundle} runs={len(result.runs)} "
        f"window={result.manifest.get('bundle_window', {}).get('from')}..{result.manifest.get('bundle_window', {}).get('to')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
