"""Deterministic, effect-inert configuration bridge for initial commissioning.

Only external directories and immutable JSON configuration are created.  No
maintenance runner, resident, approval, or commissioning API is invoked here.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
from pathlib import Path
from typing import Any, Mapping

from sentientos import maintenance_activation_profiles as profiles
from sentientos import maintenance_autonomy_cycle as autonomy
from sentientos import maintenance_candidate_collector as collector
from sentientos import maintenance_health_probe as health
from sentientos import maintenance_initial_posix_resident_commissioning as commissioning
from sentientos import maintenance_loop_activation as activation
from sentientos import maintenance_loop_watchdog as watchdog
from sentientos import maintenance_task_authority_lease as authority
from sentientos import maintenance_wake_cycle as wake
from sentientos import maintenance_wake_daemon_adoption as wake_daemon

MANIFEST_SCHEMA = "sentientos.maintenance_initial_resident_genesis_provisioning_manifest:v1"
TEMPLATE_SCHEMA = "sentientos.maintenance_initial_resident_genesis_provisioning_template:v1"
RESULT_SCHEMA = "sentientos.maintenance_initial_resident_genesis_provisioning_result:v1"
REMOTE_AUTHORITIES = {"remote_repository_read", "remote_ref_publish", "pull_request_publish", "remote_model_invocation"}
REQUIRED = {
    "schema_version", "manifest_id", "manifest_digest", "repository_identity", "repository_root",
    "base_sha", "base_ref", "tracked_base_ref", "python_executable", "git_executable",
    "codex_executable", "codex_home", "provisioning_root", "profile_output_root", "state_root",
    "workspace_root", "scratch_root", "inbox_root", "collector_state_root", "autonomy_state_root",
    "wake_state_root", "cadence_state_root", "health_state_root", "health_signal_root",
    "governed_improvement_signal_source_roots", "normalized_work_item_source_roots",
    "operator_reference", "approval_reference", "not_before", "expires_at", "candidate_kinds",
    "allowed_path_prefixes", "forbidden_paths", "authority_classes", "budgets", "validation_bounds",
    "publication_mode", "remote_name", "head_ref_prefix", "publication_client_executable",
    "commit_identity", "commit_title_policy", "implementation_backend", "maintenance_bounds",
    "collector", "health_probe", "autonomy", "wake", "wake_daemon", "commissioning",
}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value: Any, omitted: str | None = None) -> str:
    body = {k: v for k, v in value.items() if k != omitted} if omitted else value
    return "sha256:" + hashlib.sha256(canonical_bytes(body)).hexdigest()


def _load(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise ValueError("provisioning_manifest_not_regular")
    value = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(value, dict): raise ValueError("provisioning_manifest_not_object")
    return value


def _git(repo: Path, executable: str, *args: str) -> str:
    result = subprocess.run([executable, *args], cwd=repo, text=True, capture_output=True,
                            check=False, shell=False)
    if result.returncode: raise ValueError("git_inspection_failed:" + args[0])
    return result.stdout.strip()


def _external(path: Any, repo: Path) -> Path:
    raw = Path(str(path))
    if not raw.is_absolute(): raise ValueError("external_path_not_absolute")
    if raw.is_symlink() or any(p.is_symlink() for p in raw.parents if p.exists()):
        raise ValueError("external_path_symlink")
    resolved = raw.resolve(strict=False); git = (repo / ".git").resolve(strict=True)
    if resolved == repo or repo in resolved.parents or resolved == git or git in resolved.parents:
        raise ValueError("external_path_inside_repository")
    return resolved


def validate_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    m = dict(value)
    if set(m) != REQUIRED or m.get("schema_version") != MANIFEST_SCHEMA:
        raise ValueError("provisioning_manifest_closed_schema_invalid")
    if m.get("manifest_digest") != digest(m, "manifest_digest"):
        raise ValueError("provisioning_manifest_digest_invalid")
    if not isinstance(m["repository_identity"], str) or not m["repository_identity"].strip():
        raise ValueError("repository_identity_invalid")
    repo = Path(str(m["repository_root"]));
    if repo.is_symlink() or repo.resolve(strict=True) != repo or not (repo / ".git").exists():
        raise ValueError("repository_root_unsafe")
    m["repository_root"] = str(repo)
    if m["publication_mode"] == "local_fast_forward_base_ref":
        if m["base_ref"] != m["tracked_base_ref"]: raise ValueError("local_base_ref_mismatch")
        if set(m["authority_classes"]) & REMOTE_AUTHORITIES: raise ValueError("remote_authority_in_local_mode")
        if not {"repository_commit", "local_repository_base_advance"}.issubset(m["authority_classes"]):
            raise ValueError("local_landing_authority_missing")
    if any(x not in authority.AUTHORITY_CLASSES for x in m["authority_classes"]):
        raise ValueError("authority_classes_invalid")
    if not m["base_ref"] or not m["tracked_base_ref"]: raise ValueError("explicit_local_ref_required")
    git = str(Path(str(m["git_executable"])).resolve(strict=True))
    if _git(repo, git, "rev-parse", "HEAD") != m["base_sha"]: raise ValueError("base_sha_mismatch")
    try: selected = _git(repo, git, "rev-parse", "--verify", m["base_ref"])
    except ValueError as exc: raise ValueError("selected_ref_mismatch") from exc
    if selected != m["base_sha"]: raise ValueError("selected_ref_mismatch")
    if _git(repo, git, "status", "--porcelain=v1", "--untracked-files=all"): raise ValueError("repository_dirty")
    for key in ("python_executable", "git_executable", "codex_executable"):
        p = Path(str(m[key]));
        if not p.is_file() or str(p.resolve()) != str(p): raise ValueError(key + "_not_realpath")
    roots = [_external(m[k], repo) for k in (
        "provisioning_root", "profile_output_root", "state_root", "workspace_root", "scratch_root",
        "inbox_root", "collector_state_root", "autonomy_state_root", "wake_state_root",
        "cadence_state_root", "health_state_root", "health_signal_root", "codex_home")]
    roots += [_external(x, repo) for k in ("governed_improvement_signal_source_roots", "normalized_work_item_source_roots") for x in m[k]]
    return m


def load_manifest(path: str | Path) -> dict[str, Any]: return validate_manifest(_load(path))


def doctor(value: Mapping[str, Any]) -> dict[str, Any]:
    try:
        m = validate_manifest(value)
        return {"schema_version":"sentientos.maintenance_initial_resident_genesis_provisioning_doctor:v1",
                "status":"genesis_provisioning_ready", "manifest_digest":m["manifest_digest"],
                "reason_codes":[], "read_only":True}
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return {"schema_version":"sentientos.maintenance_initial_resident_genesis_provisioning_doctor:v1",
                "status":"genesis_provisioning_blocked", "reason_codes":[str(exc)], "read_only":True}


def _write(path: Path, value: Mapping[str, Any]) -> str:
    data = canonical_bytes(value) + b"\n"; path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists():
        if path.is_symlink() or path.read_bytes() != data: raise ValueError("configuration_output_conflict:" + str(path))
        return "reused"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as handle: handle.write(data); handle.flush(); os.fsync(handle.fileno())
    return "created"


def _mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink() or not path.is_dir() or (os.name == "posix" and stat.S_IMODE(os.lstat(path).st_mode) != 0o700):
        raise ValueError("external_root_unsafe:" + str(path))


def _paths(m: Mapping[str, Any]) -> dict[str, Path]:
    root = Path(m["provisioning_root"])
    return {"profile":root/"activation-profile-manifest.json", "watchdog":root/"maintenance-watchdog.json",
        "collector":root/"candidate-collector.json", "health":root/"health-probe.json",
        "autonomy":root/"autonomy-cycle.json", "wake":root/"wake-cycle.json",
        "adoption":root/"wake-adoption.json", "commissioning":root/"initial-resident-commissioning.json",
        "result":root/"genesis-provisioning-result.json"}


def render(value: Mapping[str, Any]) -> dict[str, Any]:
    m = validate_manifest(value); repo = Path(m["repository_root"]); paths = _paths(m)
    root_keys = ("provisioning_root","profile_output_root","state_root","workspace_root","scratch_root","inbox_root",
        "collector_state_root","autonomy_state_root","wake_state_root","cadence_state_root","health_state_root","health_signal_root","codex_home")
    for key in root_keys: _mkdir(Path(m[key]))
    for key in ("governed_improvement_signal_source_roots","normalized_work_item_source_roots"):
        for item in m[key]: _mkdir(Path(item))
    profile = {"schema_version":profiles.MANIFEST_SCHEMA, "manifest_id":m["manifest_id"]+":profile",
        "manifest_digest":"", "template_no_authority":False, "repository_identity":m["repository_identity"],
        "repository_root":str(repo), "base_sha":m["base_sha"], "allowed_candidate_kinds":m["candidate_kinds"],
        "allowed_path_prefixes":m["allowed_path_prefixes"], "forbidden_paths":m["forbidden_paths"],
        "authority_classes":m["authority_classes"], "budgets":m["budgets"], "operator_reference":m["operator_reference"],
        "approval_reference":m["approval_reference"], "not_before":m["not_before"], "expires_at":m["expires_at"],
        "state_root":m["state_root"], "workspace_root":m["workspace_root"], "scratch_root":m["scratch_root"],
        "inbox_root":m["inbox_root"], "codex_home":m["codex_home"], "codex_executable":m["codex_executable"],
        "git_executable":m["git_executable"], "python_executable":m["python_executable"],
        "validation_bounds":m["validation_bounds"], "publication_mode":m["publication_mode"],
        "remote_name":m["remote_name"], "tracked_base_ref":m["tracked_base_ref"], "base_ref":m["base_ref"],
        "head_ref_prefix":m["head_ref_prefix"], "publication_client_executable":m["publication_client_executable"],
        "commit_identity":m["commit_identity"], "commit_title_policy":m["commit_title_policy"],
        "output_directory":m["profile_output_root"]}
    profile["manifest_digest"] = profiles.digest(profile, "manifest_digest"); profiles.validate_manifest(profile)
    _write(paths["profile"], profile); profiles.render_profile_bundle(paths["profile"])
    checked = profiles.verify_profile_bundle(paths["profile"], m["commissioning"]["created_at"])
    if checked["status"] != "profile_bundle_ready": raise ValueError("profile_bundle_not_ready")
    files = profiles.FILENAMES; out = Path(m["profile_output_root"]); bounds=m["maintenance_bounds"]
    activation.render_config(paths["watchdog"], repository_root=repo, state_root=m["state_root"], workspace_root=m["workspace_root"],
        scratch_root=m["scratch_root"], inbox_root=m["inbox_root"], standing_grant=out/files["standing_grant"],
        selector_policy=out/files["selector_policy"], foreman_policy=out/files["foreman_policy"], validation_policy=out/files["validation_policy"],
        landing_policy=out/files["landing_policy"], base_sha=m["base_sha"], tracked_base_ref=m["tracked_base_ref"],
        implementation_backend=m["implementation_backend"], commissioned_local_activation=None,
        maximum_actions=bounds["maximum_actions"], maximum_wall_clock_seconds=bounds["maximum_wall_clock_seconds"],
        publication_retry_backoff_seconds=bounds["publication_retry_backoff_seconds"], stop_marker=Path(m["state_root"])/"STOP",
        control_journal=Path(m["state_root"])/"control.jsonl", base_cursor_journal=Path(m["state_root"])/"base-cursor.jsonl")
    c = collector.validate_config({"schema_version":collector.CONFIG_SCHEMA,"repository_identity":m["repository_identity"],"repository_root":str(repo),"base_sha":m["base_sha"],
        "activation_profile_bundle_manifest_path":str(paths["profile"]),"watchdog_configuration_path":str(paths["watchdog"]),"collector_state_root":m["collector_state_root"],
        "maintenance_candidate_inbox":m["inbox_root"],"governed_improvement_signal_source_roots":m["governed_improvement_signal_source_roots"],
        "normalized_work_item_source_roots":m["normalized_work_item_source_roots"],"allowed_source_schemas":m["collector"]["allowed_source_schemas"],
        "allowed_source_kinds":m["collector"]["allowed_source_kinds"],"maximum_source_records_per_scan":m["collector"]["maximum_source_records_per_scan"],
        "maximum_candidates_per_collection":m["collector"]["maximum_candidates_per_collection"],"maximum_input_bytes_per_record":m["collector"]["maximum_input_bytes_per_record"],
        "evaluation_time_required":True,"receipt_journal_path":str(Path(m["collector_state_root"])/"receipts.jsonl"),"stop_marker":str(Path(m["collector_state_root"])/"STOP")}); _write(paths["collector"],c)
    h = health.validate_config({"schema_version":health.CONFIG_SCHEMA,"repository_identity":m["repository_identity"],"repository_root":str(repo),"base_sha":m["base_sha"],
        **m["health_probe"],"probe_state_root":m["health_state_root"],"governed_signal_output_root":m["health_signal_root"],
        "evaluation_time":m["commissioning"]["created_at"],"receipt_journal_path":str(Path(m["health_state_root"])/"receipts.jsonl")}); _write(paths["health"],h)
    a = autonomy.validate_config({"schema_version":autonomy.CONFIG_SCHEMA,"repository_identity":m["repository_identity"],"repository_root":str(repo),"base_sha":m["base_sha"],
        "activation_profile_bundle_manifest_path":str(paths["profile"]),"collector_configuration_path":str(paths["collector"]),"watchdog_configuration_path":str(paths["watchdog"]),
        "external_cycle_state_root":m["autonomy_state_root"],"cycle_receipt_journal_path":str(Path(m["autonomy_state_root"])/"receipts.jsonl"),"stop_marker":str(Path(m["autonomy_state_root"])/"STOP"),
        "maximum_cycle_wall_clock_seconds":m["autonomy"]["maximum_cycle_wall_clock_seconds"],"maximum_collector_invocations_per_cycle":1,"maximum_watchdog_invocations_per_cycle":1,
        "maximum_candidates_collected_per_cycle":1,"remote_readiness_probe_required":m["publication_mode"] != "local_fast_forward_base_ref","evaluation_time_required":True}); _write(paths["autonomy"],a)
    w = wake.validate_config({"schema_version":wake.CONFIG_SCHEMA,"repository_identity":m["repository_identity"],"repository_root":str(repo),"base_sha":m["base_sha"],
        "health_probe_configuration_path":str(paths["health"]),"autonomy_cycle_configuration_path":str(paths["autonomy"]),"external_wake_state_root":m["wake_state_root"],
        "wake_receipt_journal_path":str(Path(m["wake_state_root"])/"receipts.jsonl"),"stop_marker":str(Path(m["wake_state_root"])/"STOP"),"evaluation_time":m["commissioning"]["created_at"]}); _write(paths["wake"],w)
    activation.render_wake_daemon_adoption(paths["adoption"], wake_config_path=paths["wake"], cadence_state_root=m["cadence_state_root"], enabled=m["wake_daemon"]["enabled"],
        cadence_interval_seconds=m["wake_daemon"]["cadence_interval_seconds"],schedule_anchor_utc=m["wake_daemon"]["schedule_anchor_utc"],initial_run_posture=m["wake_daemon"]["initial_run_posture"],
        maximum_cycles=m["wake_daemon"]["maximum_cycles"],maximum_daemon_wall_clock_seconds=m["wake_daemon"]["maximum_daemon_wall_clock_seconds"],shutdown_timeout_seconds=m["wake_daemon"]["shutdown_timeout_seconds"])
    adoption=wake_daemon.load_adoption(paths["adoption"]); tree=_git(repo,m["git_executable"],"rev-parse","HEAD^{tree}"); cm=m["commissioning"]
    commissioned={"schema_version":commissioning.MANIFEST_SCHEMA,"repository_identity":m["repository_identity"],"repository_root":str(repo),"expected_commit":m["base_sha"],"expected_tree":tree,
        "canonical_ref":m["base_ref"],"python_executable":m["python_executable"],"daemon_entrypoint":str(repo/"sentientosd.py"),"custody_root":cm["custody_root"],
        "profile_manifest_path":str(paths["profile"]),"profile_manifest_digest":profile["manifest_digest"],"profile_bundle_digest":checked["bundle_digest"],
        "initial_wake_adoption_path":str(paths["adoption"]),"initial_wake_adoption_digest":adoption["adoption_config_digest"],"operator_reference":m["operator_reference"],
        "approval_evidence_path":cm["approval_evidence_path"],"lineage_id":cm["lineage_id"],"created_at":cm["created_at"],"stop_marker":cm["stop_marker"],
        "environment_allowlist":cm["environment_allowlist"],"required_environment":cm["required_environment"],"maximum_handoffs":cm["maximum_handoffs"],
        "maximum_successful_transitions":cm["maximum_successful_transitions"],"maximum_wall_clock_seconds":cm["maximum_wall_clock_seconds"],
        "quiescence_timeout_seconds":cm["quiescence_timeout_seconds"],"readiness_timeout_seconds":cm["readiness_timeout_seconds"],"launch_timeout_seconds":cm["launch_timeout_seconds"],"manifest_digest":""}
    commissioned["manifest_digest"]=commissioning.digest(commissioned,"manifest_digest"); commissioning.validate_manifest(commissioned); _write(paths["commissioning"],commissioned)
    report=verify(m); _write(paths["result"],report); return report


def verify(value: Mapping[str, Any]) -> dict[str, Any]:
    m=validate_manifest(value); p=_paths(m); profile=profiles.validate_manifest(_load(p["profile"])); profiles.inspect_profile_bundle(p["profile"],m["commissioning"]["created_at"]); bundle=profiles.verify_profile_bundle(p["profile"],m["commissioning"]["created_at"])
    wc=watchdog.load_config(p["watchdog"]); cc=collector.load_config(p["collector"]); hc=health.load_config(p["health"]); ac=autonomy.load_config(p["autonomy"]); wk=wake.load_config(p["wake"]); ad=wake_daemon.load_adoption(p["adoption"]); cm=commissioning.load_manifest(p["commissioning"])
    agreements=(profile["repository_identity"]==cc["repository_identity"]==hc["repository_identity"]==ac["repository_identity"]==wk["repository_identity"]==m["repository_identity"],
        profile["base_sha"]==wc["base_sha"]==cc["base_sha"]==hc["base_sha"]==ac["base_sha"]==wk["base_sha"]==m["base_sha"], wc["tracked_base_ref"]==profile["tracked_base_ref"]==m["tracked_base_ref"],
        Path(cc["activation_profile_bundle_manifest_path"])==p["profile"],Path(ac["collector_configuration_path"])==p["collector"],Path(wk["health_probe_configuration_path"])==p["health"],Path(wk["autonomy_cycle_configuration_path"])==p["autonomy"],Path(ad["wake_config_path"])==p["wake"],cm["profile_manifest_digest"]==profile["manifest_digest"],cm["profile_bundle_digest"]==bundle["bundle_digest"],cm["initial_wake_adoption_digest"]==ad["adoption_config_digest"])
    if not all(agreements): raise ValueError("component_configuration_disagreement")
    reports={"profile":profiles.verify_profile_bundle(p["profile"],m["commissioning"]["created_at"]),"activation":activation.doctor_live(p["watchdog"],evaluation_time=m["commissioning"]["created_at"],probe_remote=False),"collector":collector.doctor(cc,evaluation_time=m["commissioning"]["created_at"]),"health":health.doctor(hc),"autonomy":autonomy.doctor(ac,evaluation_time=m["commissioning"]["created_at"]),"wake":wake.doctor(wk),"commissioning":commissioning.doctor(cm)}
    checks={key:str(report["status"]) for key,report in reports.items()}
    expected={"profile":"profile_bundle_ready","activation":"activation_ready","collector":"collector_ready","health":"health_probe_ready","autonomy":"autonomy_cycle_ready","wake":"maintenance_wake_ready","commissioning":"initial_resident_commissioning_ready"}
    if checks != expected: raise ValueError("genesis_graph_not_ready:"+json.dumps(reports,sort_keys=True))
    return {"schema_version":RESULT_SCHEMA,"status":"genesis_provisioning_verified","manifest_id":m["manifest_id"],"manifest_digest":m["manifest_digest"],"checks":checks,"commissioning_inputs":commissioning_inputs(m),"runtime_effects_performed":False,"resident_launched":False,"generation_zero_created":False}


def inspect(value: Mapping[str, Any]) -> dict[str, Any]:
    m=validate_manifest(value); p=_paths(m)
    return {"schema_version":"sentientos.maintenance_initial_resident_genesis_provisioning_inspection:v1","status":"genesis_provisioning_rendered" if all(x.is_file() for x in p.values()) else "genesis_provisioning_incomplete","paths":{k:str(v) for k,v in p.items()},"read_only":True}


def commissioning_inputs(value: Mapping[str, Any]) -> dict[str, Any]:
    m=validate_manifest(value); p=_paths(m); profile=profiles.validate_manifest(_load(p["profile"])); checked=profiles.verify_profile_bundle(p["profile"],m["commissioning"]["created_at"]); ad=wake_daemon.load_adoption(p["adoption"]); cm=commissioning.load_manifest(p["commissioning"])
    return {"repository_identity":m["repository_identity"],"base_sha":m["base_sha"],"base_tree":cm["expected_tree"],"canonical_ref":m["base_ref"],"profile_manifest_path":str(p["profile"]),"profile_manifest_digest":profile["manifest_digest"],"profile_bundle_digest":checked["bundle_digest"],"wake_adoption_path":str(p["adoption"]),"wake_adoption_digest":ad["adoption_config_digest"],"commissioning_manifest_path":str(p["commissioning"]),"commissioning_manifest_digest":cm["manifest_digest"],"commissioning_custody_root":cm["custody_root"],"approval_evidence_path":cm["approval_evidence_path"],"lineage_id":cm["lineage_id"]}


def template() -> dict[str, Any]:
    return {"schema_version":TEMPLATE_SCHEMA,"status":"template_no_authority","provisioning_manifest_schema":MANIFEST_SCHEMA,"required_fields":sorted(REQUIRED),"no_runtime_authority":True}


def write_template(path: str | Path) -> dict[str, Any]:
    target=Path(path); status=_write(target,template()); return {"status":"template_no_authority","path":str(target.resolve()),"write_status":status}
