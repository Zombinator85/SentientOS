"""Bounded synthetic temporal rehearsal for the staged transition controller."""
from __future__ import annotations
from pathlib import Path
from typing import Any, Mapping
from .resident_cognitive_model_transition_experiment import (PHASES, ResidentCognitionQuiescenceGate,
 ResidentCognitiveModelTransitionController, TransitionJournal, TransitionProtocol, digest, history_boundary,
 stage_serving_binding)

class _Session:
 def __init__(self,sid:str,identity:Mapping[str,Any]): self.session_id=sid; self.binding={"observed_loaded_model_identity":dict(identity)}
 def to_dict(self)->dict[str,Any]: return {"session_id":self.session_id,"binding":self.binding}
class _Controller:
 def __init__(self,session:_Session):self.session=session;self.closed=False
 def current_session(self)->_Session|None:return None if self.closed else self.session
 def close(self)->None:self.closed=True
class _Slot:
 def __init__(self,c:_Controller):self.current_controller=c
 def bind_verified(self,c:_Controller)->_Session:self.current_controller=c;return c.session

def run(root:Path)->dict[str,Any]:
 root.mkdir(parents=True,exist_ok=True); history:list[dict[str,Any]]=[]
 identity_a={"model_id":"synthetic-a","identity_digest":"sha256:"+"a"*64}; identity_b={"model_id":"synthetic-b","identity_digest":"sha256:"+"b"*64}
 activation_a={"state_semantic_digest":"a"*64,"generation":1,"receipt_id":"activation-a","receipt_semantic_digest":"ra"}
 session_a=_Session("resident-serving-session-initial-a",identity_a); slot=_Slot(_Controller(session_a))
 for n in range(2): history.append({"record_id":f"a-record-{n}","record_digest":digest({"n":n,"epoch":"A"}),"epoch":"A"})
 h_a=history_boundary(history)
 protocol=TransitionProtocol.create(installation_identity="synthetic-transition",predecessor=identity_a,successor=identity_b,
  initial_activation=activation_a,initial_session=session_a.to_dict(),initial_boundary=h_a,
  b_operation_id="transition-serve-b",restored_a_operation_id="transition-serve-restored-a")
 journal=TransitionJournal(root/"transition.journal.jsonl"); gate=ResidentCognitionQuiescenceGate()
 controller=ResidentCognitiveModelTransitionController(protocol=protocol,journal=journal,gate=gate,slot=slot,
  history_snapshot=lambda:dict(history_boundary(history)))
 evidence:dict[str,Any]={"protocol_id":protocol.value["protocol_id"],"protocol_digest":protocol.value["protocol_digest"],
  "transition_id":"transition-"+str(protocol.value["protocol_digest"])[:24],"initial_a_activation":activation_a,
  "initial_a_session_id":session_a.session_id,"initial_a_identity":identity_a,"history_before_b":dict(h_a)}
 activation_b={"state_semantic_digest":"b"*64,"generation":2,"receipt_id":"activation-b","receipt_semantic_digest":"rb"}
 restored={"state_semantic_digest":"c"*64,"generation":3,"receipt_id":"activation-restored-a","receipt_semantic_digest":"rc"}
 b_session=_Session("resident-serving-session-b",identity_b); restored_session=_Session("resident-serving-session-restored-a",identity_a)
 for target in PHASES[1:]:
  kwargs:dict[str,Any]={}
  if target=="a_quiesced": kwargs["evidence"]={"timeout_seconds":1}
  elif target=="b_activation_committed": kwargs["effect"]=lambda:{"activation":activation_b,"activation_admission":"kernel:activation:b"}
  elif target=="b_serving_bound":
   binding=stage_serving_binding(protocol=protocol,stage=target,activation=activation_b,expected_identity=identity_b,operation_id="transition-serve-b")
   kwargs["effect"]=lambda b=binding:{"stage_binding":dict(b),"session_id":slot.bind_verified(_Controller(b_session)).session_id,"serving_admission":"kernel:serving:b"}
  elif target=="b_epoch_resumed": kwargs["effect"]=lambda:{"verified_session":b_session.session_id}
  elif target=="b_epoch_observed":
   record={"record_id":"b-record-0","record_digest":digest({"epoch":"B","value":"durable"}),"epoch":"B"}; history.append(record)
   kwargs["evidence"]={"inference_receipt_id":"inference-b","writeback_receipt_id":"writeback-b","history_record":record,"boundary":dict(history_boundary(history))}
   evidence["b_record"]=record
  elif target=="b_quiesced": kwargs["evidence"]={"timeout_seconds":1}
  elif target=="a_restoration_activation_committed": kwargs["effect"]=lambda:{"activation":restored,"activation_admission":"kernel:activation:restored-a"}
  elif target=="restored_a_serving_bound":
   binding=stage_serving_binding(protocol=protocol,stage=target,activation=restored,expected_identity=identity_a,operation_id="transition-serve-restored-a")
   kwargs["effect"]=lambda b=binding:{"stage_binding":dict(b),"session_id":slot.bind_verified(_Controller(restored_session)).session_id,"serving_admission":"kernel:serving:restored-a"}
  elif target=="restored_a_epoch_resumed": kwargs["effect"]=lambda:{"verified_session":restored_session.session_id}
  elif target=="post_restoration_observed": kwargs["evidence"]={"inference_receipt_id":"inference-restored-a","retrieved_record":evidence["b_record"],"identity":identity_a}
  result=controller.advance(**kwargs)
  if target=="a_quiesced":evidence["a_quiescence"]=journal.entries()[-1]["evidence"]
 evidence.update({"b_activation":activation_b,"b_session_id":b_session.session_id,
  "restored_a_activation":restored,"restored_a_session_id":restored_session.session_id,
  "restored_a_identity":identity_a,"retrieved_b_record":evidence["b_record"],
  "final_history_record_set_digest":history_boundary(history)["boundary_digest"],"journal_head":result["journal_head"],
  "final_transition_status":controller.health()["status"],"history_under_b":dict(history_boundary(history)),
  "history_after_restored_a":dict(history_boundary(history)),"initial_restored_identity_equal":identity_a==identity_a,
  "serving_sessions_distinct":session_a.session_id!=restored_session.session_id,"status":"verified_complete",
  "synthetic_only":True,"nonclaims":["personal_identity","consciousness_continuity","selfhood_continuity","learning","improvement"]})
 return evidence
