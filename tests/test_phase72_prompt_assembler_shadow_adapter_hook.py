"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
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
    PromptAssemblyAdapterRef,
    PromptAssemblyAdapterStatus,
    build_prompt_assembly_adapter_payload,
    build_prompt_assembly_adapter_payload_from_packet,
)
from sentientos.context_hygiene.prompt_assembler_compliance import (
    PromptAssemblerComplianceStatus,
    evaluate_prompt_assembler_adapter_compliance,
    scan_prompt_assembler_static_findings,
)
from sentientos.context_hygiene.prompt_constraint_verifier import build_candidate_plan_from_dry_run_envelope, verify_prompt_assembly_constraints
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


def _preview(payload):
    return pa.preview_context_hygiene_adapter_payload_for_prompt_assembly(payload)


def _mutated(payload, **changes):
    data = asdict(payload) if not isinstance(payload, dict) else dict(payload)
    data.update(changes)
    if "adapter_refs" in data:
        data["adapter_refs"] = tuple(PromptAssemblyAdapterRef(**r) if isinstance(r, dict) else r for r in data["adapter_refs"])
    return data


def test_shadow_hook_maps_all_phase71_compliance_statuses_to_preview_statuses():
    ready, _, _ = _payload()
    ready_preview = _preview(ready)
    assert ready_preview.compliance_status == PromptAssemblerComplianceStatus.COMPLIANCE_READY_FOR_FUTURE_INTEGRATION
    assert ready_preview.rationale.startswith("shadow_preview_ready:")

    warned, _, _ = _payload(_caveated_envelope())
    warning_preview = _preview(warned)
    assert warning_preview.compliance_status == PromptAssemblerComplianceStatus.COMPLIANCE_READY_WITH_WARNINGS
    assert warning_preview.rationale.startswith("shadow_preview_ready_with_warnings:")

    blocked_preview = _preview(_blocked_payload())
    assert blocked_preview.compliance_status == PromptAssemblerComplianceStatus.COMPLIANCE_BLOCKED
    assert blocked_preview.rationale.startswith("shadow_preview_blocked:")

    not_applicable, _, _ = _payload(_not_applicable_envelope())
    not_applicable_preview = _preview(not_applicable)
    assert not_applicable.adapter_status == PromptAssemblyAdapterStatus.ADAPTER_NOT_APPLICABLE
    assert not_applicable_preview.compliance_status == PromptAssemblerComplianceStatus.COMPLIANCE_NOT_APPLICABLE
    assert not_applicable_preview.rationale.startswith("shadow_preview_not_applicable:")

    invalid_preview = _preview(_invalid_payload())
    assert invalid_preview.compliance_status == PromptAssemblerComplianceStatus.COMPLIANCE_INVALID_ADAPTER_PAYLOAD
    assert invalid_preview.rationale.startswith("shadow_preview_invalid_adapter_payload:")


def test_shadow_preview_shape_exposes_only_metadata_counts_notes_and_boundaries():
    payload, _, _ = _payload(_caveated_envelope())
    preview = _preview(payload)
    report = evaluate_prompt_assembler_adapter_compliance(payload, prompt_assembler_path=ROOT / "prompt_assembler.py")

    assert preview.adapter_payload_id == payload.adapter_payload_id
    assert preview.adapter_status == payload.adapter_status
    assert preview.compliance_status == report.compliance_status
    assert preview.may_future_assembler_consume is True
    assert preview.must_block_prompt_materialization is False
    assert preview.adapter_ref_count == len(payload.adapter_refs)
    assert preview.section_count == len(payload.adapter_sections)
    assert preview.preserved_caveats == payload.preserved_caveats
    assert preview.provenance_notes_present is True
    assert preview.privacy_notes_present is True
    assert preview.truth_notes_present is True
    assert preview.safety_notes_present is True
    assert preview.shadow_hook_only is True
    for marker in (
        "does_not_assemble_prompt",
        "does_not_contain_final_prompt_text",
        "does_not_call_llm",
        "does_not_retrieve_memory",
        "does_not_write_memory",
        "does_not_trigger_feedback",
        "does_not_commit_retention",
        "does_not_execute_or_route_work",
        "does_not_admit_work",
    ):
        assert getattr(preview, marker) is True


def test_shadow_preview_preserves_warnings_violations_as_metadata_only_and_contains_no_prompt_text_or_raw_payloads():
    ready, _, _ = _payload()
    blocked = _blocked_payload()
    forbidden = _mutated(ready, prompt_text="forbidden final prompt text", raw_payload={"secret": "payload"})
    preview = _preview(forbidden)
    blocked_preview = _preview(blocked)
    preview_data = asdict(preview)
    serialized = repr(preview_data)

    assert any(item["code"] == "prompt_text_present" for item in preview.violations)
    assert any(item["code"] == "raw_payload_present" for item in preview.violations)
    assert blocked_preview.must_block_prompt_materialization is True
    assert blocked_preview.adapter_ref_count == 0
    assert blocked_preview.section_count == 0
    assert "forbidden final prompt text" not in serialized
    assert "packet-safe summary" not in serialized
    assert "content_summary" not in serialized
    assert "adapter_refs" not in serialized
    assert "final_prompt_text" not in preview_data
    assert "prompt_text" not in preview_data
    assert "raw_payload" not in preview_data


def test_shadow_hook_has_no_runtime_authority_and_does_not_mutate_payload_or_live_prompt_paths(monkeypatch):
    payload, _, _ = _payload()
    before = deepcopy(asdict(payload))

    monkeypatch.setattr(pa, "assemble_prompt", lambda *args, **kwargs: pytest.fail("live prompt assembly called"))
    monkeypatch.setattr(pa.mm, "get_context", lambda *args, **kwargs: pytest.fail("memory retrieval called"))
    monkeypatch.setattr(pa.em, "average_emotion", lambda *args, **kwargs: pytest.fail("emotion runtime called"))
    monkeypatch.setattr(pa.cw, "get_context", lambda *args, **kwargs: pytest.fail("context window runtime called"))
    monkeypatch.setattr(pa.actuator, "recent_logs", lambda *args, **kwargs: pytest.fail("action feedback runtime called"))
    monkeypatch.setattr(pa.ac, "capture_affective_context", lambda *args, **kwargs: pytest.fail("feedback capture called"))
    monkeypatch.setattr(pa.ac, "register_context", lambda *args, **kwargs: pytest.fail("feedback register called"))

    preview = _preview(payload)
    assert asdict(payload) == before
    assert preview.does_not_call_llm is True
    assert preview.does_not_retrieve_memory is True
    assert preview.does_not_write_memory is True
    assert preview.does_not_execute_or_route_work is True
    assert preview.does_not_admit_work is True


def test_existing_prompt_assembler_behavior_is_representatively_unchanged(monkeypatch):
    monkeypatch.setattr(pa.up, "format_profile", lambda: "name: Allen")
    monkeypatch.setattr(pa.mm, "get_context", lambda _query, k=6: [{"plan": "alpha"}, {"plan": "beta"}])
    monkeypatch.setattr(pa.em, "average_emotion", lambda: {})
    monkeypatch.setattr(pa.cw, "get_context", lambda: (["msg-1"], "summary"))
    monkeypatch.setattr(pa.actuator, "recent_logs", lambda *args, **kwargs: [])
    monkeypatch.setattr(pa.ac, "capture_affective_context", lambda *args, **kwargs: {"captured": True})
    monkeypatch.setattr(pa.ac, "register_context", lambda *args, **kwargs: None)

    prompt = pa.assemble_prompt("reflect", ["hi"], k=2)
    assert "SYSTEM:" in prompt
    assert "USER PROFILE:\nname: Allen" in prompt
    assert "RELEVANT MEMORIES:\n- alpha\n- beta" in prompt
    assert "RECENT DIALOGUE:\nhi" in prompt
    assert "SUMMARY:\nsummary" in prompt
    assert "USER:\nreflect" in prompt
    assert "affect" not in prompt


def test_static_scan_detects_intentional_shadow_hook_without_live_runtime_wiring_or_bypass():
    findings = scan_prompt_assembler_static_findings(ROOT / "prompt_assembler.py")
    assert findings["context_hygiene_shadow_hook_only"] is True
    assert findings["imports_context_hygiene_adapter_modules"] is True
    assert findings["active_context_hygiene_runtime_wiring"] is False
    assert findings["forbidden_context_bypass_detected"] is False
    assert findings["non_shadow_context_hygiene_imports"] == ()


def test_phase63_to_phase72_shadow_hook_pipeline_works_for_sanitized_embodiment_proposal():
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
    preview = _preview(payload)
    assert payload.adapter_refs
    assert preview.compliance_status in {
        PromptAssemblerComplianceStatus.COMPLIANCE_READY_FOR_FUTURE_INTEGRATION,
        PromptAssemblerComplianceStatus.COMPLIANCE_READY_WITH_WARNINGS,
    }
    assert preview.adapter_ref_count == len(payload.adapter_refs)
    assert "sanitized posture summary" not in repr(asdict(preview))


def test_phase62b_blocked_attempted_candidate_shadow_hook_blocks_materialization():
    payload, _, _ = _payload(
        _envelope_for(
            [_cand("blocked", metadata={"source_kind": "evidence", "pollution_risk": "blocked", "non_authoritative": True, "decision_power": "none"})]
        )
    )
    preview = _preview(payload)
    assert payload.adapter_status in {PromptAssemblyAdapterStatus.ADAPTER_BLOCKED, PromptAssemblyAdapterStatus.ADAPTER_NOT_APPLICABLE}
    assert preview.may_future_assembler_consume is False
    assert preview.must_block_prompt_materialization is True
    assert preview.adapter_ref_count == 0
    assert preview.section_count == 0
