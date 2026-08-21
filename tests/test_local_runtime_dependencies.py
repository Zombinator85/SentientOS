from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sentientos.local_runtime_dependencies import (
    EXPECTED_VERSIONS, REQUIRED_ENVIRONMENTS, plan_runtime_dependencies,
    semantic_digest, validate_dependency_catalog,
)

pytestmark = pytest.mark.no_legacy_skip


@pytest.fixture()
def catalog():
    return json.loads(Path("manifests/local-runtime-dependency-catalog-v1.json").read_text())


def profile(os_family="linux", minor=10, arch="x86_64", libc="glibc", libc_version="2.17", macos=""):
    return {"schema_version":"sentientos.local_runtime_environment_profile:v2", "os_family":os_family,
            "architecture":arch,"python_implementation":"cpython","python_major":3,"python_minor":minor,
            "python_abi":f"cp3{minor}","source_identity":"synthetic","source_digest":"a"*64,
            "missing_fact_codes":[],"libc_family":libc,"libc_version":libc_version,"macos_version":macos}


def redigest(value):
    value["catalog_digest"] = semantic_digest({k:v for k,v in value.items() if k != "catalog_digest"})


def test_exact_versions_closure_and_unique_artifacts(catalog):
    validated=validate_dependency_catalog(catalog)
    assert validated["curated_versions"] == EXPECTED_VERSIONS
    assert len(validated["artifacts"]) == 21
    assert validated["dependency_graph"]["Jinja2==3.1.6"] == ["MarkupSafe>=2.0"]
    assert all(not requirements for node,requirements in validated["dependency_graph"].items()
               if node not in ("llama-cpp-python==0.3.35","Jinja2==3.1.6"))


@pytest.mark.parametrize("environment_id", REQUIRED_ENVIRONMENTS)
def test_all_nine_bundles_are_exact(environment_id, catalog):
    bundle=next(b for b in validate_dependency_catalog(catalog)["environment_bundles"] if b["environment_id"]==environment_id)
    assert len(bundle["artifact_ids"]) == 5
    assert len(set(bundle["artifact_ids"])) == 5


def test_universal_wheels_are_reused(catalog):
    bundles=validate_dependency_catalog(catalog)["environment_bundles"]
    universal=[set(i for i in b["artifact_ids"] if i.endswith("-py3-none-any")) for b in bundles]
    assert len(universal[0]) == 3 and all(x == universal[0] for x in universal)


@pytest.mark.parametrize("changes", [
    {"python_minor":13}, {"os_family":"freebsd"}, {"architecture":"arm64"},
    {"libc_version":"2.16"},
])
def test_unsupported_environment_rejects(changes,catalog):
    p=profile(); p.update(changes)
    assert plan_runtime_dependencies(catalog,p)["status"] == "blocked_unsupported_environment"


def test_unknown_linux_libc_blocks(catalog):
    assert plan_runtime_dependencies(catalog,profile(libc="",libc_version=""))["status"] == "blocked_missing_environment_facts"


def test_macos_deployment_floor(catalog):
    assert plan_runtime_dependencies(catalog,profile("darwin",10,"arm64","","", "10.15"))["status"] == "blocked_unsupported_environment"


@pytest.mark.parametrize("mutation,error", [
    (lambda c:c["environment_bundles"][0]["artifact_ids"].pop(), "catalog_digest_mismatch"),
    (lambda c:c["artifacts"][0].update(artifact_sha256="0"*64), "catalog_digest_mismatch"),
    (lambda c:c["artifacts"][0].update(artifact_size_bytes=0), "catalog_digest_mismatch"),
    (lambda c:c["artifacts"][0].update(package_version="9"), "catalog_digest_mismatch"),
    (lambda c:c["artifacts"][0].update(python_tag="cp399"), "catalog_digest_mismatch"),
    (lambda c:c["artifacts"][0].update(distribution_kind="sdist"), "catalog_digest_mismatch"),
])
def test_catalog_tampering_rejected(catalog,mutation,error):
    mutation(catalog)
    with pytest.raises(ValueError,match=error): validate_dependency_catalog(catalog)


def test_semantic_digest_ignores_mapping_order_and_bundle_is_canonical(catalog):
    assert semantic_digest(catalog) == semantic_digest(dict(reversed(list(catalog.items()))))
    assert all(b["artifact_ids"] == sorted(b["artifact_ids"]) for b in catalog["environment_bundles"])


def test_end_to_end_exact_bundle_selected_with_zero_effect(catalog):
    plan=plan_runtime_dependencies(catalog,profile())
    assert plan["status"] == "selected" and plan["runtime_dependency_custody_ready"]
    assert len(plan["artifact_ids"]) == 5
    assert {a["package_name"].lower().replace("_","-") for a in plan["artifacts"]} == set(EXPECTED_VERSIONS)
    assert all(plan[key] is False for key in ("network_performed","download_performed","package_install_performed",
        "subprocess_performed","runtime_import_performed","model_load_performed","commissioning_performed",
        "runtime_execution_authority_granted"))
    assert plan == plan_runtime_dependencies(catalog,profile())


def test_missing_package_and_duplicate_package_fail_closed(catalog):
    for mutation in (lambda ids:ids.pop(), lambda ids:ids.__setitem__(1,ids[0])):
        changed=copy.deepcopy(catalog); mutation(changed["environment_bundles"][0]["artifact_ids"])
        changed["environment_bundles"][0]["bundle_digest"]=semantic_digest({k:v for k,v in changed["environment_bundles"][0].items() if k!="bundle_digest"})
        redigest(changed)
        assert plan_runtime_dependencies(changed,profile("windows"))["status"] == "blocked_invalid_catalog"
