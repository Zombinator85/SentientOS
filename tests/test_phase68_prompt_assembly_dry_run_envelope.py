from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from sentientos.context_hygiene.context_packet import ContextMode
from sentientos.context_hygiene.prompt_dry_run_envelope import (
    ContextPromptDryRunStatus,
    build_context_prompt_dry_run_envelope,
    compute_context_prompt_dry_run_envelope_digest,
    dry_run_envelope_contains_no_prompt_text,
    dry_run_envelope_has_no_runtime_authority,
    map_handoff_status_to_prompt_dry_run_status,
    summarize_context_prompt_dry_run_envelope,
)
from sentientos.context_hygiene.prompt_handoff_manifest import (
    ContextPromptHandoffStatus,
    build_context_prompt_handoff_manifest,
)
from sentientos.context_hygiene.prompt_preflight import (
    PromptContextEligibility,
    PromptContextEligibilityStatus,
    evaluate_context_packet_prompt_eligibility,
)
from sentientos.context_hygiene.selector import ContextCandidate, build_context_packet_from_candidates

NOW = datetime.now(timezone.utc)


def _cand(ref_id="r", ref_type="evidence", metadata=None, truth_ingress_status="allowed"):
    return ContextCandidate(
        ref_id=ref_id,
        ref_type=ref_type,
        packet_scope="turn",
        conversation_scope_id="conv",
        task_scope_id="task",
        provenance_refs=("p1",),
        source_locator="src",
        summary="packet-safe summary",
        already_sanitized_context_summary=True,
        truth_ingress_status=truth_ingress_status,
        metadata=metadata or {},
    )


def _pkt(cands):
    return build_context_packet_from_candidates(
        cands,
        "turn",
        "conv",
        "task",
        context_mode=ContextMode.RESPONSE,
        now=NOW,
    )


def _handoff_for_metadata(metadata):
    return build_context_prompt_handoff_manifest(_pkt([_cand("r", metadata=metadata)]))


def test_phase68_status_mapping_is_exact_and_manifest_sourced():
    assert map_handoff_status_to_prompt_dry_run_status(ContextPromptHandoffStatus.HANDOFF_READY) == ContextPromptDryRunStatus.DRY_RUN_READY
    assert map_handoff_status_to_prompt_dry_run_status(ContextPromptHandoffStatus.HANDOFF_READY_WITH_CAVEATS) == ContextPromptDryRunStatus.DRY_RUN_READY_WITH_CAVEATS
    assert map_handoff_status_to_prompt_dry_run_status(ContextPromptHandoffStatus.HANDOFF_BLOCKED) == ContextPromptDryRunStatus.DRY_RUN_BLOCKED
    assert map_handoff_status_to_prompt_dry_run_status(ContextPromptHandoffStatus.HANDOFF_NOT_APPLICABLE) == ContextPromptDryRunStatus.DRY_RUN_NOT_APPLICABLE
    assert map_handoff_status_to_prompt_dry_run_status(ContextPromptHandoffStatus.HANDOFF_INVALID_PACKET) == ContextPromptDryRunStatus.DRY_RUN_INVALID_MANIFEST

    manifest = _handoff_for_metadata({"source_kind": "evidence", "privacy_posture": "public", "non_authoritative": True, "decision_power": "none"})
    envelope = build_context_prompt_dry_run_envelope(manifest)
    assert envelope.dry_run_status == ContextPromptDryRunStatus.DRY_RUN_READY
    assert envelope.manifest_id == manifest.manifest_id
    assert envelope.manifest_digest == manifest.digest
    assert envelope.packet_id == manifest.packet_id
    assert envelope.packet_scope == manifest.packet_scope
    assert envelope.assembly_constraints["source_artifact"] == "phase67_context_prompt_handoff_manifest"
    assert envelope.assembly_constraints["uses_handoff_manifest_only"] is True
    assert envelope.section_summaries
    assert envelope.admissible_ref_summaries


def test_phase68_ready_and_caveated_include_admissible_refs_only_from_manifest():
    ready_manifest = _handoff_for_metadata({"source_kind": "evidence", "privacy_posture": "public", "non_authoritative": True, "decision_power": "none"})
    ready = build_context_prompt_dry_run_envelope(ready_manifest)
    assert ready.dry_run_status == ContextPromptDryRunStatus.DRY_RUN_READY
    assert tuple(r.ref_id for r in ready.admissible_ref_summaries) == tuple(r.ref_id for r in ready_manifest.included_ref_summaries)
    assert ready.source_kind_summary == ready_manifest.source_kind_summary
    assert ready.provenance_summary == ready_manifest.provenance_summary

    caveated_manifest = _handoff_for_metadata({
        "source_kind": "embodiment_snapshot",
        "privacy_posture": "privacy_sensitive",
        "sanitized_context_summary": True,
        "allow_context_privacy_sensitive": True,
        "non_authoritative": True,
        "decision_power": "none",
    })
    caveated = build_context_prompt_dry_run_envelope(caveated_manifest)
    assert caveated.dry_run_status == ContextPromptDryRunStatus.DRY_RUN_READY_WITH_CAVEATS
    assert caveated.caveats == caveated_manifest.caveats
    assert caveated.admissible_ref_summaries


def test_phase68_blocked_not_applicable_and_invalid_withhold_admissible_refs_and_preserve_reasons():
    blocked_manifest = _handoff_for_metadata({"source_kind": "evidence", "pollution_risk": "blocked", "non_authoritative": True, "decision_power": "none"})
    blocked = build_context_prompt_dry_run_envelope(blocked_manifest)
    assert blocked.dry_run_status == ContextPromptDryRunStatus.DRY_RUN_BLOCKED
    assert blocked.admissible_ref_summaries == ()
    assert blocked.block_reasons == blocked_manifest.block_reasons
    assert blocked.safety_contract_gap_summary == blocked_manifest.safety_contract_gap_summary

    empty_manifest = build_context_prompt_handoff_manifest(_pkt([]))
    empty = build_context_prompt_dry_run_envelope(empty_manifest)
    assert empty.dry_run_status == ContextPromptDryRunStatus.DRY_RUN_NOT_APPLICABLE
    assert empty.admissible_ref_summaries == ()

    invalid_manifest = build_context_prompt_handoff_manifest(replace(_pkt([_cand("bad", metadata={"source_kind": "evidence", "non_authoritative": True, "decision_power": "none"})]), context_packet_id=""))
    invalid = build_context_prompt_dry_run_envelope(invalid_manifest)
    assert invalid.dry_run_status == ContextPromptDryRunStatus.DRY_RUN_INVALID_MANIFEST
    assert invalid.admissible_ref_summaries == ()
    assert invalid.block_reasons == invalid_manifest.block_reasons


def test_phase68_deterministic_digest_changes_with_manifest_digest_and_caveats():
    packet = _pkt([_cand("a", metadata={"source_kind": "evidence", "non_authoritative": True, "decision_power": "none"})])
    manifest = build_context_prompt_handoff_manifest(packet)
    envelope = build_context_prompt_dry_run_envelope(manifest)
    assert envelope.digest == compute_context_prompt_dry_run_envelope_digest(replace(envelope, digest=""))
    assert envelope.digest == build_context_prompt_dry_run_envelope(manifest).digest

    pre = evaluate_context_packet_prompt_eligibility(packet)
    caveated_pre = PromptContextEligibility(
        eligibility_status=PromptContextEligibilityStatus.PROMPT_ELIGIBLE_WITH_CAVEATS,
        prompt_eligible=True,
        may_be_prompted_only_with_caveats=True,
        caveats=("operator_review",),
        packet_id=packet.context_packet_id,
        included_ref_count=pre.included_ref_count,
    )
    caveated_manifest = build_context_prompt_handoff_manifest(packet, caveated_pre)
    assert build_context_prompt_dry_run_envelope(caveated_manifest).digest != envelope.digest


def test_phase68_no_runtime_markers_no_prompt_text_and_import_purity():
    manifest = _handoff_for_metadata({
        "source_kind": "evidence",
        "privacy_posture": "public",
        "non_authoritative": True,
        "decision_power": "none",
        "prompt_text": "must not pass through",
        "raw_payload": "must not pass through",
    })
    envelope = build_context_prompt_dry_run_envelope(manifest)
    markers = envelope.no_runtime_markers
    assert markers.does_not_assemble_prompt is True
    assert markers.does_not_contain_final_prompt_text is True
    assert markers.does_not_call_llm is True
    assert markers.does_not_retrieve_memory is True
    assert markers.does_not_write_memory is True
    assert markers.does_not_trigger_feedback is True
    assert markers.does_not_commit_retention is True
    assert markers.does_not_execute_or_route_work is True
    assert markers.does_not_admit_work is True
    assert dry_run_envelope_has_no_runtime_authority(envelope)
    assert dry_run_envelope_contains_no_prompt_text(envelope)
    assert summarize_context_prompt_dry_run_envelope(envelope)["manifest_digest"] == manifest.digest

    import sentientos.context_hygiene.prompt_dry_run_envelope as mod

    txt = open(mod.__file__, encoding="utf-8").read()
    for forbidden in ["prompt_assembler", "memory_manager", "task_executor", "task_admission", "openai", "requests"]:
        assert forbidden not in txt
