"""Offline verifier for the fixed local-runtime dependency custody catalog."""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

from sentientos.local_runtime_dependencies import validate_dependency_catalog


def verify(catalog_path: Path, provenance_path: Path) -> list[str]:
    errors: list[str] = []
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        validated = validate_dependency_catalog(catalog)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return [f"catalog_invalid:{exc}"]
    try:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"provenance_invalid:{exc}"]
    if provenance.get("catalog_digest") != validated["catalog_digest"]:
        errors.append("provenance_catalog_digest_mismatch")
    if provenance.get("dependency_graph") != validated["dependency_graph"]:
        errors.append("provenance_dependency_graph_mismatch")
    if provenance.get("environment_bundles") != validated["environment_bundles"]:
        errors.append("provenance_bundle_mismatch")
    evidence = {item.get("artifact_id"): item for item in provenance.get("artifacts", [])}
    if set(evidence) != set(validated["artifacts_by_id"]):
        errors.append("provenance_artifact_coverage_mismatch")
    for artifact_id, artifact in validated["artifacts_by_id"].items():
        item = evidence.get(artifact_id, {})
        for key in ("artifact_url", "artifact_filename", "requires_python", "dependency_requirement_strings",
                    "license_identity", "wheel_tags"):
            if item.get(key) != artifact.get(key):
                errors.append(f"provenance_{key}_mismatch:{artifact_id}")
        if item.get("expected_sha256") != artifact["artifact_sha256"] or item.get("observed_sha256") != artifact["artifact_sha256"]:
            errors.append(f"provenance_hash_mismatch:{artifact_id}")
        if item.get("expected_size_bytes") != artifact["artifact_size_bytes"] or item.get("observed_size_bytes") != artifact["artifact_size_bytes"]:
            errors.append(f"provenance_size_mismatch:{artifact_id}")
    source = Path("sentientos/local_runtime_dependencies.py").read_text(encoding="utf-8")
    forbidden = {"subprocess", "pip", "venv", "llama_cpp", "requests", "httpx"}
    for node in ast.walk(ast.parse(source)):
        names: set[str] = set()
        if isinstance(node, ast.Import):
            names = {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            names = {(node.module or "").split(".")[0]}
        for name in names & forbidden:
            errors.append(f"forbidden_import:{name}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=Path("manifests/local-runtime-dependency-catalog-v1.json"))
    parser.add_argument("--provenance", type=Path, default=Path("docs/development/local_runtime_dependency_catalog_provenance.json"))
    args = parser.parse_args()
    errors = verify(args.catalog, args.provenance)
    print("local_runtime_dependency_custody_verified" if not errors else "\n".join(errors))
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
