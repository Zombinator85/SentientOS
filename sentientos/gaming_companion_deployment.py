"""Closed deployment manifest and read-only gaming-companion readiness doctor."""
from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "sentientos.gaming_companion_deployment:v1"
_TOP_FIELDS = frozenset({
    "schema_version", "deployment_id", "repository_root", "python_executable",
    "state_root", "installation_identity_ref", "serving_operation_ref",
    "runtime_handoff_ref", "software_generation_digest", "enabled_windows_components",
    "bridge_key_reference", "bridge_bind_scope", "firewall_rule_reference",
    "start_on_login", "automatic_capture", "automatic_speech",
})
_WINDOWS_COMPONENTS = frozenset({"foreground_observer", "godot_renderer", "local_audio_output"})


class GamingCompanionDeploymentError(ValueError):
    """Invalid or unsafe deployment configuration."""


def validate_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the versioned split-host contract without probing or mutating hosts."""
    if not isinstance(value, Mapping) or set(value) != _TOP_FIELDS:
        raise GamingCompanionDeploymentError("manifest_fields_invalid")
    result = dict(value)
    if result.get("schema_version") != SCHEMA:
        raise GamingCompanionDeploymentError("manifest_schema_unsupported")
    for field in ("deployment_id", "repository_root", "python_executable", "state_root"):
        if not isinstance(result.get(field), str) or not result[field].strip():
            raise GamingCompanionDeploymentError("manifest_field_missing:" + field)
    for field in ("repository_root", "python_executable", "state_root"):
        if "\x00" in result[field] or not Path(result[field]).is_absolute():
            raise GamingCompanionDeploymentError("manifest_posix_absolute_path_required:" + field)
    if not isinstance(result["enabled_windows_components"], list):
        raise GamingCompanionDeploymentError("manifest_windows_components_invalid")
    components = result["enabled_windows_components"]
    if any(not isinstance(item, str) or item not in _WINDOWS_COMPONENTS for item in components):
        raise GamingCompanionDeploymentError("manifest_windows_components_invalid")
    if len(components) != len(set(components)):
        raise GamingCompanionDeploymentError("manifest_windows_components_invalid")
    if result["bridge_bind_scope"] not in {"loopback_only", "private_host_firewall"}:
        raise GamingCompanionDeploymentError("manifest_bridge_scope_invalid")
    key_ref = result["bridge_key_reference"]
    if key_ref is not None and (not isinstance(key_ref, str) or not key_ref.strip()):
        raise GamingCompanionDeploymentError("manifest_bridge_key_reference_invalid")
    firewall_ref = result["firewall_rule_reference"]
    if result["bridge_bind_scope"] == "private_host_firewall" and (
            not isinstance(firewall_ref, str) or not firewall_ref.strip()):
        raise GamingCompanionDeploymentError("manifest_firewall_reference_required")
    for field in ("start_on_login", "automatic_capture", "automatic_speech"):
        if type(result[field]) is not bool:
            raise GamingCompanionDeploymentError("manifest_boolean_invalid:" + field)
    # The first deployment contract is opt-in and manually started. A manifest
    # cannot install persistence, capture, or speech consent by setting flags.
    if result["start_on_login"] or result["automatic_capture"] or result["automatic_speech"]:
        raise GamingCompanionDeploymentError("manifest_requires_explicit_manual_activation")
    for field in ("installation_identity_ref", "serving_operation_ref", "runtime_handoff_ref"):
        if result[field] is not None and (not isinstance(result[field], str) or not result[field].strip()):
            raise GamingCompanionDeploymentError("manifest_reference_invalid:" + field)
    generation = result["software_generation_digest"]
    if generation is not None and (
            not isinstance(generation, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", generation) is None):
        raise GamingCompanionDeploymentError("manifest_software_generation_digest_invalid")
    return result


def _is_wsl2() -> bool:
    marker = os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP")
    try:
        release = Path("/proc/sys/kernel/osrelease").read_text(encoding="utf-8").lower()
    except OSError:
        release = ""
    return sys.platform.startswith("linux") and bool(marker or "microsoft" in release)


def _native_linux_state_root(path_text: str) -> bool:
    path = Path(path_text)
    if not path.is_absolute():
        return False
    try:
        resolved = path.resolve(strict=False)
    except OSError:
        return False
    # POSIX custody must remain on the Linux filesystem, not a Windows mount.
    return not (resolved == Path("/mnt") or Path("/mnt") in resolved.parents)


def inspect_local(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Read-only local checks; Windows-side readiness remains explicitly unknown."""
    try:
        cfg = validate_manifest(manifest)
    except (GamingCompanionDeploymentError, TypeError) as exc:
        return {
            "schema_version": "sentientos.gaming_companion_readiness:v1",
            "status": "blocked", "reason_codes": [str(exc)], "facts": {},
            "evidence_level": "configuration_validation_only",
            "host_mutation_performed": False,
        }
    repo = Path(cfg["repository_root"])
    python = Path(cfg["python_executable"])
    state = Path(cfg["state_root"])
    bridge_runtime_source = repo / "sentientos" / "gaming_companion_bridge_runtime.py"
    try:
        resolved_repo = repo.resolve(strict=False)
        resolved_state = state.resolve(strict=False)
        state_separate_from_repo = resolved_state != resolved_repo and resolved_repo not in resolved_state.parents
    except OSError:
        state_separate_from_repo = False
    facts = {
        "wsl2_environment": _is_wsl2(),
        "repository_exists": repo.is_dir() and (repo / "pyproject.toml").is_file(),
        "python_executable_exists": python.is_file() and os.access(python, os.X_OK),
        "state_root_native_linux_path": _native_linux_state_root(str(state)),
        "state_root_separate_from_checkout": state_separate_from_repo,
        "state_root_exists": state.is_dir() and not state.is_symlink(),
        "chat_entrypoint": shutil.which("sentientos-chat") is not None,
        "bridge_runtime_source_in_checkout": bridge_runtime_source.is_file(),
        "bridge_listener": "not_observed_from_this_environment",
        "windows_observer": "not_observed_from_this_environment",
        "godot_renderer": "not_observed_from_this_environment",
        "speech_output": "not_observed_from_this_environment",
        "installation_identity_reference_present": bool(cfg["installation_identity_ref"]),
        "serving_operation_reference_present": bool(cfg["serving_operation_ref"]),
        "runtime_handoff_reference_present": bool(cfg["runtime_handoff_ref"]),
        "bridge_key_reference_present": bool(cfg["bridge_key_reference"]),
        "software_generation_digest_present": bool(cfg["software_generation_digest"]),
    }
    reasons: list[str] = []
    for key in ("wsl2_environment", "repository_exists", "python_executable_exists",
                "state_root_native_linux_path", "state_root_separate_from_checkout",
                "state_root_exists", "chat_entrypoint",
                "installation_identity_reference_present", "serving_operation_reference_present",
                "runtime_handoff_reference_present", "bridge_key_reference_present",
                "software_generation_digest_present"):
        if facts[key] is not True:
            reasons.append(key + "_not_ready")
    warnings: list[str] = []
    if facts["bridge_listener"] != "ready":
        warnings.append("authenticated_bridge_listener_unobserved")
    if facts["bridge_runtime_source_in_checkout"] is not True:
        warnings.append("authenticated_bridge_runtime_source_unavailable")
    for component in cfg["enabled_windows_components"]:
        facts[component] = "not_observed_from_this_environment"
        warnings.append(component + "_readiness_unverified")
    status = "blocked" if reasons else "ready_with_warnings" if warnings else "ready"
    return {
        "schema_version": "sentientos.gaming_companion_readiness:v1",
        "status": status,
        "reason_codes": sorted(set(reasons)),
        "warning_codes": sorted(set(warnings)),
        "facts": facts,
        "evidence_level": "local_read_only_checks; external components require attributable probes",
        "authority_effects_performed": False,
        "host_mutation_performed": False,
    }


__all__ = ["SCHEMA", "GamingCompanionDeploymentError", "validate_manifest", "inspect_local"]
