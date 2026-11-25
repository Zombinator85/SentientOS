"""Independent relevance scoring for semantic history retrieval cohorts."""
from __future__ import annotations

import json
import math
import random
import re
from typing import Any, Mapping, Sequence

from .local_model_authority import digest_payload

LEGACY_ANNOTATION_SCHEMA = "sentientos.developmental_history_retrieval_annotations:v6"
ANNOTATION_SCHEMA = "sentientos.developmental_history_retrieval_annotations:v7"
RECORD_BOUND_ANNOTATION_SCHEMA = (
    "sentientos.developmental_history_retrieval_annotations:v8")
BLINDED_STRATA_ANNOTATION_SCHEMA = (
    "sentientos.developmental_history_retrieval_annotations:v9")
LEGACY_CORPUS_MANIFEST_SCHEMA = (
    "sentientos.developmental_history_corpus_manifest:v1")
CORPUS_MANIFEST_SCHEMA = "sentientos.developmental_history_corpus_manifest:v2"
LEGACY_EVALUATION_SCHEMA = "sentientos.developmental_history_retrieval_evaluation:v4"
PREVIOUS_COMMON_K_EVALUATION_SCHEMA = (
    "sentientos.developmental_history_retrieval_evaluation:v5")
PREVIOUS_SAMPLING_EVALUATION_SCHEMA = (
    "sentientos.developmental_history_retrieval_evaluation:v6")
PREVIOUS_UNIT_BINDING_EVALUATION_SCHEMA = (
    "sentientos.developmental_history_retrieval_evaluation:v7")
PREVIOUS_RECORD_BINDING_EVALUATION_SCHEMA = (
    "sentientos.developmental_history_retrieval_evaluation:v8")
PREVIOUS_RECORD_RELEVANCE_EVALUATION_SCHEMA = (
    "sentientos.developmental_history_retrieval_evaluation:v9")
PREVIOUS_FALSE_INCLUSION_EVALUATION_SCHEMA = (
    "sentientos.developmental_history_retrieval_evaluation:v10")
PREVIOUS_STRATUM_VALIDATION_EVALUATION_SCHEMA = (
    "sentientos.developmental_history_retrieval_evaluation:v11")
EVALUATION_SCHEMA = "sentientos.developmental_history_retrieval_evaluation:v12"
LEGACY_PROTOCOL_SCHEMA = "sentientos.semantic_history_retrieval_gate:v3"
COMMON_K_PROTOCOL_SCHEMA = "sentientos.semantic_history_retrieval_gate:v4"
COMMON_K_PROTOCOL_SCHEMAS = {COMMON_K_PROTOCOL_SCHEMA,
    "sentientos.semantic_history_retrieval_gate:v5",
    "sentientos.semantic_history_retrieval_gate:v6",
    "sentientos.semantic_history_retrieval_gate:v7",
    "sentientos.semantic_history_retrieval_gate:v8",
    "sentientos.semantic_history_retrieval_gate:v9",
    "sentientos.semantic_history_retrieval_gate:v10",
    "sentientos.semantic_history_retrieval_gate:v11",
    "sentientos.semantic_history_retrieval_gate:v12"}
FALLBACK_GATED_PROTOCOL_SCHEMA = "sentientos.semantic_history_retrieval_gate:v5"
FALLBACK_GATED_PROTOCOL_SCHEMAS = {FALLBACK_GATED_PROTOCOL_SCHEMA,
    "sentientos.semantic_history_retrieval_gate:v6",
    "sentientos.semantic_history_retrieval_gate:v7",
    "sentientos.semantic_history_retrieval_gate:v8",
    "sentientos.semantic_history_retrieval_gate:v9",
    "sentientos.semantic_history_retrieval_gate:v10",
    "sentientos.semantic_history_retrieval_gate:v11",
    "sentientos.semantic_history_retrieval_gate:v12"}
FINITE_SAMPLE_FALSE_INCLUSION_PROTOCOL_SCHEMAS = {
    "sentientos.semantic_history_retrieval_gate:v11",
    "sentientos.semantic_history_retrieval_gate:v12"}
NONRELEVANT_SELECTION_PROTOCOL_SCHEMAS = {
    "sentientos.semantic_history_retrieval_gate:v8",
    "sentientos.semantic_history_retrieval_gate:v9",
    "sentientos.semantic_history_retrieval_gate:v10",
    *FINITE_SAMPLE_FALSE_INCLUSION_PROTOCOL_SCHEMAS}
STRATA = ("paraphrased_experience", "lexical_distractor",
    "no_applicable_history")
MIN_QUERIES = 60
MAX_QUERIES = 255
BOOTSTRAP_SAMPLES = 10_000
MAX_ANNOTATION_ARTIFACT_BYTES = 2_097_152


def retrieval_source_experience_record_unit_digest(*, record_id: str,
        record_digest: str) -> str:
    """Derive a sampling-unit ID from one exact frozen history record ref."""
    if (not isinstance(record_id, str) or not record_id
            or not isinstance(record_digest, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", record_digest) is None):
        raise ValueError("retrieval_source_experience_record_ref_invalid")
    return digest_payload({
        "schema_version": "sentientos.retrieval_source_experience_record_unit:v1",
        "record_id": record_id, "record_digest": record_digest})


def retrieval_adjudication_procedure(*, source_record_bindings: bool = False,
        conceal_preregistered_strata: bool = False
        ) -> dict[str, Any]:
    """Return the fixed blinded rubric used for record-level relevance labels."""
    instructions = [
            "Judge each query-record pair from the query and the bounded record projection only.",
            "Do not inspect retrieval selections, rankings, condition names, or model answers.",
            "Mark relevant only when the record bears directly on the query and its task scope, source-model applicability, and evidence posture permit that use.",
            "Mark inapplicable when the record must be excluded for scope, source-model, or evidence-posture mismatch; ordinary irrelevance alone is not inapplicability.",
            "Use the packet's target model identity when assessing source-model applicability; if it is unbound, do not assume same-model applicability.",
            "Assign exactly one label to every record in the frozen corpus for each query: relevant, inapplicable, or neither.",
            "Two reviewers must independently label the packet before discussion; preserve both label sets and do not expose retrieval outcomes to either reviewer.",
            "Resolve disagreements by blind consensus before scoring and retain the initial independent labels so agreement can be reported.",
            "Treat historical claims as historical claims, never as current truth or authority.",
            "Assign one source-experience digest per independent experience and do not reuse an experience across queries.",
            "Record disagreement and uncertainty in the external adjudication notes; do not resolve uncertainty by viewing retrieval outcomes."]
    if source_record_bindings or conceal_preregistered_strata:
        instructions.remove(
            "Assign one source-experience digest per independent experience and do not reuse an experience across queries.")
    if not conceal_preregistered_strata:
        instructions.insert(9,
            "For no-applicable-history queries, mark no records relevant; any selected record counts as false inclusion.")
    semantic = {"schema_version": (
            "sentientos.developmental_history_retrieval_adjudication_procedure:v5"
            if conceal_preregistered_strata else
            "sentientos.developmental_history_retrieval_adjudication_procedure:v4"
            if source_record_bindings else
            "sentientos.developmental_history_retrieval_adjudication_procedure:v3"),
        "rubric_id": ("eligible_historical_relevance_and_scope:v5"
            if conceal_preregistered_strata else
            "eligible_historical_relevance_and_scope:v4"
            if source_record_bindings else
            "eligible_historical_relevance_and_scope:v3"),
        "instructions": instructions,
        "labels": {"relevant": "directly bears on the query and is applicable under the record's qualifiers",
            "inapplicable": "must be excluded due to a scope, source-model, or evidence-posture mismatch",
            "neither": "not relevant, but no explicit exclusion mismatch is established"},
        "historical_only": True, "current_truth": False, "authority": False}
    return {**semantic, "procedure_digest": digest_payload(semantic)}


def build_retrieval_reviewer_template(*, packet: Mapping[str, Any],
        reviewer_digest: str) -> dict[str, Any]:
    """Build one exhaustive, blank-label reviewer submission from a blinded packet."""
    if (not isinstance(packet, Mapping)
            or not isinstance(reviewer_digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", reviewer_digest) is None):
        raise ValueError("retrieval_reviewer_template_input_invalid")
    semantic = {key: value for key, value in packet.items()
        if key != "packet_digest"}
    queries = packet.get("queries")
    corpus_refs = packet.get("corpus_record_refs")
    corpus_digest = packet.get("corpus_manifest_digest")
    packet_fields = {"schema_version", "cohort_id", "cohort_digest",
        "history_state_digest", "corpus_manifest_digest",
        "target_model_identity", "target_model_identity_digest",
        "corpus_record_refs", "queries", "adjudication_procedure",
        "condition_selections_included", "generative_model_invoked",
        "authority", "packet_digest"}
    packet_schema = packet.get("schema_version")
    if (set(packet) != packet_fields
            or not isinstance(packet_schema, str)
            or packet_schema not in {
                "sentientos.developmental_history_retrieval_adjudication_packet:v5",
                "sentientos.developmental_history_retrieval_adjudication_packet:v6",
                "sentientos.developmental_history_retrieval_adjudication_packet:v7",
                "sentientos.developmental_history_retrieval_adjudication_packet:v8"}
            or packet.get("condition_selections_included") is not False
            or packet.get("generative_model_invoked") is not False
            or packet.get("authority") is not False
            or packet.get("adjudication_procedure") !=
                retrieval_adjudication_procedure(source_record_bindings=(
                    packet_schema ==
                    "sentientos.developmental_history_retrieval_adjudication_packet:v7"),
                    conceal_preregistered_strata=(packet_schema ==
                        "sentientos.developmental_history_retrieval_adjudication_packet:v8"))
            or packet.get("packet_digest") != digest_payload(semantic)
            or not isinstance(corpus_digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", corpus_digest) is None
            or not isinstance(queries, list) or not queries
            or not isinstance(corpus_refs, list) or not corpus_refs):
        raise ValueError("retrieval_reviewer_template_packet_invalid")
    history_state_digest = packet.get("history_state_digest")
    target_identity = packet.get("target_model_identity")
    target_identity_digest = packet.get("target_model_identity_digest")
    if ((not isinstance(history_state_digest, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", history_state_digest) is None)
            or ((target_identity is None) != (target_identity_digest is None))
            or (target_identity is not None
                and (not isinstance(target_identity, Mapping)
                    or not isinstance(target_identity_digest, str)
                    or re.fullmatch(r"[0-9a-f]{64}", target_identity_digest) is None
                    or digest_payload(dict(target_identity)) != target_identity_digest))):
        raise ValueError("retrieval_reviewer_template_packet_identity_invalid")
    preregistered_units = packet_schema.endswith(":v6")
    concealed_strata = packet_schema.endswith(":v8")
    records: list[dict[str, str]] = []
    for ref in corpus_refs:
        if (not isinstance(ref, Mapping)
                or set(ref) != {"record_id", "record_digest"}
                or not isinstance(ref.get("record_id"), str)
                or not ref["record_id"]
                or not isinstance(ref.get("record_digest"), str)
                or re.fullmatch(r"sha256:[0-9a-f]{64}",
                    ref["record_digest"]) is None
                or (records and ref["record_id"] <= records[-1]["record_id"])):
            raise ValueError("retrieval_reviewer_template_corpus_invalid")
        records.append({"record_id": ref["record_id"],
            "record_digest": ref["record_digest"]})
    manifest_semantic = {"schema_version": CORPUS_MANIFEST_SCHEMA,
        "history_state_digest": history_state_digest, "records": records}
    if digest_payload(manifest_semantic) != corpus_digest:
        raise ValueError("retrieval_reviewer_template_corpus_manifest_mismatch")
    annotations: list[dict[str, Any]] = []
    question_digests: set[str] = set()
    source_experience_digests: set[str] = set()
    for query in queries:
        query_fields = ({"question_digest", "question"} if concealed_strata
            else {"question_digest", "question", "preregistered_stratum"})
        if preregistered_units:
            query_fields.add("source_experience_digest")
        if (not isinstance(query, Mapping)
                or set(query) != query_fields
                or not isinstance(query.get("question"), str)
                or not query["question"].strip()
                or not isinstance(query.get("question_digest"), str)
                or re.fullmatch(r"[0-9a-f]{64}",
                    query["question_digest"]) is None
                or query["question_digest"] in question_digests
                or (not concealed_strata and
                    query.get("preregistered_stratum") not in STRATA)):
            raise ValueError("retrieval_reviewer_template_query_invalid")
        if query["question_digest"] != digest_payload(
                {"question": query["question"]}):
            raise ValueError("retrieval_reviewer_template_query_digest_mismatch")
        question_digests.add(query["question_digest"])
        if preregistered_units:
            source_digest = query.get("source_experience_digest")
            if (not isinstance(source_digest, str)
                    or re.fullmatch(r"[0-9a-f]{64}", source_digest) is None
                    or source_digest in source_experience_digests):
                raise ValueError("retrieval_reviewer_template_query_invalid")
            source_experience_digests.add(source_digest)
        annotations.append({"question_digest": query["question_digest"],
            **({"stratum": query["preregistered_stratum"]}
                if not concealed_strata else {}),
            "reviewed_corpus_manifest_digest": corpus_digest,
            "record_labels": [{**record, "label": None}
                for record in records]})
    result = {"reviewer_digest": reviewer_digest,
        "annotations": annotations}
    try:
        encoded_size = len(json.dumps(result, ensure_ascii=False,
            sort_keys=True, separators=(",", ":"), allow_nan=False)
            .encode("utf-8"))
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("retrieval_reviewer_template_invalid") from exc
    if encoded_size > MAX_ANNOTATION_ARTIFACT_BYTES // 4:
        raise ValueError("retrieval_reviewer_template_over_bound")
    return result


def build_retrieval_consensus_template(*,
        packet: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Build blank consensus rows using only fields visible in this packet version."""
    skeleton = build_retrieval_reviewer_template(packet=packet,
        reviewer_digest="0" * 64)
    packet_queries = packet["queries"]
    rows = []
    for template_row, query in zip(skeleton["annotations"], packet_queries):
        row = {"question_digest": template_row["question_digest"],
            "reviewed_corpus_manifest_digest":
                template_row["reviewed_corpus_manifest_digest"],
            "record_labels": template_row["record_labels"]}
        if "stratum" in template_row:
            row["stratum"] = template_row["stratum"]
        if "source_experience_digest" in query:
            row["source_experience_digest"] = query[
                "source_experience_digest"]
        rows.append(row)
    try:
        encoded_size = len(json.dumps(rows, ensure_ascii=False,
            sort_keys=True, separators=(",", ":"), allow_nan=False)
            .encode("utf-8"))
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("retrieval_consensus_template_invalid") from exc
    if encoded_size > MAX_ANNOTATION_ARTIFACT_BYTES // 4:
        raise ValueError("retrieval_consensus_template_over_bound")
    return rows


def _complete_record_labels(value: object, *, records: Mapping[str, str]
        ) -> dict[str, set[str]]:
    """Validate an exhaustive query label partition against the frozen corpus."""
    if not isinstance(value, list) or len(value) != len(records):
        raise ValueError("retrieval_annotation_corpus_partition_incomplete")
    labels: dict[str, set[str]] = {"relevant": set(),
        "inapplicable": set(), "neither": set()}
    seen: set[str] = set()
    previous_id: str | None = None
    for row in value:
        if (not isinstance(row, Mapping)
                or set(row) != {"record_id", "record_digest", "label"}
                or not isinstance(row.get("record_id"), str)
                or not isinstance(row.get("record_digest"), str)
                or row.get("label") not in labels
                or records.get(row["record_id"]) != row["record_digest"]
                or row["record_id"] in seen
                or (previous_id is not None and row["record_id"] <= previous_id)):
            raise ValueError("retrieval_annotation_corpus_partition_invalid")
        labels[row["label"]].add(row["record_id"])
        seen.add(row["record_id"])
        previous_id = row["record_id"]
    if seen != set(records):
        raise ValueError("retrieval_annotation_corpus_partition_incomplete")
    return labels


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _paired_ci(values: list[float], *, seed: int,
        bootstrap_samples: int = BOOTSTRAP_SAMPLES,
        confidence_level: float = 0.95) -> list[float] | None:
    if not values:
        return None
    generator = random.Random(seed)
    sample_count = len(values)
    means = sorted(_mean([values[generator.randrange(sample_count)]
        for _ in range(sample_count)]) for _ in range(bootstrap_samples))
    lower = (1 - confidence_level) / 2
    return [means[int((bootstrap_samples - 1) * lower)],
        means[int((bootstrap_samples - 1) * (1 - lower))]]


def _binomial_cdf(successes: int, trials: int, probability: float) -> float:
    if successes < 0:
        return 0.0
    if successes >= trials:
        return 1.0
    return sum(math.comb(trials, index) * probability ** index
        * (1 - probability) ** (trials - index)
        for index in range(successes + 1))


def _binomial_lower_tail_bound(successes: int, trials: int,
        tail_probability: float) -> float:
    """One-sided Clopper-Pearson lower bound for a binomial proportion."""
    if successes <= 0:
        return 0.0
    low, high = 0.0, successes / trials
    for _ in range(64):
        middle = (low + high) / 2
        upper_tail = 1 - _binomial_cdf(successes - 1, trials, middle)
        if upper_tail < tail_probability:
            low = middle
        else:
            high = middle
    return (low + high) / 2


def _binomial_upper_tail_bound(successes: int, trials: int,
        tail_probability: float) -> float:
    """One-sided Clopper-Pearson upper bound for a binomial proportion."""
    if successes >= trials:
        return 1.0
    low, high = successes / trials, 1.0
    for _ in range(64):
        middle = (low + high) / 2
        if _binomial_cdf(successes, trials, middle) > tail_probability:
            low = middle
        else:
            high = middle
    return (low + high) / 2


def _paired_binary_difference_ci(lexical: list[float],
        semantic: list[float], *, confidence_level: float) -> list[float]:
    """Conservative paired risk-difference interval via exact binomial bounds.

    Treats semantic-only selections as adverse discordances and lexical-only
    selections as beneficial discordances. Bonferroni-adjusted one-sided exact
    bounds give a finite-sample interval without percentile-bootstrap boundary
    degeneracy.
    """
    if not lexical or len(lexical) != len(semantic):
        raise ValueError("paired_binary_difference_inputs_invalid")
    if any(value not in (0.0, 1.0) for value in (*lexical, *semantic)):
        raise ValueError("paired_binary_difference_outcomes_invalid")
    adverse = sum(left == 0.0 and right == 1.0
        for left, right in zip(lexical, semantic))
    beneficial = sum(left == 1.0 and right == 0.0
        for left, right in zip(lexical, semantic))
    # Four one-sided proportion bounds define both interval endpoints; split
    # alpha across all four so the returned two-sided interval has joint
    # coverage of at least the requested confidence level.
    tail = (1 - confidence_level) / 4
    trials = len(lexical)
    lower = (_binomial_lower_tail_bound(adverse, trials, tail)
        - _binomial_upper_tail_bound(beneficial, trials, tail))
    upper = (_binomial_upper_tail_bound(adverse, trials, tail)
        - _binomial_lower_tail_bound(beneficial, trials, tail))
    return [max(-1.0, lower), min(1.0, upper)]


def _zero_discordance_binary_difference_upper_bound(*, query_count: int,
        confidence_level: float) -> float:
    """Return the paired CI upper limit when neither condition has discordances."""
    if type(query_count) is not int or query_count <= 0:
        raise ValueError("paired_binary_difference_query_count_invalid")
    tail = (1 - confidence_level) / 4
    return 1 - tail ** (1 / query_count)


def make_retrieval_corpus_manifest(*, history_state_digest: str,
        records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Build the canonical digest-bound inventory for a frozen history corpus."""
    if (not isinstance(history_state_digest, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", history_state_digest) is None
            or not isinstance(records, Sequence)
            or isinstance(records, (str, bytes))
            or not records or len(records) > 100_000):
        raise ValueError("retrieval_corpus_manifest_input_invalid")
    normalized: list[dict[str, str]] = []
    for row in records:
        if (not isinstance(row, Mapping)
                or set(row) != {"record_id", "record_digest"}
                or not isinstance(row.get("record_id"), str)
                or not 1 <= len(row["record_id"]) <= 256
                or not isinstance(row.get("record_digest"), str)
                or re.fullmatch(r"sha256:[0-9a-f]{64}",
                    row["record_digest"]) is None):
            raise ValueError("retrieval_corpus_manifest_record_invalid")
        normalized.append({"record_id": row["record_id"],
            "record_digest": row["record_digest"]})
    normalized.sort(key=lambda row: row["record_id"])
    if len({row["record_id"] for row in normalized}) != len(normalized):
        raise ValueError("retrieval_corpus_manifest_duplicate_record")
    semantic = {"schema_version": CORPUS_MANIFEST_SCHEMA,
        "history_state_digest": history_state_digest,
        "records": normalized}
    return {**semantic, "corpus_manifest_digest": digest_payload(semantic)}


def make_retrieval_relevance_annotations(*, packet: Mapping[str, Any],
        adjudication_procedure_digest: str,
        annotations: Sequence[Mapping[str, Any]],
        independent_reviewers: Sequence[Mapping[str, Any]],
        blind_consensus: bool,
        sealed_strata: Sequence[str] | None = None,
        sealed_source_experience_digests: Sequence[str] | None = None,
        sealed_source_record_bindings: bool = False) -> dict[str, Any]:
    """Seal externally judged query labels to the exact blinded packet."""
    if not isinstance(packet, Mapping):
        raise ValueError("retrieval_adjudication_packet_invalid")
    packet_semantic = {key: value for key, value in packet.items()
        if key != "packet_digest"}
    expected_packet_fields = {"schema_version", "cohort_id", "cohort_digest",
        "history_state_digest", "corpus_manifest_digest", "target_model_identity",
        "target_model_identity_digest", "corpus_record_refs",
        "queries", "adjudication_procedure", "condition_selections_included", "generative_model_invoked",
        "authority", "packet_digest"}
    questions = packet.get("queries")
    packet_schema = packet.get("schema_version")
    preregistered_units = (packet_schema ==
        "sentientos.developmental_history_retrieval_adjudication_packet:v6")
    record_bound_units = (packet_schema ==
        "sentientos.developmental_history_retrieval_adjudication_packet:v7")
    concealed_strata_units = (packet_schema ==
        "sentientos.developmental_history_retrieval_adjudication_packet:v8")
    packet_source_digests = ([row.get("source_experience_digest")
        if isinstance(row, Mapping) else None for row in questions]
        if preregistered_units and isinstance(questions, list) else None)
    query_bindings_valid = (isinstance(questions, list) and all(
        isinstance(row, Mapping)
        and isinstance(row.get("question"), str)
        and row.get("question_digest") == digest_payload(
            {"question": row["question"]}) for row in questions))
    manifest_records = packet.get("corpus_record_refs")
    manifest_binding_valid = False
    if isinstance(manifest_records, list):
        manifest_semantic = {"schema_version": CORPUS_MANIFEST_SCHEMA,
            "history_state_digest": packet.get("history_state_digest"),
            "records": manifest_records}
        manifest_binding_valid = (
            isinstance(packet.get("history_state_digest"), str)
            and re.fullmatch(r"sha256:[0-9a-f]{64}",
                packet["history_state_digest"]) is not None
            and digest_payload(manifest_semantic) ==
                packet.get("corpus_manifest_digest"))
    if (set(packet) != expected_packet_fields
            or not isinstance(packet_schema, str)
            or packet_schema not in {
                "sentientos.developmental_history_retrieval_adjudication_packet:v5",
                "sentientos.developmental_history_retrieval_adjudication_packet:v6",
                "sentientos.developmental_history_retrieval_adjudication_packet:v7",
                "sentientos.developmental_history_retrieval_adjudication_packet:v8"}
            or packet.get("condition_selections_included") is not False
            or packet.get("generative_model_invoked") is not False
            or packet.get("authority") is not False
            or packet.get("adjudication_procedure") !=
                retrieval_adjudication_procedure(source_record_bindings=(
                    packet_schema ==
                    "sentientos.developmental_history_retrieval_adjudication_packet:v7"),
                    conceal_preregistered_strata=concealed_strata_units)
            or ((packet.get("target_model_identity") is None)
                != (packet.get("target_model_identity_digest") is None))
            or (packet.get("target_model_identity") is not None
                and (not isinstance(packet["target_model_identity"], Mapping)
                    or digest_payload(dict(packet["target_model_identity"])) !=
                        packet["target_model_identity_digest"]))
            or adjudication_procedure_digest !=
                packet["adjudication_procedure"]["procedure_digest"]
            or packet.get("packet_digest") != digest_payload(packet_semantic)
            or not query_bindings_valid
            or not manifest_binding_valid
            or not isinstance(questions, list)
            or any(not isinstance(row, Mapping)
                or set(row) != ({"question_digest", "question"}
                    if concealed_strata_units else {"question_digest", "question",
                    "preregistered_stratum", "source_experience_digest"}
                    if preregistered_units else {"question_digest", "question",
                        "preregistered_stratum"})
                for row in questions)
            or (preregistered_units and (
                any(not isinstance(item, str)
                    or re.fullmatch(r"[0-9a-f]{64}", item) is None
                    for item in packet_source_digests or [])
                or len(set(packet_source_digests or [])) != len(questions)))
            or not isinstance(annotations, Sequence)
            or isinstance(annotations, (str, bytes))
            or len(annotations) != len(questions)
            or not isinstance(independent_reviewers, Sequence)
            or isinstance(independent_reviewers, (str, bytes))
            or len(independent_reviewers) != 2
            or any(not isinstance(reviewer, Mapping)
                or set(reviewer) != {"reviewer_digest", "annotations"}
                or not isinstance(reviewer.get("reviewer_digest"), str)
                or re.fullmatch(r"[0-9a-f]{64}",
                    reviewer["reviewer_digest"]) is None
                or not isinstance(reviewer.get("annotations"), Sequence)
                or isinstance(reviewer.get("annotations"), (str, bytes))
                or len(reviewer["annotations"]) != len(questions)
                for reviewer in independent_reviewers)
            or independent_reviewers[0]["reviewer_digest"] ==
                independent_reviewers[1]["reviewer_digest"]
            or blind_consensus is not True
            or not isinstance(adjudication_procedure_digest, str)
            or re.fullmatch(r"[0-9a-f]{64}",
                adjudication_procedure_digest) is None):
        raise ValueError("retrieval_adjudication_packet_binding_invalid")
    question_digests = [row.get("question_digest")
        if isinstance(row, Mapping) else None for row in questions]
    question_strata = (list(sealed_strata) if concealed_strata_units
        and isinstance(sealed_strata, Sequence)
        and not isinstance(sealed_strata, (str, bytes)) else
        [row.get("preregistered_stratum")
            if isinstance(row, Mapping) else None for row in questions])
    if (any(not isinstance(value, str)
                or re.fullmatch(r"[0-9a-f]{64}", value) is None
                for value in question_digests)
            or [row.get("question_digest") if isinstance(row, Mapping) else None
                for row in annotations] != question_digests
            or len(question_strata) != len(questions)
            or any(stratum not in STRATA for stratum in question_strata)
            or (concealed_strata_units and type(sealed_source_record_bindings)
                is not bool)):
        raise ValueError("retrieval_annotation_question_order_invalid")
    if (not concealed_strata_units and
            [row.get("stratum") if isinstance(row, Mapping) else None
                for row in annotations] != question_strata):
        raise ValueError("retrieval_annotation_preregistered_stratum_mismatch")
    if (preregistered_units and [row.get("source_experience_digest")
            if isinstance(row, Mapping) else None for row in annotations]
            != packet_source_digests):
        raise ValueError("retrieval_annotation_source_experience_preregistration_mismatch")
    packet_records = {ref["record_id"]: ref["record_digest"]
        for ref in packet["corpus_record_refs"]}
    if concealed_strata_units:
        if (not isinstance(sealed_source_experience_digests, Sequence)
                or isinstance(sealed_source_experience_digests, (str, bytes))
                or len(sealed_source_experience_digests) != len(questions)
                or any(not isinstance(item, str)
                    or re.fullmatch(r"[0-9a-f]{64}", item) is None
                    for item in sealed_source_experience_digests)
                or (not sealed_source_record_bindings
                    and len(set(sealed_source_experience_digests))
                        != len(questions))):
            raise ValueError("retrieval_annotation_hidden_query_bindings_invalid")
    def labels_by_question(rows: Sequence[Mapping[str, Any]]) -> list[tuple[str, str]]:
        labels: list[tuple[str, str]] = []
        for index, row in enumerate(rows):
            reviewer_fields = {"question_digest",
                "reviewed_corpus_manifest_digest", "record_labels"}
            if not concealed_strata_units:
                reviewer_fields.add("stratum")
            if (not isinstance(row, Mapping)
                    or set(row) != reviewer_fields
                    or row.get("question_digest") != question_digests[index]
                    or (not concealed_strata_units and
                        row.get("stratum") != question_strata[index])
                    or row.get("reviewed_corpus_manifest_digest") !=
                        packet.get("corpus_manifest_digest")):
                raise ValueError("retrieval_independent_annotation_row_invalid")
            row_labels = _complete_record_labels(row.get("record_labels"),
                records=packet_records)
            relevant_ids = row_labels["relevant"]
            inapplicable_ids = row_labels["inapplicable"]
            stratum = question_strata[index]
            if (relevant_ids & inapplicable_ids
                    or (not concealed_strata_units and (
                    (stratum == "no_applicable_history" and relevant_ids)
                    or (stratum != "no_applicable_history" and not relevant_ids)
                    or (stratum == "lexical_distractor" and not inapplicable_ids)))):
                raise ValueError("retrieval_independent_annotation_labels_invalid")
            labels.append((digest_payload(sorted(relevant_ids)),
                digest_payload(sorted(inapplicable_ids))))
        return labels
    reviewer_labels = [labels_by_question(reviewer["annotations"])
        for reviewer in independent_reviewers]
    agreement_count = sum(first == second for first, second in
        zip(*reviewer_labels))
    agreement_by_stratum: dict[str, Any] = {}
    for stratum in STRATA:
        indexes = [index for index, value in enumerate(question_strata)
            if value == stratum]
        count = sum(reviewer_labels[0][index] == reviewer_labels[1][index]
            for index in indexes)
        agreement_by_stratum[stratum] = {"query_count": len(indexes),
            "exact_label_agreement_count": count,
            "exact_label_agreement_rate": count / len(indexes) if indexes else 0.0}
    expected_consensus_fields = {"question_digest",
        "reviewed_corpus_manifest_digest", "record_labels"} if (
            concealed_strata_units) else {"question_digest", "stratum",
                "reviewed_corpus_manifest_digest", "record_labels"}
    if not record_bound_units and not concealed_strata_units:
        expected_consensus_fields.add("source_experience_digest")
    if any(not isinstance(row, Mapping)
            or set(row) != expected_consensus_fields
            or row.get("reviewed_corpus_manifest_digest") !=
                packet.get("corpus_manifest_digest")
            or not isinstance(row.get("record_labels"), list)
            for row in annotations):
        raise ValueError("retrieval_annotation_corpus_partition_invalid")
    consensus_labels = [_complete_record_labels(row["record_labels"],
        records=packet_records) for row in annotations]
    consensus_label_hashes: list[tuple[str, str]] = []
    for stratum, row_labels in zip(question_strata, consensus_labels):
        if (not concealed_strata_units and (
                (stratum == "no_applicable_history" and row_labels["relevant"])
                or (stratum != "no_applicable_history"
                    and not row_labels["relevant"])
                or (stratum == "lexical_distractor"
                    and not row_labels["inapplicable"]))):
            raise ValueError("retrieval_annotation_labels_invalid")
        consensus_label_hashes.append((digest_payload(
            sorted(row_labels["relevant"])), digest_payload(
            sorted(row_labels["inapplicable"]))))
    consensus_resolution = {"query_count": len(questions),
        "initial_reviewer_disagreement_count": 0,
        "consensus_matches_reviewer_a_count": 0,
        "consensus_matches_reviewer_b_count": 0,
        "consensus_matches_neither_reviewer_count": 0}
    for first, second, consensus in zip(reviewer_labels[0], reviewer_labels[1],
            consensus_label_hashes):
        if first == second and consensus != first:
            raise ValueError("retrieval_consensus_changed_agreed_labels")
        if first != second:
            consensus_resolution["initial_reviewer_disagreement_count"] += 1
        matches_first = consensus == first
        matches_second = consensus == second
        if matches_first:
            consensus_resolution["consensus_matches_reviewer_a_count"] += 1
        if matches_second:
            consensus_resolution["consensus_matches_reviewer_b_count"] += 1
        if not matches_first and not matches_second:
            consensus_resolution["consensus_matches_neither_reviewer_count"] += 1
    sealed_annotations = []
    for index, row in enumerate(annotations):
        sealed_row = dict(row)
        if concealed_strata_units:
            sealed_row["stratum"] = question_strata[index]
            if not sealed_source_record_bindings:
                sealed_row["source_experience_digest"] = (
                    sealed_source_experience_digests[index])
        sealed_annotations.append(sealed_row)
    semantic = {"schema_version": (
            BLINDED_STRATA_ANNOTATION_SCHEMA if concealed_strata_units else
            RECORD_BOUND_ANNOTATION_SCHEMA if record_bound_units else
            ANNOTATION_SCHEMA if preregistered_units else
            LEGACY_ANNOTATION_SCHEMA),
        "cohort_id": packet["cohort_id"],
        "cohort_digest": packet["cohort_digest"],
        "history_state_digest": packet["history_state_digest"],
        "corpus_manifest_digest": packet["corpus_manifest_digest"],
        "adjudication_packet_digest": packet["packet_digest"],
        "blinded_adjudication": True,
        "independent_reviewer_digests": sorted(
            reviewer["reviewer_digest"] for reviewer in independent_reviewers),
        "independent_reviewer_annotations": [
            {"reviewer_digest": reviewer["reviewer_digest"],
                "annotations": [dict(row) for row in reviewer["annotations"]]}
            for reviewer in sorted(independent_reviewers,
                key=lambda item: item["reviewer_digest"])],
        "independent_review_agreement": {
            "query_count": len(questions), "exact_label_agreement_count":
                agreement_count, "exact_label_agreement_rate":
                agreement_count / len(questions) if questions else 0.0,
            "by_stratum": agreement_by_stratum,
            "consensus_after_blind_review": True},
        "consensus_resolution": consensus_resolution,
        "adjudication_procedure_digest": adjudication_procedure_digest,
        "annotations": sealed_annotations}
    result = {**semantic, "annotation_digest": digest_payload(semantic)}
    try:
        encoded_size = len(json.dumps(result, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False).encode("utf-8"))
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("retrieval_annotation_artifact_invalid") from exc
    if encoded_size > MAX_ANNOTATION_ARTIFACT_BYTES:
        raise ValueError("retrieval_annotation_artifact_over_bound")
    return result


def _validate_corpus_manifest(value: object, *, history_state_digest: str
        ) -> tuple[str, dict[str, str]]:
    if not isinstance(value, Mapping):
        raise ValueError("retrieval_corpus_manifest_invalid")
    semantic = {key: item for key, item in value.items()
        if key != "corpus_manifest_digest"}
    rows = value.get("records")
    if (set(value) != {"schema_version", "history_state_digest", "records",
            "corpus_manifest_digest"}
            or value.get("schema_version") not in {
                LEGACY_CORPUS_MANIFEST_SCHEMA, CORPUS_MANIFEST_SCHEMA}
            or not isinstance(value.get("history_state_digest"), str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}",
                value["history_state_digest"]) is None
            or value.get("history_state_digest") != history_state_digest
            or not isinstance(rows, list) or not rows
            or len(rows) > 100_000
            or value.get("corpus_manifest_digest") != digest_payload(semantic)):
        raise ValueError("retrieval_corpus_manifest_binding_invalid")
    records: dict[str, str] = {}
    previous_id: str | None = None
    for row in rows:
        if (not isinstance(row, Mapping)
                or set(row) != {"record_id", "record_digest"}
                or not isinstance(row.get("record_id"), str)
                or not 1 <= len(row["record_id"]) <= 256
                or not isinstance(row.get("record_digest"), str)
                or re.fullmatch(r"sha256:[0-9a-f]{64}",
                    row["record_digest"]) is None
                or (previous_id is not None and row["record_id"] <= previous_id)):
            raise ValueError("retrieval_corpus_manifest_records_invalid")
        records[row["record_id"]] = row["record_digest"]
        previous_id = row["record_id"]
    return str(value["corpus_manifest_digest"]), records


def score_retrieval_comparison_cohort(store: Any, *, cohort_id: str,
        annotations: Mapping[str, Any]) -> dict[str, Any]:
    """Score a cohort against blinded external record-relevance annotations.

    Annotation truth remains an externally supplied judgment. The returned
    artifact reports selection quality only; it does not measure model use or
    learning.
    """
    cohort = store.load_retrieval_comparison_cohort(cohort_id)
    protocol = cohort["evaluation_protocol"]
    query_set = store.load_retrieval_query_set(cohort["query_set_id"])
    source_experience_record_ids = query_set.get(
        "source_experience_record_ids")
    source_record_bindings_preregistered = isinstance(
        source_experience_record_ids, list)
    preregistered_source_digests = cohort.get("source_experience_digests")
    source_units_preregistered = isinstance(preregistered_source_digests, list)
    legacy_annotation_schema = (
        RECORD_BOUND_ANNOTATION_SCHEMA if source_record_bindings_preregistered
        else ANNOTATION_SCHEMA if source_units_preregistered
        else LEGACY_ANNOTATION_SCHEMA)
    adjudication_packet = store.build_retrieval_adjudication_packet(cohort_id)
    concealed_strata = adjudication_packet.get("schema_version") == (
        "sentientos.developmental_history_retrieval_adjudication_packet:v8")
    expected_annotation_schema = (BLINDED_STRATA_ANNOTATION_SCHEMA
        if concealed_strata else legacy_annotation_schema)
    corpus_manifest = cohort.get("corpus_manifest")
    manifest_digest, manifest_records = _validate_corpus_manifest(
        corpus_manifest, history_state_digest=cohort["history_state_digest"])
    if not isinstance(annotations, Mapping):
        raise ValueError("retrieval_annotations_invalid")
    annotation_semantic = {key: value for key, value in annotations.items()
        if key != "annotation_digest"}
    expected_fields = {"schema_version", "cohort_id", "cohort_digest",
        "history_state_digest", "corpus_manifest_digest",
        "adjudication_packet_digest", "blinded_adjudication",
        "independent_reviewer_digests", "independent_review_agreement",
        "independent_reviewer_annotations",
        "consensus_resolution",
        "adjudication_procedure_digest", "annotations", "annotation_digest"}
    rows = annotations.get("annotations")
    if (set(annotations) != expected_fields
            or annotations.get("schema_version") != expected_annotation_schema
            or annotations.get("cohort_id") != cohort_id
            or annotations.get("cohort_digest") != cohort.get("cohort_digest")
            or annotations.get("history_state_digest") !=
                cohort.get("history_state_digest")
            or annotations.get("corpus_manifest_digest") != manifest_digest
            or annotations.get("adjudication_packet_digest") !=
                adjudication_packet.get("packet_digest")
            or annotations.get("adjudication_procedure_digest") !=
                adjudication_packet.get("adjudication_procedure", {}).get(
                    "procedure_digest")
            or annotations.get("blinded_adjudication") is not True
            or not isinstance(annotations.get("independent_reviewer_digests"), list)
            or len(annotations["independent_reviewer_digests"]) != 2
            or any(not isinstance(item, str)
                or re.fullmatch(r"[0-9a-f]{64}", item) is None
                for item in annotations.get("independent_reviewer_digests", []))
            or annotations["independent_reviewer_digests"] != sorted(set(
                annotations["independent_reviewer_digests"]))
            or not isinstance(annotations.get("independent_review_agreement"), Mapping)
            or set(annotations["independent_review_agreement"]) != {
                "query_count", "exact_label_agreement_count",
                "exact_label_agreement_rate", "by_stratum",
                "consensus_after_blind_review"}
            or not isinstance(rows, list)
            or annotations["independent_review_agreement"].get("query_count") !=
                len(rows)
            or not isinstance(annotations.get("independent_reviewer_annotations"), list)
            or len(annotations["independent_reviewer_annotations"]) != 2
            or annotations["independent_review_agreement"].get(
                "consensus_after_blind_review") is not True
            or not isinstance(annotations.get("adjudication_procedure_digest"), str)
            or re.fullmatch(r"[0-9a-f]{64}",
                annotations["adjudication_procedure_digest"]) is None
            or len(rows) != cohort.get("question_count")
            or annotations.get("annotation_digest") != digest_payload(
                annotation_semantic)):
        raise ValueError("retrieval_annotations_binding_invalid")
    reviewers = annotations["independent_reviewer_annotations"]
    if ([reviewer.get("reviewer_digest") if isinstance(reviewer, Mapping)
            else None for reviewer in reviewers] !=
            annotations["independent_reviewer_digests"]
            or any(not isinstance(reviewer, Mapping)
                or set(reviewer) != {"reviewer_digest", "annotations"}
                or not isinstance(reviewer.get("annotations"), list)
                or len(reviewer["annotations"]) != len(rows)
                for reviewer in reviewers)):
        raise ValueError("retrieval_independent_reviewers_invalid")
    def reviewer_labels(rows_: Sequence[Mapping[str, Any]]) -> list[tuple[str, str]]:
        labels_: list[tuple[str, str]] = []
        for index, row in enumerate(rows_):
            if not isinstance(row, Mapping):
                raise ValueError("retrieval_independent_review_labels_invalid")
            corpus_labels = row.get("record_labels")
            reviewer_row_fields = {"question_digest",
                "reviewed_corpus_manifest_digest", "record_labels"}
            if not concealed_strata:
                reviewer_row_fields.add("stratum")
            if (set(row) != reviewer_row_fields
                    or row.get("question_digest") != cohort["question_digests"][index]
                    or (not concealed_strata and
                        row.get("stratum") != cohort["strata"][index])
                    or row.get("reviewed_corpus_manifest_digest") != manifest_digest
                    or not isinstance(corpus_labels, list)):
                raise ValueError("retrieval_independent_review_labels_invalid")
            partition = _complete_record_labels(corpus_labels,
                records=manifest_records)
            relevant_ids = partition["relevant"]
            inapplicable_ids = partition["inapplicable"]
            stratum = cohort["strata"][index]
            if (relevant_ids & inapplicable_ids
                    or (not concealed_strata and (
                    (stratum == "no_applicable_history" and relevant_ids)
                    or (stratum != "no_applicable_history" and not relevant_ids)
                    or (stratum == "lexical_distractor" and not inapplicable_ids)))):
                raise ValueError("retrieval_independent_review_labels_invalid")
            labels_.append((digest_payload(sorted(relevant_ids)),
                digest_payload(sorted(inapplicable_ids))))
        return labels_
    first_labels, second_labels = [reviewer_labels(item["annotations"])
        for item in reviewers]
    agreement_count = sum(first == second for first, second in
        zip(first_labels, second_labels))
    agreement = annotations["independent_review_agreement"]
    expected_agreement_rate = agreement_count / len(rows) if rows else 0.0
    expected_agreement_by_stratum: dict[str, Any] = {}
    for stratum in STRATA:
        indexes = [index for index, value in enumerate(cohort["strata"])
            if value == stratum]
        count = sum(first_labels[index] == second_labels[index]
            for index in indexes)
        expected_agreement_by_stratum[stratum] = {"query_count": len(indexes),
            "exact_label_agreement_count": count,
            "exact_label_agreement_rate": count / len(indexes) if indexes else 0.0}
    if (agreement["exact_label_agreement_count"] != agreement_count
            or agreement["exact_label_agreement_rate"] !=
                expected_agreement_rate
            or agreement["by_stratum"] != expected_agreement_by_stratum):
        raise ValueError("retrieval_independent_review_agreement_mismatch")
    expected_consensus_resolution = {"query_count": len(rows),
        "initial_reviewer_disagreement_count": 0,
        "consensus_matches_reviewer_a_count": 0,
        "consensus_matches_reviewer_b_count": 0,
        "consensus_matches_neither_reviewer_count": 0}
    reports = [store.load_retrieval_comparison(artifact_id)["comparison"]
        for artifact_id in cohort["comparison_artifact_ids"]]
    expected_questions = cohort["question_digests"]
    if ([row.get("question_digest") if isinstance(row, Mapping) else None
            for row in rows] != expected_questions
            or [row.get("stratum") if isinstance(row, Mapping) else None
                for row in rows] != cohort.get("strata")):
        raise ValueError("retrieval_annotations_question_order_invalid")
    expected_row_fields = {"question_digest", "stratum",
        "reviewed_corpus_manifest_digest", "record_labels"}
    if not source_record_bindings_preregistered:
        expected_row_fields.add("source_experience_digest")
    source_experiences: set[str] = set()
    counts = {stratum: 0 for stratum in STRATA}
    scored_rows: dict[str, list[dict[str, Any]]] = {
        stratum: [] for stratum in STRATA}
    per_query_results: list[dict[str, Any]] = []
    for query_index, (report, annotation) in enumerate(zip(reports, rows)):
        annotation_source_digest = (
            preregistered_source_digests[query_index]
            if source_record_bindings_preregistered else
            annotation.get("source_experience_digest")
            if isinstance(annotation, Mapping) else None)
        if (not isinstance(annotation, Mapping)
                or set(annotation) != expected_row_fields
                or annotation.get("question_digest") != report["question_digest"]
                or annotation.get("stratum") not in STRATA
                or annotation.get("reviewed_corpus_manifest_digest") !=
                    manifest_digest
                or not isinstance(annotation_source_digest, str)
                or re.fullmatch(r"[0-9a-f]{64}",
                    annotation_source_digest) is None
                or (source_units_preregistered
                    and not source_record_bindings_preregistered
                    and annotation["source_experience_digest"] !=
                        preregistered_source_digests[query_index])
                or annotation_source_digest in source_experiences
                or not isinstance(annotation.get("record_labels"), list)):
            raise ValueError("retrieval_annotation_row_invalid")
        source_experiences.add(annotation_source_digest)
        stratum = annotation["stratum"]
        partition = _complete_record_labels(annotation["record_labels"],
            records=manifest_records)
        relevant_ids = partition["relevant"]
        inapplicable_ids = partition["inapplicable"]
        stratum_label_expectations_met = (
            not relevant_ids if stratum == "no_applicable_history" else
            bool(relevant_ids and inapplicable_ids)
            if stratum == "lexical_distractor" else bool(relevant_ids))
        consensus_label_hash = (digest_payload(sorted(relevant_ids)),
            digest_payload(sorted(inapplicable_ids)))
        first_label_hash = first_labels[query_index]
        second_label_hash = second_labels[query_index]
        if first_label_hash == second_label_hash:
            if consensus_label_hash != first_label_hash:
                raise ValueError("retrieval_consensus_changed_agreed_labels")
        else:
            expected_consensus_resolution[
                "initial_reviewer_disagreement_count"] += 1
        matches_first = consensus_label_hash == first_label_hash
        matches_second = consensus_label_hash == second_label_hash
        if matches_first:
            expected_consensus_resolution[
                "consensus_matches_reviewer_a_count"] += 1
        if matches_second:
            expected_consensus_resolution[
                "consensus_matches_reviewer_b_count"] += 1
        if not matches_first and not matches_second:
            expected_consensus_resolution[
                "consensus_matches_neither_reviewer_count"] += 1
        if (not concealed_strata and (
                (stratum == "no_applicable_history" and relevant_ids)
                or (stratum != "no_applicable_history" and not relevant_ids)
                or (stratum == "lexical_distractor" and not inapplicable_ids))):
            raise ValueError("retrieval_annotation_labels_invalid")
        source_experience_record_id = (
            source_experience_record_ids[query_index]
            if source_record_bindings_preregistered else None)
        source_experience_record_reference_verified = bool(
            source_record_bindings_preregistered
            and isinstance(source_experience_record_id, str)
            and source_experience_record_id in manifest_records)
        source_experience_record_binding_verified = bool(
            source_experience_record_reference_verified
            and (stratum == "no_applicable_history"
                or source_experience_record_id in relevant_ids))
        if (source_record_bindings_preregistered and not concealed_strata
                and not source_experience_record_binding_verified):
            raise ValueError("retrieval_annotation_source_experience_record_irrelevant")
        source_experience_record_relevance_status = (
            "not_applicable" if stratum == "no_applicable_history" else
            "verified_relevant" if source_experience_record_binding_verified
            else "not_verified")
        known_digests: dict[str, str] = {}
        for condition in report["conditions"]:
            for ref in condition["available_records"]:
                if manifest_records.get(ref["record_id"]) != ref["record_digest"]:
                    raise ValueError(
                        "retrieval_candidate_missing_from_corpus_manifest")
                known_digests[ref["record_id"]] = ref["record_digest"]
        label_digest_by_id = {item["record_id"]: item["record_digest"]
            for item in annotation["record_labels"]}
        for record_id, record_digest in label_digest_by_id.items():
            known = known_digests.get(record_id)
            if known is not None and known != record_digest:
                raise ValueError("retrieval_annotation_record_digest_mismatch")
        selections = {
            condition["condition"]: {ref["record_id"]: ref["record_digest"]
                for ref in condition["selected_records"]}
            for condition in report["conditions"]}
        for condition in report["conditions"]:
            for record_id, record_digest in selections[condition["condition"]].items():
                if (record_id in label_digest_by_id
                        and label_digest_by_id[record_id] != record_digest):
                    raise ValueError("retrieval_annotation_selected_digest_mismatch")
        result: dict[str, Any] = {"question_digest": report["question_digest"],
            "stratum": stratum,
            "source_experience_record_reference_verified": (
                source_experience_record_reference_verified),
            "source_experience_record_binding_verified": (
                source_experience_record_binding_verified),
            "source_experience_record_relevance_status": (
                source_experience_record_relevance_status),
            "full_corpus_label_partition_verified": True,
            "source_experience_digest": annotation_source_digest,
            "corpus_record_count": len(annotation["record_labels"]),
            "relevant_record_count": len(relevant_ids),
            "inapplicable_record_count": len(inapplicable_ids),
            "preregistered_stratum_label_expectations_met": (
                stratum_label_expectations_met),
            "neither_record_count": len(partition["neither"]),
            "selected_record_ids_lexical": list(selections["lexical"]),
            "selected_record_ids_semantic": list(selections["semantic"]),
            "same_selected_records": (
                list(selections["lexical"]) == list(selections["semantic"])),
            "semantic_fallback_to_lexical": report[
                "semantic_fallback_to_lexical"]}
        selected_orders = {item["condition"]: [ref["record_id"] for ref in
            item["selected_records"]] for item in report["conditions"]}
        same_selected_order = (selected_orders["lexical"] ==
            selected_orders["semantic"])
        common_k = min(len(selected_orders["lexical"]),
            len(selected_orders["semantic"]))
        if protocol.get("schema_version") in COMMON_K_PROTOCOL_SCHEMAS:
            result["same_selected_records"] = (
                set(selected_orders["lexical"]) ==
                set(selected_orders["semantic"]))
            result["same_selected_order"] = same_selected_order
            result["common_selected_record_count"] = common_k
            result["selected_record_count_lexical"] = len(
                selected_orders["lexical"])
            result["selected_record_count_semantic"] = len(
                selected_orders["semantic"])
            result["selected_record_count_delta_semantic_minus_lexical"] = (
                len(selected_orders["semantic"]) -
                len(selected_orders["lexical"]))
        if relevant_ids:
            ranks: dict[str, int | None] = {}
            recalls: dict[str, float] = {}
            common_k_recalls: dict[str, float | None] = {}
            common_k_ranks: dict[str, int | None] = {}
            for condition_name in ("lexical", "semantic"):
                condition = next(item for item in report["conditions"]
                    if item["condition"] == condition_name)
                ordered_ids = [ref["record_id"]
                    for ref in condition["selected_records"]]
                hits = [index + 1 for index, record_id in enumerate(ordered_ids)
                    if record_id in relevant_ids]
                ranks[condition_name] = min(hits) if hits else None
                recalls[condition_name] = len(set(ordered_ids) & relevant_ids) / len(
                    relevant_ids)
                common_k_recalls[condition_name] = (
                    len(set(ordered_ids[:common_k]) & relevant_ids) /
                        len(relevant_ids))
                common_hits = [index + 1 for index, record_id in
                    enumerate(ordered_ids[:common_k])
                    if record_id in relevant_ids]
                common_k_ranks[condition_name] = (
                    min(common_hits) if common_hits else None)
            result.update({"recall_lexical": recalls["lexical"],
                "recall_semantic": recalls["semantic"],
                "reciprocal_rank_lexical": (1 / ranks["lexical"]
                    if ranks["lexical"] else 0.0),
                "reciprocal_rank_semantic": (1 / ranks["semantic"]
                    if ranks["semantic"] else 0.0)})
            if protocol.get("schema_version") in COMMON_K_PROTOCOL_SCHEMAS:
                result.update({
                    "common_k_recall_lexical": common_k_recalls["lexical"],
                    "common_k_recall_semantic": common_k_recalls["semantic"],
                    "common_k_reciprocal_rank_lexical": (
                        1 / common_k_ranks["lexical"]
                        if common_k_ranks["lexical"] else 0.0),
                    "common_k_reciprocal_rank_semantic": (
                        1 / common_k_ranks["semantic"]
                        if common_k_ranks["semantic"] else 0.0)})
        else:
            result.update({"recall_lexical": None, "recall_semantic": None,
                "reciprocal_rank_lexical": None,
                "reciprocal_rank_semantic": None})
            if protocol.get("schema_version") in COMMON_K_PROTOCOL_SCHEMAS:
                result.update({"common_k_recall_lexical": None,
                    "common_k_recall_semantic": None,
                    "common_k_reciprocal_rank_lexical": None,
                    "common_k_reciprocal_rank_semantic": None})
        if protocol.get("schema_version") in (
                NONRELEVANT_SELECTION_PROTOCOL_SCHEMAS):
            for condition in ("lexical", "semantic"):
                result[f"nonrelevant_selected_{condition}"] = bool(
                    set(selections[condition]) - relevant_ids)
        if stratum == "no_applicable_history":
            result["inapplicable_selected_lexical"] = bool(selections["lexical"])
            result["inapplicable_selected_semantic"] = bool(selections["semantic"])
        elif inapplicable_ids:
            result["inapplicable_selected_lexical"] = bool(
                set(selections["lexical"]) & inapplicable_ids)
            result["inapplicable_selected_semantic"] = bool(
                set(selections["semantic"]) & inapplicable_ids)
        else:
            result["inapplicable_selected_lexical"] = None
            result["inapplicable_selected_semantic"] = None
        scored_rows[stratum].append(result)
        per_query_results.append(result)
        counts[stratum] += 1
    if annotations.get("consensus_resolution") != expected_consensus_resolution:
        raise ValueError("retrieval_consensus_resolution_mismatch")
    if (counts[STRATA[0]] < protocol["minimum_queries_per_stratum"]
            or len(set(counts.values())) != 1):
        raise ValueError("retrieval_annotation_strata_unbalanced")
    if protocol.get("bootstrap_seed") == (
            "preregistered_query_set_digest_first_16_hex:v1"):
        query_set_digest = cohort.get("query_set_digest")
        if (not isinstance(query_set_digest, str)
                or re.fullmatch(r"sha256:[0-9a-f]{64}",
                    query_set_digest) is None):
            raise ValueError("retrieval_preregistered_bootstrap_seed_invalid")
        seed = int(query_set_digest[7:23], 16)
    else:
        # Preserve historical evaluation bytes for already sealed protocols.
        seed = int(digest_payload({"cohort_digest": cohort["cohort_digest"],
            "annotation_digest": annotations["annotation_digest"]})[:16], 16)
    if protocol.get("schema_version") in COMMON_K_PROTOCOL_SCHEMAS:
        metric_seed_offsets = protocol["bootstrap_metric_offsets"]
        stratum_seed_offsets = protocol["bootstrap_stratum_offsets"]
    else:
        metric_seed_offsets = {"recall": 0, "reciprocal_rank": 1,
            "inapplicable_selection_rate": 2}
        stratum_seed_offsets = {stratum: index * 10
            for index, stratum in enumerate(STRATA)}
        stratum_seed_offsets["overall"] = 100
    def summarize(items: list[dict[str, Any]], *, seed_offset: int) -> dict[str, Any]:
        summary: dict[str, Any] = {"query_count": len(items)}
        for metric in ("recall", "reciprocal_rank"):
            first = [float(item[f"{metric}_lexical"]) for item in items
                if item[f"{metric}_lexical"] is not None]
            second = [float(item[f"{metric}_semantic"]) for item in items
                if item[f"{metric}_semantic"] is not None]
            if first and len(first) == len(second):
                differences = [b - a for a, b in zip(first, second)]
                summary[metric] = {"lexical_mean": _mean(first),
                    "semantic_mean": _mean(second),
                    "semantic_minus_lexical_mean": _mean(differences),
                    "paired_95_percent_ci": _paired_ci(differences,
                        seed=seed + seed_offset + metric_seed_offsets[metric],
                        bootstrap_samples=protocol["bootstrap_samples"],
                        confidence_level=protocol["confidence_level"])}
            else:
                summary[metric] = None
        if protocol.get("schema_version") in COMMON_K_PROTOCOL_SCHEMAS:
            lexical_counts = [item["selected_record_count_lexical"]
                for item in items]
            semantic_counts = [item["selected_record_count_semantic"]
                for item in items]
            lexical_common = [float(item["common_k_recall_lexical"])
                for item in items
                if item.get("common_k_recall_lexical") is not None]
            semantic_common = [float(item["common_k_recall_semantic"])
                for item in items
                if item.get("common_k_recall_semantic") is not None]
            lexical_common_rank = [float(
                item["common_k_reciprocal_rank_lexical"]) for item in items
                if item.get("common_k_reciprocal_rank_lexical") is not None]
            semantic_common_rank = [float(
                item["common_k_reciprocal_rank_semantic"]) for item in items
                if item.get("common_k_reciprocal_rank_semantic") is not None]
            summary["zero_common_k_query_count"] = sum(
                item.get("common_selected_record_count") == 0
                for item in items)
            if lexical_common and len(lexical_common) == len(semantic_common):
                common_differences = [semantic - lexical for lexical, semantic
                    in zip(lexical_common, semantic_common)]
                summary["common_k_recall"] = {
                    "query_count": len(common_differences),
                    "lexical_mean": _mean(lexical_common),
                    "semantic_mean": _mean(semantic_common),
                    "semantic_minus_lexical_mean": _mean(common_differences),
                    "paired_95_percent_ci": _paired_ci(common_differences,
                        seed=seed + seed_offset + metric_seed_offsets[
                            "common_k_recall"],
                        bootstrap_samples=protocol["bootstrap_samples"],
                        confidence_level=protocol["confidence_level"])}
            else:
                summary["common_k_recall"] = None
            if (lexical_common_rank
                    and len(lexical_common_rank) == len(semantic_common_rank)):
                common_rank_differences = [semantic - lexical
                    for lexical, semantic in zip(lexical_common_rank,
                        semantic_common_rank)]
                summary["common_k_reciprocal_rank"] = {
                    "query_count": len(common_rank_differences),
                    "lexical_mean": _mean(lexical_common_rank),
                    "semantic_mean": _mean(semantic_common_rank),
                    "semantic_minus_lexical_mean": _mean(
                        common_rank_differences),
                    "paired_95_percent_ci": _paired_ci(
                        common_rank_differences,
                        seed=seed + seed_offset + metric_seed_offsets[
                            "common_k_reciprocal_rank"],
                        bootstrap_samples=protocol["bootstrap_samples"],
                        confidence_level=protocol["confidence_level"])}
            else:
                summary["common_k_reciprocal_rank"] = None
            summary["selected_record_count"] = {
                "lexical_mean": _mean([float(value)
                    for value in lexical_counts]),
                "semantic_mean": _mean([float(value)
                    for value in semantic_counts]),
                "semantic_minus_lexical_mean": _mean([
                    float(item["selected_record_count_delta_semantic_minus_lexical"])
                    for item in items]),
                "paired_95_percent_ci": _paired_ci([
                    float(item[
                        "selected_record_count_delta_semantic_minus_lexical"])
                    for item in items], seed=seed + seed_offset +
                        metric_seed_offsets["selected_record_count"],
                    bootstrap_samples=protocol["bootstrap_samples"],
                    confidence_level=protocol["confidence_level"])}
        false_pairs = [(float(item["inapplicable_selected_lexical"]),
            float(item["inapplicable_selected_semantic"])) for item in items
            if item["inapplicable_selected_lexical"] is not None
                and item["inapplicable_selected_semantic"] is not None]
        if false_pairs:
            false_lexical = [pair[0] for pair in false_pairs]
            false_semantic = [pair[1] for pair in false_pairs]
            false_differences = [b - a for a, b in false_pairs]
            summary["inapplicable_selection_rate"] = {
                "query_count": len(false_pairs),
                "lexical_mean": _mean(false_lexical),
                "semantic_mean": _mean(false_semantic),
                "semantic_minus_lexical_mean": _mean(false_differences),
                "paired_95_percent_ci": (
                    _paired_binary_difference_ci(false_lexical, false_semantic,
                        confidence_level=protocol["confidence_level"])
                    if protocol.get("schema_version") in
                        FINITE_SAMPLE_FALSE_INCLUSION_PROTOCOL_SCHEMAS
                    else _paired_ci(false_differences,
                    seed=seed + seed_offset + metric_seed_offsets[
                        "inapplicable_selection_rate"],
                    bootstrap_samples=protocol["bootstrap_samples"],
                    confidence_level=protocol["confidence_level"]))}
            if protocol.get("schema_version") in (
                    FINITE_SAMPLE_FALSE_INCLUSION_PROTOCOL_SCHEMAS):
                zero_discordance_upper = (
                    _zero_discordance_binary_difference_upper_bound(
                        query_count=len(false_pairs),
                        confidence_level=protocol["confidence_level"]))
                summary["inapplicable_selection_rate"].update({
                    "zero_discordance_reference_95_percent_ci_upper":
                        zero_discordance_upper,
                    "zero_discordance_reference_meets_noninferiority_limit":
                        zero_discordance_upper <= protocol[
                            "false_inclusion_ci_upper_inclusive"]})
        else:
            summary["inapplicable_selection_rate"] = None
        if protocol.get("schema_version") in (
                NONRELEVANT_SELECTION_PROTOCOL_SCHEMAS):
            nonrelevant_pairs = [(float(item["nonrelevant_selected_lexical"]),
                float(item["nonrelevant_selected_semantic"])) for item in items]
            differences = [semantic - lexical
                for lexical, semantic in nonrelevant_pairs]
            summary["nonrelevant_selection_rate"] = {
                "query_count": len(nonrelevant_pairs),
                "lexical_mean": _mean([pair[0] for pair in nonrelevant_pairs]),
                "semantic_mean": _mean([pair[1] for pair in nonrelevant_pairs]),
                "semantic_minus_lexical_mean": _mean(differences),
                "paired_95_percent_ci": (
                    _paired_binary_difference_ci(
                        [pair[0] for pair in nonrelevant_pairs],
                        [pair[1] for pair in nonrelevant_pairs],
                        confidence_level=protocol["confidence_level"])
                    if protocol.get("schema_version") in
                        FINITE_SAMPLE_FALSE_INCLUSION_PROTOCOL_SCHEMAS
                    else _paired_ci(differences,
                    seed=seed + seed_offset + metric_seed_offsets[
                        "nonrelevant_selection_rate"],
                    bootstrap_samples=protocol["bootstrap_samples"],
                    confidence_level=protocol["confidence_level"]))}
            if protocol.get("schema_version") in (
                    FINITE_SAMPLE_FALSE_INCLUSION_PROTOCOL_SCHEMAS):
                zero_discordance_upper = (
                    _zero_discordance_binary_difference_upper_bound(
                        query_count=len(nonrelevant_pairs),
                        confidence_level=protocol["confidence_level"]))
                summary["nonrelevant_selection_rate"].update({
                    "zero_discordance_reference_95_percent_ci_upper":
                        zero_discordance_upper,
                    "zero_discordance_reference_meets_noninferiority_limit":
                        zero_discordance_upper <= protocol[
                            "maximum_nonrelevant_selection_rate_increase"]})
        summary["same_selected_records_count"] = sum(
            item["same_selected_records"] for item in items)
        summary["same_selected_records_rate"] = (
            summary["same_selected_records_count"] / len(items) if items else None)
        if protocol.get("schema_version") in COMMON_K_PROTOCOL_SCHEMAS:
            summary["same_selected_order_count"] = sum(
                item["same_selected_order"] for item in items)
            summary["same_selected_order_rate"] = (
                summary["same_selected_order_count"] / len(items)
                if items else None)
        summary["semantic_fallback_count"] = sum(
            item["semantic_fallback_to_lexical"] for item in items)
        summary["semantic_fallback_rate"] = (
            summary["semantic_fallback_count"] / len(items) if items else None)
        return summary

    summaries: dict[str, Any] = {
        stratum: summarize(scored_rows[stratum],
            seed_offset=stratum_seed_offsets[stratum])
        for stratum_index, stratum in enumerate(STRATA)}
    summaries["overall"] = summarize(per_query_results,
        seed_offset=stratum_seed_offsets["overall"])
    stratum_label_mismatch_counts = {
        stratum: sum(item["preregistered_stratum_label_expectations_met"]
            is not True for item in scored_rows[stratum])
        for stratum in STRATA}
    stratum_validation_passed = not any(
        stratum_label_mismatch_counts.values())
    source_record_binding_mismatch_count = (sum(
        item["source_experience_record_binding_verified"] is not True
        for item in per_query_results
        if item["stratum"] != "no_applicable_history")
        if source_record_bindings_preregistered else 0)
    source_record_binding_validation_passed = (
        source_record_binding_mismatch_count == 0
        if source_record_bindings_preregistered else None)
    stratum_validation = {
        "schema_version":
            "sentientos.retrieval_query_stratum_label_validation:v1",
        "query_count": len(per_query_results),
        "consistent_query_count": sum(
            item["preregistered_stratum_label_expectations_met"] is True
            for item in per_query_results),
        "inconsistent_query_count": sum(
            stratum_label_mismatch_counts.values()),
        "inconsistent_query_count_by_stratum":
            stratum_label_mismatch_counts,
        "source_record_binding_validation_applicable":
            source_record_bindings_preregistered,
        "source_record_binding_mismatch_count":
            source_record_binding_mismatch_count,
        "source_record_binding_validation_passed":
            source_record_binding_validation_passed,
        "gate_qualification_requires_zero_preregistration_mismatches": True,
        "preregistered_query_design_consistent": (stratum_validation_passed
            and source_record_binding_validation_passed is not False),
        "labels_rewritten_or_rejected": False,
    }
    primary_recall_metric = ("common_k_recall"
        if protocol.get("schema_version") in COMMON_K_PROTOCOL_SCHEMAS
        else "recall")
    paraphrase = summaries["paraphrased_experience"][primary_recall_metric]
    full_selection_recall = summaries["paraphrased_experience"]["recall"]
    lexical_distractor_summary = summaries["lexical_distractor"][
        "inapplicable_selection_rate"]
    lexical_distractor = lexical_distractor_summary["paired_95_percent_ci"]
    no_applicable_summary = summaries["no_applicable_history"][
        "inapplicable_selection_rate"]
    no_applicable = no_applicable_summary["paired_95_percent_ci"]
    reviewer_agreement = annotations["independent_review_agreement"][
        "exact_label_agreement_rate"]
    per_stratum_agreement = annotations["independent_review_agreement"][
        "by_stratum"]
    agreement_floor = protocol["minimum_independent_reviewer_exact_agreement"]
    agreement_passed = all(per_stratum_agreement[stratum][
        "exact_label_agreement_rate"] >= agreement_floor for stratum in STRATA)
    semantic_fallback_count = sum(
        item["semantic_fallback_to_lexical"] for item in per_query_results)
    gate_passed = bool(stratum_validation_passed
        and source_record_binding_validation_passed is not False
        and agreement_passed
        and (protocol.get("schema_version") not in
            FALLBACK_GATED_PROTOCOL_SCHEMAS
            or semantic_fallback_count <= protocol[
                "maximum_semantic_fallback_queries"])
        and paraphrase is not None
        and paraphrase["semantic_minus_lexical_mean"] >=
            protocol["paraphrase_recall_minimum_gain"]
        and paraphrase["paired_95_percent_ci"][0] >
            protocol["paraphrase_recall_ci_lower_exclusive"]
        and (protocol.get("schema_version") not in COMMON_K_PROTOCOL_SCHEMAS
            or (full_selection_recall is not None
                and full_selection_recall["semantic_minus_lexical_mean"] >=
                    protocol["full_selection_recall_minimum_gain"]))
        and lexical_distractor[1] <=
            protocol["false_inclusion_ci_upper_inclusive"]
        and no_applicable[1] <=
            protocol["false_inclusion_ci_upper_inclusive"]
        and (protocol.get("schema_version") not in
            NONRELEVANT_SELECTION_PROTOCOL_SCHEMAS
            or all(summaries[stratum]["nonrelevant_selection_rate"][
                "paired_95_percent_ci"][1] <=
                    protocol["maximum_nonrelevant_selection_rate_increase"]
                and summaries[stratum]["nonrelevant_selection_rate"][
                    "semantic_minus_lexical_mean"] <=
                    protocol["maximum_nonrelevant_selection_rate_increase"]
                for stratum in ("lexical_distractor", "no_applicable_history")))
        and (protocol.get("schema_version") not in {
            "sentientos.semantic_history_retrieval_gate:v6",
            "sentientos.semantic_history_retrieval_gate:v7"}
            or (lexical_distractor_summary[
                    "semantic_minus_lexical_mean"] <=
                protocol["maximum_false_inclusion_rate_increase"]
                and no_applicable_summary[
                    "semantic_minus_lexical_mean"] <=
                protocol["maximum_false_inclusion_rate_increase"])))
    result = {"schema_version": EVALUATION_SCHEMA,
        "cohort_id": cohort_id, "cohort_digest": cohort["cohort_digest"],
        "history_state_digest": cohort["history_state_digest"],
        "corpus_manifest_digest": annotations["corpus_manifest_digest"],
        "adjudication_packet_digest": annotations[
            "adjudication_packet_digest"],
        "annotation_digest": annotations["annotation_digest"],
        "label_posture": (
            "external_dual_blinded_review_and_consensus_asserted"),
        "independent_review_agreement": annotations[
            "independent_review_agreement"],
        "consensus_resolution": annotations["consensus_resolution"],
        "evaluation_protocol": protocol,
        "sampling_assumptions": {
            "bootstrap_resampling_unit": "query_row",
            "asserted_source_experience_digest_count": len(source_experiences),
            "source_experience_digests_preregistered": source_units_preregistered,
            "source_experience_record_bindings_preregistered": (
                source_record_bindings_preregistered),
            "source_experience_record_bindings_verified": (
                source_record_bindings_preregistered
                and all(item["source_experience_record_binding_verified"]
                    for item in per_query_results)),
            "source_experience_record_references_verified": (
                source_record_bindings_preregistered
                and all(item["source_experience_record_reference_verified"]
                    for item in per_query_results)),
            "source_experience_record_relevance_checks_verified": (
                source_record_bindings_preregistered
                and all(item["source_experience_record_relevance_status"]
                    in {"verified_relevant", "not_applicable"}
                    for item in per_query_results)),
            "preregistered_source_experience_binding_verified": (
                source_units_preregistered),
            "source_experience_independence_verified": False,
            "inferential_gate_qualification": (
                "conditional_on_unverified_source_experience_independence"),
            "confidence_intervals_conditional_on_external_unit_assertions": True,
            "population_uncertainty": (
                "finite_sample_query_outcome_intervals_conditional_on_"
                "unverified_source_experience_independence"
                if protocol.get("schema_version") in
                    FINITE_SAMPLE_FALSE_INCLUSION_PROTOCOL_SCHEMAS
                else "not_estimated")},
        "bootstrap_samples": protocol["bootstrap_samples"],
        "per_query_outcomes": per_query_results,
        "query_stratum_label_validation": stratum_validation,
        "strata": summaries,
        "gate": {"status": (
                "retrieval_gate_passed_conditional_on_unverified_source_independence"
                if gate_passed else
                "retrieval_gate_not_passed_or_inconclusive"),
            "qualification_posture": (
                "conditional_on_unverified_source_experience_independence"
                if gate_passed else "not_met"),
            **({"paraphrase_recall_metric": primary_recall_metric}
                if protocol.get("schema_version") in COMMON_K_PROTOCOL_SCHEMAS
                else {}),
            **({"full_selection_recall_minimum_gain": protocol[
                    "full_selection_recall_minimum_gain"],
                "full_selection_recall_nonregression_passed": (
                    full_selection_recall is not None
                    and full_selection_recall[
                        "semantic_minus_lexical_mean"] >= protocol[
                            "full_selection_recall_minimum_gain"])}
                if protocol.get("schema_version") in COMMON_K_PROTOCOL_SCHEMAS
                else {}),
            "independent_reviewer_exact_agreement_rate": reviewer_agreement,
            "query_stratum_label_validation_passed":
                stratum_validation_passed,
            "preregistered_source_record_label_expectations_met":
                source_record_binding_validation_passed,
            "independent_reviewer_agreement_by_stratum":
                per_stratum_agreement,
            "minimum_independent_reviewer_exact_agreement": protocol[
                "minimum_independent_reviewer_exact_agreement"],
            "paraphrase_recall_minimum_gain":
                protocol["paraphrase_recall_minimum_gain"],
            "maximum_false_inclusion_rate_increase":
                protocol["maximum_false_inclusion_rate_increase"],
            "confidence_level": protocol["confidence_level"],
            "false_inclusion_interval_method": protocol.get(
                "false_inclusion_interval_method",
                "paired_query_percentile_bootstrap:v1"),
            "false_inclusion_interval_sampling_posture": (
                "paired_query_binary_outcomes_conditional_on_unverified"
                "_source_experience_independence"
                if protocol.get("schema_version") in
                    FINITE_SAMPLE_FALSE_INCLUSION_PROTOCOL_SCHEMAS
                else "paired_query_bootstrap_conditional_on_unverified"
                    "_source_experience_independence"),
            "source_experience_record_bindings_verified": (
                source_record_bindings_preregistered
                and all(item["source_experience_record_binding_verified"]
                    for item in per_query_results)),
            "source_experience_record_references_verified": (
                source_record_bindings_preregistered
                and all(item["source_experience_record_reference_verified"]
                    for item in per_query_results)),
            "source_experience_record_relevance_checks_verified": (
                source_record_bindings_preregistered
                and all(item["source_experience_record_relevance_status"]
                    in {"verified_relevant", "not_applicable"}
                    for item in per_query_results)),
            "paraphrase_recall_ci_lower_exclusive":
                protocol["paraphrase_recall_ci_lower_exclusive"],
            "false_inclusion_ci_upper_inclusive":
                protocol["false_inclusion_ci_upper_inclusive"],
            **({"maximum_nonrelevant_selection_rate_increase": protocol[
                    "maximum_nonrelevant_selection_rate_increase"],
                "nonrelevant_selection_rates": {
                    stratum: summaries[stratum]["nonrelevant_selection_rate"]
                    for stratum in ("lexical_distractor",
                        "no_applicable_history")}}
                if protocol.get("schema_version") in
                    NONRELEVANT_SELECTION_PROTOCOL_SCHEMAS else {}),
            "effect_established": False, "learning_established": False},
        "effect_established": False, "learning_established": False,
        "authority": False}
    return {**result, "evaluation_digest": digest_payload(result)}
