"""Deterministic, metadata-only local model selection planning."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from hf_intake.manifest import ManifestError, validate_manifest
from sentientos.host_inventory import HostInventoryManifest

SCHEMA_VERSION = "sentientos.local_model_selection:v1"
PROFILE_SCHEMA_VERSION = "sentientos.local_inference_hardware_profile:v1"
GIB = 1024**3
UNKNOWN = "unknown"


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _feature(value: object) -> bool | str:
    return value if isinstance(value, bool) else UNKNOWN


@dataclass(frozen=True)
class LocalInferenceHardwareProfile:
    source_inventory_id: str
    source_inventory_digest: str
    os_family: str
    architecture: str
    total_ram_bytes: int | None
    available_storage_bytes: int | None = None
    avx: bool | str = UNKNOWN
    avx2: bool | str = UNKNOWN
    avx512: bool | str = UNKNOWN
    accelerator_observed: bool | str = UNKNOWN
    accelerator_vendor: str | None = None
    accelerator_family: str | None = None
    vram_bytes: int | None = None
    backend_family: str | None = None
    missing_fact_codes: tuple[str, ...] = ()
    warning_codes: tuple[str, ...] = ()
    schema_version: str = PROFILE_SCHEMA_VERSION
    metadata_only: bool = True
    no_authority: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())


def hardware_profile_from_inventory(inventory: HostInventoryManifest) -> LocalInferenceHardwareProfile:
    """Adapt supplied inventory facts without probing or brand/model inference."""
    cpu, gpu, ram, disk = inventory.cpu_summary, inventory.gpu_summary, inventory.ram_summary, inventory.disk_summary
    total = ram.get("total_bytes") if isinstance(ram.get("total_bytes"), int) and ram["total_bytes"] >= 0 else None
    storage = disk.get("available_bytes", disk.get("cwd_free_bytes"))
    storage = storage if isinstance(storage, int) and storage >= 0 else None
    observed = gpu.get("observed", gpu.get("present"))
    if not isinstance(observed, bool):
        gpu_devices = [device for device in inventory.devices if device.kind == "gpu"]
        observed = True if gpu_devices else UNKNOWN
    missing: list[str] = []
    facts = {"architecture": inventory.architecture if inventory.architecture and inventory.architecture != UNKNOWN else None,
             "ram": total, "avx": _feature(cpu.get("avx")), "avx2": _feature(cpu.get("avx2")),
             "avx512": _feature(cpu.get("avx512")), "accelerator": observed,
             "accelerator_backend": gpu.get("backend_family"), "vram": gpu.get("vram_bytes")}
    for name, value in facts.items():
        if value is None or value == UNKNOWN:
            missing.append(f"{name}_unknown")
    return LocalInferenceHardwareProfile(
        source_inventory_id=inventory.manifest_id,
        source_inventory_digest=_digest(inventory.to_dict()),
        os_family=inventory.os_family or UNKNOWN,
        architecture=inventory.architecture or UNKNOWN,
        total_ram_bytes=total,
        available_storage_bytes=storage,
        avx=facts["avx"], avx2=facts["avx2"], avx512=facts["avx512"],
        accelerator_observed=observed,
        accelerator_vendor=str(gpu["vendor"]) if gpu.get("vendor") else None,
        accelerator_family=str(gpu["family"]) if gpu.get("family") else None,
        vram_bytes=gpu.get("vram_bytes") if isinstance(gpu.get("vram_bytes"), int) else None,
        backend_family=str(gpu["backend_family"]) if gpu.get("backend_family") else None,
        missing_fact_codes=tuple(sorted(missing)), warning_codes=tuple(sorted(inventory.warning_risk_codes)),
    )


def _architecture(value: object) -> str:
    normalized = str(value or UNKNOWN).lower()
    return {"amd64": "x86_64", "aarch64": "arm64"}.get(normalized, normalized)


def _normalize(entry: Mapping[str, Any]) -> dict[str, Any]:
    artifact, requirements = entry["artifact"], entry["requirements"]
    if not isinstance(artifact, Mapping) or not isinstance(requirements, Mapping):
        raise ValueError("invalid sections")
    model_id, sha, path = entry["id"], artifact["sha256"], artifact["escrow_path"]
    if not all(isinstance(item, str) and item for item in (model_id, sha, path)) or len(sha) != 64:
        raise ValueError("invalid identity")
    if not isinstance(entry.get("priority", 0), int) or not isinstance(artifact.get("size_bytes"), int):
        raise ValueError("invalid numeric metadata")
    for key in ("avx", "avx2", "avx512", "gpu"):
        if key in requirements and not isinstance(requirements.get(key), bool):
            raise ValueError("invalid boolean requirement")
    if not isinstance(requirements.get("ram_gb_min"), int) or requirements["ram_gb_min"] < 0:
        raise ValueError("invalid RAM requirement")
    return {"model_id": model_id, "priority": entry.get("priority", 0), "artifact_sha256": sha,
            "artifact_size_bytes": artifact["size_bytes"], "escrow_path": path,
            "urls": tuple(str(url) for url in artifact.get("urls", ())), "license": str(entry.get("license", "")),
            "requirements": {"architecture": str(requirements.get("architecture", UNKNOWN)),
                             "ram_gb_min": requirements["ram_gb_min"], "avx": requirements.get("avx", False),
                             "avx2": requirements.get("avx2", False), "avx512": requirements.get("avx512", False),
                             "gpu": requirements.get("gpu", False), "quantization": str(requirements.get("quantization", ""))}}


def _evaluate(candidate: dict[str, Any], host: LocalInferenceHardwareProfile) -> dict[str, Any]:
    req = candidate["requirements"]
    incompatible: list[str] = []
    unresolved: list[str] = []
    required_arch, host_arch = _architecture(req["architecture"]), _architecture(host.architecture)
    if required_arch != UNKNOWN:
        if host_arch == UNKNOWN: unresolved.append("architecture_unknown")
        elif required_arch != host_arch: incompatible.append("architecture_mismatch")
    if req["ram_gb_min"]:
        if host.total_ram_bytes is None: unresolved.append("ram_unknown")
        elif host.total_ram_bytes < req["ram_gb_min"] * GIB: incompatible.append("insufficient_ram")
    for name in ("avx", "avx2", "avx512"):
        if req[name]:
            value = getattr(host, name)
            if value == UNKNOWN: unresolved.append(f"{name}_unknown")
            elif value is False: incompatible.append(f"{name}_missing")
    if req["gpu"]:
        if host.accelerator_observed is False: incompatible.append("accelerator_missing")
        else: unresolved.append("manifest_accelerator_backend_unspecified")
    state = "ineligible" if incompatible else ("unresolved" if unresolved else "eligible")
    return {**candidate, "state": state, "reason_codes": tuple(sorted(incompatible + unresolved))}


def plan_local_model_selection(host: LocalInferenceHardwareProfile, manifest: Mapping[str, Any], *, manifest_trusted: bool = True) -> dict[str, Any]:
    """Return a deterministic plan. Mapping callers must state trust explicitly."""
    base = {"schema_version": SCHEMA_VERSION, "host_profile_digest": host.digest,
            "no_network_performed": True, "no_download_performed": True, "no_install_performed": True,
            "no_model_load_performed": True, "no_commissioning_performed": True, "no_authority_granted": True}
    try:
        if not manifest_trusted or not isinstance(manifest.get("models"), list) or not manifest.get("manifest_version"):
            raise ValueError("untrusted or malformed manifest")
        candidates = [_normalize(item) for item in manifest["models"] if isinstance(item, Mapping)]
        if len(candidates) != len(manifest["models"]): raise ValueError("invalid entry")
    except (KeyError, TypeError, ValueError):
        plan = {**base, "status": "blocked_manifest_invalid", "selected": None, "manifest_digest": _digest(manifest),
                "eligible_candidates": (), "candidate_summaries": (), "reason_codes": ("manifest_entry_invalid",)}
        plan["plan_digest"] = _digest(plan)
        return plan
    normalized = sorted(candidates, key=lambda item: (item["priority"], item["model_id"]))
    evaluated = [_evaluate(item, host) for item in normalized]
    eligible = [item for item in evaluated if item["state"] == "eligible"]
    selected = eligible[0] if eligible else None
    if selected: status, reasons = "selected", ()
    elif any(item["state"] == "unresolved" for item in evaluated): status, reasons = "blocked_missing_hardware_facts", tuple(sorted({r for item in evaluated for r in item["reason_codes"]}))
    else: status, reasons = "blocked_no_eligible_model", tuple(sorted({r for item in evaluated for r in item["reason_codes"]}))
    plan = {**base, "status": status, "selected": selected, "manifest_digest": _digest({"manifest_version": manifest["manifest_version"], "models": normalized}),
            "eligible_candidates": tuple(eligible), "candidate_summaries": tuple(evaluated), "reason_codes": reasons}
    plan["plan_digest"] = _digest(plan)
    return plan


def plan_local_model_selection_file(host: LocalInferenceHardwareProfile, manifest_path: Path) -> dict[str, Any]:
    try:
        validate_manifest(manifest_path)
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (ManifestError, OSError, json.JSONDecodeError):
        return plan_local_model_selection(host, {}, manifest_trusted=False)
    return plan_local_model_selection(host, data)
