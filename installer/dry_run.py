"""Deterministic installer dry-run utilities."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Mapping

from hf_intake import manifest as manifest_module


class InstallerError(RuntimeError):
    """Raised when a dry-run condition fails."""


@dataclass(frozen=True)
class HardwareProfile:
    ram_gb: int
    avx: bool
    avx2: bool
    avx512: bool


def _load_manifest_models(manifest_path: Path) -> List[dict]:
    manifest_module.validate_manifest(manifest_path)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    models = data.get("models") or []
    if not isinstance(models, list) or not models:
        raise InstallerError("Manifest contains no models")
    return models


def _require_hardware(requirements: Mapping[str, object], hardware: HardwareProfile) -> None:
    ram_required = int(requirements.get("ram_gb_min", 0))
    if hardware.ram_gb < ram_required:
        raise InstallerError(f"Insufficient RAM: requires {ram_required}GB, found {hardware.ram_gb}GB")
    if bool(requirements.get("avx2")) and not hardware.avx2:
        raise InstallerError("AVX2 support required")
    if bool(requirements.get("avx512")) and not hardware.avx512:
        raise InstallerError("AVX-512 support required")


def dry_run_install(
    manifest_path: Path,
    target_dir: Path,
    *,
    hardware: HardwareProfile,
    network_available: bool = True,
    available_bytes: int | None = None,
    fetcher: Callable[[dict], bytes] | None = None,
) -> Path:
    """Simulate an installer run without side effects beyond the target dir.

    The call fails closed on any deviation from the manifest (network outage,
    checksum mismatch, insufficient hardware or disk space).
    """

    models = _load_manifest_models(manifest_path)
    selected = models[0]
    requirements = selected.get("requirements", {})
    _require_hardware(requirements, hardware)

    artifact = selected.get("artifact", {})
    escrow_path = Path(artifact.get("escrow_path", ""))
    size_bytes = int(artifact.get("size_bytes", 0))
    destination = target_dir / escrow_path.name

    if destination.exists():
        existing = destination.read_bytes()
        checksum = hashlib.sha256(existing).hexdigest()
        if checksum != artifact.get("sha256"):
            raise InstallerError("Existing artifact checksum mismatch; clean target directory before retrying")
        if len(existing) < size_bytes:
            raise InstallerError("Existing artifact appears incomplete")
        return destination

    if not network_available:
        raise InstallerError("Network unavailable after manifest fetch")

    if available_bytes is not None and available_bytes < size_bytes:
        raise InstallerError("Insufficient disk space for model download")

    def _default_fetch(entry: dict) -> bytes:
        path = Path(entry.get("artifact", {}).get("escrow_path", ""))
        return path.read_bytes()

    fetch = fetcher or _default_fetch
    try:
        payload = fetch(selected)
    except Exception as exc:  # pragma: no cover - defensive error path
        raise InstallerError(f"Download failed: {exc}") from exc

    if len(payload) < size_bytes:
        raise InstallerError("Partial download detected")
    checksum = hashlib.sha256(payload).hexdigest()
    if checksum != artifact.get("sha256"):
        raise InstallerError("Checksum mismatch for escrowed artifact")

    target_dir.mkdir(parents=True, exist_ok=True)
    try:
        destination.write_bytes(payload)
    except OSError as exc:  # pragma: no cover - disk full path
        raise InstallerError(f"Unable to write artifact: {exc}") from exc

    return destination
