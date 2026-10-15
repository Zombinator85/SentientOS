"""Preregistered, non-destructive developmental-history projection experiment."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, cast

from .local_model_authority import digest_payload
from .canonical_memory import sentientos_memory_dir
from .resident_developmental_writeback import (
    CognitionObservation, DevelopmentalHistoryProjection, measure_changed_cognition,
    DevelopmentalWritebackError, _open_store_directory, _read_store_file, _publish_store_json,
)
from .windows_handle_custody import WindowsHandleCustodyError, read_explicit_file

LEGACY_SCHEMA = "sentientos.developmental_history_intervention_protocol:v1"
SCHEMA = "sentientos.developmental_history_intervention_protocol:v2"
LEGACY_OBJECTIVE_SCHEMA = "sentientos.developmental_history_intervention_protocol:v3"
OBJECTIVE_SCHEMA = "sentientos.developmental_history_intervention_protocol:v4"
HISTORY_SELECTION_SCHEMA = "sentientos.developmental_history_intervention_protocol:v5"
OBJECTIVE_HISTORY_SELECTION_SCHEMA = "sentientos.developmental_history_intervention_protocol:v6"
OBJECTIVE_SCHEMAS = frozenset({LEGACY_OBJECTIVE_SCHEMA, OBJECTIVE_SCHEMA,
    OBJECTIVE_HISTORY_SELECTION_SCHEMA})
HISTORY_SELECTION_SCHEMAS = frozenset({HISTORY_SELECTION_SCHEMA,
    OBJECTIVE_HISTORY_SELECTION_SCHEMA})
RUN_SCHEMA = "sentientos.developmental_history_intervention_run:v1"
PURPOSE = "resident_developmental_history_intervention_experiment"
CONDITION_ORDER = ("history_present", "history_withheld", "history_restored")
NON_CLAIMS = ("learning", "improvement", "persistent_individuality", "selfhood", "consciousness", "sentience", "causal_closure")
MAX_EXPERIMENT_ARTIFACT_BYTES = 4_194_304


class DevelopmentalHistoryInterventionError(ValueError):
    pass


def _digest(value: Any) -> str:
    return "sha256:" + str(digest_payload(value))


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
    grants_authority: bool = False
    schema_version: str = SCHEMA

    def semantic_payload(self) -> dict[str, Any]:
        value = asdict(self); value.pop("protocol_id"); value.pop("protocol_digest")
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
        return value


def make_protocol(**kwargs: Any) -> DevelopmentalHistoryInterventionProtocol:
    raw = DevelopmentalHistoryInterventionProtocol("", "", condition_order=CONDITION_ORDER,
        inference_purpose=PURPOSE, planned_comparisons=("present_vs_withheld", "restored_vs_withheld"),
        non_claims=NON_CLAIMS, **kwargs)
    digest = _digest(raw.semantic_payload())
    return replace(raw, protocol_id="devexp-protocol-" + digest[7:31], protocol_digest=digest)


def verify_protocol(protocol: DevelopmentalHistoryInterventionProtocol) -> None:
    digest = _digest(protocol.semantic_payload())
    if protocol.protocol_digest != digest or protocol.protocol_id != "devexp-protocol-" + digest[7:31]:
        raise DevelopmentalHistoryInterventionError("protocol_digest_mismatch")
    if (protocol.schema_version not in {LEGACY_SCHEMA, SCHEMA,
            HISTORY_SELECTION_SCHEMA, *OBJECTIVE_SCHEMAS}
            or protocol.condition_order != CONDITION_ORDER or protocol.inference_purpose != PURPOSE
            or protocol.grants_authority):
        raise DevelopmentalHistoryInterventionError("protocol_control_invalid")
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
                raw = read_explicit_file(path, max_bytes=MAX_EXPERIMENT_ARTIFACT_BYTES)
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

    @classmethod
    def _write_immutable(cls, path: Path, payload: Mapping[str, Any]) -> None:
        normalized = json.loads(json.dumps(dict(payload), sort_keys=True))
        try:
            existing = cls._read_json(path)
        except FileNotFoundError:
            existing = None
        if existing is not None:
            if existing != normalized:
                raise DevelopmentalHistoryInterventionError("artifact_identity_collision")
            return
        if os.name != "posix":
            raise DevelopmentalHistoryInterventionError("experiment_artifact_publication_unsupported_platform")
        try:
            _publish_store_json(path, payload, collision_error="artifact_identity_collision",
                                max_bytes=MAX_EXPERIMENT_ARTIFACT_BYTES)
        except DevelopmentalWritebackError as exc:
            if str(exc) == "artifact_identity_collision":
                raise DevelopmentalHistoryInterventionError("artifact_identity_collision") from exc
            raise DevelopmentalHistoryInterventionError("experiment_artifact_publication_failed") from exc

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

    def persist_objective_task_plan(self, protocol: DevelopmentalHistoryInterventionProtocol,
                                    task: Any) -> dict[str, Any]:
        """Durably freeze the independent oracle before the first condition runs."""
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
            "sentientos.affine_prediction_task_family_suite:v3"}
        semantic = {"schema_version": ("sentientos.objective_task_plan:v1"
                if protocol.schema_version == LEGACY_OBJECTIVE_SCHEMA
                else "sentientos.objective_task_plan:v2"),
            "protocol_id": protocol.protocol_id, "protocol_digest": protocol.protocol_digest,
            "task": dict(specification), "task_descriptor": dict(descriptor),
            "condition_order": list(CONDITION_ORDER),
            "rubric": "exact_integer_answer_suite_v2" if suite else "exact_integer_answer_v1",
            "authority": False}
        if protocol.schema_version in {OBJECTIVE_SCHEMA, OBJECTIVE_HISTORY_SELECTION_SCHEMA}:
            semantic["task_commitment_nonce"] = task.commitment_nonce
            public_semantic = {key: value for key, value in semantic.items()
                if key not in {"task", "task_commitment_nonce"}}
        else:
            public_semantic = semantic
        plan = {**semantic, "plan_digest": _digest(public_semantic)}
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
        if protocol.schema_version in {OBJECTIVE_SCHEMA, OBJECTIVE_HISTORY_SELECTION_SCHEMA}:
            expected.add("task_commitment_nonce")
        if set(value) != expected:
            raise DevelopmentalHistoryInterventionError("objective_task_plan_invalid")
        semantic = dict(value); claimed = semantic.pop("plan_digest")
        if protocol.schema_version in {OBJECTIVE_SCHEMA, OBJECTIVE_HISTORY_SELECTION_SCHEMA}:
            public_semantic = {key: item for key, item in semantic.items()
                if key not in {"task", "task_commitment_nonce"}}
        else:
            public_semantic = semantic
        task = value.get("task")
        suite = isinstance(task, Mapping) and task.get("schema_version") == (
            "sentientos.affine_prediction_task_suite:v2") or (
            isinstance(task, Mapping) and task.get("schema_version") ==
                "sentientos.affine_prediction_task_family_suite:v3")
        expected_plan_schema = ("sentientos.objective_task_plan:v1"
            if protocol.schema_version == LEGACY_OBJECTIVE_SCHEMA
            else "sentientos.objective_task_plan:v2")
        if (value.get("schema_version") != expected_plan_schema
                or value.get("protocol_id") != protocol.protocol_id
                or value.get("protocol_digest") != protocol.protocol_digest
                or value.get("condition_order") != list(CONDITION_ORDER)
                or value.get("rubric") != ("exact_integer_answer_suite_v2" if suite
                    else "exact_integer_answer_v1")
                or value.get("authority") is not False
                or claimed != _digest(public_semantic)):
            raise DevelopmentalHistoryInterventionError("objective_task_plan_binding_invalid")
        expected_task_fields = ({"schema_version", "multiplier", "offset", "probe_inputs", "oracle_scope"}
            if suite else {"schema_version", "multiplier", "offset", "probe_input", "oracle_scope"})
        if isinstance(task, Mapping) and task.get("schema_version") == (
                "sentientos.affine_prediction_task_family_suite:v3"):
            expected_task_fields.update({"task_family_id", "requires_task_family_history"})
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
                        if protocol.schema_version in {OBJECTIVE_SCHEMA, OBJECTIVE_HISTORY_SELECTION_SCHEMA} else {}))
            else:
                reconstructed = ObjectivePredictionTask(task["multiplier"], task["offset"], task["probe_input"],
                    **({"commitment_nonce": value["task_commitment_nonce"]}
                        if protocol.schema_version in {OBJECTIVE_SCHEMA, OBJECTIVE_HISTORY_SELECTION_SCHEMA} else {}))
            reconstructed_descriptor = (reconstructed.legacy_public_descriptor()
                if protocol.schema_version == LEGACY_OBJECTIVE_SCHEMA
                else reconstructed.public_descriptor())
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
        path = self.protocols / f"objective-score-{protocol.protocol_id}-{condition_id}.json"
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
        try:
            value = self._read_json(self.protocols /
                f"objective-score-{protocol.protocol_id}-{condition_id}.json")
        except FileNotFoundError as exc:
            raise DevelopmentalHistoryInterventionError("objective_condition_score_missing") from exc
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
        return protocol

    def persist_run(self, payload: Mapping[str, Any]) -> str:
        semantic = dict(payload); semantic["schema_version"] = RUN_SCHEMA
        digest = _digest(semantic); run_id = "devexp-run-" + digest[7:31]
        self._write_immutable(self.runs / f"{run_id}.json", {**semantic, "run_id": run_id, "run_digest": digest})
        return run_id

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
        if (value.get("schema_version") != RUN_SCHEMA or value.get("run_id") != run_id
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
        if (not set(value).issubset(expected_fields | {"objective_scores", "objective_evaluation",
                    "contamination_assessment"})
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
            observations = []
            for raw_observation in conditions:
                if not isinstance(raw_observation, Mapping):
                    raise TypeError("condition_observation_invalid")
                raw_condition_payload = dict(raw_observation)
                for key in observation_tuple_fields:
                    if key in raw_condition_payload:
                        raw_condition_payload[key] = tuple(raw_condition_payload[key])
                observations.append(ResidentCognitionObservation(**raw_condition_payload))
            recomputed = summarize(protocol, observations)
        except (KeyError, TypeError, ValueError) as exc:
            raise DevelopmentalHistoryInterventionError("run_artifact_control_invalid") from exc
        verified_invocations: dict[str, Mapping[str, Any]] = {}
        for observation in observations:
            if observation.serving_session_id is None:
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
        def canonical(item: object) -> str:
            return json.dumps(item, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False)
        if canonical(recomputed) != canonical(value["summary"]):
            raise DevelopmentalHistoryInterventionError("run_artifact_summary_mismatch")
        if protocol.schema_version in OBJECTIVE_SCHEMAS:
            if not {"objective_scores", "objective_evaluation"}.issubset(value):
                raise DevelopmentalHistoryInterventionError("objective_scores_missing")
            plan = self.verify_objective_task_plan(protocol)
            scores = value.get("objective_scores")
            if not isinstance(scores, list) or len(scores) != len(CONDITION_ORDER):
                raise DevelopmentalHistoryInterventionError("objective_scores_incomplete")
            from .developmental_model_replacement_experiment import _verify_objective_score
            verified_scores: list[dict[str, Any]] = []
            by_condition = {str(item.get("condition_id")): item for item in conditions
                if isinstance(item, Mapping)}
            for condition_id, wrapper in zip(CONDITION_ORDER, scores):
                observation_payload = by_condition.get(condition_id)
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
            evaluation = summarize_objective_task(plan, verified_scores)
            if canonical(evaluation) != canonical(value.get("objective_evaluation")):
                raise DevelopmentalHistoryInterventionError("objective_evaluation_binding_invalid")
        elif "objective_scores" in value or "objective_evaluation" in value:
            raise DevelopmentalHistoryInterventionError("objective_scores_unplanned")
        return value

    def objective_task_family_evidence_binding(self, *, run_id: str,
            expected_run_digest: str, proposition_id: str) -> Any:
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
        descriptor = protocol_raw.get("objective_task_descriptor")
        evaluation = run.get("objective_evaluation")
        scores = run.get("objective_scores")
        conditions = run.get("conditions")
        probe_inputs = descriptor.get("probe_inputs") if isinstance(descriptor, Mapping) else None
        if (not isinstance(descriptor, Mapping)
                or descriptor.get("family_posture") != "operator_declared_protocol_bound"
                or not isinstance(probe_inputs, list) or not probe_inputs
                or descriptor.get("probe_count") != len(probe_inputs)
                or not isinstance(descriptor.get("task_family_id"), str)
                or not descriptor.get("task_family_id")
                or not isinstance(evaluation, Mapping)
                or evaluation.get("assessment") != "preregistered_probe_suite_scored"
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
        observed_times = [row.get("observed_at") for row in conditions]
        if any(not isinstance(value, str) or not value for value in observed_times):
            raise DevelopmentalHistoryInterventionError("epistemic_task_family_event_time_missing")
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
        relation = "supports" if delta > 0 else "contradicts" if delta < 0 else "contextualizes"
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
                observed_at = condition.get("observed_at")
                event_times.append(observed_at if isinstance(observed_at, str) else None)
                verified_receipt = None
                if condition.get("serving_session_id") is not None and callable(
                        self._invocation_verifier):
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
                if (condition.get("serving_session_id") is None
                        or not isinstance(observed_at, str)):
                    all_receipt_times_verified = False
                    continue
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
                score_projection = [{"condition_id": item["condition_id"],
                    **({key: item["score"][key] for key in (
                        "schema_version", "plan_digest", "task_digest", "output_digest",
                        "evaluator") if key in item["score"]}
                        if family_scored_experience
                        and item["condition_id"] == "history_present" else {}),
                    "score_digest": item["score"]["score_digest"],
                    "status": item["score"]["status"],
                    "correct": item["score"]["correct"],
                    **({"correct_count": item["score"]["correct_count"],
                        "probe_count": item["score"]["probe_count"],
                        **({"probe_results": item["score"]["probe_results"]}
                            if "probe_results" in item["score"] else {})}
                        if "correct_count" in item["score"] else {})}
                    for item in objective_scores]
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
                        "active_model_identity", "developmental_history_selection",
                        "resource_allocation_digest", "resource_attempt_id",
                        "resource_consumption_receipt_digests", "resource_linkage_digest")}
                        if "resource_allocation_digest" in condition else {})}
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
                "history_intervention_summary": run["summary"],
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
            if len(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                    ensure_ascii=False).encode("utf-8")) > 32_768:
                raise DevelopmentalHistoryInterventionError("run_projection_payload_over_bound")
            record: dict[str, Any] = {"source_kind": "embodiment",
                "source_id": "developmental-history-run:" + run_id,
                "schema_version": RUN_SCHEMA, "subject_id": run_id,
                "subject_kind": "developmental_history_intervention_experiment",
                "stage": "observation", "disposition": str(run["summary"].get("classification") or "unknown"),
                "evidence_strength": "digest_bound_history_intervention_artifact",
                "payload": payload, "effect_claimed": False, "effect_proven": False,
                "observed_at": world_state_event_time}
            record["digest"] = record_digest(record)
            records.append(record)
        return records


def summarize(protocol: DevelopmentalHistoryInterventionProtocol, observations: Sequence[Any]) -> dict[str, Any]:
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
            if schema_version != "sentientos.resident_cognition_observation:v7":
                for field in ("resource_allocation_digest", "resource_attempt_id",
                        "resource_consumption_receipt_digests", "resource_linkage_digest"):
                    semantic_observation.pop(field, None)
            if schema_version not in {"sentientos.resident_cognition_observation:v6",
                    "sentientos.resident_cognition_observation:v7"}:
                # The v6 history-selection binding is absent from older
                # canonical observation identities, even though dataclass
                # recovery now supplies its default value.
                semantic_observation.pop("developmental_history_selection", None)
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
                        "sentientos.resident_cognition_observation:v7"}
                    or observation_digest != calculated
                    or observation_id != "devcog-" + calculated[7:31]):
                raise DevelopmentalHistoryInterventionError("observation_identity_mismatch")
            if schema_version in {"sentientos.resident_cognition_observation:v6",
                    "sentientos.resident_cognition_observation:v7"}:
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
    elif not stable: classification = "unstable_or_order_sensitive_observation"
    else: classification = "mixed_observation"
    return {"protocol_id":protocol.protocol_id, "protocol_digest":protocol.protocol_digest,
        "record_set_digest":protocol.record_set_digest, "present_vs_withheld_difference_observed":first.observable_difference,
        "restored_vs_withheld_difference_observed":second.observable_difference, "restored_matches_present":stable,
        "present_restoration_stable":stable, "classification":classification,
        "observation_ids":[x.observation_id for x in observations],
        "observation_digests":[x.observation_digest for x in observations],
        "measurements":[asdict(first), asdict(second)], "claims_posture":"bounded_observed_association_only"}


def summarize_objective_task(plan: Mapping[str, Any], scores: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
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
            "sentientos.affine_prediction_task_family_suite:v3"}:
        counts = [row["score"].get("correct_count")
            if isinstance(row.get("score"), Mapping) else None for row in scores]
        count_complete = len(counts) == 3 and all(type(value) is int for value in counts)
        history_delta = (cast(int, counts[0]) - cast(int, counts[1])
            if count_complete else None)
        restoration_delta = (cast(int, counts[0]) - cast(int, counts[2])
            if count_complete else None)
        evaluation.update({"probe_count": len(plan["task"]["probe_inputs"]),
            "condition_correct_counts": counts,
            "history_correct_probe_delta": history_delta,
            "restoration_correct_probe_delta": restoration_delta,
            "assessment": ("preregistered_probe_suite_scored" if complete else
                "unscoreable_truncated_output" if truncated else "unscoreable_missing_output")})
    return evaluation
