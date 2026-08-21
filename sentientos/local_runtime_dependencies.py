"""Offline validation and metadata-only selection of curated runtime dependencies."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from sentientos.local_runtime_provisioning import (
    ENVIRONMENT_SCHEMA_VERSION_V2,
    LocalRuntimeEnvironmentProfile,
    environment_profile_from_mapping,
)

CATALOG_SCHEMA = "sentientos.local_runtime_dependency_catalog:v1"
PLAN_SCHEMA = "sentientos.local_runtime_dependency_plan:v1"
EXPECTED_VERSIONS = {
    "typing-extensions": "4.16.0", "numpy": "2.2.6", "diskcache": "5.6.3",
    "jinja2": "3.1.6", "markupsafe": "3.0.3",
}
REQUIRED_ENVIRONMENTS = tuple(
    f"cpython{minor}-{os_family}-{'arm64' if os_family == 'macos' else 'x86_64'}"
    for os_family in ("windows", "linux", "macos") for minor in ("310", "311", "312")
)
ZERO_EFFECT = {
    "network_performed": False, "download_performed": False,
    "package_install_performed": False, "subprocess_performed": False,
    "runtime_import_performed": False, "model_load_performed": False,
    "commissioning_performed": False, "runtime_execution_authority_granted": False,
}
_SHA = re.compile(r"^[0-9a-f]{64}$")


def semantic_digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode()).hexdigest()


def _without_digest(value: Mapping[str, Any], key: str) -> dict[str, Any]:
    result = dict(value)
    result.pop(key, None)
    return result


def _version(value: str) -> tuple[int, ...]:
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", value):
        raise ValueError("invalid_platform_version")
    return tuple(int(part) for part in value.split("."))


def _wheel_parts(filename: str) -> tuple[str, str, str, str, str]:
    if not filename.endswith(".whl"):
        raise ValueError("sdist_or_non_wheel_artifact")
    parts = filename[:-4].split("-", 4)
    if len(parts) != 5:
        raise ValueError("invalid_wheel_filename")
    return tuple(parts)  # type: ignore[return-value]


def validate_dependency_catalog(catalog: Mapping[str, Any]) -> dict[str, Any]:
    """Fail closed unless the fixed closure and all nine exact bundles are sound."""
    if catalog.get("schema_version") != CATALOG_SCHEMA:
        raise ValueError("invalid_catalog_schema")
    if catalog.get("curated_versions") != EXPECTED_VERSIONS:
        raise ValueError("wrong_curated_versions")
    if catalog.get("catalog_digest") != semantic_digest(_without_digest(catalog, "catalog_digest")):
        raise ValueError("catalog_digest_mismatch")
    graph = catalog.get("dependency_graph")
    expected_nodes = {
        "llama-cpp-python==0.3.35", "Jinja2==3.1.6", "typing-extensions==4.16.0",
        "numpy==2.2.6", "diskcache==5.6.3", "MarkupSafe==3.0.3",
    }
    if not isinstance(graph, Mapping) or set(graph) != expected_nodes:
        raise ValueError("incomplete_dependency_closure")
    direct = {str(x).split(" ", 1)[0].split(">", 1)[0].lower() for x in graph["llama-cpp-python==0.3.35"]}
    if direct != {"typing-extensions", "numpy", "diskcache", "jinja2"}:
        raise ValueError("direct_dependency_closure_mismatch")
    if not any(str(x).lower().startswith("markupsafe") for x in graph["Jinja2==3.1.6"]):
        raise ValueError("transitive_dependency_closure_mismatch")
    artifacts = catalog.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 21:
        raise ValueError("artifact_coverage_incomplete")
    by_id: dict[str, dict[str, Any]] = {}
    for raw in artifacts:
        if not isinstance(raw, Mapping):
            raise ValueError("invalid_artifact")
        item = dict(raw)
        required = ("artifact_id", "package_name", "package_version", "distribution_kind",
                    "artifact_filename", "artifact_url", "artifact_sha256", "artifact_size_bytes",
                    "python_tag", "abi_tag", "platform_tag", "license_identity", "source_kind",
                    "requires_python", "dependency_requirement_strings")
        if any(key not in item for key in required):
            raise ValueError("incomplete_artifact_custody")
        artifact_id = item["artifact_id"]
        if not isinstance(artifact_id, str) or artifact_id in by_id:
            raise ValueError("duplicate_artifact_id")
        package = str(item["package_name"]).lower().replace("_", "-")
        if EXPECTED_VERSIONS.get(package) != item["package_version"]:
            raise ValueError("wrong_package_version")
        if item["distribution_kind"] != "python_wheel":
            raise ValueError("sdist_or_non_wheel_artifact")
        distribution, version, python_tag, abi_tag, platform_tag = _wheel_parts(str(item["artifact_filename"]))
        if (distribution.lower().replace("_", "-") != package or version != item["package_version"] or
                (python_tag, abi_tag, platform_tag) !=
                (item["python_tag"], item["abi_tag"], item["platform_tag"])):
            raise ValueError("wheel_filename_tag_mismatch")
        parsed = urlsplit(str(item["artifact_url"]))
        if parsed.scheme != "https" or parsed.hostname != "files.pythonhosted.org" or parsed.path.endswith("/latest"):
            raise ValueError("untrusted_artifact_url")
        if not isinstance(item["artifact_size_bytes"], int) or isinstance(item["artifact_size_bytes"], bool) or item["artifact_size_bytes"] <= 0:
            raise ValueError("invalid_artifact_size")
        if not isinstance(item["artifact_sha256"], str) or not _SHA.fullmatch(item["artifact_sha256"]):
            raise ValueError("invalid_artifact_hash")
        if item["source_kind"] != "pypi_distribution":
            raise ValueError("invalid_source_kind")
        by_id[artifact_id] = item
    bundles = catalog.get("environment_bundles")
    if not isinstance(bundles, list) or {b.get("environment_id") for b in bundles if isinstance(b, Mapping)} != set(REQUIRED_ENVIRONMENTS):
        raise ValueError("environment_bundle_coverage_incomplete")
    for bundle in bundles:
        ids = bundle.get("artifact_ids")
        if not isinstance(ids, list) or ids != sorted(ids) or len(ids) != 5 or len(set(ids)) != 5:
            raise ValueError("invalid_bundle_membership")
        selected = [by_id.get(str(artifact_id)) for artifact_id in ids]
        if None in selected or {str(a["package_name"]).lower().replace("_", "-") for a in selected if a} != set(EXPECTED_VERSIONS):
            raise ValueError("incomplete_dependency_closure")
        expected = semantic_digest(_without_digest(bundle, "bundle_digest"))
        if bundle.get("bundle_digest") != expected:
            raise ValueError("bundle_digest_mismatch")
        if any(not _artifact_matches_environment(a, str(bundle["environment_id"])) for a in selected if a):
            raise ValueError("incompatible_bundle_artifact")
    if catalog.get("runtime_dependency_custody_ready") is not True:
        raise ValueError("custody_not_ready")
    return {**dict(catalog), "artifacts_by_id": by_id}


def _artifact_matches_environment(artifact: Mapping[str, Any], environment_id: str) -> bool:
    minor = environment_id[7:10]
    py = artifact["python_tag"]
    if py != "py3" and py != f"cp{minor}":
        return False
    platform = str(artifact["platform_tag"])
    if platform == "any":
        return True
    if "-windows-" in environment_id:
        return platform == "win_amd64"
    if "-linux-" in environment_id:
        return "manylinux" in platform and "x86_64" in platform
    return "-macos-" in environment_id and platform == "macosx_11_0_arm64"


def _base(status: str, profile_digest: str, reasons: list[str]) -> dict[str, Any]:
    return {"schema_version": PLAN_SCHEMA, "status": status, "reason_codes": sorted(reasons),
            "environment_profile_digest": profile_digest, "runtime_dependency_custody_ready": False,
            **ZERO_EFFECT}


def plan_runtime_dependencies(catalog: Mapping[str, Any], environment: Mapping[str, Any] | LocalRuntimeEnvironmentProfile) -> dict[str, Any]:
    """Select one pre-curated bundle; never resolve, download, install, or import."""
    profile = environment if isinstance(environment, LocalRuntimeEnvironmentProfile) else environment_profile_from_mapping(environment)
    try:
        validated = validate_dependency_catalog(catalog)
    except (KeyError, TypeError, ValueError) as exc:
        return _base("blocked_invalid_catalog", profile.digest, [str(exc)])
    missing = list(profile.missing_fact_codes)
    if profile.schema_version != ENVIRONMENT_SCHEMA_VERSION_V2:
        missing.append("environment_profile_v2_required")
    if profile.os_family == "linux" and (not profile.libc_family or not profile.libc_version):
        missing.append("libc_unknown")
    if profile.os_family in ("darwin", "macos") and not profile.macos_version:
        missing.append("macos_version_unknown")
    if missing:
        return _base("blocked_missing_environment_facts", profile.digest, missing)
    os_family = "macos" if profile.os_family == "darwin" else profile.os_family
    if (profile.python_implementation != "cpython" or profile.python_major != 3 or
            profile.python_minor not in (10, 11, 12) or profile.architecture != ("arm64" if os_family == "macos" else "x86_64") or
            os_family not in ("windows", "linux", "macos")):
        return _base("blocked_unsupported_environment", profile.digest, ["unsupported_environment"])
    if os_family == "linux" and (profile.libc_family not in ("glibc", "gnu") or _version(profile.libc_version) < (2, 17)):
        return _base("blocked_unsupported_environment", profile.digest, ["glibc_floor_not_met"])
    if os_family == "macos" and _version(profile.macos_version) < (11, 0):
        return _base("blocked_unsupported_environment", profile.digest, ["macos_deployment_floor_not_met"])
    environment_id = f"cpython3{profile.python_minor}-{os_family}-{'arm64' if os_family == 'macos' else 'x86_64'}"
    bundle = next((b for b in validated["environment_bundles"] if b["environment_id"] == environment_id), None)
    if bundle is None:
        return _base("blocked_incomplete_dependency_closure", profile.digest, ["bundle_missing"])
    artifacts = [validated["artifacts_by_id"][artifact_id] for artifact_id in bundle["artifact_ids"]]
    result = _base("selected", profile.digest, [])
    result.update(environment_id=environment_id, dependency_catalog_digest=validated["catalog_digest"],
                  artifact_ids=bundle["artifact_ids"], bundle_digest=bundle["bundle_digest"],
                  artifacts=[{"artifact_id": a["artifact_id"], "package_name": a["package_name"],
                              "package_version": a["package_version"], "artifact_filename": a["artifact_filename"],
                              "artifact_sha256": a["artifact_sha256"], "artifact_size_bytes": a["artifact_size_bytes"]}
                             for a in artifacts], runtime_dependency_custody_ready=True)
    result["dependency_plan_digest"] = semantic_digest(_without_digest(result, "dependency_plan_digest"))
    return result


def load_dependency_catalog(path: str | Path = "manifests/local-runtime-dependency-catalog-v1.json") -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("invalid_catalog_document")
    return value
