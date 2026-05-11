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
    provider_invocation_denial_closure_is_metadata_only,
    validate_provider_invocation_denial_closure_manifest,
)
from sentientos.context_hygiene.prompt_provider_invocation_denial_enforcement import (
    ProviderInvocationDenialEnforcementSnapshot,
    ProviderInvocationDenialEnforcementStatus,
    compute_provider_invocation_denial_enforcement_digest,
    provider_invocation_denial_enforcement_blocks_release,
    provider_invocation_denial_enforcement_contains_no_client,
    provider_invocation_denial_enforcement_contains_no_endpoint,
    provider_invocation_denial_enforcement_contains_no_export,
    provider_invocation_denial_enforcement_contains_no_network,
    provider_invocation_denial_enforcement_contains_no_prompt_text,
    provider_invocation_denial_enforcement_contains_no_provider,
    provider_invocation_denial_enforcement_contains_no_runtime_authority,
    provider_invocation_denial_enforcement_contains_no_secret,
    provider_invocation_denial_enforcement_grants_no_clearance,
    provider_invocation_denial_enforcement_grants_no_unblock,
    provider_invocation_denial_enforcement_is_metadata_only,
    validate_provider_invocation_denial_enforcement_snapshot,
)


class ProviderInvocationDenialDriftReviewStatus:
    DENIAL_DRIFT_REVIEW_CLEAN = "denial_drift_review_clean"
    DENIAL_DRIFT_REVIEW_BLOCKED = "denial_drift_review_blocked"
    DENIAL_DRIFT_REVIEW_INCOMPLETE = "denial_drift_review_incomplete"
    DENIAL_DRIFT_REVIEW_CONTRADICTED = "denial_drift_review_contradicted"


class ProviderInvocationDenialDriftDimensionStatus:
    CONSISTENT = "consistent"
    BLOCKED = "blocked"
    INCOMPLETE = "incomplete"
    CONTRADICTED = "contradicted"


@dataclass(frozen=True)
class ProviderInvocationDenialDriftFinding:
    code: str
    category: str
    severity: str = "blocker"


@dataclass(frozen=True)
class ProviderInvocationDenialDriftDimensions:
    closure_enforcement_status_consistency: str = ProviderInvocationDenialDriftDimensionStatus.INCOMPLETE
    release_blocker_consistency: str = ProviderInvocationDenialDriftDimensionStatus.INCOMPLETE
    architecture_classification_consistency: str = ProviderInvocationDenialDriftDimensionStatus.INCOMPLETE
    prompt_boundary_scan_coverage_consistency: str = ProviderInvocationDenialDriftDimensionStatus.INCOMPLETE
    no_provider_no_network_no_export_no_runtime_no_prompt_text_consistency: str = ProviderInvocationDenialDriftDimensionStatus.INCOMPLETE
    no_clearance_no_unblock_consistency: str = ProviderInvocationDenialDriftDimensionStatus.INCOMPLETE


@dataclass(frozen=True)
class ProviderInvocationDenialDriftEvidenceSummary:
    phase100_closure_manifest_id: str = ""
    phase100_closure_digest: str = ""
    phase100_computed_closure_digest: str = ""
    phase100_closure_status: str = ""
    phase100_release_blocker_status: str = ""
    phase101_enforcement_snapshot_id: str = ""
    phase101_enforcement_digest: str = ""
    phase101_computed_enforcement_digest: str = ""
    phase101_expected_phase100_closure_digest: str = ""
    phase101_enforcement_status: str = ""
    phase101_release_blocked: bool = False
    architecture_classification_digest: str = ""
    architecture_classification_clean: bool = False
    architecture_provider_invocation_allowed: bool = False
    architecture_runtime_authority_allowed: bool = False
    prompt_boundary_scan_status: str = ""
    prompt_boundary_scan_target_count: int = 0
    prompt_boundary_scan_finding_count: int = 0
    prompt_boundary_phase100_target_present: bool = False
    prompt_boundary_phase101_target_present: bool = False
    prompt_boundary_phase102_target_present: bool = False
    allowlist_label_count: int = 0
    allowlist_metadata_only: bool = False
    metadata_only_source_count: int = 0
    finding_count: int = 0


@dataclass(frozen=True)
class ProviderInvocationDenialDriftReview:
    drift_review_id: str
    drift_status: str
    drift_scope: str
    drift_ref: str
    drift_label: str
    dimensions: ProviderInvocationDenialDriftDimensions = field(default_factory=ProviderInvocationDenialDriftDimensions)
    evidence_summary: ProviderInvocationDenialDriftEvidenceSummary = field(default_factory=ProviderInvocationDenialDriftEvidenceSummary)
    findings: tuple[str, ...] = field(default_factory=tuple)
    release_blocked: bool = True
    metadata_only: bool = True
    drift_clean_or_fail_closed: bool = True
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
    phase102_drift_review: bool = True
    provider_invocation_denial_drift_review_only: bool = True
    artifact_bodies_read: bool = False
    prompt_assembler_modified: bool = False
    provider_invocation_performed: bool = False
    network_egress_performed: bool = False
    export_io_performed: bool = False
    prompt_text_included: bool = False
    secret_material_detected: bool = False
    endpoint_material_detected: bool = False
    client_material_detected: bool = False
    runtime_authority_detected: bool = False
    clearance_granted: bool = False
    release_unblocked: bool = False
    allowlist_broadened: bool = False
    sensitive_material_detected: bool = False
    drift_digest: str = ""


_ALLOWED_ALLOWLIST_LABELS = frozenset(
    {
        "metadata_only",
        "id",
        "digest",
        "status",
        "count",
        "boolean",
        "guardrail",
        "classification",
        "coverage",
        "negative_capability",
        "release_blocked",
        "no_provider",
        "no_network",
        "no_export",
        "no_runtime_authority",
        "no_prompt_text",
        "no_clearance",
        "no_unblock",
    }
)
_REQUIRED_PROMPT_BOUNDARY_TARGETS = frozenset(
    {
        "sentientos/context_hygiene/prompt_provider_invocation_denial_closure.py",
        "sentientos/context_hygiene/prompt_provider_invocation_denial_enforcement.py",
        "sentientos/context_hygiene/prompt_provider_invocation_denial_drift_review.py",
    }
)
_AUTHORITY_FIELDS = (
    "prompt_assembler_modified",
    "provider_invocation_performed",
    "network_egress_performed",
    "export_io_performed",
    "prompt_text_included",
    "secret_material_detected",
    "endpoint_material_detected",
    "client_material_detected",
    "runtime_authority_detected",
    "clearance_granted",
    "release_unblocked",
    "allowlist_broadened",
    "artifact_bodies_read",
)
_NEGATIVE_MARKERS = ("forbidden", "blocked", "denied", "denial", "not_", "no_", "metadata_only", "release_blocked")
_MARKER_CATEGORIES: Mapping[str, tuple[str, ...]] = {
    "unblock": ("unblock provider", "release ready", "release approved", "clearance granted", "approved for invocation"),
    "sensitive": ("api_key", "bearer", "token", "secret", "password", "private_key", "authorization"),
    "endpoint": ("https://", "http://", "endpoint", "base_url", "host", "port", "dns", "resolve"),
    "client": ("client", "session", "transport", "stream", "request builder", "sdk"),
    "runtime": ("runtime handle", "raw_payload", "tool schema", "function call", "action execution", "retention", "routing", "memory write"),
    "export_destination": ("upload", "deliver", "email", "webhook", "bucket", "object storage", "destination", "recipient"),
    "prompt_text": ("prompt_text", "final_prompt", "assembled_prompt", "system_prompt", "developer_prompt", "hidden reasoning", "scratchpad"),
    "provider_invocation": ("invoke", "send_to_provider", "chat.completions", "completion"),
}


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


def _prompt_scan_data(prompt_boundary_scan: Mapping[str, Any] | None) -> Mapping[str, Any]:
    data = _mapping(prompt_boundary_scan)
    if not data:
        return {}
    return data


def _prompt_scan_targets(prompt_boundary_scan: Mapping[str, Any] | None) -> tuple[str, ...]:
    data = _prompt_scan_data(prompt_boundary_scan)
    return _tuple_str(data.get("scanned_paths", data.get("targets", ())))


def _prompt_scan_status(prompt_boundary_scan: Mapping[str, Any] | None) -> str:
    return str(_prompt_scan_data(prompt_boundary_scan).get("status", ""))


def _prompt_scan_finding_count(prompt_boundary_scan: Mapping[str, Any] | None) -> int:
    data = _prompt_scan_data(prompt_boundary_scan)
    if "finding_count" in data:
        return int(data.get("finding_count", 0) or 0)
    return len(tuple(data.get("findings", ()) or ()))


def _allowlist_labels(prompt_boundary_scan: Mapping[str, Any] | None) -> tuple[str, ...]:
    data = _prompt_scan_data(prompt_boundary_scan)
    return _dedupe(_tuple_str(data.get("allowlist_labels", ())))


def _allowlist_metadata_only(prompt_boundary_scan: Mapping[str, Any] | None) -> bool:
    labels = set(_allowlist_labels(prompt_boundary_scan))
    if not labels:
        return bool(_prompt_scan_data(prompt_boundary_scan).get("allowlist_metadata_only", True))
    return labels <= _ALLOWED_ALLOWLIST_LABELS


def _evidence_summary(
    closure_manifest: ProviderInvocationDenialClosureManifest | Mapping[str, Any] | None,
    enforcement_snapshot: ProviderInvocationDenialEnforcementSnapshot | Mapping[str, Any] | None,
    architecture_classification: Mapping[str, Any] | None,
    prompt_boundary_scan: Mapping[str, Any] | None,
    finding_count: int,
) -> ProviderInvocationDenialDriftEvidenceSummary:
    closure = _mapping(closure_manifest)
    enforcement = _mapping(enforcement_snapshot)
    enforcement_evidence = _mapping(enforcement.get("evidence", {}))
    arch = dict(architecture_classification or {})
    targets = set(_prompt_scan_targets(prompt_boundary_scan))
    labels = _allowlist_labels(prompt_boundary_scan)
    return ProviderInvocationDenialDriftEvidenceSummary(
        phase100_closure_manifest_id=str(closure.get("closure_manifest_id", "")),
        phase100_closure_digest=str(closure.get("closure_digest", "")),
        phase100_computed_closure_digest=compute_provider_invocation_denial_closure_digest(closure) if closure else "",
        phase100_closure_status=str(closure.get("closure_status", "")),
        phase100_release_blocker_status=str(closure.get("release_blocker_status", "")),
        phase101_enforcement_snapshot_id=str(enforcement.get("enforcement_snapshot_id", "")),
        phase101_enforcement_digest=str(enforcement.get("enforcement_digest", "")),
        phase101_computed_enforcement_digest=compute_provider_invocation_denial_enforcement_digest(enforcement) if enforcement else "",
        phase101_expected_phase100_closure_digest=str(enforcement_evidence.get("expected_phase100_closure_digest", "")),
        phase101_enforcement_status=str(enforcement.get("enforcement_status", "")),
        phase101_release_blocked=bool(enforcement.get("release_blocked", False)),
        architecture_classification_digest=str(arch.get("architecture_classification_digest", arch.get("digest", ""))),
        architecture_classification_clean=_architecture_clean(arch),
        architecture_provider_invocation_allowed=bool(arch.get("provider_invocation_allowed", False)),
        architecture_runtime_authority_allowed=bool(arch.get("runtime_authority_allowed", False)),
        prompt_boundary_scan_status=_prompt_scan_status(prompt_boundary_scan),
        prompt_boundary_scan_target_count=len(targets),
        prompt_boundary_scan_finding_count=_prompt_scan_finding_count(prompt_boundary_scan),
        prompt_boundary_phase100_target_present="sentientos/context_hygiene/prompt_provider_invocation_denial_closure.py" in targets,
        prompt_boundary_phase101_target_present="sentientos/context_hygiene/prompt_provider_invocation_denial_enforcement.py" in targets,
        prompt_boundary_phase102_target_present="sentientos/context_hygiene/prompt_provider_invocation_denial_drift_review.py" in targets,
        allowlist_label_count=len(labels),
        allowlist_metadata_only=_allowlist_metadata_only(prompt_boundary_scan),
        metadata_only_source_count=sum(1 for item in (closure, enforcement, arch, _prompt_scan_data(prompt_boundary_scan)) if bool(item)),
        finding_count=finding_count,
    )


def _dimension_statuses(findings: Sequence[str], closure_status: str) -> ProviderInvocationDenialDriftDimensions:
    def status_for(prefixes: tuple[str, ...]) -> str:
        selected = [code for code in findings if code.startswith(prefixes)]
        if not selected:
            return ProviderInvocationDenialDriftDimensionStatus.CONSISTENT
        if any("missing" in code or "incomplete" in code or "coverage_gap" in code for code in selected):
            return ProviderInvocationDenialDriftDimensionStatus.INCOMPLETE
        if any("blocked" in code for code in selected) and not any("contradiction" in code or "mismatch" in code or "detected" in code or "broadening" in code for code in selected):
            return ProviderInvocationDenialDriftDimensionStatus.BLOCKED
        return ProviderInvocationDenialDriftDimensionStatus.CONTRADICTED

    closure_enforcement = status_for(("phase100_", "phase101_", "closure_enforcement_"))
    if closure_status == ProviderInvocationDenialClosureStatus.PROVIDER_INVOCATION_DENIAL_CLOSURE_SEALED_WITH_CONDITIONS and closure_enforcement == ProviderInvocationDenialDriftDimensionStatus.CONSISTENT:
        closure_enforcement = ProviderInvocationDenialDriftDimensionStatus.BLOCKED
    return ProviderInvocationDenialDriftDimensions(
        closure_enforcement_status_consistency=closure_enforcement,
        release_blocker_consistency=status_for(("release_blocker_",)),
        architecture_classification_consistency=status_for(("architecture_",)),
        prompt_boundary_scan_coverage_consistency=status_for(("prompt_boundary_", "allowlist_")),
        no_provider_no_network_no_export_no_runtime_no_prompt_text_consistency=status_for(("metadata_marker_detected", "authority_detected", "phase100_not_metadata", "phase101_not_metadata", "phase100_provider", "phase101_provider", "phase100_network", "phase101_network", "phase100_export", "phase101_export", "phase100_runtime", "phase101_runtime", "phase100_prompt", "phase101_prompt")),
        no_clearance_no_unblock_consistency=status_for(("clearance_", "unblock_", "phase100_release_unblock", "phase101_release_unblock")),
    )


def _status(findings: Sequence[str], closure_status: str) -> str:
    if any("contradiction" in code or "mismatch" in code or "marker_detected" in code or "authority_detected" in code or "broadening" in code or "clearance" in code or "unblock" in code for code in findings):
        return ProviderInvocationDenialDriftReviewStatus.DENIAL_DRIFT_REVIEW_CONTRADICTED
    if any("missing" in code or "incomplete" in code or "coverage_gap" in code for code in findings):
        return ProviderInvocationDenialDriftReviewStatus.DENIAL_DRIFT_REVIEW_INCOMPLETE
    if closure_status == ProviderInvocationDenialClosureStatus.PROVIDER_INVOCATION_DENIAL_CLOSURE_SEALED_WITH_CONDITIONS or findings:
        return ProviderInvocationDenialDriftReviewStatus.DENIAL_DRIFT_REVIEW_BLOCKED
    return ProviderInvocationDenialDriftReviewStatus.DENIAL_DRIFT_REVIEW_CLEAN


def build_provider_invocation_denial_drift_review(
    phase100_closure_manifest: ProviderInvocationDenialClosureManifest | Mapping[str, Any] | None,
    phase101_enforcement_snapshot: ProviderInvocationDenialEnforcementSnapshot | Mapping[str, Any] | None,
    *,
    architecture_classification: Mapping[str, Any] | None = None,
    prompt_boundary_scan: Mapping[str, Any] | None = None,
    drift_ref: str = "phase102-provider-invocation-denial-drift-review",
    drift_label: str = "metadata-only provider invocation denial drift review",
    allowlist_labels: Sequence[str] | str | None = None,
    **flag_overrides: Any,
) -> ProviderInvocationDenialDriftReview:
    closure = _mapping(phase100_closure_manifest)
    enforcement = _mapping(phase101_enforcement_snapshot)
    enforcement_evidence = _mapping(enforcement.get("evidence", {}))
    arch = dict(architecture_classification or {})
    scan = dict(prompt_boundary_scan or {})
    if allowlist_labels is not None:
        scan["allowlist_labels"] = _tuple_str(allowlist_labels)
    findings: list[str] = []

    if not closure:
        findings.append("phase100_closure_metadata_missing")
    else:
        closure_for_checks = cast(ProviderInvocationDenialClosureManifest | Mapping[str, Any], phase100_closure_manifest)
        findings.extend(f"phase100:{finding.code}" for finding in validate_provider_invocation_denial_closure_manifest(closure_for_checks))
        closure_digest = str(closure.get("closure_digest", ""))
        if not closure_digest or closure_digest != compute_provider_invocation_denial_closure_digest(closure):
            findings.append("phase100_closure_digest_mismatch")
        if not provider_invocation_denial_closure_is_metadata_only(closure_for_checks):
            findings.append("phase100_not_metadata_only")
        if not provider_invocation_denial_closure_blocks_release(closure_for_checks):
            findings.append("phase100_release_unblock_detected")
        if not provider_invocation_denial_closure_denies_invocation(closure_for_checks):
            findings.append("phase100_provider_invocation_not_denied")
        if not provider_invocation_denial_closure_does_not_export(closure_for_checks):
            findings.append("phase100_export_authority_detected")
        if not provider_invocation_denial_closure_contains_no_prompt_text(closure_for_checks):
            findings.append("phase100_prompt_text_detected")
        if not provider_invocation_denial_closure_contains_no_secrets(closure_for_checks):
            findings.append("phase100_secret_material_detected")
        if not provider_invocation_denial_closure_contains_no_endpoints(closure_for_checks):
            findings.append("phase100_endpoint_material_detected")
        if not provider_invocation_denial_closure_contains_no_clients(closure_for_checks):
            findings.append("phase100_client_material_detected")
        if not provider_invocation_denial_closure_contains_no_network_handles(closure_for_checks):
            findings.append("phase100_network_authority_detected")
        if not provider_invocation_denial_closure_contains_no_runtime_authority(closure_for_checks):
            findings.append("phase100_runtime_authority_detected")

    if not enforcement:
        findings.append("phase101_enforcement_metadata_missing")
    else:
        enforcement_for_checks = cast(ProviderInvocationDenialEnforcementSnapshot | Mapping[str, Any], phase101_enforcement_snapshot)
        findings.extend(f"phase101:{finding.code}" for finding in validate_provider_invocation_denial_enforcement_snapshot(enforcement_for_checks))
        enforcement_digest = str(enforcement.get("enforcement_digest", ""))
        if not enforcement_digest or enforcement_digest != compute_provider_invocation_denial_enforcement_digest(enforcement):
            findings.append("phase101_enforcement_digest_mismatch")
        if not provider_invocation_denial_enforcement_is_metadata_only(enforcement_for_checks):
            findings.append("phase101_not_metadata_only")
        if not provider_invocation_denial_enforcement_blocks_release(enforcement_for_checks):
            findings.append("phase101_release_unblock_detected")
        if not provider_invocation_denial_enforcement_contains_no_provider(enforcement_for_checks):
            findings.append("phase101_provider_authority_detected")
        if not provider_invocation_denial_enforcement_contains_no_network(enforcement_for_checks):
            findings.append("phase101_network_authority_detected")
        if not provider_invocation_denial_enforcement_contains_no_export(enforcement_for_checks):
            findings.append("phase101_export_authority_detected")
        if not provider_invocation_denial_enforcement_contains_no_prompt_text(enforcement_for_checks):
            findings.append("phase101_prompt_text_detected")
        if not provider_invocation_denial_enforcement_contains_no_secret(enforcement_for_checks):
            findings.append("phase101_secret_material_detected")
        if not provider_invocation_denial_enforcement_contains_no_endpoint(enforcement_for_checks):
            findings.append("phase101_endpoint_material_detected")
        if not provider_invocation_denial_enforcement_contains_no_client(enforcement_for_checks):
            findings.append("phase101_client_material_detected")
        if not provider_invocation_denial_enforcement_contains_no_runtime_authority(enforcement_for_checks):
            findings.append("phase101_runtime_authority_detected")
        if not provider_invocation_denial_enforcement_grants_no_clearance(enforcement_for_checks):
            findings.append("clearance_marker_detected:phase101")
        if not provider_invocation_denial_enforcement_grants_no_unblock(enforcement_for_checks):
            findings.append("unblock_marker_detected:phase101")

    if closure and enforcement:
        closure_digest = str(closure.get("closure_digest", ""))
        expected = str(enforcement_evidence.get("expected_phase100_closure_digest", ""))
        recorded = str(enforcement_evidence.get("phase100_closure_digest", ""))
        if not expected or expected != closure_digest or recorded != closure_digest:
            findings.append("phase100_phase101_digest_mismatch")
        sealed_or_conditioned = closure.get("closure_status") in {
            ProviderInvocationDenialClosureStatus.PROVIDER_INVOCATION_DENIAL_CLOSURE_SEALED,
            ProviderInvocationDenialClosureStatus.PROVIDER_INVOCATION_DENIAL_CLOSURE_SEALED_WITH_CONDITIONS,
        }
        enforcement_clean_or_blocked = enforcement.get("enforcement_status") in {
            ProviderInvocationDenialEnforcementStatus.ENFORCEMENT_SNAPSHOT_CLEAN,
            ProviderInvocationDenialEnforcementStatus.ENFORCEMENT_SNAPSHOT_BLOCKED,
        }
        if not sealed_or_conditioned or not enforcement_clean_or_blocked:
            findings.append("closure_enforcement_status_contradiction")
        if closure.get("closure_status") == ProviderInvocationDenialClosureStatus.PROVIDER_INVOCATION_DENIAL_CLOSURE_SEALED and enforcement.get("enforcement_status") != ProviderInvocationDenialEnforcementStatus.ENFORCEMENT_SNAPSHOT_CLEAN:
            findings.append("closure_enforcement_status_contradiction")
        if closure.get("closure_status") == ProviderInvocationDenialClosureStatus.PROVIDER_INVOCATION_DENIAL_CLOSURE_SEALED_WITH_CONDITIONS:
            findings.append("closure_enforcement_conditioned_blocked")
            if enforcement.get("enforcement_status") != ProviderInvocationDenialEnforcementStatus.ENFORCEMENT_SNAPSHOT_BLOCKED:
                findings.append("closure_enforcement_status_contradiction")
        closure_release_blocked = closure.get("release_blocker_status") in {
            ProviderInvocationReleaseBlockerStatus.PROVIDER_INVOCATION_RELEASE_BLOCKED,
            ProviderInvocationReleaseBlockerStatus.PROVIDER_INVOCATION_RELEASE_BLOCKED_WITH_CONDITIONS,
        }
        if not closure_release_blocked or enforcement.get("release_blocked") is not True:
            findings.append("release_blocker_contradiction")

    if not arch:
        findings.append("architecture_classification_missing")
    elif not _architecture_clean(arch):
        findings.append("architecture_classification_contradiction")
    elif closure and enforcement:
        guardrail = _mapping(closure.get("guardrail_summary", {}))
        if guardrail.get("architecture_boundaries_clean") is not True or _mapping(enforcement_evidence).get("architecture_classification_clean") is not True:
            findings.append("architecture_classification_contradiction")

    if not scan:
        findings.append("prompt_boundary_scan_metadata_missing")
    else:
        targets = set(_prompt_scan_targets(scan))
        if not _REQUIRED_PROMPT_BOUNDARY_TARGETS <= targets:
            findings.append("prompt_boundary_scan_coverage_gap")
        if _prompt_scan_status(scan) not in {"boundary_clean", "boundary_clean_with_warnings"}:
            findings.append("prompt_boundary_scan_incomplete")
        if _prompt_scan_finding_count(scan):
            findings.append("prompt_boundary_scan_findings_present")
        if scan.get("allowlist_broadened") is True or not _allowlist_metadata_only(scan):
            findings.append("allowlist_broadening_detected")

    marker_counts = _scan_categories(drift_ref, drift_label, scan.get("notes", ""), closure.get("findings", ()), enforcement.get("findings", ()))
    for category, count in sorted(marker_counts.items()):
        findings.append(f"metadata_marker_detected:{category}:{count}")

    authority_values = {field_name: bool(flag_overrides.get(field_name, False)) for field_name in _AUTHORITY_FIELDS}
    for field_name, value in authority_values.items():
        if value:
            findings.append(f"authority_detected:{field_name}")

    deduped_findings = _dedupe(findings)
    dimensions = _dimension_statuses(deduped_findings, str(closure.get("closure_status", "")))
    status = _status(deduped_findings, str(closure.get("closure_status", "")))
    sensitive = any("secret" in code or "sensitive" in code for code in deduped_findings) or authority_values["secret_material_detected"]
    endpoint = any("endpoint" in code for code in deduped_findings) or authority_values["endpoint_material_detected"]
    client = any("client" in code for code in deduped_findings) or authority_values["client_material_detected"]
    runtime = any("runtime" in code or "authority_detected" in code for code in deduped_findings) or authority_values["runtime_authority_detected"]
    prompt_text = any("prompt_text" in code for code in deduped_findings) or authority_values["prompt_text_included"]
    clearance_or_unblock = any("clearance" in code or "unblock" in code for code in deduped_findings)
    review = ProviderInvocationDenialDriftReview(
        drift_review_id="provider-invocation-denial-drift-review:pending-digest",
        drift_status=status,
        drift_scope="phase102_provider_invocation_denial_drift_review",
        drift_ref=str(drift_ref),
        drift_label=str(drift_label),
        dimensions=dimensions,
        evidence_summary=_evidence_summary(phase100_closure_manifest, phase101_enforcement_snapshot, architecture_classification, scan, len(deduped_findings)),
        findings=deduped_findings,
        release_blocked=not authority_values["release_unblocked"],
        metadata_only=not any(authority_values.values()) and not any(code.startswith("metadata_marker_detected") for code in deduped_findings),
        drift_clean_or_fail_closed=status in {
            ProviderInvocationDenialDriftReviewStatus.DENIAL_DRIFT_REVIEW_CLEAN,
            ProviderInvocationDenialDriftReviewStatus.DENIAL_DRIFT_REVIEW_BLOCKED,
            ProviderInvocationDenialDriftReviewStatus.DENIAL_DRIFT_REVIEW_INCOMPLETE,
            ProviderInvocationDenialDriftReviewStatus.DENIAL_DRIFT_REVIEW_CONTRADICTED,
        },
        no_provider=not authority_values["provider_invocation_performed"] and not any("provider_authority" in code or "provider_invocation" in code for code in deduped_findings),
        no_network=not authority_values["network_egress_performed"] and not any("network_authority" in code for code in deduped_findings),
        no_export=not authority_values["export_io_performed"] and not any("export_authority" in code or "export_destination" in code for code in deduped_findings),
        no_prompt_text=not prompt_text,
        no_secret=not sensitive,
        no_endpoint=not endpoint,
        no_client=not client,
        no_runtime_authority=not runtime,
        no_clearance=not authority_values["clearance_granted"] and not clearance_or_unblock,
        no_unblock=not authority_values["release_unblocked"] and not clearance_or_unblock,
        artifact_bodies_read=authority_values["artifact_bodies_read"],
        prompt_assembler_modified=authority_values["prompt_assembler_modified"],
        provider_invocation_performed=authority_values["provider_invocation_performed"],
        network_egress_performed=authority_values["network_egress_performed"],
        export_io_performed=authority_values["export_io_performed"],
        prompt_text_included=authority_values["prompt_text_included"],
        secret_material_detected=sensitive,
        endpoint_material_detected=endpoint,
        client_material_detected=client,
        runtime_authority_detected=runtime,
        clearance_granted=authority_values["clearance_granted"],
        release_unblocked=authority_values["release_unblocked"],
        allowlist_broadened=authority_values["allowlist_broadened"] or "allowlist_broadening_detected" in deduped_findings,
        sensitive_material_detected=sensitive,
    )
    digest = compute_provider_invocation_denial_drift_review_digest(review)
    return replace(review, drift_review_id=f"provider-invocation-denial-drift-review:{digest}", drift_digest=digest)


def compute_provider_invocation_denial_drift_review_digest(review: ProviderInvocationDenialDriftReview | Mapping[str, Any]) -> str:
    data = dict(_mapping(review))
    data.pop("drift_digest", None)
    if data.get("drift_review_id") == "provider-invocation-denial-drift-review:pending-digest" or str(data.get("drift_review_id", "")).startswith("provider-invocation-denial-drift-review:sha256:"):
        data["drift_review_id"] = "provider-invocation-denial-drift-review:pending-digest"
    return _digest_from_data(data)


def validate_provider_invocation_denial_drift_review(review: ProviderInvocationDenialDriftReview | Mapping[str, Any]) -> tuple[ProviderInvocationDenialDriftFinding, ...]:
    data = _mapping(review)
    if not data:
        return (ProviderInvocationDenialDriftFinding("denial_drift_review_malformed", "invalid"),)
    findings = [ProviderInvocationDenialDriftFinding(code=code, category=code.split(":", 1)[0]) for code in _tuple_str(data.get("findings", ()))]
    if data.get("drift_digest") and compute_provider_invocation_denial_drift_review_digest(data) != data.get("drift_digest"):
        findings.append(ProviderInvocationDenialDriftFinding("drift_digest_mismatch", "integrity"))
    return tuple(findings)


def provider_invocation_denial_drift_review_is_metadata_only(review: ProviderInvocationDenialDriftReview | Mapping[str, Any]) -> bool:
    data = _mapping(review)
    return bool(data and data.get("metadata_only") is True and data.get("artifact_bodies_read") is False and all(data.get(field_name) is False for field_name in _AUTHORITY_FIELDS if field_name != "allowlist_broadened"))


def provider_invocation_denial_drift_review_clean_or_fail_closed(review: ProviderInvocationDenialDriftReview | Mapping[str, Any]) -> bool:
    data = _mapping(review)
    return bool(data and data.get("drift_clean_or_fail_closed") is True and data.get("drift_status") in {ProviderInvocationDenialDriftReviewStatus.DENIAL_DRIFT_REVIEW_CLEAN, ProviderInvocationDenialDriftReviewStatus.DENIAL_DRIFT_REVIEW_BLOCKED, ProviderInvocationDenialDriftReviewStatus.DENIAL_DRIFT_REVIEW_INCOMPLETE, ProviderInvocationDenialDriftReviewStatus.DENIAL_DRIFT_REVIEW_CONTRADICTED})


def provider_invocation_denial_drift_review_blocks_release(review: ProviderInvocationDenialDriftReview | Mapping[str, Any]) -> bool:
    data = _mapping(review)
    return bool(data and data.get("release_blocked") is True and data.get("release_unblocked") is False and data.get("clearance_granted") is False)


def provider_invocation_denial_drift_review_contains_no_provider(review: ProviderInvocationDenialDriftReview | Mapping[str, Any]) -> bool:
    data = _mapping(review)
    return bool(data and data.get("no_provider") is True and data.get("provider_invocation_performed") is False)


def provider_invocation_denial_drift_review_contains_no_network(review: ProviderInvocationDenialDriftReview | Mapping[str, Any]) -> bool:
    data = _mapping(review)
    return bool(data and data.get("no_network") is True and data.get("network_egress_performed") is False)


def provider_invocation_denial_drift_review_contains_no_export(review: ProviderInvocationDenialDriftReview | Mapping[str, Any]) -> bool:
    data = _mapping(review)
    return bool(data and data.get("no_export") is True and data.get("export_io_performed") is False)


def provider_invocation_denial_drift_review_contains_no_prompt_text(review: ProviderInvocationDenialDriftReview | Mapping[str, Any]) -> bool:
    data = _mapping(review)
    return bool(data and data.get("no_prompt_text") is True and data.get("prompt_text_included") is False)


def provider_invocation_denial_drift_review_contains_no_secret(review: ProviderInvocationDenialDriftReview | Mapping[str, Any]) -> bool:
    data = _mapping(review)
    return bool(data and data.get("no_secret") is True and data.get("secret_material_detected") is False and data.get("sensitive_material_detected") is False)


def provider_invocation_denial_drift_review_contains_no_endpoint(review: ProviderInvocationDenialDriftReview | Mapping[str, Any]) -> bool:
    data = _mapping(review)
    return bool(data and data.get("no_endpoint") is True and data.get("endpoint_material_detected") is False)


def provider_invocation_denial_drift_review_contains_no_client(review: ProviderInvocationDenialDriftReview | Mapping[str, Any]) -> bool:
    data = _mapping(review)
    return bool(data and data.get("no_client") is True and data.get("client_material_detected") is False)


def provider_invocation_denial_drift_review_contains_no_runtime_authority(review: ProviderInvocationDenialDriftReview | Mapping[str, Any]) -> bool:
    data = _mapping(review)
    return bool(data and data.get("no_runtime_authority") is True and data.get("runtime_authority_detected") is False)


def provider_invocation_denial_drift_review_grants_no_clearance(review: ProviderInvocationDenialDriftReview | Mapping[str, Any]) -> bool:
    data = _mapping(review)
    return bool(data and data.get("no_clearance") is True and data.get("clearance_granted") is False)


def provider_invocation_denial_drift_review_grants_no_unblock(review: ProviderInvocationDenialDriftReview | Mapping[str, Any]) -> bool:
    data = _mapping(review)
    return bool(data and data.get("no_unblock") is True and data.get("release_unblocked") is False)


def provider_invocation_denial_drift_review_ready(review: ProviderInvocationDenialDriftReview | Mapping[str, Any]) -> bool:
    data = _mapping(review)
    return bool(
        data
        and data.get("drift_status") == ProviderInvocationDenialDriftReviewStatus.DENIAL_DRIFT_REVIEW_CLEAN
        and not validate_provider_invocation_denial_drift_review(review)
        and provider_invocation_denial_drift_review_is_metadata_only(review)
        and provider_invocation_denial_drift_review_blocks_release(review)
        and provider_invocation_denial_drift_review_contains_no_provider(review)
        and provider_invocation_denial_drift_review_contains_no_network(review)
        and provider_invocation_denial_drift_review_contains_no_export(review)
        and provider_invocation_denial_drift_review_contains_no_prompt_text(review)
        and provider_invocation_denial_drift_review_contains_no_secret(review)
        and provider_invocation_denial_drift_review_contains_no_endpoint(review)
        and provider_invocation_denial_drift_review_contains_no_client(review)
        and provider_invocation_denial_drift_review_contains_no_runtime_authority(review)
        and provider_invocation_denial_drift_review_grants_no_clearance(review)
        and provider_invocation_denial_drift_review_grants_no_unblock(review)
    )


def explain_provider_invocation_denial_drift_review_findings(review: ProviderInvocationDenialDriftReview | Mapping[str, Any]) -> tuple[str, ...]:
    data = _mapping(review)
    if not data:
        return ("denial_drift_review_malformed",)
    return _dedupe(_tuple_str(data.get("findings", ())) + tuple(finding.code for finding in validate_provider_invocation_denial_drift_review(review)))


def summarize_provider_invocation_denial_drift_review(review: ProviderInvocationDenialDriftReview | Mapping[str, Any]) -> Mapping[str, Any]:
    data = _mapping(review)
    evidence = _mapping(data.get("evidence_summary", {}))
    dimensions = _mapping(data.get("dimensions", {}))
    return {
        "drift_review_id": data.get("drift_review_id", ""),
        "drift_status": data.get("drift_status", ""),
        "phase100_closure_manifest_id": evidence.get("phase100_closure_manifest_id", ""),
        "phase100_closure_digest": evidence.get("phase100_closure_digest", ""),
        "phase101_enforcement_snapshot_id": evidence.get("phase101_enforcement_snapshot_id", ""),
        "phase101_enforcement_digest": evidence.get("phase101_enforcement_digest", ""),
        "architecture_classification_digest": evidence.get("architecture_classification_digest", ""),
        "prompt_boundary_scan_target_count": evidence.get("prompt_boundary_scan_target_count", 0),
        "finding_count": evidence.get("finding_count", 0),
        "closure_enforcement_status_consistency": dimensions.get("closure_enforcement_status_consistency", ""),
        "release_blocker_consistency": dimensions.get("release_blocker_consistency", ""),
        "architecture_classification_consistency": dimensions.get("architecture_classification_consistency", ""),
        "prompt_boundary_scan_coverage_consistency": dimensions.get("prompt_boundary_scan_coverage_consistency", ""),
        "release_blocked": data.get("release_blocked", False),
        "metadata_only": data.get("metadata_only", False),
        "no_provider": data.get("no_provider", False),
        "no_network": data.get("no_network", False),
        "no_export": data.get("no_export", False),
        "no_clearance": data.get("no_clearance", False),
        "no_unblock": data.get("no_unblock", False),
        "drift_digest": data.get("drift_digest", ""),
    }
