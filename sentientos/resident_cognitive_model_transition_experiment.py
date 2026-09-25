"""Explicit, fail-closed A -> B -> A resident cognitive transition protocol."""
from __future__ import annotations
import hashlib, json, threading, time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Iterator, Mapping, Sequence

SCHEMA = "sentientos.resident_cognitive_model_transition_protocol:v1"
BINDING_SCHEMA = "sentientos.resident_cognitive_transition_stage_serving_binding:v1"
JOURNAL_SCHEMA = "sentientos.resident_cognitive_model_transition_journal_entry:v1"
PHASES = ("predecessor_a_epoch_current", "a_to_b_transition_requested", "a_quiesced",
 "b_activation_committed", "b_serving_bound", "b_epoch_resumed", "b_epoch_observed",
 "b_to_a_restoration_requested", "b_quiesced", "a_restoration_activation_committed",
 "restored_a_serving_bound", "restored_a_epoch_resumed", "post_restoration_observed",
 "experiment_complete")

class TransitionError(RuntimeError):
    def __init__(self, code: str): self.code=code; super().__init__(code)

def digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256((json.dumps(dict(value),sort_keys=True,separators=(",",":"))+"\n").encode()).hexdigest()

def history_boundary(records: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    exact=[dict(x) for x in records]
    body={"schema_version":"sentientos.developmental_history_boundary:v1","records":exact,
          "record_ids":[x.get("record_id") for x in exact],"record_digests":[x.get("record_digest") for x in exact]}
    return MappingProxyType({**body,"boundary_digest":digest(body)})

@dataclass(frozen=True)
class TransitionProtocol:
    value: Mapping[str, Any]
    @classmethod
    def create(cls, *, installation_identity: str, predecessor: Mapping[str,Any], successor: Mapping[str,Any],
               initial_activation: Mapping[str,Any], initial_session: Mapping[str,Any],
               initial_boundary: Mapping[str,Any], b_operation_id: str, restored_a_operation_id: str) -> "TransitionProtocol":
        body={"schema_version":SCHEMA,"installation_identity":installation_identity,
          "predecessor_a":dict(predecessor),"successor_b":dict(successor),"restored_a":dict(predecessor),
          "initial_activation":dict(initial_activation),"initial_resident_session":dict(initial_session),
          "initial_history_boundary":dict(initial_boundary),"phase_order":list(PHASES),
          "transitions":["A->B","B->A"],"b_serving_operation_id":b_operation_id,
          "restored_a_serving_operation_id":restored_a_operation_id,
          "failure_policy":"interrupt_no_retry_no_rollback","grants_authority":False,
          "nonclaims":["personal_identity","consciousness_continuity","selfhood_continuity","learning","improvement"]}
        pd=digest(body); value={**body,"protocol_id":"resident-transition-protocol-"+pd[:24],"protocol_digest":pd}
        return cls(MappingProxyType(value))
    def verify(self)->None:
        value=dict(self.value); claimed=value.pop("protocol_digest",None); value.pop("protocol_id",None)
        if self.value.get("schema_version")!=SCHEMA or self.value.get("phase_order")!=list(PHASES) or digest(value)!=claimed:
            raise TransitionError("protocol_tamper")

class ResidentCognitionQuiescenceGate:
    def __init__(self) -> None:
        self._condition=threading.Condition(); self._quiesced=False; self._inflight=0; self._generation=0
    @contextmanager
    def cycle(self) -> Iterator[None]:
        with self._condition:
            if self._quiesced: raise TransitionError("resident_cognition_quiesced")
            self._inflight+=1
        try: yield
        finally:
            with self._condition: self._inflight-=1; self._condition.notify_all()
    def quiesce(self, *, timeout_seconds: float, observation: Mapping[str,Any]) -> Mapping[str,Any]:
        deadline=time.monotonic()+timeout_seconds
        with self._condition:
            self._quiesced=True
            while self._inflight:
                remaining=deadline-time.monotonic()
                if remaining<=0: self._quiesced=False; self._condition.notify_all(); raise TransitionError("quiescence_timeout")
                self._condition.wait(remaining)
            self._generation+=1
            body={"schema_version":"sentientos.resident_cognition_quiescence:v1","generation":self._generation,
                  "no_inflight":True,"observation":dict(observation)}
            return MappingProxyType({**body,"token":"quiescence-"+digest(body)[:24],"observation_digest":digest(body)})
    def resume(self, token: Mapping[str,Any])->None:
        with self._condition:
            if not self._quiesced or token.get("generation")!=self._generation: raise TransitionError("quiescence_token_mismatch")
            self._quiesced=False; self._condition.notify_all()
    @property
    def quiesced(self)->bool:
        with self._condition:return self._quiesced

class QuiescedDevelopmentalCognitionOwner:
    def __init__(self, owner: Any, gate: ResidentCognitionQuiescenceGate): self._owner=owner; self.gate=gate
    def run_tick(self, **kwargs:Any)->Any:
        with self.gate.cycle(): return self._owner.run_tick(**kwargs)

class TransitionJournal:
    def __init__(self,path:Path): self.path=path; path.parent.mkdir(parents=True,exist_ok=True)
    def entries(self)->list[dict[str,Any]]:
        if not self.path.exists(): return []
        out=[]; prior="GENESIS"
        for line in self.path.read_text().splitlines():
            try: item=json.loads(line)
            except ValueError as exc: raise TransitionError("journal_tamper") from exc
            claimed=item.pop("entry_digest",None)
            if item.get("schema_version")!=JOURNAL_SCHEMA or item.get("prior_digest")!=prior or digest(item)!=claimed: raise TransitionError("journal_tamper")
            item["entry_digest"]=claimed; out.append(item); prior=claimed
        return out
    def append(self, phase:str, evidence:Mapping[str,Any], *, status:str="completed")->Mapping[str,Any]:
        entries=self.entries(); body={"schema_version":JOURNAL_SCHEMA,"sequence":len(entries)+1,
          "prior_digest":entries[-1]["entry_digest"] if entries else "GENESIS","phase":phase,"status":status,"evidence":dict(evidence)}
        item={**body,"entry_digest":digest(body)}
        with self.path.open("a",encoding="utf-8") as f: f.write(json.dumps(item,sort_keys=True,separators=(",",":"))+"\n"); f.flush()
        return MappingProxyType(item)

def stage_serving_binding(*, protocol:TransitionProtocol, stage:str, activation:Mapping[str,Any], expected_identity:Mapping[str,Any], operation_id:str)->Mapping[str,Any]:
    protocol.verify(); body={"schema_version":BINDING_SCHEMA,"protocol_id":protocol.value["protocol_id"],
      "protocol_digest":protocol.value["protocol_digest"],"stage":stage,"installation_identity":protocol.value["installation_identity"],
      "activation_state_digest":activation["state_semantic_digest"],"activation_generation":activation["generation"],
      "activation_receipt_id":activation["receipt_id"],"activation_receipt_digest":activation["receipt_semantic_digest"],
      "expected_model_identity":dict(expected_identity),"serving_operation_id":operation_id,
      "resident_serving_capability_id":"resident_cognitive_model_serving","grants_activation":False,
      "grants_model_serving":False,"grants_inference":False}
    return MappingProxyType({**body,"binding_digest":digest(body)})

class ResidentCognitiveModelTransitionController:
    """Advances exactly one phase per call; effect owners are injected, never duplicated."""
    def __init__(self, *, protocol:TransitionProtocol,journal:TransitionJournal,gate:ResidentCognitionQuiescenceGate,
                 slot:Any, history_snapshot:Callable[[],Mapping[str,Any]]):
        protocol.verify(); self.protocol=protocol; self.journal=journal; self.gate=gate; self.slot=slot; self.history_snapshot=history_snapshot
        self._failed=False; self._token:Mapping[str,Any]|None=None
    @property
    def phase(self)->str:
        entries=self.journal.entries(); return str(entries[-1]["phase"]) if entries else PHASES[0]
    def advance(self, *, evidence:Mapping[str,Any]|None=None, effect:Callable[[],Mapping[str,Any]]|None=None)->Mapping[str,Any]:
        self.protocol.verify()
        if self._failed: raise TransitionError("failed_stage_replay_forbidden")
        current=self.phase; index=PHASES.index(current)
        if index==len(PHASES)-1: raise TransitionError("experiment_already_complete")
        target=PHASES[index+1]; supplied=dict(evidence or {})
        # Persist the attempt before externally owned activation/serving effects.
        effectful=target in {"b_activation_committed","b_serving_bound","a_restoration_activation_committed","restored_a_serving_bound"}
        if effectful: self.journal.append(current,{"attempted_stage":target},status="attempted")
        try:
            if target in {"a_quiesced","b_quiesced"}:
                self._token=self.gate.quiesce(timeout_seconds=float(supplied.pop("timeout_seconds",5)),observation={**self.history_snapshot(),**supplied})
                supplied=dict(self._token)
            elif target in {"b_epoch_resumed","restored_a_epoch_resumed"}:
                if self._token is None: raise TransitionError("resume_without_quiescence")
                if effect is not None: supplied.update(effect())
                self.gate.resume(self._token); self._token=None
            elif effect is not None: supplied.update(effect())
            entry=self.journal.append(target,supplied)
            return MappingProxyType({"prior_phase":current,"phase":target,"journal_head":entry["entry_digest"],"advanced_one_stage":True})
        except Exception as exc:
            self._failed=True; self.journal.append(current,{"failed_stage":target,"error":getattr(exc,"code",type(exc).__name__)},status="failed")
            raise
    def health(self)->Mapping[str,Any]:
        entries=self.journal.entries(); return MappingProxyType({"schema_version":"sentientos.resident_cognitive_model_transition_health:v1",
          "status":"interrupted" if self._failed else "complete" if self.phase==PHASES[-1] else "in_progress",
          "phase":self.phase,"quiesced":self.gate.quiesced,"journal_head":entries[-1]["entry_digest"] if entries else "GENESIS","read_only":True})
