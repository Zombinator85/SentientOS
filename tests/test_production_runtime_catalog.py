from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import pytest
from sentientos.local_runtime_provisioning import (CATALOG_SCHEMA_VERSION_V2, ENVIRONMENT_SCHEMA_VERSION_V2,
    LocalRuntimeEnvironmentProfile, plan_local_runtime_provisioning, semantic_digest, validate_runtime_catalog)
pytestmark = pytest.mark.no_legacy_skip
ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / "manifests/local-runtime-catalog-v2.json").read_text())
PROVENANCE = json.loads((ROOT / "docs/development/production_runtime_catalog_provenance.json").read_text())

def selection(backend: str) -> dict[str, object]:
    value: dict[str, object] = {"status": "selected", "selected": {"model_id": "production-witness-model", "artifact_sha256": "c" * 64, "route_id": f"{backend}-production-route", "runtime_requirement": {"engine": "llama_cpp", "backend_family": backend}}}
    value["plan_digest"] = semantic_digest(value); return value

def environment(entry: dict[str, object]) -> LocalRuntimeEnvironmentProfile:
    platform = str(entry["platform_tag"]); os_family = "windows" if platform == "win_amd64" else ("darwin" if platform.startswith("macosx") else "linux")
    return LocalRuntimeEnvironmentProfile(os_family, "arm64" if "arm64" in platform else "x86_64", "cpython", 3, 11,
        "unrelated-soabi", "production-fixture", "d" * 64, schema_version=ENVIRONMENT_SCHEMA_VERSION_V2,
        libc_family="glibc" if os_family == "linux" else "", libc_version="2.35" if os_family == "linux" else "", macos_version="11.0" if os_family == "darwin" else "")

def test_production_catalog_exists_is_v2_and_validates_deterministically() -> None:
    assert CATALOG["schema_version"] == CATALOG_SCHEMA_VERSION_V2
    assert validate_runtime_catalog(CATALOG) == validate_runtime_catalog(json.loads(json.dumps(CATALOG, sort_keys=True)))

def test_exact_upstream_custody_hash_size_tags_license_and_provenance() -> None:
    records = {item["runtime_id"]: item for item in PROVENANCE["entries"]}; assert records.keys() == {item["runtime_id"] for item in CATALOG["runtimes"]}
    for item in CATALOG["runtimes"]:
        url = item["artifact_urls"][0]; sha = item["artifact_sha256"]; record = records[item["runtime_id"]]
        assert url.startswith("https://github.com/abetlen/llama-cpp-python/releases/download/v0.3.35") and ".invalid" not in url and "latest" not in url and "/simple" not in url
        assert item["package_name"] == "llama-cpp-python" and item["package_version"] == "0.3.35"
        assert len(sha) == 64 and sha != "0" * 64 and len(set(sha)) > 1 and item["artifact_size_bytes"] > 0
        assert item["supported_python_versions"] == ["3.10", "3.11", "3.12"] and item["backend_variant"] and item["license_spdx"] == "MIT"
        assert (record["artifact_filename"], record["artifact_sha256"], record["artifact_size_bytes"]) == (item["artifact_filename"], sha, item["artifact_size_bytes"])
        assert record["metadata_name"] == "llama_cpp_python" and record["metadata_version"] == "0.3.35" and record["wheel_metadata_tag"] == f"{item['python_tag']}-{item['abi_tag']}-{item['platform_tag']}"
        assert record["expected_artifact_sha256"] == record["observed_artifact_sha256"] == sha
        assert record["expected_artifact_size_bytes"] == record["observed_artifact_size_bytes"] == item["artifact_size_bytes"]
        assert record["independent_reproduction_status"] == "matched_recorded_custody_anchor" and "0.2.90" not in json.dumps(item)

@pytest.mark.parametrize("runtime_id", [item["runtime_id"] for item in CATALOG["runtimes"]])
def test_real_catalog_entry_planner_witness_is_exact_and_zero_effect(runtime_id: str) -> None:
    entry = next(item for item in CATALOG["runtimes"] if item["runtime_id"] == runtime_id)
    plan = plan_local_runtime_provisioning(selection(str(entry["backend_family"])), environment(entry), CATALOG)
    assert plan["status"] == "selected" and plan["runtime_id"] == runtime_id and plan["artifact_sha256"] == entry["artifact_sha256"]
    assert (plan["backend_variant"], plan["python_tag"], plan["abi_tag"], plan["platform_tag"]) == (entry["backend_variant"], entry["python_tag"], entry["abi_tag"], entry["platform_tag"])
    assert plan["prerequisite_status"] == ("not_evaluated" if entry["external_prerequisite_codes"] else "not_required")
    for key in ("runtime_provisioning_executed", "network_performed", "download_performed", "package_install_performed", "subprocess_performed", "model_load_performed", "commissioning_performed", "authority_granted"): assert plan[key] is False

def test_backend_and_platform_coverage_and_readiness_are_derived() -> None:
    assert {item["backend_family"] for item in CATALOG["runtimes"]} == {"cpu", "cuda", "rocm", "metal"}
    assert len(CATALOG["runtimes"]) == 7

def test_offline_production_verifier_passes_and_readiness_is_true() -> None:
    spec = importlib.util.spec_from_file_location("production_verifier", ROOT / "scripts/verify_production_runtime_catalog.py")
    assert spec and spec.loader; module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    result = module.verify(); assert result["status"] == "production_runtime_catalog_verified" and result["production_runtime_catalog_ready"] is True
