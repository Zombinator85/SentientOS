"""Preregistered, non-destructive developmental-history projection experiment."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from .local_model_authority import atomic_write_json, digest_payload
from .resident_developmental_writeback import CognitionObservation, DevelopmentalHistoryProjection, measure_changed_cognition

SCHEMA = "sentientos.developmental_history_intervention_protocol:v1"
RUN_SCHEMA = "sentientos.developmental_history_intervention_run:v1"
PURPOSE = "resident_developmental_history_intervention_experiment"
CONDITION_ORDER = ("history_present", "history_withheld", "history_restored")
NON_CLAIMS = ("learning", "improvement", "persistent_individuality", "selfhood", "consciousness", "sentience", "causal_closure")


class DevelopmentalHistoryInterventionError(ValueError):
    pass


def _digest(value: Any) -> str:
    return "sha256:" + digest_payload(value)


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
    grants_authority: bool = False
    schema_version: str = SCHEMA

    def semantic_payload(self) -> dict[str, Any]:
        value = asdict(self); value.pop("protocol_id"); value.pop("protocol_digest"); return value


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
    if protocol.condition_order != CONDITION_ORDER or protocol.inference_purpose != PURPOSE or protocol.grants_authority:
        raise DevelopmentalHistoryInterventionError("protocol_control_invalid")


class DevelopmentalExperimentStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root) / "developmental_experiments"
        self.protocols = self.root / "protocols"; self.runs = self.root / "runs"

    @staticmethod
    def _write_immutable(path: Path, payload: Mapping[str, Any]) -> None:
        if path.exists():
            if json.loads(path.read_text(encoding="utf-8")) != dict(payload):
                raise DevelopmentalHistoryInterventionError("artifact_identity_collision")
            return
        atomic_write_json(path, payload)

    def persist_protocol(self, protocol: DevelopmentalHistoryInterventionProtocol) -> None:
        verify_protocol(protocol)
        self._write_immutable(self.protocols / f"{protocol.protocol_id}.json", asdict(protocol))
        payload = json.loads((self.protocols / f"{protocol.protocol_id}.json").read_text())
        for key in ("current_fact_ids", "record_ids", "record_digests", "condition_order", "planned_comparisons", "non_claims"):
            payload[key] = tuple(payload[key])
        loaded = DevelopmentalHistoryInterventionProtocol(**payload)
        verify_protocol(loaded)

    def persist_run(self, payload: Mapping[str, Any]) -> str:
        semantic = dict(payload); semantic["schema_version"] = RUN_SCHEMA
        digest = _digest(semantic); run_id = "devexp-run-" + digest[7:31]
        self._write_immutable(self.runs / f"{run_id}.json", {**semantic, "run_id": run_id, "run_digest": digest})
        return run_id


def summarize(protocol: DevelopmentalHistoryInterventionProtocol, observations: Sequence[Any]) -> dict[str, Any]:
    if tuple(x.condition_id for x in observations) != CONDITION_ORDER:
        raise DevelopmentalHistoryInterventionError("condition_order_violated")
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
