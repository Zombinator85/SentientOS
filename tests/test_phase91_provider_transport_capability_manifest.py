from __future__ import annotations

from dataclasses import replace
import inspect

from sentientos.context_hygiene.prompt_provider_transport_capability import (
    ProviderTransportCapabilityKind as CK,
    ProviderTransportCapabilityStatus as CS,
    ProviderTransportRegistrationStatus as RS,
    build_provider_transport_capability_manifest,
    compute_provider_transport_capability_digest,
    compute_provider_transport_registration_preflight_digest,
    evaluate_provider_transport_registration_preflight,
    provider_transport_capability_forbids_real_transport,
    provider_transport_capability_has_no_credentials,
    provider_transport_capability_has_no_endpoint,
    provider_transport_capability_has_no_network,
    provider_transport_capability_has_no_provider_client,
    provider_transport_capability_has_no_runtime_authority,
    provider_transport_capability_is_null_only,
    provider_transport_registration_preflight_denies_real_transport,
    provider_transport_registration_remains_forbidden,
    summarize_provider_transport_registration_preflight,
    validate_provider_transport_capability_manifest,
)
from sentientos.context_hygiene.prompt_provider_transport_registry import (
    ProviderTransportAdapterKind as AK,
    build_provider_transport_registry_manifest,
    provider_transport_registry_is_null_only,
)
from scripts import verify_context_hygiene_prompt_boundaries as guardrails


NULL_ADAPTER = AK.PROVIDER_TRANSPORT_NULL_ADAPTER
LIVE_ADAPTER = AK.PROVIDER_TRANSPORT_OPENAI_LIVE_ADAPTER_FORBIDDEN
HTTP_ADAPTER = AK.PROVIDER_TRANSPORT_HTTP_ADAPTER_FORBIDDEN
SOCKET_ADAPTER = AK.PROVIDER_TRANSPORT_SOCKET_ADAPTER_FORBIDDEN
CUSTOM_ADAPTER = AK.PROVIDER_TRANSPORT_CUSTOM_ENDPOINT_ADAPTER_FORBIDDEN


def _manifest(**kwargs):
    return build_provider_transport_capability_manifest(**kwargs)


def _registry(**kwargs):
    return build_provider_transport_registry_manifest(**kwargs)


def _preflight(manifest=None, registry=None, **kwargs):
    return evaluate_provider_transport_registration_preflight(manifest or _manifest(), registry or _registry(), **kwargs)


def _codes(obj) -> set[str]:
    return {finding.code for finding in obj.findings}


def test_default_null_adapter_capability_manifest_is_null_only_and_valid():
    manifest = _manifest()
    assert manifest.capability_status == CS.TRANSPORT_CAPABILITY_NULL_ONLY
    assert manifest.null_only_compatible is True
    assert provider_transport_capability_is_null_only(manifest)
    assert validate_provider_transport_capability_manifest(manifest) == ()
    assert manifest.provider_transport_capability_manifest_only is True
    assert manifest.real_transport_registration_forbidden is True
    assert manifest.does_not_make_network_calls is True
    assert manifest.does_not_send_to_provider is True
    assert manifest.does_not_call_llm is True
    assert manifest.does_not_retrieve_memory is True
    assert manifest.does_not_write_memory is True


def test_forbidden_capability_kinds_map_to_specific_capability_statuses():
    cases = [
        (CK.TRANSPORT_CAPABILITY_LIVE_PROVIDER, CS.TRANSPORT_CAPABILITY_FORBIDDEN_REAL_TRANSPORT),
        (CK.TRANSPORT_CAPABILITY_NETWORK_EGRESS, CS.TRANSPORT_CAPABILITY_NETWORK_DETECTED),
        (CK.TRANSPORT_CAPABILITY_HTTP, CS.TRANSPORT_CAPABILITY_FORBIDDEN_REAL_TRANSPORT),
        (CK.TRANSPORT_CAPABILITY_SOCKET, CS.TRANSPORT_CAPABILITY_FORBIDDEN_REAL_TRANSPORT),
        (CK.TRANSPORT_CAPABILITY_PROVIDER_SDK, CS.TRANSPORT_CAPABILITY_FORBIDDEN_REAL_TRANSPORT),
        (CK.TRANSPORT_CAPABILITY_CREDENTIALED, CS.TRANSPORT_CAPABILITY_CREDENTIALS_DETECTED),
        (CK.TRANSPORT_CAPABILITY_ENDPOINT, CS.TRANSPORT_CAPABILITY_ENDPOINT_DETECTED),
        (CK.TRANSPORT_CAPABILITY_PROVIDER_CLIENT, CS.TRANSPORT_CAPABILITY_CLIENT_DETECTED),
        (CK.TRANSPORT_CAPABILITY_SEMANTIC_GENERATION, CS.TRANSPORT_CAPABILITY_FORBIDDEN_REAL_TRANSPORT),
        (CK.TRANSPORT_CAPABILITY_UNKNOWN_FORBIDDEN, CS.TRANSPORT_CAPABILITY_FORBIDDEN_REAL_TRANSPORT),
    ]
    for kind, status in cases:
        manifest = _manifest(declared_capabilities=(kind,))
        assert manifest.capability_status == status, kind
        assert provider_transport_capability_forbids_real_transport(manifest)
        assert not provider_transport_capability_is_null_only(manifest)


def test_tool_memory_action_retention_and_routing_capabilities_are_runtime_authority():
    for kind in (
        CK.TRANSPORT_CAPABILITY_TOOL_CALLING,
        CK.TRANSPORT_CAPABILITY_MEMORY_ACCESS,
        CK.TRANSPORT_CAPABILITY_ACTION_EXECUTION,
        CK.TRANSPORT_CAPABILITY_RETENTION_COMMIT,
        CK.TRANSPORT_CAPABILITY_ROUTING_EXECUTION,
    ):
        manifest = _manifest(declared_capabilities=(kind,))
        assert manifest.capability_status == CS.TRANSPORT_CAPABILITY_RUNTIME_AUTHORITY_DETECTED
        assert "forbidden_capability_declared" in _codes(manifest)


def test_missing_required_null_only_evidence_yields_incomplete():
    manifest = _manifest(has_null_only_evidence=False)
    assert manifest.capability_status == CS.TRANSPORT_CAPABILITY_INCOMPLETE
    assert manifest.missing_required_evidence == ("null_only_evidence",)


def test_capability_digest_is_deterministic_and_changes_for_adapter_capabilities_and_flags():
    one = _manifest()
    two = _manifest()
    assert one.capability_digest == two.capability_digest == compute_provider_transport_capability_digest(one)
    assert _manifest(adapter_kind=CK.TRANSPORT_CAPABILITY_LIVE_PROVIDER).capability_digest != one.capability_digest
    assert _manifest(declared_capabilities=(CK.TRANSPORT_CAPABILITY_HTTP,)).capability_digest != one.capability_digest
    assert _manifest(http_capable=True).capability_digest != one.capability_digest


def test_null_manifest_and_phase90_registry_yield_null_only_allowed_without_mutation():
    manifest = _manifest()
    registry = _registry()
    before_registry = registry
    before_manifest = manifest
    preflight = _preflight(manifest, registry)
    assert preflight.registration_status == RS.TRANSPORT_REGISTRATION_NULL_ONLY_ALLOWED
    assert preflight.registration_allowed is True
    assert preflight.selected_adapter_kind == NULL_ADAPTER
    assert preflight.real_transport_registration_allowed is False
    assert summarize_provider_transport_registration_preflight(preflight)["registration_status"] == RS.TRANSPORT_REGISTRATION_NULL_ONLY_ALLOWED
    assert registry == before_registry
    assert manifest == before_manifest
    assert registry.registered_adapter_kinds == (NULL_ADAPTER,)


def test_requested_registration_true_for_null_is_metadata_only_no_op_and_does_not_mutate_registry():
    registry = _registry()
    preflight = _preflight(registry=registry, requested_registration=True)
    assert preflight.registration_status == RS.TRANSPORT_REGISTRATION_NULL_ONLY_ALLOWED
    assert preflight.registration_allowed is True
    assert preflight.warnings == ("requested_registration_true_treated_as_null_only_no_op_metadata",)
    assert registry.registered_adapter_kinds == (NULL_ADAPTER,)


def test_requested_real_http_socket_custom_and_unknown_adapters_are_forbidden():
    for adapter in (LIVE_ADAPTER, HTTP_ADAPTER, SOCKET_ADAPTER, CUSTOM_ADAPTER, "provider_transport_mystery_adapter"):
        preflight = _preflight(requested_adapter_kind=adapter)
        assert preflight.registration_status == RS.TRANSPORT_REGISTRATION_FORBIDDEN_REAL_TRANSPORT
        assert provider_transport_registration_remains_forbidden(preflight)
        assert provider_transport_registration_preflight_denies_real_transport(preflight)
        assert "requested_adapter_forbidden" in _codes(preflight)


def test_invalid_or_forbidden_registry_denies_registration():
    invalid = _registry(registered_adapter_kinds=())
    assert _preflight(registry=invalid).registration_status == RS.TRANSPORT_REGISTRATION_DENIED
    forbidden = _registry(registered_adapter_kinds=(NULL_ADAPTER, LIVE_ADAPTER))
    assert _preflight(registry=forbidden).registration_status == RS.TRANSPORT_REGISTRATION_DENIED
    assert not provider_transport_registry_is_null_only(forbidden)


def test_requested_registration_true_for_real_transport_is_forbidden():
    preflight = _preflight(requested_adapter_kind=LIVE_ADAPTER, requested_registration=True)
    assert preflight.registration_status == RS.TRANSPORT_REGISTRATION_FORBIDDEN_REAL_TRANSPORT
    assert "requested_real_registration_forbidden" in _codes(preflight)


def test_capability_flags_block_with_specific_or_forbidden_statuses():
    cases = {
        "network_egress_capable": CS.TRANSPORT_CAPABILITY_NETWORK_DETECTED,
        "provider_send_capable": CS.TRANSPORT_CAPABILITY_NETWORK_DETECTED,
        "credentials_capable": CS.TRANSPORT_CAPABILITY_CREDENTIALS_DETECTED,
        "endpoint_capable": CS.TRANSPORT_CAPABILITY_ENDPOINT_DETECTED,
        "provider_client_capable": CS.TRANSPORT_CAPABILITY_CLIENT_DETECTED,
        "socket_capable": CS.TRANSPORT_CAPABILITY_FORBIDDEN_REAL_TRANSPORT,
        "http_capable": CS.TRANSPORT_CAPABILITY_FORBIDDEN_REAL_TRANSPORT,
        "provider_sdk_capable": CS.TRANSPORT_CAPABILITY_FORBIDDEN_REAL_TRANSPORT,
        "semantic_generation_capable": CS.TRANSPORT_CAPABILITY_FORBIDDEN_REAL_TRANSPORT,
        "tool_calling_capable": CS.TRANSPORT_CAPABILITY_RUNTIME_AUTHORITY_DETECTED,
        "memory_access_capable": CS.TRANSPORT_CAPABILITY_RUNTIME_AUTHORITY_DETECTED,
        "retention_capable": CS.TRANSPORT_CAPABILITY_RUNTIME_AUTHORITY_DETECTED,
        "action_execution_capable": CS.TRANSPORT_CAPABILITY_RUNTIME_AUTHORITY_DETECTED,
        "routing_capable": CS.TRANSPORT_CAPABILITY_RUNTIME_AUTHORITY_DETECTED,
    }
    for flag, status in cases.items():
        manifest = _manifest(**{flag: True})
        assert manifest.capability_status == status, flag
        assert not provider_transport_capability_is_null_only(manifest)


def test_no_runtime_and_no_network_preflight_flags_block():
    cases = {
        "no_network": RS.TRANSPORT_REGISTRATION_NETWORK_DETECTED,
        "no_provider_send": RS.TRANSPORT_REGISTRATION_NETWORK_DETECTED,
        "no_credentials": RS.TRANSPORT_REGISTRATION_CREDENTIALS_DETECTED,
        "no_endpoint": RS.TRANSPORT_REGISTRATION_ENDPOINT_DETECTED,
        "no_provider_client": RS.TRANSPORT_REGISTRATION_CLIENT_DETECTED,
        "no_http": RS.TRANSPORT_REGISTRATION_FORBIDDEN_REAL_TRANSPORT,
        "no_socket": RS.TRANSPORT_REGISTRATION_FORBIDDEN_REAL_TRANSPORT,
        "no_provider_sdk": RS.TRANSPORT_REGISTRATION_FORBIDDEN_REAL_TRANSPORT,
        "no_semantic_generation": RS.TRANSPORT_REGISTRATION_FORBIDDEN_REAL_TRANSPORT,
        "no_tools": RS.TRANSPORT_REGISTRATION_RUNTIME_AUTHORITY_DETECTED,
        "no_memory": RS.TRANSPORT_REGISTRATION_RUNTIME_AUTHORITY_DETECTED,
        "no_retention": RS.TRANSPORT_REGISTRATION_RUNTIME_AUTHORITY_DETECTED,
        "no_actions": RS.TRANSPORT_REGISTRATION_RUNTIME_AUTHORITY_DETECTED,
        "no_routing": RS.TRANSPORT_REGISTRATION_RUNTIME_AUTHORITY_DETECTED,
        "no_raw_payload_marker": RS.TRANSPORT_REGISTRATION_RUNTIME_AUTHORITY_DETECTED,
        "no_runtime_handle_marker": RS.TRANSPORT_REGISTRATION_RUNTIME_AUTHORITY_DETECTED,
        "no_provider_model_params": RS.TRANSPORT_REGISTRATION_RUNTIME_AUTHORITY_DETECTED,
    }
    for flag, status in cases.items():
        preflight = _preflight(**{flag: False})
        assert preflight.registration_status == status, flag
        assert not preflight.registration_allowed


def test_marker_evidence_for_raw_payload_runtime_handle_and_model_params_blocks():
    for evidence in ({"raw_payload": "x"}, {"runtime_handle": "x"}, {"model_params": {"temperature": 1}}):
        preflight = _preflight(marker_evidence=evidence)
        assert preflight.registration_status == RS.TRANSPORT_REGISTRATION_RUNTIME_AUTHORITY_DETECTED
        assert "runtime_marker_detected" in _codes(preflight)


def test_helper_predicates_only_pass_for_clean_null_manifest():
    clean = _manifest()
    dirty = _manifest(network_egress_capable=True)
    assert provider_transport_capability_is_null_only(clean)
    assert not provider_transport_capability_is_null_only(dirty)
    assert provider_transport_capability_forbids_real_transport(dirty)
    assert provider_transport_capability_has_no_network(clean)
    assert provider_transport_capability_has_no_credentials(clean)
    assert provider_transport_capability_has_no_endpoint(clean)
    assert provider_transport_capability_has_no_provider_client(clean)
    assert provider_transport_capability_has_no_runtime_authority(clean)


def test_registration_preflight_digest_is_deterministic_and_changes_for_inputs():
    manifest = _manifest()
    registry = _registry()
    one = _preflight(manifest, registry)
    two = _preflight(manifest, registry)
    assert one.registration_preflight_digest == two.registration_preflight_digest == compute_provider_transport_registration_preflight_digest(one)
    changed_capability = _preflight(_manifest(http_capable=True), registry)
    assert changed_capability.registration_preflight_digest != one.registration_preflight_digest
    changed_registry = _preflight(manifest, _registry(marker_overrides={"does_not_send_to_provider": False}))
    assert changed_registry.registration_preflight_digest != one.registration_preflight_digest
    changed_adapter = _preflight(manifest, registry, requested_adapter_kind=HTTP_ADAPTER)
    assert changed_adapter.registration_preflight_digest != one.registration_preflight_digest
    changed_registration = _preflight(manifest, registry, requested_registration=True)
    assert changed_registration.registration_preflight_digest != one.registration_preflight_digest
    changed_no_flag = _preflight(manifest, registry, no_memory=False)
    assert changed_no_flag.registration_preflight_digest != one.registration_preflight_digest


def test_helper_does_not_mutate_capability_manifest_or_registry():
    manifest = _manifest()
    registry = _registry()
    manifest_digest = manifest.capability_digest
    registry_digest = registry.registry_digest
    _preflight(manifest, registry, requested_adapter_kind=HTTP_ADAPTER, no_memory=False)
    assert manifest.capability_digest == manifest_digest
    assert registry.registry_digest == registry_digest
    assert registry.registered_adapter_kinds == (NULL_ADAPTER,)


def test_phase91_module_does_not_call_forbidden_runtime_functions():
    import sentientos.context_hygiene.prompt_provider_transport_capability as module

    source = inspect.getsource(module)
    forbidden = (
        "assemble_prompt(",
        "retrieve_memory(",
        "write_memory(",
        "commit_retention(",
        "execute_action(",
        "route_work(",
        "admit_work(",
        "openai.",
        "requests.",
        "httpx.",
        "socket.",
    )
    for token in forbidden:
        assert token not in source


def test_phase90_registry_remains_null_only_after_phase91_checks():
    registry = _registry()
    for adapter in (NULL_ADAPTER, LIVE_ADAPTER, HTTP_ADAPTER, SOCKET_ADAPTER):
        _preflight(registry=registry, requested_adapter_kind=adapter)
    assert registry.registered_adapter_kinds == (NULL_ADAPTER,)
    assert provider_transport_registry_is_null_only(registry)


def test_upstream_blocked_or_adversarial_metadata_does_not_enable_real_transport_capability():
    blocked_manifest = _manifest(declared_capabilities=(CK.TRANSPORT_CAPABILITY_NULL_ADAPTER,), has_null_only_evidence=False)
    assert blocked_manifest.capability_status == CS.TRANSPORT_CAPABILITY_INCOMPLETE
    preflight = _preflight(blocked_manifest)
    assert preflight.registration_status == RS.TRANSPORT_REGISTRATION_INCOMPLETE_EVIDENCE
    adversarial = _preflight(marker_evidence={"attempted_candidate": {"endpoint_url": "blocked", "provider_client_handle": "blocked"}})
    assert adversarial.registration_status == RS.TRANSPORT_REGISTRATION_RUNTIME_AUTHORITY_DETECTED
    assert not adversarial.registration_allowed


def test_guardrail_scans_new_module_and_finds_no_violations():
    report = guardrails.scan_context_hygiene_prompt_boundaries(["sentientos/context_hygiene/prompt_provider_transport_capability.py"])
    assert report.ok, guardrails.summarize_context_hygiene_prompt_boundary_scan(report)
    assert "sentientos/context_hygiene/prompt_provider_transport_capability.py" in report.scanned_paths
