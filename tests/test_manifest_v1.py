import json
from pathlib import Path

import pytest

from hf_intake import manifest


MANIFEST_PATH = Path("manifests/manifest-v1.json")


def test_manifest_v1_validates() -> None:
    manifest.validate_manifest(MANIFEST_PATH)


def test_manifest_v1_rejects_missing_artifact(tmp_path: Path) -> None:
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    data["models"][0]["artifact"]["escrow_path"] = str(tmp_path / "missing.gguf")
    broken = tmp_path / "manifest.json"
    broken.write_text(json.dumps(data, indent=2), encoding="utf-8")
    with pytest.raises(manifest.ManifestError):
        manifest.validate_manifest(broken)


def test_manifest_v1_rejects_hf_urls(tmp_path: Path) -> None:
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    data["models"][0]["artifact"]["urls"] = ["https://huggingface.co/bad/gguf"]
    broken = tmp_path / "manifest.json"
    broken.write_text(json.dumps(data, indent=2), encoding="utf-8")
    with pytest.raises(manifest.ManifestError):
        manifest.validate_manifest(broken)


def _write_v2(tmp_path: Path, routes: object, *, gpu: bool = False) -> Path:
    artifact = tmp_path / "fixture.gguf"
    artifact.write_bytes(b"fixture")
    import hashlib
    requirements = {"architecture": "x86_64", "ram_gb_min": 1, "avx": False, "avx2": False,
                    "avx512": False, "quantization": "q4"}
    if gpu:
        requirements["gpu"] = False
    data = {"schema_version": manifest.V2_SCHEMA_VERSION, "manifest_version": "test", "models": [{
        "id": "fixture", "license": "apache-2.0", "priority": 1, "requirements": requirements,
        "execution_routes": routes, "artifact": {"escrow_path": str(artifact), "size_bytes": 7,
        "sha256": hashlib.sha256(b"fixture").hexdigest(), "urls": ["https://models.sentientos.org/fixture.gguf"]}}]}
    path = tmp_path / "manifest-v2.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.mark.parametrize("backend,vendor", [("cpu", None), ("cuda", "nvidia"), ("rocm", "amd"), ("metal", "apple")])
def test_manifest_v2_explicit_routes_validate(tmp_path: Path, backend: str, vendor: str | None) -> None:
    route = {"route_id": backend, "engine": "llama_cpp", "backend_family": backend, "route_priority": 1}
    if vendor:
        route["accelerator_vendor"] = vendor
    manifest.validate_manifest(_write_v2(tmp_path, [route]))


@pytest.mark.parametrize("routes,gpu", [([], False), (None, False), ([{"route_id": "cpu", "engine": "llama_cpp", "backend_family": "cpu", "route_priority": 1}], True)])
def test_manifest_v2_rejects_missing_routes_and_gpu(tmp_path: Path, routes: object, gpu: bool) -> None:
    with pytest.raises(manifest.ManifestError):
        manifest.validate_manifest(_write_v2(tmp_path, routes, gpu=gpu))


def test_manifest_v2_rejects_duplicate_unsupported_and_noncanonical_routes(tmp_path: Path) -> None:
    duplicate = [{"route_id": "same", "engine": "llama_cpp", "backend_family": "cpu", "route_priority": n} for n in (1, 2)]
    with pytest.raises(manifest.ManifestError): manifest.validate_manifest(_write_v2(tmp_path, duplicate))
    unsupported = [{"route_id": "x", "engine": "llama_cpp", "backend_family": "vulkan", "route_priority": 1}]
    with pytest.raises(manifest.ManifestError): manifest.validate_manifest(_write_v2(tmp_path, unsupported))
    unordered = [{"route_id": "cpu", "engine": "llama_cpp", "backend_family": "cpu", "route_priority": 2},
                 {"route_id": "metal", "engine": "llama_cpp", "backend_family": "metal", "accelerator_vendor": "apple", "route_priority": 1}]
    with pytest.raises(manifest.ManifestError): manifest.validate_manifest(_write_v2(tmp_path, unordered))
