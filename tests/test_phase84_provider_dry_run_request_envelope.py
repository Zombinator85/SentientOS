"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import importlib
import sys
import types

# Keep privilege imports side-effect-safe under the repo's test ritual.
tts_stub = types.ModuleType("tts_bridge")
tts_stub.speak = lambda *args, **kwargs: None
sys.modules.setdefault("tts_bridge", tts_stub)

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from sentientos.context_hygiene.prompt_internal_candidate import (
    InternalPromptCandidateRef,
    InternalPromptCandidateSection,
    InternalPromptCandidateStatus,
    build_internal_prompt_candidate_input,
    compute_internal_prompt_candidate_digest,
    materialize_internal_no_llm_prompt_candidate,
)
from sentientos.context_hygiene.prompt_internal_display import InternalPromptDisplayScope, build_internal_prompt_display_receipt
from sentientos.context_hygiene.prompt_materialization_policy import PromptMaterializationPolicyRing, PromptMaterializationPolicyStatus
from sentientos.context_hygiene.prompt_model_call_preflight import (
    InternalModelCallPreflightRing,
    InternalModelCallPreflightStatus,
    build_internal_model_call_preflight_input,
    compute_internal_model_call_preflight_digest,
    evaluate_internal_model_call_preflight,
)
from sentientos.context_hygiene.prompt_model_call_review import (
    InternalModelCallReviewDecision,
    InternalModelCallReviewScope,
    InternalModelCallReviewStatus,
    build_internal_model_call_review_receipt,
    compute_internal_model_call_review_digest,
    extract_required_internal_model_call_review_mitigation_codes,
)
from sentientos.context_hygiene.prompt_provider_dry_run import (
    ProviderDryRunModelFamily,
    ProviderDryRunProviderFamily,
    ProviderDryRunScope,
    ProviderDryRunStatus,
    build_provider_dry_run_request_envelope,
    compute_provider_dry_run_digest,
    provider_dry_run_has_no_network_egress,
    provider_dry_run_has_no_provider_credentials,
    provider_dry_run_has_no_runtime_authority,
    provider_dry_run_is_non_sendable,
    provider_dry_run_preserves_review_receipt,
    summarize_provider_dry_run_request_envelope,
    validate_provider_dry_run_request_envelope,
)
from scripts.verify_context_hygiene_prompt_boundaries import scan_context_hygiene_prompt_boundaries

READY = ProviderDryRunStatus.PROVIDER_DRY_RUN_READY
WARN = ProviderDryRunStatus.PROVIDER_DRY_RUN_READY_WITH_WARNINGS
BLOCKED = ProviderDryRunStatus.PROVIDER_DRY_RUN_BLOCKED
REVIEW_MISSING = ProviderDryRunStatus.PROVIDER_DRY_RUN_REVIEW_MISSING
PREFLIGHT_NOT_READY = ProviderDryRunStatus.PROVIDER_DRY_RUN_PREFLIGHT_NOT_READY
SEND_FORBIDDEN = ProviderDryRunStatus.PROVIDER_DRY_RUN_SEND_FORBIDDEN
RUNTIME = ProviderDryRunStatus.PROVIDER_DRY_RUN_RUNTIME_AUTHORITY_DETECTED
CREDS = ProviderDryRunStatus.PROVIDER_DRY_RUN_CREDENTIALS_DETECTED
NETWORK = ProviderDryRunStatus.PROVIDER_DRY_RUN_NETWORK_EGRESS_DETECTED
OPENAI_LABEL = ProviderDryRunProviderFamily.PROVIDER_FAMILY_OPENAI_LABEL_ONLY
LOCAL_LABEL = ProviderDryRunProviderFamily.PROVIDER_FAMILY_LOCAL_LABEL_ONLY
REASONING_LABEL = ProviderDryRunModelFamily.MODEL_FAMILY_REASONING_LABEL_ONLY
CHAT_LABEL = ProviderDryRunModelFamily.MODEL_FAMILY_CHAT_LABEL_ONLY


def _policy(status: str = PromptMaterializationPolicyStatus.POLICY_INTERNAL_CANDIDATE_NO_LLM_ALLOWED, **overrides):
    data = {
        "decision_id": "policy:packet:1",
        "policy_status": status,
        "requested_ring": PromptMaterializationPolicyRing.RING_INTERNAL_CANDIDATE_NO_LLM,
        "effective_ring": PromptMaterializationPolicyRing.RING_INTERNAL_CANDIDATE_NO_LLM,
        "allowed": status == PromptMaterializationPolicyStatus.POLICY_INTERNAL_CANDIDATE_NO_LLM_ALLOWED,
        "denied": status == PromptMaterializationPolicyStatus.POLICY_DENY,
        "requires_operator_review": status == PromptMaterializationPolicyStatus.POLICY_OPERATOR_REVIEW_REQUIRED,
        "allows_shadow_only": status == PromptMaterializationPolicyStatus.POLICY_SHADOW_ONLY,
        "allows_synthetic_materializer": False,
        "allows_internal_candidate_no_llm": status == PromptMaterializationPolicyStatus.POLICY_INTERNAL_CANDIDATE_NO_LLM_ALLOWED,
        "forbids_live_llm": True,
        "forbids_memory_retrieval": True,
        "forbids_memory_write": True,
        "forbids_action_execution": True,
        "forbids_retention_commit": True,
        "reasons": (),
        "required_mitigations": (),
        "receipt_id": "audit:1",
        "receipt_digest": "digest:audit:1",
        "packet_id": "packet:1",
        "packet_scope": "turn",
        "source_kind_summary": {"evidence": 1},
        "caveat_count": 0,
        "warning_count": 0,
        "violation_count": 0,
        "finding_count": 0,
        "rationale": "test policy",
        "policy_digest": "digest:policy:1",
        "does_not_call_llm": True,
        "does_not_retrieve_memory": True,
        "does_not_write_memory": True,
        "does_not_trigger_feedback": True,
        "does_not_commit_retention": True,
        "does_not_execute_or_route_work": True,
        "does_not_admit_work": True,
    }
    data.update(overrides)
    return data


def _audit(**overrides):
    data = {
        "receipt_id": "audit:1",
        "audit_status": "audit_ready_for_shadow_materialization",
        "blueprint_id": "blueprint:1",
        "blueprint_digest": "digest:blueprint:1",
        "adapter_payload_id": "adapter:1",
        "adapter_status": "adapter_ready",
        "compliance_status": "compliance_ready",
        "preview_status": "preview_ready",
        "blueprint_status": "shadow_blueprint_ready",
        "packet_id": "packet:1",
        "packet_scope": "turn",
        "manifest_id": "manifest:1",
        "manifest_digest": "digest:manifest:1",
        "envelope_id": "envelope:1",
        "envelope_digest": "digest:envelope:1",
        "candidate_plan_id": "plan:1",
        "candidate_plan_digest": "digest:plan:1",
        "adapter_payload_digest": "digest:adapter:1",
        "verification_digest": "digest:verification:1",
        "shadow_preview_digest": "digest:preview:1",
        "shadow_blueprint_digest": "digest:shadow-blueprint:1",
        "digest_chain_complete": True,
        "digest_chain": {"complete": True, "missing": ()},
        "boundary_summary": {"may_future_assembler_consume": True, "must_block_prompt_materialization": False},
        "preserved_caveats": (),
        "warnings": (),
        "violations": (),
        "findings": (),
        "provenance_summary": {},
        "privacy_summary": {},
        "truth_summary": {},
        "safety_summary": {},
        "source_kind_summary": {"evidence": 1},
        "ref_counts": {"included": 1},
        "section_counts": {"included": 1},
        "rationale": "audit ready",
        "receipt_digest": "digest:audit:1",
        "audit_receipt_only": True,
        "attestation_only": True,
        "does_not_materialize_prompt_text": True,
        "does_not_assemble_prompt": True,
        "does_not_contain_final_prompt_text": True,
        "does_not_call_llm": True,
        "does_not_retrieve_memory": True,
        "does_not_write_memory": True,
        "does_not_trigger_feedback": True,
        "does_not_commit_retention": True,
        "does_not_execute_or_route_work": True,
        "does_not_admit_work": True,
    }
    data.update(overrides)
    return data


def _candidate(*, policy=None, audit=None, warnings=False, text_suffix=""):
    policy = policy or _policy(warning_count=1 if warnings else 0)
    audit = audit or _audit(warnings=("audit warning",) if warnings else ())
    candidate_input = build_internal_prompt_candidate_input(
        policy_decision=policy,
        audit_receipt=audit,
        adapter_payload={"adapter_payload_id": "adapter:1", "digest": "digest:adapter:1", "adapter_status": "adapter_ready"},
        blueprint={"blueprint_id": "blueprint:1", "blueprint_digest": "digest:blueprint:1", "blueprint_status": "shadow_blueprint_ready"},
        candidate_refs=(
            InternalPromptCandidateRef(
                ref_id="ref:1",
                ref_kind="adapter_ref",
                summary="approved packet-safe context summary",
                provenance_summary="prov:1",
                source_kind="evidence",
                caveats=("accepted caveat",) if warnings else (),
                boundary_notes=("packet-safe summary only",),
            ),
        ),
        candidate_sections=(
            InternalPromptCandidateSection(
                section_id="section:1",
                section_kind="adapter_context_refs",
                summary="approved packet-safe section summary",
                ref_ids=("ref:1",),
                caveats=("accepted caveat",) if warnings else (),
                boundary_notes=("packet-safe summary only",),
            ),
        ),
        preserved_caveats=("accepted caveat",) if warnings else (),
        preserved_boundary_notes=("boundary preserved",),
        feature_flag_state={"internal_no_llm_candidate": True},
    )
    candidate = materialize_internal_no_llm_prompt_candidate(candidate_input)
    if text_suffix:
        candidate = replace(candidate, internal_candidate_text=candidate.internal_candidate_text + text_suffix)
        candidate = replace(candidate, candidate_digest=compute_internal_prompt_candidate_digest(candidate))
    return candidate


def _display(candidate=None, *, display_scope=InternalPromptDisplayScope.OPERATOR_INTERNAL_REVIEW):
    candidate = candidate or _candidate()
    return build_internal_prompt_display_receipt(
        candidate,
        display_scope=display_scope,
        operator_ref="operator:phase84",
        display_reason="phase84 provider dry-run test",
        expires_at="2030-01-01T00:00:00Z",
    )


def _preflight(**overrides):
    policy = overrides.pop("policy", _policy())
    audit = overrides.pop("audit", _audit())
    candidate = overrides.pop("candidate", _candidate(policy=policy, audit=audit))
    display = overrides.pop("display", _display(candidate))
    flags = overrides.pop("feature_flag_state", {"model_call_preflight": True})
    input_data = build_internal_model_call_preflight_input(candidate, display, policy, audit, feature_flag_state=flags, **overrides)
    return evaluate_internal_model_call_preflight(input_data)


def _review(preflight=None, **overrides):
    preflight = preflight or _preflight()
    required = extract_required_internal_model_call_review_mitigation_codes(preflight)
    kwargs = {
        "reviewer_ref": "operator:phase84",
        "decision": InternalModelCallReviewDecision.APPROVE_FUTURE_REVIEW_GATE,
        "review_scope": InternalModelCallReviewScope.INTERNAL_MODEL_CALL_REVIEW_GATE,
        "approved_constraint_codes": tuple(code for code in required if code.startswith("constraint:")),
        "accepted_mitigation_codes": required,
        "expires_at": "2030-01-01T00:00:00Z",
        "reviewed_at": "2026-05-08T00:00:00Z",
        "evaluated_at": "2026-05-08T00:00:00Z",
        "rationale": "metadata-only future gate review; provider calls remain forbidden",
    }
    kwargs.update(overrides)
    return build_internal_model_call_review_receipt(preflight, **kwargs)


def _chain(*, warnings=False):
    policy = _policy(warning_count=1 if warnings else 0)
    audit = _audit(warnings=("audit warning",) if warnings else ())
    candidate = _candidate(policy=policy, audit=audit, warnings=warnings)
    display = _display(candidate)
    preflight = _preflight(policy=policy, audit=audit, candidate=candidate, display=display)
    if warnings:
        preflight = replace(preflight, preflight_status=InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_READY_WITH_WARNINGS, warnings=("phase84 warning",))
        preflight = replace(preflight, preflight_digest=compute_internal_model_call_preflight_digest(preflight))
        preflight = replace(preflight, preflight_id=f"internal-model-call-preflight:{preflight.candidate_id or 'missing'}:{preflight.preflight_digest[:16]}")
    review = _review(preflight)
    return candidate, display, preflight, review


def _envelope(**overrides):
    candidate, display, preflight, review = overrides.pop("chain", _chain())
    return build_provider_dry_run_request_envelope(
        overrides.pop("candidate", candidate),
        overrides.pop("display_receipt", display),
        overrides.pop("preflight", preflight),
        overrides.pop("review_receipt", review),
        provider_family_label=overrides.pop("provider_family_label", OPENAI_LABEL),
        model_family_label=overrides.pop("model_family_label", REASONING_LABEL),
        request_purpose=overrides.pop("request_purpose", "internal provider dry-run review"),
        dry_run_scope=overrides.pop("dry_run_scope", ProviderDryRunScope.INTERNAL_REVIEW_ONLY),
        **overrides,
    )


def _codes(envelope):
    return {finding.code for finding in envelope.findings}


def test_valid_chain_produces_provider_dry_run_ready_and_summary_preserves_review():
    candidate, display, preflight, review = _chain()
    envelope = _envelope(chain=(candidate, display, preflight, review))
    assert envelope.dry_run_status == READY
    assert provider_dry_run_is_non_sendable(envelope)
    assert provider_dry_run_preserves_review_receipt(envelope, review)
    assert validate_provider_dry_run_request_envelope(envelope) == ()
    assert summarize_provider_dry_run_request_envelope(envelope)["dry_run_status"] == READY


def test_ready_with_warnings_chain_produces_warning_status():
    envelope = _envelope(chain=_chain(warnings=True))
    assert envelope.dry_run_status == WARN
    assert provider_dry_run_is_non_sendable(envelope)


def test_missing_rejected_expired_or_mismatched_review_blocks():
    candidate, display, preflight, review = _chain()
    assert _envelope(chain=(candidate, display, preflight, None)).dry_run_status == REVIEW_MISSING
    rejected = _review(preflight, decision=InternalModelCallReviewDecision.REJECT_FUTURE_REVIEW_GATE, accepted_mitigation_codes=())
    expired = _review(preflight, expires_at="2026-05-08T00:00:00Z", evaluated_at="2026-05-08T00:00:00Z")
    mismatched = replace(review, preflight_id="other", review_digest=compute_internal_model_call_review_digest(replace(review, preflight_id="other")))
    for bad in (rejected, expired, mismatched):
        envelope = _envelope(chain=(candidate, display, preflight, bad))
        assert envelope.dry_run_status == BLOCKED
        assert "review_does_not_satisfy_preflight" in _codes(envelope)


def test_denied_provider_forbidden_and_candidate_display_blocks():
    candidate = replace(_candidate(), status=InternalPromptCandidateStatus.INTERNAL_PROMPT_CANDIDATE_BLOCKED)
    preflight_denied = _preflight(no_actions=False)
    preflight_provider_forbidden = _preflight(requested_model_review_ring=InternalModelCallPreflightRing.INTERNAL_MODEL_CALL_DRY_RUN_FORBIDDEN_PROVIDER)
    display_denied = _display(_candidate(), display_scope=InternalPromptDisplayScope.EXTERNAL_USER_VISIBLE_FORBIDDEN)
    assert _envelope(candidate=candidate).dry_run_status == BLOCKED
    assert _envelope(preflight=preflight_denied, review_receipt=_review(preflight_denied)).dry_run_status in {PREFLIGHT_NOT_READY, RUNTIME}
    assert _envelope(preflight=preflight_provider_forbidden, review_receipt=_review(preflight_provider_forbidden)).dry_run_status == PREFLIGHT_NOT_READY
    assert _envelope(display_receipt=display_denied).dry_run_status == BLOCKED


def test_unknown_labels_and_live_scope_block():
    assert _envelope(provider_family_label=ProviderDryRunProviderFamily.PROVIDER_FAMILY_UNKNOWN_FORBIDDEN).dry_run_status == BLOCKED
    assert _envelope(model_family_label=ProviderDryRunModelFamily.MODEL_FAMILY_UNKNOWN_FORBIDDEN).dry_run_status == BLOCKED
    assert _envelope(dry_run_scope="live_provider_scope").dry_run_status == BLOCKED


def test_credentials_network_provider_client_and_auth_markers_block():
    bad_keys = ["api" + "_key", "endpoint", "url", "auth", "headers", "client", "session"]
    expected = [CREDS, NETWORK, NETWORK, CREDS, CREDS, CREDS, CREDS]
    for key, status in zip(bad_keys, expected):
        envelope = _envelope(extra_metadata={key: "present"})
        assert envelope.dry_run_status == status
    assert not provider_dry_run_has_no_provider_credentials(_envelope(extra_metadata={"api" + "_key": "present"}))
    assert not provider_dry_run_has_no_network_egress(_envelope(extra_metadata={"endpoint": "present"}))


def test_marker_false_cases_and_runtime_markers_block_non_sendability():
    assert _envelope(marker_overrides={"provider_send_forbidden": False}).dry_run_status == SEND_FORBIDDEN
    assert _envelope(marker_overrides={"non_sendable": False}).dry_run_status == SEND_FORBIDDEN
    for key in ("tool_call", "tool_schema", "function_call", "memory_handle", "action_handle", "retention_handle", "routing_handle", "raw_payload", "runtime_authority", "llm_params", "provider_params"):
        envelope = _envelope(extra_metadata={key: "present"})
        assert envelope.dry_run_status == RUNTIME
    assert not provider_dry_run_has_no_runtime_authority(_envelope(extra_metadata={"action_handle": "present"}))
    assert not provider_dry_run_is_non_sendable(_envelope(marker_overrides={"non_sendable": False}))


def test_prompt_text_and_payload_shape_are_non_provider_dry_run_only():
    envelope = _envelope()
    assert "INTERNAL NO-LLM CANDIDATE" in envelope.dry_run_prompt_text
    assert "NON-SENDABLE PROVIDER DRY RUN" in envelope.dry_run_prompt_text
    assert "raw_payload" not in envelope.dry_run_prompt_text
    payload = envelope.dry_run_payload_shape
    labels = {entry["dry_run_label"] for entry in payload.entries}
    assert {"dry_run_internal_candidate", "dry_run_boundary_notes", "dry_run_caveats"}.issubset(labels)
    rendered = str(payload).lower()
    for forbidden in ('"role": "system"', '"role": "developer"', "api" + "_key", "endpoint", "auth:", "client:", "session:"):
        assert forbidden not in rendered


def test_digest_is_deterministic_and_changes_for_linkage_labels_text_and_metadata():
    candidate, display, preflight, review = _chain()
    one = _envelope(chain=(candidate, display, preflight, review))
    two = _envelope(chain=(candidate, display, preflight, review))
    assert one.dry_run_digest == two.dry_run_digest == compute_provider_dry_run_digest(one)
    changed_candidate = replace(candidate, internal_candidate_text=candidate.internal_candidate_text + "\nextra safe note")
    changed_candidate = replace(changed_candidate, candidate_digest=compute_internal_prompt_candidate_digest(changed_candidate))
    assert _envelope(candidate=changed_candidate).dry_run_digest != one.dry_run_digest
    assert _envelope(preflight=replace(preflight, preflight_digest="changed"), review_receipt=review).dry_run_digest != one.dry_run_digest
    assert _envelope(review_receipt=replace(review, review_digest="changed")).dry_run_digest != one.dry_run_digest
    assert _envelope(provider_family_label=LOCAL_LABEL, model_family_label=CHAT_LABEL).dry_run_digest != one.dry_run_digest
    assert _envelope(request_purpose="different internal dry-run purpose").dry_run_digest != one.dry_run_digest
    assert _envelope(extra_metadata={"max_output_tokens_metadata_note": 1}).dry_run_digest != one.dry_run_digest


def test_builder_does_not_mutate_inputs_or_call_runtime_surfaces(monkeypatch):
    candidate, display, preflight, review = _chain()
    originals = deepcopy((candidate, display, preflight, review))
    forbidden_modules = ("prompt_assembler", "openai", "requests", "httpx", "memory_manager", "action_router", "retention", "routing")
    for module_name in forbidden_modules:
        sys.modules.pop(module_name, None)
    envelope = _envelope(chain=(candidate, display, preflight, review))
    assert (candidate, display, preflight, review) == originals
    assert envelope.dry_run_status == READY
    assert "prompt_assembler" not in sys.modules
    for module_name in ("openai", "requests", "httpx", "memory_manager"):
        assert module_name not in sys.modules


def test_phase63_to_phase84_and_blocked_attempted_candidate_paths_are_gated():
    candidate, display, preflight, review = _chain()
    assert candidate.packet_id == preflight.packet_id == "packet:1"
    assert _envelope(chain=(candidate, display, preflight, review)).dry_run_status == READY
    blocked = replace(candidate, status=InternalPromptCandidateStatus.INTERNAL_PROMPT_CANDIDATE_FORBIDDEN_RAW_CONTEXT)
    assert _envelope(candidate=blocked).dry_run_status == BLOCKED
    adversarial = replace(candidate, internal_candidate_text=candidate.internal_candidate_text + "\nprovider_params runtime_authority")
    adversarial = replace(adversarial, candidate_digest=compute_internal_prompt_candidate_digest(adversarial))
    assert _envelope(candidate=adversarial).dry_run_status == RUNTIME


def test_phase75_guardrail_allows_new_dry_run_text_and_rejects_provider_markers(tmp_path):
    clean = scan_context_hygiene_prompt_boundaries(["sentientos/context_hygiene/prompt_provider_dry_run.py"])
    assert clean.ok, [finding.to_dict() for finding in clean.findings]
    fixture = tmp_path / "bad_provider_dry_run_fixture.py"
    fixture.write_text('from dataclasses import dataclass\napi_key = "x"\nendpoint = "x"\nclient = object()\nsession = object()\nprovider_params = {}\n', encoding="utf-8")
    report = scan_context_hygiene_prompt_boundaries([fixture])
    details = "\n".join(f.detail for f in report.findings)
    assert not report.ok
    assert "api_key" in details and "endpoint" in details and "client" in details and "session" in details and "provider_params" in details


def test_import_purity_surface_imports():
    module = importlib.import_module("sentientos.context_hygiene.prompt_provider_dry_run")
    assert hasattr(module, "ProviderDryRunRequestEnvelope")
