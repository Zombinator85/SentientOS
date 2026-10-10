"""Bounded, configured World-State to persistent epistemic-state composition.

This orchestrator selects exact facts and asks an injected admission authority for
two narrow permissions.  It neither infers proposition meaning nor owns mutation.
"""
from __future__ import annotations

import json
import hashlib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .codex_task_authority_admission import (
    RESIDENT_EPISTEMIC_STATE_MUTATION,
    RESIDENT_EPISTEMIC_STATE_MUTATION_DEFINITION,
)
from .persistent_epistemic_state import (
    EpistemicStateError, EvidenceBinding, PersistentEpistemicStateOwner,
    evidence_posture, make_epistemic_update_candidate, make_evidence_binding,
)
from .resident_epistemic_state_mutation import (
    EVIDENCE_BINDING_EFFECTS, PRINCIPAL, STATE_UPDATE_EFFECTS,
    ResidentEpistemicStateMutationController,
    make_epistemic_evidence_source_proof,
)
from .runtime_admission import AdmissionLedger, RuntimeAdmissionAuthority
from .world_state_board import WorldStateFact, WorldStateSnapshot, validate_snapshot
from .windows_handle_custody import WindowsHandleCustodyError, read_explicit_file

CONFIG_SCHEMA = "sentientos.resident_epistemic_development_config:v1"
RULE_SCHEMA = "sentientos.resident_epistemic_development_rule:v1"
ADAPTER_ID = "sentientos.world_state_epistemic_evidence_adapter:v1"
QUALITATIVE_RULE = "sentientos.qualitative_epistemic_posture:v1"
CONFIG_ENV = "SENTIENTOS_EPISTEMIC_DEVELOPMENT_CONFIG"
MAX_BINDINGS_PER_TICK = 64
MAX_PROPOSITIONS_PER_TICK = 16
MAX_ACTIVE_EVIDENCE = 256
MAX_EPISTEMIC_DEVELOPMENT_CONFIG_BYTES = 65_536
SELECTOR_FIELDS = frozenset({"source_kind", "source_id", "subject_kind", "subject_id", "stage", "disposition"})


class EpistemicDevelopmentError(ValueError):
    """Configuration, provenance, bound, or custody failed closed."""


def _latest_historical_event_time(values: list[str]) -> str | None:
    """Return the original text for the latest valid instant, or stay unknown."""
    if not values:
        return None
    parsed: list[tuple[datetime, str]] = []
    for value in values:
        try:
            instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if instant.tzinfo is None or instant.utcoffset() is None:
                return None
            parsed.append((instant.astimezone(timezone.utc), value))
        except (OverflowError, OSError, ValueError):
            return None
    return max(parsed, key=lambda item: (item[0], item[1]))[1]


@dataclass(frozen=True)
class EpistemicDevelopmentRule:
    rule_id: str; proposition_id: str; proposition_digest: str
    selector: Mapping[str, str]; evidence_relation: str
    dependency_kind: str; reliability_posture: str
    qualitative_rule_revision: str = QUALITATIVE_RULE
    independence_basis: str | None = None
    schema: str = RULE_SCHEMA


@dataclass(frozen=True)
class EpistemicDevelopmentConfig:
    enabled: bool; max_new_bindings_per_tick: int
    max_updated_propositions_per_tick: int
    rules: tuple[EpistemicDevelopmentRule, ...]
    allowed_namespaces: tuple[str, ...]
    schema: str = CONFIG_SCHEMA


@dataclass(frozen=True)
class EpistemicDevelopmentFeedback:
    status: str; snapshot_id: str; rule_count: int; matched_fact_count: int
    new_binding_count: int; updated_proposition_count: int
    evidence_receipt_ids: tuple[str, ...]; state_receipt_ids: tuple[str, ...]
    successor_state_ids: tuple[str, ...]; generations: tuple[int, ...]
    next_tick_only: bool = True; authority: bool = False


def load_epistemic_development_config(path: str | Path) -> EpistemicDevelopmentConfig:
    try:
        raw = json.loads(read_explicit_file(Path(path),
            max_bytes=MAX_EPISTEMIC_DEVELOPMENT_CONFIG_BYTES).decode("utf-8"))
    except (WindowsHandleCustodyError, UnicodeError, json.JSONDecodeError) as exc:
        raise EpistemicDevelopmentError("configuration_unreadable_or_invalid") from exc
    if set(raw) != {"schema", "enabled", "max_new_bindings_per_tick", "max_updated_propositions_per_tick", "allowed_namespaces", "rules"}:
        raise EpistemicDevelopmentError("configuration_fields_invalid")
    rules = tuple(EpistemicDevelopmentRule(**item) for item in raw["rules"])
    config = EpistemicDevelopmentConfig(raw["enabled"], raw["max_new_bindings_per_tick"],
        raw["max_updated_propositions_per_tick"], rules, tuple(raw["allowed_namespaces"]), raw["schema"])
    _validate_config(config)
    return config


def _validate_config(config: EpistemicDevelopmentConfig) -> None:
    if config.schema != CONFIG_SCHEMA or not isinstance(config.enabled, bool):
        raise EpistemicDevelopmentError("configuration_schema_invalid")
    if not 1 <= config.max_new_bindings_per_tick <= MAX_BINDINGS_PER_TICK:
        raise EpistemicDevelopmentError("binding_bound_invalid")
    if not 1 <= config.max_updated_propositions_per_tick <= MAX_PROPOSITIONS_PER_TICK:
        raise EpistemicDevelopmentError("proposition_bound_invalid")
    ids: set[str] = set()
    for rule in config.rules:
        if (rule.schema != RULE_SCHEMA or not rule.rule_id or rule.rule_id in ids
                or not rule.selector or set(rule.selector) - SELECTOR_FIELDS
                or any(not isinstance(value, str) or not value for value in rule.selector.values())
                or rule.evidence_relation not in {"supports", "contradicts"}
                or rule.dependency_kind not in {"unknown_dependency", "independently_sourced_observation"}
                or rule.qualitative_rule_revision != QUALITATIVE_RULE):
            raise EpistemicDevelopmentError("rule_invalid")
        if rule.dependency_kind == "independently_sourced_observation" and not rule.independence_basis:
            raise EpistemicDevelopmentError("independence_not_established")
        ids.add(rule.rule_id)


class ResidentEpistemicDevelopmentRuntime:
    """One bounded maintenance-cycle orchestrator; cadence remains daemon-owned."""

    def __init__(self, *, config: EpistemicDevelopmentConfig,
                 owner: PersistentEpistemicStateOwner,
                 mutation_controller: ResidentEpistemicStateMutationController,
                 admission_authority: RuntimeAdmissionAuthority,
                 admission_ledger: AdmissionLedger) -> None:
        _validate_config(config)
        self.config, self.owner = config, owner
        self.controller, self.authority = mutation_controller, admission_authority
        self.ledger = admission_ledger
        for rule in config.rules:
            proposition = owner.proposition(rule.proposition_id)
            if proposition.proposition_digest != rule.proposition_digest:
                raise EpistemicDevelopmentError("proposition_digest_mismatch")
            if proposition.namespace not in config.allowed_namespaces or proposition.namespace not in owner.allowed_namespaces:
                raise EpistemicDevelopmentError("proposition_namespace_not_allowed")

    def _next_sequence(self) -> int:
        admissions, revocations = self.ledger.load()
        return max([x.issued_sequence for x in admissions] + [x.sequence for x in revocations], default=0) + 1

    @staticmethod
    def _matches(rule: EpistemicDevelopmentRule, fact: WorldStateFact) -> bool:
        values = {"source_kind": fact.source.kind, "source_id": fact.source.source_id,
            "subject_kind": fact.subject.subject_kind, "subject_id": fact.subject.subject_id,
            "stage": fact.stage, "disposition": fact.disposition}
        return all(values[key] == value for key, value in rule.selector.items())

    @staticmethod
    def _adapt(snapshot: WorldStateSnapshot, fact: WorldStateFact,
               rule: EpistemicDevelopmentRule) -> tuple[Any, EvidenceBinding]:
        observed = fact.observed_at
        historical_resource_fact = fact.source.kind == "resource_governor"
        resource_invocation_lineage = (historical_resource_fact and fact.subject.subject_kind in {
            "strategy_invocation_resource_lineage", "model_replacement_invocation_resource_lineage"})
        incomplete_resource_lineage = (resource_invocation_lineage
            and (fact.disposition != "verified" or not isinstance(fact.payload, Mapping)
                or fact.payload.get("lineage_findings") != []))
        historical_resource_introspection = (fact.source.kind == "owner_introspection"
            and fact.subject.subject_kind == "causal_resources")
        historical_unverified_owner_record = (fact.source.kind == "owner_introspection"
            and fact.subject.subject_kind == "post_adoption_attribution_campaign")
        historical_transition_event = (
            fact.source.kind == "runtime_supervisor"
            and fact.subject.subject_kind in {"resident_model_transition", "software_generation_transition"}
            and isinstance(fact.payload, Mapping))
        historical_chat_recovery_event = (
            fact.source.kind == "runtime_supervisor"
            and fact.subject.subject_kind == "chat_process_recovery_transition"
            and isinstance(fact.payload, Mapping)
            and fact.payload.get("phase_evidence_posture")
                == "canonical_installation_custody_and_digest_chain_checked_not_independently_signed")
        historical_chat_runtime_observation = (
            fact.source.kind == "runtime_supervisor"
            and fact.subject.subject_kind == "chat_process_runtime_generation_observation"
            and isinstance(fact.payload, Mapping)
            and isinstance(fact.payload.get("chat_process_runtime_observation"), Mapping)
            and fact.payload.get("event_time_posture")
                == "runtime_owner_observation_not_current_liveness")
        historical_serving_operation_attempt = (
            fact.source.kind == "runtime_supervisor"
            and fact.subject.subject_kind == "serving_operation_attempt"
            and isinstance(fact.payload, Mapping)
            and isinstance(fact.payload.get("serving_operation_attempt"), Mapping)
            and fact.payload.get("event_time_posture")
                == "reservation_time_not_model_load_time")
        historical_serving_operation_history = (
            fact.source.kind == "runtime_supervisor"
            and fact.subject.subject_kind == "serving_operation_history"
            and isinstance(fact.payload, Mapping)
            and fact.payload.get("historical_only") is True
            and fact.payload.get("current_model_claimed") is False
            and fact.payload.get("event_time_posture") in {
                "owner_observed_model_load_time",
                "reservation_time_model_load_outcome_unknown"})
        historical_transition_observation = (
            historical_transition_event
            and fact.subject.subject_kind == "resident_model_transition"
            and fact.payload.get("transition_phase") in {"b_epoch_observed", "post_restoration_observed"})
        qualified_transition_observation = (
            historical_transition_observation
            and fact.disposition == "completed"
            and fact.payload.get("transition_observation_posture")
                == "owner_verified_durable_cognition_history_handoff")

        historical_undated_consequence = (fact.source.kind == "embodiment"
            and fact.subject.subject_kind in {"embodied_strategy_experiment",
                                               "developmental_model_replacement_experiment",
                                               "embodied_consequence_chain",
                                               "embodied_action_expectation",
                                               "avatar_renderer_handoff",
                                               "avatar_renderer_report",
                                               "embodied_consequence_attribution",
                                               "embodied_prediction_comparison",
                                               "embodied_proposal_fulfillment_receipt"})
        historical_consequence_chain = (fact.source.kind == "embodiment"
            and fact.subject.subject_kind == "embodied_consequence_chain")
        historical_embodied_event_fields = {
            "embodied_action_expectation": ("created_at",),
            "avatar_renderer_handoff": ("commanded_at",),
            "avatar_renderer_report": ("completed_at",),
            "avatar_independently_observed_state": ("observed_at",),
            "embodied_consequence_attribution": ("evaluated_at",),
            "embodied_prediction_comparison": ("evaluated_at",),
        }.get(fact.subject.subject_kind)
        historical_strategy_proposal = (fact.source.kind == "embodiment"
            and fact.subject.subject_kind == "embodied_strategy_proposal")
        historical_strategy_review = (fact.source.kind == "embodiment"
            and fact.subject.subject_kind == "embodied_strategy_proposal_review")
        unverified_embodiment_observation = (fact.source.kind == "embodiment"
            and fact.subject.subject_kind == "avatar_independently_observed_state")
        source_integrity_conflict = (fact.source.finding != "ok" or any(
            conflict.subject_id == fact.source.source_id
            and conflict.conflict_type in {"source_digest_mismatch",
                "source_observation_time_mismatch"}
            for conflict in snapshot.conflicts))
        unverified_source_context = (historical_undated_consequence
            or historical_unverified_owner_record
            or historical_chat_recovery_event or historical_chat_runtime_observation
            or historical_serving_operation_attempt or historical_serving_operation_history
            or (historical_transition_observation and not qualified_transition_observation)
            or historical_strategy_proposal
            or historical_strategy_review or unverified_embodiment_observation
            or incomplete_resource_lineage or source_integrity_conflict)
        stable_source_digest = fact.source.digest
        stable_fact_identity = {"source_id": fact.source.source_id, "fact_id": fact.fact_id}
        artifact_id = "world-state-fact:" + hashlib.sha256(json.dumps(stable_fact_identity,
            sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:32]
        if (historical_serving_operation_history and isinstance(fact.payload, Mapping)):
            # Preserve the event time from the canonical serving receipt or
            # reservation. World-State retrieval time is not a substitute.
            source_event_time = fact.payload.get("event_time")
            observed = (_latest_historical_event_time([source_event_time])
                if isinstance(source_event_time, str) else None)
        if (historical_chat_runtime_observation and isinstance(fact.payload, Mapping)):
            # The runtime row timestamp is a historical observation event, not
            # retrieval time. Preserve it in the evidence binding while the
            # freshness posture below remains non-current.
            runtime_observation = fact.payload.get("chat_process_runtime_observation")
            source_event_time = (fact.payload.get("event_time")
                if isinstance(fact.payload.get("event_time"), str)
                else runtime_observation.get("observed_at")
                    if isinstance(runtime_observation, Mapping) else None)
            observed = (_latest_historical_event_time([source_event_time])
                if isinstance(source_event_time, str) else None)
        if (historical_resource_fact and fact.subject.subject_kind == "host_resource_snapshot"
                and isinstance(fact.payload, Mapping)):
            # The snapshot's payload timestamp belongs to the owner's
            # digest-bound telemetry object. The World-State row timestamp is
            # retrieval metadata and must not be substituted during replay.
            source_event_time = fact.payload.get("observed_at")
            observed = (_latest_historical_event_time([source_event_time])
                if isinstance(source_event_time, str) else None)
        elif fact.source.kind == "resource_governor" and isinstance(fact.payload, Mapping):
            historical_times = [str(item.get("observed_at")) for item in fact.payload.get("consumption_receipts", ())
                                if isinstance(item, Mapping) and item.get("observed_at")]
            if resource_invocation_lineage:
                historical_times.extend(str(item) for item in fact.payload.get("event_times", ())
                    if isinstance(item, str))
            observed = _latest_historical_event_time(historical_times)
        if historical_consequence_chain and isinstance(fact.payload, Mapping):
            event_times = fact.payload.get("event_times")
            event_time_fields = ("expectation_created_at", "commanded_at",
                "renderer_started_at", "renderer_completed_at", "claimed_observation_at",
                "comparison_evaluated_at")
            if isinstance(event_times, Mapping):
                raw_times = [event_times.get(key) for key in event_time_fields
                    if event_times.get(key) is not None]
                observed = (_latest_historical_event_time(raw_times)
                    if all(isinstance(value, str) for value in raw_times) and raw_times else None)
            else:
                observed = None
        if (fact.source.kind == "embodiment" and historical_embodied_event_fields
                and isinstance(fact.payload, Mapping)):
            raw_times = [fact.payload.get(key) for key in historical_embodied_event_fields
                if fact.payload.get(key) is not None]
            observed = (_latest_historical_event_time(raw_times)
                if all(isinstance(value, str) for value in raw_times) and raw_times else None)
        if fact.source.kind == "runtime_supervisor":
            if fact.subject.subject_kind == "serving_operation_attempt" and isinstance(fact.payload, Mapping):
                attempt = fact.payload.get("serving_operation_attempt")
                event_time = attempt.get("reserved_at") if isinstance(attempt, Mapping) else None
                observed = (_latest_historical_event_time([event_time])
                    if isinstance(event_time, str) else None)
            elif fact.subject.subject_kind == "chat_process_runtime_generation_observation" and isinstance(fact.payload, Mapping):
                runtime_observation = fact.payload.get("chat_process_runtime_observation")
                event_time = runtime_observation.get("observed_at") if isinstance(
                    runtime_observation, Mapping) else None
                observed = (_latest_historical_event_time([event_time])
                    if isinstance(event_time, str) else None)
            elif fact.subject.subject_kind == "chat_process_recovery_transition" and isinstance(fact.payload, Mapping):
                phase_times = fact.payload.get("phase_event_times")
                values = ([phase_times.get(key) for key in (
                    "attempt_started_at", "readiness_observed_at", "snapshot_advanced_at")
                    if phase_times.get(key) is not None] if isinstance(phase_times, Mapping) else [])
                observed = (_latest_historical_event_time(values)
                    if values and all(isinstance(value, str) for value in values) else None)
            elif fact.subject.subject_kind in {"resident_model_transition",
                    "software_generation_transition"} and isinstance(fact.payload, Mapping):
                event_time = fact.payload.get("event_time")
                observed = (_latest_historical_event_time([event_time])
                    if isinstance(event_time, str) else None)
            elif fact.subject.subject_kind == "observed_running_software_generation" and isinstance(fact.payload, Mapping):
                event_time = fact.payload.get("startup_timestamp")
                observed = (_latest_historical_event_time([event_time])
                    if isinstance(event_time, str) else None)
            elif fact.subject.subject_kind in {"observed_running_model",
                    "resident_model_transition_recovery",
                    "software_generation_transition_recovery"}:
                # Session-currentness checks and journal reconstruction time
                # are not retained source events. Keep their chronology unknown.
                observed = None
        if (fact.source.kind == "embodiment"
                and fact.subject.subject_kind == "developmental_model_replacement_experiment"
                and isinstance(fact.payload, Mapping)):
            observations = fact.payload.get("observations")
            if isinstance(observations, (list, tuple)):
                event_times = [item.get("inference_event_time") for item in observations
                    if isinstance(item, Mapping) and isinstance(item.get("inference_event_time"), str)]
                malformed_time = any(isinstance(item, Mapping)
                    and item.get("inference_event_time") is not None
                    and not isinstance(item.get("inference_event_time"), str) for item in observations)
                observed = (None if malformed_time else
                    _latest_historical_event_time(event_times) if event_times else None)
        if historical_resource_introspection and isinstance(fact.payload, Mapping):
            observations = fact.payload.get("observations", ())
            if not isinstance(observations, (list, tuple)):
                observations = ()
            def unique_observation_value(key: str) -> Any:
                matches = [item.get("value") for item in observations
                    if isinstance(item, Mapping) and item.get("key") == key]
                return matches[0] if len(matches) == 1 else None

            latest_event = unique_observation_value("latest_consumption_event_at")
            if latest_event:
                observed = (_latest_historical_event_time([latest_event])
                    if isinstance(latest_event, str) else None)
            else:
                observed = None
            retained = unique_observation_value("ledger_digest")
            installation = unique_observation_value("installation_identity")
            provisioning = unique_observation_value("provisioning_id")
            manifest_digest = unique_observation_value("manifest_digest")
            if all(isinstance(value, str) and value for value in (
                    retained, installation, provisioning, manifest_digest)):
                stable_identity = {"installation_identity": installation,
                    "provisioning_id": provisioning, "manifest_digest": manifest_digest,
                    "ledger_digest": retained}
                stable_source_digest = "sha256:" + hashlib.sha256(json.dumps(stable_identity,
                    sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
                artifact_id = "resource-introspection:" + hashlib.sha256(json.dumps(stable_identity,
                    sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:32]
        if (not isinstance(observed, str)
                or _latest_historical_event_time([observed]) is None):
            observed = None
        if source_integrity_conflict:
            # Keep malformed producer records visible as context, but do not
            # let a failed source binding provide an event time or support.
            observed = None
        # A snapshot's reconstruction clock is not a source event time. Preserve
        # missing event time as a stable semantic value for every source kind.
        missing_source_time = observed is None
        observed = observed or "undated"
        provenance = json.dumps({"snapshot_id": snapshot.snapshot_id, "snapshot_digest": snapshot.digest,
            "fact_id": fact.fact_id, "source_id": fact.source.source_id, "source_kind": fact.source.kind,
            "rule_id": rule.rule_id, "proposition_id": rule.proposition_id,
            "proposition_digest": rule.proposition_digest, "adapter_id": ADAPTER_ID,
            "event_time_posture": "runtime_owner_observation_time_not_current_liveness"
                if historical_chat_runtime_observation else "chat_recovery_phase_time_not_process_liveness_or_inference_time"
                if historical_chat_recovery_event else "transition_stage_time_not_cognition_event_time"
                if historical_transition_observation else "historical_transition_stage_event_time"
                if historical_transition_event else "historical_or_unknown"
                if historical_resource_fact or historical_resource_introspection
                or historical_undated_consequence or historical_unverified_owner_record
                or historical_strategy_proposal or historical_strategy_review
                or source_integrity_conflict
                else "source_time_unverified" if unverified_embodiment_observation
                else "source_time_missing" if missing_source_time
                else "source_observed"},
            sort_keys=True, separators=(",", ":"))
        proof = make_epistemic_evidence_source_proof(source_artifact_id=artifact_id,
            source_digest=stable_source_digest, source_schema=fact.source.schema_version,
            source_class=fact.source.kind, recorded_at=observed, adapter_id=ADAPTER_ID,
            provenance_id=provenance)
        # Source freshness is evidence metadata, not an adapter default.  A
        # degraded or undated snapshot must remain unknown; only a fresh,
        # healthy source may be represented as current.
        source_staleness = str(fact.source.staleness or "unknown").lower()
        if (not historical_resource_fact and not historical_resource_introspection
                and not historical_undated_consequence and not historical_unverified_owner_record
                and not historical_transition_event and not historical_chat_recovery_event
                and not historical_chat_runtime_observation
                and not historical_strategy_proposal and not historical_strategy_review
                and not unverified_embodiment_observation
                and source_staleness == "fresh" and fact.source.finding == "ok" and not snapshot.degraded):
            freshness = "current"
        elif source_staleness in {"aging", "stale", "expired"}:
            freshness = "stale"
        else:
            freshness = "unknown"
        binding = make_evidence_binding(proposition_id=rule.proposition_id,
            source_artifact_id=artifact_id, source_digest=stable_source_digest,
            source_schema=fact.source.schema_version, source_class=fact.source.kind,
            observation_time=observed,
            evidence_relation="contextualizes" if (unverified_source_context or historical_transition_event) else rule.evidence_relation,
            dependency_kind=("unknown_dependency" if (unverified_source_context or historical_transition_event)
                else rule.dependency_kind),
            dependency_group=(rule.independence_basis if rule.dependency_kind == "independently_sourced_observation"
                and not unverified_source_context and not historical_transition_event else None),
            upstream_binding_ids=(), freshness=freshness,
            reliability_posture=("qualified_historical_transition_owner_observation"
                if qualified_transition_observation
                else "unqualified_transition_observation_context" if historical_transition_observation
                else "historical_transition_event_context" if historical_transition_event
                else "proposal_source_not_world_truth" if historical_strategy_proposal
                else "unverified_review_context_only" if historical_strategy_review
                else "resource_lineage_incomplete_context_only" if incomplete_resource_lineage
                else "unverified_source_context_only" if unverified_source_context
                else rule.reliability_posture))
        return proof, binding

    def _issue(self, *, admission_id: str, effects: tuple[str, ...], subject_id: str,
               configuration_digest: str, provenance: str) -> Any:
        sequence = self._next_sequence()
        definition = RESIDENT_EPISTEMIC_STATE_MUTATION_DEFINITION
        return self.authority.issue(admission_id=admission_id,
            capability_id=RESIDENT_EPISTEMIC_STATE_MUTATION, definition_version=1,
            subsystem_kind="epistemics", principal_id=PRINCIPAL, principal_kind=PRINCIPAL,
            effects=effects, subject_id=subject_id,
            request_configuration_digest=configuration_digest, provenance=provenance,
            issued_sequence=sequence, valid_through_sequence=sequence,
            affirmative_preconditions=definition.approval_requirements)

    def process_snapshot(self, snapshot: WorldStateSnapshot, *, tick: int,
                         recorded_at: str) -> EpistemicDevelopmentFeedback:
        if not self.config.enabled:
            return EpistemicDevelopmentFeedback("disabled", snapshot.snapshot_id, len(self.config.rules), 0, 0, 0, (), (), (), ())
        validation = validate_snapshot(snapshot)
        if not validation.valid:
            raise EpistemicDevelopmentError("world_state_snapshot_invalid")
        matches = [(rule, fact) for rule in self.config.rules for fact in snapshot.facts if self._matches(rule, fact)]
        matches.sort(key=lambda pair: (pair[0].rule_id, pair[1].fact_id))
        bounded = matches[:self.config.max_new_bindings_per_tick]
        evidence_receipts: list[str] = []; touched: set[str] = set(); new_count = 0
        for rule, fact in bounded:
            proof, binding = self._adapt(snapshot, fact, rule); touched.add(rule.proposition_id)
            existing = {item.binding_id: item for item in self.owner.bindings(rule.proposition_id)}
            if binding.binding_id in existing:
                if existing[binding.binding_id] != binding:
                    raise EpistemicDevelopmentError("evidence_identity_collision")
                continue
            operation = f"{tick}:{rule.rule_id}:evidence"
            configuration = self.controller.evidence_configuration_digest(binding=binding,
                proposition_digest=rule.proposition_digest, operation_id=operation)
            admission = self._issue(admission_id=f"epistemic-E-{tick}-{new_count}-{binding.binding_id}",
                effects=EVIDENCE_BINDING_EFFECTS, subject_id=binding.binding_id,
                configuration_digest=configuration, provenance=proof.provenance_id)
            evidence_receipt = self.controller.append_evidence_binding(binding=binding, source_proof=proof,
                admission=admission, operation_id=operation, correlation_id=f"tick:{tick}:{rule.rule_id}")
            evidence_receipts.append(evidence_receipt.receipt_id); new_count += 1
        state_receipts: list[str] = []; states: list[str] = []; generations: list[int] = []
        for proposition_id in sorted(touched)[:self.config.max_updated_propositions_per_tick]:
            bindings = tuple(item for item in self.owner.bindings(proposition_id) if not item.withdrawn)
            if len(bindings) > MAX_ACTIVE_EVIDENCE:
                raise EpistemicDevelopmentError("active_evidence_bound_exceeded")
            active_ids = tuple(sorted(item.binding_id for item in bindings))
            prior = self.owner.current_state(proposition_id)
            if prior and set(active_ids) == set(self.owner.active_binding_ids(proposition_id)):
                continue
            posture = evidence_posture(bindings)["posture"]
            stance = {"support_only": "provisionally_supported", "contradiction_only": "provisionally_contradicted",
                "mixed": "contested", "all_evidence_stale": "suspended"}.get(str(posture))
            if stance is None: continue
            new_relations = {item.evidence_relation for item in bindings if not prior or item.binding_id not in self.owner.active_binding_ids(proposition_id)}
            reason = "contradiction_arrival" if "contradicts" in new_relations else "new_evidence"
            rules = sorted(rule.rule_id for rule in self.config.rules if rule.proposition_id == proposition_id)
            candidate = make_epistemic_update_candidate(proposition_id=proposition_id,
                predecessor_state_digest=prior.state_digest if prior else None, proposed_stance=stance,
                evidence_binding_ids=active_ids, reason=reason,
                rationale=f"{QUALITATIVE_RULE}:{posture}; dependency posture preserved",
                uncertainty="high" if evidence_posture(bindings)["dependency_unresolved"] else "medium",
                model_id=None, proposer_kind="deterministic_rule", proposer_id="+".join(rules))
            operation = f"{tick}:{proposition_id}:state"
            configuration = self.controller.state_configuration_digest(candidate=candidate, operation_id=operation)
            admission = self._issue(admission_id=f"epistemic-S-{tick}-{candidate.candidate_id}",
                effects=STATE_UPDATE_EFFECTS, subject_id=candidate.candidate_id,
                configuration_digest=configuration,
                provenance=f"tick:{tick};snapshot:{snapshot.snapshot_id};rules:{'+'.join(rules)}")
            state_receipt = self.controller.commit_update_candidate(candidate=candidate, admission=admission,
                operation_id=operation, correlation_id=f"tick:{tick}:epistemic-development",
                tick=tick, recorded_at=recorded_at)
            state_receipts.append(state_receipt.receipt_id); states.append(state_receipt.successor_state_id); generations.append(state_receipt.generation)
        partial = len(matches) > len(bounded) or len(touched) > self.config.max_updated_propositions_per_tick
        status = "bounded_partial" if partial else "state_advanced" if state_receipts else "evidence_appended" if evidence_receipts else "no_matching_evidence"
        return EpistemicDevelopmentFeedback(status, snapshot.snapshot_id, len(self.config.rules), len(matches),
            new_count, len(state_receipts), tuple(evidence_receipts), tuple(state_receipts), tuple(states), tuple(generations))


__all__ = ["ResidentEpistemicDevelopmentRuntime", "EpistemicDevelopmentConfig",
    "EpistemicDevelopmentRule", "EpistemicDevelopmentFeedback", "EpistemicDevelopmentError",
    "load_epistemic_development_config", "CONFIG_ENV"]
