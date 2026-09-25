from __future__ import annotations
import hashlib, json
from pathlib import Path
import pytest
from sentientos.local_model_catalog import validate_local_model_catalog
from sentientos.local_model_selection import GIB, LocalInferenceHardwareProfile, plan_local_model_selection_catalog
from sentientos.model_mirror_publication import EFFECTS, MODEL_MIRROR_PUBLISH, PRINCIPAL

ROOT = Path(__file__).resolve().parents[1]
A = ROOT / "docs/development/qwen25_coder_linux_cpu_production_curator_package.json"
B = ROOT / "docs/development/phi3_mini_production_model_curator_package.json"
CATALOG = ROOT / "docs/development/two_model_linux_cpu_catalog_candidate.json"
INTAKE = ROOT / "docs/development/two_model_mirror_publication_intake.json"
pytestmark = pytest.mark.no_legacy_skip

def semantic(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()

def test_two_frozen_packages_bind_real_linux_cpu_routes_and_evidence() -> None:
    a, b = json.loads(A.read_text()), json.loads(B.read_text())
    for package in (a, b):
        claimed = package.pop("curator_package_semantic_digest")
        assert claimed == semantic(package)
        model = validate_local_model_catalog(package["catalog_preview"])["models"][0]
        linux = [r for r in model["execution_routes"] if r["backend_family"] == "cpu" and r.get("os_families") == ["linux"]]
        assert len(linux) == 1 and linux[0]["architectures"] == ["x86_64"]
        assert package["sovereign_mirror"]["upload_attempted"] is False
    assert a["predecessor"]["mutation_posture"] == "historical_package_preserved"
    assert b["artifact"]["sha256"] == b["evidence"]["streamed_artifact_sha256"] == b["evidence"]["upstream_lfs_sha256"]
    assert b["artifact"]["size_bytes"] == b["evidence"]["streamed_artifact_size_bytes"] == 2_393_231_072
    assert b["artifact"]["gguf_magic_hex"] == "47475546"

def test_candidate_has_exactly_two_distinct_eligible_cpu_identities_on_primary_profile() -> None:
    catalog = validate_local_model_catalog(json.loads(CATALOG.read_text()))
    assert len(catalog["models"]) == 2
    host = LocalInferenceHardwareProfile("primary", "0" * 64, "linux", "x86_64", int(64.8 * GIB),
        avx=True, avx2=True, avx512=True, accelerator_observed="unknown")
    plan = plan_local_model_selection_catalog(host, catalog)
    eligible = {(x["model_id"], x["route_id"]) for x in plan["eligible_candidates"] if x["backend_family"] == "cpu"}
    assert eligible == {("qwen2.5-coder-7b-instruct-q4-k-m", "qwen25-coder-q4-cpu-linux-x86-64"),
                        ("phi-3-mini-4k-instruct-q4-k-m", "phi3-mini-q4-cpu-linux-x86-64")}
    assert plan["selected"]["model_id"] == "qwen2.5-coder-7b-instruct-q4-k-m"
    assert plan["authoritative_deployed_catalog_verified"] is False and plan["production_eligible"] is False

def test_publication_intake_is_exact_but_contains_no_grant_or_provider_claim() -> None:
    intake = json.loads(INTAKE.read_text())
    claimed = intake.pop("intake_semantic_digest")
    assert claimed == semantic(intake)
    assert intake["status"] == "model_mirror_provider_configuration_required"
    assert intake["provider_available"] is intake["publication_performed"] is False
    assert {r["role"] for r in intake["requests"]} == {"A", "B"}
    for request in intake["requests"]:
        assert request["authority_principal"] == PRINCIPAL
        assert request["capability_id"] == MODEL_MIRROR_PUBLISH
        assert set(request["required_effects"]) == EFFECTS
        assert request["required_external_bindings"] == ["artifact_root", "active_grant_id", "active_lease_id"]
        assert request["artifact_sha256"] in request["object_name"]
        assert request["canonical_url"] == "https://models.sentientos.org/" + request["object_name"]
        assert hashlib.sha256((ROOT / request["curator_package_path"]).read_bytes()).hexdigest() == request["curator_package_sha256"]
