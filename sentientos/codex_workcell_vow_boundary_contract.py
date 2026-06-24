from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

WORKCELL_VOW_BOUNDARY_CONTRACT_ID = "codex_workcell_vow_boundary_contract.v1"
DIGEST_ALGO = "sha256"

INPUT_IDS: tuple[str, ...] = (
    "architecture_json",
    "health_snapshot_json",
    "pulse_contract_json",
    "daemon_recommendation_contract_json",
    "memory_contract_json",
    "memory_candidate_bundle_json",
    "memory_candidate_verifier_json",
    "memory_activation_preflight_json",
)

CONSTRAINT_ROWS: tuple[tuple[str, str, str, str, str, str, str], ...] = (
    ("finalizer_authority_only_for_commit_readiness", "Finalizer authority only for commit readiness", "finalizer_boundary", "Only the landing finalizer may report commit-readiness under its own contract.", "Do not infer finalizer authority from workcell reports or vow digests.", "Use the explicit finalizer contract and current finalizer artifact.", "Commit readiness stays with the finalizer."),
    ("pr_metadata_guard_authority_only_for_pr_metadata", "PR metadata guard authority only for PR metadata", "guard_boundary", "Only the PR metadata guard may authorize PR metadata creation under its own contract.", "Do not infer PR metadata readiness from workcell reports or vow digests.", "Use the explicit PR metadata guard contract and current guard artifact.", "PR metadata authority stays with the guard."),
    ("reports_do_not_create_runtime_authority", "Reports do not create runtime authority", "report_boundary", "Metadata reports are review surfaces only.", "Do not infer runtime authority from a report existing or aligning.", "Create a separate runtime authority contract with operator consent.", "Reports remain non-executable."),
    ("recommendations_are_not_commands", "Recommendations are not commands", "recommendation_boundary", "Recommendations may describe possible repairs but cannot command execution.", "Do not treat recommendations as commands, tickets, tasks, or daemon actions.", "Create an explicit command/action contract with admission and rollback.", "Recommendation surfaces are advisory."),
    ("pulse_signals_are_not_actions", "Pulse signals are not actions", "pulse_boundary", "Pulse signals name observation pressure but do not perform actions.", "Do not infer watcher, scheduler, task, or alert behavior from pulse signals.", "Create an explicit pulse watcher contract and consent boundary.", "Pulse remains inactive metadata."),
    ("health_snapshots_are_not_decisions", "Health snapshots are not decisions", "health_boundary", "Health snapshots render supplied evidence but do not decide readiness.", "Do not infer commit, PR, or operational readiness from health snapshots.", "Use finalizer, guard, matrix, and explicit operator decision contracts.", "Health is a cockpit view, not authority."),
    ("memory_candidates_are_not_writes", "Memory candidates are not writes", "memory_boundary", "Memory candidate records are staged metadata only.", "Do not infer /ledger writes or /glow archives from candidates.", "Create explicit storage writer and archive contracts.", "Candidates are not persisted memory."),
    ("memory_verification_is_not_readiness", "Memory verification is not readiness", "memory_boundary", "Candidate verification checks structure only.", "Do not infer landing readiness from candidate verification status.", "Use authoritative validation, finalizer, and guard flows.", "Verification is not readiness."),
    ("activation_preflight_is_not_activation", "Activation preflight is not activation", "memory_boundary", "Activation preflight exposes future gaps without activating memory.", "Do not infer active memory writer behavior from preflight status.", "Create explicit active writer, storage, consent, and policy contracts.", "Preflight remains inactive."),
    ("ledger_schema_is_not_ledger_write", "Ledger schema is not ledger write", "storage_boundary", "A /ledger schema only describes future record shape.", "Do not infer a ledger entry was written from schema presence.", "Create explicit ledger writer implementation and storage policy.", "Schema is not storage."),
    ("glow_schema_is_not_glow_archive", "Glow schema is not glow archive", "storage_boundary", "A /glow schema only describes future archive shape.", "Do not infer glow evidence was archived from schema presence.", "Create explicit glow archiver implementation and retention policy.", "Schema is not archive."),
    ("evidence_indexes_are_not_authority", "Evidence indexes are not authority", "proof_boundary", "Evidence indexes locate artifacts and hints but do not decide authority.", "Do not infer proof, freshness, or readiness from index presence alone.", "Read underlying artifacts through authoritative rails.", "Indexes improve reviewability only."),
    ("appendices_are_review_context_only", "Appendices are review context only", "proof_boundary", "Appendices render reviewer context and do not add gates.", "Do not infer validation proof or authority from appendix prose.", "Use required matrix, finalizer, and guard artifacts.", "Appendices are not proof lanes."),
    ("doctrine_maps_do_not_train_models", "Doctrine maps do not train models", "report_boundary", "Doctrine maps describe review rubrics and do not train or modify models.", "Do not infer model training, RL, or policy update from doctrine metadata.", "Create explicit model governance and training contracts.", "Doctrine is not training."),
    ("provenance_digests_do_not_verify_authority", "Provenance digests do not verify authority", "proof_boundary", "Digests identify bytes but do not prove source authority by themselves.", "Do not infer trust without source, policy, and authority checks.", "Create explicit provenance source and verification policy.", "Digest equality is not authority."),
    ("future_integrations_are_inactive_without_explicit_contract", "Future integrations inactive without explicit contract", "report_boundary", "Future integrations remain inactive until separately contracted.", "Do not infer active behavior from roadmap or future integration text.", "Create explicit integration contract and validation.", "Future text is not activation."),
    ("daemon_must_not_self_authorize", "Daemon must not self-authorize", "daemon_boundary", "Daemon surfaces cannot grant themselves action authority.", "Do not infer daemon execution authority from recommendations or alignment.", "Require explicit daemon action contract with operator authority.", "Daemons need external admission."),
    ("federation_consensus_not_implied", "Federation consensus not implied", "federation_boundary", "Local reports and digests do not establish federation consensus.", "Do not infer federation adoption, sync, merge, or consensus.", "Create explicit federation drift and consensus rule.", "Consensus is not implied."),
    ("no_skipped_or_nonexecuted_tests_as_required_proof", "No skipped or nonexecuted tests as required proof", "proof_boundary", "Skipped, missing, stale, or nonexecuted checks cannot satisfy required proof.", "Do not count diagnostic or non-proof lanes as required proof.", "Run and pass authoritative required proof lanes.", "Proof must execute and pass."),
    ("no_runtime_or_host_action_without_explicit_boundary", "No runtime or host action without explicit boundary", "operator_boundary", "Runtime or host actions require explicit boundary, consent, audit, and rollback.", "Do not infer host actuation permission from metadata.", "Create explicit runtime/host action boundary contract.", "Host action remains blocked."),
    ("no_backdoor_or_hidden_authority", "No backdoor or hidden authority", "operator_boundary", "All authority must be declared, auditable, and explicit.", "Do not infer hidden authority from omissions or implementation detail.", "Declare authority in explicit contracts and docs.", "No hidden grants."),
    ("operator_consent_required_for_active_watchers_or_daemons", "Operator consent required for active watchers or daemons", "operator_boundary", "Active watchers or daemons require explicit operator consent.", "Do not infer consent from report generation.", "Create explicit consent and revocation policy.", "Consent is required before activity."),
    ("storage_policy_required_for_memory_writes", "Storage policy required for memory writes", "storage_boundary", "Memory writes require explicit storage path and retention policy.", "Do not infer write permission without storage policy.", "Create explicit storage path, retention, and verification policy.", "Storage policy gates future writers."),
    ("vow_digest_required_for_future_active_writers", "Vow digest required for future active writers", "vow_boundary", "Future active writers must adopt an explicit vow digest boundary.", "Do not infer writer authority from digest presence alone.", "Create explicit vow adoption policy linked to writer contract.", "The vow digest is a future prerequisite, not authority."),
)

INFERENCE_ROWS: tuple[tuple[str, str, str, str, tuple[str, ...], str], ...] = (
    ("architecture_map_implies_runtime_authority", "architecture_map", "architecture map grants runtime authority", "architecture maps review surfaces and future boundaries only", ("reports_do_not_create_runtime_authority",), "false"),
    ("health_snapshot_implies_readiness", "health_snapshot", "health snapshot decides readiness", "health snapshots summarize supplied evidence only", ("health_snapshots_are_not_decisions",), "false"),
    ("pulse_contract_implies_action", "pulse_contract", "pulse contract triggers actions", "pulse contracts name inactive signal categories", ("pulse_signals_are_not_actions",), "false"),
    ("daemon_recommendation_implies_command", "daemon_recommendation_contract", "daemon recommendation is a command", "recommendations are advisory metadata", ("recommendations_are_not_commands", "daemon_must_not_self_authorize"), "false"),
    ("memory_contract_implies_storage_write", "memory_contract", "memory contract writes storage", "memory contracts define future schema only", ("ledger_schema_is_not_ledger_write", "glow_schema_is_not_glow_archive"), "false"),
    ("memory_candidate_bundle_implies_ledger_write", "memory_candidate_bundle", "candidate bundle writes /ledger", "candidate bundles stage candidate records only", ("memory_candidates_are_not_writes",), "false"),
    ("memory_candidate_bundle_implies_glow_archive", "memory_candidate_bundle", "candidate bundle archives /glow", "candidate bundles stage candidate archive items only", ("memory_candidates_are_not_writes",), "false"),
    ("memory_candidate_verifier_implies_readiness", "memory_candidate_verifier", "candidate verification grants readiness", "verification checks structure only", ("memory_verification_is_not_readiness",), "false"),
    ("memory_activation_preflight_implies_activation", "memory_activation_preflight", "activation preflight activates memory", "preflight exposes inactive future gaps", ("activation_preflight_is_not_activation",), "false"),
    ("matrix_diagnostic_nonproof_implies_required_proof", "matrix_diagnostic_lane", "diagnostic or nonexecuted lane satisfies proof", "only executed passing required proof lanes satisfy proof", ("no_skipped_or_nonexecuted_tests_as_required_proof",), "false"),
    ("evidence_index_implies_authority", "evidence_index", "evidence index grants authority", "indexes locate artifacts only", ("evidence_indexes_are_not_authority",), "false"),
    ("appendix_implies_authority", "evidence_appendix", "appendix grants authority", "appendices render review context only", ("appendices_are_review_context_only",), "false"),
    ("doctrine_map_implies_model_training", "doctrine_map", "doctrine map trains or modifies models", "doctrine maps are static metadata", ("doctrine_maps_do_not_train_models",), "false"),
    ("provenance_digest_implies_trust_without_source", "provenance_digest", "digest alone proves authority or trust", "digests identify bytes only", ("provenance_digests_do_not_verify_authority",), "false"),
    ("future_integration_implies_active_behavior", "future_integration", "future integration is active behavior", "future integrations are inactive without explicit contracts", ("future_integrations_are_inactive_without_explicit_contract",), "false"),
)

NON_AUTHORITY_POSTURE: dict[str, bool] = {
    "vow_boundary_contract_is_read_only": True,
    "vow_boundary_contract_is_metadata_only": True,
    "vow_boundary_contract_is_contract_only": True,
    "vow_boundary_contract_does_not_activate_memory": True,
    "vow_boundary_contract_does_not_write_ledger": True,
    "vow_boundary_contract_does_not_archive_glow": True,
    "vow_boundary_contract_does_not_modify_memory": True,
    "vow_boundary_contract_does_not_watch_files": True,
    "vow_boundary_contract_does_not_poll_state": True,
    "vow_boundary_contract_does_not_rerun_commands": True,
    "vow_boundary_contract_does_not_decide_readiness": True,
    "vow_boundary_contract_does_not_bypass_finalizer": True,
    "vow_boundary_contract_does_not_bypass_pr_metadata_guard": True,
    "vow_boundary_contract_does_not_authorize_commit": True,
    "vow_boundary_contract_does_not_authorize_pr_creation": True,
    "vow_boundary_contract_does_not_trigger_daemon": True,
    "vow_boundary_contract_does_not_create_tasks": True,
    "vow_boundary_contract_does_not_schedule_tasks": True,
    "vow_boundary_contract_does_not_send_alerts": True,
    "vow_boundary_contract_does_not_train_or_modify_models": True,
    "vow_boundary_contract_does_not_establish_federation_consensus": True,
}

FUTURE_REQUIREMENTS: tuple[str, ...] = (
    "explicit vow digest adoption policy", "explicit ledger writer implementation", "explicit glow archiver implementation", "explicit storage path policy", "explicit retention policy", "explicit digest verification policy", "explicit parent-chain validation policy", "explicit operator consent", "explicit finalizer/guard non-bypass invariant", "explicit pulse watcher contract", "explicit daemon action contract", "explicit federation drift consensus rule", "tests proving no readiness authority", "docs marking active behavior",
)

class CodexWorkcellVowBoundaryContractError(ValueError):
    pass

def canonical_vow_constraints() -> list[dict[str, str]]:
    return [{"constraint_id": cid, "constraint_name": name, "constraint_category": cat, "canonical_statement": stmt, "forbidden_inference": forb, "required_future_contract": req, "reviewer_summary": summ} for cid, name, cat, stmt, forb, req, summ in sorted(CONSTRAINT_ROWS)]

def compute_canonical_vow_digest(constraints: Sequence[Mapping[str, Any]] | None = None) -> str:
    records = sorted((constraints or canonical_vow_constraints()), key=lambda item: str(item["constraint_id"]))
    canonical = json.dumps(records, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()

def forbidden_inference_catalog() -> list[dict[str, Any]]:
    return [{"inference_id": iid, "source_surface": src, "forbidden_claim": claim, "allowed_claim": allowed, "blocking_constraint_ids": list(blockers), "authority_boundary": boundary} for iid, src, claim, allowed, blockers, boundary in sorted(INFERENCE_ROWS)]

def read_json_input(path_text: str | None, input_id: str) -> tuple[dict[str, Any], Mapping[str, Any] | None]:
    if path_text is None:
        return {"provided": False, "path": None, "digest": None, "byte_size": None, "readable_json": False, "error": None}, None
    path = Path(path_text)
    if not path.exists():
        raise CodexWorkcellVowBoundaryContractError(f"missing_{input_id}:{path_text}")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        loaded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CodexWorkcellVowBoundaryContractError(f"invalid_{input_id}:{path_text}:{exc}") from exc
    if not isinstance(loaded, Mapping):
        raise CodexWorkcellVowBoundaryContractError(f"{input_id}_not_object:{path_text}")
    return {"provided": True, "path": path_text, "digest_algo": DIGEST_ALGO, "digest": digest, "byte_size": len(raw), "readable_json": True, "error": None}, loaded

def _detected_report_id(data: Mapping[str, Any] | None) -> Any:
    if not data:
        return None
    for key in sorted(data):
        if key.endswith("_id") or key in {"doctor_report_id", "workcell_memory_contract_id"}:
            return data.get(key)
    return None

def _active_authority(data: Mapping[str, Any] | None) -> bool:
    if not data:
        return False
    active_true_keys = {"memory_writer", "ledger_writer", "glow_archiver", "watcher", "scheduler", "executor", "daemon_action", "task_creator", "alerting_system", "model_training", "reinforcement_learning", "runtime_authority"}
    for key, value in data.items():
        if (key in active_true_keys or key.startswith("active_") or key.endswith("_authority")) and value is True:
            return True
        if key.startswith("not_") and value is False:
            return True
    posture = data.get("non_authority_posture")
    if isinstance(posture, Mapping) and any(value is False for value in posture.values()):
        return True
    return False

def _applicable_inferences(input_id: str) -> list[str]:
    surface = input_id.removesuffix("_json")
    aliases = {"architecture": "architecture_map", "daemon_recommendation_contract": "daemon_recommendation_contract"}
    target = aliases.get(surface, surface)
    return [item["inference_id"] for item in forbidden_inference_catalog() if item["source_surface"] == target]

def _alignment(input_id: str, summary: Mapping[str, Any], data: Mapping[str, Any] | None) -> dict[str, Any]:
    if not summary.get("provided"):
        return {"input_id": input_id, "provided": False, "source_digest": None, "source_digest_algo": None, "source_byte_size": None, "detected_report_id": None, "metadata_only_seen": None, "non_authority_posture_present": False, "non_authority_posture_all_true": None, "forbidden_inference_ids_applicable": _applicable_inferences(input_id), "alignment_status": "not_supplied", "alignment_notes": ["input not supplied; no action taken"]}
    posture = data.get("non_authority_posture") if data else None
    posture_present = isinstance(posture, Mapping)
    posture_all_true = all(value is True for value in posture.values()) if isinstance(posture, Mapping) else None
    active = _active_authority(data)
    metadata_seen = data.get("metadata_only") if data else None
    notes: list[str] = []
    status = "aligned"
    if metadata_seen is not True:
        status = "warning"
        notes.append("metadata_only flag missing or not true")
    if posture_present and not posture_all_true:
        status = "failed"
        notes.append("non_authority_posture contains false values")
    if active:
        status = "failed"
        notes.append("active writer, daemon, scheduler, or authority flag detected")
    if not notes:
        notes.append("metadata-only non-authority alignment observed")
    return {"input_id": input_id, "provided": True, "source_digest": summary.get("digest"), "source_digest_algo": summary.get("digest_algo"), "source_byte_size": summary.get("byte_size"), "detected_report_id": _detected_report_id(data), "metadata_only_seen": metadata_seen, "non_authority_posture_present": posture_present, "non_authority_posture_all_true": posture_all_true, "forbidden_inference_ids_applicable": _applicable_inferences(input_id), "alignment_status": status, "alignment_notes": notes}

def build_codex_workcell_vow_boundary_contract(inputs: Mapping[str, tuple[Mapping[str, Any], Mapping[str, Any] | None]] | None = None) -> dict[str, Any]:
    normalized = {input_id: (dict(inputs[input_id][0]), inputs[input_id][1]) if inputs and input_id in inputs else ({"provided": False, "path": None, "digest": None, "byte_size": None, "readable_json": False, "error": None}, None) for input_id in INPUT_IDS}
    constraints = canonical_vow_constraints()
    inferences = forbidden_inference_catalog()
    alignments = [_alignment(input_id, summary, data) for input_id, (summary, data) in sorted(normalized.items())]
    return {
        "vow_boundary_contract_id": WORKCELL_VOW_BOUNDARY_CONTRACT_ID,
        "metadata_only": True, "vow_boundary_contract_only": True,
        "not_runtime_authority": True, "not_memory_writer": True, "not_ledger_writer": True, "not_glow_archiver": True, "not_watcher": True, "not_scheduler": True, "not_executor": True, "not_daemon_action": True, "not_task_creator": True, "not_alerting_system": True, "not_model_training": True, "not_reinforcement_learning": True,
        "input_summaries": {key: dict(value[0]) for key, value in sorted(normalized.items())},
        "canonical_vow_constraints": constraints,
        "canonical_vow_digest": compute_canonical_vow_digest(constraints),
        "canonical_vow_digest_algo": DIGEST_ALGO,
        "forbidden_inference_catalog": inferences,
        "report_alignment_results": alignments,
        "vow_gap_summary": {"supplied_report_count": sum(1 for a in alignments if a["provided"]), "aligned_report_count": sum(1 for a in alignments if a["alignment_status"] == "aligned"), "warning_report_count": sum(1 for a in alignments if a["alignment_status"] == "warning"), "failed_report_count": sum(1 for a in alignments if a["alignment_status"] == "failed"), "not_supplied_report_count": sum(1 for a in alignments if a["alignment_status"] == "not_supplied"), "canonical_constraint_count": len(constraints), "forbidden_inference_count": len(inferences), "canonical_vow_digest_present": True, "active_authority_detected": any(a["alignment_status"] == "failed" for a in alignments), "vow_boundary_contract_only": True, "no_action_taken": True},
        "sentientos_mount_alignment": {"/vow": "canonical constraint digest and forbidden inference boundary", "/ledger": "future consumer of vow-bounded write policy; inactive here", "/glow": "future consumer of vow-bounded archive policy; inactive here", "/pulse": "future consumer of vow-bounded observation history; inactive here", "/daemon": "future consumer of vow-bounded recommendation context; inactive here"},
        "future_activation_requirements": [{"requirement": r, "status": "future_only", "met": False, "active": False} for r in FUTURE_REQUIREMENTS],
        "non_authority_posture": dict(sorted(NON_AUTHORITY_POSTURE.items())),
    }

def _cell(value: Any) -> str:
    text = json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else ("" if value is None else str(value))
    return text.replace("|", "\\|").replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>")

def render_codex_workcell_vow_boundary_contract_markdown(report: Mapping[str, Any]) -> str:
    lines = ["# Codex Workcell Vow Digest Boundary Contract", "", "Deterministic metadata-only /vow boundary. It records forbidden inferences and a canonical constraint digest, but does not activate memory, write /ledger, archive /glow, decide readiness, trigger daemons, create tasks, schedule work, or authorize commits/PR metadata.", "", f"Canonical vow digest: `{_cell(report['canonical_vow_digest'])}`", "", "## Input summaries", "| input | provided | path | digest | byte_size |", "| --- | --- | --- | --- | --- |"]
    for key, value in sorted(report["input_summaries"].items()):
        lines.append(f"| {_cell(key)} | {_cell(value.get('provided'))} | {_cell(value.get('path'))} | {_cell(value.get('digest'))} | {_cell(value.get('byte_size'))} |")
    lines += ["", "## Canonical vow constraints", "| constraint_id | category | statement | forbidden inference |", "| --- | --- | --- | --- |"]
    for item in report["canonical_vow_constraints"]:
        lines.append(f"| {_cell(item['constraint_id'])} | {_cell(item['constraint_category'])} | {_cell(item['canonical_statement'])} | {_cell(item['forbidden_inference'])} |")
    lines += ["", "## Forbidden inference catalog", "| inference_id | source_surface | forbidden_claim | allowed_claim |", "| --- | --- | --- | --- |"]
    for item in report["forbidden_inference_catalog"]:
        lines.append(f"| {_cell(item['inference_id'])} | {_cell(item['source_surface'])} | {_cell(item['forbidden_claim'])} | {_cell(item['allowed_claim'])} |")
    lines += ["", "## Report alignment results", "| input | status | report_id | notes |", "| --- | --- | --- | --- |"]
    for item in report["report_alignment_results"]:
        lines.append(f"| {_cell(item['input_id'])} | {_cell(item['alignment_status'])} | {_cell(item['detected_report_id'])} | {_cell(item['alignment_notes'])} |")
    lines += ["", "## Vow gap summary", f"`{_cell(report['vow_gap_summary'])}`", "", "## SentientOS mount alignment", "| mount | alignment |", "| --- | --- |"]
    for key, value in sorted(report["sentientos_mount_alignment"].items()):
        lines.append(f"| {_cell(key)} | {_cell(value)} |")
    lines += ["", "## Future activation requirements", "| requirement | status | met | active |", "| --- | --- | --- | --- |"]
    for item in report["future_activation_requirements"]:
        lines.append(f"| {_cell(item['requirement'])} | {_cell(item['status'])} | {_cell(item['met'])} | {_cell(item['active'])} |")
    lines += ["", "## Non-authority posture"] + [f"- **{key}:** {str(value).lower()}" for key, value in sorted(report["non_authority_posture"].items())]
    lines.append("")
    return "\n".join(lines)

def write_codex_workcell_vow_boundary_contract_json(report: Mapping[str, Any], output: str) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def write_codex_workcell_vow_boundary_contract_markdown(markdown: str, output: str) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(markdown, encoding="utf-8")
