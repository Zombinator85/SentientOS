from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, List, Mapping, Sequence

from hf_intake.classifier import HardwareRequirements, classify
from hf_intake.escrow import EscrowedArtifact


class ManifestError(RuntimeError):
    """Raised when manifest generation or validation fails."""


V2_SCHEMA_VERSION = "sentientos.model_manifest:v2"
SUPPORTED_ENGINES = frozenset({"llama_cpp"})
SUPPORTED_BACKENDS = frozenset({"cpu", "cuda", "rocm", "metal"})
BACKEND_VENDORS = {"cuda": "nvidia", "rocm": "amd", "metal": "apple"}


def validate_execution_routes(value: object) -> list[dict[str, Any]]:
    """Validate curator-authored v2 routes and return their canonical form."""
    if not isinstance(value, list) or not value:
        raise ManifestError("V2 model execution_routes must be a non-empty list")
    routes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, Mapping):
            raise ManifestError("Execution route must be an object")
        route = dict(raw)
        route_id = route.get("route_id")
        engine = route.get("engine")
        backend = route.get("backend_family")
        priority = route.get("route_priority")
        if not isinstance(route_id, str) or not route_id or route_id in seen:
            raise ManifestError("Execution route_id is missing, malformed, or duplicated")
        seen.add(route_id)
        if engine not in SUPPORTED_ENGINES:
            raise ManifestError(f"Unsupported execution engine: {engine}")
        if backend not in SUPPORTED_BACKENDS:
            raise ManifestError(f"Unsupported backend_family: {backend}")
        if isinstance(priority, bool) or not isinstance(priority, int) or priority < 0:
            raise ManifestError("Invalid route_priority")
        minimum = route.get("min_vram_bytes")
        if minimum is not None and (isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 0):
            raise ManifestError("Invalid min_vram_bytes")
        for key in ("accelerator_vendor", "accelerator_family"):
            if key in route and (not isinstance(route[key], str) or not route[key].strip()):
                raise ManifestError(f"Malformed {key}")
        for key in ("os_families", "architectures"):
            if key in route and (not isinstance(route[key], list) or not route[key] or
                                 any(not isinstance(item, str) or not item for item in route[key])):
                raise ManifestError(f"Malformed {key}")
        if backend == "cpu" and any(key in route for key in ("accelerator_vendor", "accelerator_family", "min_vram_bytes")):
            raise ManifestError("CPU route cannot declare accelerator requirements")
        expected_vendor = BACKEND_VENDORS.get(str(backend))
        if expected_vendor and route.get("accelerator_vendor") != expected_vendor:
            raise ManifestError(f"{backend} route requires accelerator_vendor {expected_vendor}")
        routes.append(route)
    if routes != sorted(routes, key=lambda item: (item["route_priority"], item["route_id"])):
        raise ManifestError("Execution routes are not deterministically sorted")
    return routes


@dataclass
class ManifestModel:
    identifier: str
    escrow: EscrowedArtifact
    requirements: HardwareRequirements
    license_name: str
    priority: int
    base_url: str
    execution_routes: list[dict[str, Any]] | None = None

    def to_dict(self, *, schema_version: str | None = None) -> dict[str, Any]:
        requirements = {
            "ram_gb_min": self.requirements.ram_gb_min,
            "avx": self.requirements.avx,
            "avx2": self.requirements.avx2,
            "avx512": self.requirements.avx512,
            "architecture": self.requirements.architecture,
            "quantization": self.requirements.quantization,
        }
        if schema_version is None:
            requirements["gpu"] = self.requirements.gpu
        result = {
            "id": self.identifier,
            "artifact": {
                "urls": [f"{self.base_url.rstrip('/')}/{self.escrow.artifact_path.name}"],
                "sha256": self.escrow.sha256,
                "size_bytes": self.escrow.size_bytes,
                "escrow_path": str(self.escrow.artifact_path),
            },
            "requirements": requirements,
            "priority": self.priority,
            "license": self.license_name,
        }
        if schema_version == V2_SCHEMA_VERSION:
            result["execution_routes"] = validate_execution_routes(self.execution_routes)
        return result


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_escrow_record(escrow_dir: Path) -> ManifestModel:
    source_path = escrow_dir / "SOURCE.json"
    license_path = escrow_dir / "LICENSE.txt"
    card_path = escrow_dir / "MODEL_CARD.md"

    if not source_path.exists() or not license_path.exists() or not card_path.exists():
        raise ManifestError(f"Incomplete escrow record in {escrow_dir}")

    source = json.loads(source_path.read_text(encoding="utf-8"))
    artifact_path = escrow_dir / source["artifact"]
    checksum_path = artifact_path.with_suffix(artifact_path.suffix + ".sha256")
    if not artifact_path.exists() or not checksum_path.exists():
        raise ManifestError(f"Escrow artifact missing for {escrow_dir}")

    recorded_checksum = checksum_path.read_text(encoding="utf-8").split()[0]
    actual_checksum = _sha256_file(artifact_path)
    if recorded_checksum != actual_checksum:
        raise ManifestError(f"Checksum mismatch for {artifact_path}")

    escrow = EscrowedArtifact(
        model_id=escrow_dir.name,
        artifact_path=artifact_path,
        sha256=actual_checksum,
        size_bytes=artifact_path.stat().st_size,
    )
    requirements = classify(artifact_path, escrow.size_bytes)
    license_name = source.get("license")
    if not license_name:
        raise ManifestError(f"License missing for {escrow_dir}")

    priority = source.get("priority", 1)
    base_url = source.get("base_url", "https://models.sentientos.org")

    identifier = source.get("id") or escrow_dir.name
    return ManifestModel(
        identifier=identifier,
        escrow=escrow,
        requirements=requirements,
        license_name=license_name,
        priority=priority,
        base_url=base_url,
        execution_routes=source.get("execution_routes"),
    )


def generate_manifest(escrow_root: Path, manifest_path: Path, manifest_version: str | None = None,
                      *, schema_version: str | None = None) -> dict[str, Any]:
    if schema_version not in (None, V2_SCHEMA_VERSION):
        raise ManifestError(f"Unsupported manifest schema_version: {schema_version}")
    manifest_version = manifest_version or date.today().isoformat()
    models: List[ManifestModel] = []
    for child in sorted(escrow_root.iterdir()):
        if not child.is_dir():
            continue
        models.append(_load_escrow_record(child))

    models_sorted = sorted(models, key=lambda m: (m.priority, m.identifier))
    manifest_dict = {
        "manifest_version": manifest_version,
        "models": [model.to_dict(schema_version=schema_version) for model in models_sorted],
    }
    if schema_version is not None:
        manifest_dict["schema_version"] = schema_version
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest_dict, indent=2, sort_keys=True), encoding="utf-8")
    return manifest_dict


def validate_manifest_data(data: object, *, verify_artifacts: bool = True) -> None:
    """Validate one already-parsed manifest snapshot.

    ``verify_artifacts=False`` is for callers which provide their own descriptor-
    based artifact custody.  Schema, route, URL, and ordering checks are unchanged.
    """
    if not isinstance(data, dict) or "models" not in data or "manifest_version" not in data:
        raise ManifestError("Manifest schema is invalid")

    schema_version = data.get("schema_version")
    if schema_version not in (None, V2_SCHEMA_VERSION):
        raise ManifestError(f"Unsupported manifest schema_version: {schema_version}")
    for entry in data.get("models", []):
        if not isinstance(entry, dict) or not entry.get("id"):
            raise ManifestError("Manifest model identity is missing")
        requirements = entry.get("requirements")
        if not isinstance(requirements, dict):
            raise ManifestError(f"Missing requirements for model {entry.get('id')}")
        if schema_version == V2_SCHEMA_VERSION:
            if not entry.get("license"):
                raise ManifestError("V2 manifest model license is missing")
            if "gpu" in requirements:
                raise ManifestError("V2 requirements.gpu is ambiguous and forbidden")
            validate_execution_routes(entry.get("execution_routes"))
        artifact = entry.get("artifact", {})
        escrow_path = artifact.get("escrow_path")
        if not escrow_path:
            raise ManifestError(f"Missing escrow path for model {entry.get('id')}")
        if verify_artifacts:
            path_obj = Path(escrow_path)
            if not path_obj.exists():
                raise ManifestError(f"Escrow artifact missing on disk: {escrow_path}")
            actual = _sha256_file(path_obj)
            if artifact.get("sha256") != actual:
                raise ManifestError(f"Checksum mismatch for {entry.get('id')}")
        elif not artifact.get("sha256"):
            raise ManifestError(f"Missing checksum for model {entry.get('id')}")
        urls = artifact.get("urls") or []
        if not urls:
            raise ManifestError(f"Missing artifact URLs for {entry.get('id')}")
        for url in urls:
            lowered = str(url).lower()
            if "huggingface.co" in lowered or lowered.startswith("hf://"):
                raise ManifestError(f"Untrusted URL in manifest for {entry.get('id')}: {url}")

    sorted_models = sorted(data["models"], key=lambda m: (m.get("priority", 0), m.get("id")))
    if data["models"] != sorted_models:
        raise ManifestError("Manifest models are not deterministically sorted")


def validate_manifest(manifest_path: Path) -> None:
    if not manifest_path.exists():
        raise ManifestError(f"Manifest not found: {manifest_path}")

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestError(f"Invalid JSON in manifest: {exc}") from exc

    validate_manifest_data(data)
