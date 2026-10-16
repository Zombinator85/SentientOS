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


def discover_codex_transfer_records(*, writeback: ResidentDevelopmentalWritebackController
        ) -> list[dict[str, Any]]:
    """Return a privacy-bounded inventory from the verified read-only owner."""
    inventory: list[dict[str, Any]] = []
    for record, receipt in writeback.inspect_completed_records():
        facts = record.candidate.get("selected_facts", ())
        for fact in facts:
            if not isinstance(fact, Mapping):
                continue
            payload = fact.get("payload")
            if not isinstance(payload, Mapping):
                continue
            examples = payload.get("acquisition_examples", ())
            if not isinstance(examples, (list, tuple)) or not examples:
                continue
            inputs: list[int] = []
            for item in examples:
                value = item.get("probe_input") if isinstance(item, Mapping) else None
                if isinstance(value, int) and not isinstance(value, bool):
                    inputs.append(value)
            correct = [item.get("evaluator_correct") for item in examples
                if isinstance(item, Mapping) and type(item.get("evaluator_correct")) is bool]
            scores = payload.get("objective_scores", ())
            if not isinstance(scores, (list, tuple)):
                scores = ()
            descriptor = payload.get("objective_task_descriptor", {})
            source = fact.get("source", {})
            inventory.append({"record_id": record.record_id,
                "record_digest": record.record_digest,
                "fact_id": fact.get("fact_id"),
                "task_family": payload.get("objective_task_family"),
                "task_family_posture": payload.get("task_family_posture"),
                "source_run_id": payload.get("run_id"),
                "source_run_digest": payload.get("run_digest"),
                "source_score_identities": [{"score_digest": score.get("score_digest"),
                    "task_digest": score.get("task_digest"),
                    "condition_id": score.get("condition_id")}
                    for score in scores if isinstance(score, Mapping)],
                "example_count": len(examples),
                "positive_count": sum(value is True for value in correct),
                "adverse_count": sum(value is False for value in correct),
                "probe_inputs": inputs,
                "probe_range": [min(inputs), max(inputs)] if inputs else None,
                "source_task_commitment": descriptor.get("task_digest")
                    if isinstance(descriptor, Mapping) else None,
                "source_event_time": payload.get("source_event_time") or
                    payload.get("created_at") or payload.get("event_time"),
                "source_validity_posture": payload.get("validity_posture") or
                    payload.get("run_validity_posture"),
                "execution_evidence_posture": payload.get("execution_evidence_posture"),
                "source_id": source.get("source_id") if isinstance(source, Mapping) else None,
                "source_digest": source.get("digest") if isinstance(source, Mapping) else None,
                "admission_receipt_id": receipt.receipt_id,
                "admission_receipt_digest": receipt.receipt_digest,
                "admission_verification": "verified_by_read_only_writeback_owner",
                "mapping_compatibility": "operator_review_required_family_does_not_prove_shared_truth"})
    return sorted(inventory, key=lambda item: (str(item.get("task_family")),
        str(item.get("record_id")), str(item.get("fact_id"))))


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
        payload = fact.get("payload") if isinstance(fact, Mapping) else None
        descriptor = payload.get("objective_task_descriptor") if isinstance(payload, Mapping) else None
        scores = payload.get("objective_scores") if isinstance(payload, Mapping) else None
        if not isinstance(descriptor, Mapping) or not isinstance(scores, list):
            raise CodexTransferPacketError("history_source_task_provenance_missing")
        task_digest = descriptor.get("task_digest")
        if (descriptor.get("task_digest_posture") != "salted_private_oracle_commitment:v1"
                or not isinstance(task_digest, str) or not task_digest.startswith("sha256:")):
            raise CodexTransferPacketError("source_task_identity_not_privately_committed")
        result.append({"record_id": record.record_id, "record_digest": record.record_digest,
            "source_fact_id": item["source_fact_id"],
            "source_id": source.get("source_id"), "source_digest": source.get("digest"),
            "source_task_family": family,
            "source_task_digest": task_digest,
            "source_task_digest_posture": descriptor.get("task_digest_posture"),
            "source_score_digests": [score.get("score_digest") for score in scores
                if isinstance(score, Mapping) and isinstance(score.get("score_digest"), str)],
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
    for group_name, sources in (("positive", present), ("adverse", adverse)):
        for source in sources:
            for example in source["examples"]:
                agrees = example["observed_answer"] == (
                    multiplier * example["probe_input"] + offset)
                if agrees != example["evaluator_correct"]:
                    raise CodexTransferPacketError(
                        "source_evaluator_label_conflicts_with_declared_target_mapping:" + group_name)

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
    preregistered_packet_digests: dict[str, str] = {}
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
                "and current probes below. Return exactly one JSON object with exactly one "
                "field, answers, whose value is an integer array in probe order. Do not add "
                "prose, markdown, or other fields. If evidence is insufficient, return your "
                "best predictions in the same format."),
            "historical_examples": treatment_history[condition][0],
            "source_fact_projections": [{"fact_id": source["source_fact_id"],
                "record_id": source["record_id"], "record_digest": source["record_digest"],
                "source_id": source["source_id"], "source_digest": source["source_digest"],
                "task_family": source["source_task_family"],
                "task_commitment": source["source_task_digest"],
                "task_commitment_posture": source["source_task_digest_posture"],
                "score_digests": source["source_score_digests"]}
                for source in treatment_history[condition][1]],
            "current_task": {"family": family, "probe_inputs": list(probe_inputs),
                "answer_format": '{"answers": [integer, ...]}'},
        }
        preregistered_packet_digests[opaque_id] = "sha256:" + digest_payload(subjects[opaque_id])
    preregistration = {"schema_version": "sentientos.operator_codex_transfer_preregistration:v1",
        "task_commitment": commitment, "packet_ids_in_randomized_order": list(subjects),
        "condition_by_packet_id": dict(scorer_conditions),
        "subject_packet_digests": preregistered_packet_digests,
        "model_settings_preregistered": dict(model_settings),
        "custody_note": "Record or timestamp this artifact before running any subject session; its file hash alone does not prove independent custody."}
    return {"subject_packets": subjects, "preregistration": preregistration,
        "scorer_manifest": {"schema_version": "sentientos.operator_codex_transfer_scorer:v1",
            "protocol_version": 1, "condition_by_packet_id": scorer_conditions,
            "subject_packet_digests": preregistered_packet_digests,
            "condition_order": order, "oracle_plan": private_plan,
            "task_commitment": commitment,
            "answer_key": [multiplier * value + offset for value in probe_inputs],
            "model_settings_preregistered": dict(model_settings),
            "applicability": {"posture": "operator_declared_shared_mapping_not_independently_verified",
                "basis": applicability_basis},
            "contamination_audit": {"status": "operator_review_required",
                "source_probes_checked_disjoint": True,
                "scorer_key_and_nonce_absent_from_subject_packets": True,
                "subject_packets_include_bounded_source_fact_projections": True,
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
        responses: Mapping[str, Mapping[str, Any]],
        subject_packets: Mapping[str, Mapping[str, Any]],
        preregistration: Mapping[str, Any]) -> dict[str, Any]:
    """Score operator-recorded fresh-session outputs without inference or replay."""
    if (not isinstance(scorer_manifest, Mapping) or not isinstance(responses, Mapping)
            or not isinstance(subject_packets, Mapping) or not isinstance(preregistration, Mapping)
            or set(scorer_manifest) != {"schema_version", "protocol_version",
                "condition_by_packet_id", "subject_packet_digests", "condition_order",
                "oracle_plan", "task_commitment", "answer_key", "model_settings_preregistered",
                "applicability", "contamination_audit", "source_record_identities", "scoring",
                "recording", "contamination_controls", "interpretation_limits"}
            or set(preregistration) != {"schema_version", "task_commitment",
                "packet_ids_in_randomized_order", "condition_by_packet_id",
                "subject_packet_digests", "model_settings_preregistered", "custody_note"}
            or scorer_manifest.get("schema_version") != "sentientos.operator_codex_transfer_scorer:v1"
            or not isinstance(scorer_manifest.get("condition_by_packet_id"), Mapping)
            or not isinstance(scorer_manifest.get("answer_key"), list)
            or scorer_manifest.get("protocol_version") != 1
            or not isinstance(scorer_manifest.get("oracle_plan"), Mapping)
            or not isinstance(scorer_manifest.get("subject_packet_digests"), Mapping)
            or not isinstance(scorer_manifest.get("model_settings_preregistered"), Mapping)
            or preregistration.get("schema_version") !=
                "sentientos.operator_codex_transfer_preregistration:v1"):
        raise CodexTransferPacketError("scorer_manifest_invalid")
    packet_conditions = scorer_manifest["condition_by_packet_id"]
    answer_key = scorer_manifest["answer_key"]
    plan = scorer_manifest["oracle_plan"]
    expected_commitment = "sha256:" + digest_payload({"schema": "sentientos.codex_private_oracle:v1",
        "plan": plan})
    nonce = plan.get("nonce")
    probe_inputs = plan.get("probe_inputs")
    condition_order = scorer_manifest.get("condition_order")
    source_records = scorer_manifest.get("source_record_identities")
    settings = scorer_manifest["model_settings_preregistered"]
    if (set(plan) != {"multiplier", "offset", "probe_inputs", "nonce"}
            or not isinstance(nonce, str) or len(nonce) != 64
            or any(character not in "0123456789abcdef" for character in nonce)
            or set(settings) != {"visible_model_name", "effort_setting", "generation_settings"}
            or not isinstance(settings.get("visible_model_name"), str)
            or not settings["visible_model_name"]
            or not isinstance(settings.get("effort_setting"), str)
            or not settings["effort_setting"]
            or not isinstance(settings.get("generation_settings"), Mapping)
            or not isinstance(condition_order, list) or len(condition_order) != len(CONDITIONS)
            or set(condition_order) != set(CONDITIONS)
            or not isinstance(source_records, list) or len(source_records) != 3
            or any(not isinstance(item, Mapping)
                or set(item) != {"record_id", "record_digest"}
                or not isinstance(item.get("record_id"), str) or not item.get("record_id")
                or not isinstance(item.get("record_digest"), str)
                for item in source_records)
            or len({item.get("record_id") for item in source_records
                if isinstance(item, Mapping) and isinstance(item.get("record_id"), str)
                and item.get("record_id")}) != 3
            or len({item.get("record_digest") for item in source_records
                if isinstance(item, Mapping) and isinstance(item.get("record_digest"), str)
                and item.get("record_digest")}) != 3
            or not isinstance(probe_inputs, list) or not 2 <= len(probe_inputs) <= 16
            or any(type(value) is not int or abs(value) > 1_000_000 for value in probe_inputs)
            or len(set(probe_inputs)) != len(probe_inputs)
            or any(not isinstance(value, str) for value in packet_conditions.values())
            or set(packet_conditions.values()) != set(CONDITIONS)
            or len(packet_conditions) != len(CONDITIONS)
            or set(scorer_manifest["subject_packet_digests"]) != set(packet_conditions)
            or any(not isinstance(key, str) or len(key) != 24 for key in packet_conditions)
            or set(subject_packets) != set(packet_conditions)
            or set(preregistration.get("subject_packet_digests", {})) != set(packet_conditions)
            or preregistration.get("task_commitment") != expected_commitment
            or preregistration.get("condition_by_packet_id") != packet_conditions
            or preregistration.get("subject_packet_digests") !=
                scorer_manifest["subject_packet_digests"]
            or preregistration.get("model_settings_preregistered") !=
                scorer_manifest["model_settings_preregistered"]
            or not isinstance(preregistration.get("packet_ids_in_randomized_order"), list)
            or len(preregistration["packet_ids_in_randomized_order"]) != len(packet_conditions)
            or set(preregistration["packet_ids_in_randomized_order"]) != set(packet_conditions)
            or [packet_conditions[item] for item in
                preregistration["packet_ids_in_randomized_order"]] != condition_order
            or scorer_manifest.get("task_commitment") != expected_commitment
            or type(plan.get("multiplier")) is not int or type(plan.get("offset")) is not int
            or any(type(value) is not int for value in probe_inputs)
            or any(type(value) is not int for value in answer_key)
            or [plan["multiplier"] * value + plan["offset"]
                for value in probe_inputs] != answer_key):
        raise CodexTransferPacketError("scorer_manifest_integrity_invalid")
    for packet_id, packet in subject_packets.items():
        expected_digest = scorer_manifest["subject_packet_digests"].get(packet_id)
        if (not isinstance(packet, Mapping)
                or expected_digest != "sha256:" + digest_payload(packet)
                or set(packet) != {"schema_version", "packet_id", "model_settings",
                    "task_commitment", "instructions", "historical_examples",
                    "source_fact_projections", "current_task"}
                or packet.get("packet_id") != packet_id
                or packet.get("schema_version") != PACKET_SCHEMA
                or packet.get("task_commitment") != expected_commitment
                or packet.get("model_settings") != scorer_manifest["model_settings_preregistered"]
                or not isinstance(packet.get("current_task"), Mapping)
                or packet["current_task"].get("probe_inputs") != probe_inputs):
            raise CodexTransferPacketError("subject_packet_identity_or_digest_mismatch")
        if any(not isinstance(example, Mapping) or set(example) != {
                "probe_input", "observed_answer", "evaluator_correct", "record_id",
                "record_digest", "source_fact_id", "source_id", "source_digest",
                "source_task_family", "source_task_digest"}
                for example in packet["historical_examples"]):
            raise CodexTransferPacketError("subject_packet_history_projection_invalid")
        if any(not isinstance(source, Mapping) or set(source) != {
                "fact_id", "record_id", "record_digest", "source_id", "source_digest",
                "task_family", "task_commitment", "task_commitment_posture", "score_digests"}
                for source in packet["source_fact_projections"]):
            raise CodexTransferPacketError("subject_packet_provenance_projection_invalid")
    if (not 1 <= len(answer_key) <= 16
            or any(type(value) is not int for value in answer_key)
            or not set(responses).issubset(set(packet_conditions))):
        raise CodexTransferPacketError("response_packet_set_mismatch")
    if any(not isinstance(response, Mapping) or response.get("packet_id") != packet_id
            for packet_id, response in responses.items()):
        raise CodexTransferPacketError("response_packet_binding_mismatch")
    response_fields = {"packet_id", "session_id", "timestamp", "visible_model_name",
        "effort_setting", "generation_settings", "raw_output"}
    if any(not set(response).issubset(response_fields) for response in responses.values()):
        raise CodexTransferPacketError("response_record_schema_invalid")
    preregistered = scorer_manifest.get("model_settings_preregistered")
    rows: list[dict[str, Any]] = []
    seen_sessions: set[str] = set()
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
            parse_failed = False
            try:
                parsed = json.loads(raw)
            except (ValueError, TypeError):
                parse_failed = True
                parsed = None
                stripped = raw.strip()
                status = ("unscoreable_partial_output" if stripped.startswith("{")
                    and not stripped.endswith("}") else "unscoreable_malformed_json")
            if parse_failed:
                pass
            elif not isinstance(parsed, Mapping) or set(parsed) != {"answers"}:
                status, parsed = "unscoreable_malformed_schema", None
            elif not isinstance(parsed.get("answers"), list):
                status, parsed = "unscoreable_malformed_schema", None
            elif len(parsed["answers"]) < len(answer_key):
                status, parsed = "unscoreable_partial_output", None
            elif len(parsed["answers"]) > len(answer_key):
                status, parsed = "unscoreable_wrong_length_output", None
            elif any(type(value) is not int for value in parsed["answers"]):
                status, parsed = "unscoreable_noninteger_answers", None
            else:
                status = "scored"
        session_id = response.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            status, parsed = "unscoreable_session_identity_missing", None
        elif session_id in seen_sessions:
            status, parsed = "duplicate_session_submission", None
        else:
            seen_sessions.add(session_id)
        actual_settings = {"visible_model_name": response.get("visible_model_name"),
            "effort_setting": response.get("effort_setting"),
            "generation_settings": response.get("generation_settings")}
        if status == "scored":
            answers = parsed["answers"] if isinstance(parsed, Mapping) else []
            correct = [actual == expected for actual, expected in
                zip(answers, answer_key, strict=True)]
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
