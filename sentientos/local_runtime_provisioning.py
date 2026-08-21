"""Deterministic, metadata-only local runtime provisioning plans."""
from __future__ import annotations

import hashlib
import json
import platform
import re
import sys
import sysconfig
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

CATALOG_SCHEMA_VERSION = "sentientos.local_runtime_catalog:v1"
ENVIRONMENT_SCHEMA_VERSION = "sentientos.local_runtime_environment_profile:v1"
PLAN_SCHEMA_VERSION = "sentientos.local_runtime_provisioning:v1"
ENGINES = frozenset({"llama_cpp"})
BACKENDS = frozenset({"cpu", "cuda", "rocm", "metal"})
VENDORS = {"cuda": "nvidia", "rocm": "amd", "metal": "apple"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
EXACT_VERSION_RE = re.compile(r"^[0-9]+(?:[A-Za-z0-9._+-]*[A-Za-z0-9])?$")


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def semantic_digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def normalize_architecture(value: str) -> str:
    normalized = value.strip().lower()
    return {"amd64": "x86_64", "aarch64": "arm64"}.get(normalized, normalized)


@dataclass(frozen=True)
class LocalRuntimeEnvironmentProfile:
    os_family: str
    architecture: str
    python_implementation: str
    python_major: int
    python_minor: int
    python_abi: str
    source_identity: str
    source_digest: str
    missing_fact_codes: tuple[str, ...] = ()
    schema_version: str = ENVIRONMENT_SCHEMA_VERSION
    metadata_only: bool = True
    no_authority: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def digest(self) -> str:
        return semantic_digest(self.to_dict())


def observe_local_runtime_environment() -> LocalRuntimeEnvironmentProfile:
    """Observe bounded standard-library process facts; perform no probing."""
    facts = {
        "os_family": platform.system().lower(),
        "architecture": normalize_architecture(platform.machine()),
        "python_implementation": platform.python_implementation().lower(),
        "python_major": sys.version_info.major,
        "python_minor": sys.version_info.minor,
        "python_abi": str(sysconfig.get_config_var("SOABI") or ""),
    }
    missing = tuple(sorted(f"{key}_unknown" for key, value in facts.items() if value in (None, "")))
    identity = "current_python_process"
    return LocalRuntimeEnvironmentProfile(
        os_family=str(facts["os_family"]), architecture=str(facts["architecture"]),
        python_implementation=str(facts["python_implementation"]), python_major=sys.version_info.major,
        python_minor=sys.version_info.minor, python_abi=str(facts["python_abi"]), source_identity=identity,
        source_digest=semantic_digest({"source_identity": identity, **facts}), missing_fact_codes=missing)


def environment_profile_from_mapping(value: Mapping[str, Any]) -> LocalRuntimeEnvironmentProfile:
    fields = ("os_family", "architecture", "python_implementation", "python_major", "python_minor",
              "python_abi", "source_identity", "source_digest")
    if any(key not in value for key in fields):
        raise ValueError("missing_environment_field")
    return LocalRuntimeEnvironmentProfile(
        os_family=str(value["os_family"]).lower(), architecture=normalize_architecture(str(value["architecture"])),
        python_implementation=str(value["python_implementation"]).lower(), python_major=int(value["python_major"]),
        python_minor=int(value["python_minor"]), python_abi=str(value["python_abi"]),
        source_identity=str(value["source_identity"]), source_digest=str(value["source_digest"]),
        missing_fact_codes=tuple(sorted(str(item) for item in value.get("missing_fact_codes", ()))),
    )


def _trusted_url(url: object) -> bool:
    if not isinstance(url, str) or not url:
        return False
    parsed = urlsplit(url)
    lowered = url.lower()
    return parsed.scheme == "https" and bool(parsed.netloc) and "latest" not in lowered and \
        "/simple" not in parsed.path.lower() and "search" not in parsed.path.lower()


def validate_runtime_catalog(catalog: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize curator-supplied exact artifact custody."""
    if catalog.get("schema_version") != CATALOG_SCHEMA_VERSION:
        raise ValueError("invalid_catalog_schema")
    raw = catalog.get("runtimes")
    if not isinstance(raw, list) or not raw:
        raise ValueError("empty_runtime_catalog")
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    required_strings = ("runtime_id", "engine", "backend_family", "distribution_kind", "package_name",
                        "package_version", "artifact_filename", "artifact_sha256", "os_family",
                        "architecture", "python_implementation", "python_abi")
    for item in raw:
        if not isinstance(item, Mapping) or any(not isinstance(item.get(key), str) or not item[key] for key in required_strings):
            raise ValueError("invalid_runtime_entry")
        entry = dict(item)
        runtime_id = entry["runtime_id"]
        if runtime_id in seen: raise ValueError("duplicate_runtime_id")
        seen.add(runtime_id)
        if entry["engine"] not in ENGINES or entry["backend_family"] not in BACKENDS:
            raise ValueError("unsupported_runtime_route")
        if entry["distribution_kind"] != "python_wheel": raise ValueError("unsupported_distribution_kind")
        version = entry["package_version"]
        if not EXACT_VERSION_RE.fullmatch(version) or any(token in version.lower() for token in ("latest", "*", ">", "<", "~=")):
            raise ValueError("non_exact_package_version")
        if not SHA256_RE.fullmatch(entry["artifact_sha256"]): raise ValueError("invalid_artifact_sha256")
        urls = entry.get("artifact_urls")
        if not isinstance(urls, (list, tuple)) or not urls or not all(_trusted_url(url) for url in urls):
            raise ValueError("untrusted_artifact_url")
        priority = entry.get("runtime_priority")
        size = entry.get("artifact_size_bytes")
        if isinstance(priority, bool) or not isinstance(priority, int) or priority < 0: raise ValueError("invalid_runtime_priority")
        if size is not None and (isinstance(size, bool) or not isinstance(size, int) or size < 0): raise ValueError("invalid_artifact_size")
        vendor = entry.get("accelerator_vendor")
        expected = VENDORS.get(entry["backend_family"])
        if vendor is not None and (not isinstance(vendor, str) or (expected and vendor.lower() != expected) or (not expected)):
            raise ValueError("backend_vendor_inconsistent")
        prereqs = entry.get("external_prerequisite_codes", ())
        if not isinstance(prereqs, (list, tuple)) or not all(isinstance(code, str) and code for code in prereqs):
            raise ValueError("invalid_external_prerequisites")
        entry.update(artifact_urls=tuple(sorted(set(urls))), architecture=normalize_architecture(entry["architecture"]),
                     os_family=entry["os_family"].lower(), python_implementation=entry["python_implementation"].lower(),
                     external_prerequisite_codes=tuple(sorted(set(prereqs))))
        entries.append(entry)
    entries.sort(key=lambda item: item["runtime_id"])
    normalized = {"schema_version": CATALOG_SCHEMA_VERSION, "runtimes": tuple(entries)}
    normalized["catalog_digest"] = semantic_digest(normalized)
    return normalized


def _base(status: str, reasons: Sequence[str], environment: LocalRuntimeEnvironmentProfile,
          catalog_digest: str | None = None) -> dict[str, Any]:
    return {"schema_version": PLAN_SCHEMA_VERSION, "status": status, "reason_codes": tuple(sorted(reasons)),
        "environment_profile_digest": environment.digest, "runtime_catalog_digest": catalog_digest,
        "runtime_availability_status": "not_evaluated", "runtime_installed": "not_evaluated",
        "runtime_provisioning_executed": False, "network_performed": False, "download_performed": False,
        "package_install_performed": False, "subprocess_performed": False, "model_load_performed": False,
        "commissioning_performed": False, "authority_granted": False}


def plan_local_runtime_provisioning(selection: Mapping[str, Any], environment: LocalRuntimeEnvironmentProfile,
                                     catalog: Mapping[str, Any]) -> dict[str, Any]:
    """Select one exact artifact target; never acquire, install, or inspect it."""
    try:
        selected = selection["selected"]
        requirement = selected["runtime_requirement"]
        if selection.get("status") != "selected" or not isinstance(selected, Mapping) or not isinstance(requirement, Mapping):
            raise ValueError
        identity = (selected["model_id"], selected["artifact_sha256"], selected["route_id"])
        engine, backend = requirement["engine"], requirement["backend_family"]
        if not all(isinstance(value, str) and value for value in identity) or engine not in ENGINES or backend not in BACKENDS:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        plan = _base("blocked_invalid_selection", ("invalid_selected_route",), environment)
        plan["provisioning_plan_digest"] = semantic_digest(plan); return plan
    try:
        normalized = validate_runtime_catalog(catalog)
    except (TypeError, ValueError) as exc:
        plan = _base("blocked_invalid_catalog", (str(exc),), environment)
        plan["provisioning_plan_digest"] = semantic_digest(plan); return plan
    if environment.missing_fact_codes or not all((environment.os_family, environment.architecture,
            environment.python_implementation, environment.python_abi)):
        plan = _base("blocked_missing_environment_facts", environment.missing_fact_codes or ("environment_fact_unknown",),
                     environment, normalized["catalog_digest"])
        plan["provisioning_plan_digest"] = semantic_digest(plan); return plan
    compatible = [entry for entry in normalized["runtimes"] if
        entry["engine"] == engine and entry["backend_family"] == backend and
        entry["os_family"] == environment.os_family.lower() and
        entry["architecture"] == normalize_architecture(environment.architecture) and
        entry["python_implementation"] == environment.python_implementation.lower() and
        entry["python_abi"] == environment.python_abi]
    if not compatible:
        plan = _base("blocked_no_compatible_runtime", ("no_exact_environment_match",), environment, normalized["catalog_digest"])
        plan["provisioning_plan_digest"] = semantic_digest(plan); return plan
    entry = sorted(compatible, key=lambda item: (item["runtime_priority"], item["runtime_id"]))[0]
    plan = _base("selected", (), environment, normalized["catalog_digest"])
    plan.update({"selected_model_id": identity[0], "selected_model_artifact_sha256": identity[1],
        "selected_route_id": identity[2], "selection_plan_digest": selection.get("plan_digest", semantic_digest(selection)),
        "engine": engine, "backend_family": backend, "runtime_id": entry["runtime_id"],
        "distribution_kind": entry["distribution_kind"], "package_name": entry["package_name"],
        "package_version": entry["package_version"], "artifact_filename": entry["artifact_filename"],
        "artifact_sha256": entry["artifact_sha256"], "artifact_urls": entry["artifact_urls"],
        "target_os_family": environment.os_family, "target_architecture": normalize_architecture(environment.architecture),
        "python_implementation": environment.python_implementation, "python_abi": environment.python_abi,
        "external_prerequisite_codes": entry["external_prerequisite_codes"],
        "prerequisite_status": "not_evaluated" if entry["external_prerequisite_codes"] else "not_required"})
    if entry.get("artifact_size_bytes") is not None: plan["artifact_size_bytes"] = entry["artifact_size_bytes"]
    plan["provisioning_plan_digest"] = semantic_digest(plan)
    return plan
