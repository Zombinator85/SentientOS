"""Canonical provenance manifests for read-only multi-store history archives."""
from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import asdict
from typing import Any, Callable, Mapping, Sequence

from .local_model_authority import digest_payload as _raw_digest_payload
from .semantic_history_retrieval_evaluation import (
    _paired_binary_difference_ci,
    _paired_ci,
    _validate_corpus_manifest,
    make_retrieval_corpus_manifest,
    retrieval_adjudication_procedure,
)

FEDERATED_SOURCE_MANIFEST_SCHEMA = (
    "sentientos.semantic_history_federated_source_manifest:v1")
_SOURCE_ID_RE = re.compile(r"src-[0-9a-f]{24}")
_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")
_FEDERATED_QUERY_SET_SCHEMA = (
    "sentientos.federated_semantic_history_query_set:v2")
_FEDERATED_QUERY_SET_ID_RE = re.compile(r"federated-queryset-[0-9a-f]{24}")
_FEDERATED_REVIEW_PAIR_SCHEMA = (
    "sentientos.federated_semantic_history_review_pair:v1")
_FEDERATED_REVIEWER_PACKET_SCHEMA = (
    "sentientos.federated_semantic_history_reviewer_packet:v1")
_FEDERATED_REVIEW_TEMPLATE_SCHEMA = (
    "sentientos.federated_semantic_history_review_template:v1")
_FEDERATED_REVIEW_SUBMISSION_SCHEMA = (
    "sentientos.federated_semantic_history_review_submission:v1")
_FEDERATED_REVIEW_CONSENSUS_SCHEMA = (
    "sentientos.federated_semantic_history_review_consensus:v1")
_FEDERATED_COMPARISON_SCHEMA = (
    "sentientos.federated_semantic_history_comparison:v1")
_FEDERATED_REVIEW_TEMPLATE_ID_RE = re.compile(r"[0-9a-f]{64}")
_QUERY_STRATA = ("paraphrased_experience", "lexical_distractor",
    "no_applicable_history")
_FEDERATED_RETRIEVAL_PROTOCOL_BODY = {
    "schema_version": "sentientos.semantic_history_federated_retrieval_gate:v1",
    "source_evaluation_protocol_schema":
        "sentientos.semantic_history_retrieval_gate:v12",
    "minimum_queries_per_stratum": 20,
    "paraphrase_recall_minimum_gain": 0.10,
    "paraphrase_recall_ci_lower_exclusive": 0.0,
    "maximum_false_inclusion_rate_increase": 0.02,
    "false_inclusion_ci_upper_inclusive": 0.02,
    "minimum_independent_reviewer_exact_agreement": 0.80,
    "confidence_level": 0.95,
    "bootstrap_samples": 10_000,
    "bootstrap_seed": "preregistered_query_set_digest_first_16_hex:v1",
    "bootstrap_stratum_offsets": {
        "paraphrased_experience": 0, "lexical_distractor": 10,
        "no_applicable_history": 20, "overall": 100},
    "bootstrap_metric_offsets": {
        "recall": 0, "reciprocal_rank": 1,
        "inapplicable_selection_rate": 2, "common_k_recall": 3,
        "selected_record_count": 4, "common_k_reciprocal_rank": 5,
        "nonrelevant_selection_rate": 6},
    "bootstrap_interval_method":
        "percentile_floor_index_no_interpolation:v1",
    "false_inclusion_interval_method":
        "paired_binary_clopper_pearson_bonferroni:v1",
    "maximum_nonrelevant_selection_rate_increase": 0.02,
    "maximum_semantic_fallback_queries": 0,
    "paraphrase_recall_metric": "common_k_recall",
    "common_k_rule": "minimum_condition_selected_count_per_query:v1",
    "zero_common_k_recall": "zero_for_both_conditions:v1",
    "identical_selection_metric": "set_equality_and_order_separately:v1",
    "selected_record_count_interval":
        "paired_query_percentile_bootstrap:v1",
    "full_selection_recall_minimum_gain": 0.0,
    "adjudication_procedure_digest":
        "7f0b88f2a1c722e54c3f5d205a99f8a972866788b2a0140e89f54929df6c2544",
    "federated_sampling_unit":
        "source_id_record_id_record_digest:v1",
    "source_experience_independence_verified": False,
    "reviewer_independence_established": False,
    "inferential_posture":
        "conditional_on_unverified_source_and_reviewer_independence",
    "learning_established": False,
    "authority": False,
}


def digest_payload(value: Any) -> str:
    """Return the prefixed digest form used by federated evidence schemas."""
    return "sha256:" + _raw_digest_payload(value)


def _verified_query_experience_anchors(*, query_set: Mapping[str, Any],
        anchor_audit: object, anchor_verification: object
        ) -> tuple[str, str, int, str, dict[tuple[str, str], str]]:
    """Bind query records to source-replayed, distinct event anchors."""
    if (not isinstance(anchor_audit, Mapping)
            or not isinstance(anchor_verification, Mapping)):
        raise ValueError("federated_query_experience_anchor_audit_invalid")
    verification_body = {key: value for key, value in anchor_verification.items()
        if key != "verification_digest"}
    if (anchor_verification.get("schema_version") !=
            "sentientos.federated_experience_anchor_verification:v3"
            or anchor_verification.get("status") != "verified"
            or anchor_verification.get("audit_digest") !=
                anchor_audit.get("audit_digest")
            or anchor_verification.get("corpus_freeze_id") !=
                anchor_audit.get("corpus_freeze_id")
            or anchor_verification.get("anchored_record_count") !=
                anchor_audit.get("anchored_record_count")
            or anchor_verification.get("distinct_experience_anchor_count") !=
                anchor_audit.get("distinct_experience_anchor_count")
            or anchor_verification.get("distinct_experience_shortfall") !=
                anchor_audit.get("distinct_experience_shortfall")
            or anchor_verification.get("source_snapshot_count") !=
                anchor_audit.get("source_snapshot_count")
            or anchor_verification.get("source_snapshot_digest") !=
                anchor_audit.get("source_snapshot_digest")
            or anchor_verification.get("verification_digest") !=
                digest_payload(verification_body)
            or anchor_verification.get("authority") is not False
            or anchor_verification.get("inference_performed") is not False
            or anchor_verification.get("independence_established") is not False
            or anchor_verification.get("phase_a_eligibility_established") is not False):
        raise ValueError("federated_query_experience_anchor_verification_invalid")
    semantic = {key: value for key, value in anchor_audit.items()
        if key != "audit_digest"}
    if (anchor_audit.get("schema_version") !=
            "sentientos.federated_experience_anchor_audit:v3"
            or anchor_audit.get("audit_digest") != digest_payload(semantic)
            or anchor_audit.get("authority") is not False
            or anchor_audit.get("inference_performed") is not False
            or anchor_audit.get("learning_established") is not False
            or anchor_audit.get("independence_established") is not False
            or anchor_audit.get("phase_a_eligibility_established") is not False
            or anchor_audit.get("duplicate_anchor_group_count") != 0
            or anchor_audit.get("unanchored_record_count") != 0
            or anchor_audit.get("distinct_experience_shortfall") != 0
            or type(anchor_audit.get("anchored_record_count")) is not int
            or type(anchor_audit.get("distinct_experience_anchor_count")) is not int
            or type(anchor_audit.get("corpus_record_count")) is not int
            or type(anchor_audit.get("source_snapshot_count")) is not int
            or anchor_audit.get("source_snapshot_count", 0) < 1
            or not isinstance(anchor_audit.get("source_snapshot_digest"), str)
            or _DIGEST_RE.fullmatch(anchor_audit["source_snapshot_digest"]) is None
            or not isinstance(anchor_audit.get("records"), list)):
        raise ValueError("federated_query_experience_anchor_audit_invalid")
    anchors: dict[tuple[str, str], str] = {}
    for row in anchor_audit["records"]:
        if (not isinstance(row, Mapping)
                or not isinstance(row.get("record_id"), str)
                or not isinstance(row.get("record_digest"), str)
                or not isinstance(row.get("experience_unit_digest"), str)
                or _DIGEST_RE.fullmatch(row["record_digest"]) is None
                or re.fullmatch(r"[0-9a-f]{64}",
                    row["experience_unit_digest"]) is None):
            raise ValueError("federated_query_experience_anchor_row_invalid")
        key = (row["record_id"], row["record_digest"])
        event_digest = "sha256:" + row["experience_unit_digest"]
        prior = anchors.get(key)
        if prior is not None and prior != event_digest:
            raise ValueError("federated_query_experience_anchor_conflict")
        anchors[key] = event_digest
    if (anchor_audit["anchored_record_count"] != len(anchors)
            or anchor_audit["corpus_record_count"] != len(anchors)
            or anchor_audit["distinct_experience_anchor_count"] !=
                len({row["experience_unit_digest"]
                    for row in anchor_audit["records"]})):
        raise ValueError("federated_query_experience_anchor_counts_mismatch")
    query_refs = query_set.get("source_experience_refs")
    if (not isinstance(query_refs, list)
            or len(query_refs) != query_set.get("question_count")):
        raise ValueError("federated_query_experience_anchor_refs_invalid")
    bound: dict[tuple[str, str], str] = {}
    seen_units: set[str] = set()
    for reference in query_refs:
        key = (reference.get("record_id"), reference.get("record_digest"))
        unit = anchors.get(key)
        if unit is None:
            raise ValueError("federated_query_experience_anchor_missing")
        if unit in seen_units:
            raise ValueError("federated_query_experience_anchor_duplicated")
        seen_units.add(unit)
        bound[key] = unit
    return (anchor_audit["audit_digest"],
        anchor_verification["verification_digest"],
        anchor_audit["source_snapshot_count"],
        anchor_audit["source_snapshot_digest"], bound)


def make_federated_retrieval_evaluation_protocol() -> dict[str, Any]:
    """Return the immutable gate protocol bound to federated query sets."""
    current_rubric = retrieval_adjudication_procedure(
        source_record_bindings=True,
        conceal_preregistered_strata=True)["procedure_digest"]
    if current_rubric != _FEDERATED_RETRIEVAL_PROTOCOL_BODY[
            "adjudication_procedure_digest"]:
        raise ValueError("federated_retrieval_protocol_rubric_drift")
    body = json.loads(json.dumps(_FEDERATED_RETRIEVAL_PROTOCOL_BODY,
        sort_keys=True, ensure_ascii=False, allow_nan=False))
    return {**body, "protocol_digest": digest_payload(body)}


def source_id_for_origin(origin_key: str) -> str:
    """Return an opaque stable ID without publishing the private origin key."""
    if not isinstance(origin_key, str) or not origin_key or len(origin_key) > 4096:
        raise ValueError("federated_history_origin_key_invalid")
    return "src-" + digest_payload({
        "schema_version": "sentientos.semantic_history_source_origin:v1",
        "origin_key": origin_key})[7:31]


def federated_source_experience_record_unit_digest(*, source_id: str,
        record_id: str, record_digest: str) -> str:
    """Derive a sampling-unit digest that preserves source-qualified identity."""
    if (not isinstance(source_id, str)
            or _SOURCE_ID_RE.fullmatch(source_id) is None
            or not isinstance(record_id, str)
            or not 1 <= len(record_id) <= 256
            or not isinstance(record_digest, str)
            or _DIGEST_RE.fullmatch(record_digest) is None):
        raise ValueError("federated_history_record_ref_invalid")
    return digest_payload({
        "schema_version":
            "sentientos.federated_source_experience_record_unit:v1",
        "source_id": source_id, "record_id": record_id,
        "record_digest": record_digest})


def federated_review_record_ref_id(*, source_id: str, record_id: str,
        record_digest: str) -> str:
    """Return the opaque reviewer-facing handle for one federated record."""
    return "frec-" + federated_source_experience_record_unit_digest(
        source_id=source_id, record_id=record_id,
        record_digest=record_digest)[7:31]


def _blind_record_projection(value: Any) -> Any:
    """Remove store and record locators while preserving reviewable evidence."""
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            normalized = str(key).lower()
            if (normalized in {"record_id", "source_id", "receipt_id",
                    "admission_id", "history_state_digest",
                    "federated_manifest_digest", "projection_digest",
                    "record_digest", "receipt_digest", "origin_key",
                    "candidate_id", "candidate_digest",
                    "origin_path", "store_id", "store_root", "state_root",
                    "state_path", "source_path", "source_store_id"}
                    or normalized.endswith(("_record_id", "_receipt_id"))
                    or normalized.endswith(("_candidate_id", "_candidate_digest"))
                    or normalized.endswith(("_record_digest", "_receipt_digest",
                        "_store_path", "_origin_path"))):
                continue
            result[str(key)] = _blind_record_projection(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_blind_record_projection(item) for item in value]
    return value


def _validated_federated_review_pair(value: object) -> dict[str, Any]:
    required = {"schema_version", "query_set_id", "query_set_digest",
        "federated_manifest_digest", "question_digest", "question",
        "record_ref_id", "record_digest", "record_projection",
        "source_locator_fields_included", "source_experience_binding_included",
        "preregistered_stratum_included", "retrieval_condition_outcomes_included",
        "generative_model_invoked", "authority", "review_pair_digest"}
    if (not isinstance(value, Mapping) or set(value) != required
            or value.get("schema_version") != _FEDERATED_REVIEW_PAIR_SCHEMA
            or value.get("source_locator_fields_included") is not False
            or value.get("source_experience_binding_included") is not False
            or value.get("preregistered_stratum_included") is not False
            or value.get("retrieval_condition_outcomes_included") is not False
            or value.get("generative_model_invoked") is not False
            or value.get("authority") is not False
            or not isinstance(value.get("query_set_id"), str)
            or _FEDERATED_QUERY_SET_ID_RE.fullmatch(value["query_set_id"]) is None
            or not isinstance(value.get("record_ref_id"), str)
            or re.fullmatch(r"frec-[0-9a-f]{24}", value["record_ref_id"]) is None
            or not isinstance(value.get("record_projection"), Mapping)):
        raise ValueError("federated_review_pair_invalid")
    semantic = {key: item for key, item in value.items()
        if key != "review_pair_digest"}
    if value.get("review_pair_digest") != digest_payload(semantic):
        raise ValueError("federated_review_pair_digest_mismatch")
    for key in ("query_set_digest", "federated_manifest_digest",
            "question_digest", "record_digest"):
        if not isinstance(value.get(key), str) or _DIGEST_RE.fullmatch(value[key]) is None:
            raise ValueError("federated_review_pair_digest_shape_invalid")
    if (not isinstance(value.get("question"), str)
            or not value["question"].strip() or len(value["question"]) > 1200):
        raise ValueError("federated_review_pair_question_invalid")
    if digest_payload({"question": value["question"]}) != value["question_digest"]:
        raise ValueError("federated_review_pair_question_digest_mismatch")
    return dict(value)


def _make_federated_review_pair_from_projection(*, query_set: Mapping[str, Any],
        question_index: int, source_id: str, projection: Mapping[str, Any]
        ) -> dict[str, Any]:
    semantic = {"schema_version": _FEDERATED_REVIEW_PAIR_SCHEMA,
        "query_set_id": query_set["query_set_id"],
        "query_set_digest": query_set["query_set_digest"],
        "federated_manifest_digest": query_set["federated_manifest_digest"],
        "question_digest": query_set["question_digests"][question_index],
        "question": query_set["questions"][question_index],
        "record_ref_id": federated_review_record_ref_id(
            source_id=source_id, record_id=projection["record_id"],
            record_digest=projection["record_digest"]),
        "record_digest": projection["record_digest"],
        "record_projection": _blind_record_projection(
            projection["record_projection"]),
        "source_locator_fields_included": False,
        "source_experience_binding_included": False,
        "preregistered_stratum_included": False,
        "retrieval_condition_outcomes_included": False,
        "generative_model_invoked": False, "authority": False}
    return {**semantic, "review_pair_digest": digest_payload(semantic)}


def make_federated_history_source_manifest(*, sources: Sequence[Mapping[str, Any]]
        ) -> dict[str, Any]:
    """Bind each source's local records to its independently frozen state.

    Each input has exactly ``origin_key`` and ``corpus_manifest``. The origin
    key should be a stable, private identifier for the store, not a published
    path. No record payloads are copied into this manifest.
    """
    if (not isinstance(sources, Sequence) or isinstance(sources, (str, bytes))
            or not sources or len(sources) > 10_000):
        raise ValueError("federated_history_sources_invalid")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in sources:
        if (not isinstance(source, Mapping)
                or set(source) != {"origin_key", "corpus_manifest"}):
            raise ValueError("federated_history_source_invalid")
        source_id = source_id_for_origin(source["origin_key"])
        if source_id in seen:
            raise ValueError("federated_history_source_identity_duplicated")
        seen.add(source_id)
        corpus = source["corpus_manifest"]
        if not isinstance(corpus, Mapping):
            raise ValueError("federated_history_source_corpus_invalid")
        try:
            corpus_digest, records = _validate_corpus_manifest(
                corpus, history_state_digest=corpus.get("history_state_digest"))
        except (TypeError, ValueError) as exc:
            raise ValueError("federated_history_source_corpus_invalid") from exc
        normalized.append({"source_id": source_id,
            "history_state_digest": corpus["history_state_digest"],
            "corpus_manifest_digest": "sha256:" + corpus_digest,
            "records": [{"record_id": record_id,
                "record_digest": records[record_id]}
                for record_id in sorted(records)]})
    normalized.sort(key=lambda row: row["source_id"])
    semantic = {"schema_version": FEDERATED_SOURCE_MANIFEST_SCHEMA,
        "sources": normalized, "authority": False}
    return {**semantic,
        "federated_manifest_digest": digest_payload(semantic)}


def validate_federated_history_source_manifest(value: object
        ) -> dict[str, dict[str, str]]:
    """Validate digest, ordering, uniqueness, and every embedded source corpus.

    Returns a source-ID map of record-ID to record-digest bindings. It does not
    claim to reopen a store or re-verify its admission evidence at use time.
    """
    expected = {"schema_version", "sources", "federated_manifest_digest",
        "authority"}
    if (not isinstance(value, Mapping) or set(value) != expected
            or value.get("schema_version") != FEDERATED_SOURCE_MANIFEST_SCHEMA
            or value.get("authority") is not False
            or not isinstance(value.get("sources"), list)
            or not value["sources"] or len(value["sources"]) > 10_000
            or not isinstance(value.get("federated_manifest_digest"), str)
            or _DIGEST_RE.fullmatch(value["federated_manifest_digest"]) is None):
        raise ValueError("federated_history_manifest_invalid")
    semantic = {key: item for key, item in value.items()
        if key != "federated_manifest_digest"}
    if value["federated_manifest_digest"] != digest_payload(semantic):
        raise ValueError("federated_history_manifest_digest_mismatch")
    result: dict[str, dict[str, str]] = {}
    previous_source: str | None = None
    for source in value["sources"]:
        if (not isinstance(source, Mapping)
                or set(source) != {"source_id", "history_state_digest",
                    "corpus_manifest_digest", "records"}
                or not isinstance(source.get("source_id"), str)
                or _SOURCE_ID_RE.fullmatch(source["source_id"]) is None
                or source["source_id"] in result
                or (previous_source is not None
                    and source["source_id"] <= previous_source)
                or not isinstance(source.get("history_state_digest"), str)
                or _DIGEST_RE.fullmatch(source["history_state_digest"]) is None
                or not isinstance(source.get("corpus_manifest_digest"), str)
                or _DIGEST_RE.fullmatch(source["corpus_manifest_digest"]) is None
                or not isinstance(source.get("records"), list)
                or not source["records"] or len(source["records"]) > 100_000):
            raise ValueError("federated_history_source_invalid")
        previous_source = source["source_id"]
        previous_record: str | None = None
        for row in source["records"]:
            if (not isinstance(row, Mapping)
                    or not isinstance(row.get("record_id"), str)
                    or (previous_record is not None
                        and row["record_id"] <= previous_record)):
                raise ValueError("federated_history_source_record_order_invalid")
            previous_record = row["record_id"]
        try:
            corpus = make_retrieval_corpus_manifest(
                history_state_digest=source["history_state_digest"],
                records=source["records"])
        except (TypeError, ValueError) as exc:
            raise ValueError("federated_history_source_records_invalid") from exc
        if "sha256:" + corpus["corpus_manifest_digest"] != source[
                "corpus_manifest_digest"]:
            raise ValueError("federated_history_source_digest_mismatch")
        try:
            _, records = _validate_corpus_manifest(corpus,
                history_state_digest=source["history_state_digest"])
        except (TypeError, ValueError) as exc:
            raise ValueError("federated_history_source_corpus_invalid") from exc
        result[source["source_id"]] = records
    return result


def make_federated_retrieval_query_set(*, manifest: Mapping[str, Any],
        questions: Sequence[str], strata: Sequence[str],
        source_experience_refs: Sequence[Mapping[str, str]],
        max_input_chars: int = 8000,
        target_model_identity: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Freeze balanced queries to distinct source-qualified archive records.

    This artifact is metadata only. It does not call a model, establish that a
    source record is relevant to its query, or imply retrieval improvement.
    """
    records = validate_federated_history_source_manifest(manifest)
    count = len(questions) if isinstance(questions, Sequence) else 0
    if (not 60 <= count <= 255 or count % 3 != 0
            or not isinstance(questions, (list, tuple))
            or any(not isinstance(question, str) or not question.strip()
                or len(question) > 1200 for question in questions)
            or len({digest_payload({"question": question})
                for question in questions}) != count
            or not isinstance(strata, (list, tuple)) or len(strata) != count
            or any(stratum not in _QUERY_STRATA for stratum in strata)
            or any(strata.count(stratum) != count // 3
                for stratum in _QUERY_STRATA)
            or not isinstance(source_experience_refs, (list, tuple))
            or len(source_experience_refs) != count
            or type(max_input_chars) is not int
            or not 128 <= max_input_chars <= 131_072
            or (target_model_identity is not None
                and (not isinstance(target_model_identity, Mapping)
                    or not target_model_identity))):
        raise ValueError("federated_retrieval_query_set_input_invalid")
    try:
        identity = (None if target_model_identity is None else
            json.loads(json.dumps(
                dict(target_model_identity), sort_keys=True,
                ensure_ascii=False, allow_nan=False)))
    except (TypeError, ValueError) as exc:
        raise ValueError("federated_retrieval_query_set_identity_invalid") from exc
    normalized_refs: list[dict[str, str]] = []
    seen_units: set[str] = set()
    for reference in source_experience_refs:
        if (not isinstance(reference, Mapping)
                or set(reference) != {"source_id", "record_id"}
                or not isinstance(reference.get("source_id"), str)
                or not isinstance(reference.get("record_id"), str)):
            raise ValueError("federated_retrieval_query_source_ref_invalid")
        source_id, record_id = reference["source_id"], reference["record_id"]
        record_digest = records.get(source_id, {}).get(record_id)
        if record_digest is None:
            raise ValueError("federated_retrieval_query_source_ref_missing")
        unit_digest = federated_source_experience_record_unit_digest(
            source_id=source_id, record_id=record_id,
            record_digest=record_digest)
        if unit_digest in seen_units:
            raise ValueError("federated_retrieval_query_source_unit_duplicated")
        seen_units.add(unit_digest)
        normalized_refs.append({"source_id": source_id,
            "record_id": record_id, "record_digest": record_digest,
            "source_experience_unit_digest": unit_digest})
    evaluation_protocol = make_federated_retrieval_evaluation_protocol()
    semantic = {"schema_version": _FEDERATED_QUERY_SET_SCHEMA,
        "federated_manifest_digest": manifest["federated_manifest_digest"],
        "evaluation_protocol": evaluation_protocol,
        "evaluation_protocol_digest": evaluation_protocol["protocol_digest"],
        "question_count": count, "questions": list(questions),
        "question_digests": [digest_payload({"question": question})
            for question in questions],
        "strata": list(strata), "source_experience_refs": normalized_refs,
        "max_input_chars": max_input_chars,
        "target_model_identity": identity,
        "target_model_identity_digest": (None if identity is None else
            digest_payload(identity)),
        "authority": False, "inference_performed": False,
        "learning_established": False}
    query_set_digest = digest_payload(semantic)
    return {**semantic, "query_set_digest": query_set_digest,
        "query_set_id": "federated-queryset-" + query_set_digest[7:31]}


def validate_federated_retrieval_query_set(*, manifest: Mapping[str, Any],
        value: object) -> dict[str, Any]:
    """Recheck a sealed federated query artifact against its source manifest."""
    validate_federated_history_source_manifest(manifest)
    expected = {"schema_version", "federated_manifest_digest",
        "evaluation_protocol", "evaluation_protocol_digest", "question_count",
        "questions", "question_digests", "strata", "source_experience_refs",
        "max_input_chars", "target_model_identity",
        "target_model_identity_digest", "authority", "inference_performed",
        "learning_established", "query_set_digest", "query_set_id"}
    if (not isinstance(value, Mapping) or set(value) != expected
            or value.get("schema_version") != _FEDERATED_QUERY_SET_SCHEMA
            or value.get("federated_manifest_digest") !=
                manifest.get("federated_manifest_digest")
            or value.get("authority") is not False
            or value.get("inference_performed") is not False
            or value.get("learning_established") is not False
            or not isinstance(value.get("query_set_digest"), str)
            or _DIGEST_RE.fullmatch(value["query_set_digest"]) is None
            or not isinstance(value.get("query_set_id"), str)
            or _FEDERATED_QUERY_SET_ID_RE.fullmatch(value["query_set_id"]) is None):
        raise ValueError("federated_retrieval_query_set_invalid")
    protocol = make_federated_retrieval_evaluation_protocol()
    if (value.get("evaluation_protocol") != protocol
            or value.get("evaluation_protocol_digest") !=
                protocol["protocol_digest"]):
        raise ValueError("federated_retrieval_query_set_protocol_mismatch")
    semantic = {key: item for key, item in value.items()
        if key not in {"query_set_digest", "query_set_id"}}
    digest = digest_payload(semantic)
    if (digest != value["query_set_digest"]
            or value["query_set_id"] != "federated-queryset-" + digest[7:31]):
        raise ValueError("federated_retrieval_query_set_digest_mismatch")
    refs = value.get("source_experience_refs")
    if (not isinstance(refs, list)
            or any(not isinstance(row, Mapping) for row in refs)):
        raise ValueError("federated_retrieval_query_set_source_refs_invalid")
    try:
        canonical = make_federated_retrieval_query_set(manifest=manifest,
            questions=value["questions"], strata=value["strata"],
            source_experience_refs=[{"source_id": row.get("source_id"),
                "record_id": row.get("record_id")} for row in refs],
            max_input_chars=value["max_input_chars"],
            target_model_identity=value["target_model_identity"])
    except (TypeError, ValueError) as exc:
        raise ValueError("federated_retrieval_query_set_binding_mismatch") from exc
    if canonical != dict(value):
        raise ValueError("federated_retrieval_query_set_binding_mismatch")
    return canonical


def make_federated_retrieval_review_template(*, manifest: Mapping[str, Any],
        query_set: Mapping[str, Any], review_pairs: Sequence[Mapping[str, Any]],
        reviewer_digest: str) -> dict[str, Any]:
    """Create exhaustive blank labels for every query/corpus-record pair."""
    query_set = validate_federated_retrieval_query_set(
        manifest=manifest, value=query_set)
    sources = validate_federated_history_source_manifest(manifest)
    if (not isinstance(review_pairs, Sequence)
            or isinstance(review_pairs, (str, bytes))
            or not review_pairs or len(review_pairs) > 25_000
            or not isinstance(reviewer_digest, str)
            or _FEDERATED_REVIEW_TEMPLATE_ID_RE.fullmatch(reviewer_digest) is None):
        raise ValueError("federated_review_template_input_invalid")
    total_records = sum(len(records) for records in sources.values())
    if (total_records == 0 or len(query_set["questions"]) * total_records > 25_000
            or len(review_pairs) != len(query_set["questions"]) * total_records):
        raise ValueError("federated_review_template_pair_count_invalid")
    record_bindings: dict[str, str] = {}
    for source_id, records in sources.items():
        for record_id, record_digest in records.items():
            ref_id = federated_review_record_ref_id(source_id=source_id,
                record_id=record_id, record_digest=record_digest)
            if ref_id in record_bindings:
                raise ValueError("federated_review_record_ref_id_collision")
            record_bindings[ref_id] = record_digest
    query_indexes = {digest: index for index, digest in enumerate(
        query_set["question_digests"])}
    expected_pairs = {(question_digest, record_ref_id)
        for question_digest in query_indexes for record_ref_id in record_bindings}
    if len(expected_pairs) != len(review_pairs):
        raise ValueError("federated_review_template_pair_count_invalid")
    pair_digests: dict[tuple[str, str], str] = {}
    for raw_pair in review_pairs:
        pair = _validated_federated_review_pair(raw_pair)
        if (pair["query_set_id"] != query_set["query_set_id"]
                or pair["query_set_digest"] != query_set["query_set_digest"]
                or pair["federated_manifest_digest"] !=
                    query_set["federated_manifest_digest"]
                or pair["question_digest"] not in query_indexes
                or pair["question"] != query_set["questions"][
                    query_indexes[pair["question_digest"]]]
                or record_bindings.get(pair["record_ref_id"]) !=
                    pair["record_digest"]):
            raise ValueError("federated_review_template_pair_binding_mismatch")
        key = (pair["question_digest"], pair["record_ref_id"])
        if key in pair_digests:
            raise ValueError("federated_review_template_pair_duplicated")
        pair_digests[key] = pair["review_pair_digest"]
    if set(pair_digests) != expected_pairs:
        raise ValueError("federated_review_template_pair_partition_incomplete")
    ordered_pairs = sorted(pair_digests,
        key=lambda key: (query_indexes[key[0]], key[1]))
    pair_digest_list = [pair_digests[key] for key in ordered_pairs]
    annotations = [{"question_digest": question_digest,
        "record_ref_id": record_ref_id,
        "record_digest": record_bindings[record_ref_id], "label": None}
        for question_digest, record_ref_id in ordered_pairs]
    semantic = {"schema_version": _FEDERATED_REVIEW_TEMPLATE_SCHEMA,
        "query_set_id": query_set["query_set_id"],
        "query_set_digest": query_set["query_set_digest"],
        "federated_manifest_digest":
            query_set["federated_manifest_digest"],
        "reviewer_digest": reviewer_digest,
        "review_pair_digests": pair_digest_list,
        "annotations": annotations, "authority": False}
    return {**semantic, "template_digest": digest_payload(semantic)}


def make_federated_retrieval_reviewer_packet(*, manifest: Mapping[str, Any],
        query_set: Mapping[str, Any], review_pairs: Sequence[Mapping[str, Any]],
        reviewer_digest: str) -> dict[str, Any]:
    """Bind blinded pair content and one blank annotation template."""
    query_set = validate_federated_retrieval_query_set(
        manifest=manifest, value=query_set)
    template = make_federated_retrieval_review_template(manifest=manifest,
        query_set=query_set, review_pairs=review_pairs,
        reviewer_digest=reviewer_digest)
    ordered_pairs = sorted(review_pairs, key=lambda pair: (
        query_set["question_digests"].index(pair["question_digest"]),
        pair["record_ref_id"]))
    semantic = {"schema_version": _FEDERATED_REVIEWER_PACKET_SCHEMA,
        "query_set_id": query_set["query_set_id"],
        "query_set_digest": query_set["query_set_digest"],
        "federated_manifest_digest": query_set["federated_manifest_digest"],
        "reviewer_digest": reviewer_digest,
        "review_pairs": [dict(pair) for pair in ordered_pairs],
        "review_template": template,
        "generative_model_invoked": False, "authority": False}
    return {**semantic, "packet_digest": digest_payload(semantic)}


def validate_federated_retrieval_reviewer_packet(*, manifest: Mapping[str, Any],
        query_set: Mapping[str, Any], value: object) -> dict[str, Any]:
    """Recompute the pair roster, blinded template, and packet digest."""
    expected = {"schema_version", "query_set_id", "query_set_digest",
        "federated_manifest_digest", "reviewer_digest", "review_pairs",
        "review_template", "generative_model_invoked", "authority",
        "packet_digest"}
    if (not isinstance(value, Mapping) or set(value) != expected
            or value.get("schema_version") != _FEDERATED_REVIEWER_PACKET_SCHEMA
            or value.get("generative_model_invoked") is not False
            or value.get("authority") is not False
            or not isinstance(value.get("review_pairs"), list)
            or not isinstance(value.get("review_template"), Mapping)):
        raise ValueError("federated_reviewer_packet_invalid")
    try:
        canonical = make_federated_retrieval_reviewer_packet(
            manifest=manifest, query_set=query_set,
            review_pairs=value["review_pairs"],
            reviewer_digest=value["reviewer_digest"])
    except (TypeError, ValueError) as exc:
        raise ValueError("federated_reviewer_packet_binding_invalid") from exc
    if canonical != dict(value):
        raise ValueError("federated_reviewer_packet_digest_mismatch")
    return canonical


def complete_federated_retrieval_review_template(*,
        template: Mapping[str, Any], labels: Sequence[str]) -> dict[str, Any]:
    """Bind a reviewer's exhaustive labels to the exact blinded pair roster."""
    expected_fields = {"schema_version", "query_set_id", "query_set_digest",
        "federated_manifest_digest", "reviewer_digest", "review_pair_digests",
        "annotations", "authority", "template_digest"}
    if (not isinstance(template, Mapping)
            or set(template) != expected_fields
            or template.get("schema_version") != _FEDERATED_REVIEW_TEMPLATE_SCHEMA
            or template.get("authority") is not False
            or not isinstance(template.get("reviewer_digest"), str)
            or _FEDERATED_REVIEW_TEMPLATE_ID_RE.fullmatch(
                template["reviewer_digest"]) is None
            or not isinstance(template.get("query_set_id"), str)
            or _FEDERATED_QUERY_SET_ID_RE.fullmatch(
                template["query_set_id"]) is None
            or not isinstance(template.get("query_set_digest"), str)
            or _DIGEST_RE.fullmatch(template["query_set_digest"]) is None
            or not isinstance(template.get("federated_manifest_digest"), str)
            or _DIGEST_RE.fullmatch(
                template["federated_manifest_digest"]) is None
            or not isinstance(template.get("review_pair_digests"), list)
            or not isinstance(template.get("annotations"), list)
            or not 1 <= len(template["annotations"]) <= 25_000
            or len(template["review_pair_digests"]) !=
                len(template["annotations"])
            or not isinstance(labels, (list, tuple))
            or len(labels) != len(template["annotations"])):
        raise ValueError("federated_review_template_invalid")
    semantic_template = {key: value for key, value in template.items()
        if key != "template_digest"}
    if template.get("template_digest") != digest_payload(semantic_template):
        raise ValueError("federated_review_template_digest_mismatch")
    output_rows = []
    seen: set[tuple[str, str]] = set()
    for index, row in enumerate(template["annotations"]):
        if (not isinstance(row, Mapping)
                or set(row) != {"question_digest", "record_ref_id",
                    "record_digest", "label"}
                or row.get("label") is not None
                or not isinstance(row.get("question_digest"), str)
                or _DIGEST_RE.fullmatch(row["question_digest"]) is None
                or not isinstance(row.get("record_ref_id"), str)
                or re.fullmatch(r"frec-[0-9a-f]{24}",
                    row["record_ref_id"]) is None
                or not isinstance(row.get("record_digest"), str)
                or _DIGEST_RE.fullmatch(row["record_digest"]) is None
                or not isinstance(template["review_pair_digests"][index], str)
                or _DIGEST_RE.fullmatch(
                    template["review_pair_digests"][index]) is None
                or not isinstance(labels[index], str)
                or labels[index] not in {"relevant", "inapplicable", "neither"}):
            raise ValueError("federated_review_annotation_invalid")
        key = (row["question_digest"], row["record_ref_id"])
        if key in seen:
            raise ValueError("federated_review_annotation_duplicated")
        seen.add(key)
        output_rows.append({**row, "label": labels[index]})
    semantic = {"schema_version": _FEDERATED_REVIEW_SUBMISSION_SCHEMA,
        "query_set_id": template["query_set_id"],
        "query_set_digest": template["query_set_digest"],
        "federated_manifest_digest": template["federated_manifest_digest"],
        "reviewer_digest": template["reviewer_digest"],
        "template_digest": template["template_digest"],
        "review_pair_digests": list(template["review_pair_digests"]),
        "annotations": output_rows, "authority": False}
    return {**semantic, "submission_digest": digest_payload(semantic)}


def validate_federated_retrieval_review_submission(*,
        template: Mapping[str, Any], submission: object) -> dict[str, Any]:
    """Verify every submitted label against its exact blank reviewer template."""
    expected_fields = {"schema_version", "query_set_id", "query_set_digest",
        "federated_manifest_digest", "reviewer_digest", "template_digest",
        "review_pair_digests", "annotations", "authority", "submission_digest"}
    if (not isinstance(submission, Mapping)
            or set(submission) != expected_fields
            or not isinstance(submission.get("annotations"), list)):
        raise ValueError("federated_review_submission_invalid")
    labels = [row.get("label") if isinstance(row, Mapping) else None
        for row in submission["annotations"]]
    try:
        canonical = complete_federated_retrieval_review_template(
            template=template, labels=labels)
    except (TypeError, ValueError) as exc:
        raise ValueError("federated_review_submission_template_invalid") from exc
    if canonical != dict(submission):
        raise ValueError("federated_review_submission_binding_mismatch")
    return canonical


def assemble_federated_retrieval_review_consensus(*,
        reviewer_a_template: Mapping[str, Any], reviewer_a_submission: object,
        reviewer_b_template: Mapping[str, Any], reviewer_b_submission: object,
        consensus_labels: Sequence[str], adjudicator_digest: str,
        blind_consensus_confirmed: bool) -> dict[str, Any]:
    """Seal third-party resolution while preserving initial reviewer agreement."""
    reviewer_a = validate_federated_retrieval_review_submission(
        template=reviewer_a_template, submission=reviewer_a_submission)
    reviewer_b = validate_federated_retrieval_review_submission(
        template=reviewer_b_template, submission=reviewer_b_submission)
    if (reviewer_a["reviewer_digest"] == reviewer_b["reviewer_digest"]
            or reviewer_a["query_set_id"] != reviewer_b["query_set_id"]
            or reviewer_a["query_set_digest"] != reviewer_b["query_set_digest"]
            or reviewer_a["federated_manifest_digest"] !=
                reviewer_b["federated_manifest_digest"]
            or reviewer_a["review_pair_digests"] !=
                reviewer_b["review_pair_digests"]
            or [{key: row[key] for key in ("question_digest",
                    "record_ref_id", "record_digest")}
                for row in reviewer_a["annotations"]] !=
               [{key: row[key] for key in ("question_digest",
                    "record_ref_id", "record_digest")}
                for row in reviewer_b["annotations"]]
            or not isinstance(consensus_labels, (list, tuple))
            or len(consensus_labels) != len(reviewer_a["annotations"])
            or not isinstance(adjudicator_digest, str)
            or _FEDERATED_REVIEW_TEMPLATE_ID_RE.fullmatch(
                adjudicator_digest) is None
            or adjudicator_digest in {reviewer_a["reviewer_digest"],
                reviewer_b["reviewer_digest"]}
            or blind_consensus_confirmed is not True):
        raise ValueError("federated_review_consensus_input_invalid")
    a_labels = [row["label"] for row in reviewer_a["annotations"]]
    b_labels = [row["label"] for row in reviewer_b["annotations"]]
    if any(not isinstance(label, str)
            or label not in {"relevant", "inapplicable", "neither"}
            for label in consensus_labels):
        raise ValueError("federated_review_consensus_label_invalid")
    if any(a == b and consensus != a
            for a, b, consensus in zip(a_labels, b_labels, consensus_labels)):
        raise ValueError("federated_review_consensus_changed_agreement")
    by_question: dict[str, dict[str, int]] = {}
    exact_agreement = 0
    disagreements = 0
    for first, second, row in zip(a_labels, b_labels,
            reviewer_a["annotations"]):
        question_digest = row["question_digest"]
        counts = by_question.setdefault(question_digest,
            {"pair_count": 0, "exact_agreement_count": 0,
                "all_labels_exactly_agreed": True})
        counts["pair_count"] += 1
        if first == second:
            exact_agreement += 1
            counts["exact_agreement_count"] += 1
        else:
            disagreements += 1
            counts["all_labels_exactly_agreed"] = False
    agreement_by_question = {question: {**counts,
        "exact_agreement_rate": counts["exact_agreement_count"] /
            counts["pair_count"]}
        for question, counts in sorted(by_question.items())}
    annotations = [{**row, "label": consensus}
        for row, consensus in zip(reviewer_a["annotations"], consensus_labels)]
    semantic = {"schema_version": _FEDERATED_REVIEW_CONSENSUS_SCHEMA,
        "query_set_id": reviewer_a["query_set_id"],
        "query_set_digest": reviewer_a["query_set_digest"],
        "federated_manifest_digest": reviewer_a["federated_manifest_digest"],
        "review_pair_digests": list(reviewer_a["review_pair_digests"]),
        "reviewer_digests": [reviewer_a["reviewer_digest"],
            reviewer_b["reviewer_digest"]],
        "reviewer_submission_digests": [reviewer_a["submission_digest"],
            reviewer_b["submission_digest"]],
        "adjudicator_digest": adjudicator_digest,
        "blind_consensus_confirmed": True,
        "reviewer_independence_established": False,
        "pair_count": len(annotations),
        "initial_exact_agreement_count": sum(item[
            "all_labels_exactly_agreed"] for item in
            agreement_by_question.values()),
        "initial_exact_agreement_rate": sum(item[
            "all_labels_exactly_agreed"] for item in
            agreement_by_question.values()) / len(agreement_by_question),
        "initial_record_label_agreement_count": exact_agreement,
        "initial_record_label_agreement_rate":
            exact_agreement / len(annotations),
        "initial_disagreement_count": disagreements,
        "agreement_by_question": agreement_by_question,
        "annotations": annotations, "authority": False}
    return {**semantic, "consensus_digest": digest_payload(semantic)}


def validate_federated_retrieval_review_consensus(*,
        reviewer_a_template: Mapping[str, Any], reviewer_a_submission: object,
        reviewer_b_template: Mapping[str, Any], reviewer_b_submission: object,
        consensus: object) -> dict[str, Any]:
    """Recompute the consensus from the bound reviews and adjudicated labels."""
    if (not isinstance(consensus, Mapping)
            or consensus.get("schema_version") !=
                _FEDERATED_REVIEW_CONSENSUS_SCHEMA
            or not isinstance(consensus.get("annotations"), list)):
        raise ValueError("federated_review_consensus_invalid")
    labels = [row.get("label") if isinstance(row, Mapping) else None
        for row in consensus["annotations"]]
    try:
        canonical = assemble_federated_retrieval_review_consensus(
            reviewer_a_template=reviewer_a_template,
            reviewer_a_submission=reviewer_a_submission,
            reviewer_b_template=reviewer_b_template,
            reviewer_b_submission=reviewer_b_submission,
            consensus_labels=labels,
            adjudicator_digest=consensus.get("adjudicator_digest"),
            blind_consensus_confirmed=consensus.get(
                "blind_consensus_confirmed"))
    except (TypeError, ValueError) as exc:
        raise ValueError("federated_review_consensus_binding_invalid") from exc
    if canonical != dict(consensus):
        raise ValueError("federated_review_consensus_digest_mismatch")
    return canonical


def make_federated_retrieval_comparison(*, manifest: Mapping[str, Any],
        query_set: Mapping[str, Any], query_results: Sequence[Mapping[str, Any]],
        lexical_policy_id: str, semantic_policy_id: str,
        retrieval_implementation_digest: str,
        semantic_embedder_identity_digest: str | None) -> dict[str, Any]:
    """Seal source-qualified ordered selections without claiming a gate pass."""
    query_set = validate_federated_retrieval_query_set(
        manifest=manifest, value=query_set)
    corpus_records = validate_federated_history_source_manifest(manifest)
    question_digests = query_set["question_digests"]
    if (not isinstance(query_results, (list, tuple))
            or len(query_results) != len(question_digests)
            or not isinstance(lexical_policy_id, str)
            or not lexical_policy_id or len(lexical_policy_id) > 256
            or not isinstance(semantic_policy_id, str)
            or not semantic_policy_id or len(semantic_policy_id) > 256
            or not isinstance(retrieval_implementation_digest, str)
            or _DIGEST_RE.fullmatch(retrieval_implementation_digest) is None
            or (semantic_embedder_identity_digest is not None
                and (not isinstance(semantic_embedder_identity_digest, str)
                    or _DIGEST_RE.fullmatch(
                        semantic_embedder_identity_digest) is None))):
        raise ValueError("federated_retrieval_comparison_input_invalid")
    normalized_rows = []
    for index, row in enumerate(query_results):
        if (not isinstance(row, Mapping)
                or set(row) != {"question_digest", "lexical_selected_refs",
                    "semantic_selected_refs", "semantic_fallback_to_lexical"}
                or row.get("question_digest") != question_digests[index]
                or type(row.get("semantic_fallback_to_lexical")) is not bool):
            raise ValueError("federated_retrieval_comparison_query_invalid")
        normalized = {"question_digest": question_digests[index]}
        for condition in ("lexical", "semantic"):
            refs = row[f"{condition}_selected_refs"]
            if (not isinstance(refs, (list, tuple)) or len(refs) > 16):
                raise ValueError("federated_retrieval_comparison_selection_invalid")
            selection = []
            seen: set[tuple[str, str]] = set()
            for ref in refs:
                if (not isinstance(ref, Mapping)
                        or set(ref) != {"source_id", "record_id", "record_digest"}
                        or not isinstance(ref.get("source_id"), str)
                        or not isinstance(ref.get("record_id"), str)
                        or not isinstance(ref.get("record_digest"), str)):
                    raise ValueError("federated_retrieval_comparison_record_ref_invalid")
                source_id, record_id = ref["source_id"], ref["record_id"]
                if (corpus_records.get(source_id, {}).get(record_id) !=
                        ref["record_digest"]):
                    raise ValueError("federated_retrieval_comparison_record_unbound")
                key = (source_id, record_id)
                if key in seen:
                    raise ValueError("federated_retrieval_comparison_duplicate_selection")
                seen.add(key)
                selection.append({"source_id": source_id,
                    "record_id": record_id,
                    "record_digest": ref["record_digest"]})
            normalized[f"{condition}_selected_refs"] = selection
        if (row["semantic_fallback_to_lexical"]
                and normalized["semantic_selected_refs"] !=
                    normalized["lexical_selected_refs"]):
            raise ValueError("federated_retrieval_comparison_fallback_mismatch")
        normalized["semantic_fallback_to_lexical"] = (
            row["semantic_fallback_to_lexical"])
        normalized_rows.append(normalized)
    semantic = {"schema_version": _FEDERATED_COMPARISON_SCHEMA,
        "query_set_id": query_set["query_set_id"],
        "query_set_digest": query_set["query_set_digest"],
        "federated_manifest_digest":
            query_set["federated_manifest_digest"],
        "lexical_policy_id": lexical_policy_id,
        "semantic_policy_id": semantic_policy_id,
        "retrieval_implementation_digest": retrieval_implementation_digest,
        "semantic_embedder_identity_digest":
            semantic_embedder_identity_digest,
        "query_results": normalized_rows,
        "authority": False, "learning_established": False,
        "gate_qualification": "not_evaluated"}
    if (semantic_embedder_identity_digest is None
            and any(not row["semantic_fallback_to_lexical"]
                for row in normalized_rows)):
        raise ValueError("federated_retrieval_comparison_embedder_missing")
    return {**semantic, "comparison_digest": digest_payload(semantic)}


def validate_federated_retrieval_comparison(*, manifest: Mapping[str, Any],
        query_set: Mapping[str, Any], value: object) -> dict[str, Any]:
    """Recompute all source, query, order, and selection bindings."""
    expected = {"schema_version", "query_set_id", "query_set_digest",
        "federated_manifest_digest", "lexical_policy_id", "semantic_policy_id",
        "retrieval_implementation_digest", "semantic_embedder_identity_digest",
        "query_results", "authority", "learning_established",
        "gate_qualification", "comparison_digest"}
    if (not isinstance(value, Mapping) or set(value) != expected
            or value.get("schema_version") != _FEDERATED_COMPARISON_SCHEMA
            or value.get("authority") is not False
            or value.get("learning_established") is not False
            or value.get("gate_qualification") != "not_evaluated"
            or not isinstance(value.get("comparison_digest"), str)
            or _DIGEST_RE.fullmatch(value["comparison_digest"]) is None):
        raise ValueError("federated_retrieval_comparison_invalid")
    try:
        canonical = make_federated_retrieval_comparison(manifest=manifest,
            query_set=query_set, query_results=value["query_results"],
            lexical_policy_id=value["lexical_policy_id"],
            semantic_policy_id=value["semantic_policy_id"],
            retrieval_implementation_digest=(
                value["retrieval_implementation_digest"]),
            semantic_embedder_identity_digest=(
                value["semantic_embedder_identity_digest"]))
    except (TypeError, ValueError) as exc:
        raise ValueError("federated_retrieval_comparison_binding_invalid") from exc
    if canonical != dict(value):
        raise ValueError("federated_retrieval_comparison_digest_mismatch")
    return canonical


def score_federated_retrieval_comparison(*, manifest: Mapping[str, Any],
        query_set: Mapping[str, Any], comparison: object,
        reviewer_a_template: Mapping[str, Any], reviewer_a_submission: object,
        reviewer_b_template: Mapping[str, Any], reviewer_b_submission: object,
        consensus: object, experience_anchor_audit: object,
        experience_anchor_verification: object) -> dict[str, Any]:
    """Score frozen selections against exhaustive blinded consensus labels.

    Output applies the query-set's frozen protocol to diagnostics and reports
    conditional intervals and criteria. It never establishes reviewer/source
    independence or durable learning.
    """
    query_set = validate_federated_retrieval_query_set(
        manifest=manifest, value=query_set)
    (experience_anchor_audit_digest,
        experience_anchor_verification_digest,
        source_snapshot_count, source_snapshot_digest, event_anchors) = (
        _verified_query_experience_anchors(query_set=query_set,
            anchor_audit=experience_anchor_audit,
            anchor_verification=experience_anchor_verification))
    protocol = query_set["evaluation_protocol"]
    comparison = validate_federated_retrieval_comparison(
        manifest=manifest, query_set=query_set, value=comparison)
    consensus = validate_federated_retrieval_review_consensus(
        reviewer_a_template=reviewer_a_template,
        reviewer_a_submission=reviewer_a_submission,
        reviewer_b_template=reviewer_b_template,
        reviewer_b_submission=reviewer_b_submission, consensus=consensus)
    if (consensus["query_set_digest"] != query_set["query_set_digest"]
            or consensus["federated_manifest_digest"] !=
                query_set["federated_manifest_digest"]
            or comparison["query_set_digest"] != query_set["query_set_digest"]):
        raise ValueError("federated_retrieval_score_experiment_binding_mismatch")
    records = validate_federated_history_source_manifest(manifest)
    record_digests: dict[str, str] = {}
    for source_id, source_records in records.items():
        for record_id, record_digest in source_records.items():
            ref_id = federated_review_record_ref_id(source_id=source_id,
                record_id=record_id, record_digest=record_digest)
            if ref_id in record_digests:
                raise ValueError("federated_retrieval_score_ref_collision")
            record_digests[ref_id] = record_digest
    expected_annotation_count = len(query_set["questions"]) * len(record_digests)
    if (expected_annotation_count > 25_000
            or consensus["pair_count"] != expected_annotation_count
            or len(consensus["annotations"]) != expected_annotation_count):
        raise ValueError("federated_retrieval_score_annotations_incomplete")
    labels: dict[tuple[str, str], str] = {}
    for row in consensus["annotations"]:
        if (not isinstance(row, Mapping)
                or set(row) != {"question_digest", "record_ref_id",
                    "record_digest", "label"}
                or not isinstance(row.get("question_digest"), str)
                or not isinstance(row.get("record_ref_id"), str)
                or not isinstance(row.get("record_digest"), str)
                or not isinstance(row.get("label"), str)
                or record_digests.get(row["record_ref_id"]) !=
                    row.get("record_digest")
                or row["label"] not in {"relevant", "inapplicable", "neither"}):
            raise ValueError("federated_retrieval_score_annotation_invalid")
        key = (row["question_digest"], row["record_ref_id"])
        if key in labels:
            raise ValueError("federated_retrieval_score_annotation_duplicated")
        labels[key] = row["label"]
    question_digests = query_set["question_digests"]
    expected_keys = {(question_digest, record_ref_id)
        for question_digest in question_digests for record_ref_id in record_digests}
    if set(labels) != expected_keys:
        raise ValueError("federated_retrieval_score_annotation_partition_invalid")
    per_query = []
    for index, result in enumerate(comparison["query_results"]):
        question_digest = question_digests[index]
        stratum = query_set["strata"][index]
        label_rows = {record_ref_id: labels[(question_digest, record_ref_id)]
            for record_ref_id in record_digests}
        relevant = {ref_id for ref_id, label in label_rows.items()
            if label == "relevant"}
        inapplicable = {ref_id for ref_id, label in label_rows.items()
            if label == "inapplicable"}
        selected: dict[str, list[str]] = {}
        metrics: dict[str, Any] = {}
        for condition in ("lexical", "semantic"):
            selected_refs = [federated_review_record_ref_id(
                source_id=ref["source_id"], record_id=ref["record_id"],
                record_digest=ref["record_digest"])
                for ref in result[f"{condition}_selected_refs"]]
            selected[condition] = selected_refs
            hits = [position + 1 for position, ref_id in enumerate(selected_refs)
                if ref_id in relevant]
            metrics[f"recall_{condition}"] = (
                len(set(selected_refs) & relevant) / len(relevant)
                if relevant else None)
            metrics[f"reciprocal_rank_{condition}"] = (
                1 / min(hits) if hits else 0.0) if relevant else None
            common_k = min(len(result["lexical_selected_refs"]),
                len(result["semantic_selected_refs"]))
            metrics[f"common_k_recall_{condition}"] = (
                len(set(selected_refs[:common_k]) & relevant) / len(relevant)
                if relevant else None)
            metrics[f"inapplicable_selected_{condition}"] = (
                bool(selected_refs) if stratum == "no_applicable_history" else
                bool(set(selected_refs) & inapplicable)
                if inapplicable else None)
            metrics[f"nonrelevant_selected_{condition}"] = bool(
                set(selected_refs) - relevant)
            metrics[f"selected_count_{condition}"] = len(selected_refs)
        source_ref = query_set["source_experience_refs"][index]
        source_unit_ref_id = federated_review_record_ref_id(
            source_id=source_ref["source_id"], record_id=source_ref["record_id"],
            record_digest=source_ref["record_digest"])
        source_label = label_rows[source_unit_ref_id]
        source_relevance = ("not_applicable" if stratum ==
            "no_applicable_history" else "verified_relevant"
            if source_label == "relevant" else "not_verified")
        stratum_expectation = (
            not relevant if stratum == "no_applicable_history" else
            bool(relevant and inapplicable) if stratum == "lexical_distractor"
            else bool(relevant))
        per_query.append({"question_digest": question_digest,
            "stratum": stratum,
            "source_experience_unit_digest": source_ref[
                "source_experience_unit_digest"],
            "source_experience_event_anchor_digest": event_anchors[(
                source_ref["record_id"], source_ref["record_digest"])],
            "initial_all_record_label_agreement": consensus[
                "agreement_by_question"][question_digest][
                    "all_labels_exactly_agreed"],
            "source_experience_record_relevance_status": source_relevance,
            "stratum_label_expectations_met": stratum_expectation,
            "relevant_record_count": len(relevant),
            "inapplicable_record_count": len(inapplicable),
            "selected_record_ref_ids_lexical": selected["lexical"],
            "selected_record_ref_ids_semantic": selected["semantic"],
            "same_selected_records": set(selected["lexical"]) ==
                set(selected["semantic"]),
            "same_selected_order": selected["lexical"] == selected["semantic"],
            "semantic_fallback_to_lexical":
                result["semantic_fallback_to_lexical"], **metrics})
    by_stratum: dict[str, Any] = {}
    for stratum in _QUERY_STRATA:
        rows = [row for row in per_query if row["stratum"] == stratum]
        def mean(field: str) -> float | None:
            values = [row[field] for row in rows if row[field] is not None]
            return sum(values) / len(values) if values else None
        by_stratum[stratum] = {"query_count": len(rows),
            "lexical_recall_mean": mean("recall_lexical"),
            "semantic_recall_mean": mean("recall_semantic"),
            "lexical_common_k_recall_mean": mean("common_k_recall_lexical"),
            "semantic_common_k_recall_mean": mean("common_k_recall_semantic"),
            "lexical_reciprocal_rank_mean": mean("reciprocal_rank_lexical"),
            "semantic_reciprocal_rank_mean": mean("reciprocal_rank_semantic"),
            "lexical_inapplicable_selection_rate": mean(
                "inapplicable_selected_lexical"),
            "semantic_inapplicable_selection_rate": mean(
                "inapplicable_selected_semantic"),
            "lexical_nonrelevant_selection_rate": mean(
                "nonrelevant_selected_lexical"),
            "semantic_nonrelevant_selection_rate": mean(
                "nonrelevant_selected_semantic"),
            "semantic_fallback_count": sum(row[
                "semantic_fallback_to_lexical"] for row in rows),
            "source_experience_relevance_verified_count": sum(row[
                "source_experience_record_relevance_status"] ==
                    "verified_relevant" for row in rows),
            "initial_all_record_label_agreement_rate": mean(
                "initial_all_record_label_agreement"),
            "stratum_label_expectations_met_count": sum(row[
                "stratum_label_expectations_met"] for row in rows)}
        for metric in ("recall", "common_k_recall", "reciprocal_rank",
                "inapplicable_selection_rate", "nonrelevant_selection_rate"):
            lexical_field, semantic_field = {
                "recall": ("recall_lexical", "recall_semantic"),
                "common_k_recall": ("common_k_recall_lexical",
                    "common_k_recall_semantic"),
                "reciprocal_rank": ("reciprocal_rank_lexical",
                    "reciprocal_rank_semantic"),
                "inapplicable_selection_rate": (
                    "inapplicable_selected_lexical",
                    "inapplicable_selected_semantic"),
                "nonrelevant_selection_rate": (
                    "nonrelevant_selected_lexical",
                    "nonrelevant_selected_semantic")}[metric]
            lexical_mean, semantic_mean = mean(lexical_field), mean(semantic_field)
            by_stratum[stratum][f"{metric}_semantic_minus_lexical_mean"] = (
                None if lexical_mean is None or semantic_mean is None else
                semantic_mean - lexical_mean)
            paired_differences = [row[semantic_field] - row[lexical_field]
                for row in rows if row[semantic_field] is not None
                    and row[lexical_field] is not None]
            if metric in {"inapplicable_selection_rate",
                    "nonrelevant_selection_rate"}:
                lexical_binary = [float(row[lexical_field]) for row in rows
                    if row[lexical_field] is not None
                    and row[semantic_field] is not None]
                semantic_binary = [float(row[semantic_field]) for row in rows
                    if row[lexical_field] is not None
                    and row[semantic_field] is not None]
                interval = (_paired_binary_difference_ci(lexical_binary,
                    semantic_binary,
                    confidence_level=protocol["confidence_level"])
                    if lexical_binary else None)
            else:
                metric_offsets = protocol["bootstrap_metric_offsets"]
                stratum_offsets = protocol["bootstrap_stratum_offsets"]
                seed = int(query_set["query_set_digest"][7:23], 16)
                interval = _paired_ci(paired_differences,
                    seed=seed + stratum_offsets[stratum]
                        + metric_offsets[metric],
                    bootstrap_samples=protocol["bootstrap_samples"],
                    confidence_level=protocol["confidence_level"])
            by_stratum[stratum].setdefault("paired_95_percent_ci", {})[
                metric] = interval
    agreement_by_stratum = {stratum:
        by_stratum[stratum]["initial_all_record_label_agreement_rate"]
        for stratum in _QUERY_STRATA}
    paraphrase_summary = by_stratum["paraphrased_experience"]
    false_inclusion_criteria = {}
    for stratum in ("lexical_distractor", "no_applicable_history"):
        interval = by_stratum[stratum]["paired_95_percent_ci"][
            "inapplicable_selection_rate"]
        false_inclusion_criteria[stratum] = (interval is not None
            and interval[1] <= protocol["false_inclusion_ci_upper_inclusive"])
    nonrelevant_criteria = {}
    for stratum in ("lexical_distractor", "no_applicable_history"):
        interval = by_stratum[stratum]["paired_95_percent_ci"][
            "nonrelevant_selection_rate"]
        mean_difference = by_stratum[stratum][
            "nonrelevant_selection_rate_semantic_minus_lexical_mean"]
        nonrelevant_criteria[stratum] = (interval is not None
            and interval[1] <= protocol[
                "maximum_nonrelevant_selection_rate_increase"]
            and mean_difference is not None
            and mean_difference <= protocol[
                "maximum_nonrelevant_selection_rate_increase"])
    agreement_passed = all(rate is not None and rate >= protocol[
        "minimum_independent_reviewer_exact_agreement"]
        for rate in agreement_by_stratum.values())
    strata_valid = all(by_stratum[stratum][
        "stratum_label_expectations_met_count"] == by_stratum[stratum][
            "query_count"] for stratum in _QUERY_STRATA)
    source_bindings_valid = all(row[
        "source_experience_record_relevance_status"] == "verified_relevant"
        for row in per_query if row["stratum"] != "no_applicable_history")
    paraphrase_interval = paraphrase_summary["paired_95_percent_ci"][
        "common_k_recall"]
    full_recall_gain = paraphrase_summary[
        "recall_semantic_minus_lexical_mean"]
    protocol_criteria = {
        "minimum_query_count_per_stratum_met": all(by_stratum[stratum][
            "query_count"] >= protocol["minimum_queries_per_stratum"]
            for stratum in _QUERY_STRATA),
        "stratum_label_expectations_met": strata_valid,
        "source_experience_bindings_relevant": source_bindings_valid,
        "source_experience_event_anchors_unique": True,
        "independent_reviewer_agreement_threshold_met": agreement_passed,
        "maximum_semantic_fallback_queries_met": sum(row[
            "semantic_fallback_to_lexical"] for row in per_query)
                <= protocol["maximum_semantic_fallback_queries"],
        "paraphrase_common_k_recall_gain_met": (
            paraphrase_summary["common_k_recall_semantic_minus_lexical_mean"]
                is not None
            and paraphrase_summary[
                "common_k_recall_semantic_minus_lexical_mean"] >=
                    protocol["paraphrase_recall_minimum_gain"]
            and paraphrase_interval is not None
            and paraphrase_interval[0] >
                protocol["paraphrase_recall_ci_lower_exclusive"]),
        "full_selection_recall_gain_met": full_recall_gain is not None
            and full_recall_gain >= protocol[
                "full_selection_recall_minimum_gain"],
        "false_inclusion_intervals_met": all(
            false_inclusion_criteria.values()),
        "nonrelevant_selection_criteria_met": all(
            nonrelevant_criteria.values())}
    protocol_criteria_passed = all(protocol_criteria.values())
    semantic = {"schema_version":
            "sentientos.federated_semantic_history_retrieval_score:v3",
        "query_set_id": query_set["query_set_id"],
        "query_set_digest": query_set["query_set_digest"],
        "federated_manifest_digest":
            query_set["federated_manifest_digest"],
        "comparison_digest": comparison["comparison_digest"],
        "consensus_digest": consensus["consensus_digest"],
        "experience_anchor_audit_digest": experience_anchor_audit_digest,
        "experience_anchor_verification_digest":
            experience_anchor_verification_digest,
        "source_snapshot_count": source_snapshot_count,
        "source_snapshot_digest": source_snapshot_digest,
        "distinct_source_experience_event_count": len(event_anchors),
        "evaluation_protocol": protocol,
        "evaluation_protocol_digest": protocol["protocol_digest"],
        "reviewer_independence_established": False,
        "source_experience_independence_verified": False,
        "per_query": per_query, "by_stratum": by_stratum,
        "reviewer_agreement_by_stratum": agreement_by_stratum,
        "protocol_criteria": protocol_criteria,
        "protocol_criteria_passed": protocol_criteria_passed,
        "gate_qualification": (
            "not_qualified_unverified_reviewer_and_source_independence"
            if protocol_criteria_passed else "not_qualified_criteria_not_met"),
        "confidence_level": protocol["confidence_level"],
        "confidence_interval_sampling_unit": "query_row",
        "confidence_interval_posture": protocol["inferential_posture"],
        "learning_established": False, "authority": False}
    return {**semantic, "score_digest": digest_payload(semantic)}


def validate_federated_retrieval_score(*, manifest: Mapping[str, Any],
        query_set: Mapping[str, Any], comparison: object,
        reviewer_a_template: Mapping[str, Any], reviewer_a_submission: object,
        reviewer_b_template: Mapping[str, Any], reviewer_b_submission: object,
        consensus: object, experience_anchor_audit: object,
        experience_anchor_verification: object,
        score: object) -> dict[str, Any]:
    """Recompute a descriptive score from its complete bound evidence chain."""
    try:
        canonical = score_federated_retrieval_comparison(manifest=manifest,
            query_set=query_set, comparison=comparison,
            reviewer_a_template=reviewer_a_template,
            reviewer_a_submission=reviewer_a_submission,
            reviewer_b_template=reviewer_b_template,
            reviewer_b_submission=reviewer_b_submission,
            consensus=consensus,
            experience_anchor_audit=experience_anchor_audit,
            experience_anchor_verification=experience_anchor_verification)
    except (TypeError, ValueError) as exc:
        raise ValueError("federated_retrieval_score_evidence_invalid") from exc
    if not isinstance(score, Mapping) or canonical != dict(score):
        raise ValueError("federated_retrieval_score_mismatch")
    return canonical


class FederatedHistoryRecordResolver:
    """Resolve frozen source-qualified references against current owners.

    ``source_bindings`` is private runtime configuration keyed by source ID;
    each value contains the matching private ``origin_key`` and live owner.
    The caller supplies the same production projection function used for
    single-owner adjudication. No source record is merged or rewritten.
    """

    def __init__(self, *, manifest: Mapping[str, Any],
            source_bindings: Mapping[str, Mapping[str, Any]],
            project_record: Callable[[Mapping[str, Any]], Mapping[str, Any]]
            ) -> None:
        records = validate_federated_history_source_manifest(manifest)
        if (not isinstance(source_bindings, Mapping)
                or set(source_bindings) != set(records)
                or not callable(project_record)):
            raise ValueError("federated_history_source_bindings_invalid")
        normalized: dict[str, tuple[Any, Mapping[str, str]]] = {}
        for source_id, binding in source_bindings.items():
            if (not isinstance(binding, Mapping)
                    or set(binding) != {"origin_key", "owner"}
                    or source_id_for_origin(binding["origin_key"]) != source_id
                    or not callable(getattr(binding["owner"],
                        "ordinary_chat_developmental_history_corpus_manifest", None))
                    or not callable(getattr(getattr(binding["owner"],
                        "writeback", None), "retrieve", None))):
                raise ValueError("federated_history_source_binding_invalid")
            normalized[source_id] = (binding["owner"], records[source_id])
        self._manifest = deepcopy(dict(manifest))
        self._source_bindings = normalized
        self._project_record = project_record

    def resolve(self, *, source_id: str, record_id: str) -> dict[str, Any]:
        """Revalidate the live source inventory and return one bound projection."""
        binding = self._source_bindings.get(source_id)
        if binding is None:
            raise ValueError("federated_history_source_unknown")
        owner, records = binding
        expected_digest = records.get(record_id)
        if expected_digest is None:
            raise ValueError("federated_history_record_unknown")
        try:
            current = owner.ordinary_chat_developmental_history_corpus_manifest()
            current_digest, current_records = _validate_corpus_manifest(
                current, history_state_digest=current.get("history_state_digest"))
        except Exception as exc:
            raise ValueError("federated_history_source_revalidation_failed") from exc
        source = next(row for row in self._manifest["sources"]
            if row["source_id"] == source_id)
        if ("sha256:" + current_digest != source["corpus_manifest_digest"]
                or current.get("history_state_digest") !=
                    source["history_state_digest"]
                or current_records.get(record_id) != expected_digest):
            raise ValueError("federated_history_source_state_changed")
        try:
            projection = owner.writeback.retrieve([record_id], limit=1)
        except Exception as exc:
            raise ValueError("federated_history_record_unavailable") from exc
        try:
            after = owner.ordinary_chat_developmental_history_corpus_manifest()
            after_digest, after_records = _validate_corpus_manifest(
                after, history_state_digest=after.get("history_state_digest"))
        except Exception as exc:
            raise ValueError("federated_history_source_revalidation_failed") from exc
        if (after_digest != current_digest
                or after.get("history_state_digest") !=
                    current.get("history_state_digest")
                or after_records != current_records):
            raise ValueError("federated_history_source_changed_during_resolution")
        projected_records = getattr(projection, "records", None)
        if (not isinstance(projected_records, (list, tuple))
                or len(projected_records) != 1
                or not isinstance(projected_records[0], Mapping)
                or projected_records[0].get("record_id") != record_id
                or projected_records[0].get("record_digest") != expected_digest):
            raise ValueError("federated_history_record_digest_mismatch")
        try:
            record_projection = self._project_record(projected_records[0])
        except Exception as exc:
            raise ValueError("federated_history_record_projection_failed") from exc
        if not isinstance(record_projection, Mapping):
            raise ValueError("federated_history_record_projection_invalid")
        semantic = {"schema_version":
                "sentientos.federated_history_record_projection:v1",
            "federated_manifest_digest":
                self._manifest["federated_manifest_digest"],
            "source_id": source_id, "history_state_digest":
                source["history_state_digest"], "record_id": record_id,
            "record_digest": expected_digest,
            "source_experience_unit_digest":
                federated_source_experience_record_unit_digest(
                    source_id=source_id, record_id=record_id,
                    record_digest=expected_digest),
            "record_projection": dict(record_projection),
            "authority": False}
        return {**semantic, "projection_digest": digest_payload(semantic)}

    def resolve_many(self, *, references: Sequence[Mapping[str, str]]
            ) -> tuple[dict[str, Any], ...]:
        """Resolve a bounded batch of source-qualified references consistently.

        A single owner supports at most 16 records per retrieval call. The
        batch is capped at that bound per source and each record receives the
        same before/after inventory checks as ``resolve``. A final inventory
        check per source rejects a batch spanning a source-state transition.
        """
        if (not isinstance(references, Sequence)
                or isinstance(references, (str, bytes))
                or not references or len(references) > 100_000):
            raise ValueError("federated_history_references_invalid")
        seen: set[tuple[str, str]] = set()
        counts: dict[str, int] = {}
        normalized: list[tuple[str, str]] = []
        for row in references:
            if (not isinstance(row, Mapping)
                    or set(row) != {"source_id", "record_id"}
                    or not isinstance(row.get("source_id"), str)
                    or not isinstance(row.get("record_id"), str)
                    or not row["record_id"]):
                raise ValueError("federated_history_reference_invalid")
            reference = (row["source_id"], row["record_id"])
            if reference in seen:
                raise ValueError("federated_history_reference_duplicated")
            seen.add(reference)
            counts[reference[0]] = counts.get(reference[0], 0) + 1
            if counts[reference[0]] > 16:
                raise ValueError("federated_history_source_batch_limit")
            normalized.append(reference)
        resolved = tuple(self.resolve(source_id=source_id, record_id=record_id)
            for source_id, record_id in normalized)
        for source_id in counts:
            owner, _ = self._source_bindings[source_id]
            source = next(row for row in self._manifest["sources"]
                if row["source_id"] == source_id)
            try:
                current = owner.ordinary_chat_developmental_history_corpus_manifest()
                current_digest, _ = _validate_corpus_manifest(
                    current, history_state_digest=current.get("history_state_digest"))
            except Exception as exc:
                raise ValueError("federated_history_source_revalidation_failed") from exc
            if ("sha256:" + current_digest != source["corpus_manifest_digest"]
                    or current.get("history_state_digest") !=
                        source["history_state_digest"]):
                raise ValueError("federated_history_source_changed_during_batch")
        return resolved

    def resolve_corpus(self, *, source_id: str
            ) -> tuple[dict[str, Any], ...]:
        """Read every frozen record for one source in bounded batches.

        This is the source-corpus path needed by exhaustive independent
        relevance review. Record projections are never written back to stores.
        """
        binding = self._source_bindings.get(source_id)
        if binding is None:
            raise ValueError("federated_history_source_unknown")
        _, records = binding
        record_ids = sorted(records)
        if not record_ids:
            raise ValueError("federated_history_source_empty")
        resolved: list[dict[str, Any]] = []
        for start in range(0, len(record_ids), 16):
            resolved.extend(self.resolve_many(references=[
                {"source_id": source_id, "record_id": record_id}
                for record_id in record_ids[start:start + 16]]))
        if ([row["record_id"] for row in resolved] != record_ids
                or any(row["source_id"] != source_id for row in resolved)):
            raise ValueError("federated_history_source_projection_partition_invalid")
        return tuple(resolved)

    def verify_sources_unchanged(self) -> None:
        """Recheck every complete source inventory after a federated operation."""
        for source in self._manifest["sources"]:
            source_id = source["source_id"]
            owner, expected_records = self._source_bindings[source_id]
            try:
                current = owner.ordinary_chat_developmental_history_corpus_manifest()
                current_digest, current_records = _validate_corpus_manifest(
                    current, history_state_digest=current.get("history_state_digest"))
            except Exception as exc:
                raise ValueError("federated_history_source_revalidation_failed") from exc
            if ("sha256:" + current_digest != source["corpus_manifest_digest"]
                    or current.get("history_state_digest") !=
                        source["history_state_digest"]
                    or current_records != expected_records):
                raise ValueError("federated_history_source_state_changed")

    def build_review_pair(self, *, query_set: Mapping[str, Any],
            question_digest: str, source_id: str,
            record_id: str) -> dict[str, Any]:
        """Create one blinded query/record unit without condition outcomes."""
        query_set = validate_federated_retrieval_query_set(
            manifest=self._manifest, value=query_set)
        if (not isinstance(question_digest, str)
                or _DIGEST_RE.fullmatch(question_digest) is None):
            raise ValueError("federated_review_pair_question_digest_invalid")
        try:
            index = query_set["question_digests"].index(question_digest)
        except ValueError as exc:
            raise ValueError("federated_review_pair_question_missing") from exc
        projection = self.resolve(source_id=source_id, record_id=record_id)
        return _make_federated_review_pair_from_projection(
            query_set=query_set, question_index=index, source_id=source_id,
            projection=projection)

    def build_review_pairs(self, *, query_set: Mapping[str, Any]
            ) -> tuple[dict[str, Any], ...]:
        """Build the exhaustive blinded roster after one bounded read per source."""
        query_set = validate_federated_retrieval_query_set(
            manifest=self._manifest, value=query_set)
        corpus_records = validate_federated_history_source_manifest(
            self._manifest)
        total_records = sum(len(records) for records in corpus_records.values())
        if (total_records == 0 or
                len(query_set["questions"]) * total_records > 25_000):
            raise ValueError("federated_review_template_pair_count_invalid")
        resolved_by_source = {source["source_id"]: self.resolve_corpus(
            source_id=source["source_id"]) for source in self._manifest["sources"]}
        pairs = []
        for question_index in range(len(query_set["questions"])):
            for source in self._manifest["sources"]:
                source_id = source["source_id"]
                for projection in resolved_by_source[source_id]:
                    pairs.append(_make_federated_review_pair_from_projection(
                        query_set=query_set, question_index=question_index,
                        source_id=source_id, projection=projection))
        pairs.sort(key=lambda pair: (query_set["question_digests"].index(
            pair["question_digest"]), pair["record_ref_id"]))
        self.verify_sources_unchanged()
        if len(pairs) != len(query_set["questions"]) * total_records:
            raise ValueError("federated_review_template_pair_partition_incomplete")
        return tuple(pairs)


class FederatedArchiveHistoryRecordResolver(FederatedHistoryRecordResolver):
    """Resolve frozen source-qualified refs against verified history archives.

    Unlike the live-owner resolver, this binds each source ID to a specific
    source-root hash and to the audit/replay/snapshot artifacts that produced
    its corpus manifest. It is suitable for blinded review and archive-based
    comparison; it does not claim live serving or owner-state equivalence.
    """

    def __init__(self, *, manifest: Mapping[str, Any], archive_binding: object,
            experience_anchor_audit: object,
            experience_anchor_verification: object, read_view: Any,
            project_record: Callable[[Mapping[str, Any]], Mapping[str, Any]]
            ) -> None:
        from .federated_developmental_history import (
            FederatedDevelopmentalHistoryReadView,
        )
        records_by_source = validate_federated_history_source_manifest(manifest)
        if (not isinstance(read_view, FederatedDevelopmentalHistoryReadView)
                or not callable(project_record)
                or not isinstance(archive_binding, Mapping)
                or not isinstance(experience_anchor_audit, Mapping)
                or not isinstance(experience_anchor_verification, Mapping)):
            raise ValueError("federated_archive_resolver_input_invalid")

        binding_semantic = {key: value for key, value in archive_binding.items()
            if key != "binding_digest"}
        audit_semantic = {key: value for key, value in experience_anchor_audit.items()
            if key != "audit_digest"}
        verification_semantic = {key: value for key, value in
            experience_anchor_verification.items() if key != "verification_digest"}
        binding_schema = archive_binding.get("schema_version")
        if (binding_schema == "sentientos.federated_archive_source_binding:v2"
                and set(archive_binding) != {"schema_version",
                    "federated_manifest_digest",
                    "experience_anchor_audit_digest",
                    "experience_anchor_verification_digest",
                    "source_snapshot_count", "source_snapshot_digest",
                    "source_snapshots", "sources", "model_invoked",
                    "learning_established", "authority", "binding_digest"}):
            raise ValueError("federated_archive_binding_v2_shape_invalid")
        if (binding_schema not in {
                "sentientos.federated_archive_source_binding:v1",
                "sentientos.federated_archive_source_binding:v2"}
                or archive_binding.get("binding_digest") !=
                    digest_payload(binding_semantic)
                or archive_binding.get("federated_manifest_digest") !=
                    manifest.get("federated_manifest_digest")
                or experience_anchor_audit.get("schema_version") !=
                    "sentientos.federated_experience_anchor_audit:v3"
                or experience_anchor_audit.get("audit_digest") !=
                    digest_payload(audit_semantic)
                or experience_anchor_verification.get("schema_version") !=
                    "sentientos.federated_experience_anchor_verification:v3"
                or experience_anchor_verification.get("status") != "verified"
                or experience_anchor_verification.get("verification_digest") !=
                    digest_payload(verification_semantic)
                or experience_anchor_verification.get("audit_digest") !=
                    experience_anchor_audit.get("audit_digest")
                or archive_binding.get("experience_anchor_audit_digest") !=
                    experience_anchor_audit.get("audit_digest")
                or archive_binding.get("experience_anchor_verification_digest") !=
                    experience_anchor_verification.get("verification_digest")
                or experience_anchor_verification.get("source_snapshot_count") !=
                    archive_binding.get("source_snapshot_count")
                or experience_anchor_verification.get("source_snapshot_digest") !=
                    archive_binding.get("source_snapshot_digest")
                or experience_anchor_audit.get("source_snapshot_count") !=
                    archive_binding.get("source_snapshot_count")
                or experience_anchor_audit.get("source_snapshot_digest") !=
                    archive_binding.get("source_snapshot_digest")
                or archive_binding.get("model_invoked") is not False
                or archive_binding.get("learning_established") is not False
                or archive_binding.get("authority") is not False
                or not callable(project_record)):
            raise ValueError("federated_archive_binding_invalid")

        if binding_schema == "sentientos.federated_archive_source_binding:v2":
            frozen_snapshots = archive_binding.get("source_snapshots")
            frozen_snapshot_keys: set[tuple[str, str]] = set()
            current_snapshots = {(row["source_root_id"], row["cycle_id"]): row
                for row in read_view.source_snapshots}
            if (not isinstance(frozen_snapshots, list)
                    or not frozen_snapshots
                    or archive_binding.get("source_snapshot_count") !=
                        len(frozen_snapshots)
                    or archive_binding.get("source_snapshot_digest") !=
                        digest_payload(frozen_snapshots)):
                raise ValueError("federated_archive_frozen_snapshot_inventory_invalid")
            for row in frozen_snapshots:
                if (not isinstance(row, Mapping)
                        or set(row) != {"source_root_id", "cycle_id",
                            "composition_state_sha256",
                            "runtime_admission_ledger_sha256",
                            "record_inventory_digest",
                            "receipt_inventory_digest"}
                        or not isinstance(row.get("source_root_id"), str)
                        or not isinstance(row.get("cycle_id"), str)):
                    raise ValueError("federated_archive_frozen_snapshot_row_invalid")
                key = (row["source_root_id"], row["cycle_id"])
                if (key in frozen_snapshot_keys
                        or current_snapshots.get(key) != row):
                    raise ValueError("federated_archive_frozen_snapshot_mismatch")
                frozen_snapshot_keys.add(key)
        else:
            frozen_snapshots = list(read_view.source_snapshots)
            if (archive_binding.get("source_snapshot_count") !=
                    len(frozen_snapshots)
                    or archive_binding.get("source_snapshot_digest") !=
                        digest_payload(frozen_snapshots)):
                raise ValueError("federated_archive_binding_invalid")

        audit_rows: dict[tuple[str, str], list[str]] = {}
        for row in experience_anchor_audit.get("records", []):
            if (not isinstance(row, Mapping)
                    or not isinstance(row.get("record_id"), str)
                    or not isinstance(row.get("record_digest"), str)
                    or not isinstance(row.get("source_root_ids"), list)):
                raise ValueError("federated_archive_audit_record_invalid")
            key = (row["record_id"], row["record_digest"])
            if key in audit_rows:
                raise ValueError("federated_archive_audit_record_duplicated")
            audit_rows[key] = row["source_root_ids"]

        snapshots_by_root: dict[str, list[dict[str, Any]]] = {}
        for row in frozen_snapshots:
            snapshots_by_root.setdefault(row["source_root_id"], []).append(row)
        binding_rows = archive_binding.get("sources")
        if not isinstance(binding_rows, list):
            raise ValueError("federated_archive_source_bindings_invalid")
        binding_by_source = {}
        for row in binding_rows:
            if (not isinstance(row, Mapping)
                    or set(row) != {"source_id", "source_root_id", "record_count",
                        "record_inventory_digest", "source_snapshot_count",
                        "source_snapshot_digest"}
                    or row.get("source_id") in binding_by_source):
                raise ValueError("federated_archive_source_bindings_invalid")
            binding_by_source[row["source_id"]] = row
        manifest_sources = {row["source_id"]: row
            for row in manifest.get("sources", []) if isinstance(row, Mapping)}
        if (set(binding_by_source) != set(records_by_source)
                or set(manifest_sources) != set(records_by_source)):
            raise ValueError("federated_archive_source_partition_invalid")

        source_roots: dict[str, str] = {}
        for source_id, source_row in manifest_sources.items():
            binding_row = binding_by_source[source_id]
            root_id = binding_row["source_root_id"]
            if (not isinstance(root_id, str)
                    or re.fullmatch(r"[0-9a-f]{64}", root_id) is None
                    or source_id != source_id_for_origin(
                        "sentientos-rootless-archive-source:v1:" + root_id)):
                raise ValueError("federated_archive_source_identity_invalid")
            expected_rows = [{"record_id": record_id,
                "record_digest": records_by_source[source_id][record_id]}
                for record_id in sorted(records_by_source[source_id])]
            audit_rows_for_root = [{"record_id": record_id,
                "record_digest": record_digest}
                for (record_id, record_digest), root_ids in sorted(audit_rows.items())
                if root_id in root_ids]
            root_snapshots = snapshots_by_root.get(root_id, [])
            expected_history_digest = digest_payload({
                "schema_version": "sentientos.federated_archive_source_state:v1",
                "source_root_id": root_id,
                "records": expected_rows,
                "source_snapshots": root_snapshots})
            if (not root_snapshots
                    or expected_rows != audit_rows_for_root
                    or source_row.get("records") != expected_rows
                    or source_row.get("history_state_digest") !=
                        expected_history_digest
                    or binding_row.get("record_count") != len(expected_rows)
                    or binding_row.get("record_inventory_digest") !=
                        digest_payload(expected_rows)
                    or binding_row.get("source_snapshot_count") !=
                        len(root_snapshots)
                    or binding_row.get("source_snapshot_digest") !=
                        digest_payload(root_snapshots)):
                raise ValueError("federated_archive_source_binding_mismatch")
            source_roots[source_id] = root_id

        view_provenance = read_view.source_provenance
        for key, root_ids in audit_rows.items():
            provenance = view_provenance.get(key[0])
            if (provenance is None or provenance.get("record_digest") != key[1]
                    or sorted(provenance.get("source_root_ids", [])) !=
                        sorted(root_ids)):
                raise ValueError("federated_archive_source_provenance_mismatch")

        self._manifest = deepcopy(dict(manifest))
        self._source_bindings = {source_id: (read_view,
            records_by_source[source_id]) for source_id in records_by_source}
        self._archive_root_ids = source_roots
        self._read_view = read_view
        self._project_record = project_record

    def resolve(self, *, source_id: str, record_id: str) -> dict[str, Any]:
        binding = self._source_bindings.get(source_id)
        if binding is None:
            raise ValueError("federated_history_source_unknown")
        read_view, records = binding
        expected_digest = records.get(record_id)
        if expected_digest is None:
            raise ValueError("federated_history_record_unknown")
        try:
            record = read_view.get(record_id)
            provenance = read_view.source_provenance.get(record_id)
            if (record.record_digest != expected_digest
                    or provenance is None
                    or self._archive_root_ids[source_id] not in
                        provenance["source_root_ids"]):
                raise ValueError("federated_history_record_digest_mismatch")
            record_projection = self._project_record(asdict(record))
            if not isinstance(record_projection, Mapping):
                raise ValueError("federated_history_record_projection_invalid")
            self.verify_sources_unchanged()
        except Exception as exc:
            if isinstance(exc, ValueError):
                raise
            raise ValueError("federated_history_record_unavailable") from exc
        source = next(row for row in self._manifest["sources"]
            if row["source_id"] == source_id)
        semantic = {"schema_version":
                "sentientos.federated_history_record_projection:v1",
            "federated_manifest_digest":
                self._manifest["federated_manifest_digest"],
            "source_id": source_id,
            "history_state_digest": source["history_state_digest"],
            "record_id": record_id, "record_digest": expected_digest,
            "source_experience_unit_digest":
                federated_source_experience_record_unit_digest(
                    source_id=source_id, record_id=record_id,
                    record_digest=expected_digest),
            "record_projection": dict(record_projection), "authority": False}
        return {**semantic, "projection_digest": digest_payload(semantic)}

    def resolve_many(self, *, references: Sequence[Mapping[str, str]]
            ) -> tuple[dict[str, Any], ...]:
        if (not isinstance(references, Sequence)
                or isinstance(references, (str, bytes))
                or not references or len(references) > 100_000):
            raise ValueError("federated_history_references_invalid")
        seen: set[tuple[str, str]] = set()
        counts: dict[str, int] = {}
        results = []
        for row in references:
            if (not isinstance(row, Mapping)
                    or set(row) != {"source_id", "record_id"}
                    or not isinstance(row.get("source_id"), str)
                    or not isinstance(row.get("record_id"), str)):
                raise ValueError("federated_history_reference_invalid")
            ref = (row["source_id"], row["record_id"])
            if ref in seen:
                raise ValueError("federated_history_reference_duplicated")
            seen.add(ref)
            counts[ref[0]] = counts.get(ref[0], 0) + 1
            if counts[ref[0]] > 16:
                raise ValueError("federated_history_source_batch_limit")
            results.append(self.resolve(source_id=ref[0], record_id=ref[1]))
        self.verify_sources_unchanged()
        return tuple(results)

    def verify_sources_unchanged(self) -> None:
        self._read_view.verify_sources_unchanged()
        provenance = self._read_view.source_provenance
        for source_id, records in self._source_bindings.items():
            root_id = self._archive_root_ids[source_id]
            for record_id, record_digest in records[1].items():
                row = provenance.get(record_id)
                if (row is None or row.get("record_digest") != record_digest
                        or root_id not in row.get("source_root_ids", [])):
                    raise ValueError("federated_history_source_state_changed")


def run_federated_retrieval_comparison(*, manifest: Mapping[str, Any],
        query_set: Mapping[str, Any], resolver: FederatedHistoryRecordResolver,
        lexical_selector: Callable[[str, Sequence[Mapping[str, Any]], int, int],
            Sequence[Mapping[str, str]]],
        semantic_selector: Callable[[str, Sequence[Mapping[str, Any]], int, int],
            Sequence[Mapping[str, str]] | None],
        lexical_policy_id: str, semantic_policy_id: str,
        retrieval_implementation_digest: str,
        semantic_embedder_identity_digest: str | None,
        max_selected_records: int = 8) -> dict[str, Any]:
    """Run both selectors over one complete, source-qualified corpus union.

    Selectors receive the same globally ordered candidate sequence, selected
    record limit, and frozen input-character budget for every question. A
    semantic selector may return ``None`` to explicitly fall back to that
    question's lexical selection. The selector implementation and policy IDs
    are supplied and bound in the resulting comparison artifact; this function
    does not claim that an arbitrary selector matches production semantics.
    """
    query_set = validate_federated_retrieval_query_set(
        manifest=manifest, value=query_set)
    if (not isinstance(resolver, FederatedHistoryRecordResolver)
            or resolver._manifest.get("federated_manifest_digest") !=
                manifest.get("federated_manifest_digest")
            or not callable(lexical_selector)
            or not callable(semantic_selector)
            or type(max_selected_records) is not int
            or not 1 <= max_selected_records <= 128):
        raise ValueError("federated_retrieval_runner_input_invalid")
    corpus_records = validate_federated_history_source_manifest(manifest)
    total_records = sum(len(rows) for rows in corpus_records.values())
    if (total_records == 0
            or len(query_set["questions"]) * total_records > 25_000):
        raise ValueError("federated_retrieval_runner_review_budget_exceeded")
    resolver.verify_sources_unchanged()
    candidates = []
    for source in manifest["sources"]:
        source_id = source["source_id"]
        resolved = resolver.resolve_corpus(source_id=source_id)
        for row in resolved:
            candidates.append({"source_id": source_id,
                "record_id": row["record_id"],
                "record_digest": row["record_digest"],
                "record_projection": row["record_projection"]})
    expected_refs = {(source_id, record_id, record_digest)
        for source_id, source_records in corpus_records.items()
        for record_id, record_digest in source_records.items()}
    actual_refs = {(row["source_id"], row["record_id"], row["record_digest"])
        for row in candidates}
    if len(candidates) != total_records or actual_refs != expected_refs:
        raise ValueError("federated_retrieval_runner_corpus_partition_invalid")
    query_results = []
    for index, question in enumerate(query_set["questions"]):
        question_digest = query_set["question_digests"][index]
        lexical_refs = lexical_selector(question, deepcopy(candidates),
            max_selected_records, query_set["max_input_chars"])
        if not isinstance(lexical_refs, Sequence) or isinstance(
                lexical_refs, (str, bytes)) or len(lexical_refs) > max_selected_records:
            raise ValueError("federated_retrieval_runner_lexical_result_invalid")
        semantic_refs = semantic_selector(question, deepcopy(candidates),
            max_selected_records, query_set["max_input_chars"])
        fallback = semantic_refs is None
        if (not fallback and (not isinstance(semantic_refs, Sequence)
                or isinstance(semantic_refs, (str, bytes))
                or len(semantic_refs) > max_selected_records)):
            raise ValueError("federated_retrieval_runner_semantic_result_invalid")
        query_results.append({"question_digest": question_digest,
            "lexical_selected_refs": list(lexical_refs),
            "semantic_selected_refs": (list(lexical_refs) if fallback
                else list(semantic_refs)),
            "semantic_fallback_to_lexical": fallback})
    resolver.verify_sources_unchanged()
    return make_federated_retrieval_comparison(manifest=manifest,
        query_set=query_set, query_results=query_results,
        lexical_policy_id=lexical_policy_id,
        semantic_policy_id=semantic_policy_id,
        retrieval_implementation_digest=retrieval_implementation_digest,
        semantic_embedder_identity_digest=semantic_embedder_identity_digest)
