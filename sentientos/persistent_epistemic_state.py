"""Durable, model-independent epistemic positions over explicit propositions.

Evidence is not belief, belief is not truth, and belief is not authority.  This
module owns records; a cognitive worker may only submit a candidate.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

PROPOSITION_SCHEMA = "sentientos.epistemic_proposition:v1"
BINDING_SCHEMA = "sentientos.epistemic_evidence_binding:v1"
STATE_SCHEMA = "sentientos.epistemic_state:v1"
UPDATE_SCHEMA = "sentientos.epistemic_update_event:v1"
CANDIDATE_SCHEMA = "sentientos.epistemic_update_candidate:v1"
CALIBRATION_SCHEMA = "sentientos.epistemic_calibration_event:v1"
PROPOSITION_CLASSES = frozenset({"descriptive", "predictive", "causal_hypothesis", "capability", "environmental", "relational", "system_hypothesis"})
RELATIONS = frozenset({"refines", "narrows", "broadens", "supersedes", "contradicts", "related_to"})
EVIDENCE_RELATIONS = frozenset({"supports", "contradicts", "undercuts", "contextualizes", "resolves", "predictive_outcome", "reliability_evidence"})
DEPENDENCIES = frozenset({"same_source_derivation", "shared_upstream_evidence", "repeated_observation", "independently_sourced_observation", "duplicate_alias", "unknown_dependency"})
STANCES = frozenset({"unknown", "suspended", "provisionally_supported", "supported", "contested", "provisionally_contradicted", "contradicted", "superseded"})
UPDATE_REASONS = frozenset({"initialization", "new_evidence", "evidence_withdrawal", "contradiction_arrival", "duplicate_evidence_correction", "dependency_correction", "source_reliability_revision", "proposition_refinement", "update_rule_correction", "calibration_outcome", "operator_error_correction"})
FALSE_AUTHORITY = {"policy": False, "goal": False, "permission": False, "effect_admission": False, "adoption": False, "memory_retention": False, "truth_oracle": False}


class EpistemicStateError(ValueError):
    """Fail-closed identity, history, or admission error."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def _identity(prefix: str, payload: Mapping[str, Any]) -> tuple[str, str]:
    dg = digest(payload)
    return f"{prefix}:{dg[7:31]}", dg


def _authority(value: Mapping[str, bool]) -> None:
    if dict(value) != FALSE_AUTHORITY:
        raise EpistemicStateError("epistemic_authority_must_be_all_false")


@dataclass(frozen=True)
class EpistemicProposition:
    proposition_id: str; proposition_digest: str; namespace: str; subject: str; predicate: str
    object_value: Any; polarity: str; qualifiers: Mapping[str, Any]; temporal_scope: Mapping[str, Any]
    context_scope: Mapping[str, Any]; proposition_class: str; statement: str | None = None
    schema_version: str = PROPOSITION_SCHEMA

    def semantic_key(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "namespace": self.namespace, "subject": self.subject,
                "predicate": self.predicate, "object_value": self.object_value, "polarity": self.polarity,
                "qualifiers": self.qualifiers, "temporal_scope": self.temporal_scope,
                "context_scope": self.context_scope, "proposition_class": self.proposition_class}


def make_proposition(**kwargs: Any) -> EpistemicProposition:
    raw = EpistemicProposition("", "", **kwargs)
    if raw.proposition_class not in PROPOSITION_CLASSES or raw.polarity not in {"positive", "negative"} or not all((raw.namespace, raw.subject, raw.predicate)):
        raise EpistemicStateError("proposition_shape_invalid")
    pid, dg = _identity("proposition", raw.semantic_key())
    return replace(raw, proposition_id=pid, proposition_digest=dg)


@dataclass(frozen=True)
class PropositionRelation:
    source_proposition_id: str; target_proposition_id: str; relation: str; recorded_at: str


@dataclass(frozen=True)
class EvidenceBinding:
    binding_id: str; binding_digest: str; proposition_id: str; source_artifact_id: str
    source_digest: str; source_schema: str; source_class: str; observation_time: str
    evidence_relation: str; dependency_kind: str; dependency_group: str | None
    upstream_binding_ids: tuple[str, ...]; freshness: str; reliability_posture: str
    withdrawn: bool = False; superseded_by: str | None = None; authority: Mapping[str, bool] = None  # type: ignore[assignment]
    schema_version: str = BINDING_SCHEMA

    def payload(self) -> dict[str, Any]:
        value = asdict(self); value.pop("binding_id"); value.pop("binding_digest"); return value


def make_evidence_binding(**kwargs: Any) -> EvidenceBinding:
    kwargs.setdefault("authority", dict(FALSE_AUTHORITY))
    raw = EvidenceBinding("", "", **kwargs)
    if raw.evidence_relation not in EVIDENCE_RELATIONS or raw.dependency_kind not in DEPENDENCIES or raw.freshness not in {"current", "stale", "unknown"}:
        raise EpistemicStateError("evidence_binding_shape_invalid")
    _authority(raw.authority)
    bid, dg = _identity("evidence", raw.payload())
    return replace(raw, binding_id=bid, binding_digest=dg)


def evidence_posture(bindings: Sequence[EvidenceBinding]) -> Mapping[str, Any]:
    active = [b for b in bindings if not b.withdrawn]
    support = [b for b in active if b.evidence_relation == "supports" or (b.evidence_relation == "predictive_outcome" and b.reliability_posture == "supports")]
    contradiction = [b for b in active if b.evidence_relation == "contradicts" or (b.evidence_relation == "predictive_outcome" and b.reliability_posture == "contradicts")]
    if not active: posture = "evidence_withdrawn" if bindings else "no_evidence"
    elif all(b.freshness == "stale" for b in active): posture = "all_evidence_stale"
    elif support and contradiction: posture = "mixed"
    elif support: posture = "support_only"
    elif contradiction: posture = "contradiction_only"
    else: posture = "context_only"
    unresolved = any(b.dependency_kind == "unknown_dependency" for b in active)
    independent = {b.dependency_group or b.binding_id for b in active if b.dependency_kind == "independently_sourced_observation"}
    return {"posture": posture, "dependency_unresolved": unresolved,
            "insufficient_independent_evidence": len(independent) < 2, "record_count": len(bindings),
            "active_count": len(active), "independent_group_count": len(independent)}


@dataclass(frozen=True)
class EpistemicState:
    state_id: str; state_digest: str; proposition_id: str; generation: int
    predecessor_state_digest: str | None; stance: str; confidence: Mapping[str, Any] | None
    evidence_set_digest: str; support_binding_ids: tuple[str, ...]; contradiction_binding_ids: tuple[str, ...]
    dependency_unresolved: bool; freshness: str; last_update_event_id: str | None
    update_rule_id: str; created_at: str; updated_at: str; authority: Mapping[str, bool]
    schema_version: str = STATE_SCHEMA

    def payload(self) -> dict[str, Any]:
        value = asdict(self); value.pop("state_id"); value.pop("state_digest"); return value


@dataclass(frozen=True)
class EpistemicCognitiveProjection:
    """Prior-only fourth substrate; never a World-State fact."""
    projection_id: str; projection_digest: str; source_tick: int
    proposition_ids: tuple[str, ...]; state_ids: tuple[str, ...]
    state_digests: tuple[str, ...]; generations: tuple[int, ...]
    evidence_set_digests: tuple[str, ...]; states: tuple[Mapping[str, Any], ...]
    evidence_only: bool = False; prior_position_only: bool = True
    current_truth: bool = False; authority: bool = False; policy: bool = False; goal: bool = False


def make_cognitive_projection(states: Sequence[EpistemicState], *, source_tick: int, current_tick: int) -> EpistemicCognitiveProjection:
    if source_tick >= current_tick: raise EpistemicStateError("same_tick_epistemic_state_forbidden")
    ordered=tuple(sorted(states,key=lambda x:x.proposition_id)); payload={"source_tick":source_tick,
        "proposition_ids":tuple(x.proposition_id for x in ordered),"state_ids":tuple(x.state_id for x in ordered),
        "state_digests":tuple(x.state_digest for x in ordered),"generations":tuple(x.generation for x in ordered),
        "evidence_set_digests":tuple(x.evidence_set_digest for x in ordered),"states":tuple(asdict(x) for x in ordered),
        "evidence_only":False,"prior_position_only":True,"current_truth":False,"authority":False,"policy":False,"goal":False}
    pid,pdg=_identity("epistemic-projection",payload)
    return EpistemicCognitiveProjection(pid, pdg, source_tick, tuple(x.proposition_id for x in ordered),
        tuple(x.state_id for x in ordered), tuple(x.state_digest for x in ordered),
        tuple(x.generation for x in ordered), tuple(x.evidence_set_digest for x in ordered),
        tuple(asdict(x) for x in ordered))


@dataclass(frozen=True)
class EpistemicUpdateCandidate:
    candidate_id: str; proposition_id: str; predecessor_state_digest: str; proposed_stance: str
    evidence_binding_ids: tuple[str, ...]; reason: str; rationale: str; uncertainty: str
    model_id: str; authority: Mapping[str, bool]; schema_version: str = CANDIDATE_SCHEMA


@dataclass(frozen=True)
class EpistemicUpdateEvent:
    event_id: str; event_digest: str; proposition_id: str; prior_state_digest: str | None
    successor_state_digest: str; reason: str; added_binding_ids: tuple[str, ...]
    removed_binding_ids: tuple[str, ...]; dependency_changes: Mapping[str, str]
    reliability_changes: Mapping[str, str]; update_rule_revision: str | None
    candidate_id: str | None; validation_result: str; correlation_id: str; tick: int
    generation: int; authority: Mapping[str, bool]; schema_version: str = UPDATE_SCHEMA

    def payload(self) -> dict[str, Any]:
        value = asdict(self); value.pop("event_id"); value.pop("event_digest"); return value

    def identity_payload(self) -> dict[str, Any]:
        """Break the state/event mutual reference while retaining the successor field."""
        value = self.payload(); value.pop("successor_state_digest"); return value


@dataclass(frozen=True)
class EpistemicCalibrationEvent:
    calibration_id: str; calibration_digest: str; proposition_id: str; forecast_artifact_id: str
    forecast_state_digest: str; observed_outcome_id: str; comparison_result: str
    source_binding_ids: tuple[str, ...]; resolved_at: str; authority: Mapping[str, bool]
    schema_version: str = CALIBRATION_SCHEMA

    def payload(self) -> dict[str, Any]:
        value = asdict(self); value.pop("calibration_id"); value.pop("calibration_digest"); return value


def _write_new(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if path.read_bytes() != canonical_bytes(value) + b"\n": raise EpistemicStateError("immutable_record_collision")
        return
    with os.fdopen(fd, "wb") as handle: handle.write(canonical_bytes(value) + b"\n")


class PersistentEpistemicStateOwner:
    """Explicit-root immutable custody with verified reconstruction and CAS."""
    def __init__(self, root: str | Path, *, allowed_namespaces: Sequence[str]) -> None:
        self.root = Path(root); self.allowed_namespaces = frozenset(allowed_namespaces)
        if not self.allowed_namespaces: raise EpistemicStateError("allowed_namespaces_required")
        for part in ("propositions", "bindings", "states", "updates", "relations", "calibrations"): (self.root / part).mkdir(parents=True, exist_ok=True)
        self.verify()

    def _read(self, kind: str) -> list[dict[str, Any]]:
        values=[]
        for path in sorted((self.root / kind).glob("*.json")):
            try: values.append(json.loads(path.read_text()))
            except (OSError, json.JSONDecodeError) as exc: raise EpistemicStateError("epistemic_history_corrupt") from exc
        return values

    def register_proposition(self, proposition: EpistemicProposition) -> None:
        expected = make_proposition(**{k:v for k,v in asdict(proposition).items() if k not in {"proposition_id","proposition_digest","schema_version"}})
        if expected != proposition: raise EpistemicStateError("proposition_identity_mismatch")
        if proposition.namespace not in self.allowed_namespaces: raise EpistemicStateError("proposition_namespace_not_allowed")
        _write_new(self.root / "propositions" / f"{proposition.proposition_id}.json", asdict(proposition))

    def add_relation(self, relation: PropositionRelation) -> None:
        if relation.relation not in RELATIONS or relation.source_proposition_id == relation.target_proposition_id: raise EpistemicStateError("proposition_relation_invalid")
        self.proposition(relation.source_proposition_id); self.proposition(relation.target_proposition_id)
        _write_new(self.root / "relations" / f"{digest(asdict(relation))[7:]}.json", asdict(relation))

    def proposition(self, proposition_id: str) -> EpistemicProposition:
        path=self.root/"propositions"/f"{proposition_id}.json"
        if not path.is_file(): raise EpistemicStateError("proposition_not_found")
        value=EpistemicProposition(**json.loads(path.read_text())); expected=make_proposition(**{k:v for k,v in asdict(value).items() if k not in {"proposition_id","proposition_digest","schema_version"}})
        if value != expected: raise EpistemicStateError("proposition_identity_mismatch")
        return value

    def bind_evidence(self, binding: EvidenceBinding) -> None:
        self.proposition(binding.proposition_id)
        expected=make_evidence_binding(**{k:v for k,v in asdict(binding).items() if k not in {"binding_id","binding_digest","schema_version"}})
        if expected != binding: raise EpistemicStateError("evidence_binding_digest_mismatch")
        if binding.dependency_kind in {"same_source_derivation","shared_upstream_evidence","duplicate_alias"} and not binding.upstream_binding_ids: raise EpistemicStateError("evidence_dependency_missing_upstream")
        for upstream in binding.upstream_binding_ids:
            if not (self.root/"bindings"/f"{upstream}.json").is_file(): raise EpistemicStateError("evidence_upstream_not_found")
        _write_new(self.root/"bindings"/f"{binding.binding_id}.json", asdict(binding))

    def bindings(self, proposition_id: str) -> tuple[EvidenceBinding, ...]:
        return tuple(EvidenceBinding(**v) for v in self._read("bindings") if v["proposition_id"] == proposition_id)

    def current_state(self, proposition_id: str) -> EpistemicState | None:
        states=[EpistemicState(**v) for v in self._read("states") if v["proposition_id"] == proposition_id]
        return max(states, key=lambda x:x.generation) if states else None

    def commit_update(self, *, proposition_id: str, expected_predecessor_digest: str | None, stance: str,
                      reason: str, active_binding_ids: Sequence[str], added_binding_ids: Sequence[str] = (),
                      removed_binding_ids: Sequence[str] = (), dependency_changes: Mapping[str,str] = {},
                      reliability_changes: Mapping[str,str] = {}, update_rule_id: str = "qualitative_explicit:v1",
                      update_rule_revision: str | None = None, candidate: EpistemicUpdateCandidate | None = None,
                      correlation_id: str, tick: int, recorded_at: str, confidence: Mapping[str,Any] | None = None) -> tuple[EpistemicState, EpistemicUpdateEvent]:
        self.proposition(proposition_id); prior=self.current_state(proposition_id)
        actual=prior.state_digest if prior else None
        if actual != expected_predecessor_digest: raise EpistemicStateError("epistemic_state_compare_and_swap_failed")
        if stance not in STANCES or reason not in UPDATE_REASONS: raise EpistemicStateError("epistemic_update_vocabulary_invalid")
        if candidate and (candidate.proposition_id != proposition_id or candidate.predecessor_state_digest != expected_predecessor_digest or candidate.proposed_stance != stance or candidate.reason != reason or dict(candidate.authority) != FALSE_AUTHORITY): raise EpistemicStateError("epistemic_candidate_validation_failed")
        known={b.binding_id:b for b in self.bindings(proposition_id)}
        if (set(active_binding_ids) | set(added_binding_ids) | set(removed_binding_ids)) - set(known): raise EpistemicStateError("epistemic_evidence_not_found")
        selected=[known[x] for x in active_binding_ids]
        posture=evidence_posture(selected); support=tuple(sorted(b.binding_id for b in selected if b.evidence_relation=="supports" or b.reliability_posture=="supports")); contradiction=tuple(sorted(b.binding_id for b in selected if b.evidence_relation=="contradicts" or b.reliability_posture=="contradicts"))
        generation=(prior.generation+1 if prior else 0); state_payload={"proposition_id":proposition_id,"generation":generation,"predecessor_state_digest":actual,"stance":stance,"confidence":confidence,"evidence_set_digest":digest(sorted(active_binding_ids)),"support_binding_ids":support,"contradiction_binding_ids":contradiction,"dependency_unresolved":posture["dependency_unresolved"],"freshness":"stale" if posture["posture"]=="all_evidence_stale" else "current","last_update_event_id":None,"update_rule_id":update_rule_id,"created_at":prior.created_at if prior else recorded_at,"updated_at":recorded_at,"authority":dict(FALSE_AUTHORITY),"schema_version":STATE_SCHEMA}
        # Event/state circularity is avoided by binding event id into state after deriving an event commitment to successor semantics without that id.
        event_payload={"proposition_id":proposition_id,"prior_state_digest":actual,"successor_state_digest":"","reason":reason,"added_binding_ids":tuple(sorted(added_binding_ids)),"removed_binding_ids":tuple(sorted(removed_binding_ids)),"dependency_changes":dict(dependency_changes),"reliability_changes":dict(reliability_changes),"update_rule_revision":update_rule_revision,"candidate_id":candidate.candidate_id if candidate else None,"validation_result":"deterministically_validated","correlation_id":correlation_id,"tick":tick,"generation":generation,"authority":dict(FALSE_AUTHORITY),"schema_version":UPDATE_SCHEMA}
        identity_payload=dict(event_payload); identity_payload.pop("successor_state_digest")
        eid,edg=_identity("epistemic-update",identity_payload); state_payload["last_update_event_id"]=eid
        sid,sdg=_identity("epistemic-state",state_payload); event_payload["successor_state_digest"]=sdg
        state=EpistemicState(sid,sdg,proposition_id,generation,actual,stance,confidence,
            str(state_payload["evidence_set_digest"]),support,contradiction,bool(posture["dependency_unresolved"]),
            str(state_payload["freshness"]),eid,update_rule_id,prior.created_at if prior else recorded_at,
            recorded_at,dict(FALSE_AUTHORITY))
        event=EpistemicUpdateEvent(eid,edg,proposition_id,actual,sdg,reason,tuple(sorted(added_binding_ids)),
            tuple(sorted(removed_binding_ids)),dict(dependency_changes),dict(reliability_changes),update_rule_revision,
            candidate.candidate_id if candidate else None,"deterministically_validated",correlation_id,tick,generation,dict(FALSE_AUTHORITY))
        _write_new(self.root/"states"/f"{generation:012d}-{sid}.json",asdict(state)); _write_new(self.root/"updates"/f"{generation:012d}-{eid}.json",asdict(event))
        return state,event

    def record_calibration(self, **kwargs: Any) -> EpistemicCalibrationEvent:
        raw=EpistemicCalibrationEvent("","",authority=dict(FALSE_AUTHORITY),**kwargs); self.proposition(raw.proposition_id)
        states=[EpistemicState(**v) for v in self._read("states")]
        forecast=next((s for s in states if s.state_digest == raw.forecast_state_digest),None)
        if forecast is None: raise EpistemicStateError("calibration_forecast_state_missing")
        if forecast.proposition_id != raw.proposition_id: raise EpistemicStateError("calibration_forecast_proposition_mismatch")
        if raw.resolved_at <= forecast.updated_at: raise EpistemicStateError("calibration_outcome_not_after_forecast")
        bindings={b.binding_id:b for b in self.bindings(raw.proposition_id)}
        if not raw.source_binding_ids: raise EpistemicStateError("calibration_source_bindings_required")
        if set(raw.source_binding_ids)-set(bindings): raise EpistemicStateError("calibration_source_binding_missing_or_foreign")
        cid,dg=_identity("epistemic-calibration",raw.payload()); value=replace(raw,calibration_id=cid,calibration_digest=dg)
        _write_new(self.root/"calibrations"/f"{cid}.json",asdict(value)); return value

    def verify(self) -> Mapping[str,int]:
        propositions={}
        for raw in self._read("propositions"):
            proposition_value=EpistemicProposition(**raw); expected_proposition=make_proposition(**{k:v for k,v in raw.items() if k not in {"proposition_id","proposition_digest","schema_version"}})
            if proposition_value != expected_proposition: raise EpistemicStateError("proposition_identity_mismatch")
            propositions[proposition_value.proposition_id]=proposition_value
        bindings={}
        for raw in self._read("bindings"):
            binding_value=EvidenceBinding(**raw)
            if binding_value.proposition_id not in propositions: raise EpistemicStateError("evidence_proposition_missing")
            expected_binding=make_evidence_binding(**{k:v for k,v in raw.items() if k not in {"binding_id","binding_digest","schema_version"}})
            if binding_value != expected_binding: raise EpistemicStateError("evidence_binding_digest_mismatch")
            bindings[binding_value.binding_id]=binding_value
        states=[EpistemicState(**v) for v in self._read("states")]; events=[EpistemicUpdateEvent(**v) for v in self._read("updates")]
        event_by_generation={(e.proposition_id,e.generation):e for e in events}
        previous: dict[str, str] = {}
        for state in sorted(states,key=lambda x:(x.proposition_id,x.generation)):
            if state.proposition_id not in propositions or state.stance not in STANCES or dict(state.authority)!=FALSE_AUTHORITY: raise EpistemicStateError("epistemic_state_invalid")
            sid,sdg=_identity("epistemic-state",state.payload())
            if (sid,sdg)!=(state.state_id,state.state_digest): raise EpistemicStateError("epistemic_state_digest_mismatch")
            if state.predecessor_state_digest != previous.get(state.proposition_id): raise EpistemicStateError("epistemic_predecessor_missing_or_mismatch")
            event=event_by_generation.get((state.proposition_id,state.generation))
            if event is None or event.prior_state_digest != state.predecessor_state_digest or event.successor_state_digest != state.state_digest or event.event_id != state.last_update_event_id: raise EpistemicStateError("epistemic_update_event_missing_or_mismatch")
            previous[state.proposition_id]=state.state_digest
        for event in events:
            eid,edg=_identity("epistemic-update",event.identity_payload())
            if (eid,edg)!=(event.event_id,event.event_digest) or event.reason not in UPDATE_REASONS or dict(event.authority)!=FALSE_AUTHORITY: raise EpistemicStateError("epistemic_update_event_invalid")
        state_by_digest={s.state_digest:s for s in states}
        for raw in self._read("calibrations"):
            calibration=EpistemicCalibrationEvent(**raw); forecast=state_by_digest.get(calibration.forecast_state_digest)
            cid,cdg=_identity("epistemic-calibration",calibration.payload())
            if ((cid,cdg)!=(calibration.calibration_id,calibration.calibration_digest) or
                    calibration.proposition_id not in propositions or forecast is None or
                    forecast.proposition_id != calibration.proposition_id or
                    calibration.resolved_at <= forecast.updated_at or not calibration.source_binding_ids or
                    any(binding_id not in bindings or bindings[binding_id].proposition_id != calibration.proposition_id
                        for binding_id in calibration.source_binding_ids)):
                raise EpistemicStateError("epistemic_calibration_invalid")
        return {"propositions":len(propositions),"bindings":len(bindings),"states":len(states),"updates":len(events),"calibrations":len(self._read("calibrations"))}


def embodied_prediction_binding(*, proposition_id: str, expectation: Any, comparison: Any, attribution: Any, observation: Any) -> EvidenceBinding:
    """Explicit adapter; renderer output alone is never independent evidence."""
    if observation is None or getattr(observation,"observation_source_class","") in {"renderer","renderer_report","renderer_internal"}: raise EpistemicStateError("independent_observation_required")
    result=getattr(attribution,"attribution_result",getattr(comparison,"result",None))
    relation="supports" if result == "expectation_satisfied" else "contradicts" if result == "expectation_contradicted" else "contextualizes"
    return make_evidence_binding(proposition_id=proposition_id,source_artifact_id=observation.observation_id,source_digest=observation.observation_digest,source_schema=observation.schema_version,source_class=observation.observation_source_class,observation_time=observation.observed_at,evidence_relation=relation,dependency_kind="independently_sourced_observation",dependency_group=observation.observer_id,upstream_binding_ids=(),freshness="current",reliability_posture=relation)


__all__ = [name for name in tuple(globals()) if name.startswith("Epistemic") or name in {"PersistentEpistemicStateOwner","PropositionRelation","EvidenceBinding","make_proposition","make_evidence_binding","evidence_posture","embodied_prediction_binding","FALSE_AUTHORITY"}]
