from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List, Sequence

from hf_intake.classifier import HardwareRequirements, classify
from hf_intake.escrow import EscrowedArtifact


class ManifestError(RuntimeError):
    """Raised when manifest generation or validation fails."""


@dataclass
class ManifestModel:
    identifier: str
    escrow: EscrowedArtifact
    requirements: HardwareRequirements
    license_name: str
    priority: int
    base_url: str

    def to_dict(self) -> dict:
        return {
            "id": self.identifier,
            "artifact": {
                "urls": [f"{self.base_url.rstrip('/')}/{self.escrow.artifact_path.name}"],
                "sha256": self.escrow.sha256,
                "size_bytes": self.escrow.size_bytes,
                "escrow_path": str(self.escrow.artifact_path),
            },
            "requirements": {
                "ram_gb_min": self.requirements.ram_gb_min,
                "avx": self.requirements.avx,
                "avx2": self.requirements.avx2,
                "avx512": self.requirements.avx512,
                "gpu": self.requirements.gpu,
                "architecture": self.requirements.architecture,
                "quantization": self.requirements.quantization,
            },
            "priority": self.priority,
            "license": self.license_name,
        }


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
    )


def generate_manifest(escrow_root: Path, manifest_path: Path, manifest_version: str | None = None) -> dict:
    manifest_version = manifest_version or date.today().isoformat()
    models: List[ManifestModel] = []
    for child in sorted(escrow_root.iterdir()):
        if not child.is_dir():
            continue
        models.append(_load_escrow_record(child))

    models_sorted = sorted(models, key=lambda m: (m.priority, m.identifier))
    manifest_dict = {
        "manifest_version": manifest_version,
        "models": [model.to_dict() for model in models_sorted],
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest_dict, indent=2, sort_keys=True), encoding="utf-8")
    return manifest_dict


def validate_manifest(manifest_path: Path) -> None:
    if not manifest_path.exists():
        raise ManifestError(f"Manifest not found: {manifest_path}")

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestError(f"Invalid JSON in manifest: {exc}") from exc

    if not isinstance(data, dict) or "models" not in data or "manifest_version" not in data:
        raise ManifestError("Manifest schema is invalid")

    for entry in data.get("models", []):
        artifact = entry.get("artifact", {})
        escrow_path = artifact.get("escrow_path")
        if not escrow_path:
            raise ManifestError(f"Missing escrow path for model {entry.get('id')}")
        path_obj = Path(escrow_path)
        if not path_obj.exists():
            raise ManifestError(f"Escrow artifact missing on disk: {escrow_path}")
        checksum = artifact.get("sha256")
        if not checksum:
            raise ManifestError(f"Missing checksum for model {entry.get('id')}")
        actual = _sha256_file(path_obj)
        if checksum != actual:
            raise ManifestError(f"Checksum mismatch for {entry.get('id')}")
        urls = artifact.get("urls") or []
        if not urls:
            raise ManifestError(f"Missing artifact URLs for {entry.get('id')}")
        for url in urls:
            lowered = str(url).lower()
            if "huggingface.co" in lowered or lowered.startswith("hf://"):
                raise ManifestError(f"Untrusted URL in manifest for {entry.get('id')}: {url}")

    # deterministic ordering guard
    sorted_models = sorted(data["models"], key=lambda m: (m.get("priority", 0), m.get("id")))
    if data["models"] != sorted_models:
        raise ManifestError("Manifest models are not deterministically sorted")
