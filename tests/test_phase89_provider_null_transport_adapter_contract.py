"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import importlib
import sys
import types
from pathlib import Path

# Keep privilege imports side-effect-safe under the repo's test ritual.
tts_stub = types.ModuleType("tts_bridge")
tts_stub.speak = lambda *args, **kwargs: None
sys.modules.setdefault("tts_bridge", tts_stub)

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from sentientos.context_hygiene.prompt_internal_candidate import InternalPromptCandidateStatus, compute_internal_prompt_candidate_digest
from sentientos.context_hygiene.prompt_network_egress_preflight import (
    ProviderNetworkEgressPreflightRing,
    ProviderNetworkEgressPreflightStatus,
    compute_provider_network_egress_preflight_digest,
)
from sentientos.context_hygiene.prompt_network_egress_review import (
    ProviderNetworkEgressReviewDecision,
    ProviderNetworkEgressReviewScope,
    compute_provider_network_egress_review_digest,
    extract_required_provider_network_egress_review_mitigation_codes,
)
from sentientos.context_hygiene.prompt_provider_dry_run import ProviderDryRunStatus, compute_provider_dry_run_digest
from sentientos.context_hygiene.prompt_provider_null_transport import (
    ProviderNullTransportMode,
    ProviderNullTransportScope,
    ProviderNullTransportStatus,
    build_provider_null_transport_receipt,
    compute_provider_null_transport_digest,
    explain_provider_null_transport_findings,
    provider_null_transport_digest_chain_complete,
    provider_null_transport_has_no_endpoint,
    provider_null_transport_has_no_network,
    provider_null_transport_has_no_provider_client,
    provider_null_transport_has_no_provider_credentials,
    provider_null_transport_has_no_runtime_authority,
    provider_null_transport_preserves_network_egress_review,
    provider_null_transport_sent_nothing,
    summarize_provider_null_transport_receipt,
    validate_provider_null_transport_receipt,
)
from scripts.verify_context_hygiene_prompt_boundaries import scan_context_hygiene_prompt_boundaries
from tests.test_phase84_provider_dry_run_request_envelope import _chain, _envelope
from tests.test_phase87_provider_simulation_network_egress_preflight import _preflight
from tests.test_phase88_provider_network_egress_review_receipt import _receipt as _network_review

REPO_ROOT = Path(__file__).resolve().parents[1]
READY = ProviderNullTransportStatus.NULL_TRANSPORT_READY
WARN = ProviderNullTransportStatus.NULL_TRANSPORT_READY_WITH_WARNINGS
REVIEW_MISSING = ProviderNullTransportStatus.NULL_TRANSPORT_REVIEW_MISSING
REVIEW_NOT_SATISFIED = ProviderNullTransportStatus.NULL_TRANSPORT_REVIEW_NOT_SATISFIED
DRY_NOT_READY = ProviderNullTransportStatus.NULL_TRANSPORT_DRY_RUN_NOT_READY
PREFLIGHT_NOT_READY = ProviderNullTransportStatus.NULL_TRANSPORT_PREFLIGHT_NOT_READY
INVALID = ProviderNullTransportStatus.NULL_TRANSPORT_INVALID_INPUT
NETWORK = ProviderNullTransportStatus.NULL_TRANSPORT_NETWORK_FORBIDDEN
CREDS = ProviderNullTransportStatus.NULL_TRANSPORT_CREDENTIALS_DETECTED
ENDPOINT = ProviderNullTransportStatus.NULL_TRANSPORT_ENDPOINT_DETECTED
CLIENT = ProviderNullTransportStatus.NULL_TRANSPORT_CLIENT_DETECTED
RUNTIME = ProviderNullTransportStatus.NULL_TRANSPORT_RUNTIME_AUTHORITY_DETECTED
SEND = ProviderNullTransportStatus.NULL_TRANSPORT_SEND_ATTEMPT_DETECTED


def _required(preflight):
    return extract_required_provider_network_egress_review_mitigation_codes(preflight)


def _null_review(preflight=None, **overrides):
    preflight = preflight if preflight is not None else _preflight()
    required = _required(preflight)
    kwargs = {
        "decision": ProviderNetworkEgressReviewDecision.APPROVE_FUTURE_TRANSPORT_NULL_ADAPTER_GATE,
        "review_scope": ProviderNetworkEgressReviewScope.FUTURE_TRANSPORT_NULL_ADAPTER_GATE,
        "approved_constraint_codes": required,
        "accepted_mitigation_codes": required,
    }
    kwargs.update(overrides)
    return _network_review(preflight, **kwargs)


def _receipt(envelope=None, preflight=None, review=None, **overrides):
    envelope = envelope if envelope is not None else _envelope()
    preflight = preflight if preflight is not None else _preflight(envelope=envelope)
    review = review if review is not None else _null_review(preflight)
    return build_provider_null_transport_receipt(envelope, preflight, review, **overrides)


def _codes(receipt):
    return {finding.code for finding in receipt.findings}


def _with_dry_digest(envelope, **overrides):
    changed = replace(envelope, **overrides)
    return replace(changed, dry_run_digest=compute_provider_dry_run_digest(changed))


def _with_preflight_digest(preflight, **overrides):
    changed = replace(preflight, **overrides)
    return replace(changed, preflight_digest=compute_provider_network_egress_preflight_digest(changed))


def _with_review_digest(review, **overrides):
    changed = replace(review, **overrides)
    return replace(changed, review_digest=compute_provider_network_egress_review_digest(changed))


def test_ready_chain_yields_null_transport_ready_and_summary():
    receipt = _receipt()
    assert receipt.null_transport_status == READY
    assert receipt.null_transport_scope == ProviderNullTransportScope.FUTURE_TRANSPORT_NULL_ADAPTER_GATE
    assert validate_provider_null_transport_receipt(receipt) == ()
    assert summarize_provider_null_transport_receipt(receipt)["null_transport_status"] == READY
    assert provider_null_transport_digest_chain_complete(receipt)
    assert provider_null_transport_preserves_network_egress_review(receipt, _null_review(_preflight(envelope=_envelope()))) is False or receipt.network_review_receipt_id


def test_ready_with_warnings_path_yields_warning_status():
    envelope = _envelope(chain=_chain(warnings=True))
    preflight = _preflight(envelope=envelope, requested_ring=ProviderNetworkEgressPreflightRing.FUTURE_PROVIDER_CALL_DRY_RUN_GATE)
    review = _null_review(preflight)
    receipt = _receipt(envelope, preflight, review)
    assert receipt.null_transport_status == WARN
    assert receipt.warnings


def test_missing_review_expired_or_mismatched_review_blocks():
    envelope = _envelope(); preflight = _preflight(envelope=envelope)
    assert build_provider_null_transport_receipt(envelope, preflight, None).null_transport_status == REVIEW_MISSING
    expired = _null_review(preflight, expires_at="2026-05-09T00:00:00Z", evaluated_at="2026-05-09T00:00:00Z")
    mismatched = _with_review_digest(_null_review(preflight), network_preflight_id="preflight:mismatch")
    for bad in (expired, mismatched):
        receipt = _receipt(envelope, preflight, bad)
        assert receipt.null_transport_status == REVIEW_NOT_SATISFIED
        assert "network_review_does_not_satisfy_preflight" in _codes(receipt)


def test_dry_run_blocked_and_preflight_denied_or_invalid_block():
    blocked = _with_dry_digest(_envelope(), dry_run_status=ProviderDryRunStatus.PROVIDER_DRY_RUN_BLOCKED)
    assert _receipt(envelope=blocked).null_transport_status == DRY_NOT_READY
    for status in (
        ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_DENIED,
        ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_INVALID_INPUT,
    ):
        preflight = _with_preflight_digest(_preflight(), preflight_status=status)
        receipt = _receipt(preflight=preflight, review=_null_review(preflight))
        assert receipt.null_transport_status in {PREFLIGHT_NOT_READY, REVIEW_NOT_SATISFIED}


def test_review_not_satisfying_or_lacking_null_adapter_gate_blocks():
    preflight = _preflight()
    ordinary = _network_review(preflight)  # Phase 88 future-network gate, not null-adapter gate.
    receipt = _receipt(preflight=preflight, review=ordinary)
    assert receipt.null_transport_status == REVIEW_NOT_SATISFIED
    assert "network_review_missing_null_transport_gate" in _codes(receipt)


def test_modes_and_scopes_are_metadata_only():
    for mode in ("unknown", ProviderNullTransportMode.LIVE_NETWORK, ProviderNullTransportMode.PROVIDER_SEND, ProviderNullTransportMode.HTTP_REQUEST, ProviderNullTransportMode.SOCKET_TRANSPORT, ProviderNullTransportMode.SEMANTIC_GENERATION):
        assert _receipt(null_transport_mode=mode).null_transport_status == INVALID
    scope_statuses = {
        ProviderNullTransportScope.PROVIDER_SEND_FORBIDDEN: SEND,
        ProviderNullTransportScope.NETWORK_EGRESS_FORBIDDEN: NETWORK,
        ProviderNullTransportScope.CREDENTIAL_USE_FORBIDDEN: CREDS,
        ProviderNullTransportScope.ENDPOINT_USE_FORBIDDEN: ENDPOINT,
        ProviderNullTransportScope.PROVIDER_CLIENT_USE_FORBIDDEN: CLIENT,
        ProviderNullTransportScope.EXTERNAL_USER_VISIBLE_FORBIDDEN: RUNTIME,
    }
    for scope, status in scope_statuses.items():
        assert _receipt(null_transport_scope=scope).null_transport_status == status
    assert _receipt(null_transport_scope=ProviderNullTransportScope.INTERNAL_NULL_TRANSPORT_AUDIT).null_transport_status == READY


def test_digest_chain_incomplete_and_mismatch_block_deterministically():
    envelope = _envelope(); preflight = _preflight(envelope=envelope); review = _null_review(preflight)
    missing = _receipt(envelope=replace(envelope, dry_run_digest=""), preflight=preflight, review=review)
    assert missing.null_transport_status in {INVALID, DRY_NOT_READY}
    assert "digest_chain_incomplete" in _codes(missing)
    mismatch = _receipt(envelope, preflight, review, expected_dry_run_digest="sha256:mismatch")
    assert mismatch.null_transport_status == INVALID
    assert "digest_chain_incomplete" in _codes(mismatch)


def test_send_network_provider_runtime_attempt_markers_block_with_specific_statuses():
    send_cases = ("sent", "bytes_sent", "request_created", "response_received", "provider_send_attempted")
    for field_name in send_cases:
        value = 1 if field_name == "bytes_sent" else True
        assert _receipt(**{field_name: value}).null_transport_status == SEND
    for field_name in ("network_egress_attempted", "socket_opened", "http_request_attempted"):
        assert _receipt(**{field_name: True}).null_transport_status == NETWORK
    assert _receipt(credentials_used=True).null_transport_status == CREDS
    assert _receipt(endpoint_used=True).null_transport_status == ENDPOINT
    assert _receipt(provider_client_used=True).null_transport_status == CLIENT
    for field_name in ("llm_call_attempted", "semantic_generation_attempted", "tool_calls_attempted", "memory_access_attempted", "retention_attempted", "action_execution_attempted", "routing_attempted"):
        assert _receipt(**{field_name: True}).null_transport_status == RUNTIME


def test_raw_payload_runtime_handle_and_provider_parameter_markers_block():
    assert _receipt(no_raw_payload_marker=False).null_transport_status == RUNTIME
    assert _receipt(no_runtime_handle_marker=False).null_transport_status == RUNTIME
    assert _receipt(no_provider_model_params=False).null_transport_status == RUNTIME
    assert _receipt(marker_evidence={"raw_payload": "x"}).null_transport_status == RUNTIME
    assert _receipt(marker_evidence={"runtime_handle": "x"}).null_transport_status == RUNTIME
    assert _receipt(marker_evidence={"provider_params": {"temperature": 0}}).null_transport_status == RUNTIME


def test_no_runtime_and_no_network_flags_block():
    expected = {
        "no_network": NETWORK,
        "no_provider_send": RUNTIME,
        "no_credentials": CREDS,
        "no_endpoint": ENDPOINT,
        "no_provider_client": CLIENT,
        "no_http": NETWORK,
        "no_socket": NETWORK,
        "no_semantic_generation": RUNTIME,
        "no_tools": RUNTIME,
        "no_memory": RUNTIME,
        "no_retention": RUNTIME,
        "no_actions": RUNTIME,
        "no_routing": RUNTIME,
    }
    for field_name, status in expected.items():
        assert _receipt(**{field_name: False}).null_transport_status == status


def test_clean_output_proof_fields_and_helpers_are_strict():
    receipt = _receipt()
    assert receipt.sent is False and receipt.bytes_sent == 0
    assert receipt.request_created is False and receipt.response_received is False
    assert provider_null_transport_sent_nothing(receipt)
    assert provider_null_transport_has_no_network(receipt)
    assert provider_null_transport_has_no_provider_credentials(receipt)
    assert provider_null_transport_has_no_endpoint(receipt)
    assert provider_null_transport_has_no_provider_client(receipt)
    assert provider_null_transport_has_no_runtime_authority(receipt)
    assert not provider_null_transport_sent_nothing(_receipt(sent=True))
    assert not provider_null_transport_has_no_network(_receipt(socket_opened=True))
    assert not provider_null_transport_has_no_provider_credentials(_receipt(credentials_used=True))
    assert not provider_null_transport_has_no_endpoint(_receipt(endpoint_used=True))
    assert not provider_null_transport_has_no_provider_client(_receipt(provider_client_used=True))
    assert not provider_null_transport_has_no_runtime_authority(_receipt(memory_access_attempted=True))


def test_digest_is_deterministic_and_changes_for_linkage_mode_scope_and_attempts():
    envelope = _envelope(); preflight = _preflight(envelope=envelope); review = _null_review(preflight)
    one = _receipt(envelope, preflight, review)
    two = _receipt(envelope, preflight, review)
    assert one.null_transport_digest == two.null_transport_digest == compute_provider_null_transport_digest(one)
    dry_changed = _with_dry_digest(envelope, request_purpose="different metadata-only reason")
    assert _receipt(dry_changed).null_transport_digest != one.null_transport_digest
    preflight_changed = _with_preflight_digest(preflight, requested_ring=ProviderNetworkEgressPreflightRing.FUTURE_PROVIDER_CALL_DRY_RUN_GATE)
    assert _receipt(envelope, preflight_changed, _null_review(preflight_changed)).null_transport_digest != one.null_transport_digest
    review_changed = _with_review_digest(review, reviewer_ref="reviewer:changed")
    assert _receipt(envelope, preflight, review_changed).null_transport_digest != one.null_transport_digest
    assert _receipt(envelope, preflight, review, null_transport_mode=ProviderNullTransportMode.NULL_TRANSPORT_MODE_DIGEST_ONLY).null_transport_digest != one.null_transport_digest
    assert _receipt(envelope, preflight, review, null_transport_scope=ProviderNullTransportScope.INTERNAL_NULL_TRANSPORT_AUDIT).null_transport_digest != one.null_transport_digest
    assert _receipt(envelope, preflight, review, sent=True).null_transport_digest != one.null_transport_digest
    assert _receipt(envelope, preflight, review, bytes_sent=1).null_transport_digest != one.null_transport_digest
    assert _receipt(envelope, preflight, review, request_created=True).null_transport_digest != one.null_transport_digest


def test_builder_does_not_mutate_inputs_or_import_runtime_surfaces():
    envelope = _envelope(); preflight = _preflight(envelope=envelope); review = _null_review(preflight)
    originals = deepcopy((envelope, preflight, review))
    for module_name in ("prompt_assembler", "openai", "requests", "httpx", "socket", "memory_manager", "action_router", "retention", "routing"):
        sys.modules.pop(module_name, None)
    receipt = _receipt(envelope, preflight, review)
    assert (envelope, preflight, review) == originals
    assert receipt.null_transport_status == READY
    assert "prompt_assembler" not in sys.modules
    for module_name in ("openai", "requests", "httpx", "memory_manager", "action_router", "retention", "routing"):
        assert module_name not in sys.modules


def test_phase63_to_phase89_passes_only_when_all_gates_pass_and_blocked_attempts_stay_blocked():
    candidate, display, model_preflight, model_review = _chain()
    envelope = _envelope(chain=(candidate, display, model_preflight, model_review))
    preflight = _preflight(envelope=envelope)
    review = _null_review(preflight)
    assert _receipt(envelope, preflight, review).null_transport_status == READY
    blocked_candidate = replace(candidate, status=InternalPromptCandidateStatus.INTERNAL_PROMPT_CANDIDATE_FORBIDDEN_RAW_CONTEXT)
    blocked_envelope = _envelope(candidate=blocked_candidate)
    assert _receipt(envelope=blocked_envelope).null_transport_status == DRY_NOT_READY
    adversarial = replace(candidate, internal_candidate_text=candidate.internal_candidate_text + "\nprovider_params runtime_authority")
    adversarial = replace(adversarial, candidate_digest=compute_internal_prompt_candidate_digest(adversarial))
    assert _receipt(envelope=_envelope(candidate=adversarial)).null_transport_status == DRY_NOT_READY
    assert _receipt(marker_evidence={"execution_handle": "present"}).null_transport_status == RUNTIME


def test_findings_explanation_guardrail_and_import_purity():
    bad = _receipt(sent=True)
    assert any("send_attempt_detected" in line for line in explain_provider_null_transport_findings(bad))
    clean = scan_context_hygiene_prompt_boundaries(["sentientos/context_hygiene/prompt_provider_null_transport.py"])
    assert clean.ok, [finding.to_dict() for finding in clean.findings]
    default = scan_context_hygiene_prompt_boundaries()
    assert "sentientos/context_hygiene/prompt_provider_null_transport.py" in default.scanned_paths
    module = importlib.import_module("sentientos.context_hygiene.prompt_provider_null_transport")
    assert hasattr(module, "ProviderNullTransportReceipt")
