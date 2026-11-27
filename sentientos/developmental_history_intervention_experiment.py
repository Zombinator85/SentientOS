"""Preregistered, non-destructive developmental-history projection experiment."""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, cast

from .local_model_authority import digest_payload
from .semantic_history_retrieval_evaluation import (
    retrieval_adjudication_procedure)
from .canonical_memory import sentientos_memory_dir
from .resident_developmental_writeback import (
    CognitionObservation, DevelopmentalHistoryProjection, measure_changed_cognition,
    DevelopmentalWritebackError, _open_store_directory, _read_store_file, _publish_store_json,
)
from .windows_handle_custody import (
    WindowsHandleCustodyError, ensure_private_child_directory,
    observe_private_directory_identity,
    read_explicit_file, verify_explicit_directory,
)

LEGACY_SCHEMA = "sentientos.developmental_history_intervention_protocol:v1"
SCHEMA = "sentientos.developmental_history_intervention_protocol:v2"
LEGACY_OBJECTIVE_SCHEMA = "sentientos.developmental_history_intervention_protocol:v3"
OBJECTIVE_SCHEMA = "sentientos.developmental_history_intervention_protocol:v4"
HISTORY_SELECTION_SCHEMA = "sentientos.developmental_history_intervention_protocol:v5"
OBJECTIVE_HISTORY_SELECTION_SCHEMA = "sentientos.developmental_history_intervention_protocol:v6"
COUNTERBALANCED_HISTORY_SELECTION_SCHEMA = "sentientos.developmental_history_intervention_protocol:v7"
SCHEDULED_HISTORY_SELECTION_SCHEMA = "sentientos.developmental_history_intervention_protocol:v8"
OBJECTIVE_SCHEDULED_HISTORY_SELECTION_SCHEMA = "sentientos.developmental_history_intervention_protocol:v9"
BALANCED_SCHEDULED_HISTORY_SELECTION_SCHEMA = "sentientos.developmental_history_intervention_protocol:v10"
BALANCED_OBJECTIVE_SCHEDULED_HISTORY_SELECTION_SCHEMA = "sentientos.developmental_history_intervention_protocol:v11"
OBJECTIVE_PROBE_OUTCOMES_SCHEMA = "sentientos.developmental_history_intervention_protocol:v12"
CALIBRATED_OBJECTIVE_SCHEDULED_HISTORY_SCHEMA = (
    "sentientos.developmental_history_intervention_protocol:v13")
OBJECTIVE_STRATEGY_ARM_SCHEMA = (
    "sentientos.developmental_history_intervention_protocol:v14")
OBJECTIVE_AUTHORITY_POLICY_SCHEMA = (
    "sentientos.developmental_history_intervention_protocol:v15")
OBJECTIVE_SCHEDULE_SCHEMA = "sentientos.developmental_objective_history_schedule:v1"
OBJECTIVE_SCHEDULE_ID_PREFIX = "developmental-objective-schedule-"
OBJECTIVE_SCHEMAS = frozenset({LEGACY_OBJECTIVE_SCHEMA, OBJECTIVE_SCHEMA,
    OBJECTIVE_HISTORY_SELECTION_SCHEMA, OBJECTIVE_SCHEDULED_HISTORY_SELECTION_SCHEMA,
    BALANCED_OBJECTIVE_SCHEDULED_HISTORY_SELECTION_SCHEMA,
    OBJECTIVE_PROBE_OUTCOMES_SCHEMA,
    CALIBRATED_OBJECTIVE_SCHEDULED_HISTORY_SCHEMA,
    OBJECTIVE_STRATEGY_ARM_SCHEMA, OBJECTIVE_AUTHORITY_POLICY_SCHEMA})
HISTORY_SELECTION_SCHEMAS = frozenset({HISTORY_SELECTION_SCHEMA,
    OBJECTIVE_HISTORY_SELECTION_SCHEMA, COUNTERBALANCED_HISTORY_SELECTION_SCHEMA,
    SCHEDULED_HISTORY_SELECTION_SCHEMA, OBJECTIVE_SCHEDULED_HISTORY_SELECTION_SCHEMA,
    BALANCED_SCHEDULED_HISTORY_SELECTION_SCHEMA,
    BALANCED_OBJECTIVE_SCHEDULED_HISTORY_SELECTION_SCHEMA,
    OBJECTIVE_PROBE_OUTCOMES_SCHEMA,
    CALIBRATED_OBJECTIVE_SCHEDULED_HISTORY_SCHEMA,
    OBJECTIVE_STRATEGY_ARM_SCHEMA, OBJECTIVE_AUTHORITY_POLICY_SCHEMA})
SCHEDULED_ORDER_SCHEMAS = frozenset({SCHEDULED_HISTORY_SELECTION_SCHEMA,
    OBJECTIVE_SCHEDULED_HISTORY_SELECTION_SCHEMA,
    BALANCED_SCHEDULED_HISTORY_SELECTION_SCHEMA,
    BALANCED_OBJECTIVE_SCHEDULED_HISTORY_SELECTION_SCHEMA,
    CALIBRATED_OBJECTIVE_SCHEDULED_HISTORY_SCHEMA})
LEGACY_RUN_SCHEMA = "sentientos.developmental_history_intervention_run:v1"
PREVIOUS_RUN_SCHEMA = "sentientos.developmental_history_intervention_run:v2"
RUN_SCHEMA = "sentientos.developmental_history_intervention_run:v3"
COMPANION_DECISION_RUN_SCHEMAS = frozenset({PREVIOUS_RUN_SCHEMA, RUN_SCHEMA})
RETRIEVAL_COMPARISON_ARTIFACT_SCHEMA = (
    "sentientos.developmental_history_retrieval_comparison_artifact:v1")
RETRIEVAL_COMPARISON_ID_PREFIX = "devexp-retrieval-comparison-"
RETRIEVAL_CORPUS_FREEZE_SCHEMA = (
    "sentientos.developmental_history_retrieval_corpus_freeze:v2")
RETRIEVAL_CORPUS_FREEZE_ID_PREFIX = "devexp-retrieval-freeze-"
LEGACY_RETRIEVAL_QUERY_SET_SCHEMA = (
    "sentientos.developmental_history_retrieval_query_set:v5")
PREVIOUS_RETRIEVAL_QUERY_SET_SCHEMA = (
    "sentientos.developmental_history_retrieval_query_set:v6")
RETRIEVAL_QUERY_SET_SCHEMA = (
    "sentientos.developmental_history_retrieval_query_set:v7")
RETRIEVAL_QUERY_SET_ID_PREFIX = "devexp-retrieval-queries-"
LEGACY_RETRIEVAL_COMPARISON_COHORT_SCHEMA = (
    "sentientos.developmental_history_retrieval_comparison_cohort:v11")
PREVIOUS_RETRIEVAL_COMPARISON_COHORT_SCHEMA = (
    "sentientos.developmental_history_retrieval_comparison_cohort:v12")
RETRIEVAL_COMPARISON_COHORT_SCHEMA = (
    "sentientos.developmental_history_retrieval_comparison_cohort:v13")
RETRIEVAL_COMPARISON_COHORT_ID_PREFIX = "devexp-retrieval-cohort-"
RETRIEVAL_EVALUATION_ARTIFACT_SCHEMA = (
    "sentientos.developmental_history_retrieval_evaluation_artifact:v3")
RETRIEVAL_EVALUATION_ID_PREFIX = "devexp-retrieval-evaluation-"
MIN_RETRIEVAL_COMPARISON_QUERIES = 60
MAX_RETRIEVAL_COMPARISON_QUERIES = 255
RETRIEVAL_QUERY_STRATA = ("paraphrased_experience", "lexical_distractor",
    "no_applicable_history")
RETRIEVAL_EVALUATION_PROTOCOL_V3 = {
    "schema_version": "sentientos.semantic_history_retrieval_gate:v3",
    "minimum_queries_per_stratum": 20,
    "paraphrase_recall_minimum_gain": 0.10,
    "paraphrase_recall_ci_lower_exclusive": 0.0,
    "maximum_false_inclusion_rate_increase": 0.02,
    "false_inclusion_ci_upper_inclusive": 0.02,
    "minimum_independent_reviewer_exact_agreement": 0.80,
    "confidence_level": 0.95,
    "bootstrap_samples": 10_000,
    "bootstrap_seed": "cohort_and_annotation_digest:v1",
    "adjudication_procedure_digest": (
        retrieval_adjudication_procedure()["procedure_digest"]),
}
RETRIEVAL_EVALUATION_PROTOCOL = {
    **RETRIEVAL_EVALUATION_PROTOCOL_V3,
    "schema_version": "sentientos.semantic_history_retrieval_gate:v4",
    "bootstrap_seed": "cohort_annotation_digest_first_16_hex:v2",
    "bootstrap_stratum_offsets": {
        "paraphrased_experience": 0,
        "lexical_distractor": 10,
        "no_applicable_history": 20,
        "overall": 100},
    "bootstrap_metric_offsets": {
        "recall": 0,
        "reciprocal_rank": 1,
        "inapplicable_selection_rate": 2,
        "common_k_recall": 3,
        "selected_record_count": 4,
        "common_k_reciprocal_rank": 5},
    "bootstrap_interval_method": "percentile_floor_index_no_interpolation:v1",
    "paraphrase_recall_metric": "common_k_recall",
    "common_k_rule": "minimum_condition_selected_count_per_query:v1",
    "zero_common_k_recall": "zero_for_both_conditions:v1",
    "identical_selection_metric": "set_equality_and_order_separately:v1",
    "selected_record_count_interval": "paired_query_percentile_bootstrap:v1",
    "full_selection_recall_minimum_gain": 0.0,
}
RETRIEVAL_EVALUATION_PROTOCOL_V4 = RETRIEVAL_EVALUATION_PROTOCOL
RETRIEVAL_EVALUATION_PROTOCOL_V5 = {
    **RETRIEVAL_EVALUATION_PROTOCOL,
    "schema_version": "sentientos.semantic_history_retrieval_gate:v5",
    "maximum_semantic_fallback_queries": 0,
}
RETRIEVAL_EVALUATION_PROTOCOL_V6 = {
    **RETRIEVAL_EVALUATION_PROTOCOL_V5,
    "schema_version": "sentientos.semantic_history_retrieval_gate:v6",
    "bootstrap_seed": "preregistered_query_set_digest_first_16_hex:v1",
}
RETRIEVAL_EVALUATION_PROTOCOL_V7 = {
    **RETRIEVAL_EVALUATION_PROTOCOL_V6,
    "schema_version": "sentientos.semantic_history_retrieval_gate:v7",
    "adjudication_procedure_digest": (
        retrieval_adjudication_procedure(source_record_bindings=True)[
            "procedure_digest"]),
}
RETRIEVAL_EVALUATION_PROTOCOL_V8 = {
    **RETRIEVAL_EVALUATION_PROTOCOL_V7,
    "schema_version": "sentientos.semantic_history_retrieval_gate:v8",
    "bootstrap_metric_offsets": {
        **RETRIEVAL_EVALUATION_PROTOCOL_V7["bootstrap_metric_offsets"],
        "nonrelevant_selection_rate": 6},
    "maximum_nonrelevant_selection_rate_increase": 0.02,
}
RETRIEVAL_EVALUATION_PROTOCOL_V9 = {
    **RETRIEVAL_EVALUATION_PROTOCOL_V8,
    "schema_version": "sentientos.semantic_history_retrieval_gate:v9",
    "adjudication_procedure_digest": (
        retrieval_adjudication_procedure(
            conceal_preregistered_strata=True)["procedure_digest"]),
}
RETRIEVAL_EVALUATION_PROTOCOL_V10 = {
    **RETRIEVAL_EVALUATION_PROTOCOL_V8,
    "schema_version": "sentientos.semantic_history_retrieval_gate:v10",
    "adjudication_procedure_digest": (
        retrieval_adjudication_procedure(source_record_bindings=True,
            conceal_preregistered_strata=True)["procedure_digest"]),
}
RETRIEVAL_EVALUATION_PROTOCOL_V11 = {
    **RETRIEVAL_EVALUATION_PROTOCOL_V9,
    "schema_version": "sentientos.semantic_history_retrieval_gate:v11",
    "false_inclusion_interval_method":
        "paired_binary_clopper_pearson_bonferroni:v1",
}
RETRIEVAL_EVALUATION_PROTOCOL_V12 = {
    **RETRIEVAL_EVALUATION_PROTOCOL_V10,
    "schema_version": "sentientos.semantic_history_retrieval_gate:v12",
    "false_inclusion_interval_method":
        "paired_binary_clopper_pearson_bonferroni:v1",
}
RETRIEVAL_EVALUATION_PROTOCOL = RETRIEVAL_EVALUATION_PROTOCOL_V11
SUPPORTED_RETRIEVAL_EVALUATION_PROTOCOLS = (
    RETRIEVAL_EVALUATION_PROTOCOL_V3,
    RETRIEVAL_EVALUATION_PROTOCOL_V4,
    RETRIEVAL_EVALUATION_PROTOCOL_V5,
    RETRIEVAL_EVALUATION_PROTOCOL_V6,
    RETRIEVAL_EVALUATION_PROTOCOL_V7,
    RETRIEVAL_EVALUATION_PROTOCOL_V8,
    RETRIEVAL_EVALUATION_PROTOCOL_V9,
    RETRIEVAL_EVALUATION_PROTOCOL_V10,
    RETRIEVAL_EVALUATION_PROTOCOL_V11,
    RETRIEVAL_EVALUATION_PROTOCOL_V12)
MAX_RETRIEVAL_COMPARISON_INPUT_CHARS = 48_000
PURPOSE = "resident_developmental_history_intervention_experiment"
CONDITION_ORDER = ("history_present", "history_withheld", "history_restored")
COUNTERBALANCED_CONDITION_ORDER = (
    "history_withheld", "history_present", "history_restored")
BALANCED_CONDITION_ORDERS = (
    CONDITION_ORDER,
    COUNTERBALANCED_CONDITION_ORDER,
    ("history_present", "history_restored", "history_withheld"),
    ("history_withheld", "history_restored", "history_present"),
    ("history_restored", "history_present", "history_withheld"),
    ("history_restored", "history_withheld", "history_present"),
)
NON_CLAIMS = ("learning", "improvement", "persistent_individuality", "selfhood", "consciousness", "sentience", "causal_closure")
MAX_EXPERIMENT_ARTIFACT_BYTES = 4_194_304


class DevelopmentalHistoryInterventionError(ValueError):
    pass


def _digest(value: Any) -> str:
    return "sha256:" + str(digest_payload(value))


def _valid_sha256_digest(value: Any) -> bool:
    return (type(value) is str and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:]))


def _valid_raw_sha256_digest(value: Any) -> bool:
    return (type(value) is str and len(value) == 64
        and all(character in "0123456789abcdef" for character in value))


def _strategy_intervention_digest(value: Mapping[str, Any]) -> str:
    """Match the compact ASCII digest used by the CPU strategy protocol."""
    try:
        body = json.dumps(value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise DevelopmentalHistoryInterventionError(
            "strategy_intervention_artifact_not_canonical") from exc
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _objective_cohort_binding_values(protocol: Mapping[str, Any]) -> tuple[Any, ...]:
    descriptor = protocol.get("objective_task_descriptor")
    if not isinstance(descriptor, Mapping):
        raise DevelopmentalHistoryInterventionError("objective_cohort_task_binding_missing")
    return (protocol.get("model_id"), protocol.get("model_artifact_digest"),
        protocol.get("active_model_identity_digest"), protocol.get(
            "authority_map_policy_digest") or protocol.get("authority_map_digest"),
        protocol.get("instruction_template_digest"), protocol.get("history_selection_digest"),
        protocol.get("history_available_records_digest"),
        protocol.get("objective_task_digest"), descriptor.get("task_family_id"),
        descriptor.get("task_digest"), protocol.get("current_projection_digest"),
        protocol.get("generation_posture"), protocol.get("inference_budget"),
        protocol.get("self_model_projection_digest"),
        protocol.get("epistemic_projection_digest"))


def objective_history_cohort_binding_digest(protocol: Mapping[str, Any]) -> str:
    """Digest the exact controls that make objective runs members of one cohort."""
    binding = _objective_cohort_binding_values(protocol)
    if (any(value is None for value in binding[:8])
            or not _valid_sha256_digest(binding[9])
            or not _valid_sha256_digest(binding[10])
            or not isinstance(binding[11], Mapping)
            or not isinstance(binding[12], Mapping)):
        raise DevelopmentalHistoryInterventionError("objective_cohort_binding_incomplete")
    return _digest(list(binding))


def _verify_objective_schedule_claim(claim: Mapping[str, Any], *,
        binding_digest: str, trial_index: int,
        protocol: DevelopmentalHistoryInterventionProtocol | None = None) -> None:
    expected_fields = {"schema_version", "cohort_binding_digest", "trial_index",
        "protocol_id", "protocol_digest", "condition_order", "authority",
        "schedule_digest"}
    semantic = {key: value for key, value in claim.items()
        if key != "schedule_digest"}
    protocol_digest = claim.get("protocol_digest")
    protocol_id = claim.get("protocol_id")
    if (set(claim) != expected_fields
            or claim.get("schema_version") != OBJECTIVE_SCHEDULE_SCHEMA
            or claim.get("cohort_binding_digest") != binding_digest
            or type(claim.get("trial_index")) is not int
            or claim.get("trial_index") != trial_index or trial_index < 0
            or not _valid_sha256_digest(protocol_digest)
            or protocol_id != "devexp-protocol-" + protocol_digest[7:31]
            or claim.get("condition_order") != list(
                balanced_history_condition_order_for_trial(trial_index))
            or claim.get("authority") is not False
            or claim.get("schedule_digest") != _digest(semantic)):
        raise DevelopmentalHistoryInterventionError(
            "objective_history_schedule_claim_invalid")
    if (protocol is not None
            and (claim.get("protocol_id") != protocol.protocol_id
                or claim.get("protocol_digest") != protocol.protocol_digest
                or claim.get("condition_order") != list(protocol.condition_order))):
        raise DevelopmentalHistoryInterventionError(
            "objective_history_schedule_protocol_mismatch")


@dataclass(frozen=True)
class DevelopmentalHistoryInterventionProtocol:
    protocol_id: str
    protocol_digest: str
    snapshot_id: str
    snapshot_digest: str
    current_projection_id: str
    current_projection_digest: str
    current_fact_ids: tuple[str, ...]
    record_ids: tuple[str, ...]
    record_digests: tuple[str, ...]
    record_set_digest: str
    model_id: str
    model_artifact_digest: str | None
    active_model_identity: Mapping[str, Any]
    active_model_identity_digest: str
    authority_map_digest: str
    inference_purpose: str
    inference_budget: Mapping[str, Any]
    generation_posture: Mapping[str, Any]
    condition_order: tuple[str, ...]
    instruction_template_digest: str
    planned_comparisons: tuple[str, ...]
    non_claims: tuple[str, ...]
    epistemic_projection_id: str | None = None
    epistemic_projection_digest: str | None = None
    epistemic_state_digests: tuple[str, ...] = ()
    epistemic_evidence_set_digests: tuple[str, ...] = ()
    self_model_projection_id: str | None = None
    self_model_projection_digest: str | None = None
    self_model_reconciliation_id: str | None = None
    self_model_reconciliation_digest: str | None = None
    self_model_reconciliation_generation: int | None = None
    self_model_source_tick: str | None = None
    self_model_claim_ids: tuple[str, ...] = ()
    self_model_claim_digests: tuple[str, ...] = ()
    objective_task_digest: str | None = None
    objective_task_descriptor: Mapping[str, Any] | None = None
    history_selection_digest: str | None = None
    history_available_records_digest: str | None = None
    condition_order_trial_index: int | None = None
    grants_authority: bool = False
    schema_version: str = SCHEMA
    authority_map_policy_digest: str | None = None

    def semantic_payload(self) -> dict[str, Any]:
        value = asdict(self); value.pop("protocol_id"); value.pop("protocol_digest")
        if self.schema_version == OBJECTIVE_AUTHORITY_POLICY_SCHEMA:
            value.pop("authority_map_digest", None)
        else:
            value.pop("authority_map_policy_digest", None)
        if self.schema_version == LEGACY_SCHEMA:
            for key in ("self_model_projection_id", "self_model_projection_digest",
                        "self_model_reconciliation_id", "self_model_reconciliation_digest",
                        "self_model_reconciliation_generation", "self_model_source_tick",
                        "self_model_claim_ids", "self_model_claim_digests"):
                value.pop(key, None)
        if self.schema_version not in OBJECTIVE_SCHEMAS:
            value.pop("objective_task_digest", None)
            value.pop("objective_task_descriptor", None)
        if self.schema_version not in HISTORY_SELECTION_SCHEMAS:
            value.pop("history_selection_digest", None)
            value.pop("history_available_records_digest", None)
        if self.schema_version not in SCHEDULED_ORDER_SCHEMAS:
            value.pop("condition_order_trial_index", None)
        return value


def history_condition_order_for_trial(trial_index: int) -> tuple[str, ...]:
    """Return the legacy deterministic alternating-first order for a trial."""
    if type(trial_index) is not int or trial_index < 0:
        raise DevelopmentalHistoryInterventionError("trial_index_invalid")
    return (CONDITION_ORDER if trial_index % 2 == 0
        else COUNTERBALANCED_CONDITION_ORDER)


def balanced_history_condition_order_for_trial(
        trial_index: int) -> tuple[str, ...]:
    """Balance all three conditions across positions over six scheduled trials."""
    if type(trial_index) is not int or trial_index < 0:
        raise DevelopmentalHistoryInterventionError("trial_index_invalid")
    return BALANCED_CONDITION_ORDERS[trial_index % len(BALANCED_CONDITION_ORDERS)]


def make_protocol(*, condition_order: tuple[str, ...] = CONDITION_ORDER,
        planned_comparisons: tuple[str, ...] = (
            "present_vs_withheld", "restored_vs_withheld"),
        **kwargs: Any) -> DevelopmentalHistoryInterventionProtocol:
    raw = DevelopmentalHistoryInterventionProtocol("", "", condition_order=condition_order,
        inference_purpose=PURPOSE, planned_comparisons=planned_comparisons,
        non_claims=NON_CLAIMS, **kwargs)
    digest = _digest(raw.semantic_payload())
    return replace(raw, protocol_id="devexp-protocol-" + digest[7:31], protocol_digest=digest)


def verify_protocol(protocol: DevelopmentalHistoryInterventionProtocol) -> None:
    digest = _digest(protocol.semantic_payload())
    if protocol.protocol_digest != digest or protocol.protocol_id != "devexp-protocol-" + digest[7:31]:
        raise DevelopmentalHistoryInterventionError("protocol_digest_mismatch")
    allowed_orders: tuple[tuple[str, ...], ...]
    if protocol.schema_version in {OBJECTIVE_STRATEGY_ARM_SCHEMA,
            OBJECTIVE_AUTHORITY_POLICY_SCHEMA}:
        allowed_orders = (("history_present",),)
    elif protocol.schema_version in SCHEDULED_ORDER_SCHEMAS:
        expected_order = (
            balanced_history_condition_order_for_trial(
                protocol.condition_order_trial_index)
            if protocol.schema_version in {
                BALANCED_SCHEDULED_HISTORY_SELECTION_SCHEMA,
                BALANCED_OBJECTIVE_SCHEDULED_HISTORY_SELECTION_SCHEMA,
                CALIBRATED_OBJECTIVE_SCHEDULED_HISTORY_SCHEMA}
            else history_condition_order_for_trial(
                protocol.condition_order_trial_index))
        allowed_orders = ((expected_order,)
            if type(protocol.condition_order_trial_index) is int
                and protocol.condition_order_trial_index >= 0 else ())
    elif protocol.schema_version == COUNTERBALANCED_HISTORY_SELECTION_SCHEMA:
        allowed_orders = (CONDITION_ORDER, COUNTERBALANCED_CONDITION_ORDER)
    else:
        allowed_orders = (CONDITION_ORDER,)
    if (protocol.schema_version not in {LEGACY_SCHEMA, SCHEMA,
            HISTORY_SELECTION_SCHEMA, COUNTERBALANCED_HISTORY_SELECTION_SCHEMA,
            SCHEDULED_HISTORY_SELECTION_SCHEMA,
            OBJECTIVE_SCHEDULED_HISTORY_SELECTION_SCHEMA,
            BALANCED_SCHEDULED_HISTORY_SELECTION_SCHEMA,
            BALANCED_OBJECTIVE_SCHEDULED_HISTORY_SELECTION_SCHEMA,
            CALIBRATED_OBJECTIVE_SCHEDULED_HISTORY_SCHEMA,
            *OBJECTIVE_SCHEMAS}
            or type(protocol.condition_order) is not tuple
            or protocol.condition_order not in allowed_orders
            or (protocol.schema_version in SCHEDULED_ORDER_SCHEMAS
                and (type(protocol.condition_order_trial_index) is not int
                    or protocol.condition_order_trial_index < 0))
            or (protocol.schema_version not in SCHEDULED_ORDER_SCHEMAS
                and protocol.condition_order_trial_index is not None)
            or type(protocol.planned_comparisons) is not tuple
            or (protocol.planned_comparisons not in {
                ("present_vs_withheld", "restored_vs_withheld"),
                ("present_vs_withheld", "restored_vs_withheld",
                    "accumulated_strategy_inclusion:included"),
                ("present_vs_withheld", "restored_vs_withheld",
                    "accumulated_strategy_inclusion:omitted"),
                ("strategy_arm:included",),
                ("strategy_arm:omitted",),
                ("strategy_arm:included", "negative_guidance_arm:present"),
                ("strategy_arm:included", "negative_guidance_arm:omitted")}
                or (len(protocol.planned_comparisons) > 2
                    and protocol.schema_version not in OBJECTIVE_SCHEMAS))
            or protocol.inference_purpose != PURPOSE or protocol.grants_authority):
        raise DevelopmentalHistoryInterventionError("protocol_control_invalid")
    if (protocol.schema_version == OBJECTIVE_AUTHORITY_POLICY_SCHEMA
            and (not _valid_raw_sha256_digest(protocol.authority_map_policy_digest)
                or not _valid_raw_sha256_digest(protocol.authority_map_digest))):
        raise DevelopmentalHistoryInterventionError(
            "authority_policy_protocol_binding_invalid")
    if protocol.schema_version in OBJECTIVE_SCHEMAS:
        if (not isinstance(protocol.objective_task_digest, str)
                or not isinstance(protocol.objective_task_descriptor, Mapping)
                or protocol.objective_task_descriptor.get("task_digest") != protocol.objective_task_digest):
            raise DevelopmentalHistoryInterventionError("objective_task_protocol_binding_invalid")
    elif protocol.objective_task_digest is not None or protocol.objective_task_descriptor is not None:
        raise DevelopmentalHistoryInterventionError("objective_task_protocol_binding_invalid")
    if protocol.schema_version in HISTORY_SELECTION_SCHEMAS:
        if any(not isinstance(value, str) or len(value) != 71
                or not value.startswith("sha256:")
                or any(character not in "0123456789abcdef" for character in value[7:])
                for value in (protocol.history_selection_digest,
                    protocol.history_available_records_digest)):
            raise DevelopmentalHistoryInterventionError("history_selection_protocol_binding_invalid")
    elif (protocol.history_selection_digest is not None
            or protocol.history_available_records_digest is not None):
        raise DevelopmentalHistoryInterventionError("history_selection_protocol_binding_invalid")
    if (len(protocol.planned_comparisons) > 2
            and (protocol.schema_version not in OBJECTIVE_SCHEMAS
                or not isinstance(protocol.objective_task_descriptor, Mapping)
                or protocol.objective_task_descriptor.get(
                    "requires_task_family_history") is not True)):
        raise DevelopmentalHistoryInterventionError(
            "strategy_inclusion_protocol_task_family_invalid")


def objective_task_contamination_assessment(
        protocol: DevelopmentalHistoryInterventionProtocol) -> dict[str, Any]:
    """Bind an explicit unknown posture; this owner does not certify task cleanliness."""
    if protocol.schema_version not in OBJECTIVE_SCHEMAS or not protocol.objective_task_digest:
        raise DevelopmentalHistoryInterventionError("objective_task_protocol_required")
    return {
        "schema_version": "sentientos.objective_task_contamination_assessment:v1",
        "status": "not_assessed",
        "reason_code": "task_specific_history_and_current_context_leakage_unverified",
        "objective_task_digest": protocol.objective_task_digest,
        "current_projection_id": protocol.current_projection_id,
        "current_projection_digest": protocol.current_projection_digest,
        "current_projection_shared_across_conditions": True,
        "history_examples_absent_from_current_context": None,
        "oracle_answer_absent_from_current_context": None,
        "authority": False,
    }


class DevelopmentalExperimentStore:
    def __init__(self, root: Path, *,
                 invocation_verifier: Callable[[Mapping[str, Any]], Any] | None = None) -> None:
        self.root = Path(root) / "developmental_experiments"
        self._invocation_verifier = invocation_verifier
        self.protocols = self.root / "protocols"; self.runs = self.root / "runs"
        try:
            memory_root = Path(sentientos_memory_dir()).expanduser().resolve(strict=False)
            storage_roots = (
                self.protocols.expanduser().resolve(strict=False),
                self.runs.expanduser().resolve(strict=False),
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise DevelopmentalHistoryInterventionError(
                "canonical_memory_root_identity_invalid") from exc
        if any(path == memory_root or path in memory_root.parents or memory_root in path.parents
               for path in storage_roots):
            raise DevelopmentalHistoryInterventionError(
                "experiment_root_overlaps_canonical_memory")

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        if os.name == "nt":
            try:
                raw = read_explicit_file(path, max_bytes=MAX_EXPERIMENT_ARTIFACT_BYTES,
                    require_private_acl=True)
            except WindowsHandleCustodyError as exc:
                if str(exc) == "explicit_file_missing":
                    raise FileNotFoundError(path) from exc
                raise DevelopmentalHistoryInterventionError("experiment_artifact_not_regular") from exc
        else:
            try:
                directory_fd = _open_store_directory(path.parent, create=False)
            except DevelopmentalWritebackError as exc:
                if str(exc) == "durable_store_root_missing":
                    raise FileNotFoundError(path) from exc
                raise DevelopmentalHistoryInterventionError("experiment_artifact_custody_invalid") from exc
            try:
                raw = _read_store_file(directory_fd, path.name, max_bytes=MAX_EXPERIMENT_ARTIFACT_BYTES)
            except DevelopmentalWritebackError as exc:
                if str(exc) == "stored_payload_missing":
                    raise FileNotFoundError(path) from exc
                raise DevelopmentalHistoryInterventionError("experiment_artifact_not_regular") from exc
            finally:
                os.close(directory_fd)
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise DevelopmentalHistoryInterventionError("experiment_artifact_invalid") from exc
        if (not isinstance(value, dict)
                or json.dumps(value, sort_keys=True, indent=2).encode("utf-8") + b"\n" != raw):
            raise DevelopmentalHistoryInterventionError("experiment_artifact_noncanonical")
        return value

    def _ensure_windows_collection(self, collection: Path) -> tuple[int, bytes]:
        if os.name != "nt" or collection not in {self.protocols, self.runs}:
            raise DevelopmentalHistoryInterventionError(
                "experiment_artifact_windows_collection_invalid")
        try:
            verify_explicit_directory(self.root.parent, require_private_acl=True)
            ensure_private_child_directory(self.root.parent, self.root.name)
            ensure_private_child_directory(self.root, collection.name)
            return observe_private_directory_identity(collection)
        except (WindowsHandleCustodyError, OSError) as exc:
            raise DevelopmentalHistoryInterventionError(
                "experiment_artifact_windows_collection_custody_invalid") from exc

    def _write_immutable(self, path: Path, payload: Mapping[str, Any]) -> bool:
        """Publish immutably; return False for an exact pre-existing artifact."""
        normalized = json.loads(json.dumps(dict(payload), sort_keys=True))
        try:
            existing = self._read_json(path)
        except FileNotFoundError:
            existing = None
        if existing is not None:
            if existing != normalized:
                raise DevelopmentalHistoryInterventionError("artifact_identity_collision")
            return False
        if os.name == "nt":
            root_identity = self._ensure_windows_collection(path.parent)
            policy = ("objective_task_plan"
                if (path.parent == self.protocols
                    and path.name.startswith("objective-task-plan-")) else
                "strategy_inclusion_protocol"
                if (path.parent == self.protocols
                    and path.name.startswith("strategy-inclusion-protocol-")) else
                "developmental_objective_history_schedule"
                if (path.parent == self.protocols
                    and path.name.startswith(OBJECTIVE_SCHEDULE_ID_PREFIX)) else
                "objective_condition_score"
                if (path.parent == self.protocols
                    and path.name.startswith("objective-score-")) else None)
            if policy is None:
                policy = ("strategy_inclusion_arm_claim"
                    if (path.parent == self.runs
                        and path.name.startswith("strategy-inclusion-arm-claim-")) else
                    "strategy_inclusion_arm_result"
                    if (path.parent == self.runs
                        and path.name.startswith("strategy-inclusion-arm-result-")) else
                    "strategy_inclusion_score"
                    if (path.parent == self.runs
                        and path.name.startswith("strategy-inclusion-score-")) else
                    "ordinary_chat_history_protocol"
                    if (path.parent == self.protocols
                        and path.name.startswith("ordinary-history-protocol-")) else
                    "ordinary_chat_history_schedule"
                    if (path.parent == self.protocols
                        and path.name.startswith("ordinary-history-schedule-")) else
                    "ordinary_chat_history_execution_claim"
                    if (path.parent == self.protocols
                        and path.name.startswith("ordinary-history-execution-")) else
                    "ordinary_chat_history_scoring_plan"
                    if (path.parent == self.protocols
                        and path.name.startswith("ordinary-history-score-plan-")) else
                    "ordinary_chat_history_score"
                    if (path.parent == self.runs
                        and path.name.startswith("ordinary-history-score-")) else
                    "ordinary_chat_history_result"
                    if (path.parent == self.runs
                        and path.name.startswith("ordinary-history-result-")) else
                    "ordinary_chat_history_final_result_index"
                    if (path.parent == self.runs
                        and path.name.startswith("ordinary-history-final-")) else
                    "ordinary_chat_history_evaluation"
                    if (path.parent == self.runs
                        and path.name.startswith("ordinary-history-evaluation-")) else
                    "ordinary_chat_history_cohort_summary"
                    if (path.parent == self.runs
                        and path.name.startswith("ordinary-history-cohort-")) else
                    "developmental_objective_cohort_summary"
                    if (path.parent == self.runs
                        and path.name.startswith("developmental-objective-cohort-")) else
                    "developmental_history_retrieval_comparison"
                    if (path.parent == self.runs
                        and path.name.startswith(RETRIEVAL_COMPARISON_ID_PREFIX)) else
                    "developmental_history_retrieval_corpus_freeze"
                    if (path.parent == self.runs
                        and path.name.startswith(RETRIEVAL_CORPUS_FREEZE_ID_PREFIX)) else
                    "developmental_history_retrieval_query_set"
                    if (path.parent == self.runs
                        and path.name.startswith(RETRIEVAL_QUERY_SET_ID_PREFIX)) else
                    "developmental_history_retrieval_comparison_cohort"
                    if (path.parent == self.runs
                        and path.name.startswith(RETRIEVAL_COMPARISON_COHORT_ID_PREFIX)) else
                    "developmental_history_retrieval_evaluation"
                    if (path.parent == self.runs
                        and path.name.startswith(RETRIEVAL_EVALUATION_ID_PREFIX)) else
                    "durable_learning_consolidation_intent"
                    if (path.parent == self.runs
                        and path.name.startswith(
                            "devexp-durable-learning-consolidation-intent-")) else
                    "durable_learning_consolidation_receipt"
                    if (path.parent == self.runs
                        and path.name.startswith(
                            "devexp-durable-learning-consolidation-receipt-")) else
                    "developmental_experiment_protocol"
                    if path.parent == self.protocols else
                    "developmental_experiment_run"
                    if path.parent == self.runs else None)
            if policy is None:
                raise DevelopmentalHistoryInterventionError(
                    "experiment_artifact_windows_filename_policy_invalid")
            try:
                _publish_store_json(path, payload,
                    collision_error="artifact_identity_collision",
                    max_bytes=MAX_EXPERIMENT_ARTIFACT_BYTES,
                    windows_root_identity=root_identity,
                    windows_filename_policy=policy)
            except DevelopmentalWritebackError as exc:
                if str(exc) == "artifact_identity_collision":
                    raise DevelopmentalHistoryInterventionError(
                        "artifact_identity_collision") from exc
                raise DevelopmentalHistoryInterventionError(
                    "experiment_artifact_publication_failed") from exc
            return True
        if os.name != "posix":
            raise DevelopmentalHistoryInterventionError("experiment_artifact_publication_unsupported_platform")
        try:
            _publish_store_json(path, payload, collision_error="artifact_identity_collision",
                                max_bytes=MAX_EXPERIMENT_ARTIFACT_BYTES)
        except DevelopmentalWritebackError as exc:
            if str(exc) == "artifact_identity_collision":
                raise DevelopmentalHistoryInterventionError("artifact_identity_collision") from exc
            raise DevelopmentalHistoryInterventionError("experiment_artifact_publication_failed") from exc
        return True

    def _objective_schedule_path(self, binding_digest: str, trial_index: int) -> Path:
        return self.protocols / (
            f"{OBJECTIVE_SCHEDULE_ID_PREFIX}{binding_digest[7:31]}-{trial_index:08d}.json")

    def verify_objective_history_schedule(self,
            protocol: DevelopmentalHistoryInterventionProtocol, *,
            required: bool = False) -> dict[str, Any] | None:
        if protocol.schema_version not in {
                BALANCED_OBJECTIVE_SCHEDULED_HISTORY_SELECTION_SCHEMA,
                CALIBRATED_OBJECTIVE_SCHEDULED_HISTORY_SCHEMA}:
            if required:
                raise DevelopmentalHistoryInterventionError(
                    "objective_history_schedule_protocol_invalid")
            return None
        binding_digest = objective_history_cohort_binding_digest(asdict(protocol))
        trial_index = protocol.condition_order_trial_index
        if type(trial_index) is not int:
            raise DevelopmentalHistoryInterventionError(
                "objective_history_schedule_protocol_invalid")
        try:
            claim = self._read_json(self._objective_schedule_path(
                binding_digest, trial_index))
        except FileNotFoundError as exc:
            if required:
                raise DevelopmentalHistoryInterventionError(
                    "objective_history_schedule_claim_missing") from exc
            return None
        _verify_objective_schedule_claim(claim, binding_digest=binding_digest,
            trial_index=trial_index, protocol=protocol)
        return claim

    def next_objective_history_order_trial_index(
            self, protocol_context: Mapping[str, Any]) -> int:
        binding_digest = objective_history_cohort_binding_digest(protocol_context)
        for trial_index in range(2**32):
            path = self._objective_schedule_path(binding_digest, trial_index)
            try:
                claim = self._read_json(path)
            except FileNotFoundError:
                return trial_index
            _verify_objective_schedule_claim(claim,
                binding_digest=binding_digest, trial_index=trial_index)
            prior_protocol = self.load_protocol(str(claim["protocol_id"]))
            if (prior_protocol.protocol_digest != claim.get("protocol_digest")
                    or prior_protocol.schema_version
                        not in {BALANCED_OBJECTIVE_SCHEDULED_HISTORY_SELECTION_SCHEMA,
                            CALIBRATED_OBJECTIVE_SCHEDULED_HISTORY_SCHEMA}
                    or prior_protocol.condition_order_trial_index != trial_index
                    or objective_history_cohort_binding_digest(
                        asdict(prior_protocol)) != binding_digest):
                raise DevelopmentalHistoryInterventionError(
                    "objective_history_schedule_protocol_binding_invalid")
        raise DevelopmentalHistoryInterventionError(
            "objective_history_schedule_trial_limit_reached")

    def _persist_objective_schedule_claim(
            self, protocol: DevelopmentalHistoryInterventionProtocol) -> None:
        if protocol.schema_version not in {
                BALANCED_OBJECTIVE_SCHEDULED_HISTORY_SELECTION_SCHEMA,
                CALIBRATED_OBJECTIVE_SCHEDULED_HISTORY_SCHEMA}:
            return
        context = asdict(protocol)
        binding_digest = objective_history_cohort_binding_digest(context)
        trial_index = protocol.condition_order_trial_index
        if type(trial_index) is not int or trial_index < 0:
            raise DevelopmentalHistoryInterventionError(
                "objective_history_schedule_protocol_invalid")
        existing = self.verify_objective_history_schedule(protocol)
        if existing is not None:
            return
        path = self._objective_schedule_path(binding_digest, trial_index)
        next_index = self.next_objective_history_order_trial_index(context)
        if next_index != trial_index:
            raise DevelopmentalHistoryInterventionError(
                "objective_history_schedule_index_not_next")
        semantic = {"schema_version": OBJECTIVE_SCHEDULE_SCHEMA,
            "cohort_binding_digest": binding_digest,
            "trial_index": trial_index,
            "protocol_id": protocol.protocol_id,
            "protocol_digest": protocol.protocol_digest,
            "condition_order": list(protocol.condition_order),
            "authority": False}
        self._write_immutable(path,
            {**semantic, "schedule_digest": _digest(semantic)})
        _verify_objective_schedule_claim(self._read_json(path),
            binding_digest=binding_digest, trial_index=trial_index,
            protocol=protocol)

    def persist_protocol(self, protocol: DevelopmentalHistoryInterventionProtocol) -> None:
        verify_protocol(protocol)
        self._write_immutable(self.protocols / f"{protocol.protocol_id}.json", asdict(protocol))
        payload = self._read_json(self.protocols / f"{protocol.protocol_id}.json")
        for key in ("current_fact_ids", "record_ids", "record_digests", "condition_order", "planned_comparisons", "non_claims",
                    "epistemic_state_digests", "epistemic_evidence_set_digests", "self_model_claim_ids",
                    "self_model_claim_digests"):
            payload[key] = tuple(payload[key])
        loaded = DevelopmentalHistoryInterventionProtocol(**payload)
        verify_protocol(loaded)
        self._persist_objective_schedule_claim(loaded)

    def build_objective_task_plan(self,
            protocol: DevelopmentalHistoryInterventionProtocol,
            task: Any) -> dict[str, Any]:
        """Build the digest-bound task plan without publishing an artifact."""
        verify_protocol(protocol)
        if protocol.schema_version not in OBJECTIVE_SCHEMAS:
            raise DevelopmentalHistoryInterventionError("objective_task_protocol_required")
        protocol_descriptor = protocol.objective_task_descriptor
        if not isinstance(protocol_descriptor, Mapping):
            raise DevelopmentalHistoryInterventionError("objective_task_protocol_binding_invalid")
        try:
            specification = task.specification()
            descriptor = (task.legacy_public_descriptor()
                if protocol.schema_version == LEGACY_OBJECTIVE_SCHEMA
                else task.public_descriptor())
        except (AttributeError, TypeError, ValueError) as exc:
            raise DevelopmentalHistoryInterventionError("objective_task_invalid") from exc
        if (not isinstance(specification, Mapping) or not isinstance(descriptor, Mapping)
                or descriptor != dict(protocol_descriptor)
                or descriptor.get("task_digest") != protocol.objective_task_digest
                or (protocol.schema_version == LEGACY_OBJECTIVE_SCHEMA
                    and _digest(specification) != protocol.objective_task_digest)):
            raise DevelopmentalHistoryInterventionError("objective_task_protocol_binding_invalid")
        suite = specification.get("schema_version") in {
            "sentientos.affine_prediction_task_suite:v2",
            "sentientos.affine_prediction_task_family_suite:v3",
            "sentientos.affine_prediction_task_family_suite:v4",
            "sentientos.affine_prediction_task_family_suite:v5",
            "sentientos.affine_prediction_task_family_suite:v6"}
        selective_family_suite = (specification.get("schema_version")
            in {"sentientos.affine_prediction_task_family_suite:v4",
                "sentientos.affine_prediction_task_family_suite:v5",
                "sentientos.affine_prediction_task_family_suite:v6"})
        calibrated_family_suite = (specification.get("schema_version")
            in {"sentientos.affine_prediction_task_family_suite:v5",
                "sentientos.affine_prediction_task_family_suite:v6"})
        if (calibrated_family_suite
                and protocol.schema_version !=
                    CALIBRATED_OBJECTIVE_SCHEDULED_HISTORY_SCHEMA
                and protocol.schema_version not in {OBJECTIVE_STRATEGY_ARM_SCHEMA,
                    OBJECTIVE_AUTHORITY_POLICY_SCHEMA}):
            raise DevelopmentalHistoryInterventionError(
                "calibrated_family_task_requires_v13_protocol")
        semantic = {"schema_version": ("sentientos.objective_task_plan:v1"
                if protocol.schema_version == LEGACY_OBJECTIVE_SCHEMA
                else "sentientos.objective_task_plan:v2"),
            "protocol_id": protocol.protocol_id, "protocol_digest": protocol.protocol_digest,
            "task": dict(specification), "task_descriptor": dict(descriptor),
            "condition_order": list(protocol.condition_order),
            "rubric": ("calibrated_selective_integer_answer_suite_v1"
                    if calibrated_family_suite else
                "selective_integer_answer_suite_v1" if selective_family_suite else
                "exact_integer_answer_suite_v2" if suite else "exact_integer_answer_v1"),
            "authority": False}
        if protocol.schema_version != LEGACY_OBJECTIVE_SCHEMA:
            semantic["task_commitment_nonce"] = task.commitment_nonce
            public_semantic = {key: value for key, value in semantic.items()
                if key not in {"task", "task_commitment_nonce"}}
        else:
            public_semantic = semantic
        return {**semantic, "plan_digest": _digest(public_semantic)}

    def persist_objective_task_plan(self,
            protocol: DevelopmentalHistoryInterventionProtocol,
            task: Any) -> dict[str, Any]:
        """Durably freeze the independent oracle before the first condition runs."""
        plan = self.build_objective_task_plan(protocol, task)
        path = self.protocols / f"objective-task-plan-{protocol.protocol_id}.json"
        self._write_immutable(path, plan)
        return self.verify_objective_task_plan(protocol)

    def verify_objective_task_plan(self,
            protocol: DevelopmentalHistoryInterventionProtocol) -> dict[str, Any]:
        verify_protocol(protocol)
        if protocol.schema_version not in OBJECTIVE_SCHEMAS:
            raise DevelopmentalHistoryInterventionError("objective_task_protocol_required")
        protocol_descriptor = protocol.objective_task_descriptor
        if not isinstance(protocol_descriptor, Mapping):
            raise DevelopmentalHistoryInterventionError("objective_task_protocol_binding_invalid")
        try:
            value = self._read_json(self.protocols / f"objective-task-plan-{protocol.protocol_id}.json")
        except FileNotFoundError as exc:
            raise DevelopmentalHistoryInterventionError("objective_task_plan_missing") from exc
        expected = {"schema_version", "protocol_id", "protocol_digest", "task",
            "task_descriptor", "condition_order", "rubric", "authority", "plan_digest"}
        if protocol.schema_version != LEGACY_OBJECTIVE_SCHEMA:
            expected.add("task_commitment_nonce")
        if set(value) != expected:
            raise DevelopmentalHistoryInterventionError("objective_task_plan_invalid")
        semantic = dict(value); claimed = semantic.pop("plan_digest")
        if protocol.schema_version != LEGACY_OBJECTIVE_SCHEMA:
            public_semantic = {key: item for key, item in semantic.items()
                if key not in {"task", "task_commitment_nonce"}}
        else:
            public_semantic = semantic
        task = value.get("task")
        suite = isinstance(task, Mapping) and task.get("schema_version") == (
            "sentientos.affine_prediction_task_suite:v2") or (
            isinstance(task, Mapping) and task.get("schema_version") ==
                "sentientos.affine_prediction_task_family_suite:v3") or (
            isinstance(task, Mapping) and task.get("schema_version") ==
                "sentientos.affine_prediction_task_family_suite:v4") or (
            isinstance(task, Mapping) and task.get("schema_version") ==
                "sentientos.affine_prediction_task_family_suite:v5") or (
            isinstance(task, Mapping) and task.get("schema_version") ==
                "sentientos.affine_prediction_task_family_suite:v6")
        selective_family_suite = isinstance(task, Mapping) and task.get("schema_version") == (
            "sentientos.affine_prediction_task_family_suite:v4") or (
            isinstance(task, Mapping) and task.get("schema_version") ==
                "sentientos.affine_prediction_task_family_suite:v5") or (
            isinstance(task, Mapping) and task.get("schema_version") ==
                "sentientos.affine_prediction_task_family_suite:v6")
        calibrated_family_suite = isinstance(task, Mapping) and task.get(
            "schema_version") in {"sentientos.affine_prediction_task_family_suite:v5",
                "sentientos.affine_prediction_task_family_suite:v6"}
        if (calibrated_family_suite and protocol.schema_version !=
                CALIBRATED_OBJECTIVE_SCHEDULED_HISTORY_SCHEMA
                and protocol.schema_version not in {OBJECTIVE_STRATEGY_ARM_SCHEMA,
                    OBJECTIVE_AUTHORITY_POLICY_SCHEMA}):
            raise DevelopmentalHistoryInterventionError(
                "calibrated_family_task_requires_v13_protocol")
        expected_plan_schema = ("sentientos.objective_task_plan:v1"
            if protocol.schema_version == LEGACY_OBJECTIVE_SCHEMA
            else "sentientos.objective_task_plan:v2")
        if (value.get("schema_version") != expected_plan_schema
                or value.get("protocol_id") != protocol.protocol_id
                or value.get("protocol_digest") != protocol.protocol_digest
                or value.get("condition_order") != list(protocol.condition_order)
                or value.get("rubric") != (
                    "calibrated_selective_integer_answer_suite_v1"
                        if calibrated_family_suite else
                    "selective_integer_answer_suite_v1" if selective_family_suite else
                    "exact_integer_answer_suite_v2" if suite
                    else "exact_integer_answer_v1")
                or value.get("authority") is not False
                or claimed != _digest(public_semantic)):
            raise DevelopmentalHistoryInterventionError("objective_task_plan_binding_invalid")
        expected_task_fields = ({"schema_version", "multiplier", "offset", "probe_inputs", "oracle_scope"}
            if suite else {"schema_version", "multiplier", "offset", "probe_input", "oracle_scope"})
        if isinstance(task, Mapping) and task.get("schema_version") in {
                "sentientos.affine_prediction_task_family_suite:v3",
                "sentientos.affine_prediction_task_family_suite:v4",
                "sentientos.affine_prediction_task_family_suite:v5",
                "sentientos.affine_prediction_task_family_suite:v6"}:
            expected_task_fields.update({"task_family_id", "requires_task_family_history"})
        if isinstance(task, Mapping) and task.get("schema_version") == (
                "sentientos.affine_prediction_task_family_suite:v6"):
            expected_task_fields.add("history_task_family_ids")
        if not isinstance(task, Mapping) or set(task) != expected_task_fields:
            raise DevelopmentalHistoryInterventionError("objective_task_plan_invalid")
        from .developmental_model_replacement_experiment import ObjectivePredictionTask
        try:
            if suite:
                probes = task["probe_inputs"]
                if not isinstance(probes, list) or not probes:
                    raise ValueError("objective_probe_suite_invalid")
                reconstructed = ObjectivePredictionTask(task["multiplier"], task["offset"],
                    probes[0], tuple(probes[1:]), task.get("task_family_id"),
                    task.get("requires_task_family_history", False),
                    **({"commitment_nonce": value["task_commitment_nonce"]}
                        if protocol.schema_version != LEGACY_OBJECTIVE_SCHEMA else {}),
                    family_contract_version=(
                        3 if task.get("schema_version") ==
                            "sentientos.affine_prediction_task_family_suite:v3"
                        else 4 if task.get("schema_version") ==
                            "sentientos.affine_prediction_task_family_suite:v4"
                        else 6 if task.get("schema_version") ==
                            "sentientos.affine_prediction_task_family_suite:v6"
                        else 5),
                    history_task_family_ids=tuple(task.get(
                        "history_task_family_ids", ())),
                    history_prompt_identity_policy=(
                        value.get("task_descriptor", {}).get(
                            "history_prompt_identity_policy")
                        if task.get("schema_version") ==
                            "sentientos.affine_prediction_task_family_suite:v6"
                        else None))
            else:
                reconstructed = ObjectivePredictionTask(task["multiplier"], task["offset"], task["probe_input"],
                    **({"commitment_nonce": value["task_commitment_nonce"]}
                        if protocol.schema_version != LEGACY_OBJECTIVE_SCHEMA else {}))
            reconstructed_descriptor = (reconstructed.legacy_public_descriptor()
                if protocol.schema_version == LEGACY_OBJECTIVE_SCHEMA
                else reconstructed.public_descriptor())
            # v4 affine-family task plans used a shorter fixed-mapping question.
            # Preserve that historical descriptor when replaying saved plans;
            # the current prompt may add evidence-handling guidance, but that
            # must not rewrite the descriptor committed by an earlier run.
            if (protocol.schema_version != LEGACY_OBJECTIVE_SCHEMA
                    and task.get("schema_version") ==
                        "sentientos.affine_prediction_task_family_suite:v4"):
                inputs = [task["probe_inputs"][0], *task["probe_inputs"][1:]]
                historical_v4_question = (
                    "This family shares one fixed integer affine mapping: "
                    "output = m * input + b. Verified examples from this mapping: "
                    f"[{{'input': 0, 'output': {task['offset']}}}, "
                    f"{{'input': 1, 'output': "
                    f"{task['multiplier'] + task['offset']}}}]. Predict outputs "
                    f"for inputs {inputs}.")
                if (value.get("task_descriptor", {}).get("question")
                        == historical_v4_question):
                    reconstructed_descriptor["question"] = historical_v4_question
            if (reconstructed.specification() != dict(task)
                    or reconstructed_descriptor != value.get("task_descriptor")
                    or value.get("task_descriptor") != dict(protocol_descriptor)
                    or (protocol.schema_version == LEGACY_OBJECTIVE_SCHEMA
                        and _digest(task) != protocol.objective_task_digest)):
                raise ValueError("objective_task_binding_invalid")
        except (TypeError, ValueError) as exc:
            raise DevelopmentalHistoryInterventionError("objective_task_plan_binding_invalid") from exc
        return value

    def persist_objective_condition_score(self,
            protocol: DevelopmentalHistoryInterventionProtocol,
            plan: Mapping[str, Any], *, condition_id: str,
            observation: Mapping[str, Any], receipt: Any) -> dict[str, Any]:
        """Checkpoint one bounded score while authenticated output bytes are live."""
        verified_plan = self.verify_objective_task_plan(protocol)
        if (condition_id not in CONDITION_ORDER or not isinstance(observation, Mapping)
                or observation.get("condition_id") != condition_id
                or observation.get("observation_id") is None
                or observation.get("observation_digest") is None
                or plan.get("plan_digest") != verified_plan.get("plan_digest")):
            raise DevelopmentalHistoryInterventionError("objective_condition_score_binding_invalid")
        output_text = getattr(receipt, "output_text", None)
        output_digest = getattr(receipt, "output_digest", None)
        receipt_id = getattr(receipt, "receipt_id", None)
        receipt_digest = getattr(receipt, "receipt_digest", None)
        if (receipt_id != observation.get("inference_receipt_id")
                or receipt_digest != observation.get("inference_receipt_digest")):
            raise DevelopmentalHistoryInterventionError("objective_condition_receipt_binding_invalid")
        if output_digest != observation.get("output_digest"):
            raise DevelopmentalHistoryInterventionError("objective_condition_output_binding_invalid")
        output_truncated = getattr(receipt, "output_truncated", False)
        if type(output_truncated) is not bool:
            raise DevelopmentalHistoryInterventionError("objective_condition_truncation_invalid")
        if (output_text is not None and not output_truncated
                and digest_payload({"output": output_text}) != output_digest):
            raise DevelopmentalHistoryInterventionError("objective_condition_output_digest_invalid")
        from .developmental_model_replacement_experiment import _objective_score
        try:
            score = _objective_score(verified_plan, output_text,
                output_digest, output_truncated=output_truncated)
        except (TypeError, ValueError) as exc:
            raise DevelopmentalHistoryInterventionError("objective_condition_score_invalid") from exc
        semantic = {"schema_version": "sentientos.objective_condition_score:v1",
            "protocol_id": protocol.protocol_id, "protocol_digest": protocol.protocol_digest,
            "plan_digest": verified_plan["plan_digest"], "condition_id": condition_id,
            "observation_id": observation["observation_id"],
            "observation_digest": observation["observation_digest"],
            "request_id": observation.get("request_id"),
            "request_digest": observation.get("request_digest"),
            "inference_receipt_id": receipt_id,
            "inference_receipt_digest": receipt_digest,
            "output_digest": output_digest, "output_truncated": output_truncated,
            "score": score}
        digest = _digest(semantic)
        record = {**semantic, "score_record_id": "devscore-" + digest[7:31],
            "score_record_digest": digest}
        observation_key = _digest({"observation_id": observation["observation_id"]})[7:31]
        path = self.protocols / (
            f"objective-score-{protocol.protocol_id}-{condition_id}-{observation_key}.json")
        self._write_immutable(path, record)
        return self.load_objective_condition_score(protocol, condition_id=condition_id,
            observation=observation)

    def load_objective_condition_score(self,
            protocol: DevelopmentalHistoryInterventionProtocol, *, condition_id: str,
            observation: Mapping[str, Any]) -> dict[str, Any]:
        """Revalidate a previously checkpointed score without invoking a model."""
        plan = self.verify_objective_task_plan(protocol)
        if condition_id not in CONDITION_ORDER or not isinstance(observation, Mapping):
            raise DevelopmentalHistoryInterventionError("objective_condition_score_binding_invalid")
        observation_id = observation.get("observation_id")
        if not isinstance(observation_id, str) or not observation_id:
            raise DevelopmentalHistoryInterventionError(
                "objective_condition_score_binding_invalid")
        observation_key = _digest({"observation_id": observation_id})[7:31]
        path = self.protocols / (
            f"objective-score-{protocol.protocol_id}-{condition_id}-{observation_key}.json")
        try:
            value = self._read_json(path)
        except FileNotFoundError as exc:
            # Read legacy protocol-condition checkpoints only when they bind to this exact
            # observation. This preserves old artifacts without reintroducing collisions.
            try:
                legacy = self._read_json(self.protocols /
                    f"objective-score-{protocol.protocol_id}-{condition_id}.json")
            except FileNotFoundError:
                raise DevelopmentalHistoryInterventionError(
                    "objective_condition_score_missing") from exc
            if legacy.get("observation_id") != observation_id:
                raise DevelopmentalHistoryInterventionError(
                    "objective_condition_score_missing") from exc
            value = legacy
        semantic = {key: item for key, item in value.items()
            if key not in {"score_record_id", "score_record_digest"}}
        claimed = value.get("score_record_digest")
        expected_digest = _digest(semantic)
        expected_fields = {"schema_version", "protocol_id", "protocol_digest", "plan_digest",
                "condition_id", "observation_id", "observation_digest", "request_id",
                "request_digest", "inference_receipt_id", "inference_receipt_digest",
                "output_digest", "score", "score_record_id", "score_record_digest"}
        if "output_truncated" in value:
            expected_fields.add("output_truncated")
        output_truncated = value.get("output_truncated", False)
        verified_receipt = None
        if callable(self._invocation_verifier):
            verified_receipt = self._invocation_verifier(observation)
        if (type(output_truncated) is not bool
                or (isinstance(verified_receipt, Mapping)
                    and verified_receipt.get("output_truncated") is not output_truncated)
                or (observation.get("serving_session_id") is not None
                    and not isinstance(verified_receipt, Mapping))
                or (output_truncated and not isinstance(verified_receipt, Mapping))
                or set(value) != expected_fields
                or value.get("schema_version") != "sentientos.objective_condition_score:v1"
                or value.get("protocol_id") != protocol.protocol_id
                or value.get("protocol_digest") != protocol.protocol_digest
                or value.get("plan_digest") != plan.get("plan_digest")
                or value.get("condition_id") != condition_id
                or value.get("observation_id") != observation.get("observation_id")
                or value.get("observation_digest") != observation.get("observation_digest")
                or value.get("request_id") != observation.get("request_id")
                or value.get("request_digest") != observation.get("request_digest")
                or value.get("inference_receipt_id") != observation.get("inference_receipt_id")
                or value.get("inference_receipt_digest") != observation.get("inference_receipt_digest")
                or value.get("output_digest") != observation.get("output_digest")
                or claimed != expected_digest
                or value.get("score_record_id") != "devscore-" + expected_digest[7:31]):
            raise DevelopmentalHistoryInterventionError("objective_condition_score_binding_invalid")
        score = value.get("score")
        if not isinstance(score, Mapping):
            raise DevelopmentalHistoryInterventionError("objective_condition_score_invalid")
        from .developmental_model_replacement_experiment import _verify_objective_score
        try:
            _verify_objective_score(plan, score, value["output_digest"],
                output_truncated=output_truncated)
        except (KeyError, TypeError, ValueError) as exc:
            raise DevelopmentalHistoryInterventionError("objective_condition_score_invalid") from exc
        return value

    def persist_strategy_inclusion_protocol(
            self, protocol: Mapping[str, Any]) -> dict[str, Any]:
        """Store a digest-verified strategy pair before either arm is invoked."""
        if not isinstance(protocol, Mapping):
            raise DevelopmentalHistoryInterventionError(
                "strategy_intervention_protocol_invalid")
        try:
            from work.strategy_inclusion_intervention import (
                validate_strategy_inclusion_protocol)
            validate_strategy_inclusion_protocol(protocol=protocol)
        except (ImportError, TypeError, ValueError) as exc:
            raise DevelopmentalHistoryInterventionError(
                "strategy_intervention_protocol_invalid") from exc
        semantic = {key: value for key, value in protocol.items()
            if key != "protocol_digest"}
        claimed = protocol.get("protocol_digest")
        if (protocol.get("schema_version") not in {
                "sentientos.strategy_inclusion_intervention_protocol:v2",
                "sentientos.strategy_inclusion_intervention_protocol:v3",
                "sentientos.strategy_inclusion_intervention_protocol:v4",
                "sentientos.strategy_inclusion_intervention_protocol:v5",
                "sentientos.strategy_inclusion_intervention_protocol:v6"}
                or protocol.get("exact_pair_verified") is not True
                or protocol.get("inference_performed") is not False
                or protocol.get("learning_established") is not False
                or protocol.get("authority") is not False
                or protocol.get("conditions") not in (
                    ["strategy_included", "strategy_omitted"],
                    ["strategy_omitted", "strategy_included"])
                or not _valid_sha256_digest(claimed)
                or _strategy_intervention_digest(semantic) != claimed):
            raise DevelopmentalHistoryInterventionError(
                "strategy_intervention_protocol_invalid")
        protocol_id = "strategy-inclusion-protocol-" + claimed[7:31]
        path = self.protocols / f"{protocol_id}.json"
        self._write_immutable(path, dict(protocol))
        return self.load_strategy_inclusion_protocol(claimed)

    def load_strategy_inclusion_protocol(self,
            protocol_digest: str) -> dict[str, Any]:
        """Reload and revalidate a frozen pair without invoking a model."""
        if not _valid_sha256_digest(protocol_digest):
            raise DevelopmentalHistoryInterventionError(
                "strategy_intervention_protocol_digest_invalid")
        protocol_id = "strategy-inclusion-protocol-" + protocol_digest[7:31]
        try:
            value = self._read_json(self.protocols / f"{protocol_id}.json")
        except FileNotFoundError as exc:
            raise DevelopmentalHistoryInterventionError(
                "strategy_intervention_protocol_missing") from exc
        semantic = {key: item for key, item in value.items()
            if key != "protocol_digest"}
        try:
            from work.strategy_inclusion_intervention import (
                validate_strategy_inclusion_protocol)
            validate_strategy_inclusion_protocol(protocol=value)
        except (ImportError, TypeError, ValueError) as exc:
            raise DevelopmentalHistoryInterventionError(
                "strategy_intervention_protocol_binding_invalid") from exc
        if (value.get("schema_version") not in {
                "sentientos.strategy_inclusion_intervention_protocol:v2",
                "sentientos.strategy_inclusion_intervention_protocol:v3",
                "sentientos.strategy_inclusion_intervention_protocol:v4",
                "sentientos.strategy_inclusion_intervention_protocol:v5",
                "sentientos.strategy_inclusion_intervention_protocol:v6"}
                or value.get("protocol_digest") != protocol_digest
                or _strategy_intervention_digest(semantic) != protocol_digest
                or value.get("exact_pair_verified") is not True
                or value.get("inference_performed") is not False
                or value.get("learning_established") is not False
                or value.get("authority") is not False):
            raise DevelopmentalHistoryInterventionError(
                "strategy_intervention_protocol_binding_invalid")
        return value

    @staticmethod
    def _strategy_inclusion_arm_path(protocol_digest: str, arm: str,
            *, result: bool) -> Path:
        prefix = "strategy-inclusion-arm-result-" if result else (
            "strategy-inclusion-arm-claim-")
        return Path(prefix + protocol_digest[7:31] + "-" + arm + ".json")

    def claim_strategy_inclusion_arm(self, *, protocol_digest: str,
            arm: str) -> dict[str, Any]:
        """Durably claim one arm exactly once before its invocation starts."""
        protocol = self.load_strategy_inclusion_protocol(protocol_digest)
        if arm not in protocol.get("conditions", ()):
            raise DevelopmentalHistoryInterventionError(
                "strategy_intervention_arm_invalid")
        semantic = {"schema_version":
                "sentientos.strategy_inclusion_arm_execution_claim:v1",
            "protocol_digest": protocol_digest, "arm": arm,
            "invoke_once": True, "authority": False}
        claim_digest = _strategy_intervention_digest(semantic)
        claim = {**semantic, "claim_digest": claim_digest}
        path = self.runs / self._strategy_inclusion_arm_path(
            protocol_digest, arm, result=False)
        try:
            created = self._write_immutable(path, claim)
        except DevelopmentalHistoryInterventionError as exc:
            if str(exc) == "artifact_identity_collision":
                raise DevelopmentalHistoryInterventionError(
                    "strategy_intervention_arm_already_claimed") from exc
            raise
        if not created:
            raise DevelopmentalHistoryInterventionError(
                "strategy_intervention_arm_already_claimed")
        return claim

    def strategy_inclusion_arm_execution_state(self, *, protocol_digest: str,
            arm: str) -> dict[str, Any]:
        """Read the durable claim/result state; never infer a missing receipt."""
        protocol = self.load_strategy_inclusion_protocol(protocol_digest)
        if arm not in protocol.get("conditions", ()):
            raise DevelopmentalHistoryInterventionError(
                "strategy_intervention_arm_invalid")
        claim_path = self.runs / self._strategy_inclusion_arm_path(
            protocol_digest, arm, result=False)
        result_path = self.runs / self._strategy_inclusion_arm_path(
            protocol_digest, arm, result=True)
        try:
            claim = self._read_json(claim_path)
        except FileNotFoundError:
            return {"status": "not_started", "protocol_digest": protocol_digest,
                "arm": arm}
        claim_semantic = {key: value for key, value in claim.items()
            if key != "claim_digest"}
        if (claim.get("schema_version") !=
                "sentientos.strategy_inclusion_arm_execution_claim:v1"
                or claim.get("protocol_digest") != protocol_digest
                or claim.get("arm") != arm or claim.get("invoke_once") is not True
                or claim.get("authority") is not False
                or claim.get("claim_digest") !=
                    _strategy_intervention_digest(claim_semantic)):
            raise DevelopmentalHistoryInterventionError(
                "strategy_intervention_arm_claim_invalid")
        try:
            result = self._read_json(result_path)
        except FileNotFoundError:
            return {"status": "claimed_without_receipt", "claim": claim,
                "protocol_digest": protocol_digest, "arm": arm}
        result_semantic = {key: value for key, value in result.items()
            if key != "result_digest"}
        receipt = result.get("receipt_binding")
        prompt_bindings = protocol.get("invocation_prompt_digests")
        preview_bindings = protocol.get("preview_request_digests")
        if (result.get("schema_version") !=
                "sentientos.strategy_inclusion_arm_execution_result:v1"
                or result.get("protocol_digest") != protocol_digest
                or result.get("arm") != arm
                or not isinstance(receipt, Mapping)
                or result.get("result_digest") !=
                    _strategy_intervention_digest(result_semantic)
                or set(receipt) != {"receipt_id", "receipt_digest", "request_id",
                    "request_digest", "preview_request_digest", "output_digest",
                    "prompt_digest"}
                or not isinstance(receipt.get("receipt_id"), str)
                or not receipt["receipt_id"]
                or not isinstance(receipt.get("request_id"), str)
                or not receipt["request_id"]
                or not isinstance(prompt_bindings, Mapping)
                or receipt.get("prompt_digest") != str(
                    prompt_bindings.get(arm, "")).removeprefix("sha256:")
                or not isinstance(preview_bindings, Mapping)
                or receipt.get("preview_request_digest") !=
                    preview_bindings.get(arm)
                or not _valid_sha256_digest(receipt.get("preview_request_digest"))
                or any(not _valid_raw_sha256_digest(receipt.get(field)) for field in (
                    "receipt_digest", "request_digest", "output_digest",
                    "prompt_digest"))):
            raise DevelopmentalHistoryInterventionError(
                "strategy_intervention_arm_result_invalid")
        return {"status": "completed", "claim": claim, "result": result,
            "protocol_digest": protocol_digest, "arm": arm}

    def complete_strategy_inclusion_arm(self, *, protocol_digest: str,
            arm: str, receipt_binding: Mapping[str, Any]) -> dict[str, Any]:
        """Bind the already-persisted governed invocation receipt to its arm."""
        state = self.strategy_inclusion_arm_execution_state(
            protocol_digest=protocol_digest, arm=arm)
        if state.get("status") not in {"claimed_without_receipt", "completed"}:
            raise DevelopmentalHistoryInterventionError(
                "strategy_intervention_arm_claim_required")
        if not isinstance(receipt_binding, Mapping):
            raise DevelopmentalHistoryInterventionError(
                "strategy_intervention_arm_receipt_binding_invalid")
        normalized = dict(receipt_binding)
        if (set(normalized) != {"receipt_id", "receipt_digest", "request_id",
                "request_digest", "preview_request_digest", "output_digest",
                "prompt_digest"}
                or not isinstance(normalized.get("receipt_id"), str)
                or re.fullmatch(r"lmrec-[0-9a-f]{24}",
                    normalized["receipt_id"]) is None
                or not isinstance(normalized.get("request_id"), str)
                or re.fullmatch(r"lmreq-[0-9a-f]{24}",
                    normalized["request_id"]) is None
                or not _valid_sha256_digest(normalized.get(
                    "preview_request_digest"))
                or any(not _valid_raw_sha256_digest(normalized.get(field))
                    for field in ("receipt_digest", "request_digest",
                        "output_digest", "prompt_digest"))):
            raise DevelopmentalHistoryInterventionError(
                "strategy_intervention_arm_receipt_binding_invalid")
        protocol = self.load_strategy_inclusion_protocol(protocol_digest)
        prompt_bindings = protocol.get("invocation_prompt_digests")
        preview_bindings = protocol.get("preview_request_digests")
        if (not isinstance(prompt_bindings, Mapping)
                or not isinstance(preview_bindings, Mapping)
                or normalized.get("prompt_digest") != str(
                    prompt_bindings.get(arm, "")).removeprefix("sha256:")
                or normalized.get("preview_request_digest") !=
                    preview_bindings.get(arm)):
            raise DevelopmentalHistoryInterventionError(
                "strategy_intervention_arm_receipt_binding_mismatch")
        semantic = {"schema_version":
                "sentientos.strategy_inclusion_arm_execution_result:v1",
            "protocol_digest": protocol_digest, "arm": arm,
            "receipt_binding": normalized, "authority": False}
        result = {**semantic,
            "result_digest": _strategy_intervention_digest(semantic)}
        self._write_immutable(self.runs / self._strategy_inclusion_arm_path(
            protocol_digest, arm, result=True), result)
        return self.strategy_inclusion_arm_execution_state(
            protocol_digest=protocol_digest, arm=arm)

    def persist_strategy_inclusion_score(self, *, protocol_digest: str,
            score: Mapping[str, Any], answer_key: Mapping[str, int],
            invocation_receipts_by_arm: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
        """Verify both delivered receipts, then checkpoint the answer-free score."""
        protocol = self.load_strategy_inclusion_protocol(protocol_digest)
        if not isinstance(score, Mapping):
            raise DevelopmentalHistoryInterventionError(
                "strategy_intervention_score_invalid")
        try:
            from work.strategy_inclusion_intervention import (
                score_verified_strategy_inclusion_pair)
            verified_score = score_verified_strategy_inclusion_pair(
                protocol=protocol, answer_key=answer_key,
                invocation_receipts_by_arm=invocation_receipts_by_arm)
        except (ImportError, TypeError, ValueError) as exc:
            raise DevelopmentalHistoryInterventionError(
                "strategy_intervention_receipt_verification_failed") from exc
        if dict(score) != verified_score:
            raise DevelopmentalHistoryInterventionError(
                "strategy_intervention_score_recomputation_mismatch")
        semantic = {key: value for key, value in score.items()
            if key != "score_digest"}
        score_digest = score.get("score_digest")
        receipt_bindings = score.get("invocation_receipt_bindings")
        arms = {"strategy_included", "strategy_omitted"}
        if (score.get("schema_version") not in {
                "sentientos.strategy_inclusion_intervention_score:v1",
                "sentientos.strategy_inclusion_intervention_score:v2"}
                or score.get("protocol_digest") != protocol_digest
                or not _valid_sha256_digest(score_digest)
                or _strategy_intervention_digest(semantic) != score_digest
                or score.get("paired_delivery_verified") is not True
                or score.get("learning_established") is not False
                or score.get("authority") is not False
                or not isinstance(receipt_bindings, Mapping)
                or set(receipt_bindings) != arms
                or any(not isinstance(receipt_bindings[arm], Mapping)
                    or not _valid_raw_sha256_digest(receipt_bindings[arm].get(
                        "receipt_digest")) for arm in arms)):
            raise DevelopmentalHistoryInterventionError(
                "strategy_intervention_score_invalid")
        for arm in arms:
            arm_state = self.strategy_inclusion_arm_execution_state(
                protocol_digest=protocol_digest, arm=arm)
            if (arm_state.get("status") != "completed"
                    or arm_state.get("result", {}).get("receipt_binding")
                        != dict(receipt_bindings[arm])):
                raise DevelopmentalHistoryInterventionError(
                    "strategy_intervention_score_arm_receipt_mismatch")
        score_id = "strategy-inclusion-score-" + protocol_digest[7:19] + "-" + score_digest[7:19]
        path = self.runs / f"{score_id}.json"
        self._write_immutable(path, dict(score))
        return self.load_strategy_inclusion_score(protocol_digest=protocol_digest,
            score_digest=score_digest)

    def load_strategy_inclusion_score(self, *, protocol_digest: str,
            score_digest: str) -> dict[str, Any]:
        """Recheck stored score and both invocation receipt bindings."""
        protocol = self.load_strategy_inclusion_protocol(protocol_digest)
        if not _valid_sha256_digest(score_digest):
            raise DevelopmentalHistoryInterventionError(
                "strategy_intervention_score_digest_invalid")
        score_id = "strategy-inclusion-score-" + protocol_digest[7:19] + "-" + score_digest[7:19]
        try:
            value = self._read_json(self.runs / f"{score_id}.json")
        except FileNotFoundError as exc:
            raise DevelopmentalHistoryInterventionError(
                "strategy_intervention_score_missing") from exc
        semantic = {key: item for key, item in value.items()
            if key != "score_digest"}
        receipt_bindings = value.get("invocation_receipt_bindings")
        if (value.get("schema_version") not in {
                "sentientos.strategy_inclusion_intervention_score:v1",
                "sentientos.strategy_inclusion_intervention_score:v2"}
                or value.get("protocol_digest") != protocol_digest
                or value.get("score_digest") != score_digest
                or _strategy_intervention_digest(semantic) != score_digest
                or value.get("paired_delivery_verified") is not True
                or value.get("learning_established") is not False
                or value.get("authority") is not False
                or not isinstance(receipt_bindings, Mapping)
                or set(receipt_bindings) != {
                    "strategy_included", "strategy_omitted"}
                or any(not isinstance(receipt_bindings[arm], Mapping)
                    or not _valid_raw_sha256_digest(receipt_bindings[arm].get(
                        "receipt_digest")) for arm in receipt_bindings)):
            raise DevelopmentalHistoryInterventionError(
                "strategy_intervention_score_binding_invalid")
        for arm in receipt_bindings:
            arm_state = self.strategy_inclusion_arm_execution_state(
                protocol_digest=protocol_digest, arm=arm)
            if (arm_state.get("status") != "completed"
                    or arm_state.get("result", {}).get("receipt_binding")
                        != dict(receipt_bindings[arm])):
                raise DevelopmentalHistoryInterventionError(
                    "strategy_intervention_score_arm_receipt_mismatch")
        return value

    def load_protocol(self, protocol_id: str) -> DevelopmentalHistoryInterventionProtocol:
        if (not isinstance(protocol_id, str) or not protocol_id.startswith("devexp-protocol-")
                or len(protocol_id) != len("devexp-protocol-") + 24
                or any(character not in "0123456789abcdef" for character in protocol_id[-24:])):
            raise DevelopmentalHistoryInterventionError("protocol_identity_invalid")
        try:
            payload = self._read_json(self.protocols / f"{protocol_id}.json")
            for key in ("current_fact_ids", "record_ids", "record_digests", "condition_order",
                        "planned_comparisons", "non_claims", "epistemic_state_digests",
                        "epistemic_evidence_set_digests", "self_model_claim_ids", "self_model_claim_digests"):
                payload[key] = tuple(payload.get(key, ()))
            protocol = DevelopmentalHistoryInterventionProtocol(**payload)
            verify_protocol(protocol)
        except (FileNotFoundError, KeyError, TypeError, ValueError) as exc:
            raise DevelopmentalHistoryInterventionError("protocol_artifact_invalid") from exc
        if protocol.protocol_id != protocol_id:
            raise DevelopmentalHistoryInterventionError("protocol_identity_mismatch")
        if protocol.schema_version in {
                BALANCED_OBJECTIVE_SCHEDULED_HISTORY_SELECTION_SCHEMA,
                CALIBRATED_OBJECTIVE_SCHEDULED_HISTORY_SCHEMA}:
            self.verify_objective_history_schedule(protocol)
        return protocol

    def persist_run(self, payload: Mapping[str, Any]) -> str:
        semantic = dict(payload); semantic["schema_version"] = RUN_SCHEMA
        digest = _digest(semantic); run_id = "devexp-run-" + digest[7:31]
        self._write_immutable(self.runs / f"{run_id}.json", {**semantic, "run_id": run_id, "run_digest": digest})
        return run_id

    @staticmethod
    def _verify_retrieval_comparison(value: Mapping[str, Any]) -> None:
        # Local import avoids a module cycle: resident cognition uses this store
        # for its existing intervention protocols.
        from .resident_developmental_cognition import ResidentDevelopmentalCognition
        try:
            ResidentDevelopmentalCognition.verify_ordinary_chat_developmental_history_retrieval_comparison(
                value)
        except (TypeError, ValueError) as exc:
            raise DevelopmentalHistoryInterventionError(
                "retrieval_comparison_invalid") from exc

    def persist_retrieval_comparison(self, value: Mapping[str, Any]) -> str:
        """Persist one verified retrieval-only comparison as an immutable artifact."""
        try:
            comparison = json.loads(json.dumps(dict(value), sort_keys=True,
                ensure_ascii=False, allow_nan=False))
        except (TypeError, ValueError) as exc:
            raise DevelopmentalHistoryInterventionError(
                "retrieval_comparison_invalid") from exc
        self._verify_retrieval_comparison(comparison)
        body = {"schema_version": RETRIEVAL_COMPARISON_ARTIFACT_SCHEMA,
            "comparison": comparison}
        digest = _digest(body)
        artifact_id = RETRIEVAL_COMPARISON_ID_PREFIX + digest[7:31]
        self._write_immutable(self.runs / f"{artifact_id}.json",
            {**body, "artifact_id": artifact_id, "artifact_digest": digest})
        return artifact_id

    def load_retrieval_comparison(self, artifact_id: str) -> dict[str, Any]:
        if (not isinstance(artifact_id, str)
                or re.fullmatch(re.escape(RETRIEVAL_COMPARISON_ID_PREFIX)
                    + r"[0-9a-f]{24}", artifact_id) is None):
            raise DevelopmentalHistoryInterventionError(
                "retrieval_comparison_identity_invalid")
        try:
            value = self._read_json(self.runs / f"{artifact_id}.json")
        except FileNotFoundError as exc:
            raise DevelopmentalHistoryInterventionError(
                "retrieval_comparison_missing") from exc
        body = {key: item for key, item in value.items()
            if key not in {"artifact_id", "artifact_digest"}}
        if (set(value) != {"schema_version", "comparison", "artifact_id",
                "artifact_digest"}
                or value.get("schema_version") != RETRIEVAL_COMPARISON_ARTIFACT_SCHEMA
                or value.get("artifact_id") != artifact_id
                or value.get("artifact_digest") != _digest(body)
                or artifact_id != RETRIEVAL_COMPARISON_ID_PREFIX
                    + str(value.get("artifact_digest", ""))[7:31]
                or not isinstance(value.get("comparison"), Mapping)):
            raise DevelopmentalHistoryInterventionError(
                "retrieval_comparison_digest_mismatch")
        self._verify_retrieval_comparison(value["comparison"])
        return value

    def persist_retrieval_corpus_freeze(self, *, owner: Any) -> str:
        """Capture an immutable durable-history inventory before query construction."""
        getter = getattr(owner,
            "ordinary_chat_developmental_history_corpus_manifest", None)
        if not callable(getter):
            raise DevelopmentalHistoryInterventionError(
                "retrieval_corpus_freeze_owner_unavailable")
        manifest = getter()
        if not isinstance(manifest, Mapping):
            raise DevelopmentalHistoryInterventionError(
                "retrieval_corpus_freeze_manifest_invalid")
        from .semantic_history_retrieval_evaluation import (
            _validate_corpus_manifest)
        try:
            manifest_digest, _ = _validate_corpus_manifest(manifest,
                history_state_digest=manifest.get("history_state_digest"))
        except (TypeError, ValueError) as exc:
            raise DevelopmentalHistoryInterventionError(
                "retrieval_corpus_freeze_manifest_invalid") from exc
        config = getattr(owner, "config", None)
        model_id = getattr(config, "semantic_history_model_id", None)
        revision = getattr(config, "semantic_history_model_revision", None)
        if ((model_id is None) != (revision is None)
                or (model_id is not None and (not isinstance(model_id, str)
                    or not model_id or len(model_id) > 256
                    or not isinstance(revision, str)
                    or re.fullmatch(r"[0-9a-f]{40}", revision) is None))):
            raise DevelopmentalHistoryInterventionError(
                "retrieval_corpus_freeze_embedder_binding_invalid")
        body = {"schema_version": RETRIEVAL_CORPUS_FREEZE_SCHEMA,
            "history_state_digest": manifest["history_state_digest"],
            "corpus_manifest": dict(manifest),
            "corpus_manifest_digest": manifest_digest,
            "configured_semantic_embedder_model_id": model_id,
            "configured_semantic_embedder_revision": revision}
        digest = _digest(body)
        freeze_id = RETRIEVAL_CORPUS_FREEZE_ID_PREFIX + digest[7:31]
        self._write_immutable(self.runs / f"{freeze_id}.json",
            {**body, "freeze_id": freeze_id, "freeze_digest": digest})
        return freeze_id

    def load_retrieval_corpus_freeze(self, freeze_id: str) -> dict[str, Any]:
        if (not isinstance(freeze_id, str)
                or re.fullmatch(re.escape(RETRIEVAL_CORPUS_FREEZE_ID_PREFIX)
                    + r"[0-9a-f]{24}", freeze_id) is None):
            raise DevelopmentalHistoryInterventionError(
                "retrieval_corpus_freeze_identity_invalid")
        try:
            value = self._read_json(self.runs / f"{freeze_id}.json")
        except FileNotFoundError as exc:
            raise DevelopmentalHistoryInterventionError(
                "retrieval_corpus_freeze_missing") from exc
        body = {key: item for key, item in value.items()
            if key not in {"freeze_id", "freeze_digest"}}
        expected = {"schema_version", "history_state_digest", "corpus_manifest",
            "corpus_manifest_digest", "configured_semantic_embedder_model_id",
            "configured_semantic_embedder_revision", "freeze_id", "freeze_digest"}
        if (set(value) != expected
                or value.get("schema_version") != RETRIEVAL_CORPUS_FREEZE_SCHEMA
                or value.get("freeze_id") != freeze_id
                or value.get("freeze_digest") != _digest(body)
                or freeze_id != RETRIEVAL_CORPUS_FREEZE_ID_PREFIX
                    + str(value.get("freeze_digest", ""))[7:31]
                or ((value.get("configured_semantic_embedder_model_id") is None)
                    != (value.get("configured_semantic_embedder_revision") is None))
                or (value.get("configured_semantic_embedder_model_id") is not None
                    and (not isinstance(value["configured_semantic_embedder_model_id"], str)
                        or not value["configured_semantic_embedder_model_id"]
                        or len(value["configured_semantic_embedder_model_id"]) > 256
                        or not isinstance(value["configured_semantic_embedder_revision"], str)
                        or re.fullmatch(r"[0-9a-f]{40}",
                            value["configured_semantic_embedder_revision"]) is None))):
            raise DevelopmentalHistoryInterventionError(
                "retrieval_corpus_freeze_digest_mismatch")
        from .semantic_history_retrieval_evaluation import (
            _validate_corpus_manifest)
        try:
            manifest_digest, _ = _validate_corpus_manifest(
                value.get("corpus_manifest"),
                history_state_digest=value.get("history_state_digest"))
        except (TypeError, ValueError) as exc:
            raise DevelopmentalHistoryInterventionError(
                "retrieval_corpus_freeze_manifest_invalid") from exc
        if manifest_digest != value.get("corpus_manifest_digest"):
            raise DevelopmentalHistoryInterventionError(
                "retrieval_corpus_freeze_manifest_mismatch")
        return value

    def persist_retrieval_query_set(self, *, corpus_freeze_id: str,
            questions: Sequence[str], strata: Sequence[str],
            source_experience_digests: Sequence[str] | None = None,
            source_experience_record_ids: Sequence[str] | None = None,
            max_input_chars: int = 8000,
            target_model_identity: Mapping[str, Any] | None = None) -> str:
        """Seal distinct preregistered queries against an existing corpus freeze."""
        freeze = self.load_retrieval_corpus_freeze(corpus_freeze_id)
        if (target_model_identity is not None
                and (not isinstance(target_model_identity, Mapping)
                    or not target_model_identity)):
            raise DevelopmentalHistoryInterventionError(
                "retrieval_query_set_target_identity_invalid")
        try:
            identity_snapshot = (None if target_model_identity is None else
                json.loads(json.dumps(dict(target_model_identity), sort_keys=True,
                    ensure_ascii=False, allow_nan=False)))
        except (TypeError, ValueError) as exc:
            raise DevelopmentalHistoryInterventionError(
                "retrieval_query_set_target_identity_invalid") from exc
        if (type(max_input_chars) is not int
                or not 128 <= max_input_chars
                    <= MAX_RETRIEVAL_COMPARISON_INPUT_CHARS
                or not isinstance(questions, (list, tuple))
                or not MIN_RETRIEVAL_COMPARISON_QUERIES <= len(questions)
                    <= MAX_RETRIEVAL_COMPARISON_QUERIES
                or len(questions) % 3 != 0
                or any(not isinstance(question, str) or not question.strip()
                    or len(question) > 1200 for question in questions)
                or not isinstance(strata, (list, tuple))
                or len(strata) != len(questions)
                or ((source_experience_digests is None)
                    == (source_experience_record_ids is None))
                or (source_experience_digests is not None and (
                    not isinstance(source_experience_digests, (list, tuple))
                    or len(source_experience_digests) != len(questions)
                    or any(not isinstance(item, str)
                        or re.fullmatch(r"[0-9a-f]{64}", item) is None
                        for item in source_experience_digests)
                    or len(set(source_experience_digests)) != len(questions)))
                or (source_experience_record_ids is not None and (
                    not isinstance(source_experience_record_ids, (list, tuple))
                    or len(source_experience_record_ids) != len(questions)
                    or any(not isinstance(item, str)
                        or re.fullmatch(r"devrec-[0-9a-f]{24}", item) is None
                        for item in source_experience_record_ids)
                    or len(set(source_experience_record_ids)) != len(questions)))
                or any(stratum not in RETRIEVAL_QUERY_STRATA
                    for stratum in strata)
                or len(set(strata)) != len(RETRIEVAL_QUERY_STRATA)
                or any(strata.count(stratum) != len(questions) // 3
                    for stratum in RETRIEVAL_QUERY_STRATA)
                or len({digest_payload({"question": question})
                    for question in questions}) != len(questions)):
            raise DevelopmentalHistoryInterventionError(
                "retrieval_query_set_invalid")
        from .semantic_history_retrieval_evaluation import (
            _validate_corpus_manifest)
        try:
            _, manifest_records = _validate_corpus_manifest(
                freeze["corpus_manifest"],
                history_state_digest=freeze["history_state_digest"])
        except (TypeError, ValueError) as exc:
            raise DevelopmentalHistoryInterventionError(
                "retrieval_query_set_corpus_manifest_invalid") from exc
        if source_experience_record_ids is not None:
            if any(record_id not in manifest_records
                    for record_id in source_experience_record_ids):
                raise DevelopmentalHistoryInterventionError(
                    "retrieval_query_set_source_experience_record_missing")
            from .semantic_history_retrieval_evaluation import (
                retrieval_source_experience_record_unit_digest)
            source_experience_digests = [
                retrieval_source_experience_record_unit_digest(
                    record_id=record_id,
                    record_digest=manifest_records[record_id])
                for record_id in source_experience_record_ids]
        assert source_experience_digests is not None
        evaluation_protocol = (RETRIEVAL_EVALUATION_PROTOCOL_V12
            if source_experience_record_ids is not None
            else RETRIEVAL_EVALUATION_PROTOCOL_V11)
        body = {"schema_version": (RETRIEVAL_QUERY_SET_SCHEMA
                if source_experience_record_ids is not None else
                PREVIOUS_RETRIEVAL_QUERY_SET_SCHEMA),
            "corpus_freeze_id": corpus_freeze_id,
            "corpus_freeze_digest": freeze["freeze_digest"],
            "history_state_digest": freeze["history_state_digest"],
            "configured_semantic_embedder_model_id":
                freeze["configured_semantic_embedder_model_id"],
            "configured_semantic_embedder_revision":
                freeze["configured_semantic_embedder_revision"],
            "max_input_chars": max_input_chars,
            "target_model_identity": identity_snapshot,
            "target_model_identity_digest": (None if identity_snapshot is None
                else digest_payload(identity_snapshot)),
            "question_count": len(questions),
            "questions": list(questions),
            "strata": list(strata),
            "source_experience_digests": list(source_experience_digests),
            "evaluation_protocol": dict(evaluation_protocol),
            "question_digests": [digest_payload({"question": question})
                for question in questions]}
        if source_experience_record_ids is not None:
            body["source_experience_record_ids"] = list(
                source_experience_record_ids)
        digest = _digest(body)
        query_set_id = RETRIEVAL_QUERY_SET_ID_PREFIX + digest[7:31]
        self._write_immutable(self.runs / f"{query_set_id}.json",
            {**body, "query_set_id": query_set_id,
                "query_set_digest": digest})
        return query_set_id

    def load_retrieval_query_set(self, query_set_id: str) -> dict[str, Any]:
        if (not isinstance(query_set_id, str)
                or re.fullmatch(re.escape(RETRIEVAL_QUERY_SET_ID_PREFIX)
                    + r"[0-9a-f]{24}", query_set_id) is None):
            raise DevelopmentalHistoryInterventionError(
                "retrieval_query_set_identity_invalid")
        try:
            value = self._read_json(self.runs / f"{query_set_id}.json")
        except FileNotFoundError as exc:
            raise DevelopmentalHistoryInterventionError(
                "retrieval_query_set_missing") from exc
        body = {key: item for key, item in value.items()
            if key not in {"query_set_id", "query_set_digest"}}
        base_expected = {"schema_version", "corpus_freeze_id", "corpus_freeze_digest",
            "history_state_digest", "configured_semantic_embedder_model_id",
            "configured_semantic_embedder_revision", "max_input_chars",
            "target_model_identity", "target_model_identity_digest",
            "question_count", "questions", "strata",
            "question_digests", "evaluation_protocol", "query_set_id",
            "query_set_digest"}
        query_set_schema = value.get("schema_version")
        has_preregistered_units = (isinstance(query_set_schema, str)
            and query_set_schema in {PREVIOUS_RETRIEVAL_QUERY_SET_SCHEMA,
                RETRIEVAL_QUERY_SET_SCHEMA})
        has_source_record_bindings = (
            query_set_schema == RETRIEVAL_QUERY_SET_SCHEMA)
        expected = (base_expected | {"source_experience_digests"}
            if has_preregistered_units else base_expected)
        if has_source_record_bindings:
            expected.add("source_experience_record_ids")
        source_digests = value.get("source_experience_digests")
        source_record_ids = value.get("source_experience_record_ids")
        if (set(value) != expected
                or not isinstance(query_set_schema, str)
                or query_set_schema not in {RETRIEVAL_QUERY_SET_SCHEMA,
                    PREVIOUS_RETRIEVAL_QUERY_SET_SCHEMA,
                    LEGACY_RETRIEVAL_QUERY_SET_SCHEMA}
                or value.get("query_set_id") != query_set_id
                or value.get("query_set_digest") != _digest(body)
                or query_set_id != RETRIEVAL_QUERY_SET_ID_PREFIX
                    + str(value.get("query_set_digest", ""))[7:31]
                or type(value.get("question_count")) is not int
                or not MIN_RETRIEVAL_COMPARISON_QUERIES <= value["question_count"]
                    <= MAX_RETRIEVAL_COMPARISON_QUERIES
                or value["question_count"] % 3 != 0
                or not isinstance(value.get("question_digests"), list)
                or len(value["question_digests"]) != value["question_count"]
                or any(not isinstance(item, str)
                    or re.fullmatch(r"[0-9a-f]{64}", item) is None
                    for item in value["question_digests"])
                or len(set(value["question_digests"])) != value["question_count"]
                or (has_preregistered_units and (
                    not isinstance(source_digests, list)
                    or len(source_digests) != value["question_count"]
                    or any(not isinstance(item, str)
                        or re.fullmatch(r"[0-9a-f]{64}", item) is None
                        for item in source_digests)
                    or len(set(source_digests)) != value["question_count"]))
                or (has_source_record_bindings and (
                    not isinstance(source_record_ids, list)
                    or len(source_record_ids) != value["question_count"]
                    or any(not isinstance(item, str)
                        or re.fullmatch(r"devrec-[0-9a-f]{24}", item) is None
                        for item in source_record_ids)
                    or len(set(source_record_ids)) != value["question_count"]))
                or not _valid_sha256_digest(value.get("history_state_digest"))
                or ((value.get("configured_semantic_embedder_model_id") is None)
                    != (value.get("configured_semantic_embedder_revision") is None))
                or (value.get("configured_semantic_embedder_model_id") is not None
                    and (not isinstance(value["configured_semantic_embedder_model_id"], str)
                        or not value["configured_semantic_embedder_model_id"]
                        or len(value["configured_semantic_embedder_model_id"]) > 256
                        or not isinstance(value["configured_semantic_embedder_revision"], str)
                        or re.fullmatch(r"[0-9a-f]{40}",
                            value["configured_semantic_embedder_revision"]) is None))
                or type(value.get("max_input_chars")) is not int
                or not 128 <= value["max_input_chars"]
                    <= MAX_RETRIEVAL_COMPARISON_INPUT_CHARS
                or (value.get("semantic_embedder_identity_digest") is not None
                    and (not isinstance(value["semantic_embedder_identity_digest"], str)
                        or re.fullmatch(r"[0-9a-f]{64}",
                            value["semantic_embedder_identity_digest"]) is None))
                or ((value.get("semantic_embedder_identity_digest") is None)
                    != (value.get("semantic_index_snapshot_digest") is None))
                or (value.get("semantic_index_snapshot_digest") is not None
                    and (not isinstance(value["semantic_index_snapshot_digest"], str)
                        or re.fullmatch(r"[0-9a-f]{64}",
                            value["semantic_index_snapshot_digest"]) is None))
                or not isinstance(value.get("semantic_cache_tick_digest"), str)
                or re.fullmatch(r"[0-9a-f]{64}",
                    value["semantic_cache_tick_digest"]) is None
                or (value.get("target_model_identity") is None) !=
                    (value.get("target_model_identity_digest") is None)
                or (value.get("target_model_identity") is not None
                    and (not isinstance(value["target_model_identity"], Mapping)
                        or not value["target_model_identity"]
                        or not isinstance(value["target_model_identity_digest"], str)
                        or re.fullmatch(r"[0-9a-f]{64}",
                            value["target_model_identity_digest"]) is None
                        or value["target_model_identity_digest"] !=
                            digest_payload(dict(value["target_model_identity"]))))
                or not isinstance(value.get("corpus_freeze_digest"), str)
                or re.fullmatch(r"[0-9a-f]{64}",
                    value["corpus_freeze_digest"]) is None
                or not isinstance(value.get("questions"), list)
                or len(value["questions"]) != value["question_count"]
                or not isinstance(value.get("strata"), list)
                or len(value["strata"]) != value["question_count"]
                or any(stratum not in RETRIEVAL_QUERY_STRATA
                    for stratum in value["strata"])
                or any(value["strata"].count(stratum) !=
                    value["question_count"] // 3
                    for stratum in RETRIEVAL_QUERY_STRATA)
                or value.get("evaluation_protocol") not in
                    SUPPORTED_RETRIEVAL_EVALUATION_PROTOCOLS
                or any(not isinstance(question, str) or not question.strip()
                    or len(question) > 1200
                    or digest_payload({"question": question}) !=
                        value["question_digests"][index]
                    for index, question in enumerate(value["questions"]))):
            raise DevelopmentalHistoryInterventionError(
                "retrieval_query_set_invalid")
        freeze = self.load_retrieval_corpus_freeze(value["corpus_freeze_id"])
        if (freeze["freeze_digest"] != value["corpus_freeze_digest"]
                or freeze["history_state_digest"] != value["history_state_digest"]
                or freeze["configured_semantic_embedder_model_id"] !=
                    value["configured_semantic_embedder_model_id"]
                or freeze["configured_semantic_embedder_revision"] !=
                    value["configured_semantic_embedder_revision"]):
            raise DevelopmentalHistoryInterventionError(
                "retrieval_query_set_freeze_mismatch")
        if has_source_record_bindings:
            from .semantic_history_retrieval_evaluation import (
                _validate_corpus_manifest,
                retrieval_source_experience_record_unit_digest)
            _, manifest_records = _validate_corpus_manifest(
                freeze["corpus_manifest"],
                history_state_digest=freeze["history_state_digest"])
            if (any(record_id not in manifest_records
                    for record_id in source_record_ids)
                    or source_digests != [
                        retrieval_source_experience_record_unit_digest(
                            record_id=record_id,
                            record_digest=manifest_records[record_id])
                        for record_id in source_record_ids]):
                raise DevelopmentalHistoryInterventionError(
                    "retrieval_query_set_source_experience_record_binding_invalid")
        return value

    def persist_retrieval_comparison_cohort(
            self, comparison_artifact_ids: Sequence[str], *,
            query_set_id: str) -> str:
        """Bind a fixed query set to reports from one history state and embedder config."""
        if (not isinstance(comparison_artifact_ids, (list, tuple))
                or not MIN_RETRIEVAL_COMPARISON_QUERIES <= len(
                    comparison_artifact_ids) <= MAX_RETRIEVAL_COMPARISON_QUERIES
                or len(comparison_artifact_ids) % 3 != 0
                or any(not isinstance(item, str) for item in comparison_artifact_ids)
                or len(set(comparison_artifact_ids)) != len(comparison_artifact_ids)):
            raise DevelopmentalHistoryInterventionError(
                "retrieval_comparison_cohort_selection_invalid")
        artifacts = [self.load_retrieval_comparison(item)
            for item in comparison_artifact_ids]
        reports = [item["comparison"] for item in artifacts]
        first = reports[0]
        state_digest = first["history_state_digest"]
        model_id = first["configured_semantic_embedder_model_id"]
        revision = first["configured_semantic_embedder_revision"]
        target_digest = first["target_model_identity_digest"]
        semantic_embedder_identity_digests = {
            report["semantic_embedder_identity_digest"]
            for report in reports
            if report["semantic_embedder_identity_digest"] is not None}
        if len(semantic_embedder_identity_digests) > 1:
            raise DevelopmentalHistoryInterventionError(
                "retrieval_comparison_embedder_identity_changed_during_batch")
        semantic_embedder_identity_digest = (
            next(iter(semantic_embedder_identity_digests))
            if semantic_embedder_identity_digests else None)
        semantic_index_snapshot_digests = {
            report["semantic_index_snapshot_digest"] for report in reports
            if report["semantic_index_snapshot_digest"] is not None}
        if len(semantic_index_snapshot_digests) > 1:
            raise DevelopmentalHistoryInterventionError(
                "retrieval_comparison_semantic_index_snapshot_changed")
        semantic_index_snapshot_digest = (
            next(iter(semantic_index_snapshot_digests))
            if semantic_index_snapshot_digests else None)
        semantic_cache_tick_digests = {
            report["semantic_cache_tick_digest"] for report in reports}
        if len(semantic_cache_tick_digests) != 1:
            raise DevelopmentalHistoryInterventionError(
                "retrieval_comparison_cache_tick_mismatch")
        semantic_index_statuses = sorted({report["semantic_index_status"]
            for report in reports if "semantic_index_status" in report})
        input_chars = first["max_input_chars"]
        query_set = self.load_retrieval_query_set(query_set_id)
        if (model_id != query_set["configured_semantic_embedder_model_id"]
                or revision != query_set["configured_semantic_embedder_revision"]
                or input_chars != query_set["max_input_chars"]
                or first["target_model_identity_digest"] !=
                    query_set["target_model_identity_digest"]):
            raise DevelopmentalHistoryInterventionError(
                "retrieval_comparison_preregistration_mismatch")
        questions = query_set["questions"]
        corpus_freeze_id = query_set["corpus_freeze_id"]
        corpus_freeze = self.load_retrieval_corpus_freeze(corpus_freeze_id)
        corpus_manifest = corpus_freeze["corpus_manifest"]
        from .semantic_history_retrieval_evaluation import (
            _validate_corpus_manifest)
        try:
            manifest_digest, manifest_records = _validate_corpus_manifest(
                corpus_manifest, history_state_digest=state_digest)
        except (TypeError, ValueError) as exc:
            raise DevelopmentalHistoryInterventionError(
                "retrieval_comparison_corpus_manifest_invalid") from exc
        if (any(report["history_state_digest"] != state_digest
                or report["configured_semantic_embedder_model_id"] != model_id
                or report["configured_semantic_embedder_revision"] != revision
                or report["target_model_identity_digest"] != target_digest
                or report["max_input_chars"] != input_chars
                for report in reports)
                or len({report["question_digest"] for report in reports})
                    != len(reports)):
            raise DevelopmentalHistoryInterventionError(
                "retrieval_comparison_cohort_binding_mismatch")
        if (not isinstance(questions, (list, tuple))
                or len(questions) != len(reports)
                or any(not isinstance(question, str) or not question.strip()
                    or len(question) > 1200
                    or digest_payload({"question": question}) !=
                        reports[index]["question_digest"]
                    for index, question in enumerate(questions))):
            raise DevelopmentalHistoryInterventionError(
                "retrieval_comparison_cohort_questions_invalid")
        if any(ref["record_digest"] != manifest_records.get(ref["record_id"])
                for report in reports for condition in report["conditions"]
                for ref in condition["available_records"]):
            raise DevelopmentalHistoryInterventionError(
                "retrieval_comparison_corpus_manifest_incomplete")
        cohort_schema = (RETRIEVAL_COMPARISON_COHORT_SCHEMA
            if "source_experience_digests" in query_set else
            LEGACY_RETRIEVAL_COMPARISON_COHORT_SCHEMA)
        body = {"schema_version": cohort_schema,
            "condition_order": ["lexical", "semantic"],
            "history_state_digest": state_digest,
            "question_count": len(reports),
            "questions": list(questions),
            "strata": list(query_set["strata"]),
            "evaluation_protocol": dict(query_set["evaluation_protocol"]),
            "question_digests": [report["question_digest"] for report in reports],
            "comparison_artifact_ids": list(comparison_artifact_ids),
            "comparison_digests": [report["comparison_digest"] for report in reports],
            "max_input_chars": input_chars,
            "target_model_identity_digest": target_digest,
            "target_model_identity": query_set["target_model_identity"],
            "semantic_embedder_identity_digest":
                semantic_embedder_identity_digest,
            "semantic_index_snapshot_digest": semantic_index_snapshot_digest,
            "semantic_index_statuses": semantic_index_statuses,
            "semantic_cache_tick_digest": next(iter(semantic_cache_tick_digests)),
            "configured_semantic_embedder_model_id": model_id,
            "configured_semantic_embedder_revision": revision,
            "corpus_manifest": dict(corpus_manifest),
            "corpus_manifest_digest": manifest_digest,
            "corpus_freeze_id": corpus_freeze_id,
            "corpus_freeze_digest": corpus_freeze["freeze_digest"],
            "query_set_id": query_set_id,
            "query_set_digest": query_set["query_set_digest"],
            "generative_model_invoked": False,
            "effect_established": False, "learning_established": False,
            "authority": False}
        if "source_experience_digests" in query_set:
            body["source_experience_digests"] = list(
                query_set["source_experience_digests"])
        digest = _digest(body)
        cohort_id = RETRIEVAL_COMPARISON_COHORT_ID_PREFIX + digest[7:31]
        self._write_immutable(self.runs / f"{cohort_id}.json",
            {**body, "cohort_id": cohort_id, "cohort_digest": digest})
        return cohort_id

    def load_retrieval_comparison_cohort(self, cohort_id: str) -> dict[str, Any]:
        if (not isinstance(cohort_id, str)
                or re.fullmatch(re.escape(RETRIEVAL_COMPARISON_COHORT_ID_PREFIX)
                    + r"[0-9a-f]{24}", cohort_id) is None):
            raise DevelopmentalHistoryInterventionError(
                "retrieval_comparison_cohort_identity_invalid")
        try:
            value = self._read_json(self.runs / f"{cohort_id}.json")
        except FileNotFoundError as exc:
            raise DevelopmentalHistoryInterventionError(
                "retrieval_comparison_cohort_missing") from exc
        body = {key: item for key, item in value.items()
            if key not in {"cohort_id", "cohort_digest"}}
        base_expected = {"schema_version", "condition_order", "history_state_digest",
            "question_count", "questions", "strata", "question_digests", "comparison_artifact_ids",
            "comparison_digests", "max_input_chars", "target_model_identity_digest",
            "target_model_identity", "semantic_embedder_identity_digest",
            "semantic_index_snapshot_digest", "semantic_cache_tick_digest",
            "configured_semantic_embedder_model_id",
            "configured_semantic_embedder_revision", "corpus_manifest",
            "corpus_manifest_digest", "corpus_freeze_id",
            "corpus_freeze_digest", "query_set_id", "query_set_digest",
            "evaluation_protocol",
            "generative_model_invoked",
            "effect_established", "learning_established", "authority",
            "cohort_id", "cohort_digest"}
        cohort_schema = value.get("schema_version")
        has_preregistered_units = cohort_schema in {
            RETRIEVAL_COMPARISON_COHORT_SCHEMA,
            PREVIOUS_RETRIEVAL_COMPARISON_COHORT_SCHEMA}
        expected = (base_expected | {"source_experience_digests"}
            if has_preregistered_units else base_expected)
        if cohort_schema == RETRIEVAL_COMPARISON_COHORT_SCHEMA:
            expected.add("semantic_index_statuses")
        source_digests = value.get("source_experience_digests")
        if (set(value) != expected
                or not isinstance(cohort_schema, str)
                or cohort_schema not in {RETRIEVAL_COMPARISON_COHORT_SCHEMA,
                    PREVIOUS_RETRIEVAL_COMPARISON_COHORT_SCHEMA,
                    LEGACY_RETRIEVAL_COMPARISON_COHORT_SCHEMA}
                or value.get("cohort_id") != cohort_id
                or value.get("cohort_digest") != _digest(body)
                or cohort_id != RETRIEVAL_COMPARISON_COHORT_ID_PREFIX
                    + str(value.get("cohort_digest", ""))[7:31]
                or value.get("condition_order") != ["lexical", "semantic"]
                or type(value.get("question_count")) is not int
                or not MIN_RETRIEVAL_COMPARISON_QUERIES <= value["question_count"]
                    <= MAX_RETRIEVAL_COMPARISON_QUERIES
                or value["question_count"] % 3 != 0
                or not isinstance(value.get("question_digests"), list)
                or len(value["question_digests"]) != value["question_count"]
                or not isinstance(value.get("questions"), list)
                or len(value["questions"]) != value["question_count"]
                or not isinstance(value.get("strata"), list)
                or len(value["strata"]) != value["question_count"]
                or any(stratum not in RETRIEVAL_QUERY_STRATA
                    for stratum in value["strata"])
                or any(value["strata"].count(stratum) !=
                    value["question_count"] // 3
                    for stratum in RETRIEVAL_QUERY_STRATA)
                or value.get("evaluation_protocol") not in
                    SUPPORTED_RETRIEVAL_EVALUATION_PROTOCOLS
                or any(not isinstance(question, str) or not question.strip()
                    or len(question) > 1200
                    or digest_payload({"question": question}) !=
                        value["question_digests"][index]
                    for index, question in enumerate(value["questions"]))
                or any(not isinstance(item, str)
                    or re.fullmatch(r"[0-9a-f]{64}", item) is None
                    for item in value["question_digests"])
                or len(set(value["question_digests"])) != value["question_count"]
                or (has_preregistered_units and (
                    not isinstance(source_digests, list)
                    or len(source_digests) != value["question_count"]
                    or any(not isinstance(item, str)
                        or re.fullmatch(r"[0-9a-f]{64}", item) is None
                        for item in source_digests)
                    or len(set(source_digests)) != value["question_count"]))
                or not isinstance(value.get("comparison_artifact_ids"), list)
                or len(value["comparison_artifact_ids"]) != value["question_count"]
                or any(not isinstance(item, str)
                    or re.fullmatch(re.escape(RETRIEVAL_COMPARISON_ID_PREFIX)
                        + r"[0-9a-f]{24}", item) is None
                    for item in value["comparison_artifact_ids"])
                or len(set(value["comparison_artifact_ids"])) != value["question_count"]
                or not isinstance(value.get("comparison_digests"), list)
                or len(value["comparison_digests"]) != value["question_count"]
                or any(not isinstance(item, str)
                    or re.fullmatch(r"[0-9a-f]{64}", item) is None
                    for item in value["comparison_digests"])
                or type(value.get("max_input_chars")) is not int
                or not 128 <= value["max_input_chars"]
                    <= MAX_RETRIEVAL_COMPARISON_INPUT_CHARS
                or not isinstance(value.get("history_state_digest"), str)
                or not _valid_sha256_digest(value["history_state_digest"])
                or not isinstance(value.get("corpus_freeze_id"), str)
                or re.fullmatch(re.escape(RETRIEVAL_CORPUS_FREEZE_ID_PREFIX)
                    + r"[0-9a-f]{24}", value["corpus_freeze_id"]) is None
                or not isinstance(value.get("corpus_freeze_digest"), str)
                or re.fullmatch(r"[0-9a-f]{64}",
                    value["corpus_freeze_digest"]) is None
                or not isinstance(value.get("query_set_id"), str)
                or re.fullmatch(re.escape(RETRIEVAL_QUERY_SET_ID_PREFIX)
                    + r"[0-9a-f]{24}", value["query_set_id"]) is None
                or not isinstance(value.get("query_set_digest"), str)
                or re.fullmatch(r"[0-9a-f]{64}",
                    value["query_set_digest"]) is None
                or value.get("generative_model_invoked") is not False
                or value.get("effect_established") is not False
                or value.get("learning_established") is not False
                or value.get("authority") is not False):
            raise DevelopmentalHistoryInterventionError(
                "retrieval_comparison_cohort_invalid")
        from .semantic_history_retrieval_evaluation import (
            _validate_corpus_manifest)
        try:
            manifest_digest, manifest_records = _validate_corpus_manifest(
                value.get("corpus_manifest"),
                history_state_digest=value["history_state_digest"])
        except (TypeError, ValueError) as exc:
            raise DevelopmentalHistoryInterventionError(
                "retrieval_comparison_cohort_manifest_invalid") from exc
        if manifest_digest != value.get("corpus_manifest_digest"):
            raise DevelopmentalHistoryInterventionError(
                "retrieval_comparison_cohort_manifest_mismatch")
        corpus_freeze = self.load_retrieval_corpus_freeze(
            value["corpus_freeze_id"])
        if (corpus_freeze["freeze_digest"] != value["corpus_freeze_digest"]
                or corpus_freeze["corpus_manifest"] != value["corpus_manifest"]
                or corpus_freeze["history_state_digest"] !=
                    value["history_state_digest"]):
            raise DevelopmentalHistoryInterventionError(
                "retrieval_comparison_cohort_freeze_mismatch")
        query_set = self.load_retrieval_query_set(value["query_set_id"])
        if (query_set["query_set_digest"] != value["query_set_digest"]
                or query_set["corpus_freeze_id"] != value["corpus_freeze_id"]
                or query_set["target_model_identity"] !=
                    value["target_model_identity"]
                or query_set["configured_semantic_embedder_model_id"] !=
                    value["configured_semantic_embedder_model_id"]
                or query_set["configured_semantic_embedder_revision"] !=
                    value["configured_semantic_embedder_revision"]
                or query_set["max_input_chars"] != value["max_input_chars"]
                or query_set["target_model_identity_digest"] !=
                    value["target_model_identity_digest"]
                or query_set["questions"] != value["questions"]
                or query_set["strata"] != value["strata"]
                or query_set["evaluation_protocol"] !=
                    value["evaluation_protocol"]
                or query_set["question_digests"] != value["question_digests"]
                or query_set.get("source_experience_digests") !=
                    value.get("source_experience_digests")
                or (("source_experience_digests" in query_set)
                    != has_preregistered_units)):
            raise DevelopmentalHistoryInterventionError(
                "retrieval_comparison_cohort_query_set_mismatch")
        reports = [self.load_retrieval_comparison(item)["comparison"]
            for item in value["comparison_artifact_ids"]]
        if any(report["question_digest"] != value["question_digests"][index]
                or report["comparison_digest"] != value["comparison_digests"][index]
                or report["history_state_digest"] != value["history_state_digest"]
                or report["max_input_chars"] != value["max_input_chars"]
                or report["target_model_identity_digest"] !=
                    value["target_model_identity_digest"]
                or report["configured_semantic_embedder_model_id"] !=
                    value["configured_semantic_embedder_model_id"]
                or report["configured_semantic_embedder_revision"] !=
                    value["configured_semantic_embedder_revision"]
                or (report["semantic_embedder_identity_digest"] is not None
                    and report["semantic_embedder_identity_digest"] !=
                        value["semantic_embedder_identity_digest"])
                or (report["semantic_index_snapshot_digest"] is not None
                    and report["semantic_index_snapshot_digest"] !=
                        value["semantic_index_snapshot_digest"])
                or report["semantic_cache_tick_digest"] !=
                    value["semantic_cache_tick_digest"]
                or ("semantic_index_status" in report
                    and report["semantic_index_status"] not in
                        value.get("semantic_index_statuses", [
                            report["semantic_index_status"]]))
                or any(ref["record_digest"] != manifest_records.get(ref["record_id"])
                    for condition in report["conditions"]
                    for ref in condition["available_records"])
                for index, report in enumerate(reports)):
            raise DevelopmentalHistoryInterventionError(
                "retrieval_comparison_cohort_binding_mismatch")
        observed_embedder_ids = {report["semantic_embedder_identity_digest"]
            for report in reports
            if report["semantic_embedder_identity_digest"] is not None}
        observed_index_snapshots = {report["semantic_index_snapshot_digest"]
            for report in reports
            if report["semantic_index_snapshot_digest"] is not None}
        observed_index_statuses = sorted({report["semantic_index_status"]
            for report in reports if "semantic_index_status" in report})
        if (len(observed_embedder_ids) > 1
                or (next(iter(observed_embedder_ids)) if observed_embedder_ids
                    else None) != value["semantic_embedder_identity_digest"]
                or len(observed_index_snapshots) > 1
                or (next(iter(observed_index_snapshots))
                    if observed_index_snapshots else None) !=
                        value["semantic_index_snapshot_digest"]
                or (cohort_schema == RETRIEVAL_COMPARISON_COHORT_SCHEMA
                    and observed_index_statuses !=
                        value["semantic_index_statuses"])):
            raise DevelopmentalHistoryInterventionError(
                "retrieval_comparison_cohort_embedder_identity_mismatch")
        return value

    def build_retrieval_adjudication_packet(self, cohort_id: str
            ) -> dict[str, Any]:
        """Build a reviewer packet containing queries and corpus refs, not results."""
        cohort = self.load_retrieval_comparison_cohort(cohort_id)
        query_set = self.load_retrieval_query_set(cohort["query_set_id"])
        from .semantic_history_retrieval_evaluation import (
            retrieval_adjudication_procedure)
        protocol_schema = cohort.get("evaluation_protocol", {}).get(
            "schema_version")
        concealed_strata = protocol_schema in {
            "sentientos.semantic_history_retrieval_gate:v9",
            "sentientos.semantic_history_retrieval_gate:v10",
            # v11/v12 inherit the blinded v9/v10 adjudication contracts;
            # only their finite-sample false-inclusion interval changes.
            "sentientos.semantic_history_retrieval_gate:v11",
            "sentientos.semantic_history_retrieval_gate:v12"}
        has_preregistered_units = isinstance(
            query_set.get("source_experience_digests"), list)
        has_source_record_bindings = isinstance(
            query_set.get("source_experience_record_ids"), list)
        packet_schema = (
            "sentientos.developmental_history_retrieval_adjudication_packet:v8"
            if concealed_strata else
            "sentientos.developmental_history_retrieval_adjudication_packet:v7"
            if has_source_record_bindings else
            "sentientos.developmental_history_retrieval_adjudication_packet:v6"
            if has_preregistered_units else
            "sentientos.developmental_history_retrieval_adjudication_packet:v5")
        semantic = {"schema_version": packet_schema,
            "cohort_id": cohort_id,
            "cohort_digest": cohort["cohort_digest"],
            "history_state_digest": cohort["history_state_digest"],
            "corpus_manifest_digest": cohort["corpus_manifest_digest"],
            "target_model_identity": cohort["target_model_identity"],
            "target_model_identity_digest":
                cohort["target_model_identity_digest"],
            "corpus_record_refs": cohort["corpus_manifest"]["records"],
            "queries": [{"question_digest": cohort["question_digests"][index],
                "question": question,
                **({"preregistered_stratum": cohort["strata"][index]}
                    if not concealed_strata else {}),
                **({"source_experience_digest": cohort[
                    "source_experience_digests"][index]}
                    if packet_schema ==
                        "sentientos.developmental_history_retrieval_adjudication_packet:v6"
                    else {})}
                for index, question in enumerate(cohort["questions"])],
            "adjudication_procedure": retrieval_adjudication_procedure(
                source_record_bindings=has_source_record_bindings,
                conceal_preregistered_strata=concealed_strata),
            "condition_selections_included": False,
            "generative_model_invoked": False,
            "authority": False}
        preregistered_procedure_digest = cohort.get(
            "evaluation_protocol", {}).get("adjudication_procedure_digest")
        if (semantic["adjudication_procedure"].get("procedure_digest") !=
                preregistered_procedure_digest):
            raise DevelopmentalHistoryInterventionError(
                "retrieval_adjudication_procedure_protocol_mismatch")
        return {**semantic, "packet_digest": _digest(semantic)}

    def run_retrieval_comparison_batch(self, *, owner: Any,
            query_set_id: str,
            max_input_chars: int = 8000) -> str:
        """Run and persist paired retrieval comparisons; never invokes a generative model."""
        if (type(max_input_chars) is not int
                or not 128 <= max_input_chars
                    <= MAX_RETRIEVAL_COMPARISON_INPUT_CHARS):
            raise DevelopmentalHistoryInterventionError(
                "retrieval_comparison_batch_selection_invalid")
        query_set = self.load_retrieval_query_set(query_set_id)
        questions = query_set["questions"]
        corpus_freeze_id = query_set["corpus_freeze_id"]
        config = getattr(owner, "config", None)
        if (getattr(config, "semantic_history_model_id", None) !=
                query_set["configured_semantic_embedder_model_id"]
                or getattr(config, "semantic_history_model_revision", None) !=
                    query_set["configured_semantic_embedder_revision"]
                or max_input_chars != query_set["max_input_chars"]):
            raise DevelopmentalHistoryInterventionError(
                "retrieval_comparison_configuration_changed_since_preregistration")
        compare = getattr(owner,
            "compare_ordinary_chat_developmental_history_retrieval", None)
        if not callable(compare):
            raise DevelopmentalHistoryInterventionError(
                "retrieval_comparison_owner_unavailable")
        corpus_freeze = self.load_retrieval_corpus_freeze(corpus_freeze_id)
        manifest_getter = getattr(owner,
            "ordinary_chat_developmental_history_corpus_manifest", None)
        if not callable(manifest_getter):
            raise DevelopmentalHistoryInterventionError(
                "retrieval_comparison_owner_manifest_unavailable")
        preflight_manifest = manifest_getter()
        if (not isinstance(preflight_manifest, Mapping)
                or preflight_manifest != corpus_freeze["corpus_manifest"]
                or preflight_manifest.get("history_state_digest") !=
                    corpus_freeze["history_state_digest"]):
            raise DevelopmentalHistoryInterventionError(
                "retrieval_comparison_corpus_freeze_stale")
        semantic_cache_tick_id = "retrieval-batch-" + query_set_id[-24:]
        reports = [compare(question=question,
            max_input_chars=max_input_chars,
            target_model_identity=query_set["target_model_identity"],
            semantic_cache_tick_id=semantic_cache_tick_id)
            for question in questions]
        for report in reports:
            self._verify_retrieval_comparison(report)
        runtime_embedder_ids = {report["semantic_embedder_identity_digest"]
            for report in reports
            if report["semantic_embedder_identity_digest"] is not None}
        if len(runtime_embedder_ids) > 1:
            raise DevelopmentalHistoryInterventionError(
                "retrieval_comparison_embedder_identity_changed_during_batch")
        runtime_index_snapshots = {report["semantic_index_snapshot_digest"]
            for report in reports
            if report["semantic_index_snapshot_digest"] is not None}
        if len(runtime_index_snapshots) > 1:
            raise DevelopmentalHistoryInterventionError(
                "retrieval_comparison_semantic_index_snapshot_changed")
        if len({report["semantic_cache_tick_digest"]
                for report in reports}) != 1:
            raise DevelopmentalHistoryInterventionError(
                "retrieval_comparison_cache_tick_mismatch")
        first = reports[0]
        if (first["history_state_digest"] !=
                corpus_freeze["history_state_digest"]
                or any(report["history_state_digest"] != first["history_state_digest"]
                    for report in reports)):
            raise DevelopmentalHistoryInterventionError(
                "retrieval_comparison_history_changed_during_batch")
        corpus_manifest = manifest_getter()
        if (not isinstance(corpus_manifest, Mapping)
                or corpus_manifest != corpus_freeze["corpus_manifest"]):
            raise DevelopmentalHistoryInterventionError(
                "retrieval_comparison_history_changed_during_batch")
        artifact_ids = [self.persist_retrieval_comparison(report)
            for report in reports]
        return self.persist_retrieval_comparison_cohort(artifact_ids,
            query_set_id=query_set_id)

    def persist_retrieval_comparison_evaluation(self, *, cohort_id: str,
            annotations: Mapping[str, Any]) -> str:
        """Score and immutably persist externally supplied blinded relevance labels."""
        try:
            annotation_snapshot = json.loads(json.dumps(dict(annotations),
                sort_keys=True, ensure_ascii=False, allow_nan=False))
            cohort = self.load_retrieval_comparison_cohort(cohort_id)
            manifest_snapshot = cohort["corpus_manifest"]
        except (TypeError, ValueError) as exc:
            raise DevelopmentalHistoryInterventionError(
                "retrieval_evaluation_annotations_invalid") from exc
        from .semantic_history_retrieval_evaluation import (
            score_retrieval_comparison_cohort)
        try:
            evaluation = score_retrieval_comparison_cohort(self,
                cohort_id=cohort_id, annotations=annotation_snapshot)
        except (TypeError, ValueError) as exc:
            raise DevelopmentalHistoryInterventionError(
                "retrieval_evaluation_invalid") from exc
        body = {"schema_version": RETRIEVAL_EVALUATION_ARTIFACT_SCHEMA,
            "cohort_id": cohort_id, "annotations": annotation_snapshot,
            "corpus_manifest": manifest_snapshot,
            "evaluation": evaluation}
        digest = _digest(body)
        artifact_id = RETRIEVAL_EVALUATION_ID_PREFIX + digest[7:31]
        self._write_immutable(self.runs / f"{artifact_id}.json",
            {**body, "artifact_id": artifact_id, "artifact_digest": digest})
        return artifact_id

    def load_retrieval_comparison_evaluation(self, artifact_id: str
            ) -> dict[str, Any]:
        if (not isinstance(artifact_id, str)
                or re.fullmatch(re.escape(RETRIEVAL_EVALUATION_ID_PREFIX)
                    + r"[0-9a-f]{24}", artifact_id) is None):
            raise DevelopmentalHistoryInterventionError(
                "retrieval_evaluation_identity_invalid")
        try:
            value = self._read_json(self.runs / f"{artifact_id}.json")
        except FileNotFoundError as exc:
            raise DevelopmentalHistoryInterventionError(
                "retrieval_evaluation_missing") from exc
        body = {key: item for key, item in value.items()
            if key not in {"artifact_id", "artifact_digest"}}
        if (set(value) != {"schema_version", "cohort_id", "annotations",
                "corpus_manifest", "evaluation", "artifact_id", "artifact_digest"}
                or value.get("schema_version") != RETRIEVAL_EVALUATION_ARTIFACT_SCHEMA
                or value.get("artifact_id") != artifact_id
                or value.get("artifact_digest") != _digest(body)
                or artifact_id != RETRIEVAL_EVALUATION_ID_PREFIX
                    + str(value.get("artifact_digest", ""))[7:31]
                or not isinstance(value.get("annotations"), Mapping)
                or not isinstance(value.get("corpus_manifest"), Mapping)
                or not isinstance(value.get("evaluation"), Mapping)):
            raise DevelopmentalHistoryInterventionError(
                "retrieval_evaluation_digest_mismatch")
        from .semantic_history_retrieval_evaluation import (
            score_retrieval_comparison_cohort)
        try:
            cohort = self.load_retrieval_comparison_cohort(value["cohort_id"])
            if value["corpus_manifest"] != cohort["corpus_manifest"]:
                raise DevelopmentalHistoryInterventionError(
                    "retrieval_evaluation_manifest_cohort_mismatch")
            recomputed = score_retrieval_comparison_cohort(self,
                cohort_id=value["cohort_id"], annotations=value["annotations"])
        except DevelopmentalHistoryInterventionError as exc:
            if str(exc) == "retrieval_evaluation_manifest_cohort_mismatch":
                raise
            raise DevelopmentalHistoryInterventionError(
                "retrieval_evaluation_recomputation_failed") from exc
        except (TypeError, ValueError) as exc:
            raise DevelopmentalHistoryInterventionError(
                "retrieval_evaluation_recomputation_failed") from exc
        legacy_evaluation_schema = value["evaluation"].get("schema_version")
        from .semantic_history_retrieval_evaluation import (
            EVALUATION_SCHEMA, LEGACY_EVALUATION_SCHEMA,
            PREVIOUS_COMMON_K_EVALUATION_SCHEMA,
            PREVIOUS_SAMPLING_EVALUATION_SCHEMA,
            PREVIOUS_UNIT_BINDING_EVALUATION_SCHEMA,
            PREVIOUS_RECORD_BINDING_EVALUATION_SCHEMA,
            PREVIOUS_RECORD_RELEVANCE_EVALUATION_SCHEMA,
            PREVIOUS_FALSE_INCLUSION_EVALUATION_SCHEMA,
            PREVIOUS_STRATUM_VALIDATION_EVALUATION_SCHEMA)
        if isinstance(legacy_evaluation_schema, str) and (
                legacy_evaluation_schema in {LEGACY_EVALUATION_SCHEMA,
                PREVIOUS_COMMON_K_EVALUATION_SCHEMA,
                PREVIOUS_SAMPLING_EVALUATION_SCHEMA,
                PREVIOUS_UNIT_BINDING_EVALUATION_SCHEMA,
                PREVIOUS_RECORD_BINDING_EVALUATION_SCHEMA,
                PREVIOUS_RECORD_RELEVANCE_EVALUATION_SCHEMA,
                PREVIOUS_FALSE_INCLUSION_EVALUATION_SCHEMA,
                PREVIOUS_STRATUM_VALIDATION_EVALUATION_SCHEMA}):
            if recomputed.get("schema_version") != EVALUATION_SCHEMA:
                raise DevelopmentalHistoryInterventionError(
                    "retrieval_evaluation_legacy_projection_invalid")
            legacy_semantic = {key: item for key, item in recomputed.items()
                if key != "evaluation_digest"}
            legacy_semantic.pop("query_stratum_label_validation", None)
            for row in legacy_semantic.get("per_query_outcomes", []):
                if isinstance(row, dict):
                    row.pop("preregistered_stratum_label_expectations_met", None)
            legacy_gate = legacy_semantic.get("gate")
            if isinstance(legacy_gate, Mapping):
                legacy_gate = dict(legacy_gate)
                legacy_gate.pop("query_stratum_label_validation_passed", None)
                legacy_gate.pop(
                    "preregistered_source_record_label_expectations_met", None)
                legacy_semantic["gate"] = legacy_gate
            if legacy_evaluation_schema == (
                    PREVIOUS_RECORD_RELEVANCE_EVALUATION_SCHEMA):
                for row in legacy_semantic.get("per_query_outcomes", []):
                    if isinstance(row, dict):
                        row.pop(
                            "source_experience_record_reference_verified", None)
                        row.pop(
                            "source_experience_record_relevance_status", None)
                assumptions = legacy_semantic.get("sampling_assumptions")
                if isinstance(assumptions, Mapping):
                    assumptions = dict(assumptions)
                    assumptions.pop(
                        "source_experience_record_references_verified", None)
                    assumptions.pop(
                        "source_experience_record_relevance_checks_verified",
                        None)
                    legacy_semantic["sampling_assumptions"] = assumptions
                gate = legacy_semantic.get("gate")
                if isinstance(gate, Mapping):
                    gate = dict(gate)
                    gate.pop(
                        "source_experience_record_references_verified", None)
                    gate.pop(
                        "source_experience_record_relevance_checks_verified",
                        None)
                    legacy_semantic["gate"] = gate
            if legacy_evaluation_schema != (
                    PREVIOUS_RECORD_RELEVANCE_EVALUATION_SCHEMA):
                for row in legacy_semantic.get("per_query_outcomes", []):
                    if isinstance(row, dict):
                        row.pop(
                            "source_experience_record_binding_verified", None)
                assumptions = legacy_semantic.get("sampling_assumptions")
                if isinstance(assumptions, Mapping):
                    assumptions = dict(assumptions)
                    assumptions.pop(
                        "source_experience_record_bindings_preregistered", None)
                    assumptions.pop(
                        "source_experience_record_bindings_verified", None)
                    legacy_semantic["sampling_assumptions"] = assumptions
                gate = legacy_semantic.get("gate")
                if isinstance(gate, Mapping):
                    gate = dict(gate)
                    gate.pop("qualification_posture", None)
                    gate.pop(
                        "source_experience_record_bindings_verified", None)
                    if gate.get("status") == (
                            "retrieval_gate_passed_conditional_on_unverified_source_independence"):
                        gate["status"] = "retrieval_gate_passed"
                    legacy_semantic["gate"] = gate
            if legacy_evaluation_schema in {LEGACY_EVALUATION_SCHEMA,
                    PREVIOUS_COMMON_K_EVALUATION_SCHEMA}:
                legacy_semantic.pop("sampling_assumptions", None)
            elif legacy_evaluation_schema == PREVIOUS_SAMPLING_EVALUATION_SCHEMA:
                legacy_semantic["sampling_assumptions"] = {
                    "bootstrap_resampling_unit": "query_row",
                    "asserted_source_experience_digest_count": len(
                        recomputed.get("per_query_outcomes", [])),
                    "source_experience_digests_preregistered": False,
                    "source_experience_independence_verified": False,
                    "confidence_intervals_conditional_on_external_unit_assertions": True,
                    "population_uncertainty": "not_estimated"}
            elif legacy_evaluation_schema == PREVIOUS_UNIT_BINDING_EVALUATION_SCHEMA:
                assumptions = legacy_semantic.get("sampling_assumptions")
                if isinstance(assumptions, Mapping):
                    assumptions = dict(assumptions)
                    assumptions.pop("inferential_gate_qualification", None)
                    legacy_semantic["sampling_assumptions"] = assumptions
            legacy_semantic["schema_version"] = legacy_evaluation_schema
            recomputed = {**legacy_semantic,
                "evaluation_digest": digest_payload(legacy_semantic)}
        if recomputed != value["evaluation"]:
            raise DevelopmentalHistoryInterventionError(
                "retrieval_evaluation_recomputation_mismatch")
        return value

    def persist_objective_cohort_summary(self, run_ids: Sequence[str]) -> str:
        """Persist one fully verified six-trial balanced objective cohort."""
        include_calibration = False
        if (isinstance(run_ids, Sequence) and not isinstance(run_ids, (str, bytes))
                and run_ids and isinstance(run_ids[0], str)):
            first_run = self.load_run(run_ids[0])
            first_protocol = first_run.get("protocol")
            include_calibration = (isinstance(first_protocol, Mapping)
                and first_protocol.get("schema_version") ==
                    CALIBRATED_OBJECTIVE_SCHEDULED_HISTORY_SCHEMA)
        try:
            summary = summarize_objective_cohort(self, run_ids,
                include_calibration=include_calibration)
        except DevelopmentalHistoryInterventionError as exc:
            if (str(exc) != "objective_cohort_answerability_missing"
                    or include_calibration):
                raise
            # A complete block of immutable older runs can still produce its
            # original v2 aggregate; do not fabricate the newer measurement.
            summary = summarize_objective_cohort(self, run_ids,
                include_answerability=False)
        digest = _digest(summary)
        cohort_id = "developmental-objective-cohort-" + digest[7:31]
        self._write_immutable(self.runs / f"{cohort_id}.json",
            {**summary, "cohort_id": cohort_id, "cohort_digest": digest})
        return cohort_id

    def load_objective_cohort_summary(self, cohort_id: str) -> dict[str, Any]:
        prefix = "developmental-objective-cohort-"
        if (not isinstance(cohort_id, str) or not cohort_id.startswith(prefix)
                or len(cohort_id) != len(prefix) + 24
                or any(char not in "0123456789abcdef" for char in cohort_id[len(prefix):])):
            raise DevelopmentalHistoryInterventionError("objective_cohort_identity_invalid")
        try:
            value = self._read_json(self.runs / f"{cohort_id}.json")
        except FileNotFoundError as exc:
            raise DevelopmentalHistoryInterventionError("objective_cohort_missing") from exc
        semantic = {key: item for key, item in value.items()
            if key not in {"cohort_id", "cohort_digest"}}
        if (value.get("cohort_id") != cohort_id
                or value.get("cohort_digest") != _digest(semantic)
                or cohort_id != prefix + str(value.get("cohort_digest", ""))[7:31]):
            raise DevelopmentalHistoryInterventionError("objective_cohort_digest_mismatch")
        schema = semantic.get("schema_version")
        if schema not in {
                "sentientos.developmental_objective_cohort_summary:v2",
                "sentientos.developmental_objective_cohort_summary:v3",
                "sentientos.developmental_objective_cohort_summary:v4"}:
            raise DevelopmentalHistoryInterventionError("objective_cohort_schema_invalid")
        recomputed = summarize_objective_cohort(self, semantic.get("run_ids", ()),
            include_answerability=schema in {
                "sentientos.developmental_objective_cohort_summary:v3",
                "sentientos.developmental_objective_cohort_summary:v4"},
            include_calibration=schema ==
                "sentientos.developmental_objective_cohort_summary:v4")
        if recomputed != semantic:
            raise DevelopmentalHistoryInterventionError("objective_cohort_recovery_mismatch")
        return value

    def load_run(self, run_id: str) -> dict[str, Any]:
        prefix = "devexp-run-"
        if (not isinstance(run_id, str) or len(run_id) != len(prefix) + 24
                or not run_id.startswith(prefix)
                or any(character not in "0123456789abcdef" for character in run_id[len(prefix):])):
            raise DevelopmentalHistoryInterventionError("run_identity_invalid")
        try:
            value = self._read_json(self.runs / f"{run_id}.json")
        except FileNotFoundError as exc:
            raise DevelopmentalHistoryInterventionError("run_artifact_missing") from exc
        semantic = {key: item for key, item in value.items() if key not in {"run_id", "run_digest"}}
        schema_version = value.get("schema_version")
        if (schema_version not in {LEGACY_RUN_SCHEMA, *COMPANION_DECISION_RUN_SCHEMAS}
                or value.get("run_id") != run_id
                or value.get("run_digest") != _digest(semantic)
                or run_id != prefix + str(value.get("run_digest", ""))[7:31]):
            raise DevelopmentalHistoryInterventionError("run_artifact_digest_mismatch")
        # A valid outer digest only proves that this artifact is internally
        # stable. Reconstruct the protocol and all three owner-produced
        # cognition observations, then recompute the controlled comparison so
        # recovery cannot promote a self-consistent but semantically incomplete
        # run to valid experimental evidence.
        expected_fields = {"schema_version", "protocol", "conditions", "summary",
            "validity", "contamination_reasons", "run_id", "run_digest"}
        protocol_raw, conditions = value.get("protocol"), value.get("conditions")
        optional_fields = {"objective_scores", "objective_evaluation",
            "contamination_assessment"}
        if schema_version in COMPANION_DECISION_RUN_SCHEMAS:
            optional_fields.add("companion_intervention_decisions")
        if (not set(value).issubset(expected_fields | optional_fields)
                or not expected_fields.issubset(value) or not isinstance(protocol_raw, Mapping)
                or not isinstance(conditions, list) or not isinstance(value.get("summary"), Mapping)
                or value.get("validity") != "valid_controlled_observation"
                or value.get("contamination_reasons") not in ([], None)
                or (value.get("contamination_reasons") is None
                    and "contamination_assessment" not in value)):
            raise DevelopmentalHistoryInterventionError("run_artifact_control_invalid")
        protocol_payload = dict(protocol_raw)
        tuple_fields = ("current_fact_ids", "record_ids", "record_digests", "condition_order",
            "planned_comparisons", "non_claims", "epistemic_state_digests",
            "epistemic_evidence_set_digests", "self_model_claim_ids", "self_model_claim_digests")
        try:
            for key in tuple_fields:
                protocol_payload[key] = tuple(protocol_payload.get(key, ()))
            protocol = DevelopmentalHistoryInterventionProtocol(**protocol_payload)
            verify_protocol(protocol)
            assessment = value.get("contamination_assessment")
            if (assessment is not None
                    and (protocol.schema_version not in OBJECTIVE_SCHEMAS
                        or value.get("contamination_reasons") is not None
                        or assessment != objective_task_contamination_assessment(protocol))):
                raise ValueError("objective_task_contamination_assessment_invalid")
            from .resident_developmental_cognition import ResidentCognitionObservation
            observation_tuple_fields = ("current_fact_ids", "retrieved_record_ids",
                "retrieved_record_digests", "self_model_claim_ids", "self_model_claim_digests",
                "epistemic_proposition_ids", "epistemic_state_ids", "epistemic_state_digests",
                "epistemic_generations", "epistemic_evidence_set_digests",
                "epistemic_consumed_packet_ids", "epistemic_consumed_packet_digests",
                "epistemic_omitted_packets", "resource_consumption_receipt_digests")
            observations: list[ResidentCognitionObservation] = []
            for raw_observation in conditions:
                if not isinstance(raw_observation, Mapping):
                    raise TypeError("condition_observation_invalid")
                raw_condition_payload = dict(raw_observation)
                for key in observation_tuple_fields:
                    if key in raw_condition_payload:
                        raw_condition_payload[key] = tuple(raw_condition_payload[key])
                observations.append(ResidentCognitionObservation(**raw_condition_payload))
            recomputed = summarize(protocol, observations,
                companion_intervention_decisions=(
                    value.get("companion_intervention_decisions")
                    if schema_version == RUN_SCHEMA else None))
        except (KeyError, TypeError, ValueError) as exc:
            raise DevelopmentalHistoryInterventionError("run_artifact_control_invalid") from exc
        verified_invocations: dict[str, Mapping[str, Any]] = {}
        requires_scheduled_receipts = protocol.schema_version in SCHEDULED_ORDER_SCHEMAS
        for observation in observations:
            identity = (observation.active_model_identity
                if isinstance(observation.active_model_identity, Mapping) else {})
            rootless_identity = (bool(identity)
                and (identity.get("posture") == "rootless_experimental"
                    or (identity.get("engine") == "ollama"
                        and identity.get("posture") == "development_only"
                        and identity.get("fallback") is False
                        and identity.get("candidate_index") == 0)))
            if (observation.serving_session_id is None
                    and not requires_scheduled_receipts and not rootless_identity):
                continue
            if not callable(self._invocation_verifier):
                raise DevelopmentalHistoryInterventionError(
                    "run_artifact_invocation_verifier_unavailable")
            try:
                verified_receipt = self._invocation_verifier(asdict(observation))
            except Exception as exc:
                raise DevelopmentalHistoryInterventionError(
                    "run_artifact_invocation_receipt_invalid") from exc
            if isinstance(verified_receipt, Mapping):
                verified_generation = verified_receipt.get("generation_config")
                if (isinstance(verified_generation, Mapping)
                        and dict(verified_generation) != dict(observation.generation_config)):
                    raise DevelopmentalHistoryInterventionError(
                        "run_artifact_generation_config_mismatch")
                verified_invocations[observation.condition_id] = verified_receipt
            elif requires_scheduled_receipts:
                raise DevelopmentalHistoryInterventionError(
                    "scheduled_condition_invocation_receipt_unverified")
        if requires_scheduled_receipts:
            scheduled_times: list[datetime] = []
            for condition_id in protocol.condition_order:
                receipt = verified_invocations.get(condition_id)
                observed_at = receipt.get("observed_at") if isinstance(receipt, Mapping) else None
                if (not isinstance(observed_at, str) or observed_at.endswith("-00:00")):
                    raise DevelopmentalHistoryInterventionError(
                        "scheduled_condition_invocation_time_unverified")
                try:
                    parsed_at = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
                except ValueError as exc:
                    raise DevelopmentalHistoryInterventionError(
                        "scheduled_condition_invocation_time_invalid") from exc
                if parsed_at.tzinfo is None:
                    raise DevelopmentalHistoryInterventionError(
                        "scheduled_condition_invocation_time_invalid")
                scheduled_times.append(parsed_at)
            if any(left >= right for left, right in zip(
                    scheduled_times, scheduled_times[1:])):
                raise DevelopmentalHistoryInterventionError(
                    "scheduled_condition_invocation_order_mismatch")
        def canonical(item: object) -> str:
            return json.dumps(item, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False)
        if canonical(recomputed) != canonical(value["summary"]):
            raise DevelopmentalHistoryInterventionError("run_artifact_summary_mismatch")
        decisions = value.get("companion_intervention_decisions")
        if decisions is not None:
            decision_fields = {"condition_id", "observation_id", "observation_digest",
                "inference_receipt_id", "inference_receipt_digest", "output_digest",
                "response_digest", "disposition", "model_disposition",
                "disposition_normalization", "evidence_ids", "history_record_ids"}
            decision_validation_fields = {
                "decision_validation_status", "decision_validation_error_code"}
            by_condition = {item.condition_id: item for item in observations}
            if (schema_version not in COMPANION_DECISION_RUN_SCHEMAS
                    or not isinstance(decisions, list)
                    or len(decisions) != len(CONDITION_ORDER)):
                raise DevelopmentalHistoryInterventionError(
                    "run_artifact_companion_decisions_invalid")
            for condition_id, decision in zip(CONDITION_ORDER, decisions):
                matched_observation = by_condition.get(condition_id)
                if (not isinstance(decision, Mapping)
                        or set(decision) not in (decision_fields,
                            decision_fields | decision_validation_fields)
                        or decision.get("condition_id") != condition_id
                        or matched_observation is None
                        or decision.get("observation_id") != matched_observation.observation_id
                        or decision.get("observation_digest") != matched_observation.observation_digest
                        or decision.get("inference_receipt_id") != matched_observation.inference_receipt_id
                        or decision.get("inference_receipt_digest") != matched_observation.inference_receipt_digest
                        or decision.get("output_digest") != matched_observation.output_digest
                        or not isinstance(decision.get("response_digest"), str)
                        or len(decision["response_digest"]) != 64
                        or any(char not in "0123456789abcdef"
                            for char in decision["response_digest"])
                        or decision.get("disposition") not in {"answer", "ask", "abstain"}
                        or decision.get("model_disposition") not in {"answer", "ask", "abstain"}
                        or not isinstance(decision.get("evidence_ids"), list)
                        or any(not isinstance(item, str) for item in decision["evidence_ids"])
                        or len(set(decision["evidence_ids"])) != len(decision["evidence_ids"])
                        or not set(decision["evidence_ids"]).issubset(matched_observation.current_fact_ids)
                        or not isinstance(decision.get("history_record_ids"), list)
                        or any(not isinstance(item, str) for item in decision["history_record_ids"])
                        or len(set(decision["history_record_ids"])) != len(decision["history_record_ids"])
                        or not set(decision["history_record_ids"]).issubset(
                            matched_observation.retrieved_record_ids)
                        or (condition_id == "companion-interaction"
                            and tuple(decision["history_record_ids"])
                                != tuple(matched_observation.companion_history_citation_ids))):
                    raise DevelopmentalHistoryInterventionError(
                        "run_artifact_companion_decisions_invalid")
                verified_receipt = verified_invocations.get(condition_id)
                identity = (matched_observation.active_model_identity
                    if isinstance(matched_observation.active_model_identity, Mapping) else {})
                rootless_identity = (bool(identity)
                    and (identity.get("posture") == "rootless_experimental"
                        or (identity.get("engine") == "ollama"
                            and identity.get("posture") == "development_only"
                            and identity.get("fallback") is False
                            and identity.get("candidate_index") == 0)))
                if rootless_identity:
                    if not isinstance(verified_receipt, Mapping):
                        raise DevelopmentalHistoryInterventionError(
                            "run_artifact_companion_invocation_receipt_unverified")
                validation_status = decision.get(
                    "decision_validation_status", "validated")
                output_text = (verified_receipt.get("output_text")
                    if isinstance(verified_receipt, Mapping) else None)
                if output_text is not None:
                    if (not isinstance(output_text, str)
                            or verified_receipt.get("output_truncated") is not False
                            or digest_payload({"output": output_text})
                                != verified_receipt.get("output_digest")
                            or verified_receipt.get("output_size_bytes")
                                != len(output_text.encode("utf-8"))):
                        raise DevelopmentalHistoryInterventionError(
                            "run_artifact_companion_receipt_output_unverified")
                if validation_status == "validated":
                    if output_text is None and rootless_identity:
                        raise DevelopmentalHistoryInterventionError(
                            "run_artifact_companion_receipt_output_unverified")
                    if output_text is not None:
                        try:
                            output_value = json.loads(output_text)
                        except json.JSONDecodeError:
                            output_value = None
                        response = (output_value.get("response")
                            if isinstance(output_value, Mapping) else None)
                        if (not isinstance(response, str)
                                or digest_payload({"text": response})
                                    != decision.get("response_digest")):
                            raise DevelopmentalHistoryInterventionError(
                                "run_artifact_companion_response_digest_unverified")
                elif validation_status == "rejected_invalid_output":
                    rejected_marker_digest = digest_payload(
                        {"text": "INVALID_EXPERIMENTAL_RESPONSE"})
                    if decision.get("response_digest") != rejected_marker_digest:
                        raise DevelopmentalHistoryInterventionError(
                            "run_artifact_rejected_response_marker_unverified")
                validation_error = decision.get(
                    "decision_validation_error_code")
                if validation_status == "rejected_invalid_output":
                    if (not isinstance(validation_error, str)
                            or re.fullmatch(r"[a-z0-9_]{1,120}", validation_error) is None
                            or decision.get("disposition") != "abstain"
                            or decision.get("model_disposition") != "abstain"
                            or decision.get("disposition_normalization")
                                != "invalid_experimental_response_rejected"
                            or decision.get("evidence_ids")
                            or decision.get("history_record_ids")):
                        raise DevelopmentalHistoryInterventionError(
                            "run_artifact_companion_decision_validation_invalid")
                elif (validation_status != "validated" or validation_error is not None):
                    raise DevelopmentalHistoryInterventionError(
                        "run_artifact_companion_decision_validation_invalid")
                normalization = decision.get("disposition_normalization")
                if normalization is None:
                    if decision["model_disposition"] != decision["disposition"]:
                        raise DevelopmentalHistoryInterventionError(
                            "run_artifact_companion_decision_disposition_invalid")
                elif normalization == "history_unavailable_sentinel_means_abstention":
                    if (condition_id != "history_withheld"
                            or decision["model_disposition"] != "answer"
                            or decision["disposition"] != "abstain"
                            or decision["evidence_ids"] or decision["history_record_ids"]):
                        raise DevelopmentalHistoryInterventionError(
                            "run_artifact_companion_decision_normalization_invalid")
                elif (normalization != "invalid_experimental_response_rejected"
                        or validation_status != "rejected_invalid_output"):
                    raise DevelopmentalHistoryInterventionError(
                        "run_artifact_companion_decision_normalization_invalid")
                if (decision["disposition"] == "answer"
                        and not decision["evidence_ids"]
                        and not decision["history_record_ids"]):
                    raise DevelopmentalHistoryInterventionError(
                        "run_artifact_companion_decision_unbound_answer")
        if protocol.schema_version in OBJECTIVE_SCHEMAS:
            if not {"objective_scores", "objective_evaluation"}.issubset(value):
                raise DevelopmentalHistoryInterventionError("objective_scores_missing")
            plan = self.verify_objective_task_plan(protocol)
            scores = value.get("objective_scores")
            if not isinstance(scores, list) or len(scores) != len(CONDITION_ORDER):
                raise DevelopmentalHistoryInterventionError("objective_scores_incomplete")
            from .developmental_model_replacement_experiment import _verify_objective_score
            verified_scores: list[dict[str, Any]] = []
            objective_by_condition = {str(item.get("condition_id")): item for item in conditions
                if isinstance(item, Mapping)}
            for condition_id, wrapper in zip(CONDITION_ORDER, scores):
                observation_payload = objective_by_condition.get(condition_id)
                verified_receipt = verified_invocations.get(condition_id)
                output_truncated = (verified_receipt.get("output_truncated", False)
                    if verified_receipt is not None else False)
                if (not isinstance(wrapper, Mapping)
                        or set(wrapper) not in ({"condition_id", "inference_receipt_id",
                            "inference_receipt_digest", "invocation_output_digest", "score"}
                            , {"condition_id", "inference_receipt_id",
                            "inference_receipt_digest", "invocation_output_digest",
                            "output_truncated", "score"})
                        or wrapper.get("condition_id") != condition_id
                        or wrapper.get("output_truncated", False) is not output_truncated
                        or not isinstance(observation_payload, Mapping)
                        or wrapper.get("inference_receipt_id") != observation_payload.get("inference_receipt_id")
                        or wrapper.get("inference_receipt_digest") != observation_payload.get("inference_receipt_digest")
                        or wrapper.get("invocation_output_digest") != observation_payload.get("output_digest")
                        or not isinstance(wrapper.get("score"), Mapping)):
                    raise DevelopmentalHistoryInterventionError("objective_score_receipt_binding_invalid")
                try:
                    expected_score = _verify_objective_score(plan, wrapper["score"],
                        wrapper["invocation_output_digest"],
                        output_truncated=output_truncated)
                except (KeyError, TypeError, ValueError) as exc:
                    code = ("objective_score_binding_invalid"
                        if "binding_invalid" in str(exc) else "objective_score_invalid")
                    raise DevelopmentalHistoryInterventionError(code) from exc
                checkpoint = self.load_objective_condition_score(protocol,
                    condition_id=condition_id, observation=observation_payload)
                if canonical(checkpoint.get("score")) != canonical(wrapper["score"]):
                    raise DevelopmentalHistoryInterventionError("objective_score_checkpoint_mismatch")
                verified_scores.append(dict(wrapper))
            evaluation = summarize_objective_task(plan, verified_scores,
                include_probe_transitions=(protocol.schema_version in {
                    BALANCED_OBJECTIVE_SCHEDULED_HISTORY_SELECTION_SCHEMA,
                    OBJECTIVE_PROBE_OUTCOMES_SCHEMA,
                    CALIBRATED_OBJECTIVE_SCHEDULED_HISTORY_SCHEMA}),
                include_paired_confidence_comparisons=(protocol.schema_version ==
                    CALIBRATED_OBJECTIVE_SCHEDULED_HISTORY_SCHEMA))
            if canonical(evaluation) != canonical(value.get("objective_evaluation")):
                # Preserve immutable run artifacts written before per-probe
                # answerability was added; the older projection is still
                # independently recomputed from the same verified score rows.
                legacy_evaluation = summarize_objective_task(plan, verified_scores,
                    include_probe_transitions=(protocol.schema_version in {
                        BALANCED_OBJECTIVE_SCHEDULED_HISTORY_SELECTION_SCHEMA,
                        OBJECTIVE_PROBE_OUTCOMES_SCHEMA,
                        CALIBRATED_OBJECTIVE_SCHEDULED_HISTORY_SCHEMA}),
                    include_answerability_transitions=False,
                    include_selective_suite_scoreability=False)
                transitional_evaluation = summarize_objective_task(plan,
                    verified_scores,
                    include_probe_transitions=(protocol.schema_version in {
                        BALANCED_OBJECTIVE_SCHEDULED_HISTORY_SELECTION_SCHEMA,
                        OBJECTIVE_PROBE_OUTCOMES_SCHEMA,
                        CALIBRATED_OBJECTIVE_SCHEDULED_HISTORY_SCHEMA}),
                    include_selective_suite_scoreability=False)
                stored_evaluation = canonical(value.get("objective_evaluation"))
                if (canonical(legacy_evaluation) != stored_evaluation
                        and canonical(transitional_evaluation) != stored_evaluation):
                    raise DevelopmentalHistoryInterventionError(
                        "objective_evaluation_binding_invalid")
        elif "objective_scores" in value or "objective_evaluation" in value:
            raise DevelopmentalHistoryInterventionError("objective_scores_unplanned")
        return value

    def objective_task_family_evidence_binding(self, *, run_id: str,
            expected_run_digest: str, proposition_id: str,
            expected_cohort_id: str | None = None,
            expected_cohort_digest: str | None = None) -> Any:
        """Translate one recovered task-family comparison into bounded evidence.

        The proposition must describe the effect of history presence for the
        exact tested task family.  The run owner verifies the protocol,
        condition receipts, score checkpoints, and evaluator before any binding
        is created.  Deterministic task scoring is retained as a bounded
        experiment outcome: it is never classified as an external observation
        or independent evidence.
        """
        run = self.load_run(run_id)
        if run.get("run_digest") != expected_run_digest:
            raise DevelopmentalHistoryInterventionError("epistemic_run_digest_mismatch")
        protocol_raw = run.get("protocol")
        if not isinstance(protocol_raw, Mapping):
            raise DevelopmentalHistoryInterventionError("epistemic_run_protocol_missing")
        if protocol_raw.get("schema_version") in {
                BALANCED_OBJECTIVE_SCHEDULED_HISTORY_SELECTION_SCHEMA,
                CALIBRATED_OBJECTIVE_SCHEDULED_HISTORY_SCHEMA}:
            if not isinstance(expected_cohort_id, str) or not isinstance(
                    expected_cohort_digest, str):
                raise DevelopmentalHistoryInterventionError(
                    "epistemic_scheduled_run_requires_complete_cohort")
            cohort = self.load_objective_cohort_summary(expected_cohort_id)
            if (cohort.get("cohort_digest") != expected_cohort_digest
                    or not any(member_id == run_id and member_digest == expected_run_digest
                        for member_id, member_digest in zip(
                            cohort.get("run_ids", ()), cohort.get("run_digests", ())))):
                raise DevelopmentalHistoryInterventionError(
                    "epistemic_scheduled_run_cohort_binding_mismatch")
        descriptor = protocol_raw.get("objective_task_descriptor")
        evaluation = run.get("objective_evaluation")
        scores = run.get("objective_scores")
        conditions = run.get("conditions")
        probe_inputs = descriptor.get("probe_inputs") if isinstance(descriptor, Mapping) else None
        def selectively_scoreable() -> bool:
            """Recognize the legacy aggregate posture for verified selective rows."""
            if (not isinstance(evaluation, Mapping)
                    or evaluation.get("assessment") != "unscoreable_missing_output"
                    or evaluation.get("selective_metrics_posture")
                        != "per_probe_abstention_scored_separately_from_correctness"
                    or not isinstance(probe_inputs, list) or not probe_inputs
                    or not isinstance(scores, list)
                    or len(scores) != len(CONDITION_ORDER)):
                return False
            correct_counts, answered_counts, abstained_counts = [], [], []
            for score_row in scores:
                payload = score_row.get("score") if isinstance(score_row, Mapping) else None
                if (not isinstance(payload, Mapping)
                        or payload.get("schema_version")
                            not in {"sentientos.objective_task_score:v5",
                                "sentientos.objective_task_score:v6"}
                        or payload.get("status") not in {"correct", "incorrect", "selective"}
                        or type(payload.get("correct_count")) is not int
                        or type(payload.get("answered_count")) is not int
                        or type(payload.get("abstained_count")) is not int
                        or payload["answered_count"] + payload["abstained_count"]
                            != len(probe_inputs)
                        or not 0 <= payload["correct_count"]
                            <= payload["answered_count"] <= len(probe_inputs)
                        or (payload.get("status") == "selective")
                            != (payload["abstained_count"] > 0)):
                    return False
                results = payload.get("probe_results")
                if not isinstance(results, list) or len(results) != len(probe_inputs):
                    return False
                for probe, result in zip(probe_inputs, results):
                    if (not isinstance(result, Mapping)
                            or result.get("probe_input") != probe
                            or type(result.get("correct")) not in {bool, type(None)}
                            or type(result.get("abstained")) is not bool
                            or result["abstained"] != (result.get("correct") is None)):
                        return False
                correct_counts.append(payload["correct_count"])
                answered_counts.append(payload["answered_count"])
                abstained_counts.append(payload["abstained_count"])
            return (
                evaluation.get("condition_correct_counts") == correct_counts
                and evaluation.get("condition_answered_counts") == answered_counts
                and evaluation.get("condition_abstained_counts") == abstained_counts
                and evaluation.get("probe_count") == len(probe_inputs)
                and evaluation.get("history_correct_probe_delta")
                    == correct_counts[0] - correct_counts[1])
        selectively_scored = selectively_scoreable()
        if (not isinstance(descriptor, Mapping)
                or descriptor.get("family_posture") != "operator_declared_protocol_bound"
                or not isinstance(probe_inputs, list) or not probe_inputs
                or descriptor.get("probe_count") != len(probe_inputs)
                or not isinstance(descriptor.get("task_family_id"), str)
                or not descriptor.get("task_family_id")
                or not isinstance(evaluation, Mapping)
                or (evaluation.get("assessment") != "preregistered_probe_suite_scored"
                    and not selectively_scored)
                or evaluation.get("probe_count") != len(probe_inputs)
                or not isinstance(scores, list) or len(scores) != len(CONDITION_ORDER)
                or not isinstance(conditions, list) or len(conditions) != len(CONDITION_ORDER)):
            raise DevelopmentalHistoryInterventionError("epistemic_task_family_outcome_incomplete")
        counts = evaluation.get("condition_correct_counts")
        probe_count = evaluation.get("probe_count")
        if (not isinstance(counts, list) or len(counts) != len(CONDITION_ORDER)
                or any(type(count) is not int or count < 0 for count in counts)
                or type(probe_count) is not int or probe_count <= 0
                or any(count > probe_count for count in counts)
                or evaluation.get("history_correct_probe_delta") != counts[0] - counts[1]):
            raise DevelopmentalHistoryInterventionError("epistemic_task_family_score_binding_invalid")
        for condition_id, score, observed in zip(CONDITION_ORDER, scores, conditions):
            if (not isinstance(score, Mapping) or score.get("condition_id") != condition_id
                    or not isinstance(score.get("score"), Mapping)
                    or score["score"].get("correct_count") != counts[CONDITION_ORDER.index(condition_id)]
                    or not isinstance(score["score"].get("score_digest"), str)
                    or not isinstance(observed, Mapping) or observed.get("condition_id") != condition_id):
                raise DevelopmentalHistoryInterventionError("epistemic_task_family_score_binding_invalid")
        def probe_outcome_signature(score_row: Mapping[str, Any]
                ) -> tuple[tuple[Any, ...], ...] | None:
            score_payload = score_row.get("score")
            if (isinstance(score_payload, Mapping)
                    and score_payload.get("status") == "invalid_answer"):
                # The scorer deliberately retains no probe values for a
                # malformed answer. Preserve the run as contextual evidence,
                # but do not infer a reproducible probe-level pattern.
                return None
            outcomes = score_payload.get("probe_results") if isinstance(
                score_payload, Mapping) else None
            if not isinstance(outcomes, list) or len(outcomes) != len(probe_inputs):
                raise DevelopmentalHistoryInterventionError(
                    "epistemic_task_family_probe_outcomes_missing")
            signature = []
            for expected_probe, outcome in zip(probe_inputs, outcomes):
                if (not isinstance(outcome, Mapping)
                        or outcome.get("probe_input") != expected_probe
                        or type(outcome.get("correct")) not in {bool, type(None)}
                        or ("abstained" in outcome
                            and type(outcome["abstained"]) is not bool)):
                    raise DevelopmentalHistoryInterventionError(
                        "epistemic_task_family_probe_outcomes_invalid")
                abstained = outcome.get("abstained") is True
                if abstained != (outcome.get("correct") is None):
                    raise DevelopmentalHistoryInterventionError(
                        "epistemic_task_family_probe_outcomes_invalid")
                signature.append((expected_probe, outcome["correct"], abstained))
            return tuple(signature)
        present_signature = probe_outcome_signature(scores[0])
        restored_signature = probe_outcome_signature(scores[2])
        restoration_probe_outcomes_stable = (
            present_signature is not None and restored_signature is not None
            and present_signature == restored_signature)
        observed_times = [row.get("observed_at") for row in conditions]
        if any(not isinstance(value, str) or not value for value in observed_times):
            raise DevelopmentalHistoryInterventionError("epistemic_task_family_event_time_missing")
        # Python treats RFC 3339 -00:00 as UTC, although it means the
        # producer does not know the offset. Do not invent an ordering for a
        # scored run before binding its measured relation to epistemic state.
        if any(value.endswith("-00:00") for value in observed_times):
            raise DevelopmentalHistoryInterventionError(
                "epistemic_task_family_event_time_invalid")
        try:
            instants = [datetime.fromisoformat(value.replace("Z", "+00:00"))
                for value in observed_times]
        except ValueError as exc:
            raise DevelopmentalHistoryInterventionError(
                "epistemic_task_family_event_time_invalid") from exc
        if any(value.tzinfo is None or value.utcoffset() is None for value in instants):
            raise DevelopmentalHistoryInterventionError(
                "epistemic_task_family_event_time_invalid")
        delta = counts[0] - counts[1]
        # A score delta can be directionally informative only when replaying
        # the same history reproduces the per-probe outcome pattern. Otherwise
        # the result remains useful as context, not as support or contradiction.
        relation = ("supports" if delta > 0 else "contradicts" if delta < 0
            else "contextualizes") if restoration_probe_outcomes_stable else "contextualizes"
        from .persistent_epistemic_state import make_evidence_binding
        return make_evidence_binding(
            proposition_id=proposition_id,
            source_artifact_id=run_id,
            source_digest=run["run_digest"],
            source_schema=RUN_SCHEMA,
            source_class="deterministic_task_family_evaluation",
            observation_time=max(instants).isoformat(),
            evidence_relation=relation,
            dependency_kind="unknown_dependency",
            dependency_group=None,
            upstream_binding_ids=(),
            freshness="unknown",
            reliability_posture=(
                "bounded_preregistered_task_family_outcome_not_external_observation"),
        )

    def world_state_records(self, *, run_refs: Sequence[tuple[str, str]]) -> list[dict[str, Any]]:
        """Project explicitly selected completed history trials as historical evidence."""
        from .world_state_board import record_digest

        references = tuple(run_refs)
        if (len(references) > 32 or any(not isinstance(item, tuple) or len(item) != 2
                or any(not isinstance(value, str) or not value for value in item)
                for item in references)
                or len({item[0] for item in references}) != len(references)):
            raise DevelopmentalHistoryInterventionError("run_projection_selection_invalid")
        records: list[dict[str, Any]] = []
        for run_id, expected_run_digest in references:
            run = self.load_run(run_id)
            if run.get("run_digest") != expected_run_digest:
                raise DevelopmentalHistoryInterventionError("run_projection_digest_mismatch")
            protocol_value = run.get("protocol")
            if not isinstance(protocol_value, Mapping):
                raise DevelopmentalHistoryInterventionError("run_projection_protocol_missing")
            protocol = self.load_protocol(str(protocol_value.get("protocol_id") or ""))
            if json.loads(json.dumps(asdict(protocol), sort_keys=True)) != dict(protocol_value):
                raise DevelopmentalHistoryInterventionError("run_projection_protocol_binding_mismatch")
            if (isinstance(protocol.objective_task_descriptor, Mapping)
                    and protocol.objective_task_descriptor.get("task_digest")
                    and protocol.objective_task_descriptor.get("task_digest_posture")
                        != "salted_private_oracle_commitment:v1"):
                # Historical v3 identities remain readable by the custody
                # owner, but their plain oracle hashes must not re-enter a
                # current cognition context through World-State.
                continue
            conditions = run.get("conditions")
            if (not isinstance(conditions, list) or len(conditions) != len(CONDITION_ORDER)
                    or tuple(item.get("condition_id") for item in conditions
                        if isinstance(item, Mapping)) != CONDITION_ORDER):
                raise DevelopmentalHistoryInterventionError("run_projection_conditions_invalid")
            event_times: list[str | None] = []
            all_receipt_times_verified = callable(self._invocation_verifier)
            execution_evidence_conditions: list[dict[str, Any]] = []
            for condition in conditions:
                if not isinstance(condition, Mapping):
                    raise DevelopmentalHistoryInterventionError("run_projection_condition_invalid")
                verified_receipt = None
                if callable(self._invocation_verifier):
                    try:
                        verified_receipt = self._invocation_verifier(condition)
                    except Exception as exc:
                        raise DevelopmentalHistoryInterventionError(
                            "run_projection_invocation_receipt_invalid") from exc
                receipt_matches = (isinstance(verified_receipt, Mapping)
                    and verified_receipt.get("receipt_id")
                        == condition.get("inference_receipt_id")
                    and verified_receipt.get("receipt_digest")
                        == condition.get("inference_receipt_digest"))
                # Rootless development has no serving-session ID. Its exact
                # persisted receipt is still the authoritative event clock;
                # a row timestamp alone is not.
                observed_at = (verified_receipt.get("observed_at")
                    if receipt_matches and isinstance(verified_receipt, Mapping) else None)
                event_times.append(observed_at if isinstance(observed_at, str) else None)
                effects = (verified_receipt.get("effects")
                    if isinstance(verified_receipt, Mapping) else None)
                receipt_status = (verified_receipt.get("status")
                    if isinstance(verified_receipt, Mapping) else None)
                fallback = (verified_receipt.get("fallback_occurred")
                    if isinstance(verified_receipt, Mapping) else None)
                inference_effect = (effects.get("local_model_inference")
                    if isinstance(effects, Mapping) else None)
                if not receipt_matches:
                    execution_posture = "receipt_unbound_or_identity_mismatch"
                elif receipt_status == "admitted_simulation" or inference_effect is False:
                    execution_posture = "receipt_reports_simulation_or_no_backend_entry"
                elif (receipt_status == "admitted_completed" and fallback is False
                        and inference_effect is True):
                    execution_posture = "verified_owner_receipt_reports_backend_entry"
                else:
                    execution_posture = "receipt_does_not_establish_backend_entry"
                execution_evidence_conditions.append({
                    "condition_id": condition.get("condition_id"),
                    "invocation_receipt_id": condition.get("inference_receipt_id"),
                    "invocation_receipt_digest": condition.get("inference_receipt_digest"),
                    "receipt_identity_verified": bool(receipt_matches),
                    "receipt_status": receipt_status,
                    "local_model_inference_effect": inference_effect,
                    "fallback_occurred": fallback,
                    "posture": execution_posture,
                    "independent_backend_observation": False,
                })
                if not receipt_matches or not isinstance(observed_at, str):
                    all_receipt_times_verified = False
                    continue
                if observed_at.endswith("-00:00"):
                    raise DevelopmentalHistoryInterventionError(
                        "run_projection_event_time_invalid")
                try:
                    parsed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
                except ValueError as exc:
                    raise DevelopmentalHistoryInterventionError("run_projection_event_time_invalid") from exc
                if parsed.tzinfo is None:
                    raise DevelopmentalHistoryInterventionError("run_projection_event_time_invalid")
            world_state_event_time: str | None = None
            if all_receipt_times_verified:
                parsed_times = [datetime.fromisoformat(value.replace("Z", "+00:00"))
                    for value in event_times if value is not None]
                if len(parsed_times) == len(CONDITION_ORDER):
                    world_state_event_time = max(parsed_times).isoformat()
            if (len(execution_evidence_conditions) != len(CONDITION_ORDER)
                    or any(item["receipt_identity_verified"] is not True
                        for item in execution_evidence_conditions)):
                execution_evidence_posture = "incomplete_or_unverified_condition_receipts"
            elif all(item["posture"] == "verified_owner_receipt_reports_backend_entry"
                    for item in execution_evidence_conditions):
                execution_evidence_posture = "all_owner_receipts_report_backend_entry"
            elif any(item["posture"] == "receipt_reports_simulation_or_no_backend_entry"
                    for item in execution_evidence_conditions):
                execution_evidence_posture = "one_or_more_conditions_simulated_or_no_backend_entry"
            else:
                execution_evidence_posture = "one_or_more_receipts_do_not_establish_backend_entry"
            objective_scores = run.get("objective_scores")
            objective_evaluation = run.get("objective_evaluation")
            task_descriptor = (dict(protocol.objective_task_descriptor)
                if isinstance(protocol.objective_task_descriptor, Mapping) else None)
            family_scored_experience = (task_descriptor is not None
                and isinstance(task_descriptor.get("task_family_id"), str))
            score_projection = None
            if objective_scores is not None:
                if (not isinstance(objective_scores, list)
                        or len(objective_scores) != len(CONDITION_ORDER)):
                    raise DevelopmentalHistoryInterventionError("run_projection_objective_scores_invalid")
                score_projection = []
                for item in objective_scores:
                    source_score = item["score"]
                    projected_score = {"projection_schema_version":
                            "sentientos.developmental_history_score_projection:v1",
                        "condition_id": item["condition_id"],
                        **({key: source_score[key] for key in (
                            "schema_version", "plan_digest", "task_digest", "output_digest",
                            "evaluator", "confidence_basis_points",
                            "brier_squared_error_sum_basis_points_squared",
                            "brier_scored_answer_count") if key in source_score}
                            if family_scored_experience
                            and item["condition_id"] == "history_present" else {}),
                        "score_digest": source_score["score_digest"],
                        "status": source_score["status"],
                        "correct": source_score["correct"]}
                    if "correct_count" in source_score:
                        projected_score["correct_count"] = source_score["correct_count"]
                        projected_score["probe_count"] = source_score["probe_count"]
                        if "answered_count" in source_score:
                            projected_score["answered_count"] = source_score["answered_count"]
                            projected_score["abstained_count"] = source_score["abstained_count"]
                        if ("probe_results" in source_score
                                and (not family_scored_experience
                                    or len(task_descriptor.get("probe_inputs", ())) <= 3
                                    or item["condition_id"] == "history_present")):
                            # Keep the history-present examples available for
                            # future strategy retrieval. For larger suites,
                            # objective_evaluation already stores the
                            # answer-free per-probe transitions for all three
                            # conditions; duplicating withheld/restored raw
                            # score rows needlessly exceeds the bounded
                            # developmental-history projection.
                            projected_score["probe_results"] = source_score["probe_results"]
                    projected_score["score_projection_digest"] = _digest(projected_score)
                    score_projection.append(projected_score)
            acquisition_examples = None
            if (task_descriptor is not None
                    and isinstance(task_descriptor.get("task_family_id"), str)
                    and score_projection is not None):
                history_score = next((item for item in score_projection
                    if item.get("condition_id") == "history_present"), None)
                if isinstance(history_score, Mapping) and isinstance(
                        history_score.get("probe_results"), list):
                    acquisition_examples = [{
                        "probe_input": item.get("probe_input"),
                        "observed_answer": item.get("observed_answer"),
                        "evaluator_correct": item.get("correct"),
                        "source_score_digest": history_score.get("score_digest"),
                        "source_condition": "history_present",
                    } for item in history_score["probe_results"]]
            run_summary = run.get("summary")
            run_summary = run_summary if isinstance(run_summary, Mapping) else {}
            response_assessment = run_summary.get("companion_response_assessment")
            response_assessment = (response_assessment
                if isinstance(response_assessment, Mapping) else None)
            primary_classification = (response_assessment.get(
                "response_text_classification") if response_assessment is not None
                else run_summary.get("classification"))
            classification_scope = ("response_text"
                if response_assessment is not None else "full_structured_output")
            payload = {
                "run_id": run_id, "run_digest": run["run_digest"],
                "protocol_id": protocol.protocol_id, "protocol_digest": protocol.protocol_digest,
                "protocol_schema_version": protocol.schema_version,
                "record_set_digest": protocol.record_set_digest,
                **({"history_selection_digest": protocol.history_selection_digest}
                    if protocol.schema_version in HISTORY_SELECTION_SCHEMAS else {}),
                "history_record_ids": list(protocol.record_ids),
                "history_record_digests": list(protocol.record_digests),
                "model_id": protocol.model_id,
                "model_artifact_digest": protocol.model_artifact_digest,
                "active_model_identity": dict(protocol.active_model_identity),
                "active_model_identity_digest": protocol.active_model_identity_digest,
                "authority_map_digest": protocol.authority_map_digest,
                "conditions": [{**{key: condition.get(key) for key in (
                    "condition_id", "observation_id", "observation_digest", "output_digest",
                    "request_id", "request_digest", "inference_receipt_id",
                    "inference_receipt_digest", "retrieved_record_ids",
                    "retrieved_record_digests", "serving_session_id", "observed_at")},
                    **({key: condition.get(key) for key in (
                        "model_id", "model_artifact_digest", "authority_map_digest",
                        "developmental_history_selection",
                        "resource_allocation_digest", "resource_attempt_id",
                        "resource_consumption_receipt_digests", "resource_linkage_digest")}
                        if "resource_allocation_digest" in condition else {}),
                    }
                    for condition in conditions],
                "condition_event_times": event_times,
                "event_time_posture": ("all_condition_invocation_receipt_times_verified"
                    if all_receipt_times_verified and world_state_event_time is not None
                    else "historical_event_time_unverified_or_incomplete"),
                "execution_evidence_conditions": execution_evidence_conditions,
                "execution_evidence_posture": execution_evidence_posture,
                "execution_evidence_scope": (
                    "authenticated_owner_receipt_not_independent_backend_observation"),
                "independent_backend_observation": False,
                "primary_classification": primary_classification,
                "classification_scope": classification_scope,
                "full_structured_output_classification": run_summary.get(
                    "classification"),
                "response_text_assessment_posture": (
                    "verified_run_summary" if response_assessment is not None else
                    "legacy_summary_unavailable" if isinstance(
                        run.get("companion_intervention_decisions"), list) else
                    "not_applicable"),
                "history_intervention_summary": run["summary"],
                # Keep the exact, owner-verified decision contrast available to
                # later cognition. The response text stays private; digests,
                # dispositions, and citations remain bound to the observation
                # and invocation receipts validated by load_run().
                "companion_intervention_decisions": run.get(
                    "companion_intervention_decisions"),
                "objective_scores": score_projection,
                "objective_evaluation": objective_evaluation,
                "objective_task_descriptor": task_descriptor,
                "objective_task_commitment_posture": (
                    task_descriptor.get("task_digest_posture")
                    if isinstance(task_descriptor, Mapping) else None),
                "acquisition_examples": acquisition_examples,
                "objective_task_family_id": (protocol.objective_task_descriptor.get("task_family_id")
                    if isinstance(protocol.objective_task_descriptor, Mapping) else None),
                "objective_task_family": (protocol.objective_task_descriptor.get("task_family_id")
                    if isinstance(protocol.objective_task_descriptor, Mapping) else None),
                "task_family_posture": ("operator_declared_protocol_bound"
                    if isinstance(protocol.objective_task_descriptor, Mapping)
                    and protocol.objective_task_descriptor.get("task_family_id") is not None
                    else "not_declared"),
                "claims_posture": "bounded_single_trial_history_association_only",
                "current_truth": False, "authority": False,
                "learning_established": False,
                "reconstruction_time_is_event_time": False,
            }
            # Keep projections bounded while leaving room for scored probe
            # transitions and their evidence bindings in larger preregistered
            # acquisition suites. The source run artifact itself has a
            # separate, stricter canonical-artifact limit.
            if len(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                    ensure_ascii=False).encode("utf-8")) > 65_536:
                raise DevelopmentalHistoryInterventionError("run_projection_payload_over_bound")
            record: dict[str, Any] = {"source_kind": "embodiment",
                "source_id": "developmental-history-run:" + run_id,
                "schema_version": RUN_SCHEMA, "subject_id": run_id,
                "subject_kind": "developmental_history_intervention_experiment",
                "stage": "observation", "disposition": str(
                    primary_classification or "unknown"),
                "evidence_strength": "digest_bound_history_intervention_artifact",
                "payload": payload, "effect_claimed": False, "effect_proven": False,
                "observed_at": world_state_event_time}
            record["digest"] = record_digest(record)
            records.append(record)
        return records


def summarize_objective_cohort(store: DevelopmentalExperimentStore,
        run_ids: Sequence[str], *, include_answerability: bool = True,
        include_calibration: bool = False) -> dict[str, Any]:
    """Aggregate one complete six-order block of verified objective runs.

    The returned measurements remain task- and cohort-scoped. This summary
    does not establish transfer, learning, or model-independent development.
    """
    if (not isinstance(run_ids, Sequence) or isinstance(run_ids, (str, bytes))
            or len(run_ids) != len(BALANCED_CONDITION_ORDERS)
            or any(not isinstance(run_id, str) for run_id in run_ids)
            or len(set(run_ids)) != len(run_ids)):
        raise DevelopmentalHistoryInterventionError("objective_cohort_run_set_invalid")
    trials: list[tuple[int, dict[str, Any], Mapping[str, Any]]] = []
    schedule_claim_digests: dict[int, str] = {}
    binding: tuple[Any, ...] | None = None
    block: int | None = None
    calibrated_protocols: list[bool] = []
    calibrated_task_contracts: list[bool] = []
    for run_id in run_ids:
        run = store.load_run(run_id)
        protocol = run.get("protocol")
        evaluation = run.get("objective_evaluation")
        if not isinstance(protocol, Mapping) or not isinstance(evaluation, Mapping):
            raise DevelopmentalHistoryInterventionError("objective_cohort_run_unscored")
        schema = protocol.get("schema_version")
        calibrated_protocols.append(schema ==
            CALIBRATED_OBJECTIVE_SCHEDULED_HISTORY_SCHEMA)
        index = protocol.get("condition_order_trial_index")
        if (schema not in {BALANCED_OBJECTIVE_SCHEDULED_HISTORY_SELECTION_SCHEMA,
                CALIBRATED_OBJECTIVE_SCHEDULED_HISTORY_SCHEMA}
                or type(index) is not int or index < 0
                or evaluation.get("assessment") != "preregistered_probe_suite_scored"
                or not isinstance(evaluation.get("condition_correct_counts"), list)
                or len(evaluation["condition_correct_counts"]) != len(CONDITION_ORDER)
                or any(type(value) is not int or value < 0
                    for value in evaluation["condition_correct_counts"])):
            raise DevelopmentalHistoryInterventionError("objective_cohort_run_ineligible")
        recovered_protocol = store.load_protocol(str(protocol.get("protocol_id") or ""))
        recovered_plan = store.verify_objective_task_plan(recovered_protocol)
        calibrated_task_contracts.append(recovered_plan.get("task", {}).get(
            "schema_version") in {"sentientos.affine_prediction_task_family_suite:v5",
                "sentientos.affine_prediction_task_family_suite:v6"})
        schedule_claim = store.verify_objective_history_schedule(
            recovered_protocol, required=True)
        if not isinstance(schedule_claim, Mapping):
            raise DevelopmentalHistoryInterventionError(
                "objective_cohort_schedule_claim_missing")
        schedule_claim_digests[index % len(BALANCED_CONDITION_ORDERS)] = str(
            schedule_claim["schedule_digest"])
        current_block = index // len(BALANCED_CONDITION_ORDERS)
        if block is None:
            block = current_block
        if current_block != block:
            raise DevelopmentalHistoryInterventionError("objective_cohort_schedule_block_mismatch")
        descriptor = protocol.get("objective_task_descriptor")
        if not isinstance(descriptor, Mapping):
            raise DevelopmentalHistoryInterventionError("objective_cohort_task_binding_missing")
        current_binding = _objective_cohort_binding_values(protocol)
        objective_history_cohort_binding_digest(protocol)
        if any(value is None for value in current_binding[:11]):
            raise DevelopmentalHistoryInterventionError("objective_cohort_binding_incomplete")
        if binding is None:
            binding = current_binding
        elif current_binding != binding:
            raise DevelopmentalHistoryInterventionError("objective_cohort_binding_mismatch")
        trials.append((index % len(BALANCED_CONDITION_ORDERS), run, protocol))
    trials.sort(key=lambda item: item[0])
    if [item[0] for item in trials] != list(range(len(BALANCED_CONDITION_ORDERS))):
        raise DevelopmentalHistoryInterventionError("objective_cohort_schedule_incomplete")
    if include_calibration and (not all(calibrated_protocols)
            or not all(calibrated_task_contracts)
            or not include_answerability):
        raise DevelopmentalHistoryInterventionError(
            "objective_cohort_calibration_protocol_invalid")
    if not include_calibration and any(calibrated_protocols):
        # Calibration-bearing cohorts use a distinct immutable summary shape.
        # Never silently drop their measurements into an older schema.
        raise DevelopmentalHistoryInterventionError(
            "objective_cohort_calibration_summary_required")
    by_position: dict[str, list[int]] = {condition: [0, 0, 0] for condition in CONDITION_ORDER}
    totals = {condition: 0 for condition in CONDITION_ORDER}
    per_probe: list[dict[str, Any]] | None = None
    probe_count: int | None = None
    calibration_sums = {condition: 0 for condition in CONDITION_ORDER}
    calibration_counts = {condition: 0 for condition in CONDITION_ORDER}
    paired_brier: dict[str, dict[str, Any]] = {
        "history_present_vs_withheld": {
            "first_condition": "history_present",
            "second_condition": "history_withheld"},
        "restored_vs_history_present": {
            "first_condition": "history_restored",
            "second_condition": "history_present"},
    }
    for aggregate in paired_brier.values():
        aggregate.update({"paired_answered_probe_count": 0,
            "first_brier_squared_error_sum_basis_points_squared": 0,
            "second_brier_squared_error_sum_basis_points_squared": 0,
            "trial_differences": []})
    for position, run, protocol in trials:
        evaluation = run["objective_evaluation"]
        counts = evaluation["condition_correct_counts"]
        descriptor = protocol["objective_task_descriptor"]
        this_probe_count = len(descriptor.get("probe_inputs", ()))
        if probe_count is None:
            probe_count = this_probe_count
        if this_probe_count <= 0 or this_probe_count != probe_count or any(
                value > this_probe_count for value in counts):
            raise DevelopmentalHistoryInterventionError("objective_cohort_score_range_invalid")
        if include_calibration:
            brier_sums = evaluation.get(
                "condition_brier_squared_error_sums_basis_points_squared")
            brier_counts = evaluation.get("condition_brier_scored_answer_counts")
            answered_counts = evaluation.get("condition_answered_counts")
            if (not isinstance(brier_sums, list) or len(brier_sums) != len(CONDITION_ORDER)
                    or any(type(value) is not int or value < 0 for value in brier_sums)
                    or not isinstance(brier_counts, list)
                    or len(brier_counts) != len(CONDITION_ORDER)
                    or any(type(value) is not int or value < 0
                        or value > this_probe_count for value in brier_counts)
                    or not isinstance(answered_counts, list)
                    or len(answered_counts) != len(CONDITION_ORDER)
                    or any(type(value) is not int or value < 0
                        or value > this_probe_count for value in answered_counts)
                    or brier_counts != answered_counts
                    or any(score_sum > score_count * 100_000_000
                        for score_sum, score_count in zip(brier_sums, brier_counts))):
                raise DevelopmentalHistoryInterventionError(
                    "objective_cohort_calibration_metrics_missing")
            for condition, score_sum, score_count in zip(
                    CONDITION_ORDER, brier_sums, brier_counts):
                calibration_sums[condition] += score_sum
                calibration_counts[condition] += score_count
            score_rows = run.get("objective_scores")
            if (not isinstance(score_rows, list)
                    or len(score_rows) != len(CONDITION_ORDER)
                    or tuple(row.get("condition_id") for row in score_rows
                        if isinstance(row, Mapping)) != CONDITION_ORDER):
                raise DevelopmentalHistoryInterventionError(
                    "objective_cohort_calibration_scores_missing")
            probe_confidence: dict[str, list[tuple[int, bool] | None]] = {}
            probe_inputs = descriptor.get("probe_inputs")
            if not isinstance(probe_inputs, list) or len(probe_inputs) != this_probe_count:
                raise DevelopmentalHistoryInterventionError(
                    "objective_cohort_calibration_task_invalid")
            for score_row in score_rows:
                score = score_row.get("score")
                results = score.get("probe_results") if isinstance(score, Mapping) else None
                if (not isinstance(score, Mapping)
                        or score.get("schema_version") !=
                            "sentientos.objective_task_score:v6"
                        or not isinstance(results, list)
                        or len(results) != this_probe_count):
                    raise DevelopmentalHistoryInterventionError(
                        "objective_cohort_calibration_score_invalid")
                rows: list[tuple[int, bool] | None] = []
                for expected_probe, result in zip(probe_inputs, results):
                    confidence = (result.get("confidence_basis_points")
                        if isinstance(result, Mapping) else None)
                    correct = result.get("correct") if isinstance(result, Mapping) else None
                    if (not isinstance(result, Mapping)
                            or result.get("probe_input") != expected_probe
                            or (confidence is None and correct is not None)
                            or (confidence is not None and (
                                type(confidence) is not int
                                or not 0 <= confidence <= 10_000
                                or type(correct) is not bool))):
                        raise DevelopmentalHistoryInterventionError(
                            "objective_cohort_calibration_probe_invalid")
                    rows.append((confidence, correct) if confidence is not None else None)
                probe_confidence[str(score_row["condition_id"])] = rows
            for field, aggregate in paired_brier.items():
                first_condition = aggregate["first_condition"]
                second_condition = aggregate["second_condition"]
                first_sum = second_sum = paired_count = 0
                for first, second in zip(probe_confidence[first_condition],
                        probe_confidence[second_condition]):
                    if first is None or second is None:
                        continue
                    first_confidence, first_correct = first
                    second_confidence, second_correct = second
                    first_sum += (first_confidence -
                        (10_000 if first_correct else 0)) ** 2
                    second_sum += (second_confidence -
                        (10_000 if second_correct else 0)) ** 2
                    paired_count += 1
                aggregate["paired_answered_probe_count"] += paired_count
                aggregate[
                    "first_brier_squared_error_sum_basis_points_squared"] += first_sum
                aggregate[
                    "second_brier_squared_error_sum_basis_points_squared"] += second_sum
                aggregate["trial_differences"].append({
                    "trial_index": protocol["condition_order_trial_index"],
                    "paired_answered_probe_count": paired_count,
                    "paired_probe_opportunity_count": this_probe_count,
                    "paired_answer_coverage": paired_count / this_probe_count,
                    "first_brier_squared_error_sum_basis_points_squared": first_sum,
                    "second_brier_squared_error_sum_basis_points_squared": second_sum,
                    "mean_brier_difference": ((first_sum - second_sum)
                        / (paired_count * 100_000_000) if paired_count else None),
                })
        probe_outcomes = evaluation.get("probe_level_outcomes")
        probe_inputs = descriptor.get("probe_inputs")
        if (not isinstance(probe_inputs, list) or len(probe_inputs) != this_probe_count
                or not isinstance(probe_outcomes, Mapping)
                or not isinstance(probe_outcomes.get("probe_outcomes"), list)
                or len(probe_outcomes["probe_outcomes"]) != this_probe_count):
            raise DevelopmentalHistoryInterventionError("objective_cohort_probe_outcomes_missing")
        if per_probe is None:
            per_probe = [{"probe_index": probe_index, "probe_input": probe_input,
                "correct_by_condition": {condition: {"correct": 0, "incorrect": 0,
                    "unscoreable": 0} for condition in CONDITION_ORDER},
                "correct_by_condition_position": {condition: [0, 0, 0]
                    for condition in CONDITION_ORDER},
                "observations_by_condition_position": {condition: [0, 0, 0]
                    for condition in CONDITION_ORDER},
                "abstained_by_condition": {condition: 0 for condition in CONDITION_ORDER},
                "abstained_by_condition_position": {condition: [0, 0, 0]
                    for condition in CONDITION_ORDER},
                "history_present_vs_withheld": {}, "restoration_vs_present": {}}
                for probe_index, probe_input in enumerate(probe_inputs)]
            if include_answerability:
                for outcome in per_probe:
                    outcome.update({
                        "answerable_by_condition": {condition: 0
                            for condition in CONDITION_ORDER},
                        "answerability_observations_by_condition": {
                            condition: 0 for condition in CONDITION_ORDER},
                        "answerable_by_condition_position": {
                            condition: [0, 0, 0] for condition in CONDITION_ORDER},
                        "answerability_observations_by_condition_position": {
                            condition: [0, 0, 0] for condition in CONDITION_ORDER},
                        "history_present_vs_withheld_answerability": {},
                        "restoration_answerability_vs_present": {},
                    })
        for probe_index, (probe_input, outcome) in enumerate(zip(
                probe_inputs, probe_outcomes["probe_outcomes"])):
            if (not isinstance(outcome, Mapping)
                    or outcome.get("probe_index") != probe_index
                    or outcome.get("probe_input") != probe_input
                    or not isinstance(outcome.get("correctness_by_condition"), Mapping)
                    or not isinstance(outcome.get("abstention_by_condition"), Mapping)):
                raise DevelopmentalHistoryInterventionError("objective_cohort_probe_binding_invalid")
            aggregate = per_probe[probe_index]
            answerability_by_condition = outcome.get("answerability_by_condition")
            if include_answerability and not isinstance(answerability_by_condition, Mapping):
                raise DevelopmentalHistoryInterventionError(
                    "objective_cohort_answerability_missing")
            for condition in CONDITION_ORDER:
                correct = outcome["correctness_by_condition"].get(condition)
                abstained = outcome["abstention_by_condition"].get(condition)
                answerable = (answerability_by_condition.get(condition)
                    if include_answerability else None)
                if (type(correct) not in {bool, type(None)}
                        or type(abstained) not in {bool, type(None)}
                        or (include_answerability
                            and type(answerable) not in {bool, type(None)})
                        or (include_answerability
                            and (type(abstained) is bool) != (type(answerable) is bool))
                        or (include_answerability and type(abstained) is bool
                            and answerable is not (not abstained))):
                    raise DevelopmentalHistoryInterventionError("objective_cohort_probe_score_invalid")
                aggregate["correct_by_condition"][condition][
                    "correct" if correct is True else
                    "incorrect" if correct is False else "unscoreable"] += 1
                aggregate["abstained_by_condition"][condition] += int(abstained is True)
                order_position = BALANCED_CONDITION_ORDERS[position].index(condition)
                aggregate["observations_by_condition_position"][condition][order_position] += 1
                if correct is True:
                    aggregate["correct_by_condition_position"][condition][order_position] += 1
                aggregate["abstained_by_condition_position"][condition][order_position] += int(abstained is True)
                if include_answerability and type(answerable) is bool:
                    aggregate["answerability_observations_by_condition"][condition] += 1
                    aggregate["answerable_by_condition"][condition] += int(answerable)
                    aggregate["answerability_observations_by_condition_position"][condition][order_position] += 1
                    aggregate["answerable_by_condition_position"][condition][order_position] += int(answerable)
            for field in ("history_present_vs_withheld", "restoration_vs_present"):
                value = outcome.get(field)
                allowed = ({"no_correctness_change", "history_associated_correctness_gain",
                    "history_associated_correctness_cost", "unscoreable"}
                    if field == "history_present_vs_withheld" else
                    {"matches_history_present", "differs_from_history_present", "unscoreable"})
                if value not in allowed:
                    raise DevelopmentalHistoryInterventionError("objective_cohort_probe_transition_invalid")
                aggregate[field][value] = aggregate[field].get(value, 0) + 1
            if include_answerability:
                for field in ("history_present_vs_withheld_answerability",
                        "restoration_answerability_vs_present"):
                    value = outcome.get(field)
                    allowed = ({"no_answerability_change",
                        "history_associated_answerability_gain",
                        "history_associated_answerability_cost", "unscoreable"}
                        if field == "history_present_vs_withheld_answerability" else
                        {"matches_history_present", "differs_from_history_present",
                            "unscoreable"})
                    if value not in allowed:
                        raise DevelopmentalHistoryInterventionError(
                            "objective_cohort_answerability_transition_invalid")
                    aggregate[field][value] = aggregate[field].get(value, 0) + 1
        order = BALANCED_CONDITION_ORDERS[position]
        score_by_condition = dict(zip(CONDITION_ORDER, counts))
        for condition in CONDITION_ORDER:
            totals[condition] += score_by_condition[condition]
            by_position[condition][order.index(condition)] += score_by_condition[condition]
    assert binding is not None and probe_count is not None and block is not None
    if per_probe is None:
        raise DevelopmentalHistoryInterventionError("objective_cohort_probe_outcomes_missing")
    if any(counts != [2, 2, 2] for outcome in per_probe
            for counts in outcome["observations_by_condition_position"].values()):
        raise DevelopmentalHistoryInterventionError("objective_cohort_position_balance_invalid")
    return {
        "schema_version": ("sentientos.developmental_objective_cohort_summary:v4"
            if include_calibration else
            "sentientos.developmental_objective_cohort_summary:v3"
            if include_answerability else
            "sentientos.developmental_objective_cohort_summary:v2"),
        "run_ids": [item[1]["run_id"] for item in trials],
        "run_digests": [item[1]["run_digest"] for item in trials],
        "protocol_digests": [item[2]["protocol_digest"] for item in trials],
        "schedule_claim_digests": [schedule_claim_digests[item[0]]
            for item in trials],
        "schedule_block": block,
        "trial_indices": [item[2]["condition_order_trial_index"] for item in trials],
        "matched_binding_digest": _digest(list(binding)),
        "task_family_id": binding[8], "task_digest": binding[9],
        "probe_count_per_trial": probe_count,
        "condition_correct_total_across_trials": totals,
        "condition_correct_mean_per_trial": {
            key: totals[key] / len(trials) for key in CONDITION_ORDER},
        "condition_correct_counts_by_position": by_position,
        "per_probe_outcome_counts": per_probe,
        **({
            "condition_brier_squared_error_sum_basis_points_squared":
                calibration_sums,
            "condition_brier_scored_answer_counts": calibration_counts,
            "condition_mean_brier_scores": {
                condition: (calibration_sums[condition]
                    / (calibration_counts[condition] * 100_000_000)
                    if calibration_counts[condition] else None)
                for condition in CONDITION_ORDER},
            "paired_common_answer_brier_comparisons": {
                field: {**aggregate,
                    "paired_probe_opportunity_count": (
                        len(trials) * probe_count),
                    "paired_answer_coverage": (
                        aggregate["paired_answered_probe_count"]
                        / (len(trials) * probe_count)),
                    "mean_brier_difference": (
                        (aggregate[
                            "first_brier_squared_error_sum_basis_points_squared"]
                            - aggregate[
                                "second_brier_squared_error_sum_basis_points_squared"])
                        / (aggregate["paired_answered_probe_count"] * 100_000_000)
                        if aggregate["paired_answered_probe_count"] else None),
                    "direction": "first_condition_minus_second_condition",
                    "posture": "matched_probe_predictions_answered_in_both_conditions"}
                for field, aggregate in paired_brier.items()},
            "calibration_summary_posture":
                "descriptive_answered_predictions_only_not_a_calibration_claim",
        } if include_calibration else {}),
        "interpretation_scope": "verified_same_model_preregistered_task_balanced_cohort",
        "claims_posture": "association_summary_only_no_learning_transfer_or_model_independence_claim",
    }


def summarize(protocol: DevelopmentalHistoryInterventionProtocol,
        observations: Sequence[Any], *,
        companion_intervention_decisions: Sequence[Mapping[str, Any]] | None = None
        ) -> dict[str, Any]:
    if tuple(x.condition_id for x in observations) != CONDITION_ORDER:
        raise DevelopmentalHistoryInterventionError("condition_order_violated")
    # The history condition is the only permitted input difference. The model,
    # current environment, prior self-model, prior epistemic state, authority,
    # and generation settings must remain fixed across all three observations.
    invariant_fields = (
        "tick_id", "model_id", "model_artifact_digest", "authority_map_digest",
        "active_model_identity", "generation_config", "current_snapshot_id",
        "current_snapshot_digest", "current_projection_id", "current_projection_digest",
        "current_fact_ids", "self_model_projection_present", "self_model_projection_id",
        "self_model_projection_digest", "self_model_reconciliation_id",
        "self_model_reconciliation_digest", "self_model_reconciliation_generation",
        "self_model_source_tick", "self_model_claim_ids", "self_model_claim_digests",
        "prior_tick_proven", "epistemic_projection_present", "epistemic_projection_id",
        "epistemic_projection_digest", "epistemic_proposition_ids", "epistemic_state_ids",
        "epistemic_state_digests", "epistemic_generations", "epistemic_evidence_set_digests",
        "serving_session_id", "serving_session_binding",
        "serving_session_receipt_id", "serving_session_receipt_digest",
    )
    full_controls = all(hasattr(item, "current_snapshot_digest")
                        and hasattr(item, "retrieved_record_digests") for item in observations)
    if protocol.schema_version in {SCHEMA, HISTORY_SELECTION_SCHEMA, *OBJECTIVE_SCHEMAS}:
        # Versioned results are only controlled comparisons when each condition is a
        # canonical, digest-bound resident cognition observation.  Do not let a
        # lightweight caller object silently disable the invariant-context
        # checks below while still receiving a controlled classification.
        for item in observations:
            if not hasattr(item, "__dataclass_fields__"):
                raise DevelopmentalHistoryInterventionError("observation_identity_unbound")
            try:
                semantic_observation = asdict(item)
            except (TypeError, ValueError) as exc:
                raise DevelopmentalHistoryInterventionError("observation_identity_unbound") from exc
            observation_id = semantic_observation.pop("observation_id", None)
            observation_digest = semantic_observation.pop("observation_digest", None)
            schema_version = semantic_observation.get("schema_version")
            if schema_version not in {"sentientos.resident_cognition_observation:v7",
                        "sentientos.resident_cognition_observation:v8",
                        "sentientos.resident_cognition_observation:v9",
                        "sentientos.resident_cognition_observation:v10",
                        "sentientos.resident_cognition_observation:v11", "sentientos.resident_cognition_observation:v12",
                        "sentientos.resident_cognition_observation:v13", "sentientos.resident_cognition_observation:v14",
                        "sentientos.resident_cognition_observation:v15"}:
                for field in ("resource_allocation_digest", "resource_attempt_id",
                        "resource_consumption_receipt_digests", "resource_linkage_digest"):
                    semantic_observation.pop(field, None)
            if schema_version not in {"sentientos.resident_cognition_observation:v6",
                    "sentientos.resident_cognition_observation:v7",
                    "sentientos.resident_cognition_observation:v8",
                    "sentientos.resident_cognition_observation:v9",
                    "sentientos.resident_cognition_observation:v10",
                    "sentientos.resident_cognition_observation:v11", "sentientos.resident_cognition_observation:v12",
                        "sentientos.resident_cognition_observation:v13", "sentientos.resident_cognition_observation:v14",
                        "sentientos.resident_cognition_observation:v15"}:
                # The v6 history-selection binding is absent from older
                # canonical observation identities, even though dataclass
                # recovery now supplies its default value.
                semantic_observation.pop("developmental_history_selection", None)
            if schema_version == "sentientos.resident_cognition_observation:v11":
                # v11 added companion self-model citations, but its producer's
                # canonical digest predates the two optional v10 audit fields.
                # They remain on the dataclass for recovery compatibility.
                semantic_observation.pop("developmental_history_context_budget_attempts", None)
                semantic_observation.pop("prior_self_model_prompt_selection", None)
            if schema_version not in {"sentientos.resident_cognition_observation:v8",
                    "sentientos.resident_cognition_observation:v9",
                    "sentientos.resident_cognition_observation:v10",
                    "sentientos.resident_cognition_observation:v11", "sentientos.resident_cognition_observation:v12",
                        "sentientos.resident_cognition_observation:v13", "sentientos.resident_cognition_observation:v14",
                        "sentientos.resident_cognition_observation:v15"}:
                semantic_observation.pop("companion_history_citation_ids", None)
            if schema_version not in {"sentientos.resident_cognition_observation:v9",
                    "sentientos.resident_cognition_observation:v10",
                    "sentientos.resident_cognition_observation:v11", "sentientos.resident_cognition_observation:v12",
                        "sentientos.resident_cognition_observation:v13", "sentientos.resident_cognition_observation:v14",
                        "sentientos.resident_cognition_observation:v15"}:
                for field in ("canonical_user_memory_source_snapshot_digest",
                        "canonical_user_memory_selection_digest",
                        "canonical_user_memory_record_ids",
                        "canonical_user_memory_record_digests",
                        "companion_memory_citation_ids"):
                    semantic_observation.pop(field, None)
            if schema_version not in {"sentientos.resident_cognition_observation:v14",
                    "sentientos.resident_cognition_observation:v15"}:
                # v14 added epistemic-state citations; older canonical
                # identities must not acquire the dataclass's empty default.
                semantic_observation.pop("companion_epistemic_state_citation_ids", None)
            if schema_version != "sentientos.resident_cognition_observation:v15":
                semantic_observation.pop("companion_historical_conversation_citation_ids", None)
                semantic_observation.pop("companion_historical_conversation_citation_digests", None)
            calculated = _digest(semantic_observation)
            if schema_version == "sentientos.resident_cognition_observation:v2":
                semantic_observation.pop("serving_session_id", None)
                semantic_observation.pop("serving_session_binding", None)
                calculated = _digest(semantic_observation)
            if (schema_version not in {"sentientos.resident_cognition_observation:v2",
                        "sentientos.resident_cognition_observation:v3",
                        "sentientos.resident_cognition_observation:v4",
                        "sentientos.resident_cognition_observation:v5",
                        "sentientos.resident_cognition_observation:v6",
                        "sentientos.resident_cognition_observation:v7",
                        "sentientos.resident_cognition_observation:v8",
                        "sentientos.resident_cognition_observation:v9",
                        "sentientos.resident_cognition_observation:v10",
                        "sentientos.resident_cognition_observation:v11", "sentientos.resident_cognition_observation:v12",
                        "sentientos.resident_cognition_observation:v13", "sentientos.resident_cognition_observation:v14",
                        "sentientos.resident_cognition_observation:v15"}
                    or observation_digest != calculated
                    or observation_id != "devcog-" + calculated[7:31]):
                raise DevelopmentalHistoryInterventionError("observation_identity_mismatch")
            if schema_version in {"sentientos.resident_cognition_observation:v6",
                    "sentientos.resident_cognition_observation:v7",
                        "sentientos.resident_cognition_observation:v8",
                        "sentientos.resident_cognition_observation:v9",
                        "sentientos.resident_cognition_observation:v10",
                        "sentientos.resident_cognition_observation:v11", "sentientos.resident_cognition_observation:v12",
                        "sentientos.resident_cognition_observation:v13", "sentientos.resident_cognition_observation:v14",
                        "sentientos.resident_cognition_observation:v15"}:
                selection = semantic_observation.get("developmental_history_selection")
                expected_records = [{"record_id": record_id,
                    "record_digest": record_digest} for record_id, record_digest in zip(
                        protocol.record_ids, protocol.record_digests)]
                task_descriptor = protocol.objective_task_descriptor
                expected_family = (task_descriptor.get("task_family_id")
                    if isinstance(task_descriptor, Mapping) else None)
                expected_treatment = ("withheld" if semantic_observation.get("condition_id")
                    == "history_withheld" else "present")
                if not isinstance(selection, Mapping):
                    raise DevelopmentalHistoryInterventionError(
                        "history_selection_protocol_binding_mismatch")
                if protocol.schema_version in HISTORY_SELECTION_SCHEMAS:
                    available_records = selection.get("available_records")
                    selected_records = selection.get("selected_records")
                    omitted_records = selection.get("omitted_records")
                    selection_protocol_mismatch = (
                        not isinstance(available_records, list)
                        or not isinstance(selected_records, list)
                        or not isinstance(omitted_records, list)
                        or _digest(available_records)
                            != protocol.history_available_records_digest
                        or selected_records != (expected_records
                            if expected_treatment == "present" else [])
                        or omitted_records + selected_records != available_records
                        or selection.get("omitted_records_digest") != _digest(omitted_records)
                        or (expected_treatment == "present"
                            and selection.get("selection_digest")
                                != protocol.history_selection_digest)
                        or selection.get("selection_digest") != _digest({key: value
                            for key, value in selection.items()
                            if key != "selection_digest"}))
                else:
                    selection_protocol_mismatch = (
                        selection.get("available_records") != expected_records)
                if (selection_protocol_mismatch
                        or selection.get("task_family_id") != expected_family
                        or selection.get("treatment") != expected_treatment):
                    raise DevelopmentalHistoryInterventionError(
                        "history_selection_protocol_binding_mismatch")
        if not full_controls:
            raise DevelopmentalHistoryInterventionError("observation_controls_missing")
    if full_controls:
        first_context = tuple(getattr(observations[0], key, None) for key in invariant_fields)
        if any(tuple(getattr(item, key, None) for key in invariant_fields) != first_context
               for item in observations[1:]):
            raise DevelopmentalHistoryInterventionError("non_history_context_changed")
    expected_history = (protocol.record_ids, (), protocol.record_ids)
    expected_digests = (protocol.record_digests, (), protocol.record_digests)
    for observation, record_ids, record_digests in zip(observations, expected_history, expected_digests):
        observed_ids = tuple(getattr(observation, "retrieved_record_ids", ()))
        observed_digests = tuple(getattr(observation, "retrieved_record_digests", ()))
        if (observed_ids != tuple(record_ids)
                or (full_controls and observed_digests != tuple(record_digests))
                or (hasattr(observation, "developmental_projection_present")
                    and getattr(observation, "developmental_projection_present") is not bool(record_ids))):
            raise DevelopmentalHistoryInterventionError("history_condition_binding_mismatch")
    for observation in observations:
        if (getattr(observation, "epistemic_projection_id", None) != protocol.epistemic_projection_id
                or getattr(observation, "epistemic_projection_digest", None) != protocol.epistemic_projection_digest
                or tuple(getattr(observation, "epistemic_state_digests", ())) != protocol.epistemic_state_digests
                or tuple(getattr(observation, "epistemic_evidence_set_digests", ())) != protocol.epistemic_evidence_set_digests):
            raise DevelopmentalHistoryInterventionError("epistemic_experiment_control_changed")
    present, withheld, restored = observations
    first = measure_changed_cognition(with_record=CognitionObservation(present.condition_id, present.observation_id, present.output_digest, present.retrieved_record_ids), without_record=CognitionObservation(withheld.condition_id, withheld.observation_id, withheld.output_digest, ()), expected_record_ids=protocol.record_ids)
    second = measure_changed_cognition(with_record=CognitionObservation(restored.condition_id, restored.observation_id, restored.output_digest, restored.retrieved_record_ids), without_record=CognitionObservation(withheld.condition_id, withheld.observation_id, withheld.output_digest, ()), expected_record_ids=protocol.record_ids)
    stable = present.output_digest == restored.output_digest
    if not first.observable_difference and not second.observable_difference and stable: classification = "no_observable_history_difference"
    elif first.observable_difference and second.observable_difference and stable: classification = "history_presence_associated_stable_difference"
    elif not stable: classification = "history_restoration_unstable_observation"
    else: classification = "mixed_observation"
    summary = {"protocol_id":protocol.protocol_id, "protocol_digest":protocol.protocol_digest,
        "record_set_digest":protocol.record_set_digest, "present_vs_withheld_difference_observed":first.observable_difference,
        "restored_vs_withheld_difference_observed":second.observable_difference, "restored_matches_present":stable,
        "present_restoration_stable":stable, "classification":classification,
        "observation_ids":[x.observation_id for x in observations],
        "observation_digests":[x.observation_digest for x in observations],
        "measurements":[asdict(first), asdict(second)], "claims_posture":"bounded_observed_association_only"}
    if companion_intervention_decisions is not None:
        decisions = companion_intervention_decisions
        if (not isinstance(decisions, Sequence)
                or isinstance(decisions, (str, bytes))
                or len(decisions) != len(CONDITION_ORDER)
                or tuple(row.get("condition_id") if isinstance(row, Mapping) else None
                    for row in decisions) != CONDITION_ORDER):
            raise DevelopmentalHistoryInterventionError(
                "companion_intervention_decisions_invalid")
        decision_summaries = []
        for observation, row in zip(observations, decisions):
            if not isinstance(row, Mapping):
                raise DevelopmentalHistoryInterventionError(
                    "companion_intervention_decision_invalid")
            response_digest = row.get("response_digest")
            if (not isinstance(response_digest, str)
                    or re.fullmatch(r"[0-9a-f]{64}", response_digest) is None):
                raise DevelopmentalHistoryInterventionError(
                    "companion_intervention_response_digest_invalid")
            citations = row.get("history_record_ids")
            retrieved = tuple(getattr(observation, "retrieved_record_ids", ()))
            if (not isinstance(citations, (list, tuple))
                    or any(not isinstance(value, str) for value in citations)
                    or len(set(citations)) != len(citations)):
                raise DevelopmentalHistoryInterventionError(
                    "companion_intervention_history_citations_invalid")
            validation_status = row.get("decision_validation_status", "validated")
            validation_error = row.get("decision_validation_error_code")
            if validation_status not in {"validated", "rejected_invalid_output"}:
                raise DevelopmentalHistoryInterventionError(
                    "companion_intervention_decision_status_invalid")
            decision_summaries.append({
                "condition_id": row["condition_id"],
                "response_digest": response_digest,
                "decision_validation_status": validation_status,
                "decision_validation_error_code": validation_error,
                "history_citation_count": len(citations),
                "history_citations_match_selected_records": (
                    set(citations).issubset(set(retrieved))
                    and (row["condition_id"] != "history_withheld" or not citations)),
            })
        response_digests = [item["response_digest"] for item in decision_summaries]
        decisions_valid = all(item["decision_validation_status"] == "validated"
            and item["decision_validation_error_code"] is None
            for item in decision_summaries)
        citation_bindings_valid = all(item[
            "history_citations_match_selected_records"] for item in decision_summaries)
        response_restoration_stable = (
            decision_summaries[0]["decision_validation_status"] == "validated"
            and decision_summaries[0]["decision_validation_error_code"] is None
            and decision_summaries[2]["decision_validation_status"] == "validated"
            and decision_summaries[2]["decision_validation_error_code"] is None
            and response_digests[0] == response_digests[2])
        response_difference = (response_digests[0] != response_digests[1]
            if decisions_valid else None)
        response_effect_qualified = (decisions_valid and citation_bindings_valid
            and response_restoration_stable and response_difference is True)
        response_classification = (
            "one_or_more_condition_outputs_rejected" if not decisions_valid else
            "history_citation_binding_invalid" if not citation_bindings_valid else
            "history_presence_associated_stable_response_text_difference"
                if response_restoration_stable and response_difference else
            "no_observable_response_text_difference"
                if response_restoration_stable else
            "history_restoration_unstable_response_text")
        summary["companion_response_assessment"] = {
            "schema_version": "sentientos.companion_response_assessment:v1",
            "measurement_scope": "response_text_digest_separate_from_full_output_digest",
            "conditions": decision_summaries,
            "all_decisions_validated": decisions_valid,
            "all_history_citations_match_selected_records": citation_bindings_valid,
            "present_restored_response_digest_matches": response_restoration_stable,
            "present_withheld_response_digest_differs": response_difference,
            "response_text_classification": response_classification,
            "history_associated_response_difference_qualified": (
                response_effect_qualified),
            "performance_improvement_established": False,
            "learning_claim_made": False,
        }
    return summary



def qualify_restoration_stable_history_association(*, validity: Any,
        history_summary: Mapping[str, Any], same_history_replay: Mapping[str, Any],
        present_restoration_delivery_replay: Mapping[str, Any]) -> dict[str, Any]:
    """Qualify one controlled A/B/A history association across both owners.

    The repeat is the history-present/history-restored pair already in the
    A/B/A experiment. It is not an independent repeatability control. This
    qualifier only labels an exact model-output digest difference when the
    restored condition reproduces the present condition and companion delivery
    confirms the same controls and response lineage. It says nothing about
    semantic correctness, learning, or improved task performance.
    """
    base = {"restoration_stable_association_qualified": False,
        "measurement_scope": "exact_model_output_digest_only",
        "independent_repeatability_control_performed": False,
        "performance_improvement_established": False}
    if validity != "valid_controlled_observation":
        return {**base,
            "classification": "not_qualified_controlled_observation_invalid"}

    present_difference = history_summary.get(
        "present_vs_withheld_difference_observed")
    restored_difference = history_summary.get(
        "restored_vs_withheld_difference_observed")
    restored_matches_present = history_summary.get("present_restoration_stable")
    if (present_difference is not True or restored_difference is not True
            or restored_matches_present is not True):
        return {**base,
            "classification": "no_restoration_stable_history_difference"}

    replay_verified = (
        same_history_replay.get("prompt_digest_matches") is True
        and same_history_replay.get("generation_config_matches") is True
        and same_history_replay.get("active_model_identity_matches") is True
        and same_history_replay.get("output_digest_matches") is True
        and present_restoration_delivery_replay.get("input_controls_match") is True
        and present_restoration_delivery_replay.get("output_digest_matches") is True
        and present_restoration_delivery_replay.get("response_digest_matches") is True
        and present_restoration_delivery_replay.get("all_responses_admitted") is True
        and present_restoration_delivery_replay.get(
            "cognition_receipt_output_binding_verified") is True)
    return {**base, "classification": (
            "restoration_stable_history_associated_digest_difference"
            if replay_verified else
            "history_association_not_qualified_by_cross_owner_replay"),
        "restoration_stable_association_qualified": replay_verified}

def qualify_history_transfer_decision(
        *, conditions: Sequence[Mapping[str, Any]],
        expected_history_record_id: str, expected_current_fact_id: str,
        present_response: str, withheld_response: str,
        restored_response: str, restored_prompt_matches: Any) -> dict[str, Any]:
    """Qualify a new decision only with exact current and historical citations.

    This checks A/B/A controls and citations; it does not establish action
    execution, causal learning, or improved performance. An output difference
    without both citation classes is retained as an unqualified observation.
    """
    result = {
        "schema_version": "sentientos.history_transfer_decision_qualification:v5",
        "measurement_scope": "history_conditioned_new_decision_proposal",
        "classification": "not_qualified",
        "controlled_inputs_match": False,
        "matched_non_history_inputs_bound": False,
        "restored_prompt_exact_match": False,
        "target_evidence_cited": False,
        "expected_history_cited": False,
        "history_treatment_bound": False,
        "restoration_stable": False,
        "response_difference_observed": False,
        "restored_response_matches_present": False,
        "history_conditioned_response_difference_observed_under_matched_controls": False,
        "history_changed_new_decision": False,
        "response_text_digest_binding_verified": False,
        "decision_outputs_validated": False,
        "qualification_failure_codes": [],
        "action_executed": False,
        "performance_improvement_established": False,
    }
    if (not isinstance(conditions, Sequence)
            or isinstance(conditions, (str, bytes))):
        result["classification"] = "conditions_or_restoration_not_qualified"
        result["qualification_failure_codes"] = ["conditions_not_sequence"]
        return result
    if (len(conditions) != 3
            or any(not isinstance(row, Mapping) for row in conditions)
            or not isinstance(expected_history_record_id, str)
            or not expected_history_record_id
            or not isinstance(expected_current_fact_id, str)
            or not expected_current_fact_id
            or not all(isinstance(value, str) for value in (
                present_response, withheld_response, restored_response))):
        result["classification"] = "controls_or_restoration_not_qualified"
        result["qualification_failure_codes"] = [
            "conditions_identity_or_restoration_invalid"]
        return result
    present, withheld, restored = conditions
    present_prompt_digest = present.get("prompt_digest")
    restored_prompt_digest = restored.get("prompt_digest")
    prompt_digest_match = (
        _valid_sha256_digest(present_prompt_digest)
        and _valid_sha256_digest(restored_prompt_digest)
        and present_prompt_digest == restored_prompt_digest)
    restored_prompt_exact_match = (
        restored_prompt_matches is True and prompt_digest_match)
    result["restored_prompt_exact_match"] = restored_prompt_exact_match
    if tuple(row.get("condition_id") for row in conditions) != CONDITION_ORDER:
        result["classification"] = "condition_order_invalid"
        result["qualification_failure_codes"] = ["condition_order_invalid"]
        return result
    control_fields = ("current_fact_ids", "snapshot_digest",
        "generation_config", "active_model_identity")
    base_controls_match = all(
        present.get(key) == withheld.get(key) == restored.get(key)
        for key in control_fields)
    matched_input_fields = {
        "schema_version", "question_digest", "snapshot_digest",
        "current_projection_digest", "prior_self_model_digest",
        "prior_epistemic_state_digest", "response_contract",
        "condition_group", "invocation_purpose", "expected_output_format",
        "invocation_budget_digest", "instruction_digest", "response_schema_digest",
        "history_neutral_prompt_digest",
    }
    def valid_matched_inputs(row: Mapping[str, Any]) -> Mapping[str, Any] | None:
        value = row.get("matched_control_inputs")
        if (not isinstance(value, Mapping) or set(value) != matched_input_fields
                or value.get("schema_version")
                    != "sentientos.history_intervention_matched_inputs:v1"
                or row.get("matched_control_inputs_digest") != _digest(dict(value))):
            return None
        return value
    matched_inputs = tuple(valid_matched_inputs(row) for row in conditions)
    matched_inputs_bound = (
        all(value is not None for value in matched_inputs)
        and matched_inputs[0] == matched_inputs[1] == matched_inputs[2])
    controls_match = base_controls_match and matched_inputs_bound
    result["matched_non_history_inputs_bound"] = matched_inputs_bound
    result["controlled_inputs_match"] = controls_match
    def cited_target(row: Mapping[str, Any]) -> bool:
        citations = row.get("evidence_ids")
        current_facts = row.get("current_fact_ids")
        return (isinstance(citations, (list, tuple))
            and isinstance(current_facts, (list, tuple))
            and expected_current_fact_id in citations
            and expected_current_fact_id in current_facts)
    target_cited = all(cited_target(row) for row in conditions)
    result["target_evidence_cited"] = target_cited
    def cited_expected(row: Mapping[str, Any]) -> bool:
        citations = row.get("history_record_ids")
        retrieved = row.get("retrieved_record_ids")
        return (isinstance(citations, (list, tuple))
            and isinstance(retrieved, (list, tuple))
            and tuple(citations) == (expected_history_record_id,)
            and expected_history_record_id in retrieved)
    expected_cited = (cited_expected(present) and cited_expected(restored)
        and not withheld.get("history_record_ids"))
    result["expected_history_cited"] = expected_cited
    def exact_history_treatment(row: Mapping[str, Any], *, present: bool) -> bool:
        retrieved = row.get("retrieved_record_ids")
        if not isinstance(retrieved, (list, tuple)):
            return False
        expected = (expected_history_record_id,) if present else ()
        return tuple(retrieved) == expected
    treatment_bound = (
        exact_history_treatment(present, present=True)
        and exact_history_treatment(withheld, present=False)
        and exact_history_treatment(restored, present=True))
    result["history_treatment_bound"] = treatment_bound
    stable = (present.get("response_digest") == restored.get("response_digest")
        and present.get("output_digest") == restored.get("output_digest"))
    result["restoration_stable"] = stable
    response_difference = present.get("response") != withheld.get("response")
    restored_response_matches = present.get("response") == restored.get("response")
    result["response_difference_observed"] = response_difference
    result["restored_response_matches_present"] = restored_response_matches
    response_text_digest_bound = all(
        isinstance(row.get("response"), str)
        and isinstance(row.get("response_digest"), str)
        and re.fullmatch(r"[0-9a-f]{64}", row["response_digest"]) is not None
        and digest_payload({"text": row["response"]}) == row["response_digest"]
        for row in conditions)
    result["response_text_digest_binding_verified"] = response_text_digest_bound
    decision_outputs_validated = all(
        row.get("decision_validation_status", "validated") == "validated"
        and row.get("decision_validation_error_code") is None
        for row in conditions)
    result["decision_outputs_validated"] = decision_outputs_validated
    outcomes_match_contract = (
        decision_outputs_validated
        and response_text_digest_bound
        and all(row.get("inference_status") == "admitted_completed"
            and row.get("cognition_receipt_output_binding_verified") is True
            for row in conditions)
        and present.get("disposition") == withheld.get("disposition")
            == restored.get("disposition") == "answer"
        and present.get("response") == present_response
        and withheld.get("response") == withheld_response
        and restored.get("response") == restored_response)
    response_effect_observed = (
        controls_match and treatment_bound and stable
        and outcomes_match_contract and response_difference
        and restored_response_matches and restored_prompt_exact_match
        and present_response != withheld_response
        and restored_response == present_response)
    result["history_conditioned_response_difference_observed_under_matched_controls"] = (
        response_effect_observed)
    qualified = (response_effect_observed and target_cited and expected_cited)
    result["history_changed_new_decision"] = qualified
    failures = []
    if not controls_match:
        failures.append("controlled_inputs_mismatch")
    if not restored_prompt_exact_match:
        failures.append("restored_prompt_digest_mismatch")
    if not target_cited:
        failures.append("current_target_evidence_not_cited_in_all_conditions")
    if not expected_cited:
        failures.append("expected_history_record_not_cited_in_present_and_restored")
    if not treatment_bound:
        failures.append("history_retrieval_not_exactly_bound_to_present_restored_arms")
    if not stable or not restored_response_matches:
        failures.append("history_restoration_not_stable")
    if not outcomes_match_contract:
        failures.append("inference_or_response_contract_not_satisfied")
    if not decision_outputs_validated:
        failures.append("decision_output_validation_not_satisfied")
    if not response_text_digest_bound:
        failures.append("response_text_digest_binding_invalid")
    if not response_difference:
        failures.append("no_response_difference_observed")
    result["qualification_failure_codes"] = failures
    result["classification"] = (
        "history_associated_new_decision_difference_exact_record_restored"
        if qualified else (
            "controlled_history_conditioned_response_difference_observed_but_proposal_support_unqualified"
            if response_effect_observed else (
                "response_difference_observed_but_history_treatment_or_controls_unqualified"
                if response_difference else
                "no_validated_new_decision_transfer_difference")))
    return result


def qualify_semantic_history_decision(
    *,
    semantic_decisions: Sequence[Mapping[str, Any]],
    controlled_inputs_match: Any,
    restored_prompt_matches: Any,
    restoration_stable_association_qualified: Any,
) -> dict[str, Any]:
    """Measure a matched history-dependent decision; never infer improvement."""
    result = {
        "schema_version": "sentientos.semantic_history_decision_qualification:v1",
        "measurement_scope": "structured_historical_recall_decision_and_citation",
        "classification": "not_qualified",
        "history_associated_decision_difference_observed": False,
        "history_changed_cognition": False,
        "decision_difference": "not_established",
        "restored_decision_matches_present": False,
        "invalid_condition_ids": [],
        "performance_improvement_established": False,
    }
    if (not isinstance(semantic_decisions, Sequence)
            or isinstance(semantic_decisions, (str, bytes))):
        result["classification"] = "semantic_decisions_invalid"
        return result
    if (controlled_inputs_match is not True or restored_prompt_matches is not True
            or len(semantic_decisions) != 3):
        result["classification"] = "controls_or_restoration_not_qualified"
        return result
    expected = ("history_present", "history_withheld", "history_restored")
    rows = list(semantic_decisions)
    validation_invalid = False
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        validation_status = row.get("decision_validation_status", "validated")
        validation_error = row.get("decision_validation_error_code")
        if (validation_status == "rejected_invalid_output"):
            if (not isinstance(validation_error, str)
                    or re.fullmatch(r"[a-z0-9_]{1,120}", validation_error) is None):
                validation_invalid = True
        elif validation_status != "validated" or validation_error is not None:
            validation_invalid = True
    if validation_invalid:
        result["classification"] = "semantic_decisions_invalid"
        return result
    invalid_condition_ids = [str(row.get("condition_id")) for row in semantic_decisions
        if isinstance(row, Mapping)
        and row.get("decision_validation_status") == "rejected_invalid_output"]
    if invalid_condition_ids:
        result.update({
            "classification": "invalid_condition_response_rejected",
            "invalid_condition_ids": invalid_condition_ids,
        })
        return result
    fields = ("disposition", "answers_with_exact_past_idle_token",
        "abstains_for_unavailable_history", "history_citation_bound")
    if any(not isinstance(row, Mapping) or row.get("condition_id") != condition
            or any(key not in row for key in fields)
            or not isinstance(row.get("disposition"), str)
            or row.get("disposition") not in {"answer", "ask", "abstain"}
            or any(type(row.get(key)) is not bool for key in fields[1:])
            for row, condition in zip(rows, expected)):
        result["classification"] = "semantic_decisions_invalid"
        return result
    present, withheld, restored = rows
    matches = all(present[key] == restored[key] for key in fields)
    result["restored_decision_matches_present"] = matches
    qualifies = (
        matches
        and present["disposition"] == restored["disposition"] == "answer"
        and present["answers_with_exact_past_idle_token"]
        and restored["answers_with_exact_past_idle_token"]
        and present["history_citation_bound"] and restored["history_citation_bound"]
        and not present["abstains_for_unavailable_history"]
        and not restored["abstains_for_unavailable_history"]
        and withheld["disposition"] == "abstain"
        and withheld["abstains_for_unavailable_history"]
        and not withheld["answers_with_exact_past_idle_token"]
        and not withheld["history_citation_bound"])
    if qualifies:
        result["history_associated_decision_difference_observed"] = True
        result["decision_difference"] = "answer_with_history_vs_abstain_without_history"
        if restoration_stable_association_qualified is True:
            result.update({
                "classification": "history_present_answer_with_bound_citation_withheld_abstained_restoration_stable",
                "history_changed_cognition": True,
            })
        else:
            result["classification"] = (
                "history_associated_semantic_decision_difference_observed_repeatability_unqualified")
    elif restoration_stable_association_qualified is not True:
        result["classification"] = "repeatability_not_qualified"
    return result


def _objective_probe_level_outcomes(
        plan: Mapping[str, Any], scores: Sequence[Mapping[str, Any]], *,
        include_answerability_transitions: bool = True) -> dict[str, Any]:
    """Persist answer-free per-probe history contrasts from verified scores."""
    expected_conditions = CONDITION_ORDER
    task = plan.get("task")
    descriptor = plan.get("task_descriptor")
    probes = task.get("probe_inputs") if isinstance(task, Mapping) else None
    task_schema = task.get("schema_version") if isinstance(task, Mapping) else None
    task_digest = descriptor.get("task_digest") if isinstance(descriptor, Mapping) else None
    if (not isinstance(probes, list) or not probes
            or any(type(probe) is not int for probe in probes)
            or len(set(probes)) != len(probes)
            or not _valid_sha256_digest(task_digest)
            or len(scores) != len(expected_conditions)
            or tuple(row.get("condition_id") for row in scores) != expected_conditions):
        raise DevelopmentalHistoryInterventionError(
            "objective_probe_transition_plan_invalid")
    correctness_by_condition: dict[str, list[bool | None] | None] = {}
    abstention_by_condition: dict[str, list[bool | None] | None] = {}
    unavailable: list[str] = []
    score_digests: dict[str, str] = {}
    for row in scores:
        condition_id = str(row["condition_id"])
        score = row.get("score")
        if (not isinstance(score, Mapping)
                or score.get("task_digest") != task_digest
                or type(score.get("probe_count")) is not int
                or score.get("probe_count") != len(probes)
                or score.get("schema_version") not in {
                    "sentientos.objective_task_score:v2",
                    "sentientos.objective_task_score:v3",
                    "sentientos.objective_task_score:v4",
                    "sentientos.objective_task_score:v5",
                    "sentientos.objective_task_score:v6"}
                or (score.get("schema_version") ==
                    "sentientos.objective_task_score:v2"
                    and task_schema != "sentientos.affine_prediction_task_suite:v2")
                or type(score.get("correct_count")) is not int
                    and score.get("status") not in {
                        "output_truncated", "output_unavailable"}
                or not _valid_sha256_digest(score.get("score_digest"))):
            raise DevelopmentalHistoryInterventionError(
                "objective_probe_transition_score_invalid")
        score_digests[condition_id] = str(score["score_digest"])
        status = score.get("status")
        score_schema = score.get("schema_version")
        rows_for_probes = score.get("probe_results")
        if status in {"invalid_answer", "output_truncated", "output_unavailable"}:
            if ((rows_for_probes != []
                    and not (score_schema == "sentientos.objective_task_score:v2"
                        and rows_for_probes is None))
                    or (status == "invalid_answer"
                        and (type(score.get("correct_count")) is not int
                            or score.get("correct_count") != 0))
                    or (status != "invalid_answer"
                        and score.get("correct_count") is not None)
                    or (score_schema in {
                        "sentientos.objective_task_score:v4",
                        "sentientos.objective_task_score:v5",
                        "sentientos.objective_task_score:v6"}
                        and (score.get("answered_count") is not None
                            or score.get("abstained_count") is not None))):
                raise DevelopmentalHistoryInterventionError(
                    "objective_probe_transition_unscoreable_score_invalid")
            correctness_by_condition[condition_id] = None
            abstention_by_condition[condition_id] = None
            unavailable.append(condition_id)
            continue
        if score_schema == "sentientos.objective_task_score:v2":
            answers = score.get("answer")
            multiplier, offset = task.get("multiplier"), task.get("offset")
            if (not isinstance(answers, list) or len(answers) != len(probes)
                    or any(type(answer) is not int for answer in answers)
                    or type(multiplier) is not int or type(offset) is not int):
                raise DevelopmentalHistoryInterventionError(
                    "objective_probe_transition_legacy_answers_invalid")
            rows_for_probes = [{"probe_input": probe,
                "correct": answer == multiplier * probe + offset}
                for probe, answer in zip(probes, answers)]
        if (status not in {"correct", "incorrect", "selective"}
                or not isinstance(rows_for_probes, list)
                or len(rows_for_probes) != len(probes)):
            raise DevelopmentalHistoryInterventionError(
                "objective_probe_transition_rows_invalid")
        correctness: list[bool | None] = []
        abstentions: list[bool] = []
        for probe, result in zip(probes, rows_for_probes):
            abstained = (result.get("abstained", False)
                if isinstance(result, Mapping) else None)
            if (not isinstance(result, Mapping)
                    or type(result.get("probe_input")) is not int
                    or result.get("probe_input") != probe
                    or type(result.get("correct")) not in {bool, type(None)}
                    or type(abstained) is not bool
                    or abstained != (result.get("correct") is None)):
                raise DevelopmentalHistoryInterventionError(
                    "objective_probe_transition_row_invalid")
            correctness.append(result["correct"])
            abstentions.append(abstained)
        if (type(score.get("correct_count")) is not int
                or not 0 <= score["correct_count"] <= len(probes)
                or sum(value is True for value in correctness)
                    != score.get("correct_count")):
            raise DevelopmentalHistoryInterventionError(
                "objective_probe_transition_count_mismatch")
        observed_abstained_count = sum(abstentions)
        if score_schema in {
                "sentientos.objective_task_score:v2",
                "sentientos.objective_task_score:v3"}:
            if (observed_abstained_count
                    or status != ("correct" if score["correct_count"] == len(probes)
                        else "incorrect")):
                raise DevelopmentalHistoryInterventionError(
                    "objective_probe_transition_status_mismatch")
        else:
            answered_count = score.get("answered_count")
            abstained_count = score.get("abstained_count")
            if (type(answered_count) is not int
                    or type(abstained_count) is not int
                    or answered_count != len(probes) - observed_abstained_count
                    or abstained_count != observed_abstained_count):
                raise DevelopmentalHistoryInterventionError(
                    "objective_probe_transition_selective_counts_invalid")
            all_correct = score["correct_count"] == len(probes)
            expected_status = (
                "selective" if score_schema in {
                    "sentientos.objective_task_score:v5",
                    "sentientos.objective_task_score:v6"}
                    and observed_abstained_count else
                "correct" if all_correct and not observed_abstained_count else
                "incorrect")
            if status != expected_status:
                raise DevelopmentalHistoryInterventionError(
                    "objective_probe_transition_status_mismatch")
        correctness_by_condition[condition_id] = correctness
        abstention_by_condition[condition_id] = abstentions
    outcomes: list[dict[str, Any]] = []
    for index, probe in enumerate(probes):
        abstention_values = {
            condition: (abstention_by_condition[condition][index]
                if abstention_by_condition[condition] is not None else None)
            for condition in expected_conditions}
        answerability = {
            condition: (not abstained if type(abstained) is bool else None)
            for condition, abstained in abstention_values.items()}
        present, withheld, restored = (
            correctness_by_condition[condition][index]
            if correctness_by_condition[condition] is not None else None
            for condition in expected_conditions)
        transition = ("unscoreable" if type(present) is not bool
                or type(withheld) is not bool else
            "no_correctness_change" if present == withheld else
            "history_associated_correctness_gain" if present else
            "history_associated_correctness_cost")
        restoration = ("unscoreable" if type(present) is not bool
                or type(restored) is not bool else
            "matches_history_present" if present == restored else
            "differs_from_history_present")
        present_answerable = answerability[expected_conditions[0]]
        withheld_answerable = answerability[expected_conditions[1]]
        restored_answerable = answerability[expected_conditions[2]]
        # These labels encode direction of answerability only; they do not
        # rank answering above abstaining or assign utility to either choice.
        answerability_transition = (
            "unscoreable" if type(present_answerable) is not bool
                or type(withheld_answerable) is not bool else
            "no_answerability_change" if present_answerable == withheld_answerable else
            "history_associated_answerability_gain" if present_answerable else
            "history_associated_answerability_cost")
        answerability_restoration = (
            "unscoreable" if type(present_answerable) is not bool
                or type(restored_answerable) is not bool else
            "matches_history_present" if present_answerable == restored_answerable else
            "differs_from_history_present")
        outcome = {
            "probe_index": index,
            "probe_input": probe,
            "correctness_by_condition": {
                condition: (correctness_by_condition[condition][index]
                    if correctness_by_condition[condition] is not None else None)
                for condition in expected_conditions},
            "abstention_by_condition": abstention_values,
            "history_present_vs_withheld": transition,
            "restoration_vs_present": restoration,
        }
        if include_answerability_transitions:
            outcome.update({
                "answerability_by_condition": answerability,
                "history_present_vs_withheld_answerability": answerability_transition,
                "restoration_answerability_vs_present": answerability_restoration,
            })
        outcomes.append(outcome)
    return {
        "condition_order": list(expected_conditions),
        "task_digest": task_digest,
        "condition_score_digests": score_digests,
        "probe_outcomes": outcomes,
        "unscoreable_condition_ids": unavailable,
        "posture": ("partial_per_probe_outcomes_unscoreable_conditions"
            if unavailable else
            "independent_oracle_correctness_only_answer_values_omitted"),
    }


def summarize_objective_task(plan: Mapping[str, Any], scores: Sequence[Mapping[str, Any]], *,
        include_probe_transitions: bool = False,
        include_answerability_transitions: bool = True,
        include_selective_suite_scoreability: bool = True,
        include_paired_confidence_comparisons: bool = False) -> dict[str, Any]:
    """Measure correctness separately from output-digest differences."""
    if (len(scores) != len(CONDITION_ORDER)
            or tuple(row.get("condition_id") for row in scores) != CONDITION_ORDER):
        raise DevelopmentalHistoryInterventionError("objective_scores_incomplete")
    correctness = [row["score"].get("correct") if isinstance(row.get("score"), Mapping) else None
        for row in scores]
    complete = all(type(value) is bool for value in correctness)
    truncated = any(isinstance(row.get("score"), Mapping)
        and row["score"].get("status") == "output_truncated" for row in scores)
    delta = ((1 if correctness[0] is True else 0) - (1 if correctness[1] is True else 0)
        if complete else None)
    restored_stable = correctness[0] == correctness[2] if complete else None
    evaluation = {"plan_digest": plan.get("plan_digest"),
        "condition_score_digests": [row["score"].get("score_digest")
            for row in scores if isinstance(row.get("score"), Mapping)],
        "history_accuracy_delta": delta,
        "restoration_correctness_stable": restored_stable,
        "assessment": ("single_preregistered_task_scored" if complete else
            "unscoreable_truncated_output" if truncated else "unscoreable_missing_output"),
        "scope": "same_model_task_correctness_not_general_learning_or_weight_change",
        "model_behavior_posture": "resident_endpoint_receipts_not_independent_model_attestation"}
    if plan.get("task", {}).get("schema_version") in {
            "sentientos.affine_prediction_task_suite:v2",
            "sentientos.affine_prediction_task_family_suite:v3",
            "sentientos.affine_prediction_task_family_suite:v4",
            "sentientos.affine_prediction_task_family_suite:v5",
            "sentientos.affine_prediction_task_family_suite:v6"}:
        counts = [row["score"].get("correct_count")
            if isinstance(row.get("score"), Mapping) else None for row in scores]
        count_complete = len(counts) == 3 and all(type(value) is int for value in counts)
        # A selective suite can have no aggregate Boolean `correct` value
        # while every probe still has a verified correct/abstained outcome.
        # Scoreability follows the per-condition score rows, not that aggregate.
        probe_suite_scoreable = (len(scores) == len(CONDITION_ORDER)
            and all(isinstance(row.get("score"), Mapping)
                and row["score"].get("status") in {
                    "correct", "incorrect", "selective"}
                and type(row["score"].get("correct_count")) is int
                for row in scores))
        if not include_selective_suite_scoreability:
            probe_suite_scoreable = complete
        history_delta = (cast(int, counts[0]) - cast(int, counts[1])
            if count_complete else None)
        restoration_delta = (cast(int, counts[0]) - cast(int, counts[2])
            if count_complete else None)
        evaluation.update({"probe_count": len(plan["task"]["probe_inputs"]),
            "condition_correct_counts": counts,
            "history_correct_probe_delta": history_delta,
            "restoration_correct_probe_delta": restoration_delta,
            "assessment": ("preregistered_probe_suite_scored" if probe_suite_scoreable else
                "unscoreable_truncated_output" if truncated else "unscoreable_missing_output")})
        if plan.get("task", {}).get("schema_version") == (
                "sentientos.affine_prediction_task_family_suite:v4") or (
                plan.get("task", {}).get("schema_version") ==
                    "sentientos.affine_prediction_task_family_suite:v5") or (
            plan.get("task", {}).get("schema_version") ==
                "sentientos.affine_prediction_task_family_suite:v6"):
            answered = [row["score"].get("answered_count")
                if isinstance(row.get("score"), Mapping) else None for row in scores]
            abstained = [row["score"].get("abstained_count")
                if isinstance(row.get("score"), Mapping) else None for row in scores]
            probe_count = len(plan["task"]["probe_inputs"])
            coherent = (len(answered) == 3 and len(abstained) == 3
                and all(type(answered[index]) is int and type(abstained[index]) is int
                    and cast(int, answered[index]) + cast(int, abstained[index]) == probe_count
                    for index in range(3)))
            answered_values = cast(list[int], answered) if coherent else []
            abstained_values = cast(list[int], abstained) if coherent else []
            correct_counts = cast(list[int], counts) if coherent and count_complete else []
            evaluation.update({
                "condition_answered_counts": answered_values if coherent else None,
                "condition_abstained_counts": abstained_values if coherent else None,
                "condition_coverage": ([value / probe_count
                    for value in answered_values] if coherent else None),
                "condition_selective_accuracy": ([
                    (correct_counts[index] / value if value > 0 else None)
                    for index, value in enumerate(answered_values)]
                    if coherent and count_complete else None),
                "selective_metrics_posture":
                    "per_probe_abstention_scored_separately_from_correctness",
            })
        if plan.get("task", {}).get("schema_version") == (
                "sentientos.affine_prediction_task_family_suite:v5") or (
                plan.get("task", {}).get("schema_version") ==
                    "sentientos.affine_prediction_task_family_suite:v6"):
            brier_sums = [row["score"].get(
                "brier_squared_error_sum_basis_points_squared")
                if isinstance(row.get("score"), Mapping) else None
                for row in scores]
            brier_counts = [row["score"].get("brier_scored_answer_count")
                if isinstance(row.get("score"), Mapping) else None
                for row in scores]
            brier_coherent = (all(type(value) is int and value >= 0
                    for value in brier_sums)
                and all(type(value) is int and value >= 0
                    for value in brier_counts))
            evaluation.update({
                "condition_brier_squared_error_sums_basis_points_squared": (
                    brier_sums if brier_coherent else None),
                "condition_brier_scored_answer_counts": (
                    brier_counts if brier_coherent else None),
                "condition_mean_brier_scores": ([
                    brier_sums[index] / (brier_counts[index] * 100_000_000)
                    if brier_counts[index] else None
                    for index in range(len(CONDITION_ORDER))]
                    if brier_coherent else None),
                "calibration_metric_posture":
                    "per_condition_descriptive_brier_over_confidence_scored_answers"})
            if include_paired_confidence_comparisons:
                paired_specs = {
                    "history_present_vs_withheld": (0, 1),
                    "restored_vs_history_present": (2, 0),
                }
                paired_comparisons: dict[str, dict[str, Any]] = {}
                probes = plan["task"].get("probe_inputs", ())
                if (not isinstance(probes, (list, tuple)) or not probes
                        or any(type(probe) is not int for probe in probes)):
                    raise DevelopmentalHistoryInterventionError(
                        "objective_calibration_probe_plan_invalid")
                for name, (first_index, second_index) in paired_specs.items():
                    paired_rows: list[tuple[tuple[int, bool], tuple[int, bool]]] = []
                    for first, second in zip(
                            scores[first_index]["score"].get("probe_results", ()),
                            scores[second_index]["score"].get("probe_results", ())):
                        if (not isinstance(first, Mapping)
                                or not isinstance(second, Mapping)
                                or first.get("probe_input") != second.get("probe_input")):
                            continue
                        first_confidence = first.get("confidence_basis_points")
                        second_confidence = second.get("confidence_basis_points")
                        first_correct, second_correct = first.get("correct"), second.get("correct")
                        if (type(first_confidence) is int
                                and 0 <= first_confidence <= 10_000
                                and type(second_confidence) is int
                                and 0 <= second_confidence <= 10_000
                                and type(first_correct) is bool
                                and type(second_correct) is bool):
                            paired_rows.append(((first_confidence, first_correct),
                                (second_confidence, second_correct)))
                    first_sum = sum((confidence - (10_000 if correct else 0)) ** 2
                        for (confidence, correct), _ in paired_rows)
                    second_sum = sum((confidence - (10_000 if correct else 0)) ** 2
                        for _, (confidence, correct) in paired_rows)
                    count = len(paired_rows)
                    paired_comparisons[name] = {
                        "first_condition": CONDITION_ORDER[first_index],
                        "second_condition": CONDITION_ORDER[second_index],
                        "probe_count": len(probes),
                        "paired_answered_probe_count": count,
                        "paired_answer_coverage": count / len(probes),
                        "first_brier_squared_error_sum_basis_points_squared": first_sum,
                        "second_brier_squared_error_sum_basis_points_squared": second_sum,
                        "first_minus_second_mean_brier_score": (
                            (first_sum - second_sum) / (count * 100_000_000)
                            if count else None),
                    }
                evaluation["paired_common_answer_brier_comparisons"] = {
                    "posture": "paired_answered_probe_comparison_not_a_calibration_diagnostic",
                    "comparisons": paired_comparisons}
    if (include_probe_transitions
            and isinstance(plan.get("task"), Mapping)
            and plan["task"].get("schema_version") in {
                "sentientos.affine_prediction_task_suite:v2",
                "sentientos.affine_prediction_task_family_suite:v3",
                "sentientos.affine_prediction_task_family_suite:v4",
                "sentientos.affine_prediction_task_family_suite:v5",
                "sentientos.affine_prediction_task_family_suite:v6"}):
        evaluation["probe_level_outcomes"] = _objective_probe_level_outcomes(
            plan, scores,
            include_answerability_transitions=include_answerability_transitions)
    return evaluation
