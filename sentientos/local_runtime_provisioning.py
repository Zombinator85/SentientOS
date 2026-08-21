"""Deterministic, metadata-only local runtime provisioning plans."""
from __future__ import annotations

import hashlib
import json
import platform
import re
import sys
import sysconfig
from dataclasses import dataclass
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

CATALOG_SCHEMA_VERSION = "sentientos.local_runtime_catalog:v1"
CATALOG_SCHEMA_VERSION_V2 = "sentientos.local_runtime_catalog:v2"
ENVIRONMENT_SCHEMA_VERSION = "sentientos.local_runtime_environment_profile:v1"
ENVIRONMENT_SCHEMA_VERSION_V2 = "sentientos.local_runtime_environment_profile:v2"
PLAN_SCHEMA_VERSION = "sentientos.local_runtime_provisioning:v1"
ENGINES = frozenset({"llama_cpp"})
BACKENDS = frozenset({"cpu", "cuda", "rocm", "metal"})
VENDORS = {"cuda": "nvidia", "rocm": "amd", "metal": "apple"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
EXACT_VERSION_RE = re.compile(r"^[0-9]+(?:[A-Za-z0-9._+-]*[A-Za-z0-9])?$")
PYTHON_TAG_RE = re.compile(r"^(?:py3|cp(?P<major>[0-9])(?P<minor>[0-9]{2}))$")
MANYLINUX_RE = re.compile(r"^manylinux_(?P<major>[0-9]+)_(?P<minor>[0-9]+)_(?P<arch>x86_64)$")
MACOS_RE = re.compile(r"^macosx_(?P<major>[0-9]+)_(?P<minor>[0-9]+)_(?P<arch>arm64)$")


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
    libc_family: str = ""
    libc_version: str = ""
    macos_version: str = ""

    def to_dict(self) -> dict[str, Any]:
        result = {
            "os_family": self.os_family, "architecture": self.architecture,
            "python_implementation": self.python_implementation, "python_major": self.python_major,
            "python_minor": self.python_minor, "python_abi": self.python_abi,
            "source_identity": self.source_identity, "source_digest": self.source_digest,
            "missing_fact_codes": self.missing_fact_codes, "schema_version": self.schema_version,
            "metadata_only": self.metadata_only, "no_authority": self.no_authority,
        }
        if self.schema_version == ENVIRONMENT_SCHEMA_VERSION_V2:
            result.update(libc_family=self.libc_family, libc_version=self.libc_version,
                          macos_version=self.macos_version)
        return result

    @property
    def digest(self) -> str:
        return semantic_digest(self.to_dict())


def observe_local_runtime_environment() -> LocalRuntimeEnvironmentProfile:
    """Observe bounded standard-library process facts; perform no probing."""
    os_family = platform.system().lower()
    libc_family, libc_version = platform.libc_ver()
    macos_version = platform.mac_ver()[0] if os_family == "darwin" else ""
    facts = {
        "os_family": os_family, "architecture": normalize_architecture(platform.machine()),
        "python_implementation": platform.python_implementation().lower(),
        "python_major": sys.version_info.major, "python_minor": sys.version_info.minor,
        "python_abi": str(sysconfig.get_config_var("SOABI") or ""),
        "libc_family": libc_family.lower(), "libc_version": libc_version,
        "macos_version": macos_version,
    }
    required = ["os_family", "architecture", "python_implementation", "python_abi"]
    if os_family == "linux": required += ["libc_family", "libc_version"]
    if os_family == "darwin": required += ["macos_version"]
    missing = tuple(sorted(f"{key}_unknown" for key in required if not facts[key]))
    identity = "current_python_process"
    return LocalRuntimeEnvironmentProfile(
        os_family=os_family, architecture=str(facts["architecture"]),
        python_implementation=str(facts["python_implementation"]), python_major=sys.version_info.major,
        python_minor=sys.version_info.minor, python_abi=str(facts["python_abi"]), source_identity=identity,
        source_digest=semantic_digest({"source_identity": identity, **facts}), missing_fact_codes=missing,
        schema_version=ENVIRONMENT_SCHEMA_VERSION_V2, libc_family=str(facts["libc_family"]),
        libc_version=str(facts["libc_version"]), macos_version=str(facts["macos_version"]))


def environment_profile_from_mapping(value: Mapping[str, Any]) -> LocalRuntimeEnvironmentProfile:
    fields = ("os_family", "architecture", "python_implementation", "python_major", "python_minor",
              "python_abi", "source_identity", "source_digest")
    if any(key not in value for key in fields):
        raise ValueError("missing_environment_field")
    schema = str(value.get("schema_version", ENVIRONMENT_SCHEMA_VERSION))
    if schema not in (ENVIRONMENT_SCHEMA_VERSION, ENVIRONMENT_SCHEMA_VERSION_V2):
        raise ValueError("invalid_environment_schema")
    return LocalRuntimeEnvironmentProfile(
        os_family=str(value["os_family"]).lower(), architecture=normalize_architecture(str(value["architecture"])),
        python_implementation=str(value["python_implementation"]).lower(), python_major=int(value["python_major"]),
        python_minor=int(value["python_minor"]), python_abi=str(value["python_abi"]),
        source_identity=str(value["source_identity"]), source_digest=str(value["source_digest"]),
        missing_fact_codes=tuple(sorted(str(item) for item in value.get("missing_fact_codes", ()))),
        schema_version=schema, libc_family=str(value.get("libc_family", "")).lower(),
        libc_version=str(value.get("libc_version", "")), macos_version=str(value.get("macos_version", "")))


def _trusted_url(url: object) -> bool:
    if not isinstance(url, str) or not url:
        return False
    parsed = urlsplit(url)
    lowered = url.lower()
    return (parsed.scheme == "https" and bool(parsed.netloc) and "latest" not in lowered
            and "/simple" not in parsed.path.lower() and "search" not in parsed.path.lower())


def _wheel_filename_fields(filename: str) -> tuple[str, str, str, str, str]:
    if not filename.endswith(".whl"):
        raise ValueError("invalid_wheel_filename")
    parts = filename[:-4].split("-")
    if len(parts) != 5:
        raise ValueError("invalid_wheel_filename")
    return tuple(parts)  # type: ignore[return-value]


def _validate_common(entry: dict[str, Any]) -> None:
    if entry["engine"] not in ENGINES or entry["backend_family"] not in BACKENDS:
        raise ValueError("unsupported_runtime_route")
    if entry["distribution_kind"] != "python_wheel":
        raise ValueError("unsupported_distribution_kind")
    version = entry["package_version"]
    if not EXACT_VERSION_RE.fullmatch(version) or any(token in version.lower() for token in ("latest", "*", ">", "<", "~=")):
        raise ValueError("non_exact_package_version")
    if not SHA256_RE.fullmatch(entry["artifact_sha256"]):
        raise ValueError("invalid_artifact_sha256")
    urls = entry.get("artifact_urls")
    if not isinstance(urls, (list, tuple)) or not urls or not all(_trusted_url(url) for url in urls):
        raise ValueError("untrusted_artifact_url")
    priority, size = entry.get("runtime_priority"), entry.get("artifact_size_bytes")
    if isinstance(priority, bool) or not isinstance(priority, int) or priority < 0:
        raise ValueError("invalid_runtime_priority")
    if size is not None and (isinstance(size, bool) or not isinstance(size, int) or size < 0):
        raise ValueError("invalid_artifact_size")
    vendor, expected = entry.get("accelerator_vendor"), VENDORS.get(entry["backend_family"])
    if vendor is not None and (not isinstance(vendor, str) or (expected and vendor.lower() != expected) or not expected):
        raise ValueError("backend_vendor_inconsistent")
    prereqs = entry.get("external_prerequisite_codes", ())
    if not isinstance(prereqs, (list, tuple)) or not all(isinstance(code, str) and code for code in prereqs):
        raise ValueError("invalid_external_prerequisites")
    entry.update(artifact_urls=tuple(sorted(set(urls))),
                 external_prerequisite_codes=tuple(sorted(set(prereqs))))


def validate_runtime_catalog(catalog: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize curator-supplied exact artifact custody."""
    schema = catalog.get("schema_version")
    if schema not in (CATALOG_SCHEMA_VERSION, CATALOG_SCHEMA_VERSION_V2):
        raise ValueError("invalid_catalog_schema")
    raw = catalog.get("runtimes")
    if not isinstance(raw, list) or not raw:
        raise ValueError("empty_runtime_catalog")
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    common = ("runtime_id", "engine", "backend_family", "distribution_kind", "package_name",
              "package_version", "artifact_filename", "artifact_sha256")
    v1 = ("os_family", "architecture", "python_implementation", "python_abi")
    v2 = ("backend_variant", "python_implementation", "python_tag", "abi_tag", "platform_tag")
    for item in raw:
        required = common + (v1 if schema == CATALOG_SCHEMA_VERSION else v2)
        if not isinstance(item, Mapping) or any(not isinstance(item.get(key), str) or not item[key] for key in required):
            raise ValueError("invalid_runtime_entry")
        entry = dict(item)
        if entry["runtime_id"] in seen:
            raise ValueError("duplicate_runtime_id")
        seen.add(entry["runtime_id"])
        _validate_common(entry)
        entry["python_implementation"] = entry["python_implementation"].lower()
        if schema == CATALOG_SCHEMA_VERSION:
            entry.update(architecture=normalize_architecture(entry["architecture"]), os_family=entry["os_family"].lower())
        else:
            versions = entry.get("supported_python_versions")
            if (not isinstance(versions, (list, tuple)) or not versions or
                    not all(isinstance(v, str) and re.fullmatch(r"[0-9]+\.[0-9]+", v) for v in versions)):
                raise ValueError("invalid_supported_python_versions")
            match = PYTHON_TAG_RE.fullmatch(entry["python_tag"])
            if not match:
                raise ValueError("unsupported_python_tag")
            if entry["abi_tag"] != "none" and not re.fullmatch(r"cp[0-9]{3}", entry["abi_tag"]):
                raise ValueError("unsupported_abi_tag")
            distribution, version, python_tag, abi_tag, platform_tag = _wheel_filename_fields(entry["artifact_filename"])
            if distribution.replace("_", "-").lower() != entry["package_name"].replace("_", "-").lower():
                raise ValueError("wheel_distribution_mismatch")
            if version != entry["package_version"]:
                raise ValueError("wheel_version_mismatch")
            if (python_tag, abi_tag, platform_tag) != (entry["python_tag"], entry["abi_tag"], entry["platform_tag"]):
                raise ValueError("wheel_tag_metadata_mismatch")
            entry["supported_python_versions"] = tuple(sorted(set(versions), key=lambda v: tuple(map(int, v.split(".")))))
        entries.append(entry)
    entries.sort(key=lambda item: item["runtime_id"])
    normalized = {"schema_version": schema, "runtimes": tuple(entries)}
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


def _version_tuple(value: str) -> tuple[int, ...] | None:
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", value):
        return None
    return tuple(int(part) for part in value.split("."))


def _v2_compatibility(entry: Mapping[str, Any], env: LocalRuntimeEnvironmentProfile) -> tuple[str, ...]:
    reasons: list[str] = []
    current = f"{env.python_major}.{env.python_minor}"
    if current not in entry["supported_python_versions"]:
        reasons.append("python_version_not_supported")
    tag = entry["python_tag"]
    cp = PYTHON_TAG_RE.fullmatch(tag)
    if tag == "py3":
        if env.python_major != 3:
            reasons.append("python_tag_mismatch")
    elif not cp or env.python_implementation != "cpython" or current != f"{cp.group('major')}.{int(cp.group('minor'))}":
        reasons.append("python_tag_mismatch")
    abi = entry["abi_tag"]
    if abi != "none" and abi != env.python_abi:
        reasons.append("python_abi_mismatch")
    platform_tag = entry["platform_tag"]
    arch = normalize_architecture(env.architecture)
    if platform_tag == "win_amd64":
        if env.os_family != "windows": reasons.append("wheel_os_mismatch")
        if arch != "x86_64": reasons.append("wheel_architecture_mismatch")
    elif match := MANYLINUX_RE.fullmatch(platform_tag):
        if env.os_family != "linux": reasons.append("wheel_os_mismatch")
        if arch != match.group("arch"): reasons.append("wheel_architecture_mismatch")
        if not env.libc_family or not env.libc_version:
            reasons.append("libc_unknown")
        elif env.libc_family not in ("glibc", "gnu libc"):
            reasons.append("libc_family_mismatch")
        else:
            observed = _version_tuple(env.libc_version)
            required = (int(match.group("major")), int(match.group("minor")))
            if observed is None: reasons.append("libc_unknown")
            elif observed < required: reasons.append("glibc_too_old")
    elif match := MACOS_RE.fullmatch(platform_tag):
        if env.os_family not in ("darwin", "macos"): reasons.append("wheel_os_mismatch")
        if arch != match.group("arch"): reasons.append("wheel_architecture_mismatch")
        observed = _version_tuple(env.macos_version)
        if observed is None: reasons.append("macos_version_unknown")
        elif observed < (int(match.group("major")), int(match.group("minor"))): reasons.append("macos_version_too_old")
    else:
        reasons.append("wheel_platform_unsupported" if platform_tag else "wheel_platform_unknown")
    return tuple(sorted(set(reasons)))


def plan_local_runtime_provisioning(selection: Mapping[str, Any], environment: LocalRuntimeEnvironmentProfile,
                                     catalog: Mapping[str, Any]) -> dict[str, Any]:
    """Select one exact artifact target; never acquire, install, or inspect it."""
    try:
        selected = selection["selected"]
        requirement = selected["runtime_requirement"]
        if selection.get("status") != "selected" or not isinstance(selected, Mapping) or not isinstance(requirement, Mapping): raise ValueError
        identity = (selected["model_id"], selected["artifact_sha256"], selected["route_id"])
        engine, backend = requirement["engine"], requirement["backend_family"]
        if not all(isinstance(value, str) and value for value in identity) or engine not in ENGINES or backend not in BACKENDS: raise ValueError
    except (KeyError, TypeError, ValueError):
        plan = _base("blocked_invalid_selection", ("invalid_selected_route",), environment)
        plan["provisioning_plan_digest"] = semantic_digest(plan); return plan
    try:
        normalized = validate_runtime_catalog(catalog)
    except (TypeError, ValueError) as exc:
        plan = _base("blocked_invalid_catalog", (str(exc),), environment)
        plan["provisioning_plan_digest"] = semantic_digest(plan); return plan
    schema = normalized["schema_version"]
    if schema == CATALOG_SCHEMA_VERSION and (environment.missing_fact_codes or not all((
            environment.os_family, environment.architecture, environment.python_implementation, environment.python_abi))):
        plan = _base("blocked_missing_environment_facts",
                     environment.missing_fact_codes or ("environment_fact_unknown",),
                     environment, normalized["catalog_digest"])
        plan["provisioning_plan_digest"] = semantic_digest(plan); return plan
    candidates = [entry for entry in normalized["runtimes"] if entry["engine"] == engine and entry["backend_family"] == backend]
    evaluated: list[tuple[dict[str, Any], tuple[str, ...]]] = []
    for entry in candidates:
        if schema == CATALOG_SCHEMA_VERSION:
            reasons = tuple(code for condition, code in (
                (entry["os_family"] != environment.os_family.lower(), "wheel_os_mismatch"),
                (entry["architecture"] != normalize_architecture(environment.architecture), "wheel_architecture_mismatch"),
                (entry["python_implementation"] != environment.python_implementation.lower(), "python_tag_mismatch"),
                (entry["python_abi"] != environment.python_abi, "python_abi_mismatch")) if condition)
        else:
            reasons = _v2_compatibility(entry, environment)
        evaluated.append((entry, reasons))
    compatible = [entry for entry, reasons in evaluated if not reasons]
    if not compatible:
        reasons = tuple(sorted({reason for _, item_reasons in evaluated for reason in item_reasons})) or ("no_exact_environment_match",)
        unresolved = {"libc_unknown", "macos_version_unknown", "wheel_platform_unknown"} & set(reasons)
        status = "blocked_missing_environment_facts" if unresolved else "blocked_no_compatible_runtime"
        plan = _base(status, reasons, environment, normalized["catalog_digest"])
        plan["provisioning_plan_digest"] = semantic_digest(plan); return plan
    entry = sorted(compatible, key=lambda item: (item["runtime_priority"], item["runtime_id"]))[0]
    plan = _base("selected", (), environment, normalized["catalog_digest"])
    plan.update({"catalog_schema_version": schema, "selected_model_id": identity[0],
        "selected_model_artifact_sha256": identity[1], "selected_route_id": identity[2],
        "selection_plan_digest": selection.get("plan_digest", semantic_digest(selection)), "engine": engine,
        "backend_family": backend, "runtime_id": entry["runtime_id"], "distribution_kind": entry["distribution_kind"],
        "package_name": entry["package_name"], "package_version": entry["package_version"],
        "artifact_filename": entry["artifact_filename"], "artifact_sha256": entry["artifact_sha256"],
        "artifact_urls": entry["artifact_urls"], "target_os_family": environment.os_family,
        "target_architecture": normalize_architecture(environment.architecture),
        "python_implementation": environment.python_implementation, "python_abi": environment.python_abi,
        "external_prerequisite_codes": entry["external_prerequisite_codes"],
        "prerequisite_status": "not_evaluated" if entry["external_prerequisite_codes"] else "not_required"})
    if schema == CATALOG_SCHEMA_VERSION_V2:
        plan.update(backend_variant=entry["backend_variant"], python_tag=entry["python_tag"],
                    abi_tag=entry["abi_tag"], platform_tag=entry["platform_tag"],
                    supported_python_versions=entry["supported_python_versions"])
    if entry.get("artifact_size_bytes") is not None: plan["artifact_size_bytes"] = entry["artifact_size_bytes"]
    plan["provisioning_plan_digest"] = semantic_digest(plan)
    return plan
