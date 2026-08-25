"""Curator-only promotion from proven local escrow to portable model metadata."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
import stat
from typing import Any, Mapping

from hf_intake.manifest import V2_SCHEMA_VERSION, ManifestError, validate_manifest
from sentientos.local_model_catalog import SCHEMA_VERSION, LocalModelCatalogError, validate_local_model_catalog
from sentientos.local_model_source_provenance import (
    is_canonical_source_artifact_filename, is_canonical_source_repository, is_immutable_source_revision,
)


def _require_regular_file(path: Path, label: str) -> None:
    try:
        mode = path.lstat().st_mode
    except OSError as exc:
        raise ManifestError(f"curator evidence {label} is missing") from exc
    if not stat.S_ISREG(mode):
        raise ManifestError(f"curator evidence {label} must be a non-symlink regular file")
    current = path.parent
    while current != current.parent:
        if stat.S_ISLNK(current.lstat().st_mode):
            raise ManifestError(f"curator evidence {label} has a symlinked parent")
        current = current.parent


def _read_checksum_sidecar(path: Path, artifact_name: str) -> str:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "r", encoding="ascii") as stream:
            lines = stream.read().splitlines()
    except (OSError, UnicodeError) as exc:
        raise ManifestError("escrow checksum sidecar is unreadable") from exc
    if len(lines) != 1:
        raise ManifestError("escrow checksum sidecar must contain exactly one record")
    parts = lines[0].split("  ")
    if len(parts) != 2 or len(parts[0]) != 64 or any(c not in "0123456789abcdef" for c in parts[0]):
        raise ManifestError("escrow checksum sidecar is malformed")
    if parts[1] != artifact_name:
        raise ManifestError("escrow checksum sidecar identifies the wrong artifact")
    return parts[0]


def _hash(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise ManifestError("curator GGUF evidence must remain a regular file")
    with os.fdopen(descriptor, "rb") as stream:
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
        checksum_path = artifact_path.with_suffix(artifact_path.suffix + ".sha256")
        root = artifact_path.parent
        license_path, card_path, source_path = root / "LICENSE.txt", root / "MODEL_CARD.md", root / "SOURCE.json"
        for evidence_path, label in ((artifact_path, "GGUF artifact"), (checksum_path, "checksum sidecar"),
                                     (license_path, "LICENSE.txt"), (card_path, "MODEL_CARD.md"),
                                     (source_path, "SOURCE.json")):
            _require_regular_file(evidence_path, label)
        digest, size = _hash(artifact_path)
        if digest != artifact.get("sha256") or size != artifact.get("size_bytes"):
            raise ManifestError("independent escrow artifact identity verification failed")
        if _read_checksum_sidecar(checksum_path, artifact_path.name) != digest:
            raise ManifestError("escrow checksum sidecar does not match the GGUF and manifest")
        try:
            source: Mapping[str, Any] = json.loads(source_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ManifestError("SOURCE.json is invalid") from exc
        if source.get("artifact") != artifact_path.name:
            raise ManifestError("SOURCE.json artifact does not identify the escrow record")
        if source.get("license") != entry.get("license"):
            raise ManifestError("SOURCE.json license does not match the curator manifest")
        source_repo = source.get("repo_id")
        source_revision = source.get("revision")
        source_filename = source.get("source_artifact_filename")
        if not is_canonical_source_repository(source_repo):
            raise ManifestError("SOURCE.json repo_id is not a canonical Hugging Face repository identity")
        if not is_immutable_source_revision(source_revision):
            raise ManifestError("SOURCE.json revision is not a canonical immutable Git object identity")
        if not is_canonical_source_artifact_filename(source_filename):
            raise ManifestError("SOURCE.json requires an exact repository-relative source_artifact_filename")
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
    output_path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    current = output_path.parent
    while current != current.parent:
        if stat.S_ISLNK(current.lstat().st_mode):
            raise ManifestError("catalog publication path has a symlinked parent")
        current = current.parent
    if output_path.is_symlink():
        raise ManifestError("catalog publication target must not be symlinked")
    fd, temporary = tempfile.mkstemp(prefix=f".{output_path.name}.", dir=output_path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, output_path)
        except FileExistsError:
            try:
                target_fd = os.open(output_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                with os.fdopen(target_fd, "rb") as target_stream:
                    existing = target_stream.read() if stat.S_ISREG(os.fstat(target_stream.fileno()).st_mode) else None
            except OSError as exc:
                raise ManifestError("unable to inspect concurrently published catalog") from exc
            if existing != payload:
                raise ManifestError("refusing to overwrite conflicting production catalog")
        directory_fd = os.open(output_path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return catalog
