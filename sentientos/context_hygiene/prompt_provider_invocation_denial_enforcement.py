from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass, replace
import hashlib
import json
from typing import Any, Mapping, Sequence, cast

from sentientos.context_hygiene.prompt_provider_invocation_denial_closure import (
    ProviderInvocationDenialClosureManifest,
    ProviderInvocationDenialClosureStatus,
    ProviderInvocationReleaseBlockerStatus,
    compute_provider_invocation_denial_closure_digest,
    provider_invocation_denial_closure_blocks_release,
    provider_invocation_denial_closure_contains_no_clients,
    provider_invocation_denial_closure_contains_no_endpoints,
    provider_invocation_denial_closure_contains_no_network_handles,
    provider_invocation_denial_closure_contains_no_prompt_text,
    provider_invocation_denial_closure_contains_no_runtime_authority,
    provider_invocation_denial_closure_contains_no_secrets,
    provider_invocation_denial_closure_denies_invocation,
    provider_invocation_denial_closure_does_not_export,
    provider_invocation_denial_closure_guardrails_present,
    provider_invocation_denial_closure_is_metadata_only,
    validate_provider_invocation_denial_closure_manifest,
)


class ProviderInvocationDenialEnforcementStatus:
    ENFORCEMENT_SNAPSHOT_CLEAN = "enforcement_snapshot_clean"
    ENFORCEMENT_SNAPSHOT_BLOCKED = "enforcement_snapshot_blocked"
    ENFORCEMENT_SNAPSHOT_INCOMPLETE = "enforcement_snapshot_incomplete"
    ENFORCEMENT_SNAPSHOT_CONTRADICTED = "enforcement_snapshot_contradicted"


@dataclass(frozen=True)
class ProviderInvocationDenialEnforcementFinding:
    code: str
    category: str
    severity: str = "blocker"


@dataclass(frozen=True)
class ProviderInvocationDenialBlockerPosture:
    provider_invocation_blocked: bool = True
    real_transport_registration_blocked: bool = True
    credentials_blocked: bool = True
    endpoints_blocked: bool = True
    clients_blocked: bool = True
    provider_sdks_blocked: bool = True
    network_egress_blocked: bool = True
    prompt_text_export_blocked: bool = True
    runtime_authority_blocked: bool = True
    prompt_assembler_modification_blocked: bool = True
    export_io_blocked: bool = True


@dataclass(frozen=True)
class ProviderInvocationDenialEnforcementEvidence:
    phase100_closure_manifest_id: str = ""
    phase100_closure_digest: str = ""
    expected_phase100_closure_digest: str = ""
    phase100_digest_match: bool = False
    phase100_closure_status: str = ""
    phase100_release_blocker_status: str = ""
    linked_artifact_count: int = 0
    closure_finding_count: int = 0
    closure_warning_count: int = 0
    closure_constraint_count: int = 0
    guardrail_summary_complete: bool = False
    prompt_boundary_guardrail_clean: bool = False
    architecture_boundaries_clean: bool = False
    import_purity_clean: bool = False
    immutability_audit_clean: bool = False
    architecture_classification_clean: bool = False
    architecture_classification_digest: str = ""


@dataclass(frozen=True)
class ProviderInvocationDenialEnforcementSnapshot:
    enforcement_snapshot_id: str
    enforcement_status: str
    enforcement_scope: str
    enforcement_ref: str
    enforcement_label: str
    blocker_posture: ProviderInvocationDenialBlockerPosture = field(default_factory=ProviderInvocationDenialBlockerPosture)
    evidence: ProviderInvocationDenialEnforcementEvidence = field(default_factory=ProviderInvocationDenialEnforcementEvidence)
    findings: tuple[str, ...] = field(default_factory=tuple)
    guardrail_codes: tuple[str, ...] = field(default_factory=tuple)
    release_blocked: bool = True
    metadata_only: bool = True
    no_provider: bool = True
    no_network: bool = True
    no_export: bool = True
    no_prompt_text: bool = True
    no_secret: bool = True
    no_endpoint: bool = True
    no_client: bool = True
    no_runtime_authority: bool = True
    no_clearance: bool = True
    no_unblock: bool = True
    provider_invocation_denial_enforcement_snapshot_only: bool = True
    phase101_enforcement_snapshot: bool = True
    phase100_closure_manifest_consumed: bool = False
    artifact_bodies_read: bool = False
    provider_invocation_performed: bool = False
    real_transport_registered: bool = False
    credentials_used: bool = False
    endpoints_used: bool = False
    clients_created: bool = False
    provider_sdks_imported: bool = False
    network_egress_performed: bool = False
    prompt_text_exported: bool = False
    runtime_authority_granted: bool = False
    prompt_assembler_modified: bool = False
    export_io_performed: bool = False
    clearance_granted: bool = False
    release_unblocked: bool = False
    sensitive_material_detected: bool = False
    endpoint_material_detected: bool = False
    secret_material_detected: bool = False
    client_material_detected: bool = False
    runtime_authority_detected: bool = False
    export_destination_detected: bool = False
    prompt_text_detected: bool = False
    rationale: str = ""
    enforcement_digest: str = ""


_NEGATIVE_MARKERS = (
    "forbidden",
    "blocked",
    "denied",
    "denial",
    "not_",
    "no_",
    "does_not_",
    "metadata_only",
    "not_performed",
    "release_blocked",
    "_blocked=true",
    "_allowed=false",
    "_performed=false",
)
_MARKER_CATEGORIES: Mapping[str, tuple[str, ...]] = {
    "unblock": ("unblock provider", "release ready", "release approved", "clearance granted", "approved for invocation"),
    "sensitive": ("api_key", "bearer", "token", "secret", "password", "private_key", "authorization"),
    "endpoint": ("https://", "http://", "endpoint", "base_url", "host", "port", "dns", "resolve"),
    "client": ("client", "session", "transport", "stream", "request builder", "sdk", "openai", "anthropic"),
    "runtime": ("runtime handle", "raw_payload", "tool schema", "function call", "action execution", "retention", "routing", "memory write"),
    "export_destination": ("upload", "deliver", "email", "webhook", "bucket", "object storage", "s3://", "gs://", "file://", "destination", "recipient"),
    "prompt_text": ("prompt_text", "final_prompt", "assembled_prompt", "system_prompt", "developer_prompt", "hidden reasoning", "scratchpad"),
    "provider_invocation": ("invoke", "send_to_provider", "chat.completions", "completion"),
}
_AUTHORITY_FIELDS = (
    "provider_invocation_performed",
    "real_transport_registered",
    "credentials_used",
    "endpoints_used",
    "clients_created",
    "provider_sdks_imported",
    "network_egress_performed",
    "prompt_text_exported",
    "runtime_authority_granted",
    "prompt_assembler_modified",
    "export_io_performed",
    "clearance_granted",
    "release_unblocked",
)


def _mapping(value: Any) -> Mapping[str, Any]:
    if value is None:
        return {}
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, Mapping):
        return value
    return {}


def _tuple_str(values: Sequence[str] | str | None) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        return (values,) if values else ()
    return tuple(str(value) for value in values if str(value))


def _dedupe(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value) for value in values if str(value)))


def _stable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _stable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _stable(value[key]) for key in sorted(value)}
    if isinstance(value, (tuple, list)):
        return [_stable(item) for item in value]
    return value


def _digest_from_data(data: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(_stable(data), sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def _safe_text(value: Any) -> str:
    return json.dumps(_stable(value), sort_keys=True, separators=(",", ":"), default=str).lower()


def _is_negative_fragment(fragment: str) -> bool:
    lowered = fragment.lower()
    return any(marker in lowered for marker in _NEGATIVE_MARKERS)


def _scan_categories(*values: Any) -> Mapping[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        text = _safe_text(value)
        for category, markers in _MARKER_CATEGORIES.items():
            count = 0
            for marker in markers:
                start = 0
                marker_lower = marker.lower()
                while True:
                    index = text.find(marker_lower, start)
                    if index == -1:
                        break
                    fragment = text[max(0, index - 50): index + len(marker_lower) + 50]
                    if not _is_negative_fragment(fragment):
                        count += 1
                    start = index + len(marker_lower)
            if count:
                counts[category] = counts.get(category, 0) + count
    return counts


def _architecture_clean(architecture_classification: Mapping[str, Any]) -> bool:
    if not architecture_classification:
        return False
    if architecture_classification.get("contradictory") is True:
        return False
    if architecture_classification.get("provider_invocation_allowed") is True:
        return False
    if architecture_classification.get("runtime_authority_allowed") is True:
        return False
    return bool(architecture_classification.get("architecture_boundaries_clean", architecture_classification.get("clean", False)) is True)


def _evidence(
    closure_manifest: ProviderInvocationDenialClosureManifest | Mapping[str, Any] | None,
    expected_phase100_closure_digest: str,
    architecture_classification: Mapping[str, Any] | None,
) -> ProviderInvocationDenialEnforcementEvidence:
    data = _mapping(closure_manifest)
    guardrail = _mapping(data.get("guardrail_summary", {}))
    summary = _mapping(data.get("evidence_summary", {}))
    digest = str(data.get("closure_digest", ""))
    expected = expected_phase100_closure_digest or digest
    arch = dict(architecture_classification or {})
    return ProviderInvocationDenialEnforcementEvidence(
        phase100_closure_manifest_id=str(data.get("closure_manifest_id", "")),
        phase100_closure_digest=digest,
        expected_phase100_closure_digest=expected,
        phase100_digest_match=bool(digest and expected and digest == expected),
        phase100_closure_status=str(data.get("closure_status", "")),
        phase100_release_blocker_status=str(data.get("release_blocker_status", "")),
        linked_artifact_count=int(summary.get("linked_artifact_count", 0) or 0),
        closure_finding_count=len(_tuple_str(data.get("findings", ()))),
        closure_warning_count=len(_tuple_str(data.get("warnings", ()))),
        closure_constraint_count=len(_tuple_str(data.get("constraints", ()))),
        guardrail_summary_complete=bool(guardrail.get("guardrail_summary_complete", False)),
        prompt_boundary_guardrail_clean=bool(guardrail.get("prompt_boundary_guardrail_clean", False)),
        architecture_boundaries_clean=bool(guardrail.get("architecture_boundaries_clean", False)),
        import_purity_clean=bool(guardrail.get("import_purity_clean", False)),
        immutability_audit_clean=bool(guardrail.get("immutability_audit_clean", False)),
        architecture_classification_clean=_architecture_clean(arch),
        architecture_classification_digest=str(arch.get("architecture_classification_digest", arch.get("digest", ""))),
    )


def _status(findings: Sequence[str], closure_status: str) -> str:
    if any("contradiction" in code or "digest_mismatch" in code or "marker_detected" in code or "authority_detected" in code or "clearance" in code or "unblock" in code for code in findings):
        return ProviderInvocationDenialEnforcementStatus.ENFORCEMENT_SNAPSHOT_CONTRADICTED
    if any("missing" in code or "incomplete" in code for code in findings):
        return ProviderInvocationDenialEnforcementStatus.ENFORCEMENT_SNAPSHOT_INCOMPLETE
    if closure_status == ProviderInvocationDenialClosureStatus.PROVIDER_INVOCATION_DENIAL_CLOSURE_SEALED_WITH_CONDITIONS:
        return ProviderInvocationDenialEnforcementStatus.ENFORCEMENT_SNAPSHOT_BLOCKED
    if findings:
        return ProviderInvocationDenialEnforcementStatus.ENFORCEMENT_SNAPSHOT_BLOCKED
    return ProviderInvocationDenialEnforcementStatus.ENFORCEMENT_SNAPSHOT_CLEAN


def build_provider_invocation_denial_enforcement_snapshot(
    phase100_closure_manifest: ProviderInvocationDenialClosureManifest | Mapping[str, Any] | None,
    *,
    expected_phase100_closure_digest: str = "",
    architecture_classification: Mapping[str, Any] | None = None,
    enforcement_ref: str = "phase101-provider-invocation-denial-enforcement",
    enforcement_label: str = "metadata-only provider invocation denial enforcement snapshot",
    rationale: str = "",
    guardrail_codes: Sequence[str] | str | None = None,
    **flag_overrides: Any,
) -> ProviderInvocationDenialEnforcementSnapshot:
    closure_data = _mapping(phase100_closure_manifest)
    findings: list[str] = []
    guardrail = _mapping(closure_data.get("guardrail_summary", {}))
    arch = dict(architecture_classification or {})

    if not closure_data:
        findings.append("phase100_closure_manifest_missing")
    else:
        closure_manifest_for_checks = cast(ProviderInvocationDenialClosureManifest | Mapping[str, Any], phase100_closure_manifest)
        validation = validate_provider_invocation_denial_closure_manifest(closure_manifest_for_checks)
        findings.extend(f"phase100:{finding.code}" for finding in validation)
        closure_digest = str(closure_data.get("closure_digest", ""))
        computed_digest = compute_provider_invocation_denial_closure_digest(closure_data)
        if not closure_digest or closure_digest != computed_digest:
            findings.append("phase100_closure_digest_mismatch")
        if expected_phase100_closure_digest and expected_phase100_closure_digest != closure_digest:
            findings.append("expected_phase100_closure_digest_mismatch")
        if closure_data.get("closure_status") != ProviderInvocationDenialClosureStatus.PROVIDER_INVOCATION_DENIAL_CLOSURE_SEALED:
            if closure_data.get("closure_status") == ProviderInvocationDenialClosureStatus.PROVIDER_INVOCATION_DENIAL_CLOSURE_SEALED_WITH_CONDITIONS:
                findings.append("phase100_sealed_with_conditions_blocked")
            else:
                findings.append(f"phase100_not_sealed:{closure_data.get('closure_status', '')}")
        if closure_data.get("release_blocker_status") not in {
            ProviderInvocationReleaseBlockerStatus.PROVIDER_INVOCATION_RELEASE_BLOCKED,
            ProviderInvocationReleaseBlockerStatus.PROVIDER_INVOCATION_RELEASE_BLOCKED_WITH_CONDITIONS,
        }:
            findings.append("phase100_release_blocker_not_blocked")
        if not provider_invocation_denial_closure_guardrails_present(closure_manifest_for_checks):
            findings.append("guardrail_evidence_missing")
        if not all(guardrail.get(key) is True for key in ("prompt_boundary_guardrail_clean", "architecture_boundaries_clean", "import_purity_clean", "immutability_audit_clean")):
            findings.append("guardrail_evidence_incomplete")
        if not provider_invocation_denial_closure_is_metadata_only(closure_manifest_for_checks):
            findings.append("phase100_not_metadata_only")
        if not provider_invocation_denial_closure_blocks_release(closure_manifest_for_checks):
            findings.append("phase100_release_unblock_detected")
        if not provider_invocation_denial_closure_denies_invocation(closure_manifest_for_checks):
            findings.append("phase100_provider_invocation_not_denied")
        if not provider_invocation_denial_closure_does_not_export(closure_manifest_for_checks):
            findings.append("phase100_export_authority_detected")
        if not provider_invocation_denial_closure_contains_no_prompt_text(closure_manifest_for_checks):
            findings.append("phase100_prompt_text_detected")
        if not provider_invocation_denial_closure_contains_no_secrets(closure_manifest_for_checks):
            findings.append("phase100_secret_material_detected")
        if not provider_invocation_denial_closure_contains_no_endpoints(closure_manifest_for_checks):
            findings.append("phase100_endpoint_material_detected")
        if not provider_invocation_denial_closure_contains_no_clients(closure_manifest_for_checks):
            findings.append("phase100_client_material_detected")
        if not provider_invocation_denial_closure_contains_no_network_handles(closure_manifest_for_checks):
            findings.append("phase100_network_authority_detected")
        if not provider_invocation_denial_closure_contains_no_runtime_authority(closure_manifest_for_checks):
            findings.append("phase100_runtime_authority_detected")

    if not arch:
        findings.append("architecture_classification_missing")
    elif not _architecture_clean(arch):
        findings.append("architecture_classification_contradiction")

    marker_counts = _scan_categories(
        enforcement_ref,
        enforcement_label,
        rationale,
        guardrail_codes,
        closure_data.get("closure_ref", ""),
        closure_data.get("closure_label", ""),
        closure_data.get("findings", ()),
        closure_data.get("release_blocker_codes", ()),
        closure_data.get("accepted_evidence_codes", ()),
        closure_data.get("rejected_evidence_codes", ()),
    )
    for category, count in sorted(marker_counts.items()):
        findings.append(f"metadata_marker_detected:{category}:{count}")

    authority_values = {field_name: bool(flag_overrides.get(field_name, False)) for field_name in _AUTHORITY_FIELDS}
    for field_name, value in authority_values.items():
        if value:
            findings.append(f"authority_detected:{field_name}")

    deduped_findings = _dedupe(findings)
    evidence = _evidence(phase100_closure_manifest, expected_phase100_closure_digest, architecture_classification)
    status = _status(deduped_findings, str(closure_data.get("closure_status", "")))
    sensitive = any("secret" in code or "sensitive" in code for code in deduped_findings)
    endpoint = any("endpoint" in code for code in deduped_findings)
    client = any("client" in code for code in deduped_findings)
    runtime = any("runtime" in code or "network_authority" in code or "authority_detected" in code for code in deduped_findings)
    export_destination = any("export_destination" in code for code in deduped_findings)
    prompt_text = any("prompt_text" in code for code in deduped_findings)
    clearance_or_unblock = any("clearance" in code or "unblock" in code for code in deduped_findings)

    snapshot = ProviderInvocationDenialEnforcementSnapshot(
        enforcement_snapshot_id="provider-invocation-denial-enforcement:pending-digest",
        enforcement_status=status,
        enforcement_scope="phase101_provider_invocation_denial_enforcement_snapshot",
        enforcement_ref=str(enforcement_ref),
        enforcement_label=str(enforcement_label),
        evidence=evidence,
        findings=deduped_findings,
        guardrail_codes=_dedupe(_tuple_str(guardrail_codes)),
        release_blocked=not authority_values["release_unblocked"],
        metadata_only=not any(authority_values.values()) and not marker_counts,
        no_provider=not authority_values["provider_invocation_performed"],
        no_network=not authority_values["network_egress_performed"],
        no_export=not authority_values["export_io_performed"] and not authority_values["prompt_text_exported"],
        no_prompt_text=not prompt_text,
        no_secret=not sensitive,
        no_endpoint=not endpoint,
        no_client=not client,
        no_runtime_authority=not runtime,
        no_clearance=not authority_values["clearance_granted"] and not clearance_or_unblock,
        no_unblock=not authority_values["release_unblocked"] and not clearance_or_unblock,
        phase100_closure_manifest_consumed=bool(closure_data),
        sensitive_material_detected=sensitive,
        endpoint_material_detected=endpoint,
        secret_material_detected=sensitive,
        client_material_detected=client,
        runtime_authority_detected=runtime,
        export_destination_detected=export_destination,
        prompt_text_detected=prompt_text,
        rationale=str(rationale),
        provider_invocation_performed=authority_values["provider_invocation_performed"],
        real_transport_registered=authority_values["real_transport_registered"],
        credentials_used=authority_values["credentials_used"],
        endpoints_used=authority_values["endpoints_used"],
        clients_created=authority_values["clients_created"],
        provider_sdks_imported=authority_values["provider_sdks_imported"],
        network_egress_performed=authority_values["network_egress_performed"],
        prompt_text_exported=authority_values["prompt_text_exported"],
        runtime_authority_granted=authority_values["runtime_authority_granted"],
        prompt_assembler_modified=authority_values["prompt_assembler_modified"],
        export_io_performed=authority_values["export_io_performed"],
        clearance_granted=authority_values["clearance_granted"],
        release_unblocked=authority_values["release_unblocked"],
    )
    digest = compute_provider_invocation_denial_enforcement_digest(snapshot)
    return replace(snapshot, enforcement_snapshot_id=f"provider-invocation-denial-enforcement:{digest}", enforcement_digest=digest)


def compute_provider_invocation_denial_enforcement_digest(snapshot: ProviderInvocationDenialEnforcementSnapshot | Mapping[str, Any]) -> str:
    data = dict(_mapping(snapshot))
    data.pop("enforcement_digest", None)
    if data.get("enforcement_snapshot_id") == "provider-invocation-denial-enforcement:pending-digest" or str(data.get("enforcement_snapshot_id", "")).startswith("provider-invocation-denial-enforcement:sha256:"):
        data["enforcement_snapshot_id"] = "provider-invocation-denial-enforcement:pending-digest"
    return _digest_from_data(data)


def validate_provider_invocation_denial_enforcement_snapshot(snapshot: ProviderInvocationDenialEnforcementSnapshot | Mapping[str, Any]) -> tuple[ProviderInvocationDenialEnforcementFinding, ...]:
    data = _mapping(snapshot)
    if not data:
        return (ProviderInvocationDenialEnforcementFinding("enforcement_snapshot_malformed", "invalid"),)
    findings = [ProviderInvocationDenialEnforcementFinding(code=code, category=code.split(":", 1)[0]) for code in _tuple_str(data.get("findings", ())) ]
    if data.get("enforcement_digest") and compute_provider_invocation_denial_enforcement_digest(data) != data.get("enforcement_digest"):
        findings.append(ProviderInvocationDenialEnforcementFinding("enforcement_digest_mismatch", "integrity"))
    if data.get("release_unblocked") is True or data.get("clearance_granted") is True:
        findings.append(ProviderInvocationDenialEnforcementFinding("release_or_clearance_forbidden", "override"))
    return tuple(findings)


def provider_invocation_denial_enforcement_is_metadata_only(snapshot: ProviderInvocationDenialEnforcementSnapshot | Mapping[str, Any]) -> bool:
    data = _mapping(snapshot)
    return bool(data and data.get("metadata_only") is True and data.get("artifact_bodies_read") is False and all(data.get(field_name) is False for field_name in _AUTHORITY_FIELDS))


def provider_invocation_denial_enforcement_blocks_release(snapshot: ProviderInvocationDenialEnforcementSnapshot | Mapping[str, Any]) -> bool:
    data = _mapping(snapshot)
    return bool(data and data.get("release_blocked") is True and data.get("release_unblocked") is False and data.get("clearance_granted") is False)


def provider_invocation_denial_enforcement_contains_no_provider(snapshot: ProviderInvocationDenialEnforcementSnapshot | Mapping[str, Any]) -> bool:
    data = _mapping(snapshot)
    return bool(data and data.get("no_provider") is True and data.get("provider_invocation_performed") is False and data.get("real_transport_registered") is False and data.get("provider_sdks_imported") is False)


def provider_invocation_denial_enforcement_contains_no_network(snapshot: ProviderInvocationDenialEnforcementSnapshot | Mapping[str, Any]) -> bool:
    data = _mapping(snapshot)
    return bool(data and data.get("no_network") is True and data.get("network_egress_performed") is False)


def provider_invocation_denial_enforcement_contains_no_export(snapshot: ProviderInvocationDenialEnforcementSnapshot | Mapping[str, Any]) -> bool:
    data = _mapping(snapshot)
    return bool(data and data.get("no_export") is True and data.get("export_io_performed") is False and data.get("prompt_text_exported") is False)


def provider_invocation_denial_enforcement_contains_no_prompt_text(snapshot: ProviderInvocationDenialEnforcementSnapshot | Mapping[str, Any]) -> bool:
    data = _mapping(snapshot)
    return bool(data and data.get("no_prompt_text") is True and data.get("prompt_text_detected") is False and data.get("prompt_text_exported") is False)


def provider_invocation_denial_enforcement_contains_no_secret(snapshot: ProviderInvocationDenialEnforcementSnapshot | Mapping[str, Any]) -> bool:
    data = _mapping(snapshot)
    return bool(data and data.get("no_secret") is True and data.get("secret_material_detected") is False and data.get("credentials_used") is False)


def provider_invocation_denial_enforcement_contains_no_endpoint(snapshot: ProviderInvocationDenialEnforcementSnapshot | Mapping[str, Any]) -> bool:
    data = _mapping(snapshot)
    return bool(data and data.get("no_endpoint") is True and data.get("endpoint_material_detected") is False and data.get("endpoints_used") is False)


def provider_invocation_denial_enforcement_contains_no_client(snapshot: ProviderInvocationDenialEnforcementSnapshot | Mapping[str, Any]) -> bool:
    data = _mapping(snapshot)
    return bool(data and data.get("no_client") is True and data.get("client_material_detected") is False and data.get("clients_created") is False)


def provider_invocation_denial_enforcement_contains_no_runtime_authority(snapshot: ProviderInvocationDenialEnforcementSnapshot | Mapping[str, Any]) -> bool:
    data = _mapping(snapshot)
    return bool(data and data.get("no_runtime_authority") is True and data.get("runtime_authority_detected") is False and data.get("runtime_authority_granted") is False)


def provider_invocation_denial_enforcement_grants_no_clearance(snapshot: ProviderInvocationDenialEnforcementSnapshot | Mapping[str, Any]) -> bool:
    data = _mapping(snapshot)
    return bool(data and data.get("no_clearance") is True and data.get("clearance_granted") is False)


def provider_invocation_denial_enforcement_grants_no_unblock(snapshot: ProviderInvocationDenialEnforcementSnapshot | Mapping[str, Any]) -> bool:
    data = _mapping(snapshot)
    return bool(data and data.get("no_unblock") is True and data.get("release_unblocked") is False)


def provider_invocation_denial_enforcement_ready(snapshot: ProviderInvocationDenialEnforcementSnapshot | Mapping[str, Any]) -> bool:
    data = _mapping(snapshot)
    return bool(
        data
        and data.get("enforcement_status") == ProviderInvocationDenialEnforcementStatus.ENFORCEMENT_SNAPSHOT_CLEAN
        and not validate_provider_invocation_denial_enforcement_snapshot(snapshot)
        and provider_invocation_denial_enforcement_is_metadata_only(snapshot)
        and provider_invocation_denial_enforcement_blocks_release(snapshot)
        and provider_invocation_denial_enforcement_contains_no_provider(snapshot)
        and provider_invocation_denial_enforcement_contains_no_network(snapshot)
        and provider_invocation_denial_enforcement_contains_no_export(snapshot)
        and provider_invocation_denial_enforcement_grants_no_clearance(snapshot)
        and provider_invocation_denial_enforcement_grants_no_unblock(snapshot)
    )


def explain_provider_invocation_denial_enforcement_findings(snapshot: ProviderInvocationDenialEnforcementSnapshot | Mapping[str, Any]) -> tuple[str, ...]:
    data = _mapping(snapshot)
    if not data:
        return ("enforcement_snapshot_malformed",)
    return _dedupe(_tuple_str(data.get("findings", ())) + tuple(finding.code for finding in validate_provider_invocation_denial_enforcement_snapshot(snapshot)))


def summarize_provider_invocation_denial_enforcement_snapshot(snapshot: ProviderInvocationDenialEnforcementSnapshot | Mapping[str, Any]) -> Mapping[str, Any]:
    data = _mapping(snapshot)
    evidence = _mapping(data.get("evidence", {}))
    return {
        "enforcement_snapshot_id": data.get("enforcement_snapshot_id", ""),
        "enforcement_status": data.get("enforcement_status", ""),
        "phase100_closure_manifest_id": evidence.get("phase100_closure_manifest_id", ""),
        "phase100_closure_digest": evidence.get("phase100_closure_digest", ""),
        "phase100_digest_match": evidence.get("phase100_digest_match", False),
        "guardrail_summary_complete": evidence.get("guardrail_summary_complete", False),
        "architecture_classification_clean": evidence.get("architecture_classification_clean", False),
        "release_blocked": data.get("release_blocked", False),
        "metadata_only": data.get("metadata_only", False),
        "no_provider": data.get("no_provider", False),
        "no_network": data.get("no_network", False),
        "no_export": data.get("no_export", False),
        "no_clearance": data.get("no_clearance", False),
        "no_unblock": data.get("no_unblock", False),
        "enforcement_digest": data.get("enforcement_digest", ""),
    }
