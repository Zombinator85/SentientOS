from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

from sentientos.context_hygiene.context_packet import ContextMode
from sentientos.context_hygiene.embodiment_context import build_embodiment_context_candidates
from sentientos.context_hygiene.prompt_adapter_contract import (
    PromptAssemblyAdapterStatus,
    adapter_payload_contains_no_prompt_text,
    adapter_payload_contains_no_raw_payloads,
    adapter_payload_has_no_runtime_authority,
    adapter_payload_is_safe_for_future_prompt_assembler,
    build_prompt_assembly_adapter_payload,
    build_prompt_assembly_adapter_payload_from_envelope,
    build_prompt_assembly_adapter_payload_from_packet,
    compute_prompt_adapter_payload_digest,
    explain_prompt_adapter_block,
    map_prompt_verification_status_to_adapter_status,
    summarize_prompt_adapter_payload,
    summarize_verified_candidate_plan_for_adapter,
)
from sentientos.context_hygiene.prompt_constraint_verifier import (
    PromptAssemblyCandidateRef,
    PromptAssemblyConstraintVerificationStatus,
    build_candidate_plan_from_dry_run_envelope,
    verify_prompt_assembly_constraints,
)
from sentientos.context_hygiene.prompt_dry_run_envelope import build_context_prompt_dry_run_envelope
from sentientos.context_hygiene.prompt_handoff_manifest import build_context_prompt_handoff_manifest
from sentientos.context_hygiene.prompt_preflight import PromptContextEligibility, PromptContextEligibilityStatus, evaluate_context_packet_prompt_eligibility
from sentientos.context_hygiene.selector import ContextCandidate, build_context_packet_from_candidates

NOW = datetime.now(timezone.utc)
ROOT = Path(__file__).resolve().parents[1]


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


def _blocked_envelope():
    return _envelope_for([_cand("blocked", metadata={"source_kind": "evidence", "pollution_risk": "blocked", "non_authoritative": True, "decision_power": "none"})])


def _not_applicable_envelope():
    return build_context_prompt_dry_run_envelope(build_context_prompt_handoff_manifest(_pkt([])))


def _invalid_envelope():
    packet = replace(_pkt([_cand("bad")]), context_packet_id="")
    return build_context_prompt_dry_run_envelope(build_context_prompt_handoff_manifest(packet))


def _payload(envelope=None, plan=None):
    envelope = envelope or _ready_envelope()
    plan = plan or build_candidate_plan_from_dry_run_envelope(envelope)
    verification = verify_prompt_assembly_constraints(envelope, plan)
    return build_prompt_assembly_adapter_payload(verification, plan), verification, plan


def test_verified_candidate_plan_produces_adapter_ready_and_identity_fields():
    envelope = _ready_envelope()
    payload, verification, plan = _payload(envelope)
    assert verification.status == PromptAssemblyConstraintVerificationStatus.CONSTRAINT_VERIFIED
    assert payload.adapter_status == PromptAssemblyAdapterStatus.ADAPTER_READY
    assert payload.verified is True
    assert payload.candidate_plan_id == plan.plan_id
    assert payload.envelope_id == envelope.envelope_id
    assert payload.envelope_digest == envelope.digest
    assert payload.packet_id == envelope.packet_id
    assert payload.packet_scope == envelope.packet_scope
    assert summarize_verified_candidate_plan_for_adapter(verification, plan)["adapter_ref_count"] == 1


def test_verified_with_warnings_maps_to_adapter_ready_with_warnings_and_preserves_warnings():
    payload, verification, _ = _payload(_caveated_envelope())
    assert verification.status == PromptAssemblyConstraintVerificationStatus.CONSTRAINT_VERIFIED_WITH_WARNINGS
    assert payload.adapter_status == PromptAssemblyAdapterStatus.ADAPTER_READY_WITH_WARNINGS
    assert payload.warnings
    assert payload.warnings[0]["code"] == "caveated_dry_run_envelope"


def test_constraint_failed_maps_to_blocked_preserves_violations_and_withholds_refs():
    envelope = _ready_envelope()
    plan = replace(build_candidate_plan_from_dry_run_envelope(envelope), packet_id="wrong")
    payload, verification, _ = _payload(envelope, plan)
    assert verification.status == PromptAssemblyConstraintVerificationStatus.CONSTRAINT_FAILED
    assert payload.adapter_status == PromptAssemblyAdapterStatus.ADAPTER_BLOCKED
    assert payload.adapter_refs == ()
    assert payload.violations[0]["code"] == "packet_identity_mismatch"
    assert explain_prompt_adapter_block(payload)


def test_not_applicable_invalid_envelope_and_invalid_candidate_plan_withhold_refs():
    cases = [
        (_not_applicable_envelope(), PromptAssemblyAdapterStatus.ADAPTER_NOT_APPLICABLE, PromptAssemblyConstraintVerificationStatus.CONSTRAINT_NOT_APPLICABLE),
        (_invalid_envelope(), PromptAssemblyAdapterStatus.ADAPTER_INVALID_VERIFICATION, PromptAssemblyConstraintVerificationStatus.CONSTRAINT_INVALID_ENVELOPE),
    ]
    for envelope, adapter_status, verifier_status in cases:
        payload, verification, _ = _payload(envelope)
        assert verification.status == verifier_status
        assert payload.adapter_status == adapter_status
        assert payload.adapter_refs == ()

    envelope = _ready_envelope()
    malformed = {"plan_id": "bad", "candidate_refs": "not refs"}
    verification = verify_prompt_assembly_constraints(envelope, malformed)
    payload = build_prompt_assembly_adapter_payload(verification, malformed)
    assert payload.adapter_status == PromptAssemblyAdapterStatus.ADAPTER_INVALID_CANDIDATE_PLAN
    assert payload.adapter_refs == ()
    assert payload.violations[0]["code"] == "invalid_candidate_plan"


def test_blocked_envelope_is_not_applicable_safe_and_has_no_refs():
    payload, verification, plan = _payload(_blocked_envelope())
    assert plan.candidate_refs == ()
    assert verification.status == PromptAssemblyConstraintVerificationStatus.CONSTRAINT_NOT_APPLICABLE
    assert payload.adapter_status == PromptAssemblyAdapterStatus.ADAPTER_NOT_APPLICABLE
    assert payload.adapter_refs == ()


def test_payload_includes_constraints_sections_refs_caveats_and_notes_when_allowed():
    envelope = _caveated_envelope()
    payload, _, plan = _payload(envelope)
    assert payload.assembly_constraints == plan.preserved_constraints
    assert payload.adapter_sections
    assert {s.section_kind for s in payload.adapter_sections} >= {
        "adapter_context_refs",
        "adapter_caveat_requirements",
        "adapter_provenance_boundaries",
        "adapter_privacy_boundaries",
        "adapter_truth_boundaries",
        "adapter_safety_boundaries",
        "adapter_constraint_summary",
    }
    assert payload.adapter_refs
    assert payload.preserved_caveats == plan.preserved_caveats
    assert payload.provenance_notes == plan.provenance_notes
    assert payload.privacy_notes == plan.privacy_notes
    assert payload.truth_notes == plan.truth_notes
    assert payload.safety_notes == plan.safety_notes


def test_payload_contains_no_final_prompt_text_raw_payloads_or_runtime_authority():
    payload, _, _ = _payload()
    assert payload.adapter_contract_only is True
    assert payload.does_not_assemble_prompt is True
    assert payload.does_not_contain_final_prompt_text is True
    assert payload.does_not_call_llm is True
    assert payload.does_not_retrieve_memory is True
    assert payload.does_not_write_memory is True
    assert payload.does_not_trigger_feedback is True
    assert payload.does_not_commit_retention is True
    assert payload.does_not_execute_or_route_work is True
    assert payload.does_not_admit_work is True
    assert adapter_payload_contains_no_prompt_text(payload)
    assert adapter_payload_contains_no_raw_payloads(payload)
    assert adapter_payload_has_no_runtime_authority(payload)
    assert adapter_payload_is_safe_for_future_prompt_assembler(payload)


def test_digest_is_deterministic_and_changes_with_refs_status_and_warnings_or_violations():
    envelope = _ready_envelope()
    payload, verification, plan = _payload(envelope)
    assert payload.digest == compute_prompt_adapter_payload_digest(replace(payload, digest=""))
    assert payload.digest == _payload(envelope)[0].digest

    changed_ref = replace(plan.candidate_refs[0], content_summary="different adapter-safe summary")
    changed_plan = replace(plan, candidate_refs=(changed_ref,))
    changed_verification = verify_prompt_assembly_constraints(envelope, changed_plan)
    assert build_prompt_assembly_adapter_payload(changed_verification, changed_plan).digest != payload.digest

    failed_payload, _, _ = _payload(envelope, replace(plan, packet_id="wrong"))
    assert failed_payload.digest != payload.digest

    caveated_payload, _, _ = _payload(_caveated_envelope())
    assert caveated_payload.digest != payload.digest


def test_build_from_envelope_and_packet_paths_work():
    envelope = _ready_envelope()
    from_envelope = build_prompt_assembly_adapter_payload_from_envelope(envelope)
    assert from_envelope.adapter_status == PromptAssemblyAdapterStatus.ADAPTER_READY

    packet = _pkt([_cand("packet-path")])
    from_packet = build_prompt_assembly_adapter_payload_from_packet(packet)
    assert from_packet.packet_id == packet.context_packet_id
    assert from_packet.adapter_status == PromptAssemblyAdapterStatus.ADAPTER_READY


def test_phase63_to_phase70_pipeline_works_for_sanitized_embodiment_proposal():
    proposals = build_embodiment_context_candidates(
        [
            {
                "ref_id": "emb:1",
                "source_kind": "embodiment_snapshot",
                "packet_scope": "turn",
                "conversation_scope_id": "conv",
                "task_scope_id": "task",
                "content_summary": "sanitized posture summary",
                "sanitized_context_summary": True,
                "privacy_posture": "low_risk",
                "provenance_refs": ("sensor:summary",),
                "non_authoritative": True,
                "decision_power": "none",
            }
        ]
    )
    packet = build_context_packet_from_candidates(proposals, "turn", "conv", "task", context_mode=ContextMode.RESPONSE, now=NOW)
    payload = build_prompt_assembly_adapter_payload_from_packet(packet)
    assert payload.adapter_status in {PromptAssemblyAdapterStatus.ADAPTER_READY, PromptAssemblyAdapterStatus.ADAPTER_READY_WITH_WARNINGS}
    assert payload.adapter_refs
    assert payload.adapter_refs[0].source_kind == "embodiment_snapshot"


def test_helpers_do_not_mutate_verification_or_candidate_plan():
    envelope = _ready_envelope()
    plan = build_candidate_plan_from_dry_run_envelope(envelope)
    verification = verify_prompt_assembly_constraints(envelope, plan)
    before_plan = deepcopy(asdict(plan))
    before_verification = deepcopy(asdict(verification))
    build_prompt_assembly_adapter_payload(verification, plan)
    assert asdict(plan) == before_plan
    assert asdict(verification) == before_verification


def test_status_mapping_and_summary_are_compact():
    assert map_prompt_verification_status_to_adapter_status(PromptAssemblyConstraintVerificationStatus.CONSTRAINT_VERIFIED) == PromptAssemblyAdapterStatus.ADAPTER_READY
    assert map_prompt_verification_status_to_adapter_status(PromptAssemblyConstraintVerificationStatus.CONSTRAINT_VERIFIED_WITH_WARNINGS) == PromptAssemblyAdapterStatus.ADAPTER_READY_WITH_WARNINGS
    assert map_prompt_verification_status_to_adapter_status(PromptAssemblyConstraintVerificationStatus.CONSTRAINT_FAILED) == PromptAssemblyAdapterStatus.ADAPTER_BLOCKED
    payload, _, _ = _payload()
    summary = summarize_prompt_adapter_payload(payload)
    assert summary["adapter_status"] == PromptAssemblyAdapterStatus.ADAPTER_READY
    assert summary["adapter_ref_count"] == 1


def test_adapter_module_imports_remain_pure():
    path = ROOT / "sentientos/context_hygiene/prompt_adapter_contract.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    forbidden = (
        "prompt_assembler",
        "memory_manager",
        "task_admission",
        "task_executor",
        "retention",
        "openai",
        "requests",
        "hardware",
        "webbrowser",
    )
    for imp in imports:
        assert not any(token in imp for token in forbidden), imp
