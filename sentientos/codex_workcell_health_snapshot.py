from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

WORKCELL_HEALTH_SNAPSHOT_ID = "codex_workcell_health_snapshot.v1"
DIGEST_ALGO = "sha256"
INPUT_IDS: tuple[str, ...] = (
    "architecture_json",
    "matrix_json",
    "pre_commit_finalizer_json",
    "pr_metadata_finalizer_json",
    "pr_metadata_guard_json",
    "lifecycle_summary_json",
    "lifecycle_doctor_json",
    "evidence_index_json",
    "evidence_appendix_sidecar_json",
    "beneficial_trait_doctrine_json",
)
MOUNTS = ("/vow", "/glow", "/pulse", "/daemon", "/ledger")

NON_AUTHORITY_POSTURE: dict[str, bool] = {
    "health_snapshot_is_read_only": True,
    "health_snapshot_is_metadata_only": True,
    "health_snapshot_does_not_rerun_commands": True,
    "health_snapshot_does_not_decide_readiness": True,
    "health_snapshot_does_not_bypass_finalizer": True,
    "health_snapshot_does_not_bypass_pr_metadata_guard": True,
    "health_snapshot_does_not_authorize_commit": True,
    "health_snapshot_does_not_authorize_pr_creation": True,
    "health_snapshot_does_not_trigger_daemon": True,
    "health_snapshot_does_not_schedule_tasks": True,
    "health_snapshot_does_not_train_or_modify_models": True,
    "health_snapshot_does_not_establish_federation_consensus": True,
}

class CodexWorkcellHealthSnapshotError(ValueError):
    pass

@dataclass(frozen=True)
class CodexWorkcellHealthSnapshotRequest:
    architecture_json: str | None = None
    matrix_json: str | None = None
    pre_commit_finalizer_json: str | None = None
    pr_metadata_finalizer_json: str | None = None
    pr_metadata_guard_json: str | None = None
    lifecycle_summary_json: str | None = None
    lifecycle_doctor_json: str | None = None
    evidence_index_json: str | None = None
    evidence_appendix_sidecar_json: str | None = None
    beneficial_trait_doctrine_json: str | None = None


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read_input(input_id: str, path_text: str | None) -> tuple[dict[str, Any], dict[str, Any] | None]:
    record = {"input_id": input_id, "provided": bool(path_text), "path": path_text, "readable_json": False, "digest_algo": DIGEST_ALGO, "digest": None, "byte_size": None, "error": None}
    if not path_text:
        return record, None
    path = Path(path_text)
    if not path.exists():
        record["error"] = f"missing_json:{input_id}:{path_text}"
        raise CodexWorkcellHealthSnapshotError(str(record["error"]))
    raw = path.read_bytes()
    record["digest"] = _sha256(raw)
    record["byte_size"] = len(raw)
    try:
        loaded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        record["error"] = f"invalid_json:{input_id}:{path_text}:{exc}"
        raise CodexWorkcellHealthSnapshotError(str(record["error"])) from exc
    if not isinstance(loaded, dict):
        record["error"] = f"json_not_object:{input_id}:{path_text}"
        raise CodexWorkcellHealthSnapshotError(str(record["error"]))
    record["readable_json"] = True
    return record, loaded


def _status(payload: Mapping[str, Any] | None, *keys: str) -> str | None:
    if payload is None:
        return None
    for key in keys:
        val = payload.get(key)
        if isinstance(val, str):
            return val
    dec = payload.get("decision")
    if isinstance(dec, Mapping) and isinstance(dec.get("status"), str):
        return str(dec["status"])
    return None


def _int(payload: Mapping[str, Any], key: str) -> int | None:
    val = payload.get(key)
    return val if isinstance(val, int) and not isinstance(val, bool) else None


def _count_matrix(payload: Mapping[str, Any], classification: str) -> int:
    direct = _int(payload, f"{classification}_count")
    if direct is not None:
        return direct
    results = payload.get("results") or payload.get("lanes")
    if not isinstance(results, list):
        return 0
    count = 0
    for item in results:
        if not isinstance(item, Mapping):
            continue
        cls = item.get("classification") or item.get("proof_class") or item.get("lane_class")
        status = item.get("status")
        if cls == classification and status not in {"passed", "pass", "success"}:
            count += 1
    return count


def _architecture_summary(arch: Mapping[str, Any] | None) -> dict[str, Any]:
    if arch is None:
        return {"provided": False}
    comps_raw = arch.get("components")
    flows_raw = arch.get("flows")
    future_raw = arch.get("future_integration_points")
    mounts_raw = arch.get("sentientos_mount_alignment")
    comps: list[Any] = comps_raw if isinstance(comps_raw, list) else []
    flows: list[Any] = flows_raw if isinstance(flows_raw, list) else []
    future: list[Any] = future_raw if isinstance(future_raw, list) else []
    mounts: Mapping[str, Any] = mounts_raw if isinstance(mounts_raw, Mapping) else {}
    return {"provided": True, "workcell_architecture_id": arch.get("workcell_architecture_id"), "component_count": len(comps), "flow_count": len(flows), "transition_authority_components": sorted(c.get("component_id") for c in comps if isinstance(c, Mapping) and c.get("authority_level") == "transition_authority"), "review_only_components": sorted(c.get("component_id") for c in comps if isinstance(c, Mapping) and c.get("authority_level") == "review_only"), "future_integration_count": len(future), "mount_alignment_keys": sorted(str(k) for k in mounts.keys())}


def _proof_summary(matrix: Mapping[str, Any] | None) -> dict[str, Any]:
    if matrix is None:
        return {"provided": False, "proof_signal_only": True}
    out = {"provided": True, "matrix_status": _status(matrix, "status", "overall_status"), "required_failure_count": _count_matrix(matrix, "required"), "nonproof_count": _count_matrix(matrix, "nonproof"), "diagnostic_failure_count": _count_matrix(matrix, "diagnostic"), "proof_signal_only": True}
    blocked = _int(matrix, "blocked_lane_count")
    if blocked is not None:
        out["blocked_lane_count"] = blocked
    return out


def _rerun(payload: Mapping[str, Any] | None) -> Any:
    if payload is None: return None
    if "rerun_required" in payload: return payload.get("rerun_required")
    fresh = payload.get("evidence_freshness")
    if isinstance(fresh, Mapping): return fresh.get("rerun_required")
    return None


def _terminal(payload: Mapping[str, Any] | None) -> Any:
    if payload is None: return None
    if "terminal_refresh_status" in payload: return payload.get("terminal_refresh_status")
    fresh = payload.get("evidence_freshness")
    if isinstance(fresh, Mapping): return fresh.get("terminal_refresh_status")
    return None


def _authority_summary(pre: Mapping[str, Any] | None, pr: Mapping[str, Any] | None, guard: Mapping[str, Any] | None) -> dict[str, Any]:
    return {"pre_commit_finalizer_status": _status(pre, "status"), "pr_metadata_finalizer_status": _status(pr, "status"), "pr_metadata_guard_status": _status(guard, "status"), "pre_commit_rerun_required": _rerun(pre), "pr_metadata_rerun_required": _rerun(pr), "pre_commit_terminal_refresh_status": _terminal(pre), "pr_metadata_terminal_refresh_status": _terminal(pr), "authority_observed_from_inputs_only": True}


def _evidence_summary(lifecycle: Mapping[str, Any] | None, doctor: Mapping[str, Any] | None, index: Mapping[str, Any] | None, sidecar: Mapping[str, Any] | None) -> dict[str, Any]:
    artifacts_raw = index.get("artifacts") if isinstance(index, Mapping) else None
    artifacts: list[Any] = artifacts_raw if isinstance(artifacts_raw, list) else []
    present_raw = index.get("artifact_roles_present") if isinstance(index, Mapping) else None
    missing_raw = index.get("artifact_roles_missing") if isinstance(index, Mapping) else None
    present = sorted(str(item) for item in present_raw) if isinstance(present_raw, list) else []
    missing = sorted(str(item) for item in missing_raw) if isinstance(missing_raw, list) else []
    return {"lifecycle_status": _status(lifecycle, "overall_lifecycle_status", "status"), "doctor_status": _status(doctor, "overall_doctor_status", "status"), "next_safe_action": doctor.get("next_safe_action") if isinstance(doctor, Mapping) else None, "evidence_index_id": index.get("evidence_index_id") if isinstance(index, Mapping) else None, "artifact_count": len(artifacts), "artifact_roles_present": present, "artifact_roles_missing": missing, "appendix_provenance_version": sidecar.get("provenance_version") if isinstance(sidecar, Mapping) else None, "appendix_rendered_markdown_digest": sidecar.get("rendered_markdown_digest") if isinstance(sidecar, Mapping) else None, "evidence_review_only": True}


def _doctrine_summary(doctrine: Mapping[str, Any] | None) -> dict[str, Any]:
    if doctrine is None:
        return {"provided": False, "doctrine_review_only": True}
    traits = doctrine.get("traits") or doctrine.get("trait_catalog")
    rails = doctrine.get("rail_mappings")
    return {"provided": True, "doctrine_map_id": doctrine.get("doctrine_map_id"), "trait_count": len(traits) if isinstance(traits, (list, dict)) else 0, "rail_mapping_count": len(rails) if isinstance(rails, list) else 0, "doctrine_only": doctrine.get("doctrine_only", True), "not_model_training": doctrine.get("not_model_training", True), "not_reinforcement_learning": doctrine.get("not_reinforcement_learning", True), "doctrine_review_only": True}


def _future() -> list[dict[str, Any]]:
    names = ["ledger receipt archival", "glow evidence memory", "pulse stale-evidence watch", "daemon repair recommendation", "federation drift consensus", "canonical vow digest checks", "workcell health snapshot", "operator cockpit rendering"]
    return [{"integration": n, "current_status": "future_integration" if n != "workcell health snapshot" else "observed_metadata_surface", "active_authority": False} for n in names]


def _mounts(arch: Mapping[str, Any] | None, supplied: list[str]) -> list[dict[str, Any]]:
    align = arch.get("sentientos_mount_alignment") if isinstance(arch, Mapping) and isinstance(arch.get("sentientos_mount_alignment"), Mapping) else {}
    out=[]
    for mount in MOUNTS:
        details = align.get(mount) if isinstance(align, Mapping) else None
        out.append({"mount": mount, "observed_inputs": supplied, "current_status": "observed" if details else "not_provided", "review_summary": details.get("purpose") if isinstance(details, Mapping) else f"Conceptual {mount} observation category; architecture map not provided.", "authority_boundary": "Mount snapshot is observational only and does not authorize action."})
    return out


def _pressure(missing: list[str], proof: Mapping[str, Any], authority: Mapping[str, Any]) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for item in missing:
        signals.append({"signal": "missing_input", "input_id": item, "observation_only": True})
    if proof.get("required_failure_count"):
        signals.append({"signal": "matrix_required_failures", "count": proof["required_failure_count"], "observation_only": True})
    if proof.get("diagnostic_failure_count"):
        signals.append({"signal": "diagnostic_failures_nonproof", "count": proof["diagnostic_failure_count"], "observation_only": True})
    for key in ("pre_commit_rerun_required", "pr_metadata_rerun_required"):
        if authority.get(key):
            signals.append({"signal": "finalizer_rerun_required", "source": key, "value": authority[key], "observation_only": True})
    for key in ("pre_commit_terminal_refresh_status", "pr_metadata_terminal_refresh_status"):
        if authority.get(key):
            signals.append({"signal": "stale_evidence_refresh_status", "source": key, "value": authority[key], "observation_only": True})
    if "architecture_json" in missing: signals.append({"signal": "absent_architecture_map", "observation_only": True})
    if "evidence_appendix_sidecar_json" in missing: signals.append({"signal": "absent_provenance_sidecar", "observation_only": True})
    if "beneficial_trait_doctrine_json" in missing: signals.append({"signal": "absent_doctrine_map", "observation_only": True})
    return signals


def build_codex_workcell_health_snapshot(request: CodexWorkcellHealthSnapshotRequest | None = None) -> dict[str, Any]:
    request = request or CodexWorkcellHealthSnapshotRequest()
    records=[]; payloads={}
    for input_id in INPUT_IDS:
        rec, payload = _read_input(input_id, getattr(request, input_id))
        records.append(rec); payloads[input_id] = payload
    supplied = [r["input_id"] for r in records if r["provided"]]
    missing = [r["input_id"] for r in records if not r["provided"]]
    arch = payloads["architecture_json"]
    proof = _proof_summary(payloads["matrix_json"])
    authority = _authority_summary(payloads["pre_commit_finalizer_json"], payloads["pr_metadata_finalizer_json"], payloads["pr_metadata_guard_json"])
    sidecar = payloads["evidence_appendix_sidecar_json"]
    provenance = {"input_digest_count": sum(1 for r in records if r["digest"]), "supplied_input_ids": supplied, "missing_input_ids": missing, "appendix_provenance_digest_version": sidecar.get("provenance_version") if isinstance(sidecar, Mapping) else None, "rendered_markdown_digest": sidecar.get("rendered_markdown_digest") if isinstance(sidecar, Mapping) else None, "provenance_does_not_verify_authority": True}
    return {"workcell_health_snapshot_id": WORKCELL_HEALTH_SNAPSHOT_ID, "metadata_only": True, "architecture_review_only": True, "cockpit_snapshot_only": True, "not_runtime_authority": True, "not_scheduler": True, "not_executor": True, "not_daemon_action": True, "not_model_training": True, "not_reinforcement_learning": True, "generated_from_inputs": records, "architecture_summary": _architecture_summary(arch), "proof_summary": proof, "authority_summary": authority, "evidence_summary": _evidence_summary(payloads["lifecycle_summary_json"], payloads["lifecycle_doctor_json"], payloads["evidence_index_json"], sidecar), "doctrine_summary": _doctrine_summary(payloads["beneficial_trait_doctrine_json"]), "provenance_summary": provenance, "sentientos_mount_snapshot": _mounts(arch, supplied), "future_integration_snapshot": _future(), "observed_pressure_signals": _pressure(missing, proof, authority), "missing_inputs": missing, "next_observation_recommendations": ["Observation only: provide architecture JSON for fuller component/flow summary.", "Observation only: provide matrix JSON for proof signal summary.", "Observation only: provide finalizer/guard JSON for observed authority status.", "Observation only: provide evidence index and doctor JSON for evidence interpretation.", "Observation only: provide appendix sidecar for rendered-surface provenance.", "Observation only: provide doctrine map for trait context."], "non_authority_posture": dict(sorted(NON_AUTHORITY_POSTURE.items()))}


def _cell(value: Any) -> str:
    text = json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else ("" if value is None else str(value))
    return text.replace("|", "\\|").replace("\n", "<br>")


def render_codex_workcell_health_snapshot_markdown(snapshot: Mapping[str, Any]) -> str:
    lines=["# Codex Workcell Health Snapshot", "", "This is a read-only cockpit snapshot of supplied metadata artifacts. It observes evidence only; it does not run commands, decide readiness, authorize commits or PR metadata, schedule work, trigger daemons, or train models.", "", "## Input provenance", "| input_id | provided | readable_json | digest | byte_size | error |", "| --- | --- | --- | --- | --- | --- |"]
    for r in snapshot["generated_from_inputs"]:
        lines.append(f"| {_cell(r['input_id'])} | {_cell(r['provided'])} | {_cell(r['readable_json'])} | {_cell(r['digest'])} | {_cell(r['byte_size'])} | {_cell(r['error'])} |")
    sections=[("Architecture summary","architecture_summary"),("Proof summary","proof_summary"),("Authority observation summary","authority_summary"),("Evidence summary","evidence_summary"),("Doctrine summary","doctrine_summary"),("Provenance summary","provenance_summary")]
    for title,key in sections:
        lines += ["", f"## {title}", "| key | value |", "| --- | --- |"]
        for k,v in sorted(snapshot[key].items()): lines.append(f"| {_cell(k)} | {_cell(v)} |")
    lines += ["", "## SentientOS mount snapshot", "| mount | current_status | observed_inputs | review_summary | authority_boundary |", "| --- | --- | --- | --- | --- |"]
    for m in snapshot["sentientos_mount_snapshot"]: lines.append(f"| {_cell(m['mount'])} | {_cell(m['current_status'])} | {_cell(m['observed_inputs'])} | {_cell(m['review_summary'])} | {_cell(m['authority_boundary'])} |")
    lines += ["", "## Future integration snapshot", "| integration | current_status | active_authority |", "| --- | --- | --- |"]
    for f in snapshot["future_integration_snapshot"]: lines.append(f"| {_cell(f['integration'])} | {_cell(f['current_status'])} | {_cell(f['active_authority'])} |")
    lines += ["", "## Observed pressure signals"] + [f"- {_cell(s)}" for s in snapshot["observed_pressure_signals"]]
    lines += ["", "## Next observation recommendations"] + [f"- {_cell(s)}" for s in snapshot["next_observation_recommendations"]]
    lines += ["", "## Non-authority posture"] + [f"- **{k}:** {str(v).lower()}" for k,v in sorted(snapshot["non_authority_posture"].items())]
    lines.append("")
    return "\n".join(lines)


def write_codex_workcell_health_snapshot_json(snapshot: Mapping[str, Any], output: str) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_codex_workcell_health_snapshot_markdown(markdown: str, output: str) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(markdown, encoding="utf-8")
