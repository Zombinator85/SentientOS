from __future__ import annotations

from dataclasses import replace
import ast
from pathlib import Path

from scripts import verify_context_hygiene_prompt_boundaries as guardrails
from sentientos.context_hygiene.embodiment_context import build_embodiment_context_candidates
from sentientos.context_hygiene.prompt_provider_client_custody import (
    ProviderClientCustodyKind,
    ProviderClientCustodyPreflightStatus,
    ProviderClientCustodyStatus,
    build_provider_client_custody_manifest,
    compute_provider_client_custody_digest,
    compute_provider_client_custody_preflight_digest,
    evaluate_provider_client_custody_preflight,
    provider_client_custody_contains_no_clients,
    provider_client_custody_forbids_client_instantiation,
    provider_client_custody_forbids_sdk_import,
    provider_client_custody_forbids_session_creation,
    provider_client_custody_forbids_streaming,
    provider_client_custody_forbids_transport_creation,
    provider_client_custody_has_no_credentials,
    provider_client_custody_has_no_endpoints,
    provider_client_custody_has_no_network,
    provider_client_custody_has_no_runtime_authority,
    provider_client_preflight_denies_real_clients,
    provider_client_preflight_remains_metadata_only,
)
from sentientos.context_hygiene.prompt_provider_credential_custody import (
    build_provider_credential_custody_manifest,
    provider_credential_custody_contains_no_secrets,
)
from sentientos.context_hygiene.prompt_provider_endpoint_custody import (
    build_provider_endpoint_custody_manifest,
    evaluate_provider_endpoint_custody_preflight,
    provider_endpoint_custody_contains_no_endpoints,
)
from sentientos.context_hygiene.prompt_provider_transport_capability import (
    ProviderTransportCapabilityKind,
    build_provider_transport_capability_manifest,
    evaluate_provider_transport_registration_preflight,
)
from sentientos.context_hygiene.prompt_provider_transport_registry import (
    ProviderTransportRegistryStatus,
    build_provider_transport_registry_manifest,
    provider_transport_registry_is_null_only,
)
from sentientos.context_hygiene.selector import ContextCandidate, build_context_packet_from_candidates


MODULE_PATH = "sentientos/context_hygiene/prompt_provider_client_custody.py"


def _clean_manifest():
    return build_provider_client_custody_manifest()


def _clean_preflight(**kwargs):
    return evaluate_provider_client_custody_preflight(_clean_manifest(), **kwargs)


def _assert_denied(preflight):
    assert preflight.client_preflight_status != ProviderClientCustodyPreflightStatus.CLIENT_PREFLIGHT_NO_CLIENTS_ALLOWED
    assert not preflight.client_allowed
    assert preflight.findings


def test_default_no_client_custody_manifest_and_preflight_allow_only_metadata():
    manifest = _clean_manifest()
    assert manifest.client_status == ProviderClientCustodyStatus.CLIENT_CUSTODY_NO_CLIENTS
    assert manifest.client_custody_kind == ProviderClientCustodyKind.CLIENT_CUSTODY_NONE
    assert provider_client_custody_contains_no_clients(manifest)
    preflight = evaluate_provider_client_custody_preflight(manifest)
    assert preflight.client_preflight_status == ProviderClientCustodyPreflightStatus.CLIENT_PREFLIGHT_NO_CLIENTS_ALLOWED
    assert provider_client_preflight_remains_metadata_only(preflight)


def test_forbidden_and_unknown_client_custody_kinds_are_denied():
    forbidden = [
        ProviderClientCustodyKind.CLIENT_CUSTODY_PROVIDER_SDK_CLIENT_FORBIDDEN,
        ProviderClientCustodyKind.CLIENT_CUSTODY_HTTP_CLIENT_FORBIDDEN,
        ProviderClientCustodyKind.CLIENT_CUSTODY_SOCKET_CLIENT_FORBIDDEN,
        ProviderClientCustodyKind.CLIENT_CUSTODY_SESSION_FORBIDDEN,
        ProviderClientCustodyKind.CLIENT_CUSTODY_TRANSPORT_FORBIDDEN,
        ProviderClientCustodyKind.CLIENT_CUSTODY_STREAMING_CLIENT_FORBIDDEN,
        ProviderClientCustodyKind.CLIENT_CUSTODY_RETRY_EXECUTOR_FORBIDDEN,
        ProviderClientCustodyKind.CLIENT_CUSTODY_REQUEST_BUILDER_FORBIDDEN,
        ProviderClientCustodyKind.CLIENT_CUSTODY_PROVIDER_SPECIFIC_CLIENT_FORBIDDEN,
        ProviderClientCustodyKind.CLIENT_CUSTODY_UNKNOWN_FORBIDDEN,
        "made_up_client_kind",
    ]
    for kind in forbidden:
        manifest = build_provider_client_custody_manifest(client_custody_kind=kind)
        preflight = evaluate_provider_client_custody_preflight(manifest, requested_client_custody_kind=kind)
        assert manifest.client_status in {
            ProviderClientCustodyStatus.CLIENT_CUSTODY_FORBIDDEN_CLIENT_DETECTED,
            ProviderClientCustodyStatus.CLIENT_CUSTODY_INVALID,
        }
        _assert_denied(preflight)
        assert provider_client_preflight_denies_real_clients(preflight)


def test_client_like_provider_sdk_values_are_denied():
    for marker in ["openai.OpenAI", "AsyncOpenAI", "Anthropic", "boto3.client", "google.cloud", "azure.ai"]:
        manifest = build_provider_client_custody_manifest(declared_client_properties=[marker])
        preflight = evaluate_provider_client_custody_preflight(manifest)
        _assert_denied(preflight)
        assert manifest.client_status in {
            ProviderClientCustodyStatus.CLIENT_CUSTODY_SDK_IMPORT_DETECTED,
            ProviderClientCustodyStatus.CLIENT_CUSTODY_SESSION_DETECTED,
        }


def test_http_socket_stream_retry_request_endpoint_and_secret_markers_are_denied():
    markers = [
        "httpx.Client",
        "requests.Session",
        "aiohttp.ClientSession",
        "urllib3",
        "socket",
        "websocket",
        "stream",
        "stream=True",
        "retry",
        "executor",
        "request_builder",
        "endpoint=",
        "base_url",
        "api_key",
        "authorization",
        "bearer",
        "token=",
        "secret=",
        "https://",
        "http://",
        "provider client",
        "client=",
        "session=",
        "transport=",
        "completion client",
        "chat client",
        "model client",
    ]
    for marker in markers:
        manifest = build_provider_client_custody_manifest(metadata_evidence={"evidence": marker})
        _assert_denied(evaluate_provider_client_custody_preflight(manifest))


def test_requested_client_session_transport_and_access_flags_deny():
    flag_names = [
        "requested_client_instantiation",
        "requested_sdk_import",
        "requested_session_creation",
        "requested_transport_creation",
        "requested_stream_creation",
        "requested_request_builder",
        "requested_retry_executor",
        "requested_credential_material",
        "requested_endpoint_material",
        "requested_network_access",
    ]
    for name in flag_names:
        _assert_denied(_clean_preflight(**{name: True}))
    _assert_denied(
        _clean_preflight(
            requested_registration=True,
            requested_client_custody_kind=ProviderClientCustodyKind.CLIENT_CUSTODY_PROVIDER_SDK_CLIENT_FORBIDDEN,
        )
    )


def test_linked_phase91_phase92_and_phase93_artifacts_gate_client_preflight():
    manifest = _clean_manifest()
    real_capability = build_provider_transport_capability_manifest(
        adapter_kind=ProviderTransportCapabilityKind.TRANSPORT_CAPABILITY_HTTP,
        declared_capabilities=[ProviderTransportCapabilityKind.TRANSPORT_CAPABILITY_HTTP],
        http_capable=True,
    )
    _assert_denied(evaluate_provider_client_custody_preflight(manifest, capability_manifest=real_capability))

    secret_manifest = build_provider_credential_custody_manifest(secret_values_present=True)
    _assert_denied(evaluate_provider_client_custody_preflight(manifest, credential_custody_manifest=secret_manifest))

    endpoint_manifest = build_provider_endpoint_custody_manifest(endpoint_values_present=True)
    _assert_denied(evaluate_provider_client_custody_preflight(manifest, endpoint_custody_manifest=endpoint_manifest))

    no_secret = build_provider_credential_custody_manifest()
    no_endpoint = build_provider_endpoint_custody_manifest( linked_credential_custody_manifest=no_secret)
    no_endpoint_preflight = evaluate_provider_endpoint_custody_preflight(no_endpoint, credential_custody_manifest=no_secret)
    preflight = evaluate_provider_client_custody_preflight(
        manifest,
        credential_custody_manifest=no_secret,
        endpoint_custody_manifest=no_endpoint,
        endpoint_custody_preflight=no_endpoint_preflight,
    )
    assert preflight.client_preflight_status == ProviderClientCustodyPreflightStatus.CLIENT_PREFLIGHT_NO_CLIENTS_ALLOWED


def test_no_client_no_runtime_negation_flags_are_required():
    flag_names = [
        "no_client_material",
        "no_client_references",
        "no_client_instantiation",
        "no_sdk_import",
        "no_session_creation",
        "no_transport_creation",
        "no_stream_creation",
        "no_request_builder",
        "no_retry_executor",
        "no_credentials",
        "no_endpoints",
        "no_network",
        "no_provider_send",
        "no_provider_sdk",
        "no_http",
        "no_socket",
        "no_semantic_generation",
        "no_tools",
        "no_memory",
        "no_retention",
        "no_actions",
        "no_routing",
    ]
    for name in flag_names:
        _assert_denied(_clean_preflight(**{name: False}))


def test_raw_payload_runtime_handle_and_model_provider_param_markers_deny():
    for marker in ["raw_payload", "runtime_handle", "model_params", "provider_params", "llm_params"]:
        manifest = build_provider_client_custody_manifest(metadata_evidence={"evidence": marker})
        _assert_denied(evaluate_provider_client_custody_preflight(manifest))


def test_boolean_helper_contracts_for_clean_and_forbidden_cases():
    manifest = _clean_manifest()
    preflight = evaluate_provider_client_custody_preflight(manifest)
    bad = build_provider_client_custody_manifest(client_values_present=True)
    assert provider_client_custody_contains_no_clients(manifest)
    assert not provider_client_custody_contains_no_clients(bad)
    for subject in [manifest, preflight]:
        assert provider_client_custody_forbids_client_instantiation(subject)
        assert provider_client_custody_forbids_sdk_import(subject)
        assert provider_client_custody_forbids_session_creation(subject)
        assert provider_client_custody_forbids_transport_creation(subject)
        assert provider_client_custody_forbids_streaming(subject)
        assert provider_client_custody_has_no_network(subject)
        assert provider_client_custody_has_no_credentials(subject)
        assert provider_client_custody_has_no_endpoints(subject)
        assert provider_client_custody_has_no_runtime_authority(subject)
    assert provider_client_preflight_denies_real_clients(evaluate_provider_client_custody_preflight(bad))
    assert provider_client_preflight_remains_metadata_only(preflight)


def test_client_digest_is_deterministic_and_changes_for_kind_properties_and_flags():
    first = _clean_manifest()
    second = _clean_manifest()
    assert first.client_digest == second.client_digest == compute_provider_client_custody_digest(first)
    assert first.client_digest != build_provider_client_custody_manifest(
        client_custody_kind=ProviderClientCustodyKind.CLIENT_CUSTODY_NO_CLIENT_PLACEHOLDER
    ).client_digest
    assert first.client_digest != build_provider_client_custody_manifest(declared_client_properties=["metadata placeholder"]).client_digest
    assert first.client_digest != build_provider_client_custody_manifest(no_client_material=False).client_digest


def test_preflight_digest_is_deterministic_and_changes_for_links_requests_and_flags():
    manifest = _clean_manifest()
    first = evaluate_provider_client_custody_preflight(manifest)
    second = evaluate_provider_client_custody_preflight(manifest)
    assert first.client_preflight_digest == second.client_preflight_digest == compute_provider_client_custody_preflight_digest(first)
    linked_capability = replace(manifest, linked_capability_digest="sha256:changed")
    linked_credential = replace(manifest, linked_credential_custody_digest="sha256:changed")
    linked_endpoint = replace(manifest, linked_endpoint_custody_digest="sha256:changed")
    assert first.client_preflight_digest != evaluate_provider_client_custody_preflight(linked_capability).client_preflight_digest
    assert first.client_preflight_digest != evaluate_provider_client_custody_preflight(linked_credential).client_preflight_digest
    assert first.client_preflight_digest != evaluate_provider_client_custody_preflight(linked_endpoint).client_preflight_digest
    assert first.client_preflight_digest != evaluate_provider_client_custody_preflight(
        manifest, requested_client_custody_kind=ProviderClientCustodyKind.CLIENT_CUSTODY_NO_CLIENT_PLACEHOLDER
    ).client_preflight_digest
    assert first.client_preflight_digest != evaluate_provider_client_custody_preflight(manifest, requested_network_access=True).client_preflight_digest
    assert first.client_preflight_digest != evaluate_provider_client_custody_preflight(manifest, no_network=False).client_preflight_digest


def test_helper_does_not_mutate_linked_artifacts_or_registries():
    capability = build_provider_transport_capability_manifest()
    credential = build_provider_credential_custody_manifest(linked_capability_manifest=capability)
    endpoint = build_provider_endpoint_custody_manifest(linked_capability_manifest=capability, linked_credential_custody_manifest=credential)
    endpoint_preflight = evaluate_provider_endpoint_custody_preflight(endpoint, capability_manifest=capability, credential_custody_manifest=credential)
    before = (capability, credential, endpoint, endpoint_preflight)
    preflight = evaluate_provider_client_custody_preflight(
        _clean_manifest(), capability, credential, endpoint, endpoint_preflight
    )
    assert preflight.client_preflight_status == ProviderClientCustodyPreflightStatus.CLIENT_PREFLIGHT_NO_CLIENTS_ALLOWED
    assert before == (capability, credential, endpoint, endpoint_preflight)


def test_module_source_has_no_forbidden_runtime_calls_or_imports():
    source = Path(MODULE_PATH).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_imports = {"os", "socket", "requests", "httpx", "openai", "boto3", "aiohttp", "urllib3"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not (forbidden_imports & {alias.name.split(".")[0] for alias in node.names})
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in forbidden_imports
        if isinstance(node, ast.Call):
            name = ast.unparse(node.func)
            lowered = name.lower()
            assert "assemble_prompt" not in lowered
            assert not any(term in lowered for term in ["getenv", "retrieve_memory", "write_memory", "route_work", "admit_work"])


def test_phase90_91_92_93_invariants_hold_after_phase94_checks():
    registry = build_provider_transport_registry_manifest()
    assert registry.registry_status == ProviderTransportRegistryStatus.TRANSPORT_REGISTRY_NULL_ONLY
    assert provider_transport_registry_is_null_only(registry)
    capability = build_provider_transport_capability_manifest()
    real_registration = evaluate_provider_transport_registration_preflight(
        capability,
        registry_manifest=registry,
        requested_adapter_kind=ProviderTransportCapabilityKind.TRANSPORT_CAPABILITY_HTTP,
        requested_registration=True,
    )
    assert real_registration.registration_allowed is False
    credential = build_provider_credential_custody_manifest()
    endpoint = build_provider_endpoint_custody_manifest(linked_credential_custody_manifest=credential)
    evaluate_provider_client_custody_preflight(_clean_manifest(), capability, credential, endpoint)
    assert provider_credential_custody_contains_no_secrets(credential)
    assert provider_endpoint_custody_contains_no_endpoints(endpoint)
    assert provider_transport_registry_is_null_only(registry)


def test_phase63_and_phase62b_metadata_do_not_enable_client_custody():
    embodiment_candidates = build_embodiment_context_candidates(
        [{"artifact_id": "body-proposal", "summary": "safe metadata", "privacy_posture": "sanitized", "consent_status": "approved"}]
    )
    assert embodiment_candidates
    preflight = evaluate_provider_client_custody_preflight(_clean_manifest(), metadata_evidence={"phase63": embodiment_candidates[0].ref_id})
    assert provider_client_preflight_remains_metadata_only(preflight)

    blocked = ContextCandidate(
        ref_id="blocked-attempt",
        ref_type="memory",
        summary="openai.OpenAI attempted but blocked",
        truth_ingress_status="blocked",
        metadata={"attempted": "openai.OpenAI"},
    )
    packet = build_context_packet_from_candidates(
        [blocked], packet_scope="conversation", conversation_scope_id="c", task_scope_id="t"
    )
    assert packet.excluded_refs
    blocked_preflight = evaluate_provider_client_custody_preflight(_clean_manifest(), metadata_evidence=packet.excluded_refs[0].ref_id)
    assert provider_client_preflight_remains_metadata_only(blocked_preflight)
    denied = evaluate_provider_client_custody_preflight(_clean_manifest(), metadata_evidence=blocked.metadata)
    _assert_denied(denied)


def test_adversarial_markers_and_guardrail_scan_remain_blocked():
    for marker in ["provider client", "runtime_handle", "secret=", "endpoint=", "socket", "httpx.Client"]:
        _assert_denied(evaluate_provider_client_custody_preflight(_clean_manifest(), metadata_evidence=marker))
    report = guardrails.scan_context_hygiene_prompt_boundaries([MODULE_PATH])
    assert report.ok, guardrails.summarize_context_hygiene_prompt_boundary_scan(report)
    assert MODULE_PATH in report.scanned_paths
