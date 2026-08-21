"""Offline verification for checked-in production llama.cpp runtime custody."""
from __future__ import annotations
import json
import re
from pathlib import Path
from sentientos.local_runtime_provisioning import CATALOG_SCHEMA_VERSION_V2, validate_runtime_catalog
ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "manifests/local-runtime-catalog-v2.json"
PROVENANCE = ROOT / "docs/development/production_runtime_catalog_provenance.json"
SHA = re.compile(r"[0-9a-f]{64}")
EXPECTED_PYTHONS = ["3.10", "3.11", "3.12"]
EXPECTED_FAMILIES = ["cpu", "cuda", "metal", "rocm"]

def verify() -> dict[str, object]:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8")); provenance = json.loads(PROVENANCE.read_text(encoding="utf-8"))
    if catalog.get("schema_version") != CATALOG_SCHEMA_VERSION_V2: raise ValueError("production_catalog_requires_v2")
    normalized = validate_runtime_catalog(catalog); records = {item["runtime_id"]: item for item in provenance.get("entries", [])}
    for item in catalog["runtimes"]:
        url = item["artifact_urls"][0]; lowered = url.lower()
        if any(token in lowered for token in (".invalid", "/latest", "/simple", "fixtures", "example.com")): raise ValueError("non_production_url")
        if not url.startswith("https://github.com/abetlen/llama-cpp-python/releases/download/v0.3.35"): raise ValueError("non_first_party_exact_release_url")
        if item.get("source_repository") != "abetlen/llama-cpp-python" or item.get("source_kind") != "github_release_asset": raise ValueError("invalid_source_custody")
        if item.get("package_name", "").replace("_", "-").lower() != "llama-cpp-python" or item.get("package_version") != "0.3.35": raise ValueError("invalid_package_identity")
        sha = item.get("artifact_sha256", "")
        if not SHA.fullmatch(sha) or sha == "0" * 64 or len(set(sha)) == 1: raise ValueError("placeholder_artifact_sha256")
        if item.get("artifact_size_bytes", 0) <= 0 or item.get("supported_python_versions") != EXPECTED_PYTHONS or not item.get("backend_variant"): raise ValueError("incomplete_runtime_metadata")
        if item.get("license_spdx") != "MIT": raise ValueError("invalid_license")
        record = records.get(item["runtime_id"])
        if not record: raise ValueError("missing_provenance")
        for key in ("artifact_filename", "artifact_sha256", "artifact_size_bytes"):
            if record.get(key) != item.get(key): raise ValueError("provenance_artifact_mismatch")
        tags = record.get("wheel_tags", {})
        if (tags.get("python_tag"), tags.get("abi_tag"), tags.get("platform_tag")) != (item["python_tag"], item["abi_tag"], item["platform_tag"]): raise ValueError("provenance_wheel_tag_mismatch")
        if record.get("independent_reproduction_status") != "matched_recorded_custody_anchor" or record.get("observed_artifact_sha256") != sha: raise ValueError("independent_verification_missing")
    if set(records) != {item["runtime_id"] for item in catalog["runtimes"]}: raise ValueError("orphan_provenance")
    families = sorted({item["backend_family"] for item in catalog["runtimes"]}); ready = families == EXPECTED_FAMILIES
    return {"status": "production_runtime_catalog_verified", "production_runtime_catalog_ready": ready, "backend_families": families, "runtime_count": len(records), "catalog_digest": normalized["catalog_digest"]}

def main() -> int:
    print(json.dumps(verify(), sort_keys=True)); return 0
if __name__ == "__main__": raise SystemExit(main())
