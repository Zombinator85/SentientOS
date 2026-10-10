"""Bounded repeated attribution above one-shot post-adoption evaluations.

This owner records observational control evidence; it does not infer experimental
causation and has no mutation, adoption, scheduling, rollback, or provider authority.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from sentientos.maintenance_post_adoption_evaluation import Evaluation, FALSE_AUTHORITY

PROTOCOL_SCHEMA = "sentientos.maintenance_post_adoption_attribution_campaign_protocol:v1"
CONTROL_SCHEMA = "sentientos.maintenance_attribution_control_observation:v1"
TRIAL_SCHEMA = "sentientos.maintenance_attribution_campaign_trial:v1"
RESULT_SCHEMA = "sentientos.maintenance_post_adoption_attribution_campaign_result:v1"
ATTRIBUTION_POSTURE = "repeated_controlled_association_not_experimental_causation"
CONTROL_DESIGNS = frozenset({"observed_environmental_stability", "matched_repeated_conditions", "independently_replayed_workload", "contemporaneous_reference_observation", "randomized_experimental_intervention"})
SOURCE_CLASSES = frozenset({"world_state_evidence", "host_observation", "external_instrument", "operator_attested_observation", "independent_workload_replay", "contemporaneous_reference"})
RESULTS = frozenset({"repeated_association_under_matched_controls", "repeated_target_contradiction_under_matched_controls", "environmental_confound_detected", "heterogeneous_repeated_outcome", "no_detectable_target_change", "insufficient_target_evidence", "insufficient_control_evidence", "measurement_failure", "interrupted_or_invalid_trial", "protected_regression_observed", "indeterminate"})
TERMINAL_STATUSES = frozenset({"completed", "interrupted", "invalid"})


class AttributionCampaignError(ValueError):
    """Fail-closed campaign custody or admission error."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def _identity(prefix: str, payload: Mapping[str, Any]) -> tuple[str, str]:
    value = digest(payload)
    return f"{prefix}:{value[7:31]}", value


def _payload(value: Any, id_field: str, digest_field: str) -> dict[str, Any]:
    body = asdict(value); body.pop(id_field); body.pop(digest_field); return body


def _false(authority: Mapping[str, bool]) -> None:
    if dict(authority) != FALSE_AUTHORITY:
        raise AttributionCampaignError("campaign_authority_must_be_all_false")


@dataclass(frozen=True)
class ControlDefinition:
    observable_id: str
    measurement_law: str
    matching_rule: str
    source_requirement: str
    admissible_source_classes: tuple[str, ...]
    required: bool = True


@dataclass(frozen=True)
class CampaignProtocol:
    campaign_id: str; campaign_digest: str; maintenance_task_id: str; proposal_id: str
    signal_ids: tuple[str, ...]; predecessor_generation: int; predecessor_revision: str; predecessor_tree: str
    successor_generation: int; successor_revision: str; successor_tree: str; adoption_identity: str
    evaluation_protocol_ids: tuple[str, ...]; evaluation_protocol_digests: tuple[str, ...]
    target_observable_ids: tuple[str, ...]; target_measurement_laws: Mapping[str, str]
    protected_invariant_ids: tuple[str, ...]; controls: tuple[ControlDefinition, ...]
    control_design: str; attribution_rule: str; trial_ids: tuple[str, ...]
    minimum_trials: int; maximum_trials: int; evidence_class: str; created_at: str; creation_generation: int
    no_retry: bool; no_replacement: bool; no_cherry_picking: bool; authority: Mapping[str, bool]
    schema_version: str = PROTOCOL_SCHEMA
    def payload(self) -> dict[str, Any]: return _payload(self, "campaign_id", "campaign_digest")


def make_campaign_protocol(**kwargs: Any) -> CampaignProtocol:
    controls = tuple(x if isinstance(x, ControlDefinition) else ControlDefinition(**x) for x in kwargs.pop("controls"))
    raw = CampaignProtocol("", "", controls=controls, authority=dict(FALSE_AUTHORITY), **kwargs)
    _false(raw.authority)
    invalid = (not 2 <= raw.minimum_trials <= raw.maximum_trials <= 32 or len(raw.trial_ids) < raw.minimum_trials
        or len(raw.trial_ids) > raw.maximum_trials or len(set(raw.trial_ids)) != len(raw.trial_ids)
        or len(raw.evaluation_protocol_ids) != len(raw.trial_ids) or len(raw.evaluation_protocol_digests) != len(raw.trial_ids)
        or raw.successor_generation != raw.predecessor_generation + 1 or raw.control_design not in CONTROL_DESIGNS
        or raw.evidence_class not in {"production", "synthetic"} or not raw.controls or not raw.target_observable_ids
        or set(raw.target_measurement_laws) != set(raw.target_observable_ids)
        or len({x.observable_id for x in raw.controls}) != len(raw.controls)
        or any(not x.measurement_law or not x.matching_rule or not x.source_requirement or not x.admissible_source_classes
               or not set(x.admissible_source_classes) <= SOURCE_CLASSES for x in raw.controls)
        or not (raw.no_retry and raw.no_replacement and raw.no_cherry_picking))
    if invalid: raise AttributionCampaignError("campaign_protocol_invalid")
    cid, cdg = _identity("attribution-campaign", raw.payload())
    return replace(raw, campaign_id=cid, campaign_digest=cdg)


@dataclass(frozen=True)
class ControlObservation:
    control_id: str; control_digest: str; campaign_id: str; campaign_digest: str; trial_id: str
    observable_id: str; measurement_law: str; matching_rule: str; match_result: str
    before_value: Any; after_value: Any; source_identity: str; source_digest: str; source_schema: str
    source_class: str; observed_at: str; collector_identity: str; dependency_ids: tuple[str, ...]
    window_identity: str; world_state_binding: str | None; host_observation_binding: str | None
    evidence_class: str; authority: Mapping[str, bool]; schema_version: str = CONTROL_SCHEMA
    def payload(self) -> dict[str, Any]: return _payload(self, "control_id", "control_digest")


def make_control_observation(protocol: CampaignProtocol, **kwargs: Any) -> ControlObservation:
    raw = ControlObservation("", "", campaign_id=protocol.campaign_id, campaign_digest=protocol.campaign_digest,
                             authority=dict(FALSE_AUTHORITY), **kwargs)
    definition = next((x for x in protocol.controls if x.observable_id == raw.observable_id), None)
    if (definition is None or raw.trial_id not in protocol.trial_ids or raw.measurement_law != definition.measurement_law
        or raw.matching_rule != definition.matching_rule or raw.source_class not in definition.admissible_source_classes
        or raw.match_result not in {"matched", "out_of_envelope", "unmeasurable"}
        or not raw.source_identity or not raw.source_digest.startswith("sha256:") or not raw.source_schema
        or not raw.observed_at or not raw.collector_identity or not raw.window_identity
        or raw.evidence_class != protocol.evidence_class):
        raise AttributionCampaignError("control_observation_invalid")
    cid, cdg = _identity("control-observation", raw.payload())
    return replace(raw, control_id=cid, control_digest=cdg)


@dataclass(frozen=True)
class CampaignTrial:
    trial_record_id: str; trial_digest: str; campaign_id: str; campaign_digest: str; trial_id: str; trial_order: int
    terminal_status: str; evaluation_id: str | None; evaluation_digest: str | None; evaluation_protocol_id: str
    evaluation_protocol_digest: str; evaluation_result: str | None; evaluation_lineage: tuple[str, ...]
    control_ids: tuple[str, ...]; control_digests: tuple[str, ...]; outcome: str; completed_at: str
    authority: Mapping[str, bool]; schema_version: str = TRIAL_SCHEMA
    def payload(self) -> dict[str, Any]: return _payload(self, "trial_record_id", "trial_digest")


@dataclass(frozen=True)
class CampaignResult:
    result_id: str; result_digest: str; campaign_id: str; campaign_digest: str; ordered_trial_ids: tuple[str, ...]
    trial_record_ids: tuple[str, ...]; trial_digests: tuple[str, ...]; evaluation_ids: tuple[str, ...]
    evaluation_digests: tuple[str, ...]; control_ids: tuple[str, ...]; control_digests: tuple[str, ...]
    classification: str; attribution_posture: str; production_ready: bool; evidence_class: str
    completed_at: str; reconstruction_lineage: tuple[str, ...]; authority: Mapping[str, bool]
    schema_version: str = RESULT_SCHEMA
    def payload(self) -> dict[str, Any]: return _payload(self, "result_id", "result_digest")


def _evaluation_valid(value: Evaluation) -> bool:
    return bool(digest(value.payload()) == value.evaluation_digest and value.attribution_posture == "controlled_before_after_correlation_not_experimental_causation")


def _trial_outcome(evaluation: Evaluation | None, controls: Sequence[ControlObservation], status: str, definitions: Sequence[ControlDefinition]) -> str:
    if status != "completed": return "interrupted_or_invalid_trial"
    if evaluation is None or not _evaluation_valid(evaluation): return "insufficient_target_evidence"
    present = {x.observable_id for x in controls}
    if any(x.required and x.observable_id not in present for x in definitions): return "insufficient_control_evidence"
    if any(x.match_result == "unmeasurable" for x in controls): return "insufficient_control_evidence"
    if any(x.match_result == "out_of_envelope" for x in controls): return "environmental_confound_detected"
    return {"target_expectation_satisfied":"repeated_association_under_matched_controls",
        "target_expectation_contradicted":"repeated_target_contradiction_under_matched_controls",
        "new_regression_observed":"protected_regression_observed", "no_detectable_change":"no_detectable_target_change",
        "insufficient_evidence":"insufficient_target_evidence", "measurement_failed":"measurement_failure",
        "mixed_outcome":"heterogeneous_repeated_outcome"}.get(evaluation.result, "indeterminate")


class MaintenancePostAdoptionAttributionCampaignOwner:
    """Immutable, explicit-root custody for preregistered ordered campaigns."""
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve(); self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.root.is_symlink(): raise AttributionCampaignError("campaign_custody_unsafe")
        for name in ("protocols", "controls", "trials", "results", "signals"):
            (self.root / name).mkdir(exist_ok=True, mode=0o700)
        self.verify()

    def _write(self, kind: str, identity: str, value: Any) -> None:
        path = self.root / kind / (identity.replace(":", "-") + ".json")
        data = canonical_bytes(asdict(value) if not isinstance(value, Mapping) else value) + b"\n"
        try: fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
        except FileExistsError:
            if path.read_bytes() != data: raise AttributionCampaignError("immutable_campaign_record_conflict")
            return
        with os.fdopen(fd, "wb") as handle: handle.write(data); handle.flush(); os.fsync(handle.fileno())

    def _read(self, kind: str) -> list[dict[str, Any]]:
        values = []
        for path in sorted((self.root / kind).glob("*.json")):
            if path.is_symlink(): raise AttributionCampaignError("campaign_history_corrupt")
            try: values.append(json.loads(path.read_text()))
            except (OSError, json.JSONDecodeError) as exc: raise AttributionCampaignError("campaign_history_corrupt") from exc
        return values

    def preregister(self, protocol: CampaignProtocol) -> CampaignProtocol:
        rebuilt = make_campaign_protocol(**{k:v for k,v in asdict(protocol).items() if k not in {"campaign_id","campaign_digest","schema_version","authority"}})
        if rebuilt != protocol: raise AttributionCampaignError("campaign_protocol_digest_mismatch")
        self._write("protocols", protocol.campaign_id, protocol); return protocol

    def protocol(self, campaign_id: str) -> CampaignProtocol:
        rows = [x for x in self._read("protocols") if x["campaign_id"] == campaign_id]
        if len(rows) != 1: raise AttributionCampaignError("campaign_protocol_not_found")
        row = dict(rows[0]); row["controls"] = tuple(ControlDefinition(**{**x, "admissible_source_classes":tuple(x["admissible_source_classes"])}) for x in row["controls"])
        for field in ("signal_ids", "evaluation_protocol_ids", "evaluation_protocol_digests", "target_observable_ids", "protected_invariant_ids", "trial_ids"):
            row[field] = tuple(row[field])
        return CampaignProtocol(**row)

    def record_trial(self, protocol: CampaignProtocol, *, trial_id: str, evaluation: Evaluation | None,
                     controls: Sequence[ControlObservation], terminal_status: str, completed_at: str) -> CampaignTrial:
        stored = self.protocol(protocol.campaign_id)
        if stored != protocol: raise AttributionCampaignError("campaign_protocol_custody_mismatch")
        if any(x["campaign_id"] == protocol.campaign_id for x in self._read("results")): raise AttributionCampaignError("completed_campaign_replay_forbidden")
        if trial_id not in protocol.trial_ids or terminal_status not in TERMINAL_STATUSES: raise AttributionCampaignError("trial_not_preregistered")
        order = protocol.trial_ids.index(trial_id)
        existing = self._read("trials")
        if any(x["campaign_id"] == protocol.campaign_id and x["trial_id"] == trial_id for x in existing): raise AttributionCampaignError("trial_retry_or_replacement_forbidden")
        expected_next = len([x for x in existing if x["campaign_id"] == protocol.campaign_id])
        if order != expected_next: raise AttributionCampaignError("trial_order_or_omission_forbidden")
        if any(x.campaign_digest != protocol.campaign_digest or x.trial_id != trial_id for x in controls): raise AttributionCampaignError("control_campaign_lineage_mismatch")
        for control in controls:
            expected = make_control_observation(protocol, **{k:v for k,v in asdict(control).items() if k not in {"control_id","control_digest","campaign_id","campaign_digest","authority","schema_version"}})
            if expected != control: raise AttributionCampaignError("control_digest_mismatch")
        expected_pid = protocol.evaluation_protocol_ids[order]; expected_pdg = protocol.evaluation_protocol_digests[order]
        if evaluation is not None and (not _evaluation_valid(evaluation) or evaluation.protocol_id != expected_pid or evaluation.protocol_digest != expected_pdg
                or evaluation.predecessor_generation != protocol.predecessor_generation or evaluation.successor_generation != protocol.successor_generation
                or evaluation.predecessor_revision != protocol.predecessor_revision or evaluation.successor_revision != protocol.successor_revision):
            raise AttributionCampaignError("evaluation_campaign_lineage_mismatch")
        if terminal_status == "completed" and evaluation is None: raise AttributionCampaignError("completed_trial_requires_evaluation")
        outcome = _trial_outcome(evaluation, controls, terminal_status, protocol.controls)
        raw = CampaignTrial("", "", protocol.campaign_id, protocol.campaign_digest, trial_id, order, terminal_status,
            evaluation.evaluation_id if evaluation else None, evaluation.evaluation_digest if evaluation else None,
            expected_pid, expected_pdg, evaluation.result if evaluation else None,
            tuple(evaluation.reconstruction_lineage) if evaluation else (), tuple(x.control_id for x in controls),
            tuple(x.control_digest for x in controls), outcome, completed_at, dict(FALSE_AUTHORITY))
        tid, tdg = _identity("attribution-trial", raw.payload()); value = replace(raw, trial_record_id=tid, trial_digest=tdg)
        for control in controls: self._write("controls", control.control_id, control)
        self._write("trials", tid, value); return value

    def finalize(self, protocol: CampaignProtocol, *, completed_at: str) -> CampaignResult:
        if self.protocol(protocol.campaign_id) != protocol: raise AttributionCampaignError("campaign_protocol_custody_mismatch")
        trials = sorted((CampaignTrial(**x) for x in self._read("trials") if x["campaign_id"] == protocol.campaign_id), key=lambda x:x.trial_order)
        if tuple(x.trial_id for x in trials) != protocol.trial_ids: raise AttributionCampaignError("campaign_incomplete_no_selective_aggregation")
        outcomes = {x.outcome for x in trials}
        if "protected_regression_observed" in outcomes: classification = "protected_regression_observed"
        elif "interrupted_or_invalid_trial" in outcomes: classification = "interrupted_or_invalid_trial"
        elif "measurement_failure" in outcomes: classification = "measurement_failure"
        elif "insufficient_target_evidence" in outcomes: classification = "insufficient_target_evidence"
        elif "insufficient_control_evidence" in outcomes: classification = "insufficient_control_evidence"
        elif "environmental_confound_detected" in outcomes: classification = "environmental_confound_detected"
        elif len(outcomes) > 1: classification = "heterogeneous_repeated_outcome"
        else: classification = next(iter(outcomes), "indeterminate")
        controls = sorted((x for x in self._read("controls") if x["campaign_id"] == protocol.campaign_id),
                          key=lambda x:(protocol.trial_ids.index(x["trial_id"]), x["observable_id"]))
        # ``evidence_class`` and collector/source identities are caller supplied;
        # this owner has no authenticated issuer verifier and cannot certify
        # production readiness from those declarations alone.
        production_ready = False
        lineage = (protocol.campaign_digest,) + tuple(x.trial_digest for x in trials) + tuple(x["control_digest"] for x in controls)
        raw = CampaignResult("", "", protocol.campaign_id, protocol.campaign_digest, protocol.trial_ids,
            tuple(x.trial_record_id for x in trials), tuple(x.trial_digest for x in trials),
            tuple(x.evaluation_id for x in trials if x.evaluation_id), tuple(x.evaluation_digest for x in trials if x.evaluation_digest),
            tuple(x["control_id"] for x in controls), tuple(x["control_digest"] for x in controls), classification,
            ATTRIBUTION_POSTURE, production_ready, protocol.evidence_class, completed_at, lineage, dict(FALSE_AUTHORITY))
        rid, rdg = _identity("attribution-result", raw.payload()); value = replace(raw, result_id=rid, result_digest=rdg)
        self._write("results", rid, value)
        signal = campaign_improvement_signal_record(value)
        if signal: self._write("signals", rid, signal)
        return value

    def result(self, campaign_id: str) -> CampaignResult:
        rows = [x for x in self._read("results") if x["campaign_id"] == campaign_id]
        if len(rows) != 1: raise AttributionCampaignError("campaign_result_not_found")
        row = dict(rows[0])
        for field in ("ordered_trial_ids", "trial_record_ids", "trial_digests", "evaluation_ids", "evaluation_digests", "control_ids", "control_digests", "reconstruction_lineage"):
            row[field] = tuple(row[field])
        return CampaignResult(**row)

    def verify(self) -> Mapping[str, int]:
        protocols = {}
        for row in self._read("protocols"):
            rebuilt = make_campaign_protocol(**{k:v for k,v in row.items() if k not in {"campaign_id","campaign_digest","schema_version","authority"}})
            if rebuilt.campaign_digest != row["campaign_digest"]: raise AttributionCampaignError("campaign_history_corrupt")
            protocols[row["campaign_id"]] = row
        controls = {x["control_id"]:x for x in self._read("controls")}; trials = {x["trial_record_id"]:x for x in self._read("trials")}
        for row in controls.values():
            if row["campaign_id"] not in protocols or digest({k:v for k,v in row.items() if k not in {"control_id","control_digest"}}) != row["control_digest"]: raise AttributionCampaignError("campaign_history_corrupt")
            _false(row["authority"])
        for row in trials.values():
            if row["campaign_id"] not in protocols or any(x not in controls for x in row["control_ids"]) or digest({k:v for k,v in row.items() if k not in {"trial_record_id","trial_digest"}}) != row["trial_digest"]: raise AttributionCampaignError("campaign_history_corrupt")
            _false(row["authority"])
        for row in self._read("results"):
            if row["campaign_id"] not in protocols or any(x not in trials for x in row["trial_record_ids"]) or row["classification"] not in RESULTS or digest({k:v for k,v in row.items() if k not in {"result_id","result_digest"}}) != row["result_digest"]: raise AttributionCampaignError("campaign_history_corrupt")
            _false(row["authority"])
        return {"protocols":len(protocols), "controls":len(controls), "trials":len(trials), "results":len(self._read("results")), "signals":len(self._read("signals"))}


def campaign_epistemic_binding(*, proposition_id: str, result: CampaignResult) -> Any:
    from sentientos.persistent_epistemic_state import make_evidence_binding
    expected_id, expected_digest = _identity("attribution-result", result.payload())
    _false(result.authority)
    if (result.schema_version != RESULT_SCHEMA or result.attribution_posture != ATTRIBUTION_POSTURE
            or result.classification not in RESULTS
            or (result.result_id, result.result_digest) != (expected_id, expected_digest)):
        raise AttributionCampaignError("campaign_result_identity_unverified")
    # Control source identities/classes are caller supplied and have no
    # authenticated issuer in this owner. Preserve the aggregate as historical
    # context without calling it independent or fresh evidence.
    return make_evidence_binding(proposition_id=proposition_id,
        source_artifact_id=result.result_id, source_digest=result.result_digest,
        source_schema=result.schema_version, source_class="post_adoption_attribution_campaign",
        observation_time=result.completed_at, evidence_relation="contextualizes",
        dependency_kind="unknown_dependency", dependency_group=None,
        upstream_binding_ids=(), freshness="unknown",
        reliability_posture="control_source_issuers_unverified")


def developmental_evidence_record(result: CampaignResult) -> Mapping[str, Any]:
    return {"source_kind":"post_adoption_attribution_campaign", "result_id":result.result_id,
        "result_digest":result.result_digest, "campaign_id":result.campaign_id, "campaign_digest":result.campaign_digest,
        "classification":result.classification, "evaluation_ids":result.evaluation_ids, "control_ids":result.control_ids,
        "reconstruction_lineage":result.reconstruction_lineage, "selectable_evidence_only":True,
        "interpretation_performed":False, "authority":dict(FALSE_AUTHORITY)}


def campaign_improvement_signal_record(result: CampaignResult) -> Mapping[str, Any] | None:
    kinds = {"repeated_target_contradiction_under_matched_controls":"recurring_failure",
        "protected_regression_observed":"recurring_failure", "heterogeneous_repeated_outcome":"recurring_failure",
        "environmental_confound_detected":"telemetry_gap", "insufficient_control_evidence":"telemetry_gap",
        "insufficient_target_evidence":"telemetry_gap", "measurement_failure":"telemetry_gap"}
    kind = kinds.get(result.classification)
    if kind is None: return None
    return {"source_kind":"post_adoption_attribution_campaign", "finding_kind":kind,
        "severity":"high" if result.classification == "protected_regression_observed" else "medium",
        "description":f"Campaign-level {result.classification} for {result.campaign_id}",
        "spec_id":result.campaign_id, "source_artifact":result.result_id, "source_digest":result.result_digest,
        "evidence_refs":list(result.reconstruction_lineage), "observed_at":result.completed_at,
        "declared_constraints":["proposal_only","campaign_level_distinct_finding","no_repository_mutation","no_adoption","no_rollback"],
        "signal_handoff_only":True, "repository_mutation_performed":False, "adoption_performed":False,
        "provider_or_network_or_git_operation_performed":False, "trial_performed":False}


__all__ = ["MaintenancePostAdoptionAttributionCampaignOwner", "AttributionCampaignError", "ControlDefinition",
    "CampaignProtocol", "ControlObservation", "CampaignTrial", "CampaignResult", "make_campaign_protocol",
    "make_control_observation", "campaign_epistemic_binding", "developmental_evidence_record",
    "campaign_improvement_signal_record", "ATTRIBUTION_POSTURE", "RESULTS", "SOURCE_CLASSES", "CONTROL_DESIGNS"]
