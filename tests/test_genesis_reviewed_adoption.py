from __future__ import annotations
import pytest
pytestmark = pytest.mark.no_legacy_skip
import json
from pathlib import Path
from codex.integrity_daemon import IntegrityDaemon
from sentientos.codex_healer import Anomaly, RecoveryLedger
from sentientos.control_plane_kernel import AdmissionOutcome, ControlActionDecision, LifecyclePhase
from sentientos.genesis_forge import CovenantVow, ForgeEngine, GenesisForge, NeedSeer, SpecBinder, AdoptionRite, TelemetryStream, TrialRun
from sentientos.genesis_reviewed_adoption import *
from sentientos.world_state_board import WorldStateBoardBuilder, validate_snapshot
from sentientos.codex_startup_guard import codex_runtime_mediation

class Kernel:
    def __init__(self, outcome='allow'): self.outcome=outcome; self.calls=[]
    def admit(self, request):
        self.calls.append(request)
        return ControlActionDecision(AdmissionOutcome(self.outcome), ('admitted' if self.outcome=='allow' else self.outcome,), LifecyclePhase.MAINTENANCE, request.requested_phase, request.authority_class, request.action_kind, request.actor, request.target_subsystem, {}, request.metadata['correlation_id'])

def evaluation(tmp_path: Path):
    with codex_runtime_mediation('IntegrityDaemon'):
        integrity=IntegrityDaemon(tmp_path)
    with codex_runtime_mediation('GenesisForge'):
        forge=GenesisForge(need_seer=NeedSeer(), forge_engine=ForgeEngine(), integrity_daemon=integrity, trial_run=TrialRun(), spec_binder=SpecBinder(lineage_root=tmp_path/'lin', covenant_root=tmp_path/'cov'), adoption_rite=AdoptionRite(live_mount=tmp_path/'live0', codex_index=tmp_path/'idx0.json', review_board=lambda *_: True), ledger=RecoveryLedger(tmp_path/'ledger.jsonl'))
    need=NeedSeer().scan([TelemetryStream('vision','vision_input','camera',frozenset())],[CovenantVow('vision_input','camera')])[0]
    from codex.proof_budget_governor import BudgetDecision
    return forge._evaluate_candidate_pipeline(need, anomaly=Anomaly('genesis_need','vision_input'), configured_k=3, configured_m=2, router_k=3, router_m=2, allow_escalation=True, governor_decision=BudgetDecision(3,2,True,'normal',['ok']), risk_budget=object())

def packet(tmp_path: Path):
    return build_review_packet(evaluation(tmp_path), signal_batch={'batch_id':'batch-1','batch_digest':'sig-digest'})

def test_packet_decision_plan_receipt_and_world_state(tmp_path: Path):
    pkt=packet(tmp_path); assert validate_review_packet(pkt).valid
    dec=decide(pkt, disposition='approve', reviewer='operator-1', reviewer_role='keeper', reason_codes=['reviewed'])
    assert validate_decision(dec, pkt).valid
    plan=build_plan(pkt, dec, runtime_root=tmp_path/'state')
    k=Kernel('allow')
    receipt=GenesisReviewedAdoptionCoordinator(tmp_path/'state', kernel_provider=lambda: k).execute(pkt, dec, plan, apply=True)
    assert isinstance(receipt, GenesisReviewedAdoptionReceipt)
    assert receipt.status=='adopted'
    assert receipt.model_invocation is False and receipt.reevaluation is False and receipt.redrafting is False
    assert len(k.calls)==2
    receipt2=GenesisReviewedAdoptionCoordinator(tmp_path/'state', kernel_provider=lambda: k).execute(pkt, dec, plan, apply=True)
    assert isinstance(receipt2, GenesisReviewedAdoptionReceipt)
    assert receipt2.receipt_digest==receipt.receipt_digest
    snap=WorldStateBoardBuilder().build(world_state_records_for(pkt, dec, plan, receipt))
    assert validate_snapshot(snap).valid
    assert snap.summary.adoptions == 1

def test_tamper_and_decision_boundaries(tmp_path: Path):
    pkt=packet(tmp_path); data=pkt.to_dict(); data['candidate']['objective']='tampered'
    assert not validate_review_packet(data).valid
    rej=decide(pkt, disposition='reject', reviewer='operator-1', reviewer_role='keeper', reason_codes=['no'])
    try: build_plan(pkt, rej, runtime_root=tmp_path)
    except GenesisReviewedAdoptionValidationError as e: assert 'decision_reject' in str(e)
    else: raise AssertionError('reject planned')
    changed=decide(pkt, disposition='approve', reviewer='operator-2', reviewer_role='keeper', reason_codes=['reviewed'], note='different')
    assert changed.decision_digest != decide(pkt, disposition='approve', reviewer='operator-1', reviewer_role='keeper', reason_codes=['reviewed']).decision_digest

def test_denied_admission_zero_writes_and_raw_expand_bypass_closed(tmp_path: Path):
    pkt=packet(tmp_path); dec=decide(pkt, disposition='approve', reviewer='operator-1', reviewer_role='keeper', reason_codes=['reviewed']); plan=build_plan(pkt, dec, runtime_root=tmp_path/'state')
    res=GenesisReviewedAdoptionCoordinator(tmp_path/'state', kernel_provider=lambda: Kernel('deny')).execute(pkt, dec, plan, apply=True)
    assert isinstance(res, GenesisReviewedAdoptionReceipt) and res.status=='denied'
    assert not (tmp_path/'state'/'integration').exists()
    with codex_runtime_mediation('IntegrityDaemon'):
        integrity2=IntegrityDaemon(tmp_path/'f')
    with codex_runtime_mediation('GenesisForge'):
        forge=GenesisForge(need_seer=NeedSeer(), forge_engine=ForgeEngine(), integrity_daemon=integrity2, trial_run=TrialRun(), spec_binder=SpecBinder(lineage_root=tmp_path/'l', covenant_root=tmp_path/'c'), adoption_rite=AdoptionRite(live_mount=tmp_path/'live', codex_index=tmp_path/'idx.json', review_board=lambda *_: True), ledger=RecoveryLedger(tmp_path/'log.jsonl'))
    out=forge.expand([TelemetryStream('vision','vision_input','camera',frozenset())],[CovenantVow('vision_input','camera')])
    assert out[0].status=='reviewed_adoption_required'
    assert not list((tmp_path/'live').glob('*.json'))
