from __future__ import annotations

"""Local-files-only commissioning for one operator-supplied model artifact."""

import importlib.util
import json
import os
from pathlib import Path
import stat
from typing import Any, Mapping

from .config import GenerationConfig, ModelCandidate, ModelConfig
from .local_model import LocalModel, ModelLoadError, candidate_artifact_identity, candidate_configuration_digest
from .local_model_authority import (
    PRODUCTION_ENGINES, PROVIDER_ENGINES,
    LocalModelAuthorityMap, build_local_model_authority_map, digest_payload,
)

SCHEMA = "sentientos.local_model_commissioning:v1"
OBSERVED_AT = "1970-01-01T00:00:00+00:00"
FILES = {
    "manifest": "commissioning-manifest.json", "artifact": "artifact-identity.json",
    "config": "model-config.json", "authority": "authority-preview.json",
    "verification": "verification-result.json", "handoff": "calibration-handoff.json",
}
NO_AUTHORITY = {key: False for key in (
    "provider_network", "tool", "memory", "goal", "action", "trial_enrollment",
    "calibration", "repository", "git", "adoption", "authority_grant",
)}


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode()


def _digest(value: Any) -> str:
    return digest_payload(value)


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _authorized_artifact(model_path: Path, allowed_root: Path) -> tuple[Path, Path]:
    raw = str(model_path)
    if "://" in raw or raw.startswith(("http:", "https:", "hf:", "ollama:")):
        raise ValueError("provider_or_network_path_blocked")
    if ".." in model_path.parts:
        raise ValueError("path_traversal_blocked")
    root = allowed_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("authorized_root_not_directory")
    resolved = model_path.resolve(strict=True)
    if not _inside(resolved, root):
        raise ValueError("artifact_root_escape")
    try:
        mode = model_path.stat(follow_symlinks=False).st_mode
    except OSError as exc:
        raise ValueError("artifact_unavailable") from exc
    if model_path.is_symlink():
        raise ValueError("artifact_symlink_blocked")
    if not stat.S_ISREG(mode):
        raise ValueError("artifact_not_regular_file")
    if not os.access(resolved, os.R_OK):
        raise ValueError("artifact_unreadable")
    return root, resolved


def inspect_artifact(model_path: Path, *, allowed_root: Path, engine: str = "llama_cpp",
                     name: str | None = None, max_context_tokens: int = 4096,
                     generation: GenerationConfig | None = None,
                     options: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Inspect exact bytes under one explicit local root; never writes or generates."""
    engine = engine.lower()
    if engine in PROVIDER_ENGINES or engine not in PRODUCTION_ENGINES:
        reason = "provider_engine_blocked" if engine in PROVIDER_ENGINES else "production_engine_required"
        raise ValueError(reason)
    root, resolved = _authorized_artifact(model_path, allowed_root)
    if resolved.suffix.lower() != ".gguf" or engine != "llama_cpp":
        raise ValueError("gguf_llama_cpp_candidate_required")
    candidate = ModelCandidate(path=resolved, engine=engine, name=name,
                               options=dict(options or {}))
    config = ModelConfig([candidate], default_engine=engine,
                         max_context_tokens=max_context_tokens,
                         generation=generation or GenerationConfig())
    metadata = LocalModel._load_metadata(candidate)
    path, semantic, content, size, sidecar = candidate_artifact_identity(candidate, metadata)
    result = {
        "schema_version": SCHEMA + ".artifact", "declared_path": str(model_path),
        "resolved_path": path, "authorized_root": str(root), "regular_file": True,
        "symlink": False, "readable": True, "filesystem_root_suitable": True,
        "artifact_size_bytes": size, "model_content_sha256": content,
        "semantic_artifact_identity": semantic, "engine": engine,
        "engine_inferred": model_path.suffix.lower() == ".gguf",
        "sidecar_metadata_present": sidecar is not None,
        "sidecar_metadata_digest": sidecar,
        "configuration_digest": candidate_configuration_digest(candidate, config, engine),
        "configuration_inputs": _config_mapping(config),
        "llama_cpp_dependency_available": importlib.util.find_spec("llama_cpp") is not None,
        "provider_network_posture": "blocked_local_files_only",
        "authority_effect_posture": dict(NO_AUTHORITY),
    }
    result["inspection_digest"] = _digest(result)
    return result


def _config_mapping(config: ModelConfig) -> dict[str, Any]:
    candidate = config.candidates[0]
    return {
        "candidates": [{"path": str(candidate.path), "engine": candidate.engine,
                        **({"name": candidate.name} if candidate.name else {}),
                        "options": dict(sorted(candidate.options.items()))}],
        "default_engine": config.default_engine,
        "max_context_tokens": config.max_context_tokens,
        "generation": config.generation.as_kwargs(),
    }


def _config_from_mapping(value: Mapping[str, Any]) -> ModelConfig:
    rows = value.get("candidates")
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], Mapping):
        raise ValueError("exactly_one_candidate_required")
    row = rows[0]
    generation = value.get("generation", {})
    if not isinstance(generation, Mapping):
        raise ValueError("generation_config_invalid")
    return ModelConfig(
        [ModelCandidate(Path(str(row["path"])), str(row.get("engine", "auto")),
                        str(row["name"]) if row.get("name") is not None else None,
                        dict(row.get("options", {})))],
        str(value.get("default_engine", "auto")), int(value.get("max_context_tokens", 4096)),
        GenerationConfig(max_new_tokens=int(generation.get("max_new_tokens", 512)),
                         temperature=float(generation.get("temperature", .7)),
                         top_p=float(generation.get("top_p", .95)),
                         top_k=generation.get("top_k"),
                         repetition_penalty=generation.get("repetition_penalty")),
    )


def _preview(config: ModelConfig, allowed_root: Path) -> tuple[LocalModelAuthorityMap, dict[str, Any]]:
    authority = build_local_model_authority_map(config, allowed_roots=[allowed_root], observed_at=OBSERVED_AT)
    record = authority.records[0]
    return authority, {"schema_version": SCHEMA + ".authority-preview",
                       "preview_not_authority_grant": True, "map_id": authority.map_id,
                       "map_digest": authority.map_digest, "record": record.to_dict(),
                       "summary": dict(authority.summary), "authority_effect_posture": dict(NO_AUTHORITY)}


def _handoff(config_path: Path, authority: LocalModelAuthorityMap) -> dict[str, Any]:
    record = authority.records[0]
    value = {"schema_version": SCHEMA + ".calibration-handoff",
             "target_subsystem": "sentientos.discernment_calibration",
             "target_cli": "scripts/discernment_calibration.py", "model_config_path": str(config_path),
             "model_id": record.model_id, "authority_map_digest": authority.map_digest,
             "candidate_index": 0, "automatic_calibration_run": False,
             "trial_enrolled": False, "authority_effect_posture": dict(NO_AUTHORITY)}
    value["handoff_digest"] = _digest(value)
    return value


def _external_state_root(state_root: Path) -> Path:
    repo = Path(__file__).resolve().parents[1]
    parent = state_root.parent.resolve(strict=True)
    target = parent / state_root.name
    if target == repo or _inside(target, repo):
        raise ValueError("commissioning_state_inside_repository")
    if target.exists() and (target.is_symlink() or not target.is_dir()):
        raise ValueError("commissioning_state_unsafe")
    return target


def render_bundle(model_path: Path, *, allowed_root: Path, state_root: Path,
                  name: str | None = None, max_context_tokens: int = 4096,
                  generation: GenerationConfig | None = None,
                  options: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Write bounded metadata once to an explicit external root; never copies model bytes."""
    root = _external_state_root(state_root)
    if root.exists() and any(root.iterdir()):
        raise FileExistsError("commissioning_state_no_clobber")
    inspection = inspect_artifact(model_path, allowed_root=allowed_root, name=name,
                                  max_context_tokens=max_context_tokens,
                                  generation=generation, options=options)
    config_value = inspection["configuration_inputs"]
    config = _config_from_mapping(config_value)
    authority, preview = _preview(config, allowed_root)
    root.mkdir(mode=0o700)
    config_path = root / FILES["config"]
    handoff = _handoff(config_path, authority)
    verification = {"schema_version": SCHEMA + ".verification", "status": "not_requested",
                    "process_real": False, "semantic_model_generations": 0,
                    "authority_effect_posture": dict(NO_AUTHORITY)}
    artifacts = {"artifact": inspection, "config": config_value, "authority": preview,
                 "verification": verification, "handoff": handoff}
    links = {key: _digest(value) for key, value in artifacts.items()}
    manifest = {"schema_version": SCHEMA + ".manifest", "artifact_files": dict(FILES),
                "artifact_digests": links, "model_bytes_copied": False,
                "authority_effect_posture": dict(NO_AUTHORITY)}
    manifest["manifest_digest"] = _digest(manifest)
    artifacts["manifest"] = manifest
    for key, value in artifacts.items():
        (root / FILES[key]).write_bytes(_canonical(value))
    return {"status": "commissioning_bundle_rendered", "state_root": str(root),
            "manifest": manifest, "authority_preview": preview, "handoff": handoff}


def verify_bundle(state_root: Path, *, load: bool = False) -> dict[str, Any]:
    """Recompute every link and, optionally, prove the real loader/identity/map chain."""
    root = _external_state_root(state_root)
    try:
        values = {key: json.loads((root / name).read_text()) for key, name in FILES.items()}
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return _blocked("commissioning_artifact_unavailable_or_invalid", str(exc))
    manifest = values["manifest"]
    expected_manifest = dict(manifest); supplied_manifest_digest = expected_manifest.pop("manifest_digest", None)
    reasons: list[str] = []
    if supplied_manifest_digest != _digest(expected_manifest): reasons.append("manifest_digest_mismatch")
    for key in ("artifact", "config", "authority", "verification", "handoff"):
        if manifest.get("artifact_digests", {}).get(key) != _digest(values[key]):
            reasons.append(key + "_digest_mismatch")
    try:
        config = _config_from_mapping(values["config"])
        artifact = values["artifact"]
        current = inspect_artifact(config.candidates[0].path or Path(""),
                                   allowed_root=Path(str(artifact["authorized_root"])),
                                   engine=config.candidates[0].engine,
                                   name=config.candidates[0].name,
                                   max_context_tokens=config.max_context_tokens,
                                   generation=config.generation, options=config.candidates[0].options)
        if current != artifact: reasons.append("artifact_identity_substituted")
        authority, preview = _preview(config, Path(str(artifact["authorized_root"])))
        if preview != values["authority"]: reasons.append("authority_preview_mismatch")
        expected_handoff = _handoff(root / FILES["config"], authority)
        if expected_handoff != values["handoff"]: reasons.append("calibration_handoff_mismatch")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        reasons.append("reconstruction_failed:" + str(exc))
        authority = None
    if reasons:
        return _blocked(*reasons)
    load_result: dict[str, Any] = {"status": "not_requested", "process_real": False,
                                   "semantic_model_generations": 0}
    if load:
        load_result = _load_proof(config, authority)  # type: ignore[arg-type]
    return {"schema_version": SCHEMA + ".bundle-validation", "status": "verified",
            "bundle_valid": True, "load_verification": load_result,
            "semantic_model_generations": 0, "calibration_cases_run": 0,
            "authority_effect_posture": dict(NO_AUTHORITY)}


def _load_proof(config: ModelConfig, authority: LocalModelAuthorityMap) -> dict[str, Any]:
    candidate = config.candidates[0]
    if importlib.util.find_spec("llama_cpp") is None:
        return {"status": "external_prerequisite_unavailable", "reason": "llama_cpp_dependency_unavailable",
                "process_real": False, "semantic_model_generations": 0}
    try:
        backend, metadata = LocalModel._initialise_backend(candidate, config)
        identity = LocalModel._identity_for(candidate, config, backend, metadata, 0)
        model = LocalModel(backend, backend.metadata, config, backend, identity)
        record = authority.record_for_active_identity(model.active_identity, "discernment_judgment")
    except (ModelLoadError, OSError) as exc:
        return {"status": "external_prerequisite_unavailable", "reason": str(exc),
                "process_real": False, "semantic_model_generations": 0}
    return {"status": "exact_active_identity_verified" if record else "active_identity_mismatch",
            "process_real": True, "active_model_identity": identity.to_dict(),
            "matching_model_id": record.model_id if record else None, "semantic_model_generations": 0}


def doctor(state_root: Path, *, require_load_verification: bool = False) -> dict[str, Any]:
    result = verify_bundle(state_root, load=require_load_verification)
    load = result.get("load_verification", {})
    bundle_ok = result.get("bundle_valid") is True
    exact = load.get("status") == "exact_active_identity_verified"
    return {"schema_version": SCHEMA + ".doctor", "status": "ready" if bundle_ok else "blocked",
            "artifact_present": bundle_ok, "artifact_identity_stable": bundle_ok,
            "config_valid": bundle_ok, "engine_production_capable": bundle_ok,
            "local_dependency_available": importlib.util.find_spec("llama_cpp") is not None,
            "candidate_non_fallback": bundle_ok, "authority_preview_eligible": bundle_ok,
            "exact_load_authority_verified": exact,
            "live_discernment_prerequisites_satisfiable": bundle_ok and (exact or not require_load_verification),
            "live_calibration_can_be_attempted": bundle_ok and (exact or not require_load_verification),
            "semantic_model_generations": 0, "calibration_cases_run": 0,
            "verification": result, "authority_effect_posture": dict(NO_AUTHORITY)}


def _blocked(*reasons: str) -> dict[str, Any]:
    return {"schema_version": SCHEMA + ".bundle-validation", "status": "blocked",
            "bundle_valid": False, "reason_codes": list(reasons),
            "semantic_model_generations": 0, "calibration_cases_run": 0,
            "authority_effect_posture": dict(NO_AUTHORITY)}


__all__ = ["inspect_artifact", "render_bundle", "verify_bundle", "doctor", "FILES", "NO_AUTHORITY"]
