"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timezone
import sys
import types

import pytest

tts_stub = types.ModuleType("tts_bridge")
tts_stub.speak = lambda *args, **kwargs: None
sys.modules.setdefault("tts_bridge", tts_stub)

import prompt_assembler as pa
from sentientos.context_hygiene.context_packet import ContextMode
from sentientos.context_hygiene.embodiment_context import build_embodiment_context_candidates
from sentientos.context_hygiene.prompt_adapter_contract import (
    PromptAssemblyAdapterStatus,
    build_prompt_assembly_adapter_payload,
    compute_prompt_adapter_payload_digest,
)
from sentientos.context_hygiene.prompt_constraint_verifier import build_candidate_plan_from_dry_run_envelope, verify_prompt_assembly_constraints
from sentientos.context_hygiene.prompt_dry_run_envelope import build_context_prompt_dry_run_envelope
from sentientos.context_hygiene.prompt_handoff_manifest import build_context_prompt_handoff_manifest
from sentientos.context_hygiene.prompt_materialization_audit import (
    PromptMaterializationAuditStatus,
    audit_receipt_allows_shadow_materializer,
    audit_receipt_chain_is_complete,
    audit_receipt_contains_no_prompt_text,
    audit_receipt_contains_no_raw_payloads,
    audit_receipt_has_no_runtime_authority,
    build_prompt_materialization_audit_receipt,
    build_prompt_materialization_audit_receipt_from_adapter_payload,
    build_prompt_materialization_audit_receipt_from_packet,
    compute_prompt_materialization_audit_digest,
    explain_prompt_materialization_audit_findings,
    summarize_prompt_materialization_audit_receipt,
)
from sentientos.context_hygiene.prompt_preflight import PromptContextEligibility, PromptContextEligibilityStatus, evaluate_context_packet_prompt_eligibility
from sentientos.context_hygiene.selector import ContextCandidate, build_context_packet_from_candidates

NOW = datetime.now(timezone.utc)


def _cand(ref_id="r", ref_type="evidence", metadata=None, truth_ingress_status="allowed", contradiction_status="unknown"):
    return ContextCandidate(
        ref_id=ref_id,
        ref_type=ref_type,
        packet_scope="turn",
        conversation_scope_id="conv",
        task_scope_id="task",
        provenance_refs=("prov:1",),
        source_locator="src",
        summary="packet-safe summary",
        already_sanitized_context_summary=True,
        truth_ingress_status=truth_ingress_status,
        contradiction_status=contradiction_status,
        metadata=metadata or {"source_kind": "evidence", "privacy_posture": "public", "non_authoritative": True, "decision_power": "none"},
    )


def _pkt(cands):
    return build_context_packet_from_candidates(cands, "turn", "conv", "task", context_mode=ContextMode.RESPONSE, now=NOW)


def _envelope_for(cands):
    return build_context_prompt_dry_run_envelope(build_context_prompt_handoff_manifest(_pkt(cands)))


def _ready_envelope():
    return _envelope_for([_cand("ready")])


def _caveated_envelope():
    packet = _pkt([_cand("caveat")])
    pre = evaluate_context_packet_prompt_eligibility(packet)
    caveated = PromptContextEligibility(
        eligibility_status=PromptContextEligibilityStatus.PROMPT_ELIGIBLE_WITH_CAVEATS,
        prompt_eligible=True,
        may_be_prompted_only_with_caveats=True,
        caveats=("truth_caveat: operator review",),
        packet_id=packet.context_packet_id,
        included_ref_count=pre.included_ref_count,
    )
    return build_context_prompt_dry_run_envelope(build_context_prompt_handoff_manifest(packet, caveated))


def _not_applicable_envelope():
    return build_context_prompt_dry_run_envelope(build_context_prompt_handoff_manifest(_pkt([])))


def _payload(envelope=None, plan=None):
    envelope = envelope or _ready_envelope()
    plan = plan or build_candidate_plan_from_dry_run_envelope(envelope)
    verification = verify_prompt_assembly_constraints(envelope, plan)
    return build_prompt_assembly_adapter_payload(verification, plan), verification, plan


def _blocked_payload():
    envelope = _ready_envelope()
    bad_plan = replace(build_candidate_plan_from_dry_run_envelope(envelope), packet_id="wrong")
    return _payload(envelope, bad_plan)[0]


def _invalid_payload():
    envelope = _ready_envelope()
    malformed = {"plan_id": "bad", "candidate_refs": "not refs"}
    verification = verify_prompt_assembly_constraints(envelope, malformed)
    return build_prompt_assembly_adapter_payload(verification, malformed)


def _receipt(payload=None):
    payload = payload or _payload()[0]
    return build_prompt_materialization_audit_receipt_from_adapter_payload(payload)


def test_ready_blueprint_produces_audit_ready_and_allows_shadow_materializer():
    payload, verification, _ = _payload()
    blueprint = pa.build_context_hygiene_shadow_prompt_blueprint(payload)
    preview = pa.preview_context_hygiene_adapter_payload_for_prompt_assembly(payload)
    receipt = build_prompt_materialization_audit_receipt(blueprint, preview=preview, adapter_payload=payload, verification=verification)
    assert receipt.audit_status == PromptMaterializationAuditStatus.AUDIT_READY_FOR_SHADOW_MATERIALIZATION
    assert audit_receipt_allows_shadow_materializer(receipt)
    assert receipt.blueprint_id == blueprint.blueprint_id
    assert receipt.blueprint_digest == blueprint.digest


def test_ready_with_warnings_maps_and_preserves_warning_and_caveat():
    receipt = _receipt(_payload(_caveated_envelope())[0])
    assert receipt.audit_status == PromptMaterializationAuditStatus.AUDIT_READY_WITH_WARNINGS
    assert audit_receipt_allows_shadow_materializer(receipt)
    assert receipt.preserved_caveats == ("truth_caveat: operator review",)
    assert receipt.warnings
    assert any(f.code == "warning_requires_review" for f in receipt.findings)
    assert any(f.code == "caveat_requires_review" for f in receipt.findings)


def test_blocked_not_applicable_invalid_and_runtime_wiring_do_not_allow_shadow_materializer():
    blocked = _receipt(_blocked_payload())
    assert blocked.audit_status == PromptMaterializationAuditStatus.AUDIT_BLOCKED
    assert not audit_receipt_allows_shadow_materializer(blocked)
    assert any(f.code == "blocked_blueprint" for f in blocked.findings)

    not_applicable = _receipt(_payload(_not_applicable_envelope())[0])
    assert not_applicable.audit_status == PromptMaterializationAuditStatus.AUDIT_NOT_APPLICABLE
    assert not audit_receipt_allows_shadow_materializer(not_applicable)

    invalid_data = asdict(_payload()[0])
    invalid_data.update({"adapter_status": PromptAssemblyAdapterStatus.ADAPTER_INVALID_CANDIDATE_PLAN, "adapter_refs": (), "violations": ({"code": "invalid_candidate_plan", "detail": "synthetic invalid payload"},)})
    invalid_data["digest"] = compute_prompt_adapter_payload_digest(invalid_data)
    invalid = _receipt(invalid_data)
    assert invalid.audit_status == PromptMaterializationAuditStatus.AUDIT_INVALID_BLUEPRINT
    assert not audit_receipt_allows_shadow_materializer(invalid)

    ready_payload = _payload()[0]
    runtime_blueprint = replace(pa.build_context_hygiene_shadow_prompt_blueprint(ready_payload), blueprint_status="shadow_blueprint_runtime_wiring_detected", may_future_assembler_consume=False, must_block_prompt_materialization=True)
    runtime_receipt = build_prompt_materialization_audit_receipt(runtime_blueprint, adapter_payload=ready_payload)
    assert runtime_receipt.audit_status == PromptMaterializationAuditStatus.AUDIT_RUNTIME_WIRING_DETECTED
    assert not audit_receipt_allows_shadow_materializer(runtime_receipt)


def test_receipt_includes_identity_status_packet_scope_chain_boundaries_and_summaries():
    payload, verification, _ = _payload()
    receipt = _receipt(payload)
    assert receipt.adapter_payload_id == payload.adapter_payload_id
    assert receipt.adapter_status == payload.adapter_status
    assert receipt.compliance_status == "compliance_ready_for_future_integration"
    assert receipt.preview_status == "shadow_preview_ready"
    assert receipt.blueprint_status == "shadow_blueprint_ready"
    assert receipt.packet_id == payload.packet_id
    assert receipt.packet_scope == payload.packet_scope
    assert receipt.manifest_id
    assert receipt.manifest_digest
    assert receipt.envelope_id == payload.envelope_id
    assert receipt.envelope_digest == payload.envelope_digest
    assert receipt.candidate_plan_id == payload.candidate_plan_id
    assert receipt.adapter_payload_digest == payload.digest
    assert receipt.shadow_blueprint_digest == receipt.blueprint_digest
    assert receipt.digest_chain.adapter_payload_digest == payload.digest
    assert receipt.digest_chain_complete is True
    assert audit_receipt_chain_is_complete(receipt)
    assert receipt.boundary_summary["does_not_materialize_prompt_text"] is True
    assert receipt.provenance_summary
    assert receipt.privacy_summary
    assert receipt.truth_summary
    assert receipt.safety_summary
    assert receipt.source_kind_summary == {"evidence": 1}
    assert receipt.ref_counts["blueprint_ref_count"] == 1
    assert receipt.section_counts["blueprint_section_count"] >= 1
    summary = summarize_prompt_materialization_audit_receipt(receipt)
    assert summary.allows_shadow_materializer is True
    assert summary.receipt_digest == receipt.receipt_digest


def test_digest_chain_completeness_and_invalid_chain_findings_are_deterministic():
    payload = _payload()[0]
    blueprint = pa.build_context_hygiene_shadow_prompt_blueprint(payload)
    invalid = replace(blueprint, digest="")
    r1 = build_prompt_materialization_audit_receipt(invalid, adapter_payload=payload)
    r2 = build_prompt_materialization_audit_receipt(invalid, adapter_payload=payload)
    assert r1.audit_status == PromptMaterializationAuditStatus.AUDIT_INVALID_CHAIN
    assert r1.digest_chain_complete is False
    assert "missing_blueprint_digest" in {f.code for f in r1.findings}
    assert "digest_chain_incomplete" in {f.code for f in r1.findings}
    assert r1.receipt_digest == r2.receipt_digest
    assert explain_prompt_materialization_audit_findings(r1)


def test_receipt_digest_is_deterministic_and_changes_with_bound_inputs():
    payload = _payload()[0]
    receipt1 = _receipt(payload)
    receipt2 = _receipt(payload)
    assert receipt1.receipt_digest == receipt2.receipt_digest
    assert compute_prompt_materialization_audit_digest(receipt1) == receipt1.receipt_digest

    blueprint = pa.build_context_hygiene_shadow_prompt_blueprint(payload)
    changed_blueprint = replace(blueprint, digest="changed")
    changed_digest_receipt = build_prompt_materialization_audit_receipt(changed_blueprint, adapter_payload=payload)
    assert changed_digest_receipt.receipt_digest != receipt1.receipt_digest

    warned_payload = _payload(_caveated_envelope())[0]
    assert _receipt(warned_payload).receipt_digest != receipt1.receipt_digest

    caveat_blueprint = replace(blueprint, preserved_caveats=("new caveat",))
    caveat_receipt = build_prompt_materialization_audit_receipt(caveat_blueprint, adapter_payload=payload)
    assert caveat_receipt.receipt_digest != receipt1.receipt_digest


def test_receipt_contains_no_prompt_text_raw_payload_or_runtime_authority():
    receipt = _receipt()
    assert audit_receipt_contains_no_prompt_text(receipt)
    assert audit_receipt_contains_no_raw_payloads(receipt)
    assert audit_receipt_has_no_runtime_authority(receipt)
    assert receipt.audit_receipt_only is True
    assert receipt.attestation_only is True
    assert receipt.does_not_call_llm is True
    assert receipt.does_not_retrieve_memory is True
    assert receipt.does_not_write_memory is True


def test_helpers_do_not_mutate_blueprint_or_adapter_payload_and_do_not_call_live_assemble(monkeypatch):
    payload = _payload()[0]
    payload_before = deepcopy(asdict(payload))
    blueprint = pa.build_context_hygiene_shadow_prompt_blueprint(payload)
    blueprint_before = deepcopy(asdict(blueprint))

    def forbidden(*args, **kwargs):
        raise AssertionError("assemble_prompt must not be called")

    monkeypatch.setattr(pa, "assemble_prompt", forbidden)
    receipt = build_prompt_materialization_audit_receipt(blueprint, adapter_payload=payload)
    assert receipt.audit_status == PromptMaterializationAuditStatus.AUDIT_READY_FOR_SHADOW_MATERIALIZATION
    assert asdict(payload) == payload_before
    assert asdict(blueprint) == blueprint_before


def test_helper_does_not_call_llm_retrieval_memory_action_retention_runtime_functions(monkeypatch):
    def forbidden_import(name, *args, **kwargs):
        if name in {"openai", "anthropic", "memory_manager", "task_executor", "task_admission"}:
            raise AssertionError(f"forbidden runtime import {name}")
        return real_import(name, *args, **kwargs)

    real_import = __import__
    monkeypatch.setattr("builtins.__import__", forbidden_import)
    receipt = _receipt(_payload()[0])
    assert receipt.audit_status == PromptMaterializationAuditStatus.AUDIT_READY_FOR_SHADOW_MATERIALIZATION


def test_phase63_embodiment_to_phase74_pipeline_works():
    artifacts = [
        {
            "ref_id": "emb:1",
            "source_kind": "embodiment_snapshot",
            "packet_scope": "turn",
            "conversation_scope_id": "conv",
            "task_scope_id": "task",
            "content_summary": "sanitized posture summary",
            "provenance_refs": ("sensor:sanitized",),
            "sanitized_context_summary": True,
            "proposal_status": "reviewable",
            "privacy_posture": "public",
            "non_authoritative": True,
            "decision_power": "none",
        }
    ]
    candidates = build_embodiment_context_candidates(artifacts)
    packet = _pkt(candidates)
    receipt = build_prompt_materialization_audit_receipt_from_packet(packet)
    assert receipt.audit_status == PromptMaterializationAuditStatus.AUDIT_READY_FOR_SHADOW_MATERIALIZATION
    assert audit_receipt_allows_shadow_materializer(receipt)
    assert receipt.source_kind_summary


def test_phase62b_blocked_attempted_candidate_blocks_audit_materialization():
    packet = _pkt([
        _cand("safe"),
        _cand("blocked", metadata={"source_kind": "evidence", "pollution_risk": "blocked", "privacy_posture": "public", "non_authoritative": True, "decision_power": "none"}),
    ])
    receipt = build_prompt_materialization_audit_receipt_from_packet(packet)
    assert receipt.audit_status in {
        PromptMaterializationAuditStatus.AUDIT_BLOCKED,
        PromptMaterializationAuditStatus.AUDIT_NOT_APPLICABLE,
    }
    assert not audit_receipt_allows_shadow_materializer(receipt)


def test_import_exports_remain_available():
    from sentientos.context_hygiene import PromptMaterializationAuditReceipt, build_prompt_materialization_audit_receipt_from_packet

    assert PromptMaterializationAuditReceipt.__name__ == "PromptMaterializationAuditReceipt"
    assert build_prompt_materialization_audit_receipt_from_packet is not None
