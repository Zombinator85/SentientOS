"""Curator-only promotion from proven local escrow to portable model metadata."""
from __future__ import annotations

import hashlib
import ctypes
import errno
import json
import os
from pathlib import Path
import stat
from typing import Any, Mapping, cast

from hf_intake.manifest import V2_SCHEMA_VERSION, ManifestError, validate_manifest_data
from sentientos.local_model_catalog import SCHEMA_VERSION, LocalModelCatalogError, validate_local_model_catalog
from sentientos.local_model_source_provenance import (
    is_canonical_source_artifact_filename, is_canonical_source_repository, is_immutable_source_revision,
)


_DIR_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
_FILE_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
_SIDECAR_MAXIMUM_SIZE = 1024
_DIR_FD_CAPABLE = all(fn in os.supports_dir_fd for fn in (os.open, os.mkdir))
_AT_EMPTY_PATH = 0x1000
_O_TMPFILE = getattr(os, "O_TMPFILE", 0)
_LIBC = ctypes.CDLL(None, use_errno=True)
_LINKAT = getattr(_LIBC, "linkat", None)
if _LINKAT is not None:
    _LINKAT.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int)
    _LINKAT.restype = ctypes.c_int


def _require_descriptor_custody() -> None:
    if (not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY") or not _DIR_FD_CAPABLE
            or not _O_TMPFILE or _LINKAT is None):
        raise ManifestError("platform lacks descriptor-anchored production filesystem custody")


def _link_staged_inode(staged_fd: int, parent_fd: int, destination: str) -> None:
    """Publish the descriptor-bound unnamed inode, never a replaceable source name."""
    assert _LINKAT is not None
    result = _LINKAT(staged_fd, ctypes.c_char_p(b""), parent_fd,
                     ctypes.c_char_p(os.fsencode(destination)), _AT_EMPTY_PATH)
    if result != 0:
        error = ctypes.get_errno()
        if error == errno.EEXIST:
            raise FileExistsError(error, os.strerror(error), destination)
        raise OSError(error, os.strerror(error), destination)


def _read_and_identify_at(parent_fd: int, name: str, maximum_size: int) -> tuple[bytes, tuple[int, int]]:
    descriptor = _open_regular_at(parent_fd, name, "published catalog")
    try:
        info = os.fstat(descriptor)
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            payload = stream.read(maximum_size + 1)
        return payload, (info.st_dev, info.st_ino)
    finally:
        os.close(descriptor)


def _open_directory(path: Path) -> int:
    """Open an absolute directory chain without trusting a previously checked path."""
    _require_descriptor_custody()
    absolute = Path(os.path.abspath(path))
    descriptor = os.open(absolute.anchor, _DIR_FLAGS)
    try:
        for component in absolute.parts[1:]:
            child = os.open(component, _DIR_FLAGS, dir_fd=descriptor)
            if not stat.S_ISDIR(os.fstat(child).st_mode):
                os.close(child)
                raise ManifestError("curator custody path component is not a directory")
            os.close(descriptor)
            descriptor = child
        return descriptor
    except (OSError, ManifestError) as exc:
        os.close(descriptor)
        if isinstance(exc, ManifestError):
            raise
        raise ManifestError("curator custody directory walk failed") from exc


def _open_regular_at(parent_fd: int, name: str, label: str) -> int:
    try:
        descriptor = os.open(name, _FILE_FLAGS, dir_fd=parent_fd)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            os.close(descriptor)
            raise ManifestError(f"curator evidence {label} must be a non-symlink regular file")
        return descriptor
    except OSError as exc:
        raise ManifestError(f"curator evidence {label} is unreadable") from exc


def _read_regular_file(path: Path, label: str, *, maximum_size: int) -> bytes:
    """Read one bounded input relative to its descriptor-pinned parent."""
    parent_fd = _open_directory(path.parent)
    try:
        descriptor = _open_regular_at(parent_fd, path.name, label)
        opened = os.fstat(descriptor)
        if opened.st_size > maximum_size:
            os.close(descriptor)
            raise ManifestError(f"curator evidence {label} must be a bounded regular file")
        with os.fdopen(descriptor, "rb") as stream:
            payload = stream.read(maximum_size + 1)
    finally:
        os.close(parent_fd)
    if len(payload) > maximum_size:
        raise ManifestError(f"curator evidence {label} exceeds its size limit")
    return payload


def _read_json_evidence(path: Path, label: str, *, maximum_size: int) -> Any:
    try:
        return json.loads(_read_regular_file(path, label, maximum_size=maximum_size).decode("utf-8", errors="strict"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"{label} is invalid") from exc


def _read_at(parent_fd: int, name: str, label: str, maximum_size: int) -> bytes:
    descriptor = _open_regular_at(parent_fd, name, label)
    try:
        if os.fstat(descriptor).st_size > maximum_size:
            raise ManifestError(f"curator evidence {label} exceeds its size limit")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            payload = stream.read(maximum_size + 1)
    finally:
        os.close(descriptor)
    if len(payload) > maximum_size:
        raise ManifestError(f"curator evidence {label} exceeds its size limit")
    return payload


def _read_checksum_sidecar(parent_fd: int, name: str, artifact_name: str) -> str:
    try:
        descriptor = _open_regular_at(parent_fd, name, "checksum sidecar")
        with os.fdopen(descriptor, "rb") as stream:
            raw = stream.read(_SIDECAR_MAXIMUM_SIZE + 1)
        if len(raw) > _SIDECAR_MAXIMUM_SIZE:
            raise ManifestError("escrow checksum sidecar exceeds its size limit")
        lines = raw.decode("ascii", errors="strict").splitlines()
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


def _hash(parent_fd: int, name: str) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    descriptor = _open_regular_at(parent_fd, name, "GGUF artifact")
    with os.fdopen(descriptor, "rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            size += len(chunk)
            digest.update(chunk)
    return digest.hexdigest(), size


def promote_manifest(manifest_path: Path) -> dict[str, Any]:
    """Prove every curator-held byte record before discarding local path identity."""
    manifest_data = _read_json_evidence(manifest_path, "curator manifest", maximum_size=4 * 1024 * 1024)
    validate_manifest_data(manifest_data, verify_artifacts=False)
    data = cast(dict[str, Any], manifest_data)
    if data.get("schema_version") != V2_SCHEMA_VERSION:
        raise ManifestError("production promotion requires sentientos.model_manifest:v2")
    promoted: list[dict[str, Any]] = []
    for entry in data["models"]:
        artifact = entry["artifact"]
        artifact_path = Path(artifact["escrow_path"])
        root = artifact_path.parent
        escrow_fd = _open_directory(root)
        try:
            # All evidence is opened from this one pinned escrow directory.
            for name, label in (("LICENSE.txt", "LICENSE.txt"), ("MODEL_CARD.md", "MODEL_CARD.md")):
                evidence_fd = _open_regular_at(escrow_fd, name, label)
                os.close(evidence_fd)
            digest, size = _hash(escrow_fd, artifact_path.name)
            if digest != artifact.get("sha256") or size != artifact.get("size_bytes"):
                raise ManifestError("independent escrow artifact identity verification failed")
            if _read_checksum_sidecar(escrow_fd, artifact_path.name + ".sha256", artifact_path.name) != digest:
                raise ManifestError("escrow checksum sidecar does not match the GGUF and manifest")
            try:
                source_data = json.loads(_read_at(escrow_fd, "SOURCE.json", "SOURCE.json", 256 * 1024).decode("utf-8", errors="strict"))
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise ManifestError("SOURCE.json is invalid") from exc
        finally:
            os.close(escrow_fd)
        if not isinstance(source_data, Mapping):
            raise ManifestError("SOURCE.json is invalid")
        source: Mapping[str, Any] = source_data
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
        return cast(dict[str, Any], validate_local_model_catalog(catalog))
    except LocalModelCatalogError as exc:
        raise ManifestError(f"promoted catalog is invalid: {exc}") from exc


def _revalidate_chain(identities: list[tuple[Path, tuple[int, int]]]) -> None:
    """Check visible names still identify pinned directories; never use them for I/O."""
    for path, identity in identities:
        try:
            info = path.lstat()
        except OSError as exc:
            raise ManifestError("catalog publication path custody changed") from exc
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or (info.st_dev, info.st_ino) != identity:
            raise ManifestError("catalog publication path custody changed")


def _prepare_publication_parent(output_path: Path) -> tuple[int, list[tuple[Path, tuple[int, int]]]]:
    """Create and descend solely relative to already-open directory descriptors."""
    _require_descriptor_custody()
    parent = Path(os.path.abspath(output_path)).parent
    anchor = Path(parent.anchor)
    descriptor = os.open(anchor, _DIR_FLAGS)
    identities = [(anchor, (os.fstat(descriptor).st_dev, os.fstat(descriptor).st_ino))]
    current = anchor
    try:
      for part in parent.parts[1:]:
        current = current / part
        try:
            child = os.open(part, _DIR_FLAGS, dir_fd=descriptor)
        except FileNotFoundError:
            _revalidate_chain(identities)
            try:
                os.mkdir(part, mode=0o700, dir_fd=descriptor)
            except FileExistsError:
                pass
            child = os.open(part, _DIR_FLAGS, dir_fd=descriptor)
        info = os.fstat(child)
        if not stat.S_ISDIR(info.st_mode):
            os.close(child)
            raise ManifestError("catalog publication ancestor is not a directory")
        os.close(descriptor)
        descriptor = child
        identities.append((current, (info.st_dev, info.st_ino)))
      _revalidate_chain(identities)
      return descriptor, identities
    except (OSError, ManifestError) as exc:
      os.close(descriptor)
      if isinstance(exc, ManifestError):
          raise
      raise ManifestError("catalog publication directory custody failed") from exc


def write_promoted_catalog(manifest_path: Path, output_path: Path) -> dict[str, Any]:
    """Atomically publish deterministic JSON, accepting only identical existing bytes."""
    catalog = promote_manifest(manifest_path)
    payload = (json.dumps(catalog, indent=2, sort_keys=True) + "\n").encode("utf-8")
    output_path = Path(os.path.abspath(output_path))
    parent_fd, identities = _prepare_publication_parent(output_path)
    # O_TMPFILE creates no staging directory entry for a writable-directory actor
    # to substitute.  linkat(AT_EMPTY_PATH) below consumes this opened inode.
    try:
        fd = os.open(".", os.O_RDWR | _O_TMPFILE, 0o600, dir_fd=parent_fd)
    except OSError as exc:
        os.close(parent_fd)
        raise ManifestError("platform/filesystem lacks fd-bound catalog publication") from exc
    try:
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        staged = os.fstat(fd)
        if not stat.S_ISREG(staged.st_mode):
            raise ManifestError("staged catalog is not a regular inode")
        staged_identity = (staged.st_dev, staged.st_ino)
        _revalidate_chain(identities)
        try:
            _link_staged_inode(fd, parent_fd, output_path.name)
            _revalidate_chain(identities)
            published, published_identity = _read_and_identify_at(parent_fd, output_path.name, len(payload))
            if published_identity != staged_identity or published != payload:
                raise ManifestError("published catalog does not identify the approved staged inode and bytes")
        except FileExistsError:
            try:
                existing, _ = _read_and_identify_at(parent_fd, output_path.name, len(payload))
            except OSError as exc:
                raise ManifestError("unable to inspect concurrently published catalog") from exc
            if existing != payload:
                raise ManifestError("refusing to overwrite conflicting production catalog")
            _revalidate_chain(identities)
        try:
            os.fsync(parent_fd)
        except OSError as exc:
            # Never unlink by name here: a competitor may have replaced the entry.
            raise ManifestError("catalog publication durability failed; residual entry preserved") from exc
    finally:
        os.close(fd)
        os.close(parent_fd)
    return catalog
