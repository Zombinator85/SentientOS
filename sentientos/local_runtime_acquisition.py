"""Bounded acquisition of one catalog-selected runtime artifact.

This module deliberately stops at verified byte custody.  It has no package
installation, dependency resolution, runtime import, or commissioning authority.
"""
from __future__ import annotations

import hashlib
import builtins
import json
import os
import re
import shutil
import ssl
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urljoin, urlsplit

from sentientos.local_runtime_provisioning import semantic_digest, validate_runtime_catalog
from sentientos.exact_artifact_acquisition import ExactArtifactError, StreamResponse, stream_exact

AUTHORIZATION_SCHEMA = "sentientos.local_runtime_acquisition_authorization:v1"
RECEIPT_SCHEMA = "sentientos.local_runtime_artifact_acquisition_receipt:v1"
ACTION = "acquire_runtime_artifact"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_REDIRECT_HOSTS = frozenset({"github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"})
CHUNK_SIZE = 1024 * 1024


class AcquisitionError(RuntimeError):
    """Machine-readable, fail-closed acquisition failure."""
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


Transport = Callable[[str], StreamResponse]
DiskUsageProvider = Callable[[str | os.PathLike[str]], Any]


def default_escrow_root() -> Path:
    data = os.environ.get("SENTIENTOS_DATA_DIR")
    return (Path(data) if data else Path.home() / ".sentientos") / "runtime-artifacts"


def authorization_for(plan: Mapping[str, Any], escrow_root: Path | str, *, operator_confirmed: bool) -> dict[str, Any]:
    value = {
        "schema_version": AUTHORIZATION_SCHEMA, "action": ACTION,
        "provisioning_plan_digest": plan.get("provisioning_plan_digest"),
        "runtime_catalog_digest": plan.get("runtime_catalog_digest"), "runtime_id": plan.get("runtime_id"),
        "artifact_sha256": plan.get("artifact_sha256"), "artifact_size_bytes": plan.get("artifact_size_bytes"),
        "escrow_root": str(Path(escrow_root).expanduser().absolute()), "operator_confirmed": operator_confirmed,
    }
    value["authorization_digest"] = semantic_digest(value)
    return value


def receipt_semantic_digest(receipt: Mapping[str, Any]) -> str:
    """Hash canonical semantic fields; operational ``retrieved_at`` is excluded."""
    return semantic_digest({k: v for k, v in receipt.items() if k not in {"retrieved_at", "receipt_semantic_digest"}})


def _load_catalog(path: Path | str) -> dict[str, Any]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return validate_runtime_catalog(raw)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise AcquisitionError("invalid_runtime_catalog") from exc


def _validate_filename(filename: str) -> None:
    if not filename or Path(filename).is_absolute() or Path(filename).name != filename or filename in {".", ".."}:
        raise AcquisitionError("invalid_artifact_filename")


def _validate_source(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.hostname != "github.com":
        raise AcquisitionError("untrusted_runtime_source")
    lowered = url.lower()
    if "latest" in lowered or "/simple" in parsed.path.lower() or "pypi" in lowered:
        raise AcquisitionError("untrusted_runtime_source")
    return parsed.hostname


def validate_binding(plan: Mapping[str, Any], catalog_path: Path | str) -> tuple[dict[str, Any], dict[str, Any]]:
    required = ("runtime_id", "runtime_catalog_digest", "provisioning_plan_digest", "engine", "backend_family",
                "backend_variant", "package_name", "package_version", "artifact_filename", "artifact_sha256",
                "artifact_size_bytes", "artifact_urls")
    if not isinstance(plan, Mapping) or any(key not in plan for key in required):
        raise AcquisitionError("invalid_provisioning_plan")
    if plan.get("status") != "selected":
        raise AcquisitionError("provisioning_plan_not_selected")
    without_digest = dict(plan); claimed = without_digest.pop("provisioning_plan_digest", None)
    if claimed != semantic_digest(without_digest):
        raise AcquisitionError("invalid_provisioning_plan")
    catalog = _load_catalog(catalog_path)
    if plan["runtime_catalog_digest"] != catalog["catalog_digest"]:
        raise AcquisitionError("runtime_catalog_digest_mismatch")
    entries = [entry for entry in catalog["runtimes"] if entry["runtime_id"] == plan["runtime_id"]]
    if not entries:
        raise AcquisitionError("runtime_id_not_in_catalog")
    entry = entries[0]
    urls = entry["artifact_urls"]
    if len(urls) != 1:
        raise AcquisitionError("runtime_source_ambiguous")
    identity = ("engine", "backend_family", "backend_variant", "package_name", "package_version",
                "artifact_filename", "artifact_sha256", "artifact_urls")
    if any(plan[key] != entry[key] for key in identity):
        raise AcquisitionError("runtime_artifact_identity_mismatch")
    if plan["artifact_size_bytes"] != entry["artifact_size_bytes"]:
        raise AcquisitionError("runtime_artifact_size_mismatch")
    _validate_filename(entry["artifact_filename"]); _validate_source(urls[0])
    return catalog, entry


def _check_components(path: Path, *, allow_missing: bool) -> None:
    current = Path(path.anchor)
    for component in path.parts[1:] if path.is_absolute() else path.parts:
        current /= component
        try:
            info = current.lstat()
        except FileNotFoundError:
            if allow_missing:
                continue
            raise AcquisitionError("unsafe_escrow_path")
        if os.path.islink(current) or not os.path.isdir(current):
            raise AcquisitionError("unsafe_escrow_path")


def _existing(final: Path, entry: Mapping[str, Any]) -> dict[str, Any] | None:
    if not final.exists():
        return None
    _check_components(final, allow_missing=False)
    expected = {entry["artifact_filename"], "acquisition-receipt.json"}
    if {p.name for p in final.iterdir()} != expected:
        raise AcquisitionError("existing_escrow_conflict")
    artifact, receipt_path = final / entry["artifact_filename"], final / "acquisition-receipt.json"
    for path in (artifact, receipt_path):
        if path.is_symlink() or not path.is_file():
            raise AcquisitionError("existing_escrow_conflict")
    try:
        if artifact.stat().st_size != entry["artifact_size_bytes"]:
            raise AcquisitionError("existing_escrow_conflict")
        digest = hashlib.sha256()
        with builtins.open(artifact, "rb", opener=lambda p, f: os.open(p, f | getattr(os, "O_NOFOLLOW", 0))) as stream:
            for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""): digest.update(chunk)
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise AcquisitionError("existing_escrow_conflict") from exc
    if digest.hexdigest() != entry["artifact_sha256"] or receipt.get("receipt_semantic_digest") != receipt_semantic_digest(receipt):
        raise AcquisitionError("existing_escrow_conflict")
    checks = {"artifact_filename": entry["artifact_filename"], "expected_artifact_sha256": entry["artifact_sha256"],
              "observed_artifact_sha256": entry["artifact_sha256"], "expected_artifact_size_bytes": entry["artifact_size_bytes"],
              "observed_artifact_size_bytes": entry["artifact_size_bytes"], "artifact_verified": True}
    if any(receipt.get(k) != v for k, v in checks.items()):
        raise AcquisitionError("existing_escrow_conflict")
    result = dict(receipt)
    result.update(status="already_present_verified", runtime_artifact_availability_status="already_present_verified",
                  cache_hit=True, network_performed=False, download_performed=False, host_mutation_performed=False)
    return result


def verify_runtime_custody(plan: Mapping[str, Any], *, catalog_path: Path | str,
                           escrow_root: Path | str) -> dict[str, Any]:
    """Revalidate catalog binding, receipt semantics, and escrowed bytes without acquisition authority."""
    _, entry = validate_binding(plan, catalog_path)
    final = Path(escrow_root).expanduser().absolute() / "sha256" / entry["artifact_sha256"]
    result = _existing(final, entry)
    if result is None:
        raise AcquisitionError("runtime_custody_not_verified")
    if (result.get("provisioning_plan_digest") != plan["provisioning_plan_digest"] or
            result.get("runtime_catalog_digest") != plan["runtime_catalog_digest"]):
        raise AcquisitionError("runtime_custody_not_verified")
    return {"receipt": result, "entry": entry,
            "wheel_path": final / entry["artifact_filename"]}


class _RedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, maximum: int):
        self.maximum = maximum
        self.hosts: list[str] = []
        self.count = 0
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> Any:
        url = urljoin(req.full_url, newurl); parsed = urlsplit(url)
        if self.count >= self.maximum: raise AcquisitionError("redirect_limit_exceeded")
        if parsed.scheme != "https": raise AcquisitionError("redirect_https_required")
        if parsed.hostname not in ALLOWED_REDIRECT_HOSTS: raise AcquisitionError("redirect_host_rejected")
        self.count += 1; self.hosts.append(str(parsed.hostname))
        return super().redirect_request(req, fp, code, msg, headers, url)


def https_transport(url: str, *, max_redirects: int = 5, timeout: float = 30.0) -> StreamResponse:
    handler = _RedirectHandler(max_redirects)
    opener = urllib.request.build_opener(handler, urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    try:
        response = opener.open(urllib.request.Request(url, headers={"Accept-Encoding": "identity"}), timeout=timeout)
    except AcquisitionError: raise
    except (OSError, urllib.error.URLError) as exc: raise AcquisitionError("network_error") from exc
    final_host = urlsplit(response.geturl()).hostname
    hosts = tuple(dict.fromkeys(["github.com", *handler.hosts, str(final_host)]))
    return StreamResponse(response, dict(response.headers.items()), hosts, handler.count)


def acquire_runtime_artifact(plan: Mapping[str, Any], *, catalog_path: Path | str, escrow_root: Path | str,
                             authorization: Mapping[str, Any] | None = None, execute: bool = False,
                             transport: Transport = https_transport,
                             disk_usage_provider: DiskUsageProvider = shutil.disk_usage) -> dict[str, Any]:
    """Inspect or acquire the one exact artifact bound by plan and catalog."""
    _, entry = validate_binding(plan, catalog_path)
    root = Path(escrow_root).expanduser().absolute(); _check_components(root, allow_missing=True)
    digest = entry["artifact_sha256"]
    if not SHA256_RE.fullmatch(digest): raise AcquisitionError("invalid_artifact_sha256")
    final = root / "sha256" / digest
    existing = _existing(final, entry)
    if existing is not None: return existing
    relative = str(Path("sha256") / digest)
    inspection = {"status": "inspection_ready", "runtime_id": entry["runtime_id"], "content_address": f"sha256:{digest}",
                  "final_relative_escrow_path": relative, "canonical_source_url": entry["artifact_urls"][0],
                  "network_performed": False, "download_performed": False, "host_mutation_performed": False,
                  "runtime_dependency_custody_ready": False}
    if not execute: return inspection
    expected_auth = authorization_for(plan, root, operator_confirmed=True)
    if authorization is None or dict(authorization) != expected_auth:
        raise AcquisitionError("invalid_acquisition_authorization")
    ancestor = root
    while not ancestor.exists(): ancestor = ancestor.parent
    if disk_usage_provider(ancestor).free < entry["artifact_size_bytes"]:
        raise AcquisitionError("insufficient_escrow_space")
    root.mkdir(mode=0o700, parents=True, exist_ok=True); (root / "sha256").mkdir(mode=0o700, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".acquire-", dir=root)); artifact = staging / entry["artifact_filename"]
    try:
        response = transport(entry["artifact_urls"][0])
        with artifact.open("xb", buffering=0) as output:
            os.chmod(artifact, 0o600)
            try:
                observed, observed_hash = stream_exact(
                    response, output, expected_size=entry["artifact_size_bytes"], expected_sha256=digest,
                    size_error="artifact_size_mismatch", hash_error="artifact_hash_mismatch")
            except ExactArtifactError as exc:
                raise AcquisitionError(exc.code) from exc
            os.fsync(output.fileno())
        try: response.stream.close()
        except Exception: pass
        receipt = {
            "schema_version": RECEIPT_SCHEMA, "status": "acquired_verified", "runtime_id": entry["runtime_id"],
            "engine": entry["engine"], "backend_family": entry["backend_family"], "backend_variant": entry["backend_variant"],
            "package_name": entry["package_name"], "package_version": entry["package_version"],
            "artifact_filename": entry["artifact_filename"], "expected_artifact_sha256": digest,
            "observed_artifact_sha256": observed_hash, "expected_artifact_size_bytes": entry["artifact_size_bytes"],
            "observed_artifact_size_bytes": observed, "content_address": f"sha256:{digest}",
            "final_relative_escrow_path": relative, "canonical_source_url": entry["artifact_urls"][0],
            "sanitized_network_destination_hosts": list(response.destination_hosts), "redirect_count": response.redirect_count,
            "provisioning_plan_digest": plan["provisioning_plan_digest"], "runtime_catalog_digest": plan["runtime_catalog_digest"],
            "authorization_digest": expected_auth["authorization_digest"], "artifact_verified": True, "cache_hit": False,
            "network_performed": True, "download_performed": True, "host_mutation_performed": True,
            "package_install_performed": False, "subprocess_performed": False, "runtime_import_performed": False,
            "model_load_performed": False, "commissioning_performed": False,
            "runtime_execution_authority_granted": False, "runtime_installed": False,
            "runtime_available_for_import": False, "runtime_commissioned": False,
            "runtime_artifact_availability_status": "acquired_verified", "runtime_dependency_custody_ready": False,
        }
        receipt["receipt_semantic_digest"] = receipt_semantic_digest(receipt)
        receipt_path = staging / "acquisition-receipt.json"
        with receipt_path.open("x", encoding="utf-8") as output:
            json.dump(receipt, output, sort_keys=True, separators=(",", ":")); output.write("\n"); output.flush(); os.fsync(output.fileno())
        os.chmod(receipt_path, 0o600)
        directory_fd = os.open(staging, os.O_RDONLY); os.fsync(directory_fd); os.close(directory_fd)
        try: staging.rename(final)
        except OSError:
            # POSIX may report EEXIST or ENOTEMPTY when the peer wins.
            if not final.exists():
                raise
            winner = _existing(final, entry)
            if winner is None: raise AcquisitionError("existing_escrow_conflict")
            return winner
        parent_fd = os.open(final.parent, os.O_RDONLY); os.fsync(parent_fd); os.close(parent_fd)
        return receipt
    except AcquisitionError: raise
    except (OSError, ValueError) as exc: raise AcquisitionError("acquisition_write_error") from exc
    finally:
        if staging.exists(): shutil.rmtree(staging)
