"""Closed, operator-authored maintenance activation profile bundles.

Rendering is metadata construction only.  It grants no authority and performs no
activation, authentication, candidate admission, validation, Git, or publication.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, cast

from sentientos import maintenance_candidate_selector as selector
from sentientos import maintenance_commit_publication as landing
from sentientos import maintenance_local_codex_foreman as foreman
from sentientos import maintenance_task_authority_lease as authority
from sentientos import maintenance_validation_controller as validation

MANIFEST_SCHEMA = "sentientos.maintenance_activation_profile_manifest:v1"
INDEX_SCHEMA = "sentientos.maintenance_activation_profile_bundle_index:v1"
TEMPLATE_SCHEMA = "sentientos.maintenance_activation_profile_manifest_template:v1"
FILENAMES = {
    "standing_grant": "standing_operator_grant.json",
    "selector_policy": "selector_policy.json",
    "foreman_policy": "local_codex_foreman_policy.json",
    "validation_policy": "validation_policy.json",
    "landing_policy": "landing_policy.json",
}
REQUIRED = {
    "schema_version", "manifest_id", "manifest_digest", "template_no_authority",
    "repository_identity", "repository_root", "base_sha", "allowed_candidate_kinds",
    "allowed_path_prefixes", "forbidden_paths", "authority_classes", "budgets",
    "operator_reference", "approval_reference", "not_before", "expires_at",
    "state_root", "workspace_root", "scratch_root", "inbox_root", "codex_home",
    "codex_executable", "git_executable", "python_executable", "validation_bounds",
    "publication_mode", "remote_name", "tracked_base_ref", "base_ref", "head_ref_prefix",
    "publication_client_executable", "commit_identity", "commit_title_policy", "output_directory",
}
SECRET_WORDS = re.compile(r"(?:credential|secret|password|token|api[_-]?key|private[_-]?key)", re.I)
PLACEHOLDER = re.compile(r"(?:REPLACE|PLACEHOLDER|CHOOSE)", re.I)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def bytes_digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def digest(value: Any, omitted: str | None = None) -> str:
    body = {k: v for k, v in value.items() if k != omitted} if omitted and isinstance(value, Mapping) else value
    return bytes_digest(canonical_bytes(body))


def _load(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if p.is_symlink() or not p.is_file():
        raise ValueError("profile_input_not_regular")
    return cast(dict[str, Any], json.loads(p.read_text(encoding="utf-8")))


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("timestamp_must_be_utc_z")
    return datetime.fromisoformat(value[:-1] + "+00:00")


def _contains_secret_field(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(SECRET_WORDS.search(str(k)) or _contains_secret_field(v) for k, v in value.items())
    if isinstance(value, list):
        return any(_contains_secret_field(v) for v in value)
    return False


def validate_manifest(value: Mapping[str, Any], *, production: bool = True) -> dict[str, Any]:
    m = dict(value)
    if set(m) != REQUIRED or m.get("schema_version") != MANIFEST_SCHEMA:
        raise ValueError("manifest_closed_schema_invalid")
    if _contains_secret_field(m):
        raise ValueError("credential_or_secret_field_forbidden")
    if m.get("manifest_digest") != digest(m, "manifest_digest"):
        raise ValueError("manifest_digest_invalid")
    if production and (m.get("template_no_authority") is not False or PLACEHOLDER.search(canonical_bytes(m).decode())):
        raise ValueError("template_has_no_authority")
    for key in ("allowed_candidate_kinds", "allowed_path_prefixes", "forbidden_paths", "authority_classes"):
        if not isinstance(m[key], list) or not m[key]:
            raise ValueError(key + "_explicit_nonempty_required")
    auth = m["authority_classes"]
    if len(auth) != len(set(auth)) or any(a not in authority.AUTHORITY_CLASSES for a in auth):
        raise ValueError("authority_classes_invalid")
    if m["publication_mode"] not in landing.PUBLICATION_MODES:
        raise ValueError("publication_mode_invalid")
    if m["publication_mode"] == "fast_forward_base_ref" and "pull_request_publish" in auth:
        raise ValueError("publication_authority_incompatible")
    needed = {"repository_commit", "remote_repository_read", "remote_ref_publish"}
    if m["publication_mode"] == "pull_request": needed.add("pull_request_publish")
    if not needed.issubset(auth):
        raise ValueError("landing_authority_missing")
    if not re.fullmatch(r"[0-9a-f]{40}", str(m["base_sha"])):
        raise ValueError("base_sha_invalid")
    budgets = m["budgets"]
    budget_keys = {"maximum_file_count", "maximum_changed_line_count", "maximum_implementation_seconds", "maximum_validation_seconds", "maximum_wall_clock_seconds", "maximum_attempts", "maximum_corrective_retries", "publication_retry_backoff_seconds", "maximum_actions"}
    if not isinstance(budgets, Mapping) or set(budgets) != budget_keys or any(not isinstance(v, int) or v < (0 if k == "maximum_corrective_retries" else 1) for k, v in budgets.items()):
        raise ValueError("budgets_invalid")
    bounds = m["validation_bounds"]
    bound_keys = {"aggregate_validation_ceiling_seconds", "per_command_default_ceiling_seconds", "terminal_reserve_seconds", "heartbeat_interval_seconds", "output_tail_limit", "output_byte_limit", "maximum_controller_cycles", "require_declared_behavioral_test"}
    if not isinstance(bounds, Mapping) or set(bounds) != bound_keys:
        raise ValueError("validation_bounds_invalid")
    if _timestamp(m["not_before"]) >= _timestamp(m["expires_at"]):
        raise ValueError("validity_window_invalid")
    for key in ("repository_root", "state_root", "workspace_root", "scratch_root", "inbox_root", "codex_home", "codex_executable", "git_executable", "python_executable", "publication_client_executable", "output_directory"):
        if not Path(str(m[key])).is_absolute(): raise ValueError(key + "_must_be_absolute")
    return m


def manifest_template() -> dict[str, Any]:
    m: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA, "manifest_id": "REPLACE_MANIFEST_ID", "manifest_digest": "",
        "template_no_authority": True, "repository_identity": "REPLACE_REPOSITORY_IDENTITY",
        "repository_root": "/REPLACE/REPOSITORY_ROOT", "base_sha": "REPLACE_WITH_40_HEX_SHA",
        "allowed_candidate_kinds": ["REPLACE_CANDIDATE_KIND"], "allowed_path_prefixes": ["REPLACE/PATH_PREFIX"],
        "forbidden_paths": ["REPLACE/FORBIDDEN_PATTERN"], "authority_classes": ["REPLACE_EACH_AUTHORITY_CLASS"],
        "budgets": {"maximum_file_count": 0, "maximum_changed_line_count": 0, "maximum_implementation_seconds": 0, "maximum_validation_seconds": 0, "maximum_wall_clock_seconds": 0, "maximum_attempts": 0, "maximum_corrective_retries": 0, "publication_retry_backoff_seconds": 0, "maximum_actions": 0},
        "operator_reference": "REPLACE_OPERATOR_REFERENCE", "approval_reference": "REPLACE_APPROVAL_REFERENCE",
        "not_before": "REPLACE_UTC_TIMESTAMP_Z", "expires_at": "REPLACE_UTC_TIMESTAMP_Z",
        "state_root": "/REPLACE/STATE", "workspace_root": "/REPLACE/WORKSPACE", "scratch_root": "/REPLACE/SCRATCH", "inbox_root": "/REPLACE/INBOX", "codex_home": "/REPLACE/CODEX_HOME",
        "codex_executable": "/REPLACE/CODEX", "git_executable": "/REPLACE/GIT", "python_executable": "/REPLACE/PYTHON",
        "validation_bounds": {"aggregate_validation_ceiling_seconds": 0, "per_command_default_ceiling_seconds": 0, "terminal_reserve_seconds": 0, "heartbeat_interval_seconds": 0, "output_tail_limit": 0, "output_byte_limit": 0, "maximum_controller_cycles": 0, "require_declared_behavioral_test": False},
        "publication_mode": "REPLACE_MODE", "remote_name": "REPLACE_REMOTE", "tracked_base_ref": "REPLACE_TRACKED_REF", "base_ref": "REPLACE_BASE_REF", "head_ref_prefix": "REPLACE_HEAD_PREFIX",
        "publication_client_executable": "/REPLACE/PUBLICATION_CLIENT", "commit_identity": {"author_name": "REPLACE", "author_email": "REPLACE", "committer_name": "REPLACE", "committer_email": "REPLACE", "reference": "REPLACE"},
        "commit_title_policy": {"prefix": "REPLACE_TITLE_PREFIX"}, "output_directory": "/REPLACE/OUTPUT_DIRECTORY",
    }
    m["manifest_digest"] = digest(m, "manifest_digest")
    return m


def _safe_output(m: Mapping[str, Any]) -> Path:
    output = Path(str(m["output_directory"])); repo = Path(str(m["repository_root"])).resolve(strict=True)
    if output.is_symlink() or any(p.is_symlink() for p in [output, *output.parents] if p.exists()): raise ValueError("output_symlink_forbidden")
    resolved = output.resolve(strict=False)
    if resolved == repo or repo in resolved.parents or resolved == repo / ".git" or (repo / ".git") in resolved.parents: raise ValueError("output_inside_repository")
    return resolved


def _write(path: Path, value: Mapping[str, Any]) -> str:
    data = canonical_bytes(value) + b"\n"
    if path.exists():
        if path.is_symlink() or path.read_bytes() != data: raise ValueError("profile_output_conflict")
        return "reused"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as handle: handle.write(data); handle.flush(); os.fsync(handle.fileno())
    return "created"


def _artifacts(m: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    b = m["budgets"]; auths = sorted(m["authority_classes"])
    terms = {"schema_version": landing.LANDING_TERMS_SCHEMA, "publication_mode": m["publication_mode"], "remote_name": m["remote_name"], "base_ref": m["base_ref"], "head_ref_prefix": m["head_ref_prefix"], "required_authority_classes": sorted({"repository_commit", "remote_repository_read", "remote_ref_publish", *(["pull_request_publish"] if m["publication_mode"] == "pull_request" else [])})}
    grant = authority.seal_grant({"grant_id": "activation_" + str(m["manifest_id"]), "operator_reference": m["operator_reference"], "approval_reference": m["approval_reference"], "repository_identity": m["repository_identity"], "allowed_base_sha": m["base_sha"], "allowed_base_sha_rule": "exact", "allowed_candidate_kinds": sorted(m["allowed_candidate_kinds"]), "allowed_path_prefixes": sorted(m["allowed_path_prefixes"]), "forbidden_path_patterns": sorted(m["forbidden_paths"]), "allowed_authority_classes": auths, **{k: b[k] for k in ("maximum_file_count", "maximum_changed_line_count", "maximum_implementation_seconds", "maximum_validation_seconds", "maximum_wall_clock_seconds", "maximum_attempts", "maximum_corrective_retries")}, "not_before": m["not_before"], "expires_at": m["expires_at"], "grant_generation": str(m["manifest_id"]), "explicit_constraints": ["operator_authored_manifest", "no_scope_widening"], "landing_terms": terms})
    sp = selector.build_policy({"repository_base_sha": m["base_sha"], "allowed_path_prefixes": m["allowed_path_prefixes"], "forbidden_path_patterns": m["forbidden_paths"], "available_authority_classes": auths, "maximum_file_count": b["maximum_file_count"], "maximum_estimated_changed_lines": b["maximum_changed_line_count"], "maximum_implementation_seconds": b["maximum_implementation_seconds"], "maximum_validation_seconds": b["maximum_validation_seconds"], "allowed_candidate_kinds": m["allowed_candidate_kinds"]}).to_dict()
    fc = foreman.LocalCodexForemanConfig(configuration_id="activation_" + str(m["manifest_id"]), repository_identity=str(m["repository_identity"]), repository_root=Path(m["repository_root"]), external_workspace_root=Path(m["workspace_root"]), external_state_root=Path(m["state_root"]), codex_executable=Path(m["codex_executable"]), git_executable=Path(m["git_executable"]), codex_home=Path(m["codex_home"]), process_timeout_seconds=float(b["maximum_implementation_seconds"]), maximum_same_session_recovery_count=b["maximum_corrective_retries"], configuration_constraints=tuple(["authority:" + a for a in auths])).to_dict()
    vb = m["validation_bounds"]
    vp = validation.ValidationPolicy(policy_id="activation_" + str(m["manifest_id"]), repository_identity=str(m["repository_identity"]), python_executable=str(m["python_executable"]), git_executable=str(m["git_executable"]), external_scratch_root=str(m["scratch_root"]), maximum_corrective_retries=b["maximum_corrective_retries"], **vb).to_dict()
    ci = m["commit_identity"]
    lp = landing.seal_landing_policy({"policy_id": "activation_" + str(m["manifest_id"]), "repository_identity": m["repository_identity"], "canonical_repository_root": m["repository_root"], "external_state_root": m["state_root"], "git_executable": m["git_executable"], "publication_client_executable": m["publication_client_executable"], "commit_author_name": ci["author_name"], "commit_author_email": ci["author_email"], "commit_committer_name": ci["committer_name"], "commit_committer_email": ci["committer_email"], "commit_identity_reference": ci["reference"], "maximum_publication_attempts": b["maximum_attempts"], "constraints": ["publication_mode:" + m["publication_mode"], "remote_name:" + m["remote_name"], "base_ref:" + m["base_ref"], "tracked_base_ref:" + m["tracked_base_ref"], "title_prefix:" + m["commit_title_policy"]["prefix"], *["authority:" + a for a in auths]]})
    return {"standing_grant": grant, "selector_policy": sp, "foreman_policy": fc, "validation_policy": vp, "landing_policy": lp}


def render_profile_bundle(manifest_path: str | Path) -> dict[str, Any]:
    m = validate_manifest(_load(manifest_path)); output = _safe_output(m)
    if output.exists() and (not output.is_dir() or output.is_symlink()): raise ValueError("output_root_unsafe")
    output.mkdir(parents=True, mode=0o700, exist_ok=True)
    if os.name == "posix" and stat.S_IMODE(os.lstat(output).st_mode) != 0o700: raise ValueError("output_permissions_unsafe")
    artifacts = _artifacts(m); statuses = {}
    entries = []
    for role in sorted(artifacts):
        statuses[role] = _write(output / FILENAMES[role], artifacts[role])
        schema = artifacts[role]["schema_version"]
        identity = next((artifacts[role][k] for k in ("grant_id", "policy_id", "configuration_id") if k in artifacts[role]), None)
        entries.append({"role": role, "filename": FILENAMES[role], "schema_version": schema, "artifact_id": identity, "digest": bytes_digest(canonical_bytes(artifacts[role]) + b"\n")})
    index = {"schema_version": INDEX_SCHEMA, "bundle_id": "profile_" + str(m["manifest_id"]), "manifest_id": m["manifest_id"], "manifest_digest": m["manifest_digest"], "artifacts": entries, "bundle_digest": ""}
    index["bundle_digest"] = digest(index, "bundle_digest")
    statuses["bundle_index"] = _write(output / "bundle_index.json", index)
    return {"schema_version": "sentientos.maintenance_activation_profile_render:v1", "status": "profile_bundle_ready", "output_directory": str(output), "write_statuses": statuses, "bundle_digest": index["bundle_digest"]}


def _read_bundle(manifest_path: str | Path, evaluation_time: str) -> tuple[dict[str, Any], Path, dict[str, dict[str, Any]], dict[str, Any]]:
    m = validate_manifest(_load(manifest_path)); output = _safe_output(m); now = _timestamp(evaluation_time)
    if now < _timestamp(m["not_before"]) or now >= _timestamp(m["expires_at"]): raise ValueError("profile_outside_validity_window")
    artifacts = {r: _load(output / f) for r, f in FILENAMES.items()}; index = _load(output / "bundle_index.json")
    expected = _artifacts(m)
    if any(canonical_bytes(artifacts[r]) != canonical_bytes(expected[r]) for r in artifacts): raise ValueError("bundle_artifact_mismatch")
    if authority.verify_grant(artifacts["standing_grant"], evaluation_time=evaluation_time)["status"] != "grant_valid": raise ValueError("standing_grant_invalid")
    selector.build_policy(artifacts["selector_policy"]); foreman.LocalCodexForemanConfig.from_mapping(artifacts["foreman_policy"]); validation.ValidationPolicy.from_mapping(artifacts["validation_policy"]); landing.seal_landing_policy(artifacts["landing_policy"])
    if index.get("schema_version") != INDEX_SCHEMA or index.get("manifest_digest") != m["manifest_digest"] or index.get("bundle_digest") != digest(index, "bundle_digest"): raise ValueError("bundle_index_invalid")
    entries = {e["role"]: e for e in index.get("artifacts", [])}
    for role, filename in FILENAMES.items():
        if entries.get(role, {}).get("filename") != filename or entries[role].get("digest") != bytes_digest((output / filename).read_bytes()): raise ValueError("bundle_index_artifact_invalid")
    return m, output, artifacts, index


def verify_profile_bundle(manifest_path: str | Path, evaluation_time: str) -> dict[str, Any]:
    try:
        _, output, _, index = _read_bundle(manifest_path, evaluation_time)
        return {"schema_version": "sentientos.maintenance_activation_profile_verification:v1", "status": "profile_bundle_ready", "output_directory": str(output), "bundle_digest": index["bundle_digest"], "reason_codes": []}
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return {"schema_version": "sentientos.maintenance_activation_profile_verification:v1", "status": "profile_bundle_blocked", "reason_codes": [str(exc)]}


def activation_plan(manifest_path: str | Path, evaluation_time: str) -> dict[str, Any]:
    m, output, _, index = _read_bundle(manifest_path, evaluation_time); cli = str(Path(m["repository_root"]) / "scripts" / "maintenance_loop_activation.py"); config = str(output / "maintenance_loop_config.json")
    common = ["--config", config, "--evaluation-time", evaluation_time]
    commands = [
        [m["python_executable"], cli, "init-roots", "--repository-root", m["repository_root"], "--state-root", m["state_root"], "--workspace-root", m["workspace_root"], "--scratch-root", m["scratch_root"], "--inbox-root", m["inbox_root"]],
        [m["python_executable"], cli, "render-config", "--output", config, "--repository-root", m["repository_root"], "--state-root", m["state_root"], "--workspace-root", m["workspace_root"], "--scratch-root", m["scratch_root"], "--inbox-root", m["inbox_root"], "--standing-grant", str(output/FILENAMES["standing_grant"]), "--selector-policy", str(output/FILENAMES["selector_policy"]), "--foreman-policy", str(output/FILENAMES["foreman_policy"]), "--validation-policy", str(output/FILENAMES["validation_policy"]), "--landing-policy", str(output/FILENAMES["landing_policy"]), "--base-sha", m["base_sha"], "--tracked-base-ref", m["tracked_base_ref"], "--maximum-actions", str(m["budgets"]["maximum_actions"]), "--maximum-wall-clock-seconds", str(m["budgets"]["maximum_wall_clock_seconds"]), "--publication-retry-backoff-seconds", str(m["budgets"]["publication_retry_backoff_seconds"])],
        [m["python_executable"], cli, "doctor-live", *common], [m["python_executable"], cli, "smoke-idle", *common], [m["python_executable"], cli, "print-run-command", *common],
    ]
    return {"schema_version": "sentientos.maintenance_activation_profile_plan:v1", "status": "profile_bundle_ready", "bundle_digest": index["bundle_digest"], "argv": commands, "scheduler_installation": False}


def inspect_profile_bundle(manifest_path: str | Path, evaluation_time: str) -> dict[str, Any]:
    m, _, artifacts, index = _read_bundle(manifest_path, evaluation_time)
    return {"schema_version": "sentientos.maintenance_activation_profile_inspection:v1", "status": "profile_bundle_ready", "manifest": m, "artifacts": index["artifacts"], "validity_window": {"not_before": m["not_before"], "expires_at": m["expires_at"]}, "scope": {"allowed_path_prefixes": m["allowed_path_prefixes"], "forbidden_paths": m["forbidden_paths"], "allowed_candidate_kinds": m["allowed_candidate_kinds"]}, "authority_classes": m["authority_classes"], "budgets": m["budgets"], "landing_mode": m["publication_mode"], "canonical_validator_schemas": [a["schema_version"] for a in artifacts.values()]}


def write_manifest_template(path: str | Path) -> dict[str, Any]:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True); status = _write(p, manifest_template())
    return {"schema_version": TEMPLATE_SCHEMA, "status": "template_no_authority", "output": str(p.resolve()), "write_status": status}
