from __future__ import annotations

import json
from typing import Any
from pathlib import Path

import pytest

from sentientos.local_model_catalog import LocalModelCatalogError, validate_local_model_catalog


pytestmark = pytest.mark.no_legacy_skip


PACKAGE = Path("docs/development/first_production_model_curator_package.json")


def _package() -> dict[str, Any]:
    value: Any = json.loads(PACKAGE.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_frozen_candidate_is_schema_valid_but_not_deployed() -> None:
    package = _package()
    assert package["status"] == "candidate_frozen_mirror_publication_blocked"
    assert package["success_level"] == 1
    assert package["artifact"]["verified_by_streamed_local_hash"] is True
    assert package["artifact"]["temporary_intake_only"] is True
    assert package["sovereign_mirror"]["upload_attempted"] is False
    assert package["sovereign_mirror"]["remote_object_verified"] is False
    catalog = validate_local_model_catalog(package["catalog_preview"])
    model = catalog["models"][0]
    assert model["artifact_sha256"] == "509287f78cb4d4cf6b3843734733b914b2c158e43e22a7f4bf5e963800894d3c"
    assert model["artifact_size_bytes"] == 4_683_073_536
    assert model["source_revision"] == "13fb94bfda8c8cf22497dc57b78f391a9acb426a"


@pytest.mark.parametrize(  # type: ignore[untyped-decorator]
    "url",
    [
        "https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF/resolve/main/model.gguf",
        "https://models.sentientos.org/latest.gguf",
        "https://example.invalid/qwen.gguf",
    ],
)
def test_candidate_cannot_gain_alternate_or_mutable_production_transport(url: str) -> None:
    catalog = _package()["catalog_preview"]
    catalog["models"][0]["artifact_urls"] = [url]
    with pytest.raises(LocalModelCatalogError):
        validate_local_model_catalog(catalog)


def test_candidate_routes_are_backed_by_current_runtime_families() -> None:
    package = _package()
    runtime = json.loads(Path("manifests/local-runtime-catalog-v2.json").read_text(encoding="utf-8"))
    available = {(item["backend_family"], item["platform_tag"]) for item in runtime["runtimes"]}
    catalog = validate_local_model_catalog(package["catalog_preview"])
    for route in catalog["models"][0]["execution_routes"]:
        platforms = {
            ("cpu", "windows"): "win_amd64",
            ("cuda", "linux"): "manylinux_2_35_x86_64",
            ("cuda", "windows"): "win_amd64",
            ("rocm", "linux"): "manylinux_2_35_x86_64",
            ("rocm", "windows"): "win_amd64",
        }
        for os_family in route["os_families"]:
            assert (route["backend_family"], platforms[(route["backend_family"], os_family)]) in available
