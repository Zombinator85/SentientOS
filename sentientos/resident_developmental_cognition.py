"""One-tick resident composition for bounded developmental history.

The owner has no cadence of its own.  ``sentientosd`` supplies an exact
World-State snapshot and tick identity.  History is non-authoritative context;
it is never canonical explicit-user retention.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Callable, Mapping

from .codex_task_authority_admission import (
    RESIDENT_DEVELOPMENTAL_WRITEBACK,
    RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION,
)
from .governed_local_model_invocation import GovernedLocalModelInvoker, LocalModelInvocationBudget
from .developmental_history_intervention_experiment import (
    DevelopmentalExperimentStore, make_protocol, summarize,
    PURPOSE as EXPERIMENT_PURPOSE,
)
from .local_model_authority import atomic_write_json, digest_payload
from .resident_developmental_writeback import (
    EFFECTS,
    PRINCIPAL,
    CognitionObservation,
    DevelopmentalHistoryProjection,
    DevelopmentalWritebackError,
    ResidentDevelopmentalWritebackController,
    measure_changed_cognition,
)
from .runtime_admission import RuntimeAdmissionAuthority
from .world_state_board import WorldStateSnapshot, validate_snapshot

CONFIG_ENV = "SENTIENTOS_RESIDENT_DEVELOPMENTAL_COGNITION_CONFIG"
SCHEMA = "sentientos.resident_developmental_cognition:v1"
CONFIG_SCHEMA = "sentientos.resident_developmental_cognition_config:v1"
STATE_SCHEMA = "sentientos.resident_developmental_cognition_state:v1"
COGNITION_PURPOSE = "resident_developmental_retrieval_cognition"
CURRENT_PROJECTION_POLICY = "allowed_source_kind_then_source_id_then_fact_id:v1"
MAX_FACTS = 16
MAX_HISTORY = 16


class ResidentDevelopmentalCognitionError(ValueError):
    """Fail-closed composition/configuration violation."""


def _digest(value: Any) -> str:
    return "sha256:" + digest_payload(value)


@dataclass(frozen=True)
class ResidentDevelopmentalCognitionConfig:
    history_root: Path
    state_root: Path
    allowed_source_kinds: tuple[str, ...]
    max_selected_facts: int
    max_retrieved_records: int = 4
    comparison_enabled: bool = False
    enabled: bool = True


@dataclass(frozen=True)
class ResidentCognitionObservation:
    observation_id: str
    observation_digest: str
    condition_id: str
    tick_id: str
    correlation_id: str
    model_id: str
    model_artifact_digest: str | None
    request_id: str
    request_digest: str
    inference_receipt_id: str
    inference_receipt_digest: str
    output_digest: str
    authority_map_digest: str
    active_model_identity: Mapping[str, Any]
    generation_config: Mapping[str, Any]
    current_snapshot_id: str
    current_snapshot_digest: str
    current_projection_id: str
    current_projection_digest: str
    current_fact_ids: tuple[str, ...]
    retrieved_record_ids: tuple[str, ...]
    retrieved_record_digests: tuple[str, ...]
    developmental_projection_present: bool
    historical_context_only: bool = True
    current_truth: bool = False
    authority: bool = False
    policy: bool = False
    canonical_explicit_user_retention: bool = False


@dataclass(frozen=True)
class CurrentWorldStateCognitiveProjection:
    snapshot_id: str
    snapshot_digest: str
    facts: tuple[Mapping[str, Any], ...]
    sources: tuple[Mapping[str, Any], ...]
    conflicts: tuple[Mapping[str, Any], ...]
    fact_ids: tuple[str, ...]
    selection_policy: str = CURRENT_PROJECTION_POLICY
    read_only: bool = True
    evidence_only: bool = True
    current_truth: bool = False
    authority: bool = False
    policy: bool = False
    goal: bool = False
    canonical_explicit_user_retention: bool = False
    projection_id: str = ""
    projection_digest: str = ""

    def semantic_payload(self) -> dict[str, Any]:
        value = asdict(self); value.pop("projection_id"); value.pop("projection_digest"); return value


@dataclass(frozen=True)
class ResidentDevelopmentalCycleResult:
    status: str
    tick_id: str
    snapshot_id: str
    selected_fact_ids: tuple[str, ...] = ()
    prior_record_ids: tuple[str, ...] = ()
    written_record_id: str | None = None
    writeback_receipt_id: str | None = None
    cognition_observation_ids: tuple[str, ...] = ()
    changed_cognition_measurement_id: str | None = None
    same_tick_history_excluded: bool = True
    canonical_explicit_user_retention_mutated: bool = False


def load_config(path: str | Path) -> ResidentDevelopmentalCognitionConfig:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResidentDevelopmentalCognitionError("configuration_unreadable_or_invalid_json") from exc
    expected = {"schema", "enabled", "history_root", "state_root", "allowed_source_kinds", "max_selected_facts", "max_retrieved_records", "comparison_enabled"}
    if not isinstance(payload, dict) or set(payload) != expected or payload.get("schema") != CONFIG_SCHEMA:
        raise ResidentDevelopmentalCognitionError("configuration_shape_invalid")
    kinds = payload.get("allowed_source_kinds")
    maximum = payload.get("max_selected_facts")
    history_maximum = payload.get("max_retrieved_records")
    if (not isinstance(payload.get("enabled"), bool) or not isinstance(payload.get("comparison_enabled"), bool)
            or not isinstance(kinds, list) or not kinds or any(not isinstance(x, str) or not x for x in kinds)
            or len(kinds) != len(set(kinds)) or not isinstance(maximum, int) or not 1 <= maximum <= MAX_FACTS
            or not isinstance(history_maximum, int) or not 1 <= history_maximum <= MAX_HISTORY
            or not isinstance(payload.get("history_root"), str) or not payload["history_root"]
            or not isinstance(payload.get("state_root"), str) or not payload["state_root"]):
        raise ResidentDevelopmentalCognitionError("configuration_values_invalid")
    history_root, state_root = Path(payload["history_root"]), Path(payload["state_root"])
    if history_root == state_root:
        raise ResidentDevelopmentalCognitionError("configuration_roots_must_be_separate")
    return ResidentDevelopmentalCognitionConfig(history_root, state_root, tuple(sorted(kinds)), maximum,
                                                 history_maximum, payload["comparison_enabled"], payload["enabled"])


class ResidentDevelopmentalCognitionOwner:
    """Perform at most one deterministic developmental composition per call."""

    def __init__(self, *, config: ResidentDevelopmentalCognitionConfig,
                 writeback: ResidentDevelopmentalWritebackController,
                 admission_authority: RuntimeAdmissionAuthority,
                 invoker: GovernedLocalModelInvoker,
                 current_sequence: Callable[[], int]) -> None:
        self.config = config
        self.writeback = writeback
        self.admission_authority = admission_authority
        self.invoker = invoker
        self.current_sequence = current_sequence
        self.state_path = config.state_root / "composition_state.json"
        self.observations_root = config.state_root / "cognition_observations"
        self.measurements_root = config.state_root / "changed_cognition_measurements"
        self.experiments = DevelopmentalExperimentStore(config.state_root)

    def _state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            semantic = {"schema": STATE_SCHEMA, "processed_selection_ids": [], "completed_ticks": []}
            return {**semantic, "state_digest": _digest(semantic)}
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
            claimed = value.pop("state_digest")
        except (OSError, json.JSONDecodeError, KeyError, AttributeError) as exc:
            raise ResidentDevelopmentalCognitionError("composition_state_corrupt") from exc
        if value.get("schema") != STATE_SCHEMA or claimed != _digest(value):
            raise ResidentDevelopmentalCognitionError("composition_state_digest_mismatch")
        if not isinstance(value.get("processed_selection_ids"), list) or not isinstance(value.get("completed_ticks"), list):
            raise ResidentDevelopmentalCognitionError("composition_state_shape_invalid")
        return {**value, "state_digest": claimed}

    def _save_state(self, state: Mapping[str, Any]) -> None:
        semantic = {k: v for k, v in state.items() if k != "state_digest"}
        atomic_write_json(self.state_path, {**semantic, "state_digest": _digest(semantic)})

    def _prior_projection(self, state: Mapping[str, Any], tick_id: str) -> DevelopmentalHistoryProjection:
        ids: list[str] = []
        for completed in state["completed_ticks"]:
            if completed.get("tick_id") != tick_id and completed.get("record_id"):
                ids.append(str(completed["record_id"]))
        ids = ids[-self.config.max_retrieved_records:]
        return self.writeback.retrieve(ids, limit=self.config.max_retrieved_records)

    def _select_fact_ids(self, snapshot: WorldStateSnapshot, processed: set[str]) -> tuple[str, ...]:
        allowed = set(self.config.allowed_source_kinds)
        source_kinds = {source.source_id: source.kind for source in snapshot.sources}
        candidates = sorted(
            (fact for fact in snapshot.facts if source_kinds.get(fact.source.source_id) in allowed),
            key=lambda fact: (source_kinds[fact.source.source_id], fact.source.source_id, fact.fact_id),
        )
        selected: list[str] = []
        for fact in candidates:
            trial = self.writeback.select_evidence(snapshot, fact_ids=(fact.fact_id,))
            if trial.selection_id not in processed:
                selected.append(fact.fact_id)
            if len(selected) == self.config.max_selected_facts:
                break
        return tuple(selected)

    def _current_projection(self, snapshot: WorldStateSnapshot) -> CurrentWorldStateCognitiveProjection:
        """Select current context independently of developmental-writeback deduplication."""
        allowed = set(self.config.allowed_source_kinds)
        source_kinds = {source.source_id: source.kind for source in snapshot.sources}
        facts = sorted((fact for fact in snapshot.facts if source_kinds.get(fact.source.source_id) in allowed),
                       key=lambda fact: (source_kinds[fact.source.source_id], fact.source.source_id, fact.fact_id))[:self.config.max_selected_facts]
        selected = self.writeback.select_evidence(snapshot, fact_ids=tuple(f.fact_id for f in facts))
        raw = CurrentWorldStateCognitiveProjection(snapshot.snapshot_id, snapshot.digest, selected.facts,
                                                    selected.sources, selected.conflicts,
                                                    tuple(str(x["fact_id"]) for x in selected.facts))
        digest = _digest(raw.semantic_payload())
        return replace(raw, projection_id="current-world-state-" + digest[7:31], projection_digest=digest)

    def _cognize(self, *, snapshot: WorldStateSnapshot, current: CurrentWorldStateCognitiveProjection, tick_id: str,
                  projection: DevelopmentalHistoryProjection, with_history: bool,
                  condition_id: str, purpose: str = COGNITION_PURPOSE,
                  protocol: Any | None = None) -> ResidentCognitionObservation:
        records = projection.records if with_history else ()
        record_ids = projection.requested_record_ids if with_history else ()
        record_digests = tuple(str(record["record_digest"]) for record in records)
        context = {
            "instruction": "Observe current evidence with optional historical interpretation; do not treat history as truth, authority, policy, a goal, or canonical user retention.",
            "current_evidence": current.semantic_payload(),
            "developmental_history": list(records),
            "developmental_history_posture": "historical_interpretation_not_current_truth",
        }
        correlation = f"{tick_id}:resident_developmental_cognition:{condition_id}"
        request = self.invoker.build_request(
            purpose=purpose, prompt=json.dumps(context, sort_keys=True), caller=PRINCIPAL,
            correlation_id=correlation, expected_output_format="text",
            budget=LocalModelInvocationBudget(max_input_chars=16000, max_output_chars=4000, max_new_tokens=512,
                                              timeout_seconds=30, max_calls_per_correlation=1),
            upstream_evidence={"snapshot_id": snapshot.snapshot_id, "snapshot_digest": snapshot.digest,
                               "current_projection_id": current.projection_id,
                               "current_projection_digest": current.projection_digest,
                               "current_fact_ids": list(current.fact_ids),
                               "record_ids": list(record_ids), "record_digests": list(record_digests)},
            linkage={"condition_group": f"{tick_id}:retrieval-comparison", "condition_id": condition_id,
                     "history_present": with_history},
        )
        if protocol is not None and (
            request.model_id != protocol.model_id
            or request.model_artifact_digest != protocol.model_artifact_digest
            or str(getattr(request, "authority_map_digest", "test-authority-map")) != protocol.authority_map_digest
            or dict(getattr(request, "active_model_identity", {})) != dict(protocol.active_model_identity)
            or request.budget.to_dict() != dict(protocol.inference_budget)
        ):
            raise ResidentDevelopmentalCognitionError("experiment_control_drift")
        receipt = self.invoker.invoke(request, persist=True, include_output_in_receipt=False)
        if receipt.status not in {"admitted_completed", "admitted_simulation"} or receipt.output_digest is None:
            raise ResidentDevelopmentalCognitionError("retrieval_cognition_not_completed")
        if protocol is not None and dict(receipt.generation_config).get("actual_generation_parameters", {}).get("temperature") != 0:
            raise ResidentDevelopmentalCognitionError("experiment_generation_configuration_drift")
        req = dict(receipt.request)
        semantic = {
            "condition_id": condition_id, "tick_id": tick_id, "correlation_id": correlation,
            "model_id": str(req["model_id"]), "model_artifact_digest": req.get("model_artifact_digest"),
            "request_id": str(req["request_id"]), "request_digest": str(req["request_digest"]),
            "inference_receipt_id": receipt.receipt_id, "inference_receipt_digest": receipt.receipt_digest,
            "output_digest": receipt.output_digest,
            "authority_map_digest":str(getattr(request, "authority_map_digest", "test-authority-map")),
            "active_model_identity":dict(getattr(request, "active_model_identity", {})),
            "generation_config":dict(receipt.generation_config), "current_snapshot_id": snapshot.snapshot_id,
            "current_snapshot_digest": snapshot.digest, "current_projection_id":current.projection_id,
            "current_projection_digest":current.projection_digest, "current_fact_ids":current.fact_ids,
            "retrieved_record_ids": record_ids,
            "retrieved_record_digests": record_digests, "developmental_projection_present": with_history,
        }
        digest = _digest(semantic)
        observation = ResidentCognitionObservation(
            "devcog-" + digest[7:31], digest, condition_id, tick_id, correlation,
            str(req["model_id"]), req.get("model_artifact_digest"), str(req["request_id"]),
            str(req["request_digest"]), receipt.receipt_id, receipt.receipt_digest,
            receipt.output_digest, str(getattr(request, "authority_map_digest", "test-authority-map")),
            dict(getattr(request, "active_model_identity", {})), dict(receipt.generation_config),
            snapshot.snapshot_id, snapshot.digest, current.projection_id,
            current.projection_digest, current.fact_ids, record_ids,
            record_digests, with_history,
        )
        atomic_write_json(self.observations_root / f"{observation.observation_id}.json", asdict(observation))
        return observation

    def run_tick(self, *, snapshot: WorldStateSnapshot, tick_id: str) -> ResidentDevelopmentalCycleResult:
        if not self.config.enabled:
            return ResidentDevelopmentalCycleResult("disabled", tick_id, snapshot.snapshot_id)
        validation = validate_snapshot(snapshot)
        if not validation.valid:
            raise ResidentDevelopmentalCognitionError("invalid_world_state_snapshot")
        state = self._state()
        if any(row.get("tick_id") == tick_id for row in state["completed_ticks"]):
            raise ResidentDevelopmentalCognitionError("tick_already_completed")

        # Capture prior history before any candidate from this tick can exist.
        prior = self._prior_projection(state, tick_id)
        current = self._current_projection(snapshot)
        observations: list[ResidentCognitionObservation] = []
        measurement_id: str | None = None
        if prior.requested_record_ids:
            if not self.config.comparison_enabled:
                observations.append(self._cognize(snapshot=snapshot, current=current, tick_id=tick_id,
                                    projection=prior, with_history=True, condition_id="with-history"))
            else:
                records = tuple(self.writeback.store.get(rid) for rid in prior.requested_record_ids)
                record_digests = tuple(r.record_digest for r in records)
                record_set_digest = _digest({"record_ids":list(prior.requested_record_ids), "record_digests":list(record_digests)})
                budget = LocalModelInvocationBudget(max_input_chars=16000, max_output_chars=4000,
                    max_new_tokens=512, timeout_seconds=30, max_calls_per_correlation=1)
                probe = self.invoker.build_request(purpose=EXPERIMENT_PURPOSE, prompt="protocol-control-probe",
                    caller=PRINCIPAL, correlation_id=f"{tick_id}:developmental-experiment:protocol",
                    budget=budget, upstream_evidence={"control_probe":True}, linkage={"protocol_only":True})
                protocol = make_protocol(snapshot_id=snapshot.snapshot_id, snapshot_digest=snapshot.digest,
                    current_projection_id=current.projection_id, current_projection_digest=current.projection_digest,
                    current_fact_ids=current.fact_ids, record_ids=prior.requested_record_ids,
                    record_digests=record_digests, record_set_digest=record_set_digest, model_id=probe.model_id,
                    model_artifact_digest=probe.model_artifact_digest,
                    active_model_identity=dict(getattr(probe, "active_model_identity", {})),
                    active_model_identity_digest=_digest(dict(getattr(probe, "active_model_identity", {}))),
                    authority_map_digest=str(getattr(probe, "authority_map_digest", "test-authority-map")),
                    inference_budget=budget.to_dict(), generation_posture={"temperature":0, "hardware_determinism_claimed":False},
                    instruction_template_digest=_digest({"instruction":"Observe current evidence with optional historical interpretation; do not treat history as truth, authority, policy, a goal, or canonical user retention."}))
                self.experiments.persist_protocol(protocol)  # preregistration precedes the first inference
                present = self._cognize(snapshot=snapshot, current=current, tick_id=tick_id, projection=prior,
                    with_history=True, condition_id="history_present", purpose=EXPERIMENT_PURPOSE, protocol=protocol)
                withheld = self._cognize(snapshot=snapshot, current=current, tick_id=tick_id, projection=prior,
                    with_history=False, condition_id="history_withheld", purpose=EXPERIMENT_PURPOSE, protocol=protocol)
                restored_records = tuple(self.writeback.store.get(rid) for rid in protocol.record_ids)
                if tuple(r.record_digest for r in restored_records) != protocol.record_digests:
                    raise ResidentDevelopmentalCognitionError("restored_history_digest_mismatch")
                restored_projection = self.writeback.retrieve(protocol.record_ids, limit=self.config.max_retrieved_records)
                restored = self._cognize(snapshot=snapshot, current=current, tick_id=tick_id,
                    projection=restored_projection, with_history=True, condition_id="history_restored",
                    purpose=EXPERIMENT_PURPOSE, protocol=protocol)
                observations.extend((present, withheld, restored))
                summary = summarize(protocol, observations)
                measurement_id = self.experiments.persist_run({"protocol":asdict(protocol),
                    "conditions":[asdict(x) for x in observations], "summary":summary,
                    "validity":"valid_controlled_observation", "contamination_reasons":[]})

        fact_ids = self._select_fact_ids(snapshot, set(state["processed_selection_ids"]))
        record_id = receipt_id = None
        if fact_ids:
            selection = self.writeback.select_evidence(snapshot, fact_ids=fact_ids)
            if selection.selection_id not in set(state["processed_selection_ids"]):
                candidate = self.writeback.infer_candidate(
                    selection, invoker=self.invoker,
                    correlation_id=f"{tick_id}:resident_developmental_interpretation")
                operation_id = f"resident-developmental-writeback:{tick_id}:{candidate.candidate_id}"
                config_digest = self.writeback.admission_configuration_digest(candidate, operation_id=operation_id)
                sequence = self.current_sequence()
                admission = self.admission_authority.issue(
                    admission_id=f"resident-admission-{candidate.candidate_id}-{sequence}",
                    capability_id=RESIDENT_DEVELOPMENTAL_WRITEBACK, definition_version=1,
                    subsystem_kind="memory_context_reflection", principal_id=PRINCIPAL,
                    principal_kind=PRINCIPAL, effects=EFFECTS, subject_id=candidate.candidate_id,
                    request_configuration_digest=config_digest,
                    provenance=f"configured-resident-control-plane:{tick_id}", issued_sequence=sequence,
                    valid_through_sequence=sequence,
                    affirmative_preconditions=RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION.approval_requirements,
                )
                record, receipt = self.writeback.append(candidate, admission=admission,
                                                        operation_id=operation_id,
                                                        correlation_id=f"{tick_id}:resident-developmental-writeback")
                record_id, receipt_id = record.record_id, receipt.receipt_id
                # Persist each exact fact-evidence identity so changing the batch
                # bound cannot make an already interpreted fact eligible again.
                state["processed_selection_ids"].extend(
                    self.writeback.select_evidence(snapshot, fact_ids=(fact_id,)).selection_id
                    for fact_id in fact_ids
                )
        state["completed_ticks"].append({"tick_id": tick_id, "snapshot_id": snapshot.snapshot_id,
                                         "snapshot_digest": snapshot.digest, "record_id": record_id,
                                         "receipt_id": receipt_id})
        self._save_state(state)
        return ResidentDevelopmentalCycleResult(
            "completed", tick_id, snapshot.snapshot_id, fact_ids, prior.requested_record_ids,
            record_id, receipt_id, tuple(item.observation_id for item in observations), measurement_id,
        )
