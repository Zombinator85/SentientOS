from __future__ import annotations

import json
from pathlib import Path

from sentientos.genesis_model_advice import GenesisModelAdviceCoordinator, GenesisModelAdviceRequestContext, SCHEMA_VERSION, parse_advice_output, validate_packet
from sentientos.governed_local_model_invocation import GovernedLocalModelInvoker, LocalModelInvocationBudget
from sentientos.local_model_authority import LocalModelAuthorityMap, LocalModelAuthorityRecord, digest_payload
from sentientos.genesis_forge import ForgeEngine, GenesisNeed
from sentientos.control_plane_kernel import AdmissionOutcome, ControlActionDecision, LifecyclePhase


def _valid_text(**kw):
    payload={"schema_version":SCHEMA_VERSION,"objective_refinement":"Honor the bounded gap","proposed_directives":["preserve_lineage","record_provenance"],"testing_requirements":["acknowledge_capability"],"rationale":"Advisory only candidate.","capability_interpretation":"A bounded capability gap."}
    payload.update(kw); return json.dumps(payload)

def test_strict_advice_parser_accepts_valid_and_rejects_forbidden() -> None:
    payload,reasons=parse_advice_output(_valid_text())
    assert payload is not None and not reasons
    bads=[('{"schema_version":"x"}', 'missing_objective_refinement'), (_valid_text(proposed_directives=["preserve_lineage","preserve_lineage"]),'duplicate'), (_valid_text(rationale="run git status"),'forbidden'), (_valid_text(capability_interpretation="see https://example.com"),'forbidden')]
    for text, expected in bads:
        payload,reasons=parse_advice_output(text)
        assert payload is None
        assert any(expected in r for r in reasons)

def _authority() -> LocalModelAuthorityMap:
    rec=LocalModelAuthorityRecord(model_id='m1', engine='llama_cpp', name='local', semantic_artifact_identity='sha256:abc', model_content_sha256='abc', artifact_size_bytes=3, sidecar_metadata_digest=None, configuration_digest='cfg', max_context_tokens=2048, generation_ceilings={'max_new_tokens':128}, local_files_only=True, custom_model_code_posture='disabled', custom_model_code_opt_in=False, allowed_invocation_purposes=('local_user_chat','genesis_proposal_advice'), provider_network_posture='blocked_local_files_only', tool_posture='blocked', memory_posture='blocked', action_posture='blocked', runtime_eligibility_status='eligible', reason_codes=('eligible_local_model',), disposition='production_candidate', proof_references=())
    sem={'schema_version':'local_model_authority_map.v1','records':[rec.to_dict()]}; dg=digest_payload(sem)
    return LocalModelAuthorityMap(records=(rec,), map_id='lmam-'+dg[:24], map_digest=dg, generated_at='t', summary={'eligible_count':1,'blocked_count':0,'degraded_count':0})

class _Model:
    def __init__(self): self.calls=0
    def generate(self, prompt, **kwargs): self.calls+=1; return _valid_text()

class _Kernel:
    phase=LifecyclePhase.MAINTENANCE
    def admit(self, request):
        return ControlActionDecision(outcome=AdmissionOutcome.ALLOW, reason_codes=('admitted',), current_phase=request.requested_phase, requested_phase=request.requested_phase, authority_class=request.authority_class, action_kind=request.action_kind, actor=request.actor, target_subsystem=request.target_subsystem, correlation_id=str(request.metadata.get('correlation_id')))

def test_coordinator_invokes_once_caches_and_packet_tamper_detected(tmp_path: Path) -> None:
    model=_Model(); inv=GovernedLocalModelInvoker(model=model, authority_map=_authority(), kernel=_Kernel(), runtime_root=tmp_path)
    coord=GenesisModelAdviceCoordinator(invoker=inv, runtime_root=tmp_path, review_evidence={'status':'approved','scope':'genesis'})
    need=GenesisNeed('vision_input','camera gap','telemetry')
    batch={'batch_id':'b1','batch_digest':'bd1','signals':[{'id':'s1','digest':'sd1'}]}
    p1=coord.advice_for_need(need, signal_batch=batch, tick_id='tick1')
    p2=coord.advice_for_need(need, signal_batch=batch, tick_id='tick1')
    assert p1.packet_id == p2.packet_id
    assert model.calls == 1
    assert p1.candidate_produced is True
    ok,reasons=validate_packet(p1.to_dict())
    assert ok, reasons
    tampered=p1.to_dict(); tampered['disposition']='valid_advice_tampered'
    ok,reasons=validate_packet(tampered)
    assert not ok and 'packet_digest_mismatch' in reasons

def test_forge_engine_counts_advice_candidate_inside_k(tmp_path: Path) -> None:
    model=_Model(); inv=GovernedLocalModelInvoker(model=model, authority_map=_authority(), kernel=_Kernel(), runtime_root=tmp_path)
    coord=GenesisModelAdviceCoordinator(invoker=inv, runtime_root=tmp_path, review_evidence={'status':'approved'})
    need=GenesisNeed('vision_input','camera gap','telemetry')
    packet=coord.advice_for_need(need, signal_batch={'batch_id':'b','batch_digest':'d'}, tick_id='t')
    proposals=ForgeEngine().draft_variants(need,k=2,seed='s',advice_packet=packet)
    assert len(proposals)==2
    assert sum(p.proposal_id.startswith('GF-ADVICE-') for p in proposals)==1
    assert sum(not p.proposal_id.startswith('GF-ADVICE-') for p in proposals)==1
    assert ForgeEngine().draft_variants(need,k=1,seed='s',advice_packet=packet)[0].proposal_id.startswith('GF-ADVICE-') is False
