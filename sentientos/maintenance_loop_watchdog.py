"""Bounded external coordinator for the repository maintenance loop.

The watchdog deliberately owns no implementation, validation, Git, or publication
logic.  A tick selects one transition from durable canonical observations and
dispatches it through a closed table of the repository's maintenance components.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
import subprocess
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from sentientos import maintenance_candidate_selector as selector
from sentientos import maintenance_candidate
from sentientos import maintenance_commit_publication as landing
from sentientos import maintenance_task_authority_lease as authority
from sentientos import maintenance_task_journal as task_journal
from sentientos import maintenance_validation_controller as validation
from sentientos import maintenance_implementation_agent as implementation_agent
from sentientos import maintenance_local_codex_foreman as foreman
from sentientos import maintenance_commissioned_local_agent as commissioned_agent
from sentientos.governed_local_model_invocation import GovernedLocalModelInvoker
from sentientos.local_model_production_commissioning import load_activation

CONFIG_SCHEMA = "sentientos.maintenance_watchdog_config:v1"
SCAN_SCHEMA = "sentientos.maintenance_watchdog_scan:v1"
DECISION_SCHEMA = "sentientos.maintenance_watchdog_decision:v1"
TICK_SCHEMA = "sentientos.maintenance_watchdog_tick_result:v1"
BRIEF_SCHEMA = "sentientos.maintenance_implementation_brief:v1"
BASE_CURSOR_SCHEMA = "sentientos.maintenance_base_cursor_event:v1"
CONTROL_SCHEMA = "sentientos.maintenance_watchdog_control_event:v1"
ZERO_DIGEST = "sha256:" + "0" * 64

PRIORITY = (
    "paused", "integrity_failure", "ambiguous_active_tasks", "recover_validation", "recover",
    "recover_implementation", "start_implementation", "observe_process", "close_task",
    "publish", "commit_enqueue", "validate", "prepare_implementation",
    "admit_candidate", "select_candidate", "idle",
)
TERMINAL = frozenset({"idle", "waiting", "paused", "blocked"})


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _closed(value: Mapping[str, Any], allowed: set[str], required: set[str]) -> None:
    if set(value) - allowed:
        raise ValueError("unknown_config_field")
    if not required.issubset(value):
        raise ValueError("missing_config_field")


def validate_config(value: Mapping[str, Any]) -> dict[str, Any]:
    required = {"schema_version", "repository_root", "state_root", "workspace_root",
                "scratch_root", "candidate_inbox_roots", "standing_grant",
                "selector_policy", "foreman_policy", "validation_policy",
                "landing_policy", "implementation_backend", "commissioned_local_activation",
                "commissioned_local_activation_digest",
                "maximum_active_tasks", "maximum_actions",
                "maximum_wall_clock_seconds", "publication_retry_backoff_seconds",
                "base_sha", "tracked_base_ref"}
    allowed = required | {"stop_marker", "control_journal", "base_cursor_journal",
                          "config_digest"}
    _closed(value, allowed, required)
    if value["schema_version"] != CONFIG_SCHEMA or int(value["maximum_active_tasks"]) != 1:
        raise ValueError("invalid_watchdog_config")
    if value["implementation_backend"] not in {"local_codex", "commissioned_local"}:
        raise ValueError("implementation_backend_invalid")
    activation = value["commissioned_local_activation"]
    activation_digest = value["commissioned_local_activation_digest"]
    if value["implementation_backend"] == "commissioned_local" and (not isinstance(activation, str) or not isinstance(activation_digest, str)):
        raise ValueError("commissioned_local_activation_required")
    if value["implementation_backend"] == "local_codex" and (activation is not None or activation_digest is not None):
        raise ValueError("commissioned_local_activation_forbidden")
    if int(value["maximum_actions"]) < 1 or int(value["maximum_wall_clock_seconds"]) < 1:
        raise ValueError("invalid_watchdog_bounds")
    if int(value["publication_retry_backoff_seconds"]) < 0:
        raise ValueError("invalid_publication_backoff")
    result = dict(value)
    repo = Path(str(value["repository_root"])).resolve(strict=True)
    git = (repo / ".git").resolve(strict=True)
    roots = [Path(str(value[k])) for k in ("state_root", "workspace_root", "scratch_root")]
    roots += [Path(str(p)) for p in value["candidate_inbox_roots"]]
    for root in roots:
        if root.is_symlink():
            raise ValueError("custody_root_symlink")
        resolved = root.resolve(strict=True)
        if resolved == repo or repo in resolved.parents or resolved == git or git in resolved.parents:
            raise ValueError("custody_root_inside_repository")
        if not stat.S_ISDIR(os.lstat(root).st_mode):
            raise ValueError("custody_root_not_directory")
    result["repository_root"] = str(repo)
    result["candidate_inbox_roots"] = sorted(str(Path(p).resolve()) for p in value["candidate_inbox_roots"])
    unsigned = {k: v for k, v in result.items() if k != "config_digest"}
    expected = digest(unsigned)
    if value.get("config_digest") not in (None, "", expected):
        raise ValueError("config_digest_mismatch")
    result["config_digest"] = expected
    return result


def load_config(path: str | Path) -> dict[str, Any]:
    return validate_config(json.loads(Path(path).read_text(encoding="utf-8")))


def _json_files(root: Path) -> list[dict[str, Any]]:
    records = []
    for path in sorted(root.glob("*.json"), key=lambda p: p.name):
        if path.is_symlink() or not path.is_file():
            records.append({"path": str(path), "status": "integrity_failure"})
            continue
        raw = path.read_bytes()
        try:
            payload = json.loads(raw)
            records.append({"path": str(path), "status": "ready", "digest": "sha256:" + hashlib.sha256(raw).hexdigest(), "payload": payload})
        except (ValueError, UnicodeDecodeError):
            records.append({"path": str(path), "status": "integrity_failure", "digest": "sha256:" + hashlib.sha256(raw).hexdigest()})
    return records


def _artifact(path: Path) -> dict[str, Any]:
    """Read an immutable JSON artifact and bind its byte identity."""
    raw = path.read_bytes()
    record: dict[str, Any] = {"path": str(path), "digest": "sha256:" + hashlib.sha256(raw).hexdigest()}
    try:
        record.update(status="ready", payload=json.loads(raw))
    except (ValueError, UnicodeDecodeError):
        record["status"] = "integrity_failure"
    return record


def _canonical_artifacts(state: Path) -> list[dict[str, Any]]:
    # These are the custody locations owned by the existing components.  Do not
    # broaden this to arbitrary state-root JSON: in particular, legacy summary
    # files are deliberately invisible to the production decision loop.
    names = (
        "maintenance_candidate_sets", "maintenance_selections", "maintenance_leases",
        "maintenance_implementation_briefs", "maintenance_implementation_requests",
        "maintenance_agent_sessions", "maintenance_agent_results", "maintenance_worktrees",
        "maintenance_local_codex_invocations", "maintenance_local_codex_results",
        "maintenance_commissioned_local_results",
        "maintenance_codex_invocations", "maintenance_codex_results",
        "maintenance_change_manifests", "maintenance_validation_plans",
        "maintenance_validation_cycles", "maintenance_validation_command_results",
        "maintenance_validation_results", "maintenance_commit_plans",
        "maintenance_commit_results", "maintenance_publication_requests",
        "maintenance_publication_attempts", "maintenance_publication_results",
    )
    records: list[dict[str, Any]] = []
    for name in names:
        root = state / name
        if root.is_symlink():
            records.append({"path": str(root), "status": "integrity_failure"})
        elif root.exists():
            records.extend(_artifact(p) for p in sorted(root.glob("*.json")) if p.is_file() and not p.is_symlink())
    return records


def _by_schema(records: Sequence[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    result: dict[str, list[Mapping[str, Any]]] = {}
    for record in records:
        schema = str(record.get("payload", {}).get("schema_version", ""))
        result.setdefault(schema, []).append(record)
    return result


def scan(config: Mapping[str, Any], *, evaluation_time: str) -> dict[str, Any]:
    cfg = validate_config(config)
    state = Path(cfg["state_root"])
    candidates = [r for root in cfg["candidate_inbox_roots"] for r in _json_files(Path(root))]
    discovered = task_journal.discover_maintenance_task_snapshots(
        state, repo_root=cfg["repository_root"], evaluation_time=evaluation_time)
    snapshots = [dict(item.get("snapshot", item)) for item in discovered]
    artifacts = _canonical_artifacts(state)
    active = [s for s in snapshots if not s.get("terminal")]
    integrity = [s for s in snapshots if s.get("journal_integrity_status") != "journal_ready"]
    integrity.extend(r for r in artifacts if r.get("status") != "ready")
    # Bind journal claims to the corresponding immutable artifact.  A claimed
    # digest that cannot be found is not interpreted as merely "not ready".
    artifact_digests = {str(r.get("payload", {}).get(k)) for r in artifacts for k in r.get("payload", {}) if k.endswith("_digest")}
    for snapshot in snapshots:
        for key in ("active_lease_digest",):
            claimed = snapshot.get(key)
            if claimed and claimed not in artifact_digests:
                integrity.append({"task_id": snapshot.get("task_id"), "reason": "artifact_journal_disagreement", "field": key})
    observations = {"task_snapshots": snapshots, "active_tasks": active,
                    "canonical_artifacts": artifacts, "integrity_failures": integrity}
    control = inspect_control(cfg)
    stop = Path(cfg.get("stop_marker") or state / "STOP")
    result = {"schema_version": SCAN_SCHEMA, "config_digest": cfg["config_digest"],
              "evaluation_time": evaluation_time, "stop_marker_present": stop.exists(),
              "control": control, "candidates": candidates, "observations": observations}
    result["scan_digest"] = digest(result)
    return result


def decide(config: Mapping[str, Any], scan_result: Mapping[str, Any]) -> dict[str, Any]:
    cfg = validate_config(config)
    if scan_result.get("config_digest") != cfg["config_digest"]:
        raise ValueError("scan_config_mismatch")
    obs = scan_result.get("observations", {})
    active = obs.get("active_tasks") or []
    candidate_bad = any(x.get("status") == "integrity_failure" for x in scan_result.get("candidates", []))
    schemas = _by_schema(obs.get("canonical_artifacts", []))
    task_id = str(active[0].get("task_id", "")) if len(active) == 1 else ""
    def owned(schema: str) -> list[Mapping[str, Any]]:
        return [r for r in schemas.get(schema, []) if r.get("payload", {}).get("task_id") == task_id]
    requests = owned(implementation_agent.REQUEST_SCHEMA)
    sessions = owned(implementation_agent.SESSION_SCHEMA)
    foreman_results = owned(foreman.RESULT_SCHEMA) + owned(commissioned_agent.RESULT_SCHEMA)
    ready = any(r.get("payload", {}).get("status") == "implementation_ready_for_validation" for r in foreman_results)
    interrupted = bool(foreman_results) and not ready
    incomplete_session = bool(sessions) and bool(active) and not active[0].get("active_attempt") and not ready
    consumed_revisions = {str(s.get("candidate_revision_digest")) for s in obs.get("task_snapshots", [])}
    admissible_selections = [r for r in schemas.get(selector.SELECTION_SCHEMA, [])
        if r.get("payload", {}).get("result_status") == "ready_for_scope_admission"
        and str(r.get("payload", {}).get("selected_candidate_revision_digest")) not in consumed_revisions]
    inbox_revisions = {str(c.get("payload", {}).get("candidate_revision_digest"))
        for c in scan_result.get("candidates", []) if c.get("status") == "ready"}
    checks = {
        "paused": bool(scan_result.get("stop_marker_present") or scan_result.get("control", {}).get("paused")),
        "integrity_failure": candidate_bad or bool(obs.get("integrity_failures")),
        "ambiguous_active_tasks": len(active) > 1,
        "recover_validation": any(s.get("active_validation_cycle") for s in active),
        "recover": any(s.get("recovery_state") == "started" or s.get("active_publication_attempt") for s in active),
        "recover_implementation": interrupted or incomplete_session,
        "start_implementation": bool(requests) and not sessions,
        "observe_process": bool(sessions) and not foreman_results and any(s.get("active_attempt") for s in active),
        "close_task": any(s.get("lifecycle_state") == "publication_succeeded" for s in active),
        "publish": any(s.get("lifecycle_state") in {"commit_recorded", "publication_failed"} for s in active),
        "commit_enqueue": any(s.get("lifecycle_state") == "ready_to_commit" for s in active),
        "validate": ready,
        "prepare_implementation": any(s.get("lifecycle_state") == "lease_bound" for s in active) and not requests,
        "admit_candidate": not active and bool(admissible_selections),
        "select_candidate": not active and bool(inbox_revisions - consumed_revisions), "idle": True,
    }
    transition = next(item for item in PRIORITY if checks[item])
    status = "paused" if transition == "paused" else ("blocked" if transition in {"integrity_failure", "ambiguous_active_tasks"} else ("idle" if transition == "idle" else "action_ready"))
    result = {"schema_version": DECISION_SCHEMA, "config_digest": cfg["config_digest"],
              "scan_digest": scan_result.get("scan_digest"), "transition": transition, "status": status}
    result["decision_digest"] = digest(result)
    return result


def build_implementation_brief(candidate: Mapping[str, Any], admission: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    brief = {"schema_version": BRIEF_SCHEMA, "candidate_id": candidate.get("candidate_id"),
             "candidate_revision_digest": candidate.get("candidate_revision_digest"),
             "objective": candidate.get("objective"), "subject_paths": sorted(candidate.get("declared_subject_paths", [])),
             "validation_expectations": sorted(candidate.get("declared_validation_expectations", [])),
             "admission_digest": admission.get("admission_digest"), "base_sha": config.get("base_sha")}
    brief["brief_digest"] = digest(brief)
    return brief


def _append_chain(path: Path, schema: str, event_type: str, evaluation_time: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    events = [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []
    previous = events[-1]["event_digest"] if events else ZERO_DIGEST
    event = {"schema_version": schema, "sequence": len(events) + 1, "event_type": event_type,
             "recorded_at": evaluation_time, "previous_event_digest": previous, "payload": dict(payload)}
    event["event_digest"] = digest(event)
    with path.open("ab") as handle:
        handle.write(canonical_json_bytes(event) + b"\n"); handle.flush(); os.fsync(handle.fileno())
    return event


def control(config: Mapping[str, Any], action: str, *, evaluation_time: str) -> dict[str, Any]:
    if action not in {"pause", "resume"}: raise ValueError("invalid_control_action")
    cfg = validate_config(config)
    return _append_chain(Path(cfg.get("control_journal") or Path(cfg["state_root"]) / "watchdog_control.jsonl"), CONTROL_SCHEMA, action, evaluation_time, {})


def inspect_control(config: Mapping[str, Any]) -> dict[str, Any]:
    path = Path(config.get("control_journal") or Path(str(config["state_root"])) / "watchdog_control.jsonl")
    events = [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []
    previous = ZERO_DIGEST
    for event in events:
        supplied = event.get("event_digest"); unsigned = {k: v for k, v in event.items() if k != "event_digest"}
        if event.get("previous_event_digest") != previous or supplied != digest(unsigned):
            return {"status": "integrity_failure", "paused": True, "events": events}
        previous = supplied
    return {"status": "ready", "paused": bool(events and events[-1]["event_type"] == "pause"), "events": events}


def _configured(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(k): v for k, v in value.items()}
    loaded = json.loads(Path(str(value)).read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("configured_artifact_not_object")
    return {str(k): v for k, v in loaded.items()}


def _write_once(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = canonical_json_bytes(value) + b"\n"
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError("immutable_artifact_conflict")
        return
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data); handle.flush(); os.fsync(handle.fileno())


def _write_bytes_once(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.is_symlink() or path.read_bytes() != data: raise ValueError("immutable_artifact_conflict")
        return
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data); handle.flush(); os.fsync(handle.fileno())


def _select(cfg: Mapping[str, Any], scanned: Mapping[str, Any], evaluation_time: str) -> dict[str, Any]:
    payloads = [r["payload"] for r in scanned["candidates"] if r.get("status") == "ready"]
    sets = [p for p in payloads if p.get("schema_version") == maintenance_candidate.CANDIDATE_SET_SCHEMA]
    candidate_set = sets[0] if sets else maintenance_candidate.normalize_candidate_set(
        [selector.candidate_from_dict(p) for p in payloads])
    policy = selector.build_policy(_configured(cfg["selector_policy"]))
    selected = selector.select_candidate(candidate_set, policy, journal_state_root=cfg["state_root"])
    root = Path(cfg["state_root"])
    _write_once(root / "maintenance_candidate_sets" / f"{candidate_set['aggregate_digest'].split(':')[-1]}.json", candidate_set)
    _write_once(root / "maintenance_selections" / f"{selected['selection_digest'].split(':')[-1]}.json", selected)
    return {"status": selected.get("status", "selection_completed"), "selection": selected}


def _admit(cfg: Mapping[str, Any], scanned: Mapping[str, Any], evaluation_time: str) -> dict[str, Any]:
    schemas = _by_schema(scanned["observations"]["canonical_artifacts"])
    selections = [r["payload"] for r in schemas[selector.SELECTION_SCHEMA] if r["payload"].get("result_status") == "ready_for_scope_admission"]
    if len(selections) != 1: raise ValueError("canonical_selection_ambiguous")
    selected = selections[0]
    candidate_sets = schemas[maintenance_candidate.CANDIDATE_SET_SCHEMA]
    wanted = selected.get("candidate_set_digest")
    candidate_set = next(r["payload"] for r in candidate_sets if r["payload"].get("aggregate_digest") == wanted)
    return authority.admit_selected_candidate(
        state_root=cfg["state_root"], candidate_set=candidate_set, selection=selected,
        operator_grant=_configured(cfg["standing_grant"]), evaluation_time=evaluation_time,
        repo_root=cfg["repository_root"])


def _lease_for(snapshot: Mapping[str, Any], cfg: Mapping[str, Any]) -> dict[str, Any]:
    return authority.load_lease(cfg["state_root"], str(snapshot["active_lease_id"]), repo_root=cfg["repository_root"])


def _owned(scanned: Mapping[str, Any], schema: str, task_id: str) -> list[dict[str, Any]]:
    return [dict(r["payload"]) for r in scanned["observations"]["canonical_artifacts"]
            if r.get("payload", {}).get("schema_version") == schema
            and r.get("payload", {}).get("task_id") == task_id]


def _prepare_implementation(cfg: Mapping[str, Any], scanned: Mapping[str, Any], evaluation_time: str) -> dict[str, Any]:
    snapshot = scanned["observations"]["active_tasks"][0]; lease = _lease_for(snapshot, cfg)
    schemas = _by_schema(scanned["observations"]["canonical_artifacts"])
    selection = next(dict(r["payload"]) for r in schemas[selector.SELECTION_SCHEMA]
                     if r["payload"].get("selection_digest") == lease["selection_digest"])
    candidate_set = next(dict(r["payload"]) for r in schemas[maintenance_candidate.CANDIDATE_SET_SCHEMA]
                         if r["payload"].get("aggregate_digest") == lease["candidate_set_digest"])
    candidate = next(dict(c) for c in candidate_set.get("canonical_candidates", ())
                     if c.get("candidate_id") == lease["candidate_id"]
                     and c.get("candidate_revision_digest") == lease["candidate_revision_digest"])
    brief = build_implementation_brief(candidate, {"admission_digest": lease["lease_digest"]}, cfg)
    brief.update(task_id=lease["task_id"], lease_id=lease["lease_id"], lease_digest=lease["lease_digest"],
                 selection_digest=selection["selection_digest"], admitted_scope_digest=lease["admitted_scope_digest"],
                 constraints=list(candidate.get("declared_constraints", ())), authority_classes=list(lease["authority_classes"]),
                 attempt_ordinal=1, corrective_retry_ordinal=0,
                 budgets={"maximum_file_count": lease["maximum_file_count"], "maximum_changed_line_count": lease["maximum_changed_line_count"],
                          "maximum_implementation_seconds": lease["maximum_implementation_seconds"], "maximum_validation_seconds": lease["maximum_validation_seconds"]})
    brief["brief_digest"] = digest({k: v for k, v in brief.items() if k != "brief_digest"})
    instruction = ("Objective:\n" + str(candidate["objective"]) + "\n\nAdmitted paths:\n" +
                   "".join(f"- {p}\n" for p in lease["admitted_subject_paths"]) + "\nValidation expectations:\n" +
                   "".join(f"- {v}\n" for v in lease["validation_expectations"]) + "\nConstraints:\n" +
                   "".join(f"- {v}\n" for v in candidate.get("declared_constraints", ())) +
                   "\nDo not commit, push, publish, access credentials, expand scope, or wait for hosted checks.\n").encode("utf-8")
    root = Path(cfg["state_root"]); task = str(lease["task_id"])
    _write_once(root / "maintenance_implementation_briefs" / (task + ".json"), brief)
    instruction_ref = "maintenance_implementation_instructions/" + task + ".txt"
    _write_bytes_once(root / instruction_ref, instruction)
    backend = str(cfg["implementation_backend"])
    driver_id = foreman.LocalCodexDriver.driver_id if backend == "local_codex" else commissioned_agent.CommissionedLocalDriver.driver_id
    request = implementation_agent.seal_request({
        "task_id": task, "lease_id": lease["lease_id"], "lease_digest": lease["lease_digest"], "candidate_id": lease["candidate_id"],
        "candidate_revision_digest": lease["candidate_revision_digest"], "canonical_candidate_digest": lease["canonical_candidate_digest"],
        "admitted_scope_digest": lease["admitted_scope_digest"], "repository_identity": lease["repository_identity"], "base_sha": lease["base_sha"],
        "driver_id": driver_id, "driver_kind": backend, "attempt_ordinal": 1, "corrective_retry_ordinal": 0,
        "implementation_contract_digest": brief["brief_digest"], "bounded_objective": candidate["objective"],
        "subject_paths": list(lease["admitted_subject_paths"]), "validation_expectations": list(lease["validation_expectations"]),
        "requested_authority_classes": list(lease["authority_classes"]), "implementation_time_ceiling_seconds": lease["maximum_implementation_seconds"],
        "wall_clock_deadline": lease["expires_at"], "external_instruction_artifact_reference": instruction_ref,
        "explicit_constraints": list(candidate.get("declared_constraints", ())) + ["brief_digest=" + brief["brief_digest"]],
    }, instruction_artifact_root=root)
    _write_once(root / "maintenance_implementation_requests" / (task + ".json"), request)
    return {"status": "implementation_prepared", "brief_digest": brief["brief_digest"], "request_digest": request["request_digest"]}


def _foreman_config(cfg: Mapping[str, Any]) -> foreman.LocalCodexForemanConfig:
    result = foreman.LocalCodexForemanConfig.from_mapping(_configured(cfg["foreman_policy"]))
    if result.repository_root != Path(cfg["repository_root"]) or result.external_state_root != Path(cfg["state_root"]) or result.external_workspace_root != Path(cfg["workspace_root"]):
        raise ValueError("foreman_configuration_custody_mismatch")
    return result


def _commissioned_driver(cfg: Mapping[str, Any]) -> tuple[commissioned_agent.CommissionedLocalDriver, Any]:
    """Reconstruct only the immutable activation explicitly bound in config."""
    activation = Path(str(cfg["commissioned_local_activation"]))
    if activation.is_symlink() or not activation.is_absolute() or not activation.is_file():
        raise ValueError("commissioned_local_activation_invalid")
    actual_digest = "sha256:" + hashlib.sha256(activation.read_bytes()).hexdigest()
    if actual_digest != cfg["commissioned_local_activation_digest"]:
        raise ValueError("commissioned_local_activation_digest_mismatch")
    model, authority_map = load_activation(activation)
    invoker = GovernedLocalModelInvoker(model=model, authority_map=authority_map,
        runtime_root=Path(str(cfg["state_root"])) / "maintenance_governed_local_invocations")
    return commissioned_agent.CommissionedLocalDriver(invoker), model


def _driver(cfg: Mapping[str, Any]) -> tuple[implementation_agent.EffectfulImplementationAgentDriver, Any | None]:
    if cfg["implementation_backend"] == "local_codex":
        return foreman.LocalCodexDriver(), None
    return _commissioned_driver(cfg)


def _start_implementation(cfg: Mapping[str, Any], scanned: Mapping[str, Any], evaluation_time: str) -> dict[str, Any]:
    snapshot = scanned["observations"]["active_tasks"][0]; task = str(snapshot["task_id"]); request = _owned(scanned, implementation_agent.REQUEST_SCHEMA, task)[0]
    driver, model = _driver(cfg)
    try:
        return implementation_agent.start_implementation_agent_session(state_root=cfg["state_root"], lease_id=str(snapshot["active_lease_id"]),
                request=request, driver=driver, evaluation_time=evaluation_time, repo_root=cfg["repository_root"])
    finally:
        if model is not None: model.close()


def _observe_implementation(cfg: Mapping[str, Any], scanned: Mapping[str, Any], evaluation_time: str) -> dict[str, Any]:
    snapshot = scanned["observations"]["active_tasks"][0]; task = str(snapshot["task_id"])
    session = _owned(scanned, implementation_agent.SESSION_SCHEMA, task)[0]
    request = _owned(scanned, implementation_agent.REQUEST_SCHEMA, task)[0]
    driver, model = _driver(cfg)
    try:
        result = implementation_agent.execute_implementation_agent(driver, config=_foreman_config(cfg),
            lease=_lease_for(snapshot, cfg), request=request, session=session,
            artifact_root=Path(cfg["state_root"]), evaluation_time=evaluation_time)
    finally:
        if model is not None: model.close()
    if result.get("status") == "implementation_ready_for_validation":
        current = task_journal.materialize_snapshot(cfg["state_root"], task, repo_root=cfg["repository_root"], evaluation_time=evaluation_time)
        if current.get("implementation_result", {}).get("status") == "completed": return result
        payload = {k: result.get(k) for k in ("session_id", "result_digest", "worktree_descriptor_digest", "invocation_digest", "transcript_digest", "final_message_digest", "change_manifest_digest", "patch_digest", "codex_thread_id", "measured_effect_flags", "validation_pending")}
        payload.update(repository_mutation_performed=True, validation_performed=False)
        event_id = "mevent_" + hashlib.sha256(canonical_json_bytes(payload)).hexdigest()[:32]
        appended = task_journal.append_event(cfg["state_root"], "implementation_completed", task_id=task, payload=payload,
                    event_id=event_id, recorded_at=evaluation_time, repository_sha=str(snapshot["base_sha"]),
                    repo_root=cfg["repository_root"], evaluation_time=evaluation_time)
        if appended.status not in {"event_appended", "event_already_recorded"}:
            return {"status": "blocked", "reason": appended.reason_code or "implementation_terminal_journal_failed"}
    return result


def _recover_implementation(cfg: Mapping[str, Any], scanned: Mapping[str, Any], evaluation_time: str) -> dict[str, Any]:
    snapshot = scanned["observations"]["active_tasks"][0]; task = str(snapshot["task_id"])
    request = _owned(scanned, implementation_agent.REQUEST_SCHEMA, task)[0]
    sessions = _owned(scanned, implementation_agent.SESSION_SCHEMA, task)
    if not sessions or not snapshot.get("active_attempt"):
        return _start_implementation(cfg, scanned, evaluation_time)
    if cfg["implementation_backend"] == "commissioned_local":
        driver, model = _driver(cfg)
        try:
            return implementation_agent.execute_implementation_agent(driver, config=_foreman_config(cfg),
                lease=_lease_for(snapshot, cfg), request=request, session=sessions[0],
                artifact_root=Path(cfg["state_root"]), evaluation_time=evaluation_time)
        finally:
            if model is not None: model.close()
    result = foreman.resume_local_codex_session(_foreman_config(cfg), _lease_for(snapshot, cfg), request, sessions[0], Path(cfg["state_root"]), evaluation_time)
    if result.get("status") == "foreman_recovery_unavailable" and not result.get("codex_thread_id"):
        return {"status": "blocked", "reason": "missing_codex_thread_id"}
    return result


def _one_bound(items: Sequence[Mapping[str, Any]], reason: str, **bindings: Any) -> dict[str, Any]:
    matches = [dict(item) for item in items if all(item.get(key) == value for key, value in bindings.items())]
    if len(matches) != 1:
        raise ValueError(reason)
    return matches[0]


def _validate(cfg: Mapping[str, Any], scanned: Mapping[str, Any], evaluation_time: str) -> dict[str, Any]:
    try:
        policy = validation.ValidationPolicy.from_mapping(_configured(cfg["validation_policy"]))
    except (ValueError, OSError, json.JSONDecodeError):
        return {"status": "waiting", "reason": "canonical_component_state_not_ready"}
    snapshot = scanned["observations"]["active_tasks"][0]
    task = str(snapshot["task_id"]); lease = _lease_for(snapshot, cfg)
    result_schema = foreman.RESULT_SCHEMA if cfg["implementation_backend"] == "local_codex" else commissioned_agent.RESULT_SCHEMA
    results = [r for r in _owned(scanned, result_schema, task)
               if r.get("status") == "implementation_ready_for_validation"]
    if len(results) != 1: raise ValueError("canonical_foreman_result_ambiguous")
    impl = results[0]
    session = _one_bound(_owned(scanned, implementation_agent.SESSION_SCHEMA, task),
                         "canonical_session_ambiguous", session_id=impl.get("session_id"),
                         lease_id=lease["lease_id"], lease_digest=lease["lease_digest"])
    impl.update(attempt_id=session["attempt_id"], attempt_ordinal=session["attempt_ordinal"],
                corrective_retry_ordinal=session["corrective_retry_ordinal"])
    worktree = _one_bound(_owned(scanned, foreman.WORKTREE_SCHEMA, task),
                          "canonical_worktree_ambiguous", session_id=session["session_id"],
                          lease_id=lease["lease_id"], lease_digest=lease["lease_digest"],
                          worktree_digest=impl["worktree_descriptor_digest"])
    manifest = _one_bound(_owned(scanned, foreman.CHANGE_SCHEMA, task),
                          "canonical_change_manifest_ambiguous", session_id=session["session_id"],
                          manifest_digest=impl["change_manifest_digest"])
    request = _one_bound(_owned(scanned, implementation_agent.REQUEST_SCHEMA, task),
                         "canonical_request_ambiguous", lease_id=lease["lease_id"],
                         lease_digest=lease["lease_digest"])
    recovery_plan = None
    if snapshot.get("active_validation_cycle"):
        cycle = snapshot["active_validation_cycle"]
        recovery_plan = _one_bound(_owned(scanned, validation.PLAN_SCHEMA, task),
            "canonical_validation_recovery_plan_ambiguous",
            validation_ref_id=cycle.get("validation_ref_id"), plan_digest=cycle.get("plan_digest"),
            attempt_id=cycle.get("attempt_id"), implementation_session_id=cycle.get("session_id"),
            worktree_descriptor_digest=cycle.get("worktree_descriptor_digest"),
            change_manifest_digest=cycle.get("change_manifest_digest"))
    continuation = None
    model = None
    if cfg["implementation_backend"] == "commissioned_local":
        driver, model = _driver(cfg)
        continuation = lambda envelope: implementation_agent.execute_implementation_agent(
            driver, config=_foreman_config(cfg), lease=lease, request=request, session=session,
            artifact_root=Path(cfg["state_root"]), evaluation_time=evaluation_time,
            validation_feedback=(envelope,))
    try:
        return validation.advance_validation_controller(state_root=Path(cfg["state_root"]),
            repository_root=Path(cfg["repository_root"]), policy=policy,
            lease=lease, implementation_result=impl, worktree=worktree, change_manifest=manifest,
            request=request, session=session, foreman_config=_foreman_config(cfg), evaluation_time=evaluation_time,
            recovery_plan=recovery_plan, corrective_continuation=continuation)
    finally:
        if model is not None: model.close()


def _commit(cfg: Mapping[str, Any], scanned: Mapping[str, Any], evaluation_time: str) -> dict[str, Any]:
    snapshot = scanned["observations"]["active_tasks"][0]; lease = _lease_for(snapshot, cfg)
    state = Path(cfg["state_root"])
    readiness = snapshot.get("commit_readiness", {}).get("payload", {})
    plans = _owned(scanned, validation.PLAN_SCHEMA, str(snapshot["task_id"]))
    plan = _one_bound(plans, "canonical_commit_plan_binding_missing",
        validation_ref_id=readiness.get("validation_ref_id"), plan_digest=readiness.get("plan_digest"),
        attempt_id=readiness.get("attempt_id"), worktree_descriptor_digest=readiness.get("worktree_descriptor_digest"),
        change_manifest_digest=readiness.get("change_manifest_digest"))
    validation_result = _one_bound(_owned(scanned, validation.RESULT_SCHEMA, str(snapshot["task_id"])),
        "canonical_commit_validation_result_missing", validation_ref_id=plan["validation_ref_id"],
        plan_digest=plan["plan_digest"], result_digest=readiness.get("result_digest"),
        terminal_status="validation_ready_for_commit")
    worktree = _one_bound(_owned(scanned, foreman.WORKTREE_SCHEMA, str(snapshot["task_id"])),
        "canonical_commit_worktree_missing", session_id=plan["implementation_session_id"],
        lease_id=lease["lease_id"], lease_digest=lease["lease_digest"],
        worktree_digest=plan["worktree_descriptor_digest"])
    return landing.create_commit_and_enqueue(
        state_root=state, repository_root=cfg["repository_root"],
        worktree_root=worktree["worktree_root"], lease=lease,
        validation_result=validation_result,
        landing_policy=_configured(cfg["landing_policy"]), evaluation_time=evaluation_time)


def _publish(cfg: Mapping[str, Any], scanned: Mapping[str, Any], evaluation_time: str) -> dict[str, Any]:
    snapshot = scanned["observations"]["active_tasks"][0]; lease = _lease_for(snapshot, cfg)
    queued = landing.list_queued_requests(cfg["state_root"], repo_root=cfg["repository_root"])
    if not queued: raise ValueError("canonical_publication_request_missing")
    return landing.publish_one_maintenance_request(
        state_root=cfg["state_root"], repository_root=cfg["repository_root"], lease=lease,
        landing_policy=_configured(cfg["landing_policy"]), publication_id=queued[0]["publication_id"],
        evaluation_time=evaluation_time)


def _close(cfg: Mapping[str, Any], scanned: Mapping[str, Any], evaluation_time: str) -> dict[str, Any]:
    snapshot = scanned["observations"]["active_tasks"][0]
    commit = str(snapshot.get("commit_reference", {}).get("payload", {}).get("commit_sha") or "")
    if not commit:
        return {"status": "blocked", "reason": "publication_commit_binding_missing"}
    observed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, str(cfg["tracked_base_ref"])],
        cwd=cfg["repository_root"], capture_output=True, check=False).returncode == 0
    if not observed:
        return {"status": "waiting", "reason": "verified_base_advancement_required"}
    event = _append_chain(
        Path(cfg.get("base_cursor_journal") or Path(cfg["state_root"]) / "maintenance_base_cursor.jsonl"),
        BASE_CURSOR_SCHEMA, "base_advanced", evaluation_time,
        {"task_id": snapshot["task_id"], "commit_sha": commit,
         "tracked_base_ref": cfg["tracked_base_ref"]})
    closed = task_journal.append_event(
        cfg["state_root"], "task_closed", task_id=snapshot["task_id"],
        payload={"commit_sha": commit, "base_cursor_event_digest": event["event_digest"]},
        recorded_at=evaluation_time, repo_root=cfg["repository_root"], evaluation_time=evaluation_time)
    return {"status": "completed", "base_cursor": event, "closure": closed.snapshot}


def _dispatch(transition: str, cfg: Mapping[str, Any], scanned: Mapping[str, Any], evaluation_time: str) -> dict[str, Any]:
    table = {"select_candidate": _select, "admit_candidate": _admit,
             "prepare_implementation": _prepare_implementation,
             "start_implementation": _start_implementation,
             "observe_process": _observe_implementation,
             "recover_implementation": _recover_implementation,
             "validate": _validate, "recover_validation": _validate,
             "commit_enqueue": _commit, "publish": _publish, "close_task": _close}
    operation = table.get(transition)
    if operation is None:
        return {"status": "waiting", "reason": "canonical_component_state_not_ready"}
    return operation(cfg, scanned, evaluation_time)


def tick(config: Mapping[str, Any], *, evaluation_time: str) -> dict[str, Any]:
    cfg = validate_config(config); state = Path(cfg["state_root"]); lock_path = state / "watchdog.lock"
    lock_path.touch(exist_ok=True)
    with lock_path.open("r+") as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"schema_version": TICK_SCHEMA, "status": "waiting", "transition": "global_lock_busy"}
        scanned = scan(cfg, evaluation_time=evaluation_time); decision = decide(cfg, scanned)
        transition = decision["transition"]
        if decision["status"] != "action_ready": effect = {"status": decision["status"]}
        else:
            stop = Path(cfg.get("stop_marker") or state / "STOP")
            if stop.exists(): transition, effect = "paused", {"status": "paused"}
            else:
                try:
                    effect = _dispatch(transition, cfg, scanned, evaluation_time)
                except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
                    effect = {"status": "blocked", "reason": "backend_construction_or_dispatch_failed",
                              "configured_backend": cfg["implementation_backend"],
                              "failure_type": type(exc).__name__, "failure_detail": str(exc)}
        result = {"schema_version": TICK_SCHEMA, "config_digest": cfg["config_digest"], "scan_digest": scanned["scan_digest"],
                  "decision_digest": decision["decision_digest"], "transition": transition,
                  "configured_backend": cfg["implementation_backend"],
                  "instantiated_backend": (None if effect.get("reason") == "backend_construction_or_dispatch_failed" else cfg["implementation_backend"]),
                  "effect_result": effect,
                  "status": effect.get("status", "completed") if isinstance(effect, Mapping) else "completed"}
        result["tick_digest"] = digest(result)
        _append_chain(state / "watchdog_ticks.jsonl", TICK_SCHEMA, transition, evaluation_time, result)
        return result


def run_bounded(config: Mapping[str, Any], *, evaluation_time: str) -> dict[str, Any]:
    cfg = validate_config(config); start = time.monotonic(); results = []
    for _ in range(int(cfg["maximum_actions"])):
        if time.monotonic() - start >= int(cfg["maximum_wall_clock_seconds"]): break
        result = tick(cfg, evaluation_time=evaluation_time); results.append(result)
        if result["status"] in TERMINAL or result["transition"] in {"idle", "paused"}: break
    return {"status": results[-1]["status"] if results else "time_limit", "ticks": results, "action_count": len(results)}


__all__ = ["validate_config", "load_config", "scan", "decide", "tick", "run_bounded", "control",
           "inspect_control", "build_implementation_brief", "canonical_json_bytes", "digest"]
