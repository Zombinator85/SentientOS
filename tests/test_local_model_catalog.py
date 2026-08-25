from __future__ import annotations

import copy
import json
import os
import shutil
from hashlib import sha256
from pathlib import Path

import pytest

from hf_intake import escrow, manifest as intake_manifest
from hf_intake.discovery import CandidateModel
from hf_intake.manifest import ManifestError
from hf_intake.production_catalog import promote_manifest, write_promoted_catalog
from sentientos.local_model_catalog import LocalModelCatalogError, validate_local_model_catalog
from sentientos.local_model_selection import GIB, LocalInferenceHardwareProfile, plan_local_model_selection_catalog, plan_local_model_selection_file

pytestmark = pytest.mark.no_legacy_skip
REVISION = "a" * 40


def _profile(**changes: object) -> LocalInferenceHardwareProfile:
    values = dict(source_inventory_id="fixture", source_inventory_digest="0" * 64, os_family="linux",
                  architecture="x86_64", total_ram_bytes=16 * GIB, avx=True, avx2=True, avx512=False)
    values.update(changes)
    return LocalInferenceHardwareProfile(**values)


def _curator_tree(root: Path, *, model_id: str = "synthetic-q4") -> Path:
    escrow = root / "escrow" / model_id
    escrow.mkdir(parents=True)
    payload = b"synthetic test-only GGUF bytes"
    digest = sha256(payload).hexdigest()
    filename = f"synthetic-q4-{digest}.gguf"
    artifact = escrow / filename
    artifact.write_bytes(payload)
    (escrow / f"{filename}.sha256").write_text(f"{digest}  {filename}\n", encoding="utf-8")
    (escrow / "LICENSE.txt").write_text("Apache-2.0 fixture evidence", encoding="utf-8")
    (escrow / "MODEL_CARD.md").write_text("# Synthetic test-only fixture\n", encoding="utf-8")
    source = {"id": model_id, "repo_id": "example/synthetic", "revision": REVISION,
              "source_artifact_filename": "quantized/synthetic-q4.gguf", "artifact": filename,
              "license": "apache-2.0", "priority": 1}
    (escrow / "SOURCE.json").write_text(json.dumps(source), encoding="utf-8")
    routes = [
        {"route_id": "cuda", "engine": "llama_cpp", "backend_family": "cuda", "accelerator_vendor": "nvidia", "route_priority": 10},
        {"route_id": "cpu", "engine": "llama_cpp", "backend_family": "cpu", "route_priority": 20},
    ]
    manifest = {"schema_version": "sentientos.model_manifest:v2", "manifest_version": "synthetic-v1", "models": [{
        "id": model_id, "priority": 1, "license": "apache-2.0",
        "artifact": {"sha256": digest, "size_bytes": len(payload), "escrow_path": str(artifact),
                     "urls": [f"https://models.sentientos.org/{filename}"]},
        "requirements": {"architecture": "x86_64", "ram_gb_min": 8, "avx": False, "avx2": True,
                         "avx512": False, "quantization": "q4"}, "execution_routes": routes,
    }]}
    path = root / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_promote_delete_escrow_then_validate_and_select(tmp_path: Path) -> None:
    manifest = _curator_tree(tmp_path)
    catalog = promote_manifest(manifest)
    escrow_path = Path(json.loads(manifest.read_text())["models"][0]["artifact"]["escrow_path"])
    shutil.rmtree(escrow_path.parent)
    validated = validate_local_model_catalog(catalog)
    plan = plan_local_model_selection_catalog(_profile(), validated)
    assert plan["status"] == "selected"
    assert plan["selected"]["model_id"] == "synthetic-q4"
    assert plan["selected"]["route_id"] == "cpu"
    assert plan["local_model_catalog_digest"] == validated["local_model_catalog_digest"]
    assert plan["selected"]["source_revision"] == REVISION
    assert plan["selected"]["source_artifact_filename"] == "quantized/synthetic-q4.gguf"
    assert plan["selected"]["artifact_content_address"].startswith("sha256:")
    assert "escrow_path" not in json.dumps(catalog)
    assert all(plan[key] is True for key in ("no_network_performed", "no_download_performed",
                                               "no_model_load_performed", "no_commissioning_performed", "no_authority_granted"))


def test_promotion_is_independent_of_curator_absolute_path(tmp_path: Path) -> None:
    first_path = _curator_tree(tmp_path / "one")
    second_path = _curator_tree(tmp_path / "different" / "deep" / "two")
    assert promote_manifest(first_path) == promote_manifest(second_path)


@pytest.mark.parametrize("mutation", ["bytes", "size", "checksum_missing", "checksum_bad", "sidecar_missing",
                                      "sidecar_malformed", "sidecar_digest", "sidecar_filename", "sidecar_duplicate", "coordinated_tamper",
                                      "artifact_symlink", "sidecar_symlink", "license_symlink", "card_symlink", "source_symlink", "license_missing",
                                      "card_missing", "source_missing", "source_artifact", "source_repo",
                                      "floating_revision", "license_mismatch", "invalid_route", "duplicate_route", "unsorted_route"])
def test_promotion_rejects_unproved_or_tampered_curator_evidence(tmp_path: Path, mutation: str) -> None:
    path = _curator_tree(tmp_path)
    data = json.loads(path.read_text())
    entry = data["models"][0]
    artifact = Path(entry["artifact"]["escrow_path"])
    source_path = artifact.parent / "SOURCE.json"
    source = json.loads(source_path.read_text())
    if mutation == "bytes": artifact.write_bytes(b"tampered")
    elif mutation == "size": entry["artifact"]["size_bytes"] += 1
    elif mutation == "checksum_missing": entry["artifact"].pop("sha256")
    elif mutation == "checksum_bad": entry["artifact"]["sha256"] = "f" * 64
    elif mutation == "sidecar_missing": artifact.with_suffix(".gguf.sha256").unlink()
    elif mutation == "sidecar_malformed": artifact.with_suffix(".gguf.sha256").write_text("garbage\n")
    elif mutation == "sidecar_digest": artifact.with_suffix(".gguf.sha256").write_text(f"{'f' * 64}  {artifact.name}\n")
    elif mutation == "sidecar_filename": artifact.with_suffix(".gguf.sha256").write_text(f"{entry['artifact']['sha256']}  other.gguf\n")
    elif mutation == "sidecar_duplicate": artifact.with_suffix(".gguf.sha256").write_text(artifact.with_suffix(".gguf.sha256").read_text() * 2)
    elif mutation == "coordinated_tamper":
        artifact.write_bytes(b"coordinated tamper")
        entry["artifact"]["sha256"] = sha256(artifact.read_bytes()).hexdigest()
        entry["artifact"]["size_bytes"] = artifact.stat().st_size
    elif mutation.endswith("_symlink"):
        names = {"artifact_symlink": artifact.name, "sidecar_symlink": artifact.name + ".sha256",
                 "license_symlink": "LICENSE.txt", "card_symlink": "MODEL_CARD.md", "source_symlink": "SOURCE.json"}
        victim = artifact.parent / names[mutation]
        external = tmp_path / f"external-{mutation}"
        external.write_bytes(victim.read_bytes())
        victim.unlink()
        victim.symlink_to(external)
    elif mutation == "license_missing": (artifact.parent / "LICENSE.txt").unlink()
    elif mutation == "card_missing": (artifact.parent / "MODEL_CARD.md").unlink()
    elif mutation == "source_missing": source_path.unlink()
    elif mutation == "source_artifact": source["artifact"] = "other.gguf"
    elif mutation == "source_repo": source.pop("repo_id")
    elif mutation == "floating_revision": source["revision"] = "main"
    elif mutation == "license_mismatch": source["license"] = "other"
    elif mutation == "invalid_route": entry["execution_routes"][0]["engine"] = "other"
    elif mutation == "duplicate_route": entry["execution_routes"][1]["route_id"] = "cuda"
    elif mutation == "unsorted_route": entry["execution_routes"].reverse()
    source_path.exists() and source_path.write_text(json.dumps(source), encoding="utf-8")
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ManifestError):
        promote_manifest(path)


@pytest.mark.parametrize("mutation", ["sha", "size", "address", "url", "hf", "duplicate", "engine", "backend",
                                      "vendor", "gpu", "escrow", "digest", "revision"])
def test_catalog_validator_rejects_tampered_metadata(tmp_path: Path, mutation: str) -> None:
    catalog = promote_manifest(_curator_tree(tmp_path))
    model = catalog["models"][0]
    if mutation == "sha": model["artifact_sha256"] = "bad"
    elif mutation == "size": model["artifact_size_bytes"] = -1
    elif mutation == "address": model["artifact_content_address"] = "sha256:" + "f" * 64
    elif mutation == "url": model["artifact_urls"] = ["https://evil.example/model.gguf"]
    elif mutation == "hf": model["artifact_urls"] = ["https://huggingface.co/model.gguf"]
    elif mutation == "duplicate": catalog["models"].append(copy.deepcopy(model))
    elif mutation == "engine": model["execution_routes"][0]["engine"] = "other"
    elif mutation == "backend": model["execution_routes"][0]["backend_family"] = "vulkan"
    elif mutation == "vendor": model["execution_routes"][0]["accelerator_vendor"] = "amd"
    elif mutation == "gpu": model["requirements"]["gpu"] = True
    elif mutation == "escrow": model["escrow_path"] = "/curator/model.gguf"
    elif mutation == "digest": catalog["local_model_catalog_digest"] = "f" * 64
    elif mutation == "revision": model["source_revision"] = "latest"
    with pytest.raises(LocalModelCatalogError):
        validate_local_model_catalog(catalog)


def test_file_dispatch_uses_catalog_without_artifact_and_binds_accelerated_route(tmp_path: Path) -> None:
    catalog = promote_manifest(_curator_tree(tmp_path))
    output = tmp_path / "catalog.json"
    output.write_text(json.dumps(catalog), encoding="utf-8")
    shutil.rmtree(tmp_path / "escrow")
    plan = plan_local_model_selection_file(_profile(accelerator_observed=True, accelerator_vendor="nvidia"), output)
    assert plan["status"] == "selected" and plan["selected"]["route_id"] == "cuda"
    assert plan["selected"]["route_requirements"] == {"accelerator_vendor": "nvidia"}


def test_atomic_publication_is_idempotent_and_rejects_conflict_or_symlink(tmp_path: Path) -> None:
    manifest = _curator_tree(tmp_path)
    output = tmp_path / "published" / "catalog.json"
    first = write_promoted_catalog(manifest, output)
    assert write_promoted_catalog(manifest, output) == first
    output.write_text("conflict", encoding="utf-8")
    with pytest.raises(ManifestError): write_promoted_catalog(manifest, output)
    output.unlink()
    output.symlink_to(manifest)
    with pytest.raises(ManifestError): write_promoted_catalog(manifest, output)


def test_publication_no_clobber_race(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _curator_tree(tmp_path)
    expected = tmp_path / "expected.json"
    write_promoted_catalog(manifest, expected)
    payload = expected.read_bytes()
    output = tmp_path / "race" / "catalog.json"
    real_link = __import__("os").link

    def race_with(content: bytes):
        def linked(source: object, target: object) -> None:
            Path(target).write_bytes(content)
            real_link(source, target)
        return linked

    monkeypatch.setattr("hf_intake.production_catalog.os.link", race_with(payload))
    assert write_promoted_catalog(manifest, output)["schema_version"].endswith(":v1")
    output.unlink()
    monkeypatch.setattr("hf_intake.production_catalog.os.link", race_with(b"competitor"))
    with pytest.raises(ManifestError):
        write_promoted_catalog(manifest, output)
    assert output.read_bytes() == b"competitor"


def test_publication_rejects_symlinked_parent(tmp_path: Path) -> None:
    manifest = _curator_tree(tmp_path)
    external = tmp_path / "external"
    external.mkdir()
    parent = tmp_path / "linked"
    parent.symlink_to(external, target_is_directory=True)
    with pytest.raises(ManifestError):
        write_promoted_catalog(manifest, parent / "catalog.json")
    assert not (external / "catalog.json").exists()


def test_publication_rejects_symlinked_ancestor_before_creating_descendants(tmp_path: Path) -> None:
    manifest = _curator_tree(tmp_path)
    external = tmp_path / "external"
    external.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(external, target_is_directory=True)
    with pytest.raises(ManifestError):
        write_promoted_catalog(manifest, linked / "new" / "deeper" / "catalog.json")
    assert not (external / "new").exists()


def test_symlinked_gguf_target_is_never_opened(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _curator_tree(tmp_path)
    data = json.loads(manifest.read_text())
    artifact = Path(data["models"][0]["artifact"]["escrow_path"])
    external = tmp_path / "external.gguf"
    external.write_bytes(artifact.read_bytes())
    artifact.unlink()
    artifact.symlink_to(external)
    real_open = os.open
    opened: list[Path] = []

    def recording_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        opened.append(Path(path))
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr("hf_intake.production_catalog.os.open", recording_open)
    with pytest.raises(ManifestError):
        promote_manifest(manifest)
    assert external not in opened
    assert artifact not in opened


def test_symlinked_manifest_is_rejected_before_open(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _curator_tree(tmp_path / "curator")
    linked = tmp_path / "linked-manifest.json"
    linked.symlink_to(manifest)
    real_open = os.open
    opened: list[Path] = []

    def recording_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        opened.append(Path(path))
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr("hf_intake.production_catalog.os.open", recording_open)
    with pytest.raises(ManifestError):
        promote_manifest(linked)
    assert linked not in opened and manifest not in opened


def test_source_swap_to_symlink_before_safe_open_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _curator_tree(tmp_path)
    data = json.loads(manifest.read_text())
    artifact = Path(data["models"][0]["artifact"]["escrow_path"])
    source = artifact.parent / "SOURCE.json"
    external = tmp_path / "external-source.json"
    external.write_bytes(source.read_bytes())
    real_open = os.open
    swapped = False

    def swapping_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        nonlocal swapped
        if Path(path) == source and not swapped:
            swapped = True
            source.unlink()
            source.symlink_to(external)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr("hf_intake.production_catalog.os.open", swapping_open)
    with pytest.raises(ManifestError):
        promote_manifest(manifest)
    assert swapped


def test_real_escrow_to_production_catalog_preserves_upstream_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    download = tmp_path / "download.gguf"
    download.write_bytes(b"synthetic real escrow bytes")
    monkeypatch.setattr(escrow, "hf_hub_download", lambda *args, **kwargs: str(download))
    candidate = CandidateModel("example/synthetic", REVISION, "apache-2.0", ["quantized/synthetic-Q4_K_M.gguf"],
                               "Apache-2.0 fixture", "# Synthetic fixture")
    result = escrow.escrow_artifact(candidate, candidate.gguf_files[0], tmp_path / "escrow", api=object())
    source_path = result.artifact_path.parent / "SOURCE.json"
    source = json.loads(source_path.read_text())
    source["id"] = "synthetic-q4"
    source["execution_routes"] = [{"route_id": "cpu", "engine": "llama_cpp", "backend_family": "cpu", "route_priority": 1}]
    source_path.write_text(json.dumps(source), encoding="utf-8")
    manifest_path = tmp_path / "manifest-v2.json"
    intake_manifest.generate_manifest(tmp_path / "escrow", manifest_path, "synthetic-v2", schema_version=intake_manifest.V2_SCHEMA_VERSION)
    catalog = promote_manifest(manifest_path)
    assert source["source_artifact_filename"] == "quantized/synthetic-Q4_K_M.gguf"
    assert source["artifact"] == result.artifact_path.name
    assert catalog["models"][0]["source_artifact_filename"] == "quantized/synthetic-Q4_K_M.gguf"


@pytest.mark.parametrize("revision", ["a" * 39, "a" * 41, "a" * 42, "a" * 63, "a" * 65, "main", "A" * 40])
def test_catalog_rejects_noncanonical_source_revision(tmp_path: Path, revision: str) -> None:
    catalog = promote_manifest(_curator_tree(tmp_path))
    catalog["models"][0]["source_revision"] = revision
    with pytest.raises(LocalModelCatalogError):
        validate_local_model_catalog(catalog)


@pytest.mark.parametrize("revision", ["a" * 40, "b" * 64])
def test_catalog_accepts_exact_git_object_revision(tmp_path: Path, revision: str) -> None:
    catalog = promote_manifest(_curator_tree(tmp_path))
    catalog["models"][0]["source_revision"] = revision
    catalog.pop("local_model_catalog_digest")
    assert validate_local_model_catalog(catalog)["models"][0]["source_revision"] == revision


@pytest.mark.parametrize("filename", ["../foo.gguf", "/foo.gguf", "C:\\foo.gguf", "foo\\bar.gguf", "./foo.gguf", "a//foo.gguf"])
def test_catalog_rejects_noncanonical_source_artifact_path(tmp_path: Path, filename: str) -> None:
    catalog = promote_manifest(_curator_tree(tmp_path))
    catalog["models"][0]["source_artifact_filename"] = filename
    with pytest.raises(LocalModelCatalogError):
        validate_local_model_catalog(catalog)


def test_static_catalog_boundary_verifier() -> None:
    from scripts.verify_local_model_catalog import main
    assert main() == 0
