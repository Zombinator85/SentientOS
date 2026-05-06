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


def _blueprint(payload):
    return pa.build_context_hygiene_shadow_prompt_blueprint(payload)


def _mutated(payload, **changes):
    data = asdict(payload) if not isinstance(payload, dict) else dict(payload)
    data.update(changes)
    if "adapter_refs" in data:
        data["adapter_refs"] = tuple(PromptAssemblyAdapterRef(**r) if isinstance(r, dict) else r for r in data["adapter_refs"])
    return data


def test_shadow_blueprint_maps_ready_warning_blocked_not_applicable_and_invalid_statuses():
    ready = _blueprint(_payload()[0])
    assert ready.blueprint_status == "shadow_blueprint_ready"
    assert ready.preview_status == "shadow_preview_ready"
    assert ready.compliance_status == PromptAssemblerComplianceStatus.COMPLIANCE_READY_FOR_FUTURE_INTEGRATION

    warned = _blueprint(_payload(_caveated_envelope())[0])
    assert warned.blueprint_status == "shadow_blueprint_ready_with_warnings"
    assert warned.preview_status == "shadow_preview_ready_with_warnings"

    blocked = _blueprint(_blocked_payload())
    assert blocked.blueprint_status == "shadow_blueprint_blocked"
    assert blocked.blueprint_refs == ()
    assert blocked.blueprint_ref_count == 0

    not_applicable = _blueprint(_payload(_not_applicable_envelope())[0])
    assert not_applicable.adapter_status == PromptAssemblyAdapterStatus.ADAPTER_NOT_APPLICABLE
    assert not_applicable.blueprint_status == "shadow_blueprint_not_applicable"
    assert not_applicable.blueprint_refs == ()

    invalid = _blueprint(_invalid_payload())
    assert invalid.blueprint_status == "shadow_blueprint_invalid_adapter_payload"
    assert invalid.blueprint_refs == ()


def test_shadow_blueprint_output_shape_preserves_metadata_without_prompt_materialization():
    payload, _, _ = _payload(_caveated_envelope())
    blueprint = _blueprint(payload)
    data = asdict(blueprint)
    serialized = repr(data)

    assert blueprint.blueprint_id.startswith(f"shadow-blueprint:{payload.adapter_payload_id}:")
    assert blueprint.adapter_payload_id == payload.adapter_payload_id
    assert blueprint.adapter_status == payload.adapter_status
    assert blueprint.preview_status == "shadow_preview_ready_with_warnings"
    assert blueprint.may_future_assembler_consume is True
    assert blueprint.must_block_prompt_materialization is False
    assert blueprint.adapter_ref_count == len(payload.adapter_refs)
    assert blueprint.blueprint_ref_count == len(payload.adapter_refs)
    assert blueprint.section_count == len(payload.adapter_sections)
    assert blueprint.blueprint_sections
    assert blueprint.blueprint_refs
    assert blueprint.preserved_caveats == payload.preserved_caveats
    assert blueprint.warnings
    assert blueprint.assembly_constraints == payload.assembly_constraints
    assert blueprint.provenance_notes_present is True
    assert blueprint.privacy_notes_present is True
    assert blueprint.truth_notes_present is True
    assert blueprint.safety_notes_present is True
    assert blueprint.shadow_blueprint_only is True
    assert blueprint.boundary.shadow_blueprint_only is True
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
        assert getattr(blueprint, marker) is True
        assert getattr(blueprint.boundary, marker) is True

    assert "packet-safe summary" not in serialized
    assert "content_summary" not in serialized
    assert "final_prompt_text" not in data
    assert "prompt_text" not in data
    assert "raw_payload" not in data
    assert "llm_params" not in serialized
    assert "retrieval_handle" not in serialized
    assert "action_handle" not in serialized
    assert "retention_handle" not in serialized


def test_shadow_blueprint_section_and_ref_summaries_are_adapter_derived_metadata_only():
    payload, _, _ = _payload(_caveated_envelope())
    blueprint = _blueprint(payload)
    section_kinds = {section.section_kind for section in blueprint.blueprint_sections}
    assert section_kinds == {
        "blueprint_context_refs",
        "blueprint_diagnostic_refs",
        "blueprint_evidence_refs",
        "blueprint_embodiment_refs",
        "blueprint_caveat_requirements",
        "blueprint_provenance_boundaries",
        "blueprint_privacy_boundaries",
        "blueprint_truth_boundaries",
        "blueprint_safety_boundaries",
        "blueprint_constraint_summary",
    }
    assert all(section.source_section_kind.startswith("adapter_") for section in blueprint.blueprint_sections)
    assert any(section.caveats == payload.preserved_caveats for section in blueprint.blueprint_sections)
    assert any(section.provenance_required for section in blueprint.blueprint_sections)
    assert any(section.privacy_boundary_required for section in blueprint.blueprint_sections)
    assert any(section.truth_boundary_required for section in blueprint.blueprint_sections)
    assert any(section.safety_boundary_required for section in blueprint.blueprint_sections)
    ref = blueprint.blueprint_refs[0]
    assert ref.ref_id == payload.adapter_refs[0].ref_id
    assert ref.ref_type == payload.adapter_refs[0].ref_type
    assert ref.source_kind == payload.adapter_refs[0].source_kind
    assert ref.provenance_ref_count == len(payload.adapter_refs[0].provenance_refs)
    assert ref.caveat_count == len(payload.adapter_refs[0].caveats)
    assert ref.safety_summary_present is bool(payload.adapter_refs[0].safety_summary)


def test_shadow_blueprint_blocks_materialization_and_refs_for_non_consumable_payloads():
    for payload in (_blocked_payload(), _payload(_not_applicable_envelope())[0], _invalid_payload()):
        blueprint = _blueprint(payload)
        assert blueprint.may_future_assembler_consume is False
        assert blueprint.must_block_prompt_materialization is True
        assert blueprint.blueprint_refs == ()
        assert blueprint.blueprint_ref_count == 0
        assert blueprint.blueprint_sections == ()
        assert blueprint.section_count == 0


def test_shadow_blueprint_digest_is_deterministic_and_changes_for_contract_fields():
    payload, _, _ = _payload(_caveated_envelope())
    first = _blueprint(payload)
    second = _blueprint(payload)
    assert first.digest == second.digest

    ref_changed = replace(payload.adapter_refs[0], ref_id="changed")
    changed_ref_payload = replace(payload, adapter_refs=(ref_changed,))
    assert _blueprint(changed_ref_payload).digest != first.digest

    warning_changed = _mutated(payload, warnings=({"code": "new_warning", "detail": "metadata only"},))
    assert _blueprint(warning_changed).digest != first.digest

    caveat_changed = replace(payload, preserved_caveats=("new caveat",))
    assert _blueprint(caveat_changed).digest != first.digest


def test_shadow_blueprint_does_not_mutate_payload_or_call_live_runtime_paths(monkeypatch):
    payload, _, _ = _payload()
    before = deepcopy(asdict(payload))

    monkeypatch.setattr(pa, "assemble_prompt", lambda *args, **kwargs: pytest.fail("live prompt assembly called"))
    monkeypatch.setattr(pa.mm, "get_context", lambda *args, **kwargs: pytest.fail("memory retrieval called"))
    monkeypatch.setattr(pa.em, "average_emotion", lambda *args, **kwargs: pytest.fail("emotion runtime called"))
    monkeypatch.setattr(pa.cw, "get_context", lambda *args, **kwargs: pytest.fail("context window runtime called"))
    monkeypatch.setattr(pa.actuator, "recent_logs", lambda *args, **kwargs: pytest.fail("action feedback runtime called"))
    monkeypatch.setattr(pa.ac, "capture_affective_context", lambda *args, **kwargs: pytest.fail("feedback capture called"))
    monkeypatch.setattr(pa.ac, "register_context", lambda *args, **kwargs: pytest.fail("feedback register called"))

    blueprint = _blueprint(payload)
    assert asdict(payload) == before
    assert blueprint.does_not_call_llm is True
    assert blueprint.does_not_retrieve_memory is True
    assert blueprint.does_not_write_memory is True
    assert blueprint.does_not_execute_or_route_work is True
    assert blueprint.does_not_admit_work is True


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


def test_static_scan_allows_shadow_preview_and_blueprint_without_live_runtime_wiring_or_bypass():
    findings = scan_prompt_assembler_static_findings(ROOT / "prompt_assembler.py")
    assert findings["context_hygiene_shadow_hook_only"] is True
    assert findings["imports_context_hygiene_adapter_modules"] is True
    assert findings["active_context_hygiene_runtime_wiring"] is False
    assert findings["forbidden_context_bypass_detected"] is False
    assert findings["non_shadow_context_hygiene_imports"] == ()


def test_phase63_to_phase73_shadow_blueprint_pipeline_works_for_sanitized_embodiment_proposal():
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
    blueprint = _blueprint(payload)
    assert payload.adapter_refs
    assert blueprint.blueprint_status in {"shadow_blueprint_ready", "shadow_blueprint_ready_with_warnings"}
    assert blueprint.blueprint_ref_count == len(payload.adapter_refs)
    assert "sanitized posture summary" not in repr(asdict(blueprint))


def test_phase62b_blocked_attempted_candidate_shadow_blueprint_blocks_materialization():
    payload, _, _ = _payload(
        _envelope_for(
            [_cand("blocked", metadata={"source_kind": "evidence", "pollution_risk": "blocked", "non_authoritative": True, "decision_power": "none"})]
        )
    )
    blueprint = _blueprint(payload)
    assert payload.adapter_status in {PromptAssemblyAdapterStatus.ADAPTER_BLOCKED, PromptAssemblyAdapterStatus.ADAPTER_NOT_APPLICABLE}
    assert blueprint.may_future_assembler_consume is False
    assert blueprint.must_block_prompt_materialization is True
    assert blueprint.blueprint_ref_count == 0
    assert blueprint.section_count == 0
