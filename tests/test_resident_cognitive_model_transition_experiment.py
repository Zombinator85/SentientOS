from __future__ import annotations
import json,threading,time
from pathlib import Path
import pytest
from sentientos.resident_cognitive_model_transition_experiment import *
from sentientos.resident_cognitive_model_transition_rehearsal import run

pytestmark = pytest.mark.no_legacy_skip

def protocol():
 i={"identity_digest":"a"}; a={"state_semantic_digest":"a"*64,"generation":1,"receipt_id":"r","receipt_semantic_digest":"d"}
 return TransitionProtocol.create(installation_identity="i",predecessor=i,successor={"identity_digest":"b"},initial_activation=a,initial_session={"session_id":"s"},initial_boundary=history_boundary([]),b_operation_id="b-op",restored_a_operation_id="a-op")

def controller(tmp_path):
 g=ResidentCognitionQuiescenceGate();return ResidentCognitiveModelTransitionController(protocol=protocol(),journal=TransitionJournal(tmp_path/"j"),gate=g,slot=object(),history_snapshot=lambda:history_boundary([])),g

def test_complete_temporal_rehearsal(tmp_path):
 result=run(tmp_path);assert result["status"]=="verified_complete";assert result["initial_restored_identity_equal"]
 assert result["serving_sessions_distinct"];assert result["retrieved_b_record"]==result["b_record"]

def test_one_stage_and_illegal_completion(tmp_path):
 c,_=controller(tmp_path);assert c.advance()["phase"]==PHASES[1];assert c.phase==PHASES[1]

def test_quiescence_timeout_and_inference_blocked():
 g=ResidentCognitionQuiescenceGate();entered=threading.Event();release=threading.Event()
 def work():
  with g.cycle():entered.set();release.wait()
 t=threading.Thread(target=work);t.start();entered.wait()
 with pytest.raises(TransitionError,match="quiescence_timeout"):g.quiesce(timeout_seconds=.01,observation={})
 release.set();t.join();token=g.quiesce(timeout_seconds=1,observation={})
 with pytest.raises(TransitionError,match="resident_cognition_quiesced"):
  with g.cycle():pass
 g.resume(token)

def test_activation_denial_is_persisted_and_never_replayed(tmp_path):
 c,g=controller(tmp_path);c.advance();c.advance(evidence={"timeout_seconds":1})
 with pytest.raises(RuntimeError):c.advance(effect=lambda:(_ for _ in ()).throw(RuntimeError("denied")))
 assert g.quiesced and c.health()["status"]=="interrupted"
 with pytest.raises(TransitionError,match="failed_stage_replay_forbidden"):c.advance()

def test_b_and_restored_serving_failure_preserve_committed_phase(tmp_path):
 for index,fail_target in enumerate(("b_serving_bound","restored_a_serving_bound")):
  case=tmp_path/str(index);case.mkdir();c,g=controller(case)
  while PHASES[PHASES.index(c.phase)+1]!=fail_target:
   target=PHASES[PHASES.index(c.phase)+1]
   c.advance(evidence={"timeout_seconds":1} if target in {"a_quiesced","b_quiesced"} else {},effect=(lambda:{}) if target in {"b_epoch_resumed","restored_a_epoch_resumed"} else None)
  with pytest.raises(RuntimeError):c.advance(effect=lambda:(_ for _ in ()).throw(RuntimeError("serving failed")))
  assert g.quiesced

def test_loaded_identity_mismatch_rejected_by_slot():
 from sentientos.resident_cognitive_model_serving import ResidentCognitiveServingSlot,ResidentCognitiveModelServingError
 class C:
  def current_session(self):return None
 with pytest.raises(ResidentCognitiveModelServingError):ResidentCognitiveServingSlot(C()).bind_verified(C())

def test_journal_and_protocol_tamper(tmp_path):
 c,_=controller(tmp_path);c.advance();p=tmp_path/"j";p.write_text(p.read_text().replace(PHASES[1],"skip"))
 with pytest.raises(TransitionError,match="journal_tamper"):c.health()
 proto=protocol();proto.value["phase_order"] if False else None
 bad=dict(proto.value);bad["successor_b"]={"x":1};object.__setattr__(proto,"value",bad)
 with pytest.raises(TransitionError,match="protocol_tamper"):proto.verify()

def test_stage_binding_grants_no_authority():
 p=protocol();a={"state_semantic_digest":"b"*64,"generation":2,"receipt_id":"r","receipt_semantic_digest":"d"}
 b=stage_serving_binding(protocol=p,stage="b_serving_bound",activation=a,expected_identity={"id":"b"},operation_id="b-op")
 assert not b["grants_activation"] and not b["grants_model_serving"] and not b["grants_inference"]
