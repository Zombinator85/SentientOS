"""Preregistered, non-destructive developmental-history projection experiment."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from .local_model_authority import atomic_write_json, digest_payload
from .resident_developmental_writeback import CognitionObservation, DevelopmentalHistoryProjection, measure_changed_cognition
from .windows_handle_custody import WindowsHandleCustodyError, read_explicit_file

LEGACY_SCHEMA = "sentientos.developmental_history_intervention_protocol:v1"
SCHEMA = "sentientos.developmental_history_intervention_protocol:v2"
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
    if (protocol.schema_version not in {LEGACY_SCHEMA, SCHEMA}
            or protocol.condition_order != CONDITION_ORDER or protocol.inference_purpose != PURPOSE
            or protocol.grants_authority):
        raise DevelopmentalHistoryInterventionError("protocol_control_invalid")


class DevelopmentalExperimentStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root) / "developmental_experiments"
        self.protocols = self.root / "protocols"; self.runs = self.root / "runs"

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            raw = read_explicit_file(path, max_bytes=MAX_EXPERIMENT_ARTIFACT_BYTES)
        except WindowsHandleCustodyError as exc:
            if str(exc) == "explicit_file_missing":
                raise FileNotFoundError(path) from exc
            raise DevelopmentalHistoryInterventionError("experiment_artifact_not_regular") from exc
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
        atomic_write_json(path, payload)

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
        return value


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
    )
    full_controls = all(hasattr(item, "current_snapshot_digest")
                        and hasattr(item, "retrieved_record_digests") for item in observations)
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
