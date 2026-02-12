from __future__ import annotations

import argparse
import json
import tarfile
import tempfile
from pathlib import Path
from typing import Any

import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.provenance_hash_chain import HASH_ALGO, compute_provenance_hash

DEFAULT_OUTPUT = Path("bundle_verification.json")


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def _validate_manifest_schema(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version": int,
        "created_at": str,
        "repo_root": str,
        "bundle_window": dict,
        "hash_algo": str,
        "first_provenance_hash": str,
        "last_provenance_hash": str,
        "files": list,
        "trend_report": str,
    }

    for key, expected_type in required.items():
        value = manifest.get(key)
        if not isinstance(value, expected_type):
            errors.append(f"manifest.{key} missing/invalid")

    bundle_window = manifest.get("bundle_window")
    if isinstance(bundle_window, dict):
        for key, expected_type in (("from", str), ("to", str), ("count", int)):
            if not isinstance(bundle_window.get(key), expected_type):
                errors.append(f"manifest.bundle_window.{key} missing/invalid")

    files = manifest.get("files")
    if isinstance(files, list):
        for index, entry in enumerate(files):
            if not isinstance(entry, dict):
                errors.append(f"manifest.files[{index}] not object")
                continue
            if not isinstance(entry.get("name"), str):
                errors.append(f"manifest.files[{index}].name missing/invalid")
            if not isinstance(entry.get("provenance_hash"), str):
                errors.append(f"manifest.files[{index}].provenance_hash missing/invalid")

    if manifest.get("schema_version") != 1:
        errors.append("manifest.schema_version must be 1")
    if manifest.get("hash_algo") != HASH_ALGO:
        errors.append(f"manifest.hash_algo must be {HASH_ALGO}")
    return errors


def _verify_chain(files: list[dict[str, str]], bundle_root: Path) -> tuple[bool, list[str], str | None, str | None]:
    errors: list[str] = []
    previous_hash: str | None = None
    first_hash: str | None = None
    last_hash: str | None = None

    for index, entry in enumerate(files):
        relative_name = entry["name"]
        file_path = bundle_root / relative_name
        if not file_path.exists():
            errors.append(f"missing payload file: {relative_name}")
            continue
        payload = _read_json(file_path)
        prev_hash = payload.get("prev_provenance_hash")
        actual_hash = payload.get("provenance_hash")
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

        if index == 0:
            first_hash = actual_hash
        last_hash = actual_hash
        previous_hash = actual_hash

    return (len(errors) == 0, errors, first_hash, last_hash)


def _extract_bundle(bundle_path: Path, target_dir: Path) -> None:
    with tarfile.open(bundle_path, mode="r:gz") as archive:
        archive.extractall(target_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a provenance bundle archive.")
    parser.add_argument("bundle", type=Path, help="Path to provenance bundle archive (tar.gz).")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Where to write verification JSON report.")
    args = parser.parse_args(argv)

    summary: dict[str, Any] = {
        "bundle": str(args.bundle),
        "schema_ok": False,
        "hashes_ok": False,
        "chain_ok": False,
        "verified": False,
        "errors": [],
    }

    with tempfile.TemporaryDirectory() as temp_dir:
        bundle_root = Path(temp_dir)
        _extract_bundle(args.bundle, bundle_root)

        manifest_path = bundle_root / "manifest.json"
        if not manifest_path.exists():
            summary["errors"].append("manifest.json missing")
        else:
            manifest = _read_json(manifest_path)
            schema_errors = _validate_manifest_schema(manifest)
            summary["errors"].extend(schema_errors)
            summary["schema_ok"] = len(schema_errors) == 0

            if summary["schema_ok"]:
                files = manifest["files"]
                chain_ok, chain_errors, first_hash, last_hash = _verify_chain(files, bundle_root)
                summary["errors"].extend(chain_errors)
                summary["chain_ok"] = chain_ok
                summary["hashes_ok"] = chain_ok
                summary["first_provenance_hash"] = first_hash
                summary["last_provenance_hash"] = last_hash

                if first_hash != manifest.get("first_provenance_hash"):
                    summary["errors"].append("manifest first_provenance_hash mismatch")
                    summary["hashes_ok"] = False
                if last_hash != manifest.get("last_provenance_hash"):
                    summary["errors"].append("manifest last_provenance_hash mismatch")
                    summary["hashes_ok"] = False

                trend_report = bundle_root / manifest["trend_report"]
                if not trend_report.exists():
                    summary["errors"].append("trend report missing")

                summary["verified"] = summary["schema_ok"] and summary["hashes_ok"] and summary["chain_ok"]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(f"{json.dumps(summary, indent=2, sort_keys=True)}\n", encoding="utf-8")

    status = "OK" if summary["verified"] else "FAILED"
    print(
        f"Bundle verification [{status}] schema_ok={summary['schema_ok']} "
        f"hashes_ok={summary['hashes_ok']} chain_ok={summary['chain_ok']} "
        f"errors={len(summary['errors'])}"
    )
    if summary["errors"]:
        for error in summary["errors"]:
            print(f" - {error}")
    return 0 if summary["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
