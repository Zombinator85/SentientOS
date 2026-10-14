"""Build blinded, operator-mediated Codex transfer packets from admitted history.

The builder prepares files only. It does not call Codex or any provider, run a
model, score a response, or grant execution authority.
"""
from __future__ import annotations

import json
import secrets
from typing import Any, Mapping, Sequence

from .local_model_authority import digest_payload
from .resident_developmental_cognition import _task_family_history_examples
from .resident_developmental_writeback import (
    DevelopmentalRecord, ResidentDevelopmentalWritebackController,
)

PACKET_SCHEMA = "sentientos.operator_codex_transfer_packet:v1"
CONDITIONS = ("history_present", "history_withheld", "history_restored",
              "irrelevant_history", "adverse_history")


class CodexTransferPacketError(ValueError):
    pass


def _record_examples(record: DevelopmentalRecord, *, family: str) -> list[dict[str, Any]]:
    projected = _task_family_history_examples(record.candidate, task_family_id=family)
    if not projected:
        raise CodexTransferPacketError("admitted_history_has_no_verified_family_examples")
    facts = record.candidate.get("selected_facts", ())
    fact_by_id = {item.get("fact_id"): item for item in facts
        if isinstance(item, Mapping) and isinstance(item.get("fact_id"), str)}
    result: list[dict[str, Any]] = []
    for item in projected:
        fact = fact_by_id.get(item.get("source_fact_id"))
        source = fact.get("source") if isinstance(fact, Mapping) else None
        if not isinstance(source, Mapping):
            raise CodexTransferPacketError("history_source_provenance_missing")
        result.append({"record_id": record.record_id, "record_digest": record.record_digest,
            "source_fact_id": item["source_fact_id"],
            "source_id": source.get("source_id"), "source_digest": source.get("digest"),
            "source_task_family": family,
            "source_task_digest": fact["payload"]["objective_task_descriptor"]["task_digest"],
            "source_fact": dict(fact),
            "examples": [{"probe_input": example["probe_input"],
                "observed_answer": example["observed_answer"],
                "evaluator_correct": example["evaluator_correct"]}
                for example in item["examples"]]})
    return result


def build_codex_transfer_packets(*, writeback: ResidentDevelopmentalWritebackController,
        history_record_id: str, irrelevant_record_id: str, adverse_record_id: str,
        family: str, irrelevant_family: str, probe_inputs: Sequence[int],
        multiplier: int, offset: int, applicability_basis: str,
        model_settings: Mapping[str, Any], nonce: str | None = None) -> dict[str, Any]:
    """Return isolated subject packets and a distinct private scoring manifest.

    Every source is loaded from the canonical store and bound to an immutable
    writeback receipt. Applicability is explicitly operator-declared because
    a task-family label alone cannot prove two hidden mappings share a truth.
    """
    if (not isinstance(family, str) or not family or len(family) > 96
            or not isinstance(irrelevant_family, str) or not irrelevant_family
            or irrelevant_family == family):
        raise CodexTransferPacketError("task_family_declaration_invalid")
    if (not isinstance(applicability_basis, str) or not applicability_basis.strip()
            or len(applicability_basis) > 1000):
        raise CodexTransferPacketError("mapping_applicability_basis_required")
    if (not isinstance(probe_inputs, (list, tuple)) or not 2 <= len(probe_inputs) <= 16
            or any(type(value) is not int or abs(value) > 1_000_000 for value in probe_inputs)
            or len(set(probe_inputs)) != len(probe_inputs)):
        raise CodexTransferPacketError("heldout_probe_suite_invalid")
    if (type(multiplier) is not int or type(offset) is not int
            or abs(multiplier) > 1_000_000 or abs(offset) > 1_000_000):
        raise CodexTransferPacketError("private_oracle_parameters_invalid")
    if not isinstance(model_settings, Mapping) or not model_settings:
        raise CodexTransferPacketError("model_settings_preregistration_required")
    if (not isinstance(model_settings.get("visible_model_name"), str)
            or not model_settings.get("visible_model_name")
            or not isinstance(model_settings.get("effort_setting"), str)
            or not model_settings.get("effort_setting")
            or not isinstance(model_settings.get("generation_settings"), Mapping)):
        raise CodexTransferPacketError("model_settings_incomplete")
    # The existing read-only owner validates canonical record, receipt,
    # candidate/source lineage, and the recorded runtime admission.
    verified = writeback.inspect_completed_records()
    records_by_id = {record.record_id: record for record, _receipt in verified}
    try:
        history_record = records_by_id[history_record_id]
        irrelevant_record = records_by_id[irrelevant_record_id]
        adverse_record = records_by_id[adverse_record_id]
    except KeyError as exc:
        raise CodexTransferPacketError("history_record_not_in_verified_admission_inventory") from exc
    if len({history_record.record_id, irrelevant_record.record_id,
            adverse_record.record_id}) != 3:
        raise CodexTransferPacketError("history_control_records_must_be_distinct")

    present = _record_examples(history_record, family=family)
    irrelevant = _record_examples(irrelevant_record, family=irrelevant_family)
    adverse = _record_examples(adverse_record, family=family)
    heldout = set(probe_inputs)
    if any(example["probe_input"] in heldout for source in (*present, *irrelevant, *adverse)
            for example in source["examples"]):
        raise CodexTransferPacketError("heldout_probe_overlaps_historical_example")
    if not all(example["evaluator_correct"] is True
            for source in present for example in source["examples"]):
        raise CodexTransferPacketError("history_present_record_not_positive")
    if not any(example["evaluator_correct"] is False
            for source in adverse for example in source["examples"]):
        raise CodexTransferPacketError("adverse_record_has_no_incorrect_example")

    salt = nonce or secrets.token_hex(32)
    if (not isinstance(salt, str) or len(salt) != 64
            or any(character not in "0123456789abcdef" for character in salt)):
        raise CodexTransferPacketError("oracle_commitment_nonce_invalid")
    private_plan = {"multiplier": multiplier, "offset": offset,
        "probe_inputs": list(probe_inputs), "nonce": salt}
    commitment = "sha256:" + digest_payload({"schema": "sentientos.codex_private_oracle:v1",
        "plan": private_plan})
    def prompt_examples(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{**example, "record_id": source["record_id"],
            "record_digest": source["record_digest"],
            "source_fact_id": source["source_fact_id"], "source_id": source["source_id"],
            "source_digest": source["source_digest"],
            "source_task_family": source["source_task_family"],
            "source_task_digest": source["source_task_digest"]}
            for source in sources for example in source["examples"]]
    treatment_history = {"history_present": (prompt_examples(present), present),
        "history_withheld": ([], []), "history_restored": (prompt_examples(present), present),
        "irrelevant_history": (prompt_examples(irrelevant), irrelevant),
        "adverse_history": (prompt_examples(adverse), adverse)}
    order = list(CONDITIONS)
    secrets.SystemRandom().shuffle(order)
    subjects: dict[str, dict[str, Any]] = {}
    scorer_conditions: dict[str, str] = {}
    for condition in order:
        opaque_id = secrets.token_hex(12)
        scorer_conditions[opaque_id] = condition
        subjects[opaque_id] = {
            "schema_version": PACKET_SCHEMA,
            "packet_id": opaque_id,
            "model_settings": dict(model_settings),
            "task_commitment": commitment,
            "instructions": (
                "You are solving a small prediction task. Use only the historical examples "
                "and current probes below. Return one JSON object with an integer array named "
                "answers, in probe order. If evidence is insufficient, still give your best "
                "predictions and state uncertainty in a separate short note."),
            "historical_examples": treatment_history[condition][0],
            "source_facts": treatment_history[condition][1],
            "current_task": {"family": family, "probe_inputs": list(probe_inputs),
                "answer_format": '{"answers": [integer, ...]}'},
        }
    return {"subject_packets": subjects,
        "scorer_manifest": {"schema_version": "sentientos.operator_codex_transfer_scorer:v1",
            "protocol_version": 1, "condition_by_packet_id": scorer_conditions,
            "condition_order": order, "oracle_plan": private_plan,
            "task_commitment": commitment,
            "answer_key": [multiplier * value + offset for value in probe_inputs],
            "model_settings_preregistered": dict(model_settings),
            "applicability": {"posture": "operator_declared_shared_mapping_not_independently_verified",
                "basis": applicability_basis},
            "contamination_audit": {"status": "operator_review_required",
                "source_probes_checked_disjoint": True,
                "scorer_key_and_nonce_absent_from_subject_packets": True,
                "subject_packets_include_exact_admitted_source_facts": True,
                "construction_session_excluded_from_subjects": True,
                "mapping_applicability_independently_verified": False,
                "fresh_session_isolation_requires_operator_execution": True},
            "source_record_identities": [{"record_id": record.record_id,
                "record_digest": record.record_digest} for record in
                (history_record, irrelevant_record, adverse_record)],
            "scoring": {"per_probe": "exact_integer_match",
                "full_task_correct": "all probes exactly match",
                "denominator": len(probe_inputs)},
            "recording": ["fresh_session_id", "visible_model_name", "effort_setting",
                "generation_settings", "raw_output", "timestamp", "condition_packet_id"],
            "contamination_controls": [
                "Use a fresh isolated session for each packet.",
                "Do not provide the scorer manifest or another packet to the subject.",
                "Do not use the construction conversation as a subject session.",
                "Run packets in the recorded randomized order and do not discuss answers between sessions."],
            "interpretation_limits": [
                "This measures within-model contextual use of supplied history, not a change to model weights.",
                "The family label does not independently establish mapping applicability.",
                "A score difference is fixture/task-specific and is not production evidence."]}}


def packet_json_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CodexTransferPacketError("packet_not_json_serializable") from exc


def score_codex_transfer_responses(*, scorer_manifest: Mapping[str, Any],
        responses: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Score operator-recorded fresh-session outputs without inference or replay."""
    if (scorer_manifest.get("schema_version") != "sentientos.operator_codex_transfer_scorer:v1"
            or not isinstance(scorer_manifest.get("condition_by_packet_id"), Mapping)
            or not isinstance(scorer_manifest.get("answer_key"), list)):
        raise CodexTransferPacketError("scorer_manifest_invalid")
    packet_conditions = scorer_manifest["condition_by_packet_id"]
    answer_key = scorer_manifest["answer_key"]
    if (not 1 <= len(answer_key) <= 16
            or any(type(value) is not int for value in answer_key)
            or not set(responses).issubset(set(packet_conditions))):
        raise CodexTransferPacketError("response_packet_set_mismatch")
    preregistered = scorer_manifest.get("model_settings_preregistered")
    rows: list[dict[str, Any]] = []
    for packet_id, condition in packet_conditions.items():
        if packet_id not in responses:
            rows.append({"packet_id": packet_id, "condition": condition,
                "status": "interrupted_or_not_run", "probe_correctness": [],
                "correct_count": None, "denominator": len(answer_key),
                "full_task_correct": None, "raw_output": None,
                "session_record": None,
                "reported_settings_match_preregistration": None})
            continue
        response = responses[packet_id]
        raw = response.get("raw_output")
        try:
            raw_size = len(raw.encode("utf-8")) if isinstance(raw, str) else 8193
        except UnicodeError:
            raw_size = 8193
        if not isinstance(raw, str) or raw_size > 8192:
            status, parsed = "unscoreable_missing_or_oversized_output", None
        else:
            try:
                parsed = json.loads(raw)
            except (ValueError, TypeError):
                parsed = None
            if (not isinstance(parsed, Mapping) or set(parsed) != {"answers"}
                    or not isinstance(parsed.get("answers"), list)
                    or len(parsed["answers"]) != len(answer_key)
                    or any(type(value) is not int for value in parsed["answers"])):
                status, parsed = "unscoreable_malformed_output", None
            else:
                status = "scored"
        actual_settings = {"visible_model_name": response.get("visible_model_name"),
            "effort_setting": response.get("effort_setting"),
            "generation_settings": response.get("generation_settings")}
        if status == "scored":
            correct = [actual == expected for actual, expected in
                zip(parsed["answers"], answer_key, strict=True)]
            correct_count = sum(correct)
            full_correct: bool | None = all(correct)
        else:
            correct = []
            correct_count = None
            full_correct = None
        rows.append({"packet_id": packet_id, "condition": condition, "status": status,
            "probe_correctness": correct, "correct_count": correct_count,
            "denominator": len(answer_key), "full_task_correct": full_correct,
            "raw_output": raw,
            "session_record": {key: response.get(key) for key in (
                "session_id", "timestamp", "visible_model_name", "effort_setting",
                "generation_settings")},
            "reported_settings_match_preregistration": actual_settings == preregistered})
    semantic = {"schema_version": "sentientos.operator_codex_transfer_scores:v1",
        "task_commitment": scorer_manifest.get("task_commitment"), "conditions": rows}
    semantic["score_digest"] = "sha256:" + digest_payload(semantic)
    return semantic
