"""One-tick resident composition for bounded developmental history.

The owner has no cadence of its own.  ``sentientosd`` supplies an exact
World-State snapshot and tick identity.  History is non-authoritative context;
it is never canonical explicit-user retention.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, cast

from .codex_task_authority_admission import (
    RESIDENT_DEVELOPMENTAL_WRITEBACK,
    RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION,
)
from .governed_local_model_invocation import LocalModelInvocationBudget, LocalModelInvoker
from .developmental_history_intervention_experiment import (
    DevelopmentalExperimentStore, make_protocol, summarize,
    PURPOSE as EXPERIMENT_PURPOSE,
)
from .local_model_authority import atomic_write_json, digest_payload
from .longitudinal_self_model import CognitiveSelfModelProjection
from .persistent_epistemic_state import EpistemicCognitiveProjection
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
CONFIG_SCHEMA_V2 = "sentientos.resident_developmental_cognition_config:v2"
STATE_SCHEMA = "sentientos.resident_developmental_cognition_state:v2"
LEGACY_STATE_SCHEMA = "sentientos.resident_developmental_cognition_state:v1"
COGNITION_PURPOSE = "resident_developmental_retrieval_cognition"
CURRENT_PROJECTION_POLICY = "succession_identity_then_transition_evidence_then_source_id:v2"
MAX_FACTS = 16
MAX_HISTORY = 16
MAX_RECOVERED_TICKS = 4096
MAX_RECOVERED_FACT_IDS = 65_536
MAX_COMPOSITION_STATE_BYTES = 16_777_216
MAX_COGNITION_OBSERVATIONS = 12_288
MAX_COGNITION_OBSERVATION_BYTES = 65_536
MAX_COGNITION_OBSERVATION_ROOT_BYTES = 134_217_728


class ResidentDevelopmentalCognitionError(ValueError):
    """Fail-closed composition/configuration violation."""


def _digest(value: Any) -> str:
    return "sha256:" + str(digest_payload(value))


@dataclass(frozen=True)
class ResidentDevelopmentalCognitionConfig:
    history_root: Path
    state_root: Path
    allowed_source_kinds: tuple[str, ...]
    max_selected_facts: int
    max_retrieved_records: int = 4
    comparison_enabled: bool = False
    enabled: bool = True
    model_replacement_artifact_root: Path | None = None


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
    self_model_projection_present: bool = False
    self_model_projection_id: str | None = None
    self_model_projection_digest: str | None = None
    self_model_reconciliation_id: str | None = None
    self_model_reconciliation_digest: str | None = None
    self_model_reconciliation_generation: int | None = None
    self_model_source_tick: str | None = None
    self_model_claim_ids: tuple[str, ...] = ()
    self_model_claim_digests: tuple[str, ...] = ()
    prior_tick_proven: bool = False
    epistemic_projection_present: bool = False
    epistemic_projection_id: str | None = None
    epistemic_projection_digest: str | None = None
    epistemic_proposition_ids: tuple[str, ...] = ()
    epistemic_state_ids: tuple[str, ...] = ()
    epistemic_state_digests: tuple[str, ...] = ()
    epistemic_generations: tuple[int, ...] = ()
    epistemic_evidence_set_digests: tuple[str, ...] = ()
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
    common = {"schema", "enabled", "history_root", "state_root", "allowed_source_kinds",
              "max_selected_facts", "max_retrieved_records", "comparison_enabled"}
    schema = payload.get("schema") if isinstance(payload, dict) else None
    expected = common if schema == CONFIG_SCHEMA else common | {"model_replacement_artifact_root"}
    if not isinstance(payload, dict) or set(payload) != expected or schema not in {CONFIG_SCHEMA, CONFIG_SCHEMA_V2}:
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
    provenance_root = payload.get("model_replacement_artifact_root")
    if schema == CONFIG_SCHEMA_V2 and (not isinstance(provenance_root, str) or not provenance_root):
        raise ResidentDevelopmentalCognitionError("configuration_values_invalid")
    history_root, state_root = Path(payload["history_root"]), Path(payload["state_root"])
    if history_root == state_root:
        raise ResidentDevelopmentalCognitionError("configuration_roots_must_be_separate")
    if provenance_root is not None and Path(provenance_root) in {history_root, state_root}:
        raise ResidentDevelopmentalCognitionError("configuration_artifact_root_must_be_separate")
    return ResidentDevelopmentalCognitionConfig(history_root, state_root, tuple(sorted(kinds)), maximum,
        history_maximum, payload["comparison_enabled"], payload["enabled"],
        Path(provenance_root) if provenance_root is not None else None)


class ResidentDevelopmentalCognitionOwner:
    """Perform at most one deterministic developmental composition per call."""

    def __init__(self, *, config: ResidentDevelopmentalCognitionConfig,
                 writeback: ResidentDevelopmentalWritebackController,
                 admission_authority: RuntimeAdmissionAuthority,
                 invoker: LocalModelInvoker,
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
        state_migrated = False
        if self.state_path.is_symlink():
            raise ResidentDevelopmentalCognitionError("composition_state_unbounded_or_not_regular")
        if not self.state_path.exists():
            semantic = {"schema": STATE_SCHEMA, "processed_selection_ids": [], "completed_ticks": [],
                "incomplete_ticks": []}
            state = {**semantic, "state_digest": _digest(semantic)}
        else:
            try:
                if self.state_path.is_symlink() or not self.state_path.is_file() or self.state_path.stat().st_size > MAX_COMPOSITION_STATE_BYTES:
                    raise ResidentDevelopmentalCognitionError("composition_state_unbounded_or_not_regular")
                value = json.loads(self.state_path.read_text(encoding="utf-8"))
                claimed = value.pop("state_digest")
            except (OSError, json.JSONDecodeError, KeyError, AttributeError, TypeError) as exc:
                raise ResidentDevelopmentalCognitionError("composition_state_corrupt") from exc
            if value.get("schema") not in {STATE_SCHEMA, LEGACY_STATE_SCHEMA} or claimed != _digest(value):
                raise ResidentDevelopmentalCognitionError("composition_state_digest_mismatch")
            if (not isinstance(value.get("processed_selection_ids"), list)
                    or any(not isinstance(item, str) for item in value["processed_selection_ids"])
                    or not isinstance(value.get("completed_ticks"), list)
                    or any(not isinstance(item, dict) for item in value["completed_ticks"])):
                raise ResidentDevelopmentalCognitionError("composition_state_shape_invalid")
            if value.get("schema") == LEGACY_STATE_SCHEMA:
                value["schema"] = STATE_SCHEMA
                value["incomplete_ticks"] = []
                state_migrated = True
            elif (not isinstance(value.get("incomplete_ticks"), list)
                    or any(not isinstance(item, dict) for item in value["incomplete_ticks"])):
                raise ResidentDevelopmentalCognitionError("composition_state_shape_invalid")
            migrated = {key: item for key, item in value.items() if key != "state_digest"}
            claimed = _digest(migrated)
            state = {**migrated, "state_digest": claimed}
        if (len(state["processed_selection_ids"]) > MAX_RECOVERED_FACT_IDS
                or len(state["completed_ticks"]) + len(state["incomplete_ticks"]) > MAX_RECOVERED_TICKS):
            raise ResidentDevelopmentalCognitionError("composition_state_retention_limit_exceeded")
        changed = state_migrated
        # The record and receipt are the commit point. Rebuild the checkpoint
        # if a process stopped after publication but before composition_state.
        try:
            recovered = self.writeback.recover_completed_records()
        except Exception as exc:
            raise ResidentDevelopmentalCognitionError("developmental_history_recovery_failed") from exc
        def recovery_order(item: tuple[Any, Any]) -> tuple[float, str]:
            record = item[0]
            try:
                created = datetime.fromisoformat(record.created_at.replace("Z", "+00:00"))
                if created.tzinfo is None:
                    raise ValueError("naive")
            except (AttributeError, TypeError, ValueError) as exc:
                raise ResidentDevelopmentalCognitionError("recovered_history_time_invalid") from exc
            return created.astimezone(timezone.utc).timestamp(), record.record_id
        recovered = tuple(sorted(recovered, key=recovery_order))
        processed = set(state["processed_selection_ids"])
        ticks: dict[str, dict[str, Any]] = {}
        for row in state["completed_ticks"]:
            saved_tick = row.get("tick_id")
            if not isinstance(saved_tick, str) or not saved_tick or saved_tick in ticks:
                raise ResidentDevelopmentalCognitionError("composition_tick_identity_ambiguous")
            ticks[saved_tick] = row
        incomplete: dict[str, dict[str, Any]] = {}
        for row in state["incomplete_ticks"]:
            saved_tick = row.get("tick_id")
            if not isinstance(saved_tick, str) or not saved_tick or saved_tick in incomplete or saved_tick in ticks:
                raise ResidentDevelopmentalCognitionError("composition_tick_identity_ambiguous")
            incomplete[saved_tick] = row
        for record, receipt in recovered:
            candidate = record.candidate
            fact_ids = candidate.get("selected_fact_ids", ())
            if not isinstance(fact_ids, (list, tuple)) or any(not isinstance(item, str) for item in fact_ids):
                raise ResidentDevelopmentalCognitionError("recovered_fact_identity_invalid")
            for fact_id in fact_ids:
                if fact_id not in processed:
                    state["processed_selection_ids"].append(fact_id)
                    processed.add(fact_id)
                    changed = True
            suffix = ":resident-developmental-writeback"
            correlation = record.correlation_id
            if not correlation.endswith(suffix):
                raise ResidentDevelopmentalCognitionError("recovered_tick_correlation_invalid")
            recovered_tick = correlation[:-len(suffix)]
            expected_operation = "resident-developmental-writeback:" + recovered_tick + ":" + str(candidate.get("candidate_id"))
            if not recovered_tick or record.operation_id != expected_operation:
                raise ResidentDevelopmentalCognitionError("recovered_tick_operation_binding_invalid")
            existing = ticks.get(recovered_tick)
            checkpoint = {"tick_id": recovered_tick, "snapshot_id": candidate.get("snapshot_id"),
                "snapshot_digest": candidate.get("snapshot_digest"), "record_id": record.record_id,
                "receipt_id": receipt.receipt_id}
            if existing is None:
                state["completed_ticks"].append(checkpoint)
                ticks[recovered_tick] = checkpoint
                changed = True
            elif existing.get("record_id") != record.record_id or existing.get("receipt_id") != receipt.receipt_id:
                raise ResidentDevelopmentalCognitionError("recovered_tick_record_conflict")
            if recovered_tick in incomplete:
                del incomplete[recovered_tick]
                state["incomplete_ticks"] = [row for row in state["incomplete_ticks"]
                    if row.get("tick_id") != recovered_tick]
                changed = True
        # A durable cognition observation without its enclosing tick checkpoint
        # is an interrupted tick. Preserve it and reject same-tick replay.
        for recovered_tick, observation_ids in self._recover_observation_ticks().items():
            if recovered_tick in ticks or recovered_tick in incomplete:
                continue
            item = {"tick_id": recovered_tick, "observation_ids": list(observation_ids),
                "status": "incomplete_recovered"}
            state["incomplete_ticks"].append(item)
            incomplete[recovered_tick] = item
            changed = True
        if (len(state["processed_selection_ids"]) > MAX_RECOVERED_FACT_IDS
                or len(state["completed_ticks"]) + len(state["incomplete_ticks"]) > MAX_RECOVERED_TICKS):
            raise ResidentDevelopmentalCognitionError("composition_state_retention_limit_exceeded")
        if changed:
            self._save_state(state)
        return state

    def _recover_observation_ticks(self) -> dict[str, tuple[str, ...]]:
        if self.observations_root.is_symlink():
            raise ResidentDevelopmentalCognitionError("cognition_observation_root_invalid")
        if not self.observations_root.exists():
            return {}
        if self.observations_root.is_symlink() or not self.observations_root.is_dir():
            raise ResidentDevelopmentalCognitionError("cognition_observation_root_invalid")
        paths = sorted(self.observations_root.glob("*.json"))
        if len(paths) > MAX_COGNITION_OBSERVATIONS:
            raise ResidentDevelopmentalCognitionError("cognition_observation_retention_limit_exceeded")
        total_bytes = 0
        by_tick: dict[str, list[str]] = {}
        for path in paths:
            if path.is_symlink() or not path.is_file():
                raise ResidentDevelopmentalCognitionError("cognition_observation_not_regular")
            size = path.stat().st_size
            total_bytes += size
            if size > MAX_COGNITION_OBSERVATION_BYTES or total_bytes > MAX_COGNITION_OBSERVATION_ROOT_BYTES:
                raise ResidentDevelopmentalCognitionError("cognition_observation_retention_limit_exceeded")
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                observation_id = value.pop("observation_id")
                observation_digest = value.pop("observation_digest")
            except (OSError, UnicodeError, json.JSONDecodeError, KeyError, AttributeError, TypeError) as exc:
                raise ResidentDevelopmentalCognitionError("cognition_observation_corrupt") from exc
            expected_fields = set(ResidentCognitionObservation.__dataclass_fields__) - {
                "observation_id", "observation_digest"}
            if (not isinstance(value, dict) or set(value) != expected_fields
                    or not isinstance(value.get("tick_id"), str) or not value["tick_id"]
                    or observation_digest != _digest(value)
                    or observation_id != "devcog-" + observation_digest[7:31]
                    or path.stem != observation_id):
                raise ResidentDevelopmentalCognitionError("cognition_observation_digest_mismatch")
            by_tick.setdefault(value["tick_id"], []).append(observation_id)
        return {tick: tuple(sorted(ids)) for tick, ids in by_tick.items()}

    def _save_state(self, state: Mapping[str, Any]) -> None:
        semantic = {k: v for k, v in state.items() if k != "state_digest"}
        if (len(semantic.get("processed_selection_ids", ())) > MAX_RECOVERED_FACT_IDS
                or len(semantic.get("completed_ticks", ())) + len(semantic.get("incomplete_ticks", ())) > MAX_RECOVERED_TICKS):
            raise ResidentDevelopmentalCognitionError("composition_state_retention_limit_exceeded")
        if len(json.dumps(semantic, sort_keys=True, separators=(",", ":")).encode("utf-8")) > MAX_COMPOSITION_STATE_BYTES:
            raise ResidentDevelopmentalCognitionError("composition_state_unbounded")
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
            key=lambda fact: self._fact_selection_key(fact, source_kinds[fact.source.source_id]),
        )
        selected: list[str] = []
        for fact in candidates:
            trial = self.writeback.select_evidence(snapshot, fact_ids=(fact.fact_id,))
            # Fact IDs remain stable when the same immutable source is observed
            # in a later snapshot. Selection IDs include snapshot identity and
            # are accepted only for compatibility with pre-recovery state files.
            if fact.fact_id not in processed and trial.selection_id not in processed:
                selected.append(fact.fact_id)
            if len(selected) == self.config.max_selected_facts:
                break
        return tuple(selected)

    @staticmethod
    def _fact_selection_key(fact: Any, source_kind: str) -> tuple[Any, ...]:
        """Keep observed generations and verified transition evidence ahead of journal volume."""
        subject_kind = str(fact.subject.subject_kind)
        payload = fact.payload
        if subject_kind in {"observed_running_model", "observed_running_software_generation"}:
            priority = 0
        elif payload.get("activated_model_identity") is not None or payload.get("serving_binding_digest"):
            priority = 1
        elif (isinstance(payload.get("proposed_successor_model_development_provenance"), Mapping)
                and payload["proposed_successor_model_development_provenance"].get("identity_binding_verified") is True):
            priority = 2
        elif subject_kind in {"resident_model_transition", "software_generation_transition"}:
            priority = 3
        elif subject_kind in {"resident_model_transition_recovery", "software_generation_transition_recovery"}:
            priority = 4
        else:
            priority = 5
        return priority, source_kind, fact.source.source_id, fact.fact_id

    def _current_projection(self, snapshot: WorldStateSnapshot) -> CurrentWorldStateCognitiveProjection:
        """Select current context independently of developmental-writeback deduplication."""
        allowed = set(self.config.allowed_source_kinds)
        source_kinds = {source.source_id: source.kind for source in snapshot.sources}
        facts = sorted((fact for fact in snapshot.facts if source_kinds.get(fact.source.source_id) in allowed),
                       key=lambda fact: self._fact_selection_key(fact, source_kinds[fact.source.source_id]))[:self.config.max_selected_facts]
        selected = self.writeback.select_evidence(snapshot, fact_ids=tuple(f.fact_id for f in facts))
        raw = CurrentWorldStateCognitiveProjection(snapshot.snapshot_id, snapshot.digest, selected.facts,
                                                    selected.sources, selected.conflicts,
                                                    tuple(str(x["fact_id"]) for x in selected.facts))
        digest = _digest(raw.semantic_payload())
        return replace(raw, projection_id="current-world-state-" + digest[7:31], projection_digest=digest)

    def _cognize(self, *, snapshot: WorldStateSnapshot, current: CurrentWorldStateCognitiveProjection, tick_id: str,
                  projection: DevelopmentalHistoryProjection, with_history: bool,
                  prior_self_model: CognitiveSelfModelProjection | None = None,
                  prior_epistemic_state: EpistemicCognitiveProjection | None = None,
                  condition_id: str, purpose: str = COGNITION_PURPOSE,
                  protocol: Any | None = None) -> ResidentCognitionObservation:
        records = projection.records if with_history else ()
        record_ids = projection.requested_record_ids if with_history else ()
        record_digests = tuple(str(record["record_digest"]) for record in records)
        context = {
            "instruction": "Reason over four separately typed, non-authoritative substrates. Current evidence is current external observation and outranks a conflicting prior epistemic position for current-condition reasoning. Prior self-model is earlier evidence-bound system representation. Prior epistemic state is the system's earlier position, not truth or evidence. Developmental history is earlier interpretation. Preserve contradictions; none is policy, goal, permission, admission, execution, adoption, or canonical user memory.",
            "current_evidence": current.semantic_payload(),
            "prior_self_model": asdict(prior_self_model) if prior_self_model is not None else None,
            "prior_epistemic_state": asdict(prior_epistemic_state) if prior_epistemic_state is not None else None,
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
                               "self_model_projection_present": prior_self_model is not None,
                               "self_model_projection_id": prior_self_model.projection_id if prior_self_model else None,
                               "self_model_projection_digest": prior_self_model.projection_digest if prior_self_model else None,
                               "self_model_reconciliation_id": prior_self_model.source_reconciliation_id if prior_self_model else None,
                               "self_model_reconciliation_digest": prior_self_model.source_reconciliation_digest if prior_self_model else None,
                               "self_model_reconciliation_generation": prior_self_model.source_reconciliation_generation if prior_self_model else None,
                               "self_model_source_tick": prior_self_model.source_tick if prior_self_model else None,
                               "self_model_claim_ids": list(prior_self_model.selected_claim_ids) if prior_self_model else [],
                               "self_model_claim_digests": list(prior_self_model.selected_claim_digests) if prior_self_model else [],
                               "epistemic_projection_id": prior_epistemic_state.projection_id if prior_epistemic_state else None,
                               "epistemic_projection_digest": prior_epistemic_state.projection_digest if prior_epistemic_state else None,
                               "epistemic_proposition_ids": list(prior_epistemic_state.proposition_ids) if prior_epistemic_state else [],
                               "epistemic_state_ids": list(prior_epistemic_state.state_ids) if prior_epistemic_state else [],
                               "epistemic_state_digests": list(prior_epistemic_state.state_digests) if prior_epistemic_state else [],
                               "epistemic_generations": list(prior_epistemic_state.generations) if prior_epistemic_state else [],
                               "epistemic_evidence_set_digests": list(prior_epistemic_state.evidence_set_digests) if prior_epistemic_state else [],
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
            "self_model_projection_present": prior_self_model is not None,
            "self_model_projection_id": prior_self_model.projection_id if prior_self_model else None,
            "self_model_projection_digest": prior_self_model.projection_digest if prior_self_model else None,
            "self_model_reconciliation_id": prior_self_model.source_reconciliation_id if prior_self_model else None,
            "self_model_reconciliation_digest": prior_self_model.source_reconciliation_digest if prior_self_model else None,
            "self_model_reconciliation_generation": prior_self_model.source_reconciliation_generation if prior_self_model else None,
            "self_model_source_tick": prior_self_model.source_tick if prior_self_model else None,
            "self_model_claim_ids": prior_self_model.selected_claim_ids if prior_self_model else (),
            "self_model_claim_digests": prior_self_model.selected_claim_digests if prior_self_model else (),
            "prior_tick_proven": prior_self_model is not None and prior_self_model.source_tick != tick_id,
            "epistemic_projection_present": prior_epistemic_state is not None,
            "epistemic_projection_id": prior_epistemic_state.projection_id if prior_epistemic_state else None,
            "epistemic_projection_digest": prior_epistemic_state.projection_digest if prior_epistemic_state else None,
            "epistemic_proposition_ids": prior_epistemic_state.proposition_ids if prior_epistemic_state else (),
            "epistemic_state_ids": prior_epistemic_state.state_ids if prior_epistemic_state else (),
            "epistemic_state_digests": prior_epistemic_state.state_digests if prior_epistemic_state else (),
            "epistemic_generations": prior_epistemic_state.generations if prior_epistemic_state else (),
            "epistemic_evidence_set_digests": prior_epistemic_state.evidence_set_digests if prior_epistemic_state else (),
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
            prior_self_model is not None, prior_self_model.projection_id if prior_self_model else None,
            prior_self_model.projection_digest if prior_self_model else None,
            prior_self_model.source_reconciliation_id if prior_self_model else None,
            prior_self_model.source_reconciliation_digest if prior_self_model else None,
            prior_self_model.source_reconciliation_generation if prior_self_model else None,
            prior_self_model.source_tick if prior_self_model else None,
            prior_self_model.selected_claim_ids if prior_self_model else (),
            prior_self_model.selected_claim_digests if prior_self_model else (),
            prior_self_model is not None and prior_self_model.source_tick != tick_id,
            prior_epistemic_state is not None,
            prior_epistemic_state.projection_id if prior_epistemic_state else None,
            prior_epistemic_state.projection_digest if prior_epistemic_state else None,
            prior_epistemic_state.proposition_ids if prior_epistemic_state else (),
            prior_epistemic_state.state_ids if prior_epistemic_state else (),
            prior_epistemic_state.state_digests if prior_epistemic_state else (),
            prior_epistemic_state.generations if prior_epistemic_state else (),
            prior_epistemic_state.evidence_set_digests if prior_epistemic_state else (),
        )
        atomic_write_json(self.observations_root / f"{observation.observation_id}.json", asdict(observation))
        return observation

    def run_tick(self, *, snapshot: WorldStateSnapshot, tick_id: str,
                 prior_self_model: CognitiveSelfModelProjection | None = None,
                 prior_epistemic_state: EpistemicCognitiveProjection | None = None) -> ResidentDevelopmentalCycleResult:
        if not self.config.enabled:
            return ResidentDevelopmentalCycleResult("disabled", tick_id, snapshot.snapshot_id)
        validation = validate_snapshot(snapshot)
        if not validation.valid:
            raise ResidentDevelopmentalCognitionError("invalid_world_state_snapshot")
        state = self._state()
        if (any(row.get("tick_id") == tick_id for row in state["completed_ticks"])
                or any(row.get("tick_id") == tick_id for row in state["incomplete_ticks"])):
            raise ResidentDevelopmentalCognitionError("tick_already_completed")
        if len(state["completed_ticks"]) + len(state["incomplete_ticks"]) >= MAX_RECOVERED_TICKS:
            raise ResidentDevelopmentalCognitionError("composition_state_retention_limit_exceeded")

        # Capture prior history before any candidate from this tick can exist.
        prior = self._prior_projection(state, tick_id)
        current = self._current_projection(snapshot)
        observations: list[ResidentCognitionObservation] = []
        measurement_id: str | None = None
        has_developmental_history = bool(prior.requested_record_ids)
        has_prior_self_model = prior_self_model is not None
        has_prior_epistemic_state = prior_epistemic_state is not None
        should_cognize = (has_developmental_history or has_prior_self_model
                          or has_prior_epistemic_state)
        should_run_history_comparison = (self.config.comparison_enabled
                                         and has_developmental_history)
        if should_cognize:
            if not should_run_history_comparison:
                observations.append(self._cognize(snapshot=snapshot, current=current, tick_id=tick_id,
                                    projection=prior, with_history=has_developmental_history,
                                    condition_id="with-history" if has_developmental_history else "prior-context",
                                    prior_self_model=prior_self_model, prior_epistemic_state=prior_epistemic_state))
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
                    epistemic_projection_id=prior_epistemic_state.projection_id if prior_epistemic_state else None,
                    epistemic_projection_digest=prior_epistemic_state.projection_digest if prior_epistemic_state else None,
                    epistemic_state_digests=prior_epistemic_state.state_digests if prior_epistemic_state else (),
                    epistemic_evidence_set_digests=prior_epistemic_state.evidence_set_digests if prior_epistemic_state else (),
                    instruction_template_digest=_digest({"instruction":"Observe current evidence with optional historical interpretation; do not treat history as truth, authority, policy, a goal, or canonical user retention."}))
                self.experiments.persist_protocol(protocol)  # preregistration precedes the first inference
                present = self._cognize(snapshot=snapshot, current=current, tick_id=tick_id, projection=prior,
                    with_history=True, condition_id="history_present", purpose=EXPERIMENT_PURPOSE, protocol=protocol,
                    prior_self_model=prior_self_model, prior_epistemic_state=prior_epistemic_state)
                withheld = self._cognize(snapshot=snapshot, current=current, tick_id=tick_id, projection=prior,
                    with_history=False, condition_id="history_withheld", purpose=EXPERIMENT_PURPOSE, protocol=protocol,
                    prior_self_model=prior_self_model, prior_epistemic_state=prior_epistemic_state)
                restored_records = tuple(self.writeback.store.get(rid) for rid in protocol.record_ids)
                if tuple(r.record_digest for r in restored_records) != protocol.record_digests:
                    raise ResidentDevelopmentalCognitionError("restored_history_digest_mismatch")
                restored_projection = self.writeback.retrieve(protocol.record_ids, limit=self.config.max_retrieved_records)
                restored = self._cognize(snapshot=snapshot, current=current, tick_id=tick_id,
                    projection=restored_projection, with_history=True, condition_id="history_restored",
                    purpose=EXPERIMENT_PURPOSE, protocol=protocol, prior_self_model=prior_self_model,
                    prior_epistemic_state=prior_epistemic_state)
                observations.extend((present, withheld, restored))
                summary = summarize(protocol, observations)
                measurement_id = self.experiments.persist_run({"protocol":asdict(protocol),
                    "conditions":[asdict(x) for x in observations], "summary":summary,
                    "validity":"valid_controlled_observation", "contamination_reasons":[]})

        fact_ids = self._select_fact_ids(snapshot, set(state["processed_selection_ids"]))
        if len(set(state["processed_selection_ids"]) | set(fact_ids)) > MAX_RECOVERED_FACT_IDS:
            raise ResidentDevelopmentalCognitionError("composition_state_retention_limit_exceeded")
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
                state["processed_selection_ids"].extend(fact_ids)
        state["completed_ticks"].append({"tick_id": tick_id, "snapshot_id": snapshot.snapshot_id,
                                         "snapshot_digest": snapshot.digest, "record_id": record_id,
                                         "receipt_id": receipt_id})
        self._save_state(state)
        return ResidentDevelopmentalCycleResult(
            "completed", tick_id, snapshot.snapshot_id, fact_ids, prior.requested_record_ids,
            record_id, receipt_id, tuple(item.observation_id for item in observations), measurement_id,
        )
