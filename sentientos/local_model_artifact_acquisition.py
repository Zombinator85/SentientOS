"""Bounded acquisition of one catalog-selected opaque GGUF artifact.

This boundary downloads and escrows exact bytes only.  It never imports a
runtime, parses a GGUF, constructs a model, commissions, or performs inference.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping

from sentientos.exact_artifact_acquisition import (
    ExactArtifactError, StreamResponse, https_transport as exact_https_transport, stream_exact,
)
from sentientos.local_model_catalog import TRUSTED_ARTIFACT_HOSTS, LocalModelCatalogError, validate_local_model_catalog
from sentientos.local_runtime_provisioning import semantic_digest

PLAN_SCHEMA = "sentientos.local_model_artifact_acquisition_plan:v1"
AUTHORIZATION_SCHEMA = "sentientos.local_model_artifact_acquisition_authorization:v1"
RECEIPT_SCHEMA = "sentientos.local_model_artifact_acquisition_receipt:v1"
ACTION = "acquire_exact_local_model_artifact"
SPACE_HEADROOM_BYTES = 64 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024


class ModelArtifactAcquisitionError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


Transport = Callable[[str], StreamResponse]
DiskUsageProvider = Callable[[str | os.PathLike[str]], Any]


def canonical_digest(value: object) -> str:
    return str(semantic_digest(value))


def default_escrow_root() -> Path:
    data = os.environ.get("SENTIENTOS_DATA_DIR")
    return (Path(data) if data else Path.home() / ".sentientos") / "model-artifacts"


def _canonical_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(receipt)
    if value.get("status") == "already_present_verified":
        value["status"] = "model_artifact_acquired_verified"
    claimed = value.pop("receipt_semantic_digest", None)
    if claimed != semantic_digest(value):
        raise ModelArtifactAcquisitionError("model_acquisition_receipt_invalid")
    value["receipt_semantic_digest"] = claimed
    return value


def _validate_semantic(value: Mapping[str, Any], digest_key: str, *, status: str | None = None,
                       error: str) -> dict[str, Any]:
    copy = dict(value)
    claimed = copy.pop(digest_key, None)
    if (status is not None and value.get("status") != status) or claimed != semantic_digest(copy):
        raise ModelArtifactAcquisitionError(error)
    return dict(value)


def _canonical_backend_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(receipt)
    if value.get("status") == "already_verified_current":
        value["status"] = "runtime_backend_verified"
    return _validate_semantic(value, "receipt_semantic_digest", status="runtime_backend_verified",
                              error="backend_verification_receipt_invalid")


def compose_acquisition_plan(selection: Mapping[str, Any], runtime_provisioning: Mapping[str, Any],
        backend_receipt: Mapping[str, Any], catalog: Mapping[str, Any], escrow_root: Path | str) -> dict[str, Any]:
    """Reconstruct one coherent catalog/selection/provisioning/backend contract."""
    try:
        normalized = validate_local_model_catalog(catalog)
    except (LocalModelCatalogError, TypeError, ValueError) as exc:
        raise ModelArtifactAcquisitionError("local_model_catalog_invalid") from exc
    selected_plan = _validate_semantic(selection, "plan_digest", status="selected",
                                       error="local_model_selection_invalid")
    provision = _validate_semantic(runtime_provisioning, "provisioning_plan_digest", status="selected",
                                   error="runtime_provisioning_invalid")
    backend = _canonical_backend_receipt(backend_receipt)
    selected = selected_plan.get("selected")
    if not isinstance(selected, Mapping):
        raise ModelArtifactAcquisitionError("local_model_selection_invalid")
    models = [m for m in normalized["models"] if m["model_id"] == selected.get("model_id")]
    if len(models) != 1:
        raise ModelArtifactAcquisitionError("selected_model_not_in_catalog")
    model = models[0]
    routes = [r for r in model["execution_routes"] if r["route_id"] == selected.get("route_id")]
    if len(routes) != 1:
        raise ModelArtifactAcquisitionError("selected_route_not_in_catalog")
    route = routes[0]
    requirement = selected.get("runtime_requirement")
    catalog_identity = {
        "artifact_sha256": model["artifact_sha256"], "artifact_size_bytes": model["artifact_size_bytes"],
        "artifact_filename": model["artifact_filename"], "artifact_content_address": model["artifact_content_address"],
        "artifact_urls": tuple(model["artifact_urls"]),
    }
    if (selected_plan.get("local_model_catalog_digest") != normalized["local_model_catalog_digest"] or
            any(selected.get(k) != v for k, v in catalog_identity.items()) or
            any(selected.get(k) != route.get(k) for k in ("route_id", "engine", "backend_family", "route_priority")) or
            requirement != {"engine": route["engine"], "backend_family": route["backend_family"]}):
        raise ModelArtifactAcquisitionError("selection_catalog_binding_mismatch")
    selection_digest = selected_plan["plan_digest"]
    shared = {
        "selection_plan_digest": selection_digest, "selected_model_id": model["model_id"],
        "selected_model_artifact_sha256": model["artifact_sha256"], "selected_route_id": route["route_id"],
        "engine": route["engine"], "backend_family": route["backend_family"],
    }
    if any(provision.get(k) != v for k, v in shared.items()):
        raise ModelArtifactAcquisitionError("selection_provisioning_binding_mismatch")
    backend_expected = {
        "runtime_provisioning_plan_digest": provision["provisioning_plan_digest"],
        "runtime_id": provision["runtime_id"], "engine": provision["engine"],
        "backend_family": provision["backend_family"],
    }
    if (backend.get("selected_backend_verified") is not True or
            backend.get("backend_runtime_visibility_verified") is not True or
            any(backend.get(k) != v for k, v in backend_expected.items())):
        raise ModelArtifactAcquisitionError("provisioning_backend_binding_mismatch")
    urls = model["artifact_urls"]
    if len(urls) != 1:
        raise ModelArtifactAcquisitionError("model_artifact_source_ambiguous")
    root = Path(escrow_root).expanduser().absolute()
    value = {
        "schema_version": PLAN_SCHEMA, "status": "model_artifact_acquisition_planned",
        "local_model_catalog_schema_version": normalized["schema_version"],
        "local_model_catalog_digest": normalized["local_model_catalog_digest"],
        "selection_plan_digest": selection_digest, "model_id": model["model_id"],
        "artifact_id": model["artifact_content_address"], "route_id": route["route_id"],
        "engine": route["engine"], "backend_family": route["backend_family"],
        "runtime_id": provision["runtime_id"], "runtime_provisioning_plan_digest": provision["provisioning_plan_digest"],
        "runtime_backend_verification_receipt_digest": backend["receipt_semantic_digest"],
        "artifact_filename": model["artifact_filename"], "artifact_sha256": model["artifact_sha256"],
        "artifact_size_bytes": model["artifact_size_bytes"], "canonical_source_url": urls[0],
        "source_policy": "production_local_model_catalog_exact_mirror_v1",
        "trusted_initial_hosts": sorted(TRUSTED_ARTIFACT_HOSTS),
        "trusted_redirect_hosts": sorted(TRUSTED_ARTIFACT_HOSTS),
        "escrow_root": str(root), "final_relative_escrow_path": str(Path("sha256") / model["artifact_sha256"]),
        "network_effect": "one_bounded_https_exact_artifact_stream",
        "filesystem_effect": "private_staging_and_atomic_content_addressed_model_escrow",
        "runtime_installation_performed": False, "runtime_import_performed": False,
        "backend_probe_performed": False, "gguf_compatibility_verified": False, "model_loaded": False,
        "model_commissioned": False, "inference_performed": False, "inference_authority_granted": False,
        "prompt_assembly_performed": False, "provider_invoked": False,
    }
    value["acquisition_plan_digest"] = semantic_digest(value)
    return value


def authorization_for(plan: Mapping[str, Any], *, operator_confirmed: bool) -> dict[str, Any]:
    value = {"schema_version": AUTHORIZATION_SCHEMA, "action": ACTION,
             "acquisition_plan_digest": plan.get("acquisition_plan_digest"),
             "artifact_id": plan.get("artifact_id"), "route_id": plan.get("route_id"),
             "canonical_source_url": plan.get("canonical_source_url"), "escrow_root": plan.get("escrow_root"),
             "operator_confirmed": operator_confirmed}
    value["authorization_digest"] = semantic_digest(value)
    return value


def _safe_path(path: Path, *, allow_missing: bool) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try: info = current.lstat()
        except FileNotFoundError:
            if allow_missing: continue
            raise ModelArtifactAcquisitionError("unsafe_model_escrow_path")
        if current.is_symlink() or (current != path and not current.is_dir()):
            raise ModelArtifactAcquisitionError("unsafe_model_escrow_path")


def _hash_file(path: Path) -> tuple[int, str]:
    digest, size = hashlib.sha256(), 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""):
            size += len(chunk); digest.update(chunk)
    return size, digest.hexdigest()


def _existing(final: Path, plan: Mapping[str, Any]) -> dict[str, Any] | None:
    if not final.exists(): return None
    _safe_path(final, allow_missing=False)
    artifact, receipt_path = final / str(plan["artifact_filename"]), final / "acquisition-receipt.json"
    if ({p.name for p in final.iterdir()} != {artifact.name, receipt_path.name} or
            any(p.is_symlink() or not p.is_file() for p in (artifact, receipt_path))):
        raise ModelArtifactAcquisitionError("existing_model_escrow_conflict")
    try:
        size, digest = _hash_file(artifact)
        receipt = _canonical_receipt(json.loads(receipt_path.read_text(encoding="utf-8")))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ModelArtifactAcquisitionError("existing_model_escrow_conflict") from exc
    if (size != plan["artifact_size_bytes"] or digest != plan["artifact_sha256"] or
            receipt.get("acquisition_plan_digest") != plan["acquisition_plan_digest"]):
        raise ModelArtifactAcquisitionError("existing_model_escrow_conflict")
    return {**receipt, "status": "already_present_verified", "cache_hit": True,
            "network_performed": False, "host_mutation_performed": False}


def acquire_model_artifact(plan: Mapping[str, Any], *, authorization: Mapping[str, Any] | None = None,
        execute: bool = False, transport: Transport | None = None,
        disk_usage_provider: DiskUsageProvider = shutil.disk_usage) -> dict[str, Any]:
    copy = dict(plan); claimed = copy.pop("acquisition_plan_digest", None)
    if plan.get("schema_version") != PLAN_SCHEMA or plan.get("status") != "model_artifact_acquisition_planned" or claimed != semantic_digest(copy):
        raise ModelArtifactAcquisitionError("model_acquisition_plan_invalid")
    root = Path(str(plan["escrow_root"])); _safe_path(root, allow_missing=True)
    final = root / str(plan["final_relative_escrow_path"])
    existing = _existing(final, plan)
    if existing is not None: return existing
    inspection = {"status": "inspection_ready", "acquisition_plan_digest": claimed,
        "artifact_id": plan["artifact_id"], "final_relative_escrow_path": plan["final_relative_escrow_path"],
        "network_performed": False, "host_mutation_performed": False}
    if not execute: return inspection
    expected_auth = authorization_for(plan, operator_confirmed=True)
    if authorization is None or dict(authorization) != expected_auth:
        raise ModelArtifactAcquisitionError("model_acquisition_authorization_invalid")
    ancestor = root
    while not ancestor.exists(): ancestor = ancestor.parent
    if disk_usage_provider(ancestor).free < int(plan["artifact_size_bytes"]) + SPACE_HEADROOM_BYTES:
        raise ModelArtifactAcquisitionError("insufficient_model_escrow_space")
    root.mkdir(mode=0o700, parents=True, exist_ok=True); (root / "sha256").mkdir(mode=0o700, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".model-acquire-", dir=root))
    artifact = staging / str(plan["artifact_filename"]); response: StreamResponse | None = None
    try:
        if transport is None:
            transport = lambda url: exact_https_transport(url, initial_hosts=frozenset(plan["trusted_initial_hosts"]),
                redirect_hosts=frozenset(plan["trusted_redirect_hosts"]), max_redirects=5, timeout=30.0)
        response = transport(str(plan["canonical_source_url"]))
        with artifact.open("xb", buffering=0) as output:
            os.chmod(artifact, 0o600)
            try:
                observed, digest = stream_exact(response, output, expected_size=int(plan["artifact_size_bytes"]),
                    expected_sha256=str(plan["artifact_sha256"]), size_error="model_artifact_size_mismatch",
                    hash_error="model_artifact_hash_mismatch")
            except ExactArtifactError as exc: raise ModelArtifactAcquisitionError(exc.code) from exc
            os.fsync(output.fileno())
        receipt = {"schema_version": RECEIPT_SCHEMA, "status": "model_artifact_acquired_verified",
            **{k: plan[k] for k in ("acquisition_plan_digest", "local_model_catalog_digest", "selection_plan_digest",
                "model_id", "artifact_id", "route_id", "engine", "backend_family", "runtime_id",
                "runtime_provisioning_plan_digest", "runtime_backend_verification_receipt_digest",
                "artifact_filename", "artifact_sha256", "artifact_size_bytes", "canonical_source_url",
                "source_policy", "final_relative_escrow_path")},
            "authorization_digest": expected_auth["authorization_digest"], "observed_artifact_sha256": digest,
            "observed_artifact_size_bytes": observed, "observed_transport_hosts": list(response.destination_hosts),
            "redirect_count": response.redirect_count, "artifact_verified": True, "cache_hit": False,
            "network_performed": True, "host_mutation_performed": True,
            "runtime_installation_performed": False, "runtime_import_performed": False,
            "backend_probe_performed": False, "gguf_compatibility_verified": False, "model_loaded": False,
            "model_commissioned": False, "inference_performed": False, "inference_authority_granted": False,
            "prompt_assembly_performed": False, "provider_invoked": False}
        receipt["receipt_semantic_digest"] = semantic_digest(receipt)
        receipt_path = staging / "acquisition-receipt.json"
        receipt_path.write_text(json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        os.chmod(receipt_path, 0o600)
        with receipt_path.open("rb") as stream: os.fsync(stream.fileno())
        fd = os.open(staging, os.O_RDONLY); os.fsync(fd); os.close(fd)
        try: staging.rename(final)
        except OSError:
            winner = _existing(final, plan) if final.exists() else None
            if winner is None: raise
            return winner
        return receipt
    finally:
        if response is not None:
            try: response.stream.close()
            except Exception: pass
        if staging.exists(): shutil.rmtree(staging)


def verify_acquisition_receipt(receipt: Mapping[str, Any], plan: Mapping[str, Any]) -> bool:
    canonical = _canonical_receipt(receipt)
    return (canonical.get("schema_version") == RECEIPT_SCHEMA and canonical.get("artifact_verified") is True and
            canonical.get("acquisition_plan_digest") == plan.get("acquisition_plan_digest") and
            canonical.get("model_loaded") is False and canonical.get("inference_authority_granted") is False)
