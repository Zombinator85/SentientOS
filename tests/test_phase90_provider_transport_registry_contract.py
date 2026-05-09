"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import importlib
import sys
import types
from pathlib import Path
from unittest.mock import patch

# Keep privilege imports side-effect-safe under the repo's test ritual.
tts_stub = types.ModuleType("tts_bridge")
tts_stub.speak = lambda *args, **kwargs: None
sys.modules.setdefault("tts_bridge", tts_stub)

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from sentientos.context_hygiene.prompt_internal_candidate import InternalPromptCandidateStatus, compute_internal_prompt_candidate_digest
from sentientos.context_hygiene.prompt_provider_null_transport import ProviderNullTransportStatus, compute_provider_null_transport_digest
from sentientos.context_hygiene.prompt_provider_transport_registry import (
    ProviderTransportAdapterKind,
    ProviderTransportRegistryStatus,
    ProviderTransportSelectionStatus,
    build_provider_transport_registry_manifest,
    compute_provider_transport_registry_digest,
    compute_provider_transport_selection_digest,
    explain_provider_transport_registry_findings,
    provider_transport_registry_digest_chain_complete,
    provider_transport_registry_is_null_only,
    provider_transport_selection_has_no_credentials,
    provider_transport_selection_has_no_endpoint,
    provider_transport_selection_has_no_network,
    provider_transport_selection_has_no_provider_client,
    provider_transport_selection_has_no_runtime_authority,
    provider_transport_selection_sent_nothing,
    provider_transport_selection_uses_null_transport_only,
    select_provider_transport_adapter,
    summarize_provider_transport_selection_receipt,
    validate_provider_transport_selection_receipt,
)
from scripts.verify_context_hygiene_prompt_boundaries import scan_context_hygiene_prompt_boundaries
from tests.test_phase84_provider_dry_run_request_envelope import _chain, _envelope
from tests.test_phase87_provider_simulation_network_egress_preflight import _preflight
from tests.test_phase88_provider_network_egress_review_receipt import _receipt as _network_review
from tests.test_phase89_provider_null_transport_adapter_contract import _null_review, _receipt as _null_receipt

REPO_ROOT = Path(__file__).resolve().parents[1]
NULL = ProviderTransportAdapterKind.PROVIDER_TRANSPORT_NULL_ADAPTER
LIVE = ProviderTransportAdapterKind.PROVIDER_TRANSPORT_OPENAI_LIVE_ADAPTER_FORBIDDEN
HTTP = ProviderTransportAdapterKind.PROVIDER_TRANSPORT_HTTP_ADAPTER_FORBIDDEN
SOCKET = ProviderTransportAdapterKind.PROVIDER_TRANSPORT_SOCKET_ADAPTER_FORBIDDEN
CUSTOM = ProviderTransportAdapterKind.PROVIDER_TRANSPORT_CUSTOM_ENDPOINT_ADAPTER_FORBIDDEN
READY = ProviderTransportSelectionStatus.TRANSPORT_SELECTION_NULL_READY
WARN = ProviderTransportSelectionStatus.TRANSPORT_SELECTION_NULL_READY_WITH_WARNINGS
FORBIDDEN = ProviderTransportSelectionStatus.TRANSPORT_SELECTION_ADAPTER_FORBIDDEN
UNREGISTERED = ProviderTransportSelectionStatus.TRANSPORT_SELECTION_ADAPTER_UNREGISTERED
INVALID = ProviderTransportSelectionStatus.TRANSPORT_SELECTION_INVALID_INPUT
NOT_READY = ProviderTransportSelectionStatus.TRANSPORT_SELECTION_NULL_TRANSPORT_NOT_READY
SEND = ProviderTransportSelectionStatus.TRANSPORT_SELECTION_SEND_ATTEMPT_DETECTED
NETWORK = ProviderTransportSelectionStatus.TRANSPORT_SELECTION_NETWORK_DETECTED
CREDS = ProviderTransportSelectionStatus.TRANSPORT_SELECTION_CREDENTIALS_DETECTED
ENDPOINT = ProviderTransportSelectionStatus.TRANSPORT_SELECTION_ENDPOINT_DETECTED
CLIENT = ProviderTransportSelectionStatus.TRANSPORT_SELECTION_CLIENT_DETECTED
RUNTIME = ProviderTransportSelectionStatus.TRANSPORT_SELECTION_RUNTIME_AUTHORITY_DETECTED


def _registry(**overrides):
    return build_provider_transport_registry_manifest(**overrides)


_MISSING = object()


def _selection(registry=None, null_transport=_MISSING, requested=NULL, **overrides):
    registry = registry if registry is not None else _registry()
    null_transport = _null_receipt() if null_transport is _MISSING else null_transport
    return select_provider_transport_adapter(registry, requested, null_transport, **overrides)


def _codes(subject):
    return {finding.code for finding in subject.findings}


def test_default_registry_is_null_only_and_registers_only_null_adapter():
    registry = _registry()
    assert registry.registry_status == ProviderTransportRegistryStatus.TRANSPORT_REGISTRY_NULL_ONLY
    assert registry.registered_adapter_kinds == (NULL,)
    assert registry.default_adapter_kind == NULL
    assert provider_transport_registry_is_null_only(registry)
    assert registry.provider_transport_registry_only and registry.null_transport_only
    assert registry.does_not_make_network_calls and registry.does_not_send_to_provider and registry.does_not_call_llm


def test_registry_with_live_http_socket_credentialed_endpoint_custom_adapters_is_forbidden():
    cases = [
        ({"registered_adapter_kinds": (NULL, LIVE)}, ProviderTransportRegistryStatus.TRANSPORT_REGISTRY_FORBIDDEN_ADAPTER_REGISTERED),
        ({"registered_adapter_kinds": (NULL, HTTP), "http_adapters_registered": True}, ProviderTransportRegistryStatus.TRANSPORT_REGISTRY_RUNTIME_AUTHORITY_DETECTED),
        ({"registered_adapter_kinds": (NULL, SOCKET), "socket_adapters_registered": True}, ProviderTransportRegistryStatus.TRANSPORT_REGISTRY_RUNTIME_AUTHORITY_DETECTED),
        ({"registered_adapter_kinds": (NULL, CUSTOM), "credentialed_adapters_registered": True, "endpoint_adapters_registered": True}, ProviderTransportRegistryStatus.TRANSPORT_REGISTRY_RUNTIME_AUTHORITY_DETECTED),
    ]
    for kwargs, status in cases:
        registry = _registry(**kwargs)
        assert registry.registry_status == status
        assert not provider_transport_registry_is_null_only(registry)
        assert "forbidden_adapter_registered" in _codes(registry)


def test_registry_digest_is_deterministic_and_changes_when_adapter_set_changes():
    one = _registry()
    two = _registry()
    assert one.registry_digest == two.registry_digest == compute_provider_transport_registry_digest(one)
    changed = _registry(registered_adapter_kinds=(NULL, LIVE))
    assert changed.registry_digest != one.registry_digest


def test_selecting_clean_null_adapter_yields_null_ready_and_summary():
    receipt = _selection()
    assert receipt.selection_status == READY
    assert receipt.selected_adapter_kind == NULL
    assert validate_provider_transport_selection_receipt(receipt) == ()
    assert summarize_provider_transport_selection_receipt(receipt)["selection_status"] == READY
    assert provider_transport_registry_digest_chain_complete(receipt)


def test_ready_with_warnings_null_transport_yields_ready_with_warnings():
    envelope = _envelope(chain=_chain(warnings=True))
    receipt = _selection(null_transport=_null_receipt(envelope=envelope))
    assert receipt.selection_status == WARN
    assert receipt.warnings
    assert provider_transport_selection_uses_null_transport_only(receipt)


def test_requesting_live_http_socket_or_unknown_adapter_blocks():
    for adapter in (LIVE, HTTP, SOCKET, CUSTOM):
        receipt = _selection(requested=adapter)
        assert receipt.selection_status == FORBIDDEN
        assert "requested_adapter_forbidden" in _codes(receipt)
    unknown = _selection(requested="provider_transport_mystery_adapter")
    assert unknown.selection_status == UNREGISTERED
    assert "requested_adapter_unregistered" in _codes(unknown)


def test_invalid_or_forbidden_registry_blocks():
    invalid = _registry(registered_adapter_kinds=())
    assert _selection(registry=invalid).selection_status == INVALID
    forbidden = _registry(registered_adapter_kinds=(NULL, LIVE))
    assert _selection(registry=forbidden).selection_status == INVALID


def test_missing_blocked_and_mismatched_null_transport_blocks():
    assert _selection(null_transport=None).selection_status == NOT_READY
    blocked = replace(_null_receipt(), null_transport_status=ProviderNullTransportStatus.NULL_TRANSPORT_BLOCKED)
    blocked = replace(blocked, null_transport_digest=compute_provider_null_transport_digest(blocked))
    assert _selection(null_transport=blocked).selection_status == NOT_READY
    clean = _null_receipt()
    mismatch = replace(clean, null_transport_digest="sha256:mismatch")
    assert _selection(null_transport=mismatch).selection_status == INVALID
    expected = _selection(null_transport=clean, expected_null_transport_digest="sha256:mismatch")
    assert expected.selection_status == INVALID
    assert "digest_chain_mismatch" in _codes(expected)


def test_null_transport_send_network_credential_endpoint_client_socket_http_runtime_markers_block():
    cases = {
        "sent": SEND,
        "bytes_sent": SEND,
        "network_egress_attempted": NETWORK,
        "credentials_used": CREDS,
        "endpoint_used": ENDPOINT,
        "provider_client_used": CLIENT,
        "socket_opened": NETWORK,
        "http_request_attempted": NETWORK,
        "memory_access_attempted": RUNTIME,
    }
    for field_name, expected_status in cases.items():
        value = 1 if field_name == "bytes_sent" else True
        receipt = _selection(null_transport=_null_receipt(**{field_name: value}))
        assert receipt.selection_status == expected_status, field_name


def test_digest_chain_incomplete_and_mismatch_block_or_record_findings():
    clean = _null_receipt()
    missing = replace(clean, dry_run_digest="", null_transport_digest="")
    missing = replace(missing, null_transport_digest=compute_provider_null_transport_digest(missing))
    receipt = _selection(null_transport=missing)
    assert receipt.selection_status == INVALID
    assert "digest_chain_incomplete" in _codes(receipt)
    mismatch_registry = replace(_registry(), registry_digest="sha256:mismatch")
    mismatch = _selection(registry=mismatch_registry)
    assert mismatch.selection_status == INVALID
    assert "digest_chain_mismatch" in _codes(mismatch)


def test_selection_input_attempt_flags_and_markers_block_with_specific_statuses():
    cases = {
        "sent": SEND,
        "bytes_sent": SEND,
        "network_egress_attempted": NETWORK,
        "provider_send_attempted": SEND,
        "credentials_used": CREDS,
        "endpoint_used": ENDPOINT,
        "provider_client_used": CLIENT,
        "socket_opened": NETWORK,
        "http_request_attempted": NETWORK,
        "llm_call_attempted": RUNTIME,
        "semantic_generation_attempted": RUNTIME,
        "tool_calls_attempted": RUNTIME,
        "memory_access_attempted": RUNTIME,
        "retention_attempted": RUNTIME,
        "action_execution_attempted": RUNTIME,
        "routing_attempted": RUNTIME,
        "no_raw_payload_marker": RUNTIME,
        "no_runtime_handle_marker": RUNTIME,
        "no_provider_model_params": RUNTIME,
    }
    for field_name, expected_status in cases.items():
        value = 1 if field_name == "bytes_sent" else False if field_name.startswith("no_") else True
        assert _selection(**{field_name: value}).selection_status == expected_status, field_name
    assert _selection(marker_evidence={"runtime_handle": "present"}).selection_status == RUNTIME


def test_no_runtime_input_flags_false_block():
    cases = {
        "no_network": NETWORK,
        "no_provider_send": SEND,
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
    for field_name, expected_status in cases.items():
        assert _selection(**{field_name: False}).selection_status == expected_status, field_name


def test_null_only_helpers_are_strict_for_clean_and_dirty_receipts():
    registry = _registry()
    selection = _selection(registry=registry)
    assert provider_transport_registry_is_null_only(registry)
    assert provider_transport_selection_uses_null_transport_only(selection)
    assert provider_transport_selection_sent_nothing(selection)
    assert provider_transport_selection_has_no_network(selection)
    assert provider_transport_selection_has_no_credentials(selection)
    assert provider_transport_selection_has_no_endpoint(selection)
    assert provider_transport_selection_has_no_provider_client(selection)
    assert provider_transport_selection_has_no_runtime_authority(selection)
    assert not provider_transport_registry_is_null_only(_registry(live_provider_adapters_registered=True))
    assert not provider_transport_selection_uses_null_transport_only(_selection(requested=LIVE))
    assert not provider_transport_selection_sent_nothing(_selection(sent=True))
    assert not provider_transport_selection_has_no_network(_selection(socket_opened=True))
    assert not provider_transport_selection_has_no_credentials(_selection(credentials_used=True))
    assert not provider_transport_selection_has_no_endpoint(_selection(endpoint_used=True))
    assert not provider_transport_selection_has_no_provider_client(_selection(provider_client_used=True))
    assert not provider_transport_selection_has_no_runtime_authority(_selection(memory_access_attempted=True))


def test_selection_digest_is_deterministic_and_changes_for_required_fields():
    clean = _selection()
    assert clean.selection_digest == _selection().selection_digest == compute_provider_transport_selection_digest(clean)
    changed_registry = _registry(marker_overrides={"does_not_call_llm": False})
    assert _selection(registry=changed_registry).selection_digest != clean.selection_digest
    assert _selection(requested=LIVE).selection_digest != clean.selection_digest
    changed_null = replace(_null_receipt(), transport_reason="changed reason")
    changed_null = replace(changed_null, null_transport_digest=compute_provider_null_transport_digest(changed_null))
    assert _selection(null_transport=changed_null).selection_digest != clean.selection_digest
    assert _selection(sent=True).selection_digest != clean.selection_digest
    assert _selection(bytes_sent=1).selection_digest != clean.selection_digest
    assert _selection(socket_opened=True).selection_digest != clean.selection_digest
    assert _selection(http_request_attempted=True).selection_digest != clean.selection_digest


def test_helper_does_not_mutate_inputs_or_import_runtime_surfaces_or_call_forbidden_functions():
    registry = _registry()
    null_transport = _null_receipt()
    originals = deepcopy((registry, null_transport))
    for module_name in ("prompt_assembler", "openai", "requests", "httpx", "socket", "memory_manager", "action_router", "retention", "routing"):
        sys.modules.pop(module_name, None)
    with patch("sentientos.context_hygiene.prompt_provider_transport_registry.compute_provider_transport_selection_digest", wraps=compute_provider_transport_selection_digest) as digest_mock:
        receipt = _selection(registry=registry, null_transport=null_transport)
    assert (registry, null_transport) == originals
    assert receipt.selection_status == READY
    assert digest_mock.called
    assert "prompt_assembler" not in sys.modules
    for module_name in ("openai", "requests", "httpx", "memory_manager", "action_router", "retention", "routing"):
        assert module_name not in sys.modules


def test_phase63_to_phase90_passes_only_when_all_gates_pass_and_blocked_attempts_stay_blocked():
    candidate, display, model_preflight, model_review = _chain()
    envelope = _envelope(chain=(candidate, display, model_preflight, model_review))
    preflight = _preflight(envelope=envelope)
    review = _null_review(preflight)
    null_transport = _null_receipt(envelope, preflight, review)
    assert _selection(null_transport=null_transport).selection_status == READY
    blocked_candidate = replace(candidate, status=InternalPromptCandidateStatus.INTERNAL_PROMPT_CANDIDATE_FORBIDDEN_RAW_CONTEXT)
    blocked_envelope = _envelope(candidate=blocked_candidate)
    assert _selection(null_transport=_null_receipt(envelope=blocked_envelope)).selection_status == NOT_READY
    adversarial = replace(candidate, internal_candidate_text=candidate.internal_candidate_text + "\nprovider_params runtime_handle")
    adversarial = replace(adversarial, candidate_digest=compute_internal_prompt_candidate_digest(adversarial))
    assert _selection(null_transport=_null_receipt(envelope=_envelope(candidate=adversarial))).selection_status == NOT_READY
    assert _selection(marker_evidence={"provider_params": {"runtime_handle": "present"}}).selection_status == RUNTIME


def test_guardrail_scans_new_module_and_import_purity_remains_acceptable():
    bad = _selection(sent=True)
    assert any("send_attempt_detected" in line for line in explain_provider_transport_registry_findings(bad))
    clean = scan_context_hygiene_prompt_boundaries(["sentientos/context_hygiene/prompt_provider_transport_registry.py"])
    assert clean.ok, [finding.to_dict() for finding in clean.findings]
    default = scan_context_hygiene_prompt_boundaries()
    assert "sentientos/context_hygiene/prompt_provider_transport_registry.py" in default.scanned_paths
    module = importlib.import_module("sentientos.context_hygiene.prompt_provider_transport_registry")
    assert hasattr(module, "ProviderTransportSelectionReceipt")
