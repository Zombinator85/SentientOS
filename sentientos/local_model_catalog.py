"""Portable, metadata-only catalog for curator-approved local model artifacts."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping
from urllib.parse import unquote, urlsplit

from hf_intake.manifest import ManifestError, validate_execution_routes
from sentientos.local_model_source_provenance import (
    is_canonical_source_artifact_filename, is_canonical_source_repository, is_immutable_source_revision,
)

SCHEMA_VERSION = "sentientos.local_model_catalog:v1"
TRUSTED_ARTIFACT_HOSTS = frozenset({"models.sentientos.org"})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class LocalModelCatalogError(ValueError):
    """A portable catalog is malformed or not canonical."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def local_model_catalog_digest(catalog: Mapping[str, Any]) -> str:
    """Digest semantic catalog content; presentation time and a supplied digest are excluded."""
    semantic = {key: value for key, value in catalog.items() if key not in {"generated_at", "local_model_catalog_digest"}}
    return hashlib.sha256(_canonical(semantic)).hexdigest()


def _trusted_url(value: object, filename: str, digest: str) -> str:
    if not isinstance(value, str) or not value:
        raise LocalModelCatalogError("artifact URL is missing or malformed")
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower()
    if (parsed.scheme != "https" or host not in TRUSTED_ARTIFACT_HOSTS or parsed.username is not None
            or parsed.password is not None or parsed.port is not None or parsed.fragment or parsed.query):
        raise LocalModelCatalogError("artifact URL is not an approved HTTPS mirror URL")
    lowered = unquote(value).lower()
    if "latest" in lowered or "huggingface.co" in lowered or "hf.co" in lowered or unquote(parsed.path).split("/")[-1] != filename:
        raise LocalModelCatalogError("artifact URL does not bind the approved content-addressed filename")
    if not filename.endswith(f"-{digest}.gguf"):
        raise LocalModelCatalogError("artifact filename is not content addressed")
    return value


def validate_local_model_catalog(catalog: Mapping[str, Any]) -> dict[str, Any]:
    """Validate only supplied metadata; never inspect artifacts, hardware, runtimes, or networks."""
    if not isinstance(catalog, Mapping) or catalog.get("schema_version") != SCHEMA_VERSION:
        raise LocalModelCatalogError("unsupported local model catalog schema")
    allowed_top = {"schema_version", "models", "generated_at", "local_model_catalog_digest"}
    if set(catalog) - allowed_top:
        raise LocalModelCatalogError("unknown catalog field")
    raw_models = catalog.get("models")
    if not isinstance(raw_models, list) or not raw_models:
        raise LocalModelCatalogError("catalog models must be a non-empty list")
    models: list[dict[str, Any]] = []
    seen: set[str] = set()
    required = {"model_id", "priority", "license_id", "source_repository", "source_revision",
                "source_artifact_filename", "artifact_filename", "artifact_sha256", "artifact_size_bytes",
                "artifact_content_address", "artifact_urls", "requirements", "execution_routes"}
    for raw in raw_models:
        if not isinstance(raw, Mapping) or set(raw) != required:
            raise LocalModelCatalogError("catalog model fields are incomplete or contain forbidden local metadata")
        model = dict(raw)
        model_id, digest = model["model_id"], model["artifact_sha256"]
        if not isinstance(model_id, str) or not model_id or model_id in seen:
            raise LocalModelCatalogError("model_id is missing or duplicated")
        seen.add(model_id)
        if isinstance(model["priority"], bool) or not isinstance(model["priority"], int) or model["priority"] < 0:
            raise LocalModelCatalogError("model priority is invalid")
        if not isinstance(model["license_id"], str) or not model["license_id"].strip():
            raise LocalModelCatalogError("license identity is missing")
        if not is_canonical_source_repository(model["source_repository"]):
            raise LocalModelCatalogError("source repository is malformed")
        if not is_immutable_source_revision(model["source_revision"]):
            raise LocalModelCatalogError("source revision is not an immutable commit identity")
        if not is_canonical_source_artifact_filename(model["source_artifact_filename"]):
            raise LocalModelCatalogError("source artifact filename is invalid")
        if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
            raise LocalModelCatalogError("artifact SHA-256 is malformed")
        filename = model["artifact_filename"]
        if not isinstance(filename, str) or not filename.endswith(f"-{digest}.gguf"):
            raise LocalModelCatalogError("artifact filename/content address mismatch")
        if model["artifact_content_address"] != f"sha256:{digest}":
            raise LocalModelCatalogError("artifact content address mismatch")
        size = model["artifact_size_bytes"]
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise LocalModelCatalogError("artifact size is invalid")
        urls = model["artifact_urls"]
        if not isinstance(urls, list) or not urls or urls != sorted(set(urls)):
            raise LocalModelCatalogError("artifact URLs are missing, duplicated, or unsorted")
        model["artifact_urls"] = [_trusted_url(url, filename, digest) for url in urls]
        req = model["requirements"]
        if not isinstance(req, Mapping) or set(req) != {"architecture", "ram_gb_min", "avx", "avx2", "avx512", "quantization"}:
            raise LocalModelCatalogError("model requirements are invalid or ambiguous")
        if not isinstance(req["architecture"], str) or not req["architecture"] or not isinstance(req["quantization"], str) or not req["quantization"]:
            raise LocalModelCatalogError("architecture or quantization is missing")
        if isinstance(req["ram_gb_min"], bool) or not isinstance(req["ram_gb_min"], int) or req["ram_gb_min"] < 0:
            raise LocalModelCatalogError("RAM requirement is invalid")
        if any(not isinstance(req[key], bool) for key in ("avx", "avx2", "avx512")):
            raise LocalModelCatalogError("CPU feature requirements are invalid")
        try:
            model["execution_routes"] = validate_execution_routes(model["execution_routes"])
        except ManifestError as exc:
            raise LocalModelCatalogError("execution routes are invalid") from exc
        models.append(model)
    if models != sorted(models, key=lambda item: (item["priority"], item["model_id"])):
        raise LocalModelCatalogError("catalog models are not deterministically sorted")
    normalized: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "models": models}
    if "generated_at" in catalog:
        if not isinstance(catalog["generated_at"], str):
            raise LocalModelCatalogError("generated_at is malformed")
        normalized["generated_at"] = catalog["generated_at"]
    computed = local_model_catalog_digest(normalized)
    supplied = catalog.get("local_model_catalog_digest")
    if supplied is not None and supplied != computed:
        raise LocalModelCatalogError("catalog digest mismatch")
    normalized["local_model_catalog_digest"] = computed
    return normalized
