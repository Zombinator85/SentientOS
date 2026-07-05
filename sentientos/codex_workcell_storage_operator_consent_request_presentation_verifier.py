from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, cast

from sentientos.codex_workcell_storage_operator_consent_request_presentation_contract import (
    DELIVERY_SCOPE_REQUIREMENTS,
    DENIED_INFERENCES,
    FUTURE_ACTIVATION_REQUIREMENTS,
    INPUT_SPECS,
    MISSING_GAPS,
    NON_AUTHORITY_POSTURE,
    OPERATOR_ATTENTION_REQUIREMENTS,
    PRESENTATION_AUTHORITY_REQUIREMENTS,
    PRESENTATION_SURFACES,
    REQUEST_PACKET_INTEGRITY_REQUIREMENTS,
    RESPONSE_PATH_REQUIREMENTS,
    WORKCELL_STORAGE_OPERATOR_CONSENT_REQUEST_PRESENTATION_CONTRACT_ID,
)

WORKCELL_STORAGE_OPERATOR_CONSENT_REQUEST_PRESENTATION_VERIFIER_ID = "codex_workcell_storage_operator_consent_request_presentation_verifier.v1"
DIGEST_ALGO = "sha256"
AUTHORITY_BOUNDARY = "Storage operator consent request presentation verification is deterministic metadata only; verification_status is structure status only and is not presentation, UI rendering, message delivery, response artifact creation, response collection, consent, operator approval, runtime binding, storage activation, readiness, ledger authority, glow authority, daemon authority, scheduler authority, model authority, or federation authority."
OPTIONAL_INPUT_IDS: tuple[str, ...] = tuple(INPUT_SPECS)

TOP_LEVEL_TRUE_FLAGS: tuple[str, ...] = (
    "metadata_only", "contract_only", "future_only", "presentation_not_performed", "request_not_presented",
    "ui_not_rendered", "message_not_sent", "external_delivery_not_performed", "response_artifact_not_created",
    "response_not_collected", "consent_not_collected", "consent_not_implied", "runtime_binding_not_performed",
    "not_presentation_runner", "not_ui_renderer", "not_message_sender", "not_external_delivery_system",
    "not_response_artifact_creator", "not_response_collector", "not_consent_collector", "not_runtime_authority",
    "not_memory_writer", "not_ledger_writer", "not_glow_archiver", "not_watcher", "not_scheduler", "not_executor",
    "not_daemon_action", "not_task_creator", "not_alerting_system", "not_model_training", "not_reinforcement_learning",
)
TOP_LEVEL_FALSE_FLAGS: tuple[str, ...] = (
    "operator_consent_present", "active_storage_allowed_now", "execution_performed", "writes_performed",
    "archives_performed", "memory_mutation_performed",
)
SEPARATE_FROM: tuple[str, ...] = (
    "request_packet_existence", "packet_verification", "evidence_dossier_completeness", "dossier_verification",
    "response_schema_existence", "response_verifier_success", "finalizer_readiness", "pr_metadata_guard_readiness",
    "matrix_passage", "daemon_recommendations", "federation_state", "runtime_authority_contract_presence",
    "storage_policy_evidence",
)
MOUNTS: tuple[str, ...] = ("/ledger", "/glow", "/vow", "/pulse", "/daemon")

class CodexWorkcellStorageOperatorConsentRequestPresentationVerifierError(ValueError):
    pass

def omitted_input(input_id: str) -> dict[str, Any]:
    return {"input_id": input_id, "provided": False, "path": None, "digest": None, "byte_size": None, "readable_json": False, "error": None}

def read_json_input(path_text: str, input_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    path = Path(path_text)
    if not path.exists():
        raise CodexWorkcellStorageOperatorConsentRequestPresentationVerifierError(f"missing_json:{input_id}:{path_text}")
    raw = path.read_bytes()
    try:
        loaded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CodexWorkcellStorageOperatorConsentRequestPresentationVerifierError(f"invalid_json:{input_id}:{path_text}:{exc}") from exc
    if not isinstance(loaded, dict):
        raise CodexWorkcellStorageOperatorConsentRequestPresentationVerifierError(f"json_not_object:{input_id}:{path_text}")
    return {"input_id": input_id, "provided": True, "path": path_text, "digest_algo": DIGEST_ALGO, "digest": hashlib.sha256(raw).hexdigest(), "byte_size": len(raw), "readable_json": True, "error": None}, loaded

def _all_true(value: Any) -> bool:
    return isinstance(value, Mapping) and bool(value) and all(v is True for v in value.values())

def _check(checks: list[dict[str, Any]], check_id: str, passed: bool, details: str) -> None:
    checks.append({"check_id": check_id, "passed": passed, "severity": "info" if passed else "violation", "details": details, "authority_boundary": AUTHORITY_BOUNDARY})

def _ids(rows: Any, key: str) -> dict[Any, Mapping[str, Any]]:
    return {row.get(key): row for row in rows if isinstance(row, Mapping)} if isinstance(rows, list) else {}

def _status_or_id(data: Mapping[str, Any]) -> Any:
    for key in ("verification_status", "storage_operator_consent_request_packet_id", "storage_operator_consent_evidence_dossier_id", "storage_operator_consent_verifier_id", "storage_runtime_authority_verifier_id", "vow_boundary_contract_id"):
        if data.get(key) is not None:
            return data.get(key)
    return None

def verify_codex_workcell_storage_operator_consent_request_presentation_contract(*, contract: Mapping[str, Any], contract_summary: Mapping[str, Any], optional_reports: Mapping[str, Mapping[str, Any]], optional_summaries: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    _check(checks, "contract_id_valid", contract.get("storage_operator_consent_request_presentation_contract_id") == WORKCELL_STORAGE_OPERATOR_CONSENT_REQUEST_PRESENTATION_CONTRACT_ID, "Contract ID must match v1 presentation boundary contract.")
    for key in TOP_LEVEL_TRUE_FLAGS:
        _check(checks, f"{key}_true", contract.get(key) is True, f"{key} must be true.")
    for key in TOP_LEVEL_FALSE_FLAGS:
        _check(checks, f"{key}_false", contract.get(key) is False, f"{key} must be false.")
    context = cast(Mapping[str, Any], contract.get("presentation_boundary_context") if isinstance(contract.get("presentation_boundary_context"), Mapping) else {})
    separated = set(context.get("presentation_authority_separate_from") or [])
    _check(checks, "presentation_boundary_context_complete", all(item in separated for item in SEPARATE_FROM) and context.get("no_request_presentation_action_occurred") is True, "Presentation authority must be separate from packet/evidence/response/readiness/daemon/federation/runtime/storage evidence.")
    surfaces = _ids(contract.get("presentation_surface_inventory"), "surface_id")
    _check(checks, "required_presentation_surfaces_future_only_inactive", all(s in surfaces and surfaces[s].get("future_only") is True and surfaces[s].get("active_now") is False for s in PRESENTATION_SURFACES), "All presentation surfaces must be present, future-only, and inactive.")
    for field, expected in (("required_presentation_authority_requirements", PRESENTATION_AUTHORITY_REQUIREMENTS), ("required_operator_attention_requirements", OPERATOR_ATTENTION_REQUIREMENTS), ("required_delivery_scope_requirements", DELIVERY_SCOPE_REQUIREMENTS), ("required_request_packet_integrity_requirements", REQUEST_PACKET_INTEGRITY_REQUIREMENTS), ("required_response_path_requirements", RESPONSE_PATH_REQUIREMENTS)):
        rows = _ids(contract.get(field), "requirement_id")
        _check(checks, f"{field}_present_unsatisfied", all(r in rows and rows[r].get("currently_satisfied") is False for r in expected), f"{field} must contain required unsatisfied requirements.")
    denied = _ids(contract.get("denied_inferences"), "inference_id")
    _check(checks, "required_denied_inferences_denied", all(i in denied and denied[i].get("denied") is True for i in DENIED_INFERENCES), "Required inferences must be present and denied.")
    gaps = _ids(contract.get("missing_real_world_presentation_summary"), "gap_id")
    _check(checks, "missing_real_world_presentation_gaps_blocking_inactive", all(g in gaps and gaps[g].get("present") is True and gaps[g].get("severity") == "blocking" and gaps[g].get("active") is False for g in MISSING_GAPS), "Missing real-world presentation gaps must be present, blocking, and inactive.")
    futures = _ids(contract.get("future_activation_requirements"), "requirement")
    _check(checks, "future_activation_requirements_future_only_unmet_inactive", all(r in futures and futures[r].get("future_only") is True and futures[r].get("met") is False and futures[r].get("active") is False for r in FUTURE_ACTIVATION_REQUIREMENTS), "Future activation requirements must be future-only, unmet, and inactive.")
    hygiene = cast(Mapping[str, Any], contract.get("reviewer_hygiene_summary") if isinstance(contract.get("reviewer_hygiene_summary"), Mapping) else {})
    _check(checks, "reviewer_hygiene_metadata_only_urls", hygiene.get("correct_repo_url") == "https://github.com/Zombinator85/SentientOS.git" and hygiene.get("bad_repo_url") == "https://github.com/" + "OpenAI/" + "SentientOS.git" and hygiene.get("docs_hygiene_only") is True and hygiene.get("no_runtime_effect") is True, "Reviewer hygiene must preserve correct and bad URLs as metadata only.")
    mounts = cast(Mapping[str, Any], contract.get("sentientos_mount_alignment") if isinstance(contract.get("sentientos_mount_alignment"), Mapping) else {})
    _check(checks, "mount_alignment_present_without_activation_or_writes", all(m in mounts for m in MOUNTS) and all("no ledger write" in str(mounts.get(m, "")) or "no archive write" in str(mounts.get(m, "")) or "not activated" in str(mounts.get(m, "")) or "canonical digest" in str(mounts.get(m, "")) for m in MOUNTS), "Mount alignment must cover /ledger, /glow, /vow, /pulse, and /daemon without activation or writes.")
    _check(checks, "non_authority_posture_exact_all_true", contract.get("non_authority_posture") == NON_AUTHORITY_POSTURE and _all_true(contract.get("non_authority_posture")), "Non-authority posture must match contract constants and all values must be true.")
    violation_ids = [c["check_id"] for c in checks if not c["passed"]]
    status = "storage_operator_consent_request_presentation_contract_verified" if not violation_ids else "storage_operator_consent_request_presentation_contract_failed"
    optional_summary = [{"input_id": k, "provided": optional_summaries[k].get("provided"), "path": optional_summaries[k].get("path"), "source_digest_algo": optional_summaries[k].get("digest_algo"), "source_digest": optional_summaries[k].get("digest"), "source_byte_size": optional_summaries[k].get("byte_size"), "detected_status_or_id": _status_or_id(optional_reports.get(k, {})), "context_only": True} for k in OPTIONAL_INPUT_IDS]
    return {"storage_operator_consent_request_presentation_verifier_id": WORKCELL_STORAGE_OPERATOR_CONSENT_REQUEST_PRESENTATION_VERIFIER_ID, "metadata_only": True, "verifier_only": True, "presentation_not_performed": True, "request_not_presented": True, "ui_not_rendered": True, "message_not_sent": True, "external_delivery_not_performed": True, "response_artifact_not_created": True, "response_not_collected": True, "consent_not_collected": True, "consent_not_implied": True, "operator_consent_present": False, "runtime_binding_not_performed": True, "active_storage_allowed_now": False, "execution_performed": False, "writes_performed": False, "archives_performed": False, "memory_mutation_performed": False, "verification_status": status, "verification_checks": checks, "input_summaries": {"presentation_contract_json": dict(contract_summary), **{k: dict(v) for k, v in optional_summaries.items()}}, "optional_context_summary": optional_summary, "denied_inference_results": {"required_count": len(DENIED_INFERENCES), "passed": all(i in denied and denied[i].get("denied") is True for i in DENIED_INFERENCES), "denied_inference_ids": list(DENIED_INFERENCES)}, "missing_presentation_gap_results": {"required_count": len(MISSING_GAPS), "passed": all(g in gaps and gaps[g].get("present") is True and gaps[g].get("severity") == "blocking" and gaps[g].get("active") is False for g in MISSING_GAPS), "gap_ids": list(MISSING_GAPS)}, "reviewer_hygiene_summary": dict(hygiene), "sentientos_mount_alignment": dict(mounts), "future_activation_requirements": contract.get("future_activation_requirements"), "non_authority_posture": dict(NON_AUTHORITY_POSTURE), "violation_summary": {"violation_count": len(violation_ids), "violation_check_ids": violation_ids, "verifier_only": True, "no_action_taken": True}}

def _cell(value: Any) -> str:
    return (json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else str(value)).replace("|", "\\|").replace("\n", "<br>")

def _table(rows: list[list[Any]]) -> str:
    return "| Field | Value |\n| --- | --- |\n" + "".join(f"| {_cell(a)} | {_cell(b)} |\n" for a, b in rows)

def render_codex_workcell_storage_operator_consent_request_presentation_verifier_markdown(report: Mapping[str, Any]) -> str:
    parts = ["# Codex Workcell Storage Operator Consent Request Presentation Verifier", "", AUTHORITY_BOUNDARY, "", "## Verification status", str(report.get("verification_status")), "", "## Input summaries", _table([[k, v] for k, v in sorted(cast(Mapping[str, Any], report.get("input_summaries", {})).items())]), "", "## Verification checks", _table([[c.get("check_id"), c.get("passed")] for c in cast(list[Mapping[str, Any]], report.get("verification_checks", []))]), "", "## Violation summary", _table([[k, v] for k, v in cast(Mapping[str, Any], report.get("violation_summary", {})).items()])]
    return "\n".join(parts) + "\n"
