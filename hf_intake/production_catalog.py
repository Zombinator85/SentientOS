"""Curator-only promotion from proven local escrow to portable model metadata."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from hf_intake.manifest import V2_SCHEMA_VERSION, ManifestError, validate_manifest
from sentientos.local_model_catalog import SCHEMA_VERSION, LocalModelCatalogError, validate_local_model_catalog


def _hash(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            size += len(chunk)
            digest.update(chunk)
    return digest.hexdigest(), size


def promote_manifest(manifest_path: Path) -> dict[str, Any]:
    """Prove every curator-held byte record before discarding local path identity."""
    validate_manifest(manifest_path)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if data.get("schema_version") != V2_SCHEMA_VERSION:
        raise ManifestError("production promotion requires sentientos.model_manifest:v2")
    promoted: list[dict[str, Any]] = []
    for entry in data["models"]:
        artifact = entry["artifact"]
        artifact_path = Path(artifact["escrow_path"])
        digest, size = _hash(artifact_path)
        if digest != artifact.get("sha256") or size != artifact.get("size_bytes"):
            raise ManifestError("independent escrow artifact identity verification failed")
        root = artifact_path.parent
        license_path, card_path, source_path = root / "LICENSE.txt", root / "MODEL_CARD.md", root / "SOURCE.json"
        if not all(path.is_file() for path in (license_path, card_path, source_path)):
            raise ManifestError("curator evidence LICENSE.txt, MODEL_CARD.md, or SOURCE.json is missing")
        try:
            source: Mapping[str, Any] = json.loads(source_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ManifestError("SOURCE.json is invalid") from exc
        if source.get("artifact") != artifact_path.name:
            raise ManifestError("SOURCE.json artifact does not identify the escrow record")
        if source.get("license") != entry.get("license"):
            raise ManifestError("SOURCE.json license does not match the curator manifest")
        source_repo = source.get("repo_id") or source.get("source_repository")
        source_revision = source.get("revision") or source.get("source_revision")
        source_filename = source.get("source_artifact_filename")
        if not source_filename:
            source_filename = artifact_path.name[:-(len(digest) + len("-.gguf"))] + ".gguf"
        promoted.append({
            "model_id": entry["id"], "priority": entry["priority"], "license_id": entry["license"],
            "source_repository": source_repo, "source_revision": source_revision,
            "source_artifact_filename": source_filename, "artifact_filename": artifact_path.name,
            "artifact_sha256": digest, "artifact_size_bytes": size,
            "artifact_content_address": f"sha256:{digest}", "artifact_urls": sorted(artifact["urls"]),
            "requirements": dict(entry["requirements"]), "execution_routes": entry["execution_routes"],
        })
    catalog = {"schema_version": SCHEMA_VERSION,
               "models": sorted(promoted, key=lambda item: (item["priority"], item["model_id"]))}
    try:
        return validate_local_model_catalog(catalog)
    except LocalModelCatalogError as exc:
        raise ManifestError(f"promoted catalog is invalid: {exc}") from exc


def write_promoted_catalog(manifest_path: Path, output_path: Path) -> dict[str, Any]:
    """Atomically publish deterministic JSON, accepting only identical existing bytes."""
    catalog = promote_manifest(manifest_path)
    payload = (json.dumps(catalog, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if output_path.is_symlink() or output_path.parent.is_symlink():
        raise ManifestError("catalog publication path must not be symlinked")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        if not output_path.is_file() or output_path.read_bytes() != payload:
            raise ManifestError("refusing to overwrite conflicting production catalog")
        return catalog
    fd, temporary = tempfile.mkstemp(prefix=f".{output_path.name}.", dir=output_path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output_path)
        directory_fd = os.open(output_path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return catalog
