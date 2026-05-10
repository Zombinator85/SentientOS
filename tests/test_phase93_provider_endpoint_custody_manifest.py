from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

from sentientos.context_hygiene.embodiment_context import build_embodiment_context_candidates
from sentientos.context_hygiene.prompt_provider_credential_custody import (
    ProviderCredentialCustodyKind as CK,
    build_provider_credential_custody_manifest,
    evaluate_provider_credential_custody_preflight,
    provider_credential_custody_contains_no_secrets,
)
from sentientos.context_hygiene.prompt_provider_endpoint_custody import (
    ProviderEndpointCustodyKind as EK,
    ProviderEndpointCustodyPreflightStatus as PS,
    ProviderEndpointCustodyStatus as ES,
    build_provider_endpoint_custody_manifest,
    compute_provider_endpoint_custody_digest,
    compute_provider_endpoint_custody_preflight_digest,
    evaluate_provider_endpoint_custody_preflight,
    provider_endpoint_custody_contains_no_endpoints,
    provider_endpoint_custody_forbids_config_store_access,
    provider_endpoint_custody_forbids_dns_resolution,
    provider_endpoint_custody_forbids_endpoint_resolution,
    provider_endpoint_custody_forbids_env_access,
    provider_endpoint_custody_forbids_file_access,
    provider_endpoint_custody_has_no_credentials,
    provider_endpoint_custody_has_no_network,
    provider_endpoint_custody_has_no_provider_client,
    provider_endpoint_custody_has_no_runtime_authority,
    provider_endpoint_preflight_denies_real_endpoints,
    provider_endpoint_preflight_remains_metadata_only,
)
from sentientos.context_hygiene.prompt_provider_transport_capability import (
    ProviderTransportCapabilityKind as TK,
    build_provider_transport_capability_manifest,
    evaluate_provider_transport_registration_preflight,
    provider_transport_registration_preflight_denies_real_transport,
)
from sentientos.context_hygiene.prompt_provider_transport_registry import (
    ProviderTransportAdapterKind as AK,
    build_provider_transport_registry_manifest,
    provider_transport_registry_is_null_only,
)
from scripts import verify_context_hygiene_prompt_boundaries as guardrails

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "sentientos/context_hygiene/prompt_provider_endpoint_custody.py"


def _manifest(**kwargs):
    return build_provider_endpoint_custody_manifest(**kwargs)


def _preflight(manifest=None, capability=None, credential=None, credential_preflight=None, **kwargs):
    return evaluate_provider_endpoint_custody_preflight(manifest or _manifest(), capability, credential, credential_preflight, **kwargs)


def _capability(**kwargs):
    return build_provider_transport_capability_manifest(**kwargs)


def _credential(**kwargs):
    return build_provider_credential_custody_manifest(**kwargs)


def _credential_preflight(credential=None, **kwargs):
    return evaluate_provider_credential_custody_preflight(credential or _credential(), **kwargs)


def test_default_no_endpoint_manifest_and_preflight_are_allowed_metadata_only():
    manifest = _manifest()
    preflight = _preflight(manifest)
    assert manifest.endpoint_status == ES.ENDPOINT_CUSTODY_NO_ENDPOINTS
    assert manifest.endpoint_custody_kind == EK.ENDPOINT_CUSTODY_NONE
    assert manifest.provider_endpoint_custody_manifest_only is True
    assert manifest.no_endpoint_material is True
    assert manifest.endpoint_values_present is False
    assert manifest.endpoint_references_present is False
    assert preflight.endpoint_preflight_status == PS.ENDPOINT_PREFLIGHT_NO_ENDPOINTS_ALLOWED
    assert preflight.endpoint_allowed is True
    assert provider_endpoint_preflight_remains_metadata_only(preflight)


def test_forbidden_endpoint_custody_kinds_are_denied():
    cases = [
        EK.ENDPOINT_CUSTODY_INLINE_URL_FORBIDDEN,
        EK.ENDPOINT_CUSTODY_ENV_ENDPOINT_FORBIDDEN,
        EK.ENDPOINT_CUSTODY_FILE_ENDPOINT_FORBIDDEN,
        EK.ENDPOINT_CUSTODY_CONFIG_STORE_ENDPOINT_FORBIDDEN,
        EK.ENDPOINT_CUSTODY_DNS_NAME_FORBIDDEN,
        EK.ENDPOINT_CUSTODY_IP_ADDRESS_FORBIDDEN,
        EK.ENDPOINT_CUSTODY_PROVIDER_CLIENT_ENDPOINT_FORBIDDEN,
        EK.ENDPOINT_CUSTODY_UNKNOWN_FORBIDDEN,
        "endpoint_custody_mystery",
    ]
    for kind in cases:
        manifest = _manifest(endpoint_custody_kind=kind)
        preflight = _preflight(manifest, requested_endpoint_custody_kind=kind)
        assert manifest.endpoint_status in {ES.ENDPOINT_CUSTODY_FORBIDDEN_ENDPOINT_DETECTED, ES.ENDPOINT_CUSTODY_INVALID}
        assert preflight.endpoint_preflight_status in {PS.ENDPOINT_PREFLIGHT_FORBIDDEN_ENDPOINT_DETECTED, PS.ENDPOINT_PREFLIGHT_INVALID_INPUT}
        assert provider_endpoint_preflight_denies_real_endpoints(preflight)


def test_endpoint_like_metadata_patterns_are_denied():
    cases = [
        ("https://redacted.invalid", PS.ENDPOINT_PREFLIGHT_FORBIDDEN_ENDPOINT_DETECTED),
        ("http://redacted.invalid", PS.ENDPOINT_PREFLIGHT_FORBIDDEN_ENDPOINT_DETECTED),
        ("localhost 127.0.0.1 0.0.0.0 ::1", PS.ENDPOINT_PREFLIGHT_FORBIDDEN_ENDPOINT_DETECTED),
        ("host=redacted hostname redacted port=443", PS.ENDPOINT_PREFLIGHT_FORBIDDEN_ENDPOINT_DETECTED),
        ("dns:provider resolve name", PS.ENDPOINT_PREFLIGHT_DNS_RESOLUTION_DETECTED),
        ("socket connect request session client", {PS.ENDPOINT_PREFLIGHT_NETWORK_DETECTED, PS.ENDPOINT_PREFLIGHT_CLIENT_DETECTED}),
        ("openai.com anthropic.com azure.com googleapis.com", PS.ENDPOINT_PREFLIGHT_FORBIDDEN_ENDPOINT_DETECTED),
        ("authorization bearer token=redacted secret=redacted api key", PS.ENDPOINT_PREFLIGHT_CREDENTIALS_DETECTED),
        ("/etc/hosts .env ~/.config config:path", {PS.ENDPOINT_PREFLIGHT_ENV_ACCESS_DETECTED, PS.ENDPOINT_PREFLIGHT_FILE_ACCESS_DETECTED, PS.ENDPOINT_PREFLIGHT_CONFIG_STORE_ACCESS_DETECTED}),
    ]
    for marker, status in cases:
        manifest = _manifest(declared_endpoint_properties=(marker,))
        preflight = _preflight(manifest, metadata_evidence={"evidence": marker})
        assert manifest.endpoint_status != ES.ENDPOINT_CUSTODY_NO_ENDPOINTS
        if isinstance(status, set):
            assert preflight.endpoint_preflight_status in status
        else:
            assert preflight.endpoint_preflight_status == status
        assert provider_endpoint_preflight_denies_real_endpoints(preflight)


def test_requested_access_flags_are_denied_with_specific_statuses():
    cases = {
        "requested_endpoint_resolution": PS.ENDPOINT_PREFLIGHT_ENDPOINT_RESOLUTION_FORBIDDEN,
        "requested_dns_resolution": PS.ENDPOINT_PREFLIGHT_DNS_RESOLUTION_DETECTED,
        "requested_env_access": PS.ENDPOINT_PREFLIGHT_ENV_ACCESS_DETECTED,
        "requested_file_access": PS.ENDPOINT_PREFLIGHT_FILE_ACCESS_DETECTED,
        "requested_config_store_access": PS.ENDPOINT_PREFLIGHT_CONFIG_STORE_ACCESS_DETECTED,
        "requested_credential_material": PS.ENDPOINT_PREFLIGHT_CREDENTIALS_DETECTED,
        "requested_provider_client_material": PS.ENDPOINT_PREFLIGHT_CLIENT_DETECTED,
        "requested_network_access": PS.ENDPOINT_PREFLIGHT_NETWORK_DETECTED,
        "requested_registration": PS.ENDPOINT_PREFLIGHT_NETWORK_DETECTED,
    }
    for flag, status in cases.items():
        preflight = _preflight(**{flag: True})
        assert preflight.endpoint_preflight_status == status
        assert not preflight.endpoint_allowed


def test_linked_phase91_and_phase92_gates():
    clean_capability = _capability()
    real_capability = _capability(adapter_kind=TK.TRANSPORT_CAPABILITY_HTTP)
    clean_credential = _credential()
    secret_credential = _credential(custody_kind=CK.CREDENTIAL_CUSTODY_INLINE_SECRET_FORBIDDEN)
    clean_credential_preflight = _credential_preflight(clean_credential)
    dirty_credential_preflight = _credential_preflight(clean_credential, no_secret_material=False)

    assert _preflight(capability=clean_capability).endpoint_preflight_status == PS.ENDPOINT_PREFLIGHT_NO_ENDPOINTS_ALLOWED
    assert _preflight(capability=real_capability).endpoint_preflight_status == PS.ENDPOINT_PREFLIGHT_NETWORK_DETECTED
    assert _preflight(credential=secret_credential).endpoint_preflight_status == PS.ENDPOINT_PREFLIGHT_CREDENTIALS_DETECTED
    assert _preflight(credential=clean_credential).endpoint_preflight_status == PS.ENDPOINT_PREFLIGHT_NO_ENDPOINTS_ALLOWED
    assert _preflight(credential_preflight=clean_credential_preflight).endpoint_preflight_status == PS.ENDPOINT_PREFLIGHT_NO_ENDPOINTS_ALLOWED
    assert _preflight(credential_preflight=dirty_credential_preflight).endpoint_preflight_status == PS.ENDPOINT_PREFLIGHT_CREDENTIALS_DETECTED


def test_no_endpoint_no_runtime_flags_are_denied_when_false():
    cases = {
        "no_endpoint_material": PS.ENDPOINT_PREFLIGHT_FORBIDDEN_ENDPOINT_DETECTED,
        "no_endpoint_references": PS.ENDPOINT_PREFLIGHT_ENDPOINT_RESOLUTION_FORBIDDEN,
        "no_endpoint_resolution": PS.ENDPOINT_PREFLIGHT_ENDPOINT_RESOLUTION_FORBIDDEN,
        "no_dns_resolution": PS.ENDPOINT_PREFLIGHT_DNS_RESOLUTION_DETECTED,
        "no_env_access": PS.ENDPOINT_PREFLIGHT_ENV_ACCESS_DETECTED,
        "no_file_access": PS.ENDPOINT_PREFLIGHT_FILE_ACCESS_DETECTED,
        "no_config_store_access": PS.ENDPOINT_PREFLIGHT_CONFIG_STORE_ACCESS_DETECTED,
        "no_credentials": PS.ENDPOINT_PREFLIGHT_CREDENTIALS_DETECTED,
        "no_provider_client": PS.ENDPOINT_PREFLIGHT_CLIENT_DETECTED,
        "no_network": PS.ENDPOINT_PREFLIGHT_NETWORK_DETECTED,
        "no_provider_send": PS.ENDPOINT_PREFLIGHT_NETWORK_DETECTED,
        "no_provider_sdk": PS.ENDPOINT_PREFLIGHT_RUNTIME_AUTHORITY_DETECTED,
        "no_http": PS.ENDPOINT_PREFLIGHT_NETWORK_DETECTED,
        "no_socket": PS.ENDPOINT_PREFLIGHT_NETWORK_DETECTED,
        "no_semantic_generation": PS.ENDPOINT_PREFLIGHT_RUNTIME_AUTHORITY_DETECTED,
    }
    for flag, status in cases.items():
        preflight = _preflight(**{flag: False})
        assert preflight.endpoint_preflight_status == status
        assert not preflight.endpoint_allowed


def test_runtime_payload_and_provider_param_markers_are_denied():
    for marker in ("raw_payload", "runtime_handle", "model_params provider_params"):
        preflight = _preflight(metadata_evidence={"marker": marker})
        assert preflight.endpoint_preflight_status == PS.ENDPOINT_PREFLIGHT_RUNTIME_AUTHORITY_DETECTED
        assert not preflight.endpoint_allowed


def test_helper_predicates_only_pass_for_clean_manifest_and_preflight():
    manifest = _manifest()
    preflight = _preflight(manifest)
    dirty = _manifest(endpoint_values_present=True)
    assert provider_endpoint_custody_contains_no_endpoints(manifest)
    assert not provider_endpoint_custody_contains_no_endpoints(dirty)
    for subject in (manifest, preflight):
        assert provider_endpoint_custody_forbids_endpoint_resolution(subject)
        assert provider_endpoint_custody_forbids_dns_resolution(subject)
        assert provider_endpoint_custody_forbids_env_access(subject)
        assert provider_endpoint_custody_forbids_file_access(subject)
        assert provider_endpoint_custody_forbids_config_store_access(subject)
        assert provider_endpoint_custody_has_no_network(subject)
        assert provider_endpoint_custody_has_no_credentials(subject)
        assert provider_endpoint_custody_has_no_provider_client(subject)
        assert provider_endpoint_custody_has_no_runtime_authority(subject)
    assert provider_endpoint_preflight_denies_real_endpoints(_preflight(dirty))
    assert provider_endpoint_preflight_remains_metadata_only(preflight)


def test_endpoint_digest_is_deterministic_and_changes_for_kind_properties_and_flags():
    one = _manifest()
    two = _manifest()
    assert one.endpoint_digest == two.endpoint_digest == compute_provider_endpoint_custody_digest(one)
    assert _manifest(endpoint_custody_kind=EK.ENDPOINT_CUSTODY_NO_ENDPOINT_PLACEHOLDER).endpoint_digest != one.endpoint_digest
    assert _manifest(declared_endpoint_properties=("metadata-posture",)).endpoint_digest != one.endpoint_digest
    assert _manifest(forbidden_endpoint_properties=("inline-url",)).endpoint_digest != one.endpoint_digest
    assert _manifest(no_endpoint_material=False).endpoint_digest != one.endpoint_digest


def test_preflight_digest_is_deterministic_and_changes_for_linkage_requests_and_flags():
    manifest = _manifest()
    one = _preflight(manifest)
    two = _preflight(manifest)
    assert one.endpoint_preflight_digest == two.endpoint_preflight_digest == compute_provider_endpoint_custody_preflight_digest(one)
    linked_cap = _preflight(manifest, capability=_capability())
    assert linked_cap.endpoint_preflight_digest != one.endpoint_preflight_digest
    linked_cred = _preflight(manifest, credential=_credential())
    assert linked_cred.endpoint_preflight_digest != one.endpoint_preflight_digest
    changed_kind = _preflight(manifest, requested_endpoint_custody_kind=EK.ENDPOINT_CUSTODY_NO_ENDPOINT_PLACEHOLDER)
    assert changed_kind.endpoint_preflight_digest != one.endpoint_preflight_digest
    changed_access = _preflight(manifest, requested_env_access=True)
    assert changed_access.endpoint_preflight_digest != one.endpoint_preflight_digest
    changed_no_flag = _preflight(manifest, no_memory=False)
    assert changed_no_flag.endpoint_preflight_digest != one.endpoint_preflight_digest


def test_helper_does_not_mutate_linked_artifacts_and_registries_remain_forbidden():
    registry = build_provider_transport_registry_manifest()
    capability = _capability()
    credential = _credential()
    credential_preflight = _credential_preflight(credential)
    before = (deepcopy(registry), deepcopy(capability), deepcopy(credential), deepcopy(credential_preflight))
    _ = _preflight(capability=capability, credential=credential, credential_preflight=credential_preflight)
    assert (registry, capability, credential, credential_preflight) == before
    assert provider_transport_registry_is_null_only(registry)
    real_registration = evaluate_provider_transport_registration_preflight(_capability(adapter_kind=TK.TRANSPORT_CAPABILITY_HTTP), registry, requested_adapter_kind=AK.PROVIDER_TRANSPORT_HTTP_ADAPTER_FORBIDDEN, requested_registration=True)
    assert provider_transport_registration_preflight_denies_real_transport(real_registration)
    assert provider_credential_custody_contains_no_secrets(credential)


def test_helper_does_not_call_forbidden_runtime_provider_or_prompt_functions():
    tree = ast.parse(MODULE.read_text(encoding="utf-8"), filename=str(MODULE))
    imports = []
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imports.append(ast.unparse(node))
        if isinstance(node, ast.Call):
            calls.append(ast.unparse(node.func))
    forbidden_imports = ("prompt_assembler", "memory_manager", "openai", "requests", "httpx", "socket", "keyring", "boto", "azure", "google.cloud")
    assert not any(token in text for token in forbidden_imports for text in imports)
    forbidden_calls = ("assemble_prompt", "retrieve_memory", "write_memory", "execute_action", "commit_retention", "route_work", "admit_work")
    assert not any(call.endswith(token) or call == token for token in forbidden_calls for call in calls)


def test_phase63_to_phase92_to_phase93_chain_is_metadata_only():
    artifact = {
        "source_kind": "embodiment_proposal",
        "ref_id": "embodiment:proposal:phase93",
        "packet_scope": "turn",
        "conversation_scope_id": "conv",
        "task_scope_id": "task",
        "content_summary": "sanitized metadata proposal",
        "provenance_refs": ["prov:phase93"],
        "sanitized_context_summary": True,
        "decision_power": "none",
        "non_authoritative": True,
        "proposal_status": "reviewable",
    }
    candidates = build_embodiment_context_candidates([artifact])
    assert candidates and candidates[0].metadata["context_eligible"] is True
    preflight = _preflight(credential=_credential(), credential_preflight=_credential_preflight())
    assert preflight.endpoint_preflight_status == PS.ENDPOINT_PREFLIGHT_NO_ENDPOINTS_ALLOWED
    assert provider_endpoint_preflight_remains_metadata_only(preflight)


def test_blocked_attempted_candidate_and_adversarial_markers_do_not_enable_endpoint_custody():
    blocked = {"attempted_candidate": "blocked endpoint=https://redacted provider_params runtime_handle"}
    preflight = _preflight(_manifest(metadata_evidence=blocked), metadata_evidence=blocked)
    assert preflight.endpoint_preflight_status != PS.ENDPOINT_PREFLIGHT_NO_ENDPOINTS_ALLOWED
    assert provider_endpoint_preflight_denies_real_endpoints(preflight)
    adversarial = {"provider_client_handle": "client-object", "endpoint_url": "https://redacted", "auth_header": "bearer redacted", "tool_schema": "function_call"}
    preflight = _preflight(metadata_evidence=adversarial)
    assert preflight.endpoint_preflight_status in {
        PS.ENDPOINT_PREFLIGHT_FORBIDDEN_ENDPOINT_DETECTED,
        PS.ENDPOINT_PREFLIGHT_CREDENTIALS_DETECTED,
        PS.ENDPOINT_PREFLIGHT_RUNTIME_AUTHORITY_DETECTED,
    }
    assert not preflight.endpoint_allowed


def test_phase75_guardrail_scans_new_module_and_import_purity_is_clean():
    report = guardrails.scan_context_hygiene_prompt_boundaries(paths=("sentientos/context_hygiene/prompt_provider_endpoint_custody.py",), repo_root=ROOT)
    assert report.status == guardrails.ContextHygienePromptBoundaryStatus.BOUNDARY_CLEAN
    import sentientos.context_hygiene.prompt_provider_endpoint_custody as module

    assert module.ProviderEndpointCustodyStatus.ENDPOINT_CUSTODY_NO_ENDPOINTS == ES.ENDPOINT_CUSTODY_NO_ENDPOINTS
