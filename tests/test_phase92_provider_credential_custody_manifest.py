from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

from sentientos.context_hygiene.embodiment_context import build_embodiment_context_candidates
from sentientos.context_hygiene.prompt_provider_credential_custody import (
    ProviderCredentialCustodyKind as CK,
    ProviderCredentialCustodyPreflightStatus as PS,
    ProviderCredentialCustodyStatus as CS,
    build_provider_credential_custody_manifest,
    compute_provider_credential_custody_digest,
    compute_provider_credential_custody_preflight_digest,
    evaluate_provider_credential_custody_preflight,
    provider_credential_custody_contains_no_secrets,
    provider_credential_custody_forbids_env_access,
    provider_credential_custody_forbids_file_access,
    provider_credential_custody_forbids_secret_resolution,
    provider_credential_custody_forbids_vault_access,
    provider_credential_custody_has_no_endpoint,
    provider_credential_custody_has_no_network,
    provider_credential_custody_has_no_provider_client,
    provider_credential_custody_has_no_runtime_authority,
    provider_credential_preflight_denies_real_credentials,
    provider_credential_preflight_remains_metadata_only,
)
from sentientos.context_hygiene.prompt_provider_transport_capability import (
    ProviderTransportCapabilityKind as TK,
    build_provider_transport_capability_manifest,
    evaluate_provider_transport_registration_preflight,
)
from sentientos.context_hygiene.prompt_provider_transport_registry import (
    ProviderTransportAdapterKind as AK,
    build_provider_transport_registry_manifest,
    provider_transport_registry_is_null_only,
)
from scripts import verify_context_hygiene_prompt_boundaries as guardrails

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "sentientos/context_hygiene/prompt_provider_credential_custody.py"


def _manifest(**kwargs):
    return build_provider_credential_custody_manifest(**kwargs)


def _capability(**kwargs):
    return build_provider_transport_capability_manifest(**kwargs)


def _registry(**kwargs):
    return build_provider_transport_registry_manifest(**kwargs)


def _registration(capability=None, registry=None, **kwargs):
    return evaluate_provider_transport_registration_preflight(capability or _capability(), registry or _registry(), **kwargs)


def _preflight(manifest=None, capability=None, registration=None, **kwargs):
    return evaluate_provider_credential_custody_preflight(manifest or _manifest(), capability, registration, **kwargs)


def _codes(obj) -> set[str]:
    return {finding.code for finding in obj.findings}


def test_default_no_secret_manifest_and_preflight_are_allowed_metadata_only():
    manifest = _manifest()
    preflight = _preflight(manifest)
    assert manifest.custody_status == CS.CREDENTIAL_CUSTODY_NO_SECRETS
    assert manifest.custody_kind == CK.CREDENTIAL_CUSTODY_NONE
    assert manifest.provider_credential_custody_manifest_only is True
    assert manifest.no_secret_material is True
    assert manifest.secret_values_present is False
    assert manifest.secret_references_present is False
    assert preflight.custody_preflight_status == PS.CREDENTIAL_PREFLIGHT_NO_SECRETS_ALLOWED
    assert preflight.custody_allowed is True
    assert provider_credential_preflight_remains_metadata_only(preflight)


def test_forbidden_custody_kinds_are_denied():
    cases = [
        CK.CREDENTIAL_CUSTODY_INLINE_SECRET_FORBIDDEN,
        CK.CREDENTIAL_CUSTODY_ENV_SECRET_FORBIDDEN,
        CK.CREDENTIAL_CUSTODY_FILE_SECRET_FORBIDDEN,
        CK.CREDENTIAL_CUSTODY_KEYCHAIN_SECRET_FORBIDDEN,
        CK.CREDENTIAL_CUSTODY_VAULT_SECRET_FORBIDDEN,
        CK.CREDENTIAL_CUSTODY_CLOUD_SECRET_FORBIDDEN,
        CK.CREDENTIAL_CUSTODY_PROVIDER_CLIENT_SECRET_FORBIDDEN,
        CK.CREDENTIAL_CUSTODY_UNKNOWN_FORBIDDEN,
        "credential_custody_mystery",
    ]
    for kind in cases:
        manifest = _manifest(custody_kind=kind)
        preflight = _preflight(manifest, requested_custody_kind=kind)
        assert manifest.custody_status in {CS.CREDENTIAL_CUSTODY_FORBIDDEN_SECRET_DETECTED, CS.CREDENTIAL_CUSTODY_INVALID}
        assert preflight.custody_preflight_status in {PS.CREDENTIAL_PREFLIGHT_FORBIDDEN_SECRET_DETECTED, PS.CREDENTIAL_PREFLIGHT_INVALID_INPUT}
        assert provider_credential_preflight_denies_real_credentials(preflight)


def test_secret_like_metadata_patterns_are_denied():
    cases = [
        ("sk-test-redacted", PS.CREDENTIAL_PREFLIGHT_FORBIDDEN_SECRET_DETECTED),
        ("bearer authorization header", PS.CREDENTIAL_PREFLIGHT_FORBIDDEN_SECRET_DETECTED),
        ("password plus secret=redacted client_secret", PS.CREDENTIAL_PREFLIGHT_FORBIDDEN_SECRET_DETECTED),
        ("BEGIN PRIVATE KEY redacted", PS.CREDENTIAL_PREFLIGHT_FORBIDDEN_SECRET_DETECTED),
        ("env:OPENAI_API_KEY getenv os.environ .env", PS.CREDENTIAL_PREFLIGHT_ENV_ACCESS_DETECTED),
        ("~/.config/provider /secrets/provider", PS.CREDENTIAL_PREFLIGHT_FILE_ACCESS_DETECTED),
        ("vault:path keychain:item aws secretsmanager gcp secret manager azure key vault", PS.CREDENTIAL_PREFLIGHT_VAULT_ACCESS_DETECTED),
        ("endpoint=https://example.invalid http://example.invalid", PS.CREDENTIAL_PREFLIGHT_ENDPOINT_DETECTED),
    ]
    for marker, status in cases:
        manifest = _manifest(declared_custody_properties=(marker,))
        preflight = _preflight(manifest, metadata_evidence={"evidence": marker})
        assert manifest.custody_status != CS.CREDENTIAL_CUSTODY_NO_SECRETS
        assert preflight.custody_preflight_status == status
        assert provider_credential_preflight_denies_real_credentials(preflight)


def test_requested_access_flags_are_denied_with_specific_statuses():
    cases = {
        "requested_secret_resolution": PS.CREDENTIAL_PREFLIGHT_SECRET_RESOLUTION_FORBIDDEN,
        "requested_env_access": PS.CREDENTIAL_PREFLIGHT_ENV_ACCESS_DETECTED,
        "requested_file_access": PS.CREDENTIAL_PREFLIGHT_FILE_ACCESS_DETECTED,
        "requested_vault_access": PS.CREDENTIAL_PREFLIGHT_VAULT_ACCESS_DETECTED,
        "requested_keychain_access": PS.CREDENTIAL_PREFLIGHT_VAULT_ACCESS_DETECTED,
        "requested_cloud_secret_access": PS.CREDENTIAL_PREFLIGHT_VAULT_ACCESS_DETECTED,
        "requested_endpoint_material": PS.CREDENTIAL_PREFLIGHT_ENDPOINT_DETECTED,
        "requested_provider_client_material": PS.CREDENTIAL_PREFLIGHT_CLIENT_DETECTED,
        "requested_network_access": PS.CREDENTIAL_PREFLIGHT_NETWORK_DETECTED,
    }
    for flag, status in cases.items():
        preflight = _preflight(**{flag: True})
        assert preflight.custody_preflight_status == status, flag
        assert not preflight.custody_allowed


def test_requested_registration_for_real_credentialed_transport_denies():
    capability = _capability(declared_capabilities=(TK.TRANSPORT_CAPABILITY_CREDENTIALED,))
    preflight = _preflight(capability=capability, requested_registration=True)
    assert preflight.custody_preflight_status == PS.CREDENTIAL_PREFLIGHT_NETWORK_DETECTED
    assert "capability_real_transport_detected" in _codes(preflight)


def test_linked_phase91_real_transport_capability_denies_and_null_only_allows():
    real = _capability(declared_capabilities=(TK.TRANSPORT_CAPABILITY_PROVIDER_CLIENT,))
    denied = _preflight(capability=real)
    assert denied.custody_preflight_status == PS.CREDENTIAL_PREFLIGHT_NETWORK_DETECTED
    assert "capability_real_transport_detected" in _codes(denied)

    null_only = _capability()
    allowed = _preflight(capability=null_only)
    assert allowed.custody_preflight_status == PS.CREDENTIAL_PREFLIGHT_NO_SECRETS_ALLOWED
    assert allowed.capability_digest == null_only.capability_digest


def test_linked_phase91_registration_preflight_does_not_mutate():
    capability = _capability()
    registry = _registry()
    registration = _registration(capability, registry)
    before_capability = deepcopy(capability)
    before_registration = deepcopy(registration)
    preflight = _preflight(capability=capability, registration=registration)
    assert preflight.custody_preflight_status == PS.CREDENTIAL_PREFLIGHT_NO_SECRETS_ALLOWED
    assert capability == before_capability
    assert registration == before_registration


def test_no_secret_no_runtime_flags_are_denied_when_false():
    cases = {
        "no_secret_material": PS.CREDENTIAL_PREFLIGHT_FORBIDDEN_SECRET_DETECTED,
        "no_secret_references": PS.CREDENTIAL_PREFLIGHT_DENIED,
        "no_secret_resolution": PS.CREDENTIAL_PREFLIGHT_SECRET_RESOLUTION_FORBIDDEN,
        "no_env_access": PS.CREDENTIAL_PREFLIGHT_ENV_ACCESS_DETECTED,
        "no_file_access": PS.CREDENTIAL_PREFLIGHT_FILE_ACCESS_DETECTED,
        "no_vault_access": PS.CREDENTIAL_PREFLIGHT_VAULT_ACCESS_DETECTED,
        "no_keychain_access": PS.CREDENTIAL_PREFLIGHT_VAULT_ACCESS_DETECTED,
        "no_cloud_secret_access": PS.CREDENTIAL_PREFLIGHT_VAULT_ACCESS_DETECTED,
        "no_endpoint": PS.CREDENTIAL_PREFLIGHT_ENDPOINT_DETECTED,
        "no_provider_client": PS.CREDENTIAL_PREFLIGHT_CLIENT_DETECTED,
        "no_network": PS.CREDENTIAL_PREFLIGHT_NETWORK_DETECTED,
        "no_provider_send": PS.CREDENTIAL_PREFLIGHT_NETWORK_DETECTED,
        "no_provider_sdk": PS.CREDENTIAL_PREFLIGHT_RUNTIME_AUTHORITY_DETECTED,
        "no_http": PS.CREDENTIAL_PREFLIGHT_NETWORK_DETECTED,
        "no_socket": PS.CREDENTIAL_PREFLIGHT_NETWORK_DETECTED,
        "no_semantic_generation": PS.CREDENTIAL_PREFLIGHT_RUNTIME_AUTHORITY_DETECTED,
    }
    for flag, status in cases.items():
        preflight = _preflight(**{flag: False})
        assert preflight.custody_preflight_status == status, flag
        assert not preflight.custody_allowed


def test_runtime_payload_and_provider_param_markers_are_denied():
    for evidence in ("raw_payload", "runtime_handle", "model_params provider_params llm_params"):
        preflight = _preflight(metadata_evidence={"marker": evidence})
        assert preflight.custody_preflight_status == PS.CREDENTIAL_PREFLIGHT_RUNTIME_AUTHORITY_DETECTED
        assert "runtime_marker_detected" in _codes(preflight)


def test_helper_predicates_only_pass_for_clean_manifest_and_preflight():
    clean = _manifest()
    dirty = _manifest(secret_values_present=True)
    preflight = _preflight(clean)
    assert provider_credential_custody_contains_no_secrets(clean)
    assert not provider_credential_custody_contains_no_secrets(dirty)
    for subject in (clean, preflight):
        assert provider_credential_custody_forbids_secret_resolution(subject)
        assert provider_credential_custody_forbids_env_access(subject)
        assert provider_credential_custody_forbids_file_access(subject)
        assert provider_credential_custody_forbids_vault_access(subject)
        assert provider_credential_custody_has_no_network(subject)
        assert provider_credential_custody_has_no_endpoint(subject)
        assert provider_credential_custody_has_no_provider_client(subject)
        assert provider_credential_custody_has_no_runtime_authority(subject)
    assert provider_credential_preflight_denies_real_credentials(_preflight(dirty))
    assert provider_credential_preflight_remains_metadata_only(preflight)


def test_custody_digest_is_deterministic_and_changes_for_kind_properties_and_flags():
    one = _manifest()
    two = _manifest()
    assert one.custody_digest == two.custody_digest == compute_provider_credential_custody_digest(one)
    assert _manifest(custody_kind=CK.CREDENTIAL_CUSTODY_NO_SECRET_PLACEHOLDER).custody_digest != one.custody_digest
    assert _manifest(declared_custody_properties=("metadata-posture",)).custody_digest != one.custody_digest
    assert _manifest(forbidden_custody_properties=("inline-secret",)).custody_digest != one.custody_digest
    assert _manifest(no_secret_material=False).custody_digest != one.custody_digest


def test_preflight_digest_is_deterministic_and_changes_for_linkage_requests_and_flags():
    manifest = _manifest()
    one = _preflight(manifest)
    two = _preflight(manifest)
    assert one.custody_preflight_digest == two.custody_preflight_digest == compute_provider_credential_custody_preflight_digest(one)
    linked = _preflight(manifest, capability=_capability())
    assert linked.custody_preflight_digest != one.custody_preflight_digest
    changed_kind = _preflight(manifest, requested_custody_kind=CK.CREDENTIAL_CUSTODY_NO_SECRET_PLACEHOLDER)
    assert changed_kind.custody_preflight_digest != one.custody_preflight_digest
    changed_access = _preflight(manifest, requested_env_access=True)
    assert changed_access.custody_preflight_digest != one.custody_preflight_digest
    changed_no_flag = _preflight(manifest, no_memory=False)
    assert changed_no_flag.custody_preflight_digest != one.custody_preflight_digest


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


def test_phase90_registry_remains_null_only_after_phase92_checks():
    registry = _registry()
    before = deepcopy(registry)
    _ = _preflight(capability=_capability(), registration=_registration(_capability(), registry))
    assert registry == before
    assert provider_transport_registry_is_null_only(registry)


def test_phase63_embodiment_to_phase91_to_phase92_chain_is_metadata_only():
    artifact = {
        "source_kind": "embodiment_proposal",
        "ref_id": "embodiment:proposal:phase92",
        "packet_scope": "turn",
        "conversation_scope_id": "conv",
        "task_scope_id": "task",
        "content_summary": "sanitized metadata proposal",
        "provenance_refs": ["prov:phase92"],
        "sanitized_context_summary": True,
        "decision_power": "none",
        "non_authoritative": True,
        "proposal_status": "reviewable",
    }
    candidates = build_embodiment_context_candidates([artifact])
    assert candidates and candidates[0].metadata["context_eligible"] is True
    preflight = _preflight(capability=_capability())
    assert preflight.custody_preflight_status == PS.CREDENTIAL_PREFLIGHT_NO_SECRETS_ALLOWED
    assert provider_credential_preflight_remains_metadata_only(preflight)


def test_blocked_attempted_candidate_does_not_enable_credential_custody():
    manifest = _manifest(metadata_evidence={"attempted_candidate": "blocked sk-redacted provider_params runtime_handle"})
    preflight = _preflight(manifest, metadata_evidence={"attempted_candidate": "blocked sk-redacted provider_params runtime_handle"})
    assert manifest.custody_status != CS.CREDENTIAL_CUSTODY_NO_SECRETS
    assert preflight.custody_preflight_status != PS.CREDENTIAL_PREFLIGHT_NO_SECRETS_ALLOWED
    assert provider_credential_preflight_denies_real_credentials(preflight)


def test_adversarial_provider_runtime_secret_markers_remain_blocked():
    adversarial = {
        "provider_client_handle": "client-object",
        "endpoint_url": "https://example.invalid",
        "auth_header": "bearer redacted",
        "tool_schema": "function_call",
    }
    preflight = _preflight(metadata_evidence=adversarial)
    assert preflight.custody_preflight_status in {
        PS.CREDENTIAL_PREFLIGHT_FORBIDDEN_SECRET_DETECTED,
        PS.CREDENTIAL_PREFLIGHT_ENDPOINT_DETECTED,
        PS.CREDENTIAL_PREFLIGHT_RUNTIME_AUTHORITY_DETECTED,
    }
    assert not preflight.custody_allowed


def test_phase75_guardrail_scans_new_module_and_import_purity_is_clean():
    report = guardrails.scan_context_hygiene_prompt_boundaries(paths=("sentientos/context_hygiene/prompt_provider_credential_custody.py",), repo_root=ROOT)
    assert report.status == guardrails.ContextHygienePromptBoundaryStatus.BOUNDARY_CLEAN
    import sentientos.context_hygiene.prompt_provider_credential_custody as module

    assert module.ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_NO_SECRETS == CS.CREDENTIAL_CUSTODY_NO_SECRETS
