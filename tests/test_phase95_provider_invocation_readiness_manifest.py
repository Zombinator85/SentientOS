from __future__ import annotations

from dataclasses import replace
import ast
from pathlib import Path

import pytest

from scripts import verify_context_hygiene_prompt_boundaries as guardrails
from sentientos.context_hygiene.embodiment_context import build_embodiment_context_candidates
from sentientos.context_hygiene.prompt_provider_client_custody import (
    build_provider_client_custody_manifest,
    evaluate_provider_client_custody_preflight,
    provider_client_custody_contains_no_clients,
)
from sentientos.context_hygiene.prompt_provider_credential_custody import (
    build_provider_credential_custody_manifest,
    evaluate_provider_credential_custody_preflight,
    provider_credential_custody_contains_no_secrets,
)
from sentientos.context_hygiene.prompt_provider_endpoint_custody import (
    build_provider_endpoint_custody_manifest,
    evaluate_provider_endpoint_custody_preflight,
    provider_endpoint_custody_contains_no_endpoints,
)
from sentientos.context_hygiene.prompt_provider_invocation_readiness import (
    ProviderInvocationPreflightStatus,
    ProviderInvocationReadinessStatus,
    build_provider_invocation_readiness_manifest,
    compute_provider_invocation_readiness_digest,
    compute_provider_invocation_readiness_preflight_digest,
    evaluate_provider_invocation_readiness_preflight,
    provider_invocation_preflight_denies_real_invocation,
    provider_invocation_preflight_remains_metadata_only,
    provider_invocation_readiness_digest_chain_complete,
    provider_invocation_readiness_forbids_invocation,
    provider_invocation_readiness_has_no_clients,
    provider_invocation_readiness_has_no_credentials,
    provider_invocation_readiness_has_no_endpoints,
    provider_invocation_readiness_has_no_network,
    provider_invocation_readiness_has_no_runtime_authority,
)
from sentientos.context_hygiene.prompt_provider_transport_capability import (
    ProviderTransportCapabilityKind,
    ProviderTransportRegistrationStatus,
    build_provider_transport_capability_manifest,
    evaluate_provider_transport_registration_preflight,
    provider_transport_registration_preflight_denies_real_transport,
)
from sentientos.context_hygiene.prompt_provider_transport_registry import (
    build_provider_transport_registry_manifest,
    provider_transport_registry_is_null_only,
)
from sentientos.context_hygiene.selector import ContextCandidate, build_context_packet_from_candidates


MODULE_PATH = "sentientos/context_hygiene/prompt_provider_invocation_readiness.py"


def _chain(**overrides):
    registry = overrides.get("registry") or build_provider_transport_registry_manifest()
    capability = overrides.get("capability") or build_provider_transport_capability_manifest()
    registration = overrides.get("registration") or evaluate_provider_transport_registration_preflight(capability, registry)
    credential = overrides.get("credential") or build_provider_credential_custody_manifest(linked_capability_manifest=capability)
    credential_preflight = overrides.get("credential_preflight") or evaluate_provider_credential_custody_preflight(credential, capability, registration)
    endpoint = overrides.get("endpoint") or build_provider_endpoint_custody_manifest(linked_capability_manifest=capability, linked_credential_custody_manifest=credential)
    endpoint_preflight = overrides.get("endpoint_preflight") or evaluate_provider_endpoint_custody_preflight(endpoint, capability, credential, credential_preflight)
    client = overrides.get("client") or build_provider_client_custody_manifest(
        linked_capability_manifest=capability,
        linked_credential_custody_manifest=credential,
        linked_endpoint_custody_manifest=endpoint,
        linked_endpoint_custody_preflight=endpoint_preflight,
    )
    client_preflight = overrides.get("client_preflight") or evaluate_provider_client_custody_preflight(client, capability, credential, endpoint, endpoint_preflight)
    return {
        "capability_manifest": capability,
        "registration_preflight": registration,
        "credential_custody_manifest": credential,
        "credential_custody_preflight": credential_preflight,
        "endpoint_custody_manifest": endpoint,
        "endpoint_custody_preflight": endpoint_preflight,
        "client_custody_manifest": client,
        "client_custody_preflight": client_preflight,
        "registry_manifest": registry,
    }


def _manifest(**kwargs):
    chain = _chain(**{key: value for key, value in kwargs.items() if key in {"registry", "capability", "registration", "credential", "credential_preflight", "endpoint", "endpoint_preflight", "client", "client_preflight"}})
    chain.update({key: value for key, value in kwargs.items() if key not in {"registry", "capability", "registration", "credential", "credential_preflight", "endpoint", "endpoint_preflight", "client", "client_preflight"}})
    return build_provider_invocation_readiness_manifest(**chain)


def _clean_manifest():
    return _manifest()


def _clean_preflight(**kwargs):
    return evaluate_provider_invocation_readiness_preflight(_clean_manifest(), **kwargs)


def _assert_denied(preflight):
    assert preflight.invocation_preflight_status != ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_METADATA_ONLY_NOT_INVOCABLE
    assert not preflight.invocation_allowed
    assert not preflight.provider_send_allowed
    assert provider_invocation_preflight_denies_real_invocation(preflight)


def test_full_clean_chain_is_null_only_metadata_and_not_invocable():
    manifest = _clean_manifest()
    assert manifest.readiness_status == ProviderInvocationReadinessStatus.INVOCATION_READINESS_NULL_ONLY_METADATA
    assert manifest.invocation_allowed is False
    assert manifest.provider_send_allowed is False
    assert provider_invocation_readiness_digest_chain_complete(manifest)
    assert provider_invocation_readiness_forbids_invocation(manifest)
    preflight = evaluate_provider_invocation_readiness_preflight(manifest)
    assert preflight.invocation_preflight_status == ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_METADATA_ONLY_NOT_INVOCABLE
    assert preflight.invocation_allowed is False
    assert preflight.provider_send_allowed is False
    assert provider_invocation_preflight_remains_metadata_only(preflight)


@pytest.mark.parametrize(
    "missing_key",
    [
        "capability_manifest",
        "registration_preflight",
        "credential_custody_manifest",
        "credential_custody_preflight",
        "endpoint_custody_manifest",
        "endpoint_custody_preflight",
        "client_custody_manifest",
        "client_custody_preflight",
    ],
)
def test_missing_required_evidence_yields_missing_evidence(missing_key):
    chain = _chain()
    chain[missing_key] = None
    manifest = build_provider_invocation_readiness_manifest(**chain)
    assert manifest.readiness_status == ProviderInvocationReadinessStatus.INVOCATION_READINESS_MISSING_EVIDENCE
    assert missing_key in manifest.missing_required_evidence
    assert not provider_invocation_readiness_digest_chain_complete(manifest)


def test_dirty_transport_capability_and_registration_remain_forbidden():
    capability = build_provider_transport_capability_manifest(declared_capabilities=[ProviderTransportCapabilityKind.TRANSPORT_CAPABILITY_HTTP], http_capable=True)
    manifest = _manifest(capability=capability)
    assert manifest.readiness_status in {
        ProviderInvocationReadinessStatus.INVOCATION_READINESS_FORBIDDEN,
        ProviderInvocationReadinessStatus.INVOCATION_READINESS_NETWORK_DETECTED,
        ProviderInvocationReadinessStatus.INVOCATION_READINESS_RUNTIME_AUTHORITY_DETECTED,
    }
    registration = evaluate_provider_transport_registration_preflight(capability, build_provider_transport_registry_manifest(), requested_adapter_kind="provider_transport_http_adapter", requested_registration=True)
    assert registration.registration_status == ProviderTransportRegistrationStatus.TRANSPORT_REGISTRATION_FORBIDDEN_REAL_TRANSPORT
    assert provider_transport_registration_preflight_denies_real_transport(registration)


@pytest.mark.parametrize(
    "dirty_kwargs, expected",
    [
        ({"credential": build_provider_credential_custody_manifest(secret_values_present=True)}, ProviderInvocationReadinessStatus.INVOCATION_READINESS_CREDENTIALS_DETECTED),
        ({"endpoint": build_provider_endpoint_custody_manifest(endpoint_values_present=True)}, ProviderInvocationReadinessStatus.INVOCATION_READINESS_ENDPOINT_DETECTED),
        ({"client": build_provider_client_custody_manifest(client_values_present=True)}, ProviderInvocationReadinessStatus.INVOCATION_READINESS_CLIENT_DETECTED),
        ({"capability": build_provider_transport_capability_manifest(network_egress_capable=True)}, ProviderInvocationReadinessStatus.INVOCATION_READINESS_NETWORK_DETECTED),
        ({"capability": build_provider_transport_capability_manifest(tool_calling_capable=True)}, ProviderInvocationReadinessStatus.INVOCATION_READINESS_RUNTIME_AUTHORITY_DETECTED),
    ],
)
def test_dirty_linked_artifacts_yield_specific_detected_statuses(dirty_kwargs, expected):
    assert _manifest(**dirty_kwargs).readiness_status == expected


@pytest.mark.parametrize(
    "flag, expected",
    [
        ("requested_invocation", ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_RUNTIME_AUTHORITY_DETECTED),
        ("requested_provider_send", ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_NETWORK_DETECTED),
        ("requested_network", ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_NETWORK_DETECTED),
        ("requested_credentials", ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_CREDENTIALS_DETECTED),
        ("requested_endpoints", ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_ENDPOINT_DETECTED),
        ("requested_clients", ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_CLIENT_DETECTED),
        ("requested_provider_sdk", ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_CLIENT_DETECTED),
        ("requested_dns", ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_ENDPOINT_DETECTED),
        ("requested_http", ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_NETWORK_DETECTED),
        ("requested_socket", ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_NETWORK_DETECTED),
        ("requested_semantic_generation", ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_RUNTIME_AUTHORITY_DETECTED),
        ("requested_registration", ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_RUNTIME_AUTHORITY_DETECTED),
    ],
)
def test_requested_invocation_or_access_flags_deny(flag, expected):
    preflight = _clean_preflight(**{flag: True})
    assert preflight.invocation_preflight_status == expected
    _assert_denied(preflight)


@pytest.mark.parametrize(
    "flag",
    [
        "no_invocation",
        "no_provider_send",
        "no_credentials",
        "no_endpoints",
        "no_clients",
        "no_network",
        "no_dns",
        "no_http",
        "no_socket",
        "no_provider_sdk",
        "no_semantic_generation",
        "no_tools",
        "no_memory",
        "no_retention",
        "no_actions",
        "no_routing",
    ],
)
def test_no_runtime_flags_must_remain_true(flag):
    _assert_denied(_clean_preflight(**{flag: False}))


@pytest.mark.parametrize(
    "marker",
    [
        {"raw_payload": "x"},
        {"runtime_handle": "x"},
        {"model_params": {"temperature": 1}},
        {"note": "provider invocation requested"},
        {"note": "completion chat.completions"},
        {"note": "send_to_provider"},
        {"note": "client session transport"},
        {"api_key": "redacted", "endpoint": "redacted", "network": "redacted"},
        {"note": "tool call action retention routing memory write"},
    ],
)
def test_marker_evidence_blocks_manifest_and_preflight(marker):
    manifest = _manifest(marker_evidence=marker)
    assert manifest.readiness_status != ProviderInvocationReadinessStatus.INVOCATION_READINESS_NULL_ONLY_METADATA
    _assert_denied(evaluate_provider_invocation_readiness_preflight(_clean_manifest(), marker_evidence=marker))


def test_no_secret_no_endpoint_no_client_no_network_no_runtime_helpers_true_for_clean_outputs():
    manifest = _clean_manifest()
    preflight = evaluate_provider_invocation_readiness_preflight(manifest)
    for subject in (manifest, preflight):
        assert provider_invocation_readiness_has_no_credentials(subject)
        assert provider_invocation_readiness_has_no_endpoints(subject)
        assert provider_invocation_readiness_has_no_clients(subject)
        assert provider_invocation_readiness_has_no_network(subject)
        assert provider_invocation_readiness_has_no_runtime_authority(subject)
        assert provider_invocation_readiness_forbids_invocation(subject)


def test_readiness_digest_determinism_and_linked_digest_sensitivity():
    first = _clean_manifest()
    second = _clean_manifest()
    assert first.readiness_digest == second.readiness_digest
    assert first.readiness_digest == compute_provider_invocation_readiness_digest(first)
    assert _manifest(capability=replace(_chain()["capability_manifest"], capability_digest="sha256:changed")).readiness_digest != first.readiness_digest
    assert _manifest(credential=replace(_chain()["credential_custody_manifest"], custody_digest="sha256:changed")).readiness_digest != first.readiness_digest
    assert _manifest(endpoint=replace(_chain()["endpoint_custody_manifest"], endpoint_digest="sha256:changed")).readiness_digest != first.readiness_digest
    assert _manifest(client=replace(_chain()["client_custody_manifest"], client_digest="sha256:changed")).readiness_digest != first.readiness_digest
    chain = _chain(); chain["client_custody_preflight"] = None
    assert build_provider_invocation_readiness_manifest(**chain).readiness_digest != first.readiness_digest


def test_preflight_digest_determinism_and_flag_sensitivity():
    manifest = _clean_manifest()
    first = evaluate_provider_invocation_readiness_preflight(manifest)
    second = evaluate_provider_invocation_readiness_preflight(manifest)
    assert first.invocation_preflight_digest == second.invocation_preflight_digest
    assert first.invocation_preflight_digest == compute_provider_invocation_readiness_preflight_digest(first)
    assert evaluate_provider_invocation_readiness_preflight(replace(manifest, readiness_digest="sha256:changed")).invocation_preflight_digest != first.invocation_preflight_digest
    assert evaluate_provider_invocation_readiness_preflight(manifest, requested_invocation=True).invocation_preflight_digest != first.invocation_preflight_digest
    assert evaluate_provider_invocation_readiness_preflight(manifest, no_network=False).invocation_preflight_digest != first.invocation_preflight_digest


def test_helpers_do_not_mutate_linked_artifacts_and_do_not_call_runtime_surfaces(monkeypatch):
    chain = _chain()
    before = dict(chain)
    def forbidden(*args, **kwargs):  # pragma: no cover - only reached on regression
        raise AssertionError("forbidden runtime surface called")
    import sentientos.context_hygiene.prompt_provider_invocation_readiness as readiness
    for name in ("assemble_prompt", "retrieve_memory", "write_memory", "execute_action", "route_work", "admit_work"):
        monkeypatch.setattr(readiness, name, forbidden, raising=False)
    build_provider_invocation_readiness_manifest(**chain)
    assert chain == before


def test_phase90_through_phase94_contracts_remain_preserved_after_phase95_checks():
    chain = _chain()
    manifest = build_provider_invocation_readiness_manifest(**chain)
    evaluate_provider_invocation_readiness_preflight(manifest)
    assert provider_transport_registry_is_null_only(chain["registry_manifest"])
    assert provider_credential_custody_contains_no_secrets(chain["credential_custody_manifest"])
    assert provider_endpoint_custody_contains_no_endpoints(chain["endpoint_custody_manifest"])
    assert provider_client_custody_contains_no_clients(chain["client_custody_manifest"])


def test_embodiment_metadata_chain_remains_not_invocable():
    candidates = build_embodiment_context_candidates([{"artifact_id": "presence", "sanitized": True, "privacy_posture": "public"}])
    assert candidates
    manifest = _clean_manifest()
    preflight = evaluate_provider_invocation_readiness_preflight(manifest)
    assert provider_invocation_preflight_remains_metadata_only(preflight)
    assert not preflight.invocation_allowed


def test_blocked_attempted_candidate_does_not_enable_invocation_readiness():
    packet = build_context_packet_from_candidates(
        [ContextCandidate(ref_id="blocked", ref_type="memory", summary="blocked", pollution_risk="blocked")],
        "task",
        "conversation",
        "task",
    )
    assert packet.excluded_refs
    manifest = _clean_manifest()
    assert manifest.readiness_status == ProviderInvocationReadinessStatus.INVOCATION_READINESS_NULL_ONLY_METADATA
    assert not manifest.invocation_allowed


def test_static_guardrail_scans_new_module_and_source_has_no_runtime_calls():
    assert MODULE_PATH in guardrails.DEFAULT_SCAN_TARGETS
    findings = guardrails.scan_file_for_prompt_boundary_violations(MODULE_PATH)
    assert not findings, guardrails.summarize_context_hygiene_prompt_boundary_scan(
        guardrails.ContextHygienePromptBoundaryReport(guardrails.ContextHygienePromptBoundaryStatus.BOUNDARY_FAILED, (MODULE_PATH,), findings)
    )
    tree = ast.parse(Path(MODULE_PATH).read_text(encoding="utf-8"))
    forbidden_imports = {"os", "socket", "requests", "httpx", "openai", "anthropic", "memory_manager"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not ({alias.name.split(".")[0] for alias in node.names} & forbidden_imports)
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in forbidden_imports
