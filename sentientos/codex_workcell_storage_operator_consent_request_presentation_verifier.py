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


def _source_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_digest": summary.get("digest"),
        "source_digest_algo": summary.get("digest_algo"),
        "source_byte_size": summary.get("byte_size"),
    }

def _result(required: list[str], rows_any: Any, *, key: str, section: str) -> tuple[dict[str, Any], bool]:
    rows = _ids(rows_any, key)
    missing = [item for item in required if item not in rows]
    common = {"requirement_count": len(rows), "required_requirement_ids_present": not missing, "missing_requirement_ids": missing}
    if section == "presentation_surface_results":
        res = {
            "surface_count": len(rows), "required_surface_ids_present": not missing, "missing_surface_ids": missing,
            "all_surfaces_future_only": all(rows[i].get("future_only") is True for i in required if i in rows),
            "all_surfaces_inactive": all(rows[i].get("active_now") is False for i in required if i in rows),
            "all_surfaces_have_denied_inference": all(bool(rows[i].get("denied_inference")) for i in required if i in rows),
            "all_surfaces_have_authority_boundary": all(bool(rows[i].get("authority_boundary")) for i in required if i in rows),
        }
    elif section == "presentation_authority_requirement_results":
        res = {**common,
            "all_required_before_presentation": all(rows[i].get("required_before_presentation") is True for i in required if i in rows),
            "all_currently_satisfied_false": all(rows[i].get("currently_satisfied") is False for i in required if i in rows),
            "all_have_missing_gap_id": all(bool(rows[i].get("missing_gap_id")) for i in required if i in rows),
            "all_have_authority_boundary": all(bool(rows[i].get("authority_boundary")) for i in required if i in rows),
        }
    else:
        res = {**common,
            "all_future_only": all(rows[i].get("future_only") is True for i in required if i in rows),
            "all_currently_satisfied_false": all(rows[i].get("currently_satisfied") is False for i in required if i in rows),
        }
    violations = [k for k, v in res.items() if isinstance(v, bool) and not v]
    res["passed"] = not violations
    res["violations"] = violations
    return res, isinstance(rows_any, list)

def _presentation_contract_summary(contract: Mapping[str, Any], contract_summary: Mapping[str, Any]) -> dict[str, Any]:
    posture = contract.get("non_authority_posture")
    return {
        "storage_operator_consent_request_presentation_contract_id": contract.get("storage_operator_consent_request_presentation_contract_id"),
        **{key: contract.get(key) for key in ("metadata_only", "contract_only", "future_only", "presentation_not_performed", "request_not_presented", "ui_not_rendered", "message_not_sent", "external_delivery_not_performed", "response_artifact_not_created", "response_not_collected", "consent_not_collected", "consent_not_implied", "operator_consent_present", "runtime_binding_not_performed", "active_storage_allowed_now", "execution_performed", "writes_performed", "archives_performed", "memory_mutation_performed")},
        "presentation_surface_count": len(contract.get("presentation_surface_inventory", [])) if isinstance(contract.get("presentation_surface_inventory"), list) else None,
        "denied_inference_count": len(contract.get("denied_inferences", [])) if isinstance(contract.get("denied_inferences"), list) else None,
        "missing_presentation_gap_count": len(contract.get("missing_real_world_presentation_summary", [])) if isinstance(contract.get("missing_real_world_presentation_summary"), list) else None,
        "non_authority_posture_present": isinstance(posture, Mapping),
        "non_authority_posture_all_true": _all_true(posture) if isinstance(posture, Mapping) else None,
        **_source_summary(contract_summary),
    }

def _optional_context_summary(optional_reports: Mapping[str, Mapping[str, Any]], optional_summaries: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for input_id in OPTIONAL_INPUT_IDS:
        summary = optional_summaries[input_id]
        report = optional_reports.get(input_id, {})
        rows.append({
            "input_id": input_id,
            "provided": summary.get("provided"),
            "detected_report_id": _status_or_id(report),
            "source_digest": summary.get("digest"),
            "source_digest_algo": summary.get("digest_algo"),
            "source_byte_size": summary.get("byte_size"),
            "relevant_status_or_digest": _status_or_id(report) or summary.get("digest"),
            "context_only": True,
        })
    return rows

def verify_codex_workcell_storage_operator_consent_request_presentation_contract(*, contract: Mapping[str, Any], contract_summary: Mapping[str, Any], optional_reports: Mapping[str, Mapping[str, Any]], optional_summaries: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    def add(cid: str, passed: bool, details: str, severity: str = "violation") -> None:
        checks.append({"check_id": cid, "passed": passed, "severity": "info" if passed else severity, "details": details, "authority_boundary": AUTHORITY_BOUNDARY})
    add("presentation_contract_is_object", isinstance(contract, Mapping), "Presentation contract JSON must be an object.")
    add("presentation_contract_id_matches", contract.get("storage_operator_consent_request_presentation_contract_id") == WORKCELL_STORAGE_OPERATOR_CONSENT_REQUEST_PRESENTATION_CONTRACT_ID, "Contract ID must match canonical v1 ID.")
    for key in ("metadata_only", "contract_only", "future_only"):
        add(f"presentation_contract_declares_{key.replace('_only','')}_only", contract.get(key) is True, f"{key} must be true.")
    for key in ("presentation_not_performed", "request_not_presented", "ui_not_rendered", "message_not_sent", "external_delivery_not_performed", "response_artifact_not_created", "response_not_collected", "consent_not_collected", "consent_not_implied", "runtime_binding_not_performed"):
        add(f"{key}_true", contract.get(key) is True, f"{key} must be true.")
    for key in ("operator_consent_present", "active_storage_allowed_now", "execution_performed", "writes_performed", "archives_performed", "memory_mutation_performed"):
        add(f"{key}_false", contract.get(key) is False, f"{key} must be false.")
    context = cast(Mapping[str, Any], contract.get("presentation_boundary_context") if isinstance(contract.get("presentation_boundary_context"), Mapping) else {})
    separated = set(context.get("presentation_authority_separate_from") or [])
    add("presentation_boundary_context_present", bool(context), "Presentation boundary context must be present.")
    add("presentation_authority_separated_from_packet_and_evidence", all(item in separated for item in SEPARATE_FROM) and context.get("no_request_presentation_action_occurred") is True, "Presentation authority must stay separate from packet/evidence/readiness/daemon/federation/runtime/storage evidence.")
    surface_results, surfaces_list = _result(PRESENTATION_SURFACES, contract.get("presentation_surface_inventory"), key="surface_id", section="presentation_surface_results")
    add("presentation_surface_inventory_present", surfaces_list, "Presentation surface inventory must be a list.")
    add("presentation_surface_inventory_complete", surface_results["required_surface_ids_present"], "All required presentation surface IDs must be present.")
    add("presentation_surfaces_future_only_and_inactive", surface_results["all_surfaces_future_only"] and surface_results["all_surfaces_inactive"], "All presentation surfaces must be future-only and inactive.")
    authority_results, authority_list = _result(PRESENTATION_AUTHORITY_REQUIREMENTS, contract.get("required_presentation_authority_requirements"), key="requirement_id", section="presentation_authority_requirement_results")
    add("presentation_authority_requirements_present", authority_list, "Presentation authority requirements must be a list.")
    add("presentation_authority_requirements_unsatisfied", authority_results["required_requirement_ids_present"] and authority_results["all_currently_satisfied_false"], "Presentation authority requirements must be present and unsatisfied.")
    section_defs = [
        ("operator_attention", OPERATOR_ATTENTION_REQUIREMENTS, "required_operator_attention_requirements"),
        ("delivery_scope", DELIVERY_SCOPE_REQUIREMENTS, "required_delivery_scope_requirements"),
        ("request_packet_integrity", REQUEST_PACKET_INTEGRITY_REQUIREMENTS, "required_request_packet_integrity_requirements"),
        ("response_path", RESPONSE_PATH_REQUIREMENTS, "required_response_path_requirements"),
    ]
    extra_results: dict[str, dict[str, Any]] = {}
    major_ok = surfaces_list and authority_list
    for prefix, required, field in section_defs:
        res, is_list = _result(required, contract.get(field), key="requirement_id", section=prefix)
        extra_results[f"{prefix}_requirement_results"] = res
        major_ok = major_ok and is_list
        add(f"{prefix}_requirements_present", is_list, f"{field} must be a list.")
        add(f"{prefix}_requirements_unsatisfied", res["required_requirement_ids_present"] and res["all_currently_satisfied_false"], f"{field} required IDs must be present and unsatisfied.")
    denied_rows = _ids(contract.get("denied_inferences"), "inference_id")
    denied_missing = [i for i in DENIED_INFERENCES if i not in denied_rows]
    denied_results = {"denied_inference_count": len(denied_rows), "required_inference_ids_present": not denied_missing, "missing_inference_ids": denied_missing, "all_denied": all(denied_rows[i].get("denied") is True for i in DENIED_INFERENCES if i in denied_rows), "no_inference_grants_authority": all("authority" in str(denied_rows[i].get("authority_boundary", "")) for i in DENIED_INFERENCES if i in denied_rows)}
    denied_results["violations"] = [k for k, v in denied_results.items() if isinstance(v, bool) and not v]
    denied_results["passed"] = not denied_results["violations"]
    denied_is_list = isinstance(contract.get("denied_inferences"), list); major_ok = major_ok and denied_is_list
    add("denied_inferences_present", denied_is_list, "Denied inferences must be a list.")
    add("denied_inferences_all_denied", bool(denied_results["required_inference_ids_present"] and denied_results["all_denied"]), "All required denied inferences must be present and denied.")
    gap_rows = _ids(contract.get("missing_real_world_presentation_summary"), "gap_id")
    gap_missing = [g for g in MISSING_GAPS if g not in gap_rows]
    gap_results = {"required_gap_ids_present": not gap_missing, "missing_gap_ids": gap_missing, "all_required_gaps_blocking": all(gap_rows[g].get("severity") == "blocking" for g in MISSING_GAPS if g in gap_rows), "all_required_gaps_inactive": all(gap_rows[g].get("active") is False for g in MISSING_GAPS if g in gap_rows), "presentation_mechanism_present_is_false": contract.get("presentation_mechanism_present", False) is False, "request_presented_is_false": contract.get("request_presented", False) is False, "ui_rendered_is_false": contract.get("ui_rendered", False) is False, "message_sent_is_false": contract.get("message_sent", False) is False, "external_delivery_performed_is_false": contract.get("external_delivery_performed", False) is False, "response_artifact_created_is_false": contract.get("response_artifact_created", False) is False, "response_collected_is_false": contract.get("response_collected", False) is False, "consent_collected_is_false": contract.get("consent_collected", False) is False, "consent_implied_is_false": contract.get("consent_implied", False) is False, "active_storage_allowed_now_is_false": contract.get("active_storage_allowed_now") is False}
    gap_results["violations"] = [k for k, v in gap_results.items() if isinstance(v, bool) and not v]
    gap_results["passed"] = not gap_results["violations"]
    gaps_is_list = isinstance(contract.get("missing_real_world_presentation_summary"), list); major_ok = major_ok and gaps_is_list
    add("missing_real_world_presentation_summary_present", gaps_is_list, "Missing real-world presentation summary must be a list.")
    add("required_presentation_gap_ids_present", bool(gap_results["required_gap_ids_present"]), "All required missing-presentation gap IDs must be present.")
    future_rows = _ids(contract.get("future_activation_requirements"), "requirement")
    add("future_activation_requirements_inactive", all(r in future_rows and future_rows[r].get("future_only") is True and future_rows[r].get("met") is False and future_rows[r].get("active") is False for r in FUTURE_ACTIVATION_REQUIREMENTS), "Future activation requirements must be inactive and unmet.")
    hygiene = cast(Mapping[str, Any], contract.get("reviewer_hygiene_summary") if isinstance(contract.get("reviewer_hygiene_summary"), Mapping) else {})
    add("reviewer_hygiene_bad_openai_repo_url_absent", hygiene.get("bad_openai_repo_url_expected_absent") is True and hygiene.get("docs_hygiene_only") is True and hygiene.get("no_runtime_effect") is True, "Reviewer hygiene remains metadata-only and expects bad `OpenAI` organization repository attribution for SentientOS attribution absent in docs.")
    posture = contract.get("non_authority_posture")
    add("non_authority_posture_present", isinstance(posture, Mapping), "Non-authority posture must be present.")
    add("non_authority_posture_true", _all_true(posture) if isinstance(posture, Mapping) else False, "Every non-authority posture field must be true.")
    violation_ids = [c["check_id"] for c in checks if c["severity"] == "violation" and not c["passed"]]
    warning_ids = [c["check_id"] for c in checks if c["severity"] == "warning" and not c["passed"]]
    status = "storage_operator_consent_request_presentation_contract_incomplete" if not major_ok else ("storage_operator_consent_request_presentation_contract_verified" if not violation_ids else "storage_operator_consent_request_presentation_contract_failed")
    mounts = cast(Mapping[str, Any], contract.get("sentientos_mount_alignment") if isinstance(contract.get("sentientos_mount_alignment"), Mapping) else {})
    report: dict[str, Any] = {"storage_operator_consent_request_presentation_verifier_id": WORKCELL_STORAGE_OPERATOR_CONSENT_REQUEST_PRESENTATION_VERIFIER_ID,
        "metadata_only": True, "verifier_only": True, "presentation_not_performed": True, "request_not_presented": True, "ui_not_rendered": True, "message_not_sent": True, "external_delivery_not_performed": True, "response_artifact_not_created": True, "response_not_collected": True, "consent_not_collected": True, "consent_not_implied": True, "operator_consent_present": False, "runtime_binding_not_performed": True, "active_storage_allowed_now": False, "execution_performed": False, "writes_performed": False, "archives_performed": False, "memory_mutation_performed": False,
        "not_presentation_runner": True, "not_ui_renderer": True, "not_message_sender": True, "not_external_delivery_system": True, "not_response_artifact_creator": True, "not_response_collector": True, "not_consent_collector": True, "not_runtime_authority": True, "not_memory_writer": True, "not_ledger_writer": True, "not_glow_archiver": True, "not_watcher": True, "not_scheduler": True, "not_executor": True, "not_daemon_action": True, "not_task_creator": True, "not_alerting_system": True, "not_model_training": True, "not_reinforcement_learning": True,
        "input_summaries": {"presentation_contract_json": dict(contract_summary), **{k: dict(v) for k, v in optional_summaries.items()}},
        "presentation_contract_summary": _presentation_contract_summary(contract, contract_summary), "optional_context_summary": _optional_context_summary(optional_reports, optional_summaries), "verification_status": status, "verification_checks": checks,
        "presentation_surface_results": surface_results, "presentation_authority_requirement_results": authority_results, **extra_results, "denied_inference_results": denied_results, "missing_real_world_presentation_results": gap_results, "missing_presentation_gap_results": gap_results,
        "reviewer_hygiene_summary": dict(hygiene), "violation_summary": {"violation_count": len(violation_ids), "warning_count": len(warning_ids), "info_count": sum(1 for c in checks if c["severity"] == "info"), "violation_check_ids": violation_ids, "warning_check_ids": warning_ids, "verifier_only": True, "no_action_taken": True},
        "sentientos_mount_alignment": dict(mounts), "future_activation_requirements": contract.get("future_activation_requirements"), "non_authority_posture": dict(NON_AUTHORITY_POSTURE)}
    return report

def _cell(value: Any) -> str:
    return (json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else str(value)).replace("|", "\\|").replace("\n", "<br>")

def _table(rows: list[list[Any]]) -> str:
    return "| Field | Value |\n| --- | --- |\n" + "".join(f"| {_cell(a)} | {_cell(b)} |\n" for a, b in rows)

def render_codex_workcell_storage_operator_consent_request_presentation_verifier_markdown(report: Mapping[str, Any]) -> str:
    parts = ["# Codex Workcell Storage Operator Consent Request Presentation Verifier", "", "This deterministic verifier is metadata-only: it checks presentation-boundary structure but does not present a request, render UI, send messages, deliver externally, create or collect responses, collect or imply consent, bind runtime authority, activate storage, write ledger entries, archive glow evidence, trigger daemons, decide readiness, create PR metadata, or establish federation authority.", ""]
    sections = [("Input summaries", "input_summaries"), ("Presentation contract summary", "presentation_contract_summary"), ("Optional context summary", "optional_context_summary"), ("Verification status", "verification_status"), ("Verification checks", "verification_checks"), ("Presentation surface results", "presentation_surface_results"), ("Presentation authority requirement results", "presentation_authority_requirement_results"), ("Operator attention requirement results", "operator_attention_requirement_results"), ("Delivery scope requirement results", "delivery_scope_requirement_results"), ("Request packet integrity requirement results", "request_packet_integrity_requirement_results"), ("Response path requirement results", "response_path_requirement_results"), ("Denied inference results", "denied_inference_results"), ("Missing real-world presentation results", "missing_real_world_presentation_results"), ("Reviewer hygiene summary", "reviewer_hygiene_summary"), ("Violation summary", "violation_summary"), ("SentientOS mount alignment", "sentientos_mount_alignment"), ("Future activation requirements", "future_activation_requirements"), ("Non-authority posture", "non_authority_posture")]
    for title, key in sections:
        value = report.get(key)
        parts += [f"## {title}"]
        if key == "verification_status":
            parts += [str(value), ""]
        elif isinstance(value, Mapping):
            parts += [_table([[k, v] for k, v in sorted(value.items())]), ""]
        elif isinstance(value, list):
            parts += [_table([[str(i), v] for i, v in enumerate(value)]), ""]
        else:
            parts += [_table([[key, value]]), ""]
    return "\n".join(parts).rstrip() + "\n"
