from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

from sentientos.context_hygiene.context_packet import ContextMode
from sentientos.context_hygiene.embodiment_context import build_embodiment_context_candidates
from sentientos.context_hygiene.prompt_adapter_contract import (
    PromptAssemblyAdapterPayload,
    PromptAssemblyAdapterRef,
    PromptAssemblyAdapterStatus,
    build_prompt_assembly_adapter_payload,
    build_prompt_assembly_adapter_payload_from_packet,
)
from sentientos.context_hygiene.prompt_assembler_compliance import (
    PromptAssemblerComplianceStatus,
    adapter_payload_blocks_prompt_materialization,
    adapter_payload_may_be_consumed_by_future_assembler,
    evaluate_prompt_assembler_adapter_compliance,
    prompt_assembler_module_has_no_context_hygiene_runtime_wiring,
    prompt_assembler_module_has_no_forbidden_context_bypass,
    scan_prompt_assembler_static_findings,
    summarize_future_prompt_assembler_integration_contract,
    summarize_prompt_assembler_compliance_report,
)
from sentientos.context_hygiene.prompt_constraint_verifier import (
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


def _not_applicable_envelope():
    return build_context_prompt_dry_run_envelope(build_context_prompt_handoff_manifest(_pkt([])))


def _payload(envelope=None, plan=None):
    envelope = envelope or _ready_envelope()
    plan = plan or build_candidate_plan_from_dry_run_envelope(envelope)
    verification = verify_prompt_assembly_constraints(envelope, plan)
    return build_prompt_assembly_adapter_payload(verification, plan), verification, plan


def _report(payload):
    return evaluate_prompt_assembler_adapter_compliance(payload, prompt_assembler_path=ROOT / "prompt_assembler.py")


def _mutated(payload, **changes):
    data = asdict(payload) if not isinstance(payload, dict) else dict(payload)
    data.update(changes)
    if "adapter_refs" in data:
        data["adapter_refs"] = tuple(PromptAssemblyAdapterRef(**r) if isinstance(r, dict) else r for r in data["adapter_refs"])
    return data


def _codes(report):
    return {gap.code for gap in report.gaps}


def test_ready_adapter_payload_yields_compliance_ready_for_future_integration():
    payload, _, _ = _payload()
    report = _report(payload)
    assert report.compliance_status == PromptAssemblerComplianceStatus.COMPLIANCE_READY_FOR_FUTURE_INTEGRATION
    assert report.may_future_assembler_consume is True
    assert report.must_block_prompt_materialization is False
    assert adapter_payload_may_be_consumed_by_future_assembler(payload)


def test_ready_with_warnings_adapter_payload_yields_compliance_ready_with_warnings():
    payload, _, _ = _payload(_caveated_envelope())
    report = _report(payload)
    assert payload.adapter_status == PromptAssemblyAdapterStatus.ADAPTER_READY_WITH_WARNINGS
    assert report.compliance_status == PromptAssemblerComplianceStatus.COMPLIANCE_READY_WITH_WARNINGS
    assert report.may_future_assembler_consume is True


def test_blocked_adapter_payload_yields_compliance_blocked_and_blocks_materialization():
    envelope = _ready_envelope()
    plan = replace(build_candidate_plan_from_dry_run_envelope(envelope), packet_id="wrong")
    payload, _, _ = _payload(envelope, plan)
    report = _report(payload)
    assert payload.adapter_status == PromptAssemblyAdapterStatus.ADAPTER_BLOCKED
    assert report.compliance_status == PromptAssemblerComplianceStatus.COMPLIANCE_BLOCKED
    assert report.must_block_prompt_materialization is True
    assert adapter_payload_blocks_prompt_materialization(payload)


def test_not_applicable_adapter_payload_yields_compliance_not_applicable():
    payload, _, _ = _payload(_not_applicable_envelope())
    report = _report(payload)
    assert payload.adapter_status == PromptAssemblyAdapterStatus.ADAPTER_NOT_APPLICABLE
    assert report.compliance_status == PromptAssemblerComplianceStatus.COMPLIANCE_NOT_APPLICABLE
    assert report.must_block_prompt_materialization is True


def test_invalid_verification_adapter_payload_yields_invalid_adapter_payload():
    invalid_packet = replace(_pkt([_cand("bad")]), context_packet_id="")
    envelope = build_context_prompt_dry_run_envelope(build_context_prompt_handoff_manifest(invalid_packet))
    payload, _, _ = _payload(envelope)
    report = _report(payload)
    assert payload.adapter_status == PromptAssemblyAdapterStatus.ADAPTER_INVALID_VERIFICATION
    assert report.compliance_status == PromptAssemblerComplianceStatus.COMPLIANCE_INVALID_ADAPTER_PAYLOAD


def test_invalid_candidate_plan_adapter_payload_yields_invalid_adapter_payload():
    envelope = _ready_envelope()
    malformed = {"plan_id": "bad", "candidate_refs": "not refs"}
    verification = verify_prompt_assembly_constraints(envelope, malformed)
    payload = build_prompt_assembly_adapter_payload(verification, malformed)
    report = _report(payload)
    assert payload.adapter_status == PromptAssemblyAdapterStatus.ADAPTER_INVALID_CANDIDATE_PLAN
    assert report.compliance_status == PromptAssemblerComplianceStatus.COMPLIANCE_INVALID_ADAPTER_PAYLOAD


def test_adapter_payload_with_prompt_text_is_blocked():
    payload, _, _ = _payload()
    report = _report(_mutated(payload, prompt_text="forbidden final prompt"))
    assert report.compliance_status == PromptAssemblerComplianceStatus.COMPLIANCE_BLOCKED
    assert "prompt_text_present" in _codes(report)


def test_adapter_payload_with_raw_payload_is_blocked():
    payload, _, _ = _payload()
    report = _report(_mutated(payload, raw_payload={"unsafe": True}))
    assert report.compliance_status == PromptAssemblerComplianceStatus.COMPLIANCE_BLOCKED
    assert "raw_payload_present" in _codes(report)


def test_adapter_payload_with_runtime_authority_is_blocked():
    payload, _, _ = _payload()
    report = _report(_mutated(payload, can_write_memory=True))
    assert report.compliance_status == PromptAssemblerComplianceStatus.COMPLIANCE_BLOCKED
    assert "runtime_authority_present" in _codes(report)


def test_adapter_payload_missing_non_authoritative_posture_is_blocked():
    payload, _, _ = _payload()
    report = _report(_mutated(payload, non_authoritative=False))
    assert report.compliance_status == PromptAssemblerComplianceStatus.COMPLIANCE_BLOCKED
    assert "non_authoritative_missing" in _codes(report)


def test_adapter_payload_missing_caveats_when_expected_is_warned():
    payload, _, _ = _payload()
    data = _mutated(payload)
    data.pop("preserved_caveats")
    report = _report(data)
    assert report.compliance_status == PromptAssemblerComplianceStatus.COMPLIANCE_READY_WITH_WARNINGS
    assert {w.code for w in report.warnings} >= {"caveats_missing"}


def test_adapter_payload_missing_provenance_notes_is_warned():
    payload, _, _ = _payload()
    data = _mutated(payload)
    data.pop("provenance_notes")
    report = _report(data)
    assert report.compliance_status == PromptAssemblerComplianceStatus.COMPLIANCE_READY_WITH_WARNINGS
    assert "provenance_notes_missing" in {w.code for w in report.warnings}


def test_adapter_payload_missing_privacy_truth_safety_notes_is_warned():
    payload, _, _ = _payload()
    data = _mutated(payload)
    data.pop("privacy_notes")
    data.pop("truth_notes")
    data.pop("safety_notes")
    report = _report(data)
    assert report.compliance_status == PromptAssemblerComplianceStatus.COMPLIANCE_READY_WITH_WARNINGS
    assert {"privacy_notes_missing", "truth_notes_missing", "safety_notes_missing"}.issubset({w.code for w in report.warnings})


def test_adapter_refs_present_for_blocked_status_is_blocked():
    ready, _, _ = _payload()
    blocked, _, _ = _payload(_ready_envelope(), replace(build_candidate_plan_from_dry_run_envelope(_ready_envelope()), packet_id="wrong"))
    report = _report(_mutated(blocked, adapter_refs=ready.adapter_refs))
    assert report.compliance_status == PromptAssemblerComplianceStatus.COMPLIANCE_BLOCKED
    assert "adapter_refs_present_for_blocked_status" in _codes(report)


def test_adapter_refs_absent_for_ready_status_is_blocked():
    payload, _, _ = _payload()
    report = _report(_mutated(payload, adapter_refs=()))
    assert report.compliance_status == PromptAssemblerComplianceStatus.COMPLIANCE_BLOCKED
    assert "adapter_refs_missing_for_ready_status" in _codes(report)


def test_missing_digest_is_blocked():
    payload, _, _ = _payload()
    report = _report(_mutated(payload, digest=""))
    assert report.compliance_status == PromptAssemblerComplianceStatus.COMPLIANCE_BLOCKED
    assert "digest_missing" in _codes(report)


def test_missing_packet_envelope_candidate_identifiers_are_blocked():
    payload, _, _ = _payload()
    report = _report(_mutated(payload, packet_id="", envelope_id="", candidate_plan_id=""))
    assert report.compliance_status == PromptAssemblerComplianceStatus.COMPLIANCE_BLOCKED
    assert {"packet_id_missing", "envelope_id_missing", "candidate_plan_id_missing"}.issubset(_codes(report))


def test_static_prompt_assembler_scan_reports_shadow_hook_without_active_context_hygiene_runtime_wiring():
    findings = scan_prompt_assembler_static_findings(ROOT / "prompt_assembler.py")
    assert findings["inspection_mode"] == "source_text_ast_only_no_import"
    assert findings["context_hygiene_shadow_hook_only"] is True
    assert findings["active_context_hygiene_runtime_wiring"] is False
    assert prompt_assembler_module_has_no_context_hygiene_runtime_wiring(ROOT / "prompt_assembler.py") is True


def test_static_prompt_assembler_scan_reports_no_forbidden_context_bypass():
    findings = scan_prompt_assembler_static_findings(ROOT / "prompt_assembler.py")
    assert findings["forbidden_context_bypass_detected"] is False
    assert prompt_assembler_module_has_no_forbidden_context_bypass(ROOT / "prompt_assembler.py") is True


def test_static_prompt_assembler_scan_uses_source_text_ast_only_without_importing_side_effects():
    source = "raise RuntimeError('import side effect')\nfrom sentientos.context_hygiene.prompt_adapter_contract import PromptAssemblyAdapterPayload\n"
    findings = scan_prompt_assembler_static_findings(source_text=source)
    assert findings["inspection_mode"] == "source_text_ast_only_no_import"
    assert findings["imports_prompt_adapter_contract"] is True


def test_future_integration_contract_includes_all_required_must_clauses():
    clauses = "\n".join(rule.must_clause for rule in summarize_future_prompt_assembler_integration_contract())
    for phrase in (
        "MUST accept only PromptAssemblyAdapterPayload",
        "MUST reject adapter statuses other than adapter_ready / adapter_ready_with_warnings",
        "MUST consume only adapter_refs",
        "MUST preserve caveats/provenance/privacy/truth/safety notes",
        "MUST never include raw payloads",
        "MUST never treat adapter payload as authoritative",
        "MUST not retrieve bypass context",
        "MUST not bypass Phase 69 verifier",
        "MUST not bypass Phase 68 envelope",
        "MUST not bypass Phase 64 preflight",
        "MUST not bypass Phase 62 selector",
        "MUST not make blocked refs prompt-visible",
        "MUST emit/record compliance outcome before materialization in a future phase",
    ):
        assert phrase in clauses


def test_report_includes_explicit_non_runtime_markers():
    payload, _, _ = _payload()
    report = _report(payload)
    summary = summarize_prompt_assembler_compliance_report(report)
    assert summary["compliance_harness_only"] is True
    for marker in (
        "compliance_harness_only",
        "does_not_modify_prompt_assembler",
        "does_not_assemble_prompt",
        "does_not_call_llm",
        "does_not_retrieve_memory",
        "does_not_write_memory",
        "does_not_trigger_feedback",
        "does_not_commit_retention",
        "does_not_execute_or_route_work",
        "does_not_admit_work",
    ):
        assert getattr(report, marker) is True


def test_compliance_helper_does_not_mutate_adapter_payload():
    payload, _, _ = _payload()
    before = deepcopy(asdict(payload))
    _report(payload)
    assert asdict(payload) == before


def test_compliance_helper_imports_remain_pure():
    path = ROOT / "sentientos/context_hygiene/prompt_assembler_compliance.py"
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
        "embodiment_ingress",
        "embodiment_proposals",
        "hardware",
        "openai",
        "requests",
        "webbrowser",
    )
    for imp in imports:
        assert not any(token in imp for token in forbidden), imp


def test_phase63_to_adapter_to_compliance_pipeline_works_for_sanitized_embodiment_proposal():
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
    report = _report(payload)
    assert payload.adapter_refs
    assert report.compliance_status in {
        PromptAssemblerComplianceStatus.COMPLIANCE_READY_FOR_FUTURE_INTEGRATION,
        PromptAssemblerComplianceStatus.COMPLIANCE_READY_WITH_WARNINGS,
    }


def test_phase62b_blocked_attempted_candidate_adapter_compliance_blocks_materialization():
    payload, _, _ = _payload(_envelope_for([_cand("blocked", metadata={"source_kind": "evidence", "pollution_risk": "blocked", "non_authoritative": True, "decision_power": "none"})]))
    report = _report(payload)
    assert payload.adapter_status in {PromptAssemblyAdapterStatus.ADAPTER_BLOCKED, PromptAssemblyAdapterStatus.ADAPTER_NOT_APPLICABLE}
    assert report.must_block_prompt_materialization is True
    assert report.may_future_assembler_consume is False
