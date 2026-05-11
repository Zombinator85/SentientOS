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
from sentientos.context_hygiene.prompt_provider_invocation_denial_drift_review import (
    ProviderInvocationDenialDriftReview,
    ProviderInvocationDenialDriftReviewStatus,
    compute_provider_invocation_denial_drift_review_digest,
    provider_invocation_denial_drift_review_blocks_release,
    provider_invocation_denial_drift_review_clean_or_fail_closed,
    provider_invocation_denial_drift_review_contains_no_client,
    provider_invocation_denial_drift_review_contains_no_endpoint,
    provider_invocation_denial_drift_review_contains_no_export,
    provider_invocation_denial_drift_review_contains_no_network,
    provider_invocation_denial_drift_review_contains_no_prompt_text,
    provider_invocation_denial_drift_review_contains_no_provider,
    provider_invocation_denial_drift_review_contains_no_runtime_authority,
    provider_invocation_denial_drift_review_contains_no_secret,
    provider_invocation_denial_drift_review_grants_no_clearance,
    provider_invocation_denial_drift_review_grants_no_unblock,
    provider_invocation_denial_drift_review_is_metadata_only,
    validate_provider_invocation_denial_drift_review,
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


class ProviderInvocationDenialCustodyCheckpointStatus:
    DENIAL_CUSTODY_CHECKPOINT_CLEAN = "denial_custody_checkpoint_clean"
    DENIAL_CUSTODY_CHECKPOINT_BLOCKED = "denial_custody_checkpoint_blocked"
    DENIAL_CUSTODY_CHECKPOINT_INCOMPLETE = "denial_custody_checkpoint_incomplete"
    DENIAL_CUSTODY_CHECKPOINT_CONTRADICTED = "denial_custody_checkpoint_contradicted"


class ProviderInvocationDenialCustodyDimensionStatus:
    CONSISTENT = "consistent"
    BLOCKED = "blocked"
    INCOMPLETE = "incomplete"
    CONTRADICTED = "contradicted"


@dataclass(frozen=True)
class ProviderInvocationDenialCustodyCheckpointFinding:
    code: str
    category: str
    severity: str = "blocker"


@dataclass(frozen=True)
class ProviderInvocationDenialCustodyDimensions:
    phase100_closure_custody: str = ProviderInvocationDenialCustodyDimensionStatus.INCOMPLETE
    phase101_enforcement_custody: str = ProviderInvocationDenialCustodyDimensionStatus.INCOMPLETE
    phase102_drift_review_custody: str = ProviderInvocationDenialCustodyDimensionStatus.INCOMPLETE
    strict_audit_verification_custody: str = ProviderInvocationDenialCustodyDimensionStatus.INCOMPLETE
    immutable_manifest_verification_custody: str = ProviderInvocationDenialCustodyDimensionStatus.INCOMPLETE
    architecture_classification_custody: str = ProviderInvocationDenialCustodyDimensionStatus.INCOMPLETE
    prompt_boundary_scan_custody: str = ProviderInvocationDenialCustodyDimensionStatus.INCOMPLETE
    release_blocker_continuity: str = ProviderInvocationDenialCustodyDimensionStatus.INCOMPLETE
    no_provider_no_network_no_export_no_runtime_no_prompt_text_continuity: str = ProviderInvocationDenialCustodyDimensionStatus.INCOMPLETE
    no_clearance_no_unblock_continuity: str = ProviderInvocationDenialCustodyDimensionStatus.INCOMPLETE


@dataclass(frozen=True)
class ProviderInvocationDenialCustodyEvidenceSummary:
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
    phase102_drift_review_id: str = ""
    phase102_drift_digest: str = ""
    phase102_computed_drift_digest: str = ""
    phase102_phase100_closure_digest: str = ""
    phase102_phase101_enforcement_digest: str = ""
    phase102_drift_status: str = ""
    phase102_release_blocked: bool = False
    strict_audit_status: str = ""
    strict_audit_command_result: str = ""
    strict_audit_verified: bool = False
    immutable_manifest_status: str = ""
    immutable_manifest_command_result: str = ""
    immutable_manifest_verified: bool = False
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
    prompt_boundary_phase103_target_present: bool = False
    allowlist_label_count: int = 0
    allowlist_metadata_only: bool = False
    metadata_only_source_count: int = 0
    finding_count: int = 0


@dataclass(frozen=True)
class ProviderInvocationDenialCustodyCheckpoint:
    custody_checkpoint_id: str
    checkpoint_status: str
    checkpoint_scope: str
    checkpoint_ref: str
    checkpoint_label: str
    dimensions: ProviderInvocationDenialCustodyDimensions = field(default_factory=ProviderInvocationDenialCustodyDimensions)
    evidence_summary: ProviderInvocationDenialCustodyEvidenceSummary = field(default_factory=ProviderInvocationDenialCustodyEvidenceSummary)
    findings: tuple[str, ...] = field(default_factory=tuple)
    release_blocked: bool = True
    metadata_only: bool = True
    custody_clean_or_fail_closed: bool = True
    audit_verified: bool = False
    immutable_verified: bool = False
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
    phase103_custody_checkpoint: bool = True
    provider_invocation_denial_custody_checkpoint_only: bool = True
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
    custody_digest: str = ""


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
        "command_result_label",
        "audit_verified",
        "immutable_verified",
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
        "sentientos/context_hygiene/prompt_provider_invocation_denial_custody_checkpoint.py",
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
    "artifact_body": ("artifact body", "artifact bodies", "body read", "read body", "body included"),
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
    return _mapping(prompt_boundary_scan)


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
    return _dedupe(_tuple_str(_prompt_scan_data(prompt_boundary_scan).get("allowlist_labels", ())))


def _allowlist_metadata_only(prompt_boundary_scan: Mapping[str, Any] | None) -> bool:
    labels = set(_allowlist_labels(prompt_boundary_scan))
    if not labels:
        return bool(_prompt_scan_data(prompt_boundary_scan).get("allowlist_metadata_only", True))
    return labels <= _ALLOWED_ALLOWLIST_LABELS


def _verification_passed(metadata: Mapping[str, Any], *, strict: bool = False) -> bool:
    if not metadata:
        return False
    status = str(metadata.get("status", metadata.get("verification_status", ""))).lower()
    command_result = str(metadata.get("command_result", metadata.get("command_result_label", ""))).lower()
    verified = metadata.get("verified", metadata.get("passed", metadata.get("ok", False))) is True
    strict_ok = (metadata.get("strict") is True) if strict else True
    return verified and strict_ok and status in {"passed", "clean", "verified", "ok"} and command_result in {"passed", "clean", "verified", "ok"}


def _verification_status(metadata: Mapping[str, Any]) -> str:
    return str(metadata.get("status", metadata.get("verification_status", "")))


def _verification_command_result(metadata: Mapping[str, Any]) -> str:
    return str(metadata.get("command_result", metadata.get("command_result_label", "")))


def _evidence_summary(
    closure_manifest: ProviderInvocationDenialClosureManifest | Mapping[str, Any] | None,
    enforcement_snapshot: ProviderInvocationDenialEnforcementSnapshot | Mapping[str, Any] | None,
    drift_review: ProviderInvocationDenialDriftReview | Mapping[str, Any] | None,
    strict_audit_verification: Mapping[str, Any] | None,
    immutable_manifest_verification: Mapping[str, Any] | None,
    architecture_classification: Mapping[str, Any] | None,
    prompt_boundary_scan: Mapping[str, Any] | None,
    finding_count: int,
) -> ProviderInvocationDenialCustodyEvidenceSummary:
    closure = _mapping(closure_manifest)
    enforcement = _mapping(enforcement_snapshot)
    enforcement_evidence = _mapping(enforcement.get("evidence", {}))
    drift = _mapping(drift_review)
    drift_evidence = _mapping(drift.get("evidence_summary", {}))
    strict_audit = _mapping(strict_audit_verification)
    immutable = _mapping(immutable_manifest_verification)
    arch = dict(architecture_classification or {})
    targets = set(_prompt_scan_targets(prompt_boundary_scan))
    labels = _allowlist_labels(prompt_boundary_scan)
    return ProviderInvocationDenialCustodyEvidenceSummary(
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
        phase102_drift_review_id=str(drift.get("drift_review_id", "")),
        phase102_drift_digest=str(drift.get("drift_digest", "")),
        phase102_computed_drift_digest=compute_provider_invocation_denial_drift_review_digest(drift) if drift else "",
        phase102_phase100_closure_digest=str(drift_evidence.get("phase100_closure_digest", "")),
        phase102_phase101_enforcement_digest=str(drift_evidence.get("phase101_enforcement_digest", "")),
        phase102_drift_status=str(drift.get("drift_status", "")),
        phase102_release_blocked=bool(drift.get("release_blocked", False)),
        strict_audit_status=_verification_status(strict_audit),
        strict_audit_command_result=_verification_command_result(strict_audit),
        strict_audit_verified=_verification_passed(strict_audit, strict=True),
        immutable_manifest_status=_verification_status(immutable),
        immutable_manifest_command_result=_verification_command_result(immutable),
        immutable_manifest_verified=_verification_passed(immutable),
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
        prompt_boundary_phase103_target_present="sentientos/context_hygiene/prompt_provider_invocation_denial_custody_checkpoint.py" in targets,
        allowlist_label_count=len(labels),
        allowlist_metadata_only=_allowlist_metadata_only(prompt_boundary_scan),
        metadata_only_source_count=sum(1 for item in (closure, enforcement, drift, strict_audit, immutable, arch, _prompt_scan_data(prompt_boundary_scan)) if bool(item)),
        finding_count=finding_count,
    )


def _dimension_statuses(findings: Sequence[str]) -> ProviderInvocationDenialCustodyDimensions:
    def status_for(prefixes: tuple[str, ...]) -> str:
        selected = [code for code in findings if code.startswith(prefixes)]
        if not selected:
            return ProviderInvocationDenialCustodyDimensionStatus.CONSISTENT
        if any("missing" in code or "incomplete" in code or "coverage_gap" in code for code in selected):
            return ProviderInvocationDenialCustodyDimensionStatus.INCOMPLETE
        if any("blocked" in code for code in selected) and not any("contradiction" in code or "mismatch" in code or "detected" in code or "failed" in code or "broadening" in code for code in selected):
            return ProviderInvocationDenialCustodyDimensionStatus.BLOCKED
        return ProviderInvocationDenialCustodyDimensionStatus.CONTRADICTED

    return ProviderInvocationDenialCustodyDimensions(
        phase100_closure_custody=status_for(("phase100_", "phase100:")),
        phase101_enforcement_custody=status_for(("phase101_", "phase101:")),
        phase102_drift_review_custody=status_for(("phase102_", "phase102:")),
        strict_audit_verification_custody=status_for(("strict_audit_",)),
        immutable_manifest_verification_custody=status_for(("immutable_",)),
        architecture_classification_custody=status_for(("architecture_",)),
        prompt_boundary_scan_custody=status_for(("prompt_boundary_", "allowlist_")),
        release_blocker_continuity=status_for(("release_blocker_", "phase100_release_unblock", "phase101_release_unblock", "phase102_release_unblock")),
        no_provider_no_network_no_export_no_runtime_no_prompt_text_continuity=status_for(("metadata_marker_detected", "authority_detected", "phase100_not_metadata", "phase101_not_metadata", "phase102_not_metadata", "phase100_provider", "phase101_provider", "phase102_provider", "phase100_network", "phase101_network", "phase102_network", "phase100_export", "phase101_export", "phase102_export", "phase100_runtime", "phase101_runtime", "phase102_runtime", "phase100_prompt", "phase101_prompt", "phase102_prompt")),
        no_clearance_no_unblock_continuity=status_for(("clearance_", "unblock_", "phase100_release_unblock", "phase101_release_unblock", "phase102_release_unblock")),
    )


def _status(findings: Sequence[str]) -> str:
    if any("contradiction" in code or "mismatch" in code or "marker_detected" in code or "authority_detected" in code or "broadening" in code or "failed" in code or "clearance" in code or "unblock" in code for code in findings):
        return ProviderInvocationDenialCustodyCheckpointStatus.DENIAL_CUSTODY_CHECKPOINT_CONTRADICTED
    if any("missing" in code or "incomplete" in code or "coverage_gap" in code for code in findings):
        return ProviderInvocationDenialCustodyCheckpointStatus.DENIAL_CUSTODY_CHECKPOINT_INCOMPLETE
    if findings:
        return ProviderInvocationDenialCustodyCheckpointStatus.DENIAL_CUSTODY_CHECKPOINT_BLOCKED
    return ProviderInvocationDenialCustodyCheckpointStatus.DENIAL_CUSTODY_CHECKPOINT_CLEAN


def build_provider_invocation_denial_custody_checkpoint(
    phase100_closure_manifest: ProviderInvocationDenialClosureManifest | Mapping[str, Any] | None,
    phase101_enforcement_snapshot: ProviderInvocationDenialEnforcementSnapshot | Mapping[str, Any] | None,
    phase102_drift_review: ProviderInvocationDenialDriftReview | Mapping[str, Any] | None,
    *,
    strict_audit_verification: Mapping[str, Any] | None = None,
    immutable_manifest_verification: Mapping[str, Any] | None = None,
    architecture_classification: Mapping[str, Any] | None = None,
    prompt_boundary_scan: Mapping[str, Any] | None = None,
    checkpoint_ref: str = "phase103-provider-invocation-denial-custody-checkpoint",
    checkpoint_label: str = "metadata-only provider invocation denial custody checkpoint",
    allowlist_labels: Sequence[str] | str | None = None,
    **flag_overrides: Any,
) -> ProviderInvocationDenialCustodyCheckpoint:
    closure = _mapping(phase100_closure_manifest)
    enforcement = _mapping(phase101_enforcement_snapshot)
    enforcement_evidence = _mapping(enforcement.get("evidence", {}))
    drift = _mapping(phase102_drift_review)
    drift_evidence = _mapping(drift.get("evidence_summary", {}))
    strict_audit = _mapping(strict_audit_verification)
    immutable = _mapping(immutable_manifest_verification)
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

    if not drift:
        findings.append("phase102_drift_review_metadata_missing")
    else:
        drift_for_checks = cast(ProviderInvocationDenialDriftReview | Mapping[str, Any], phase102_drift_review)
        findings.extend(f"phase102:{finding.code}" for finding in validate_provider_invocation_denial_drift_review(drift_for_checks))
        drift_digest = str(drift.get("drift_digest", ""))
        if not drift_digest or drift_digest != compute_provider_invocation_denial_drift_review_digest(drift):
            findings.append("phase102_drift_digest_mismatch")
        if not provider_invocation_denial_drift_review_is_metadata_only(drift_for_checks):
            findings.append("phase102_not_metadata_only")
        if not provider_invocation_denial_drift_review_clean_or_fail_closed(drift_for_checks):
            findings.append("phase102_not_clean_or_fail_closed")
        if not provider_invocation_denial_drift_review_blocks_release(drift_for_checks):
            findings.append("phase102_release_unblock_detected")
        if not provider_invocation_denial_drift_review_contains_no_provider(drift_for_checks):
            findings.append("phase102_provider_authority_detected")
        if not provider_invocation_denial_drift_review_contains_no_network(drift_for_checks):
            findings.append("phase102_network_authority_detected")
        if not provider_invocation_denial_drift_review_contains_no_export(drift_for_checks):
            findings.append("phase102_export_authority_detected")
        if not provider_invocation_denial_drift_review_contains_no_prompt_text(drift_for_checks):
            findings.append("phase102_prompt_text_detected")
        if not provider_invocation_denial_drift_review_contains_no_secret(drift_for_checks):
            findings.append("phase102_secret_material_detected")
        if not provider_invocation_denial_drift_review_contains_no_endpoint(drift_for_checks):
            findings.append("phase102_endpoint_material_detected")
        if not provider_invocation_denial_drift_review_contains_no_client(drift_for_checks):
            findings.append("phase102_client_material_detected")
        if not provider_invocation_denial_drift_review_contains_no_runtime_authority(drift_for_checks):
            findings.append("phase102_runtime_authority_detected")
        if not provider_invocation_denial_drift_review_grants_no_clearance(drift_for_checks):
            findings.append("clearance_marker_detected:phase102")
        if not provider_invocation_denial_drift_review_grants_no_unblock(drift_for_checks):
            findings.append("unblock_marker_detected:phase102")

    if closure and enforcement:
        closure_digest = str(closure.get("closure_digest", ""))
        if str(enforcement_evidence.get("expected_phase100_closure_digest", "")) != closure_digest or str(enforcement_evidence.get("phase100_closure_digest", "")) != closure_digest:
            findings.append("phase100_phase101_digest_mismatch")
        sealed = closure.get("closure_status") == ProviderInvocationDenialClosureStatus.PROVIDER_INVOCATION_DENIAL_CLOSURE_SEALED
        sealed_with_conditions = closure.get("closure_status") == ProviderInvocationDenialClosureStatus.PROVIDER_INVOCATION_DENIAL_CLOSURE_SEALED_WITH_CONDITIONS
        enforcement_clean = enforcement.get("enforcement_status") == ProviderInvocationDenialEnforcementStatus.ENFORCEMENT_SNAPSHOT_CLEAN
        enforcement_blocked = enforcement.get("enforcement_status") == ProviderInvocationDenialEnforcementStatus.ENFORCEMENT_SNAPSHOT_BLOCKED
        if not (sealed or sealed_with_conditions) or not (enforcement_clean or enforcement_blocked):
            findings.append("phase100_phase101_status_contradiction")
        if sealed and not enforcement_clean:
            findings.append("phase100_phase101_status_contradiction")
        if sealed_with_conditions:
            findings.append("phase100_phase101_conditioned_blocked")
            if not enforcement_blocked:
                findings.append("phase100_phase101_status_contradiction")
        closure_release_blocked = closure.get("release_blocker_status") in {
            ProviderInvocationReleaseBlockerStatus.PROVIDER_INVOCATION_RELEASE_BLOCKED,
            ProviderInvocationReleaseBlockerStatus.PROVIDER_INVOCATION_RELEASE_BLOCKED_WITH_CONDITIONS,
        }
        if not closure_release_blocked or enforcement.get("release_blocked") is not True:
            findings.append("release_blocker_contradiction")

    if closure and drift:
        closure_digest = str(closure.get("closure_digest", ""))
        if str(drift_evidence.get("phase100_closure_digest", "")) != closure_digest:
            findings.append("phase100_phase102_digest_mismatch")
    if enforcement and drift:
        enforcement_digest = str(enforcement.get("enforcement_digest", ""))
        if str(drift_evidence.get("phase101_enforcement_digest", "")) != enforcement_digest:
            findings.append("phase101_phase102_digest_mismatch")
    if closure and enforcement and drift:
        if drift.get("drift_status") not in {
            ProviderInvocationDenialDriftReviewStatus.DENIAL_DRIFT_REVIEW_CLEAN,
            ProviderInvocationDenialDriftReviewStatus.DENIAL_DRIFT_REVIEW_BLOCKED,
        }:
            findings.append("phase100_phase101_phase102_status_contradiction")
        if closure.get("closure_status") == ProviderInvocationDenialClosureStatus.PROVIDER_INVOCATION_DENIAL_CLOSURE_SEALED and enforcement.get("enforcement_status") == ProviderInvocationDenialEnforcementStatus.ENFORCEMENT_SNAPSHOT_CLEAN and drift.get("drift_status") != ProviderInvocationDenialDriftReviewStatus.DENIAL_DRIFT_REVIEW_CLEAN:
            findings.append("phase100_phase101_phase102_status_contradiction")
        if drift.get("release_blocked") is not True:
            findings.append("release_blocker_contradiction")

    if not strict_audit:
        findings.append("strict_audit_verification_missing")
    elif not _verification_passed(strict_audit, strict=True):
        findings.append("strict_audit_verification_failed")

    if not immutable:
        findings.append("immutable_manifest_verification_missing")
    elif not _verification_passed(immutable):
        findings.append("immutable_manifest_verification_failed")

    if not arch:
        findings.append("architecture_classification_missing")
    elif not _architecture_clean(arch):
        findings.append("architecture_classification_contradiction")
    elif closure and enforcement and drift:
        guardrail = _mapping(closure.get("guardrail_summary", {}))
        if guardrail.get("architecture_boundaries_clean") is not True or _mapping(enforcement_evidence).get("architecture_classification_clean") is not True or _mapping(drift.get("evidence_summary", {})).get("architecture_classification_clean") is not True:
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

    marker_counts = _scan_categories(checkpoint_ref, checkpoint_label, scan.get("notes", ""), closure.get("findings", ()), enforcement.get("findings", ()), drift.get("findings", ()))
    for category, count in sorted(marker_counts.items()):
        findings.append(f"metadata_marker_detected:{category}:{count}")

    authority_values = {field_name: bool(flag_overrides.get(field_name, False)) for field_name in _AUTHORITY_FIELDS}
    for field_name, value in authority_values.items():
        if value:
            findings.append(f"authority_detected:{field_name}")

    deduped_findings = _dedupe(findings)
    dimensions = _dimension_statuses(deduped_findings)
    status = _status(deduped_findings)
    sensitive = any("secret" in code or "sensitive" in code for code in deduped_findings) or authority_values["secret_material_detected"]
    endpoint = any("endpoint" in code for code in deduped_findings) or authority_values["endpoint_material_detected"]
    client = any("client" in code for code in deduped_findings) or authority_values["client_material_detected"]
    runtime = any("runtime" in code or "authority_detected" in code for code in deduped_findings) or authority_values["runtime_authority_detected"]
    prompt_text = any("prompt_text" in code for code in deduped_findings) or authority_values["prompt_text_included"]
    clearance_or_unblock = any("clearance" in code or "unblock" in code for code in deduped_findings)
    checkpoint = ProviderInvocationDenialCustodyCheckpoint(
        custody_checkpoint_id="provider-invocation-denial-custody-checkpoint:pending-digest",
        checkpoint_status=status,
        checkpoint_scope="phase103_provider_invocation_denial_custody_checkpoint",
        checkpoint_ref=str(checkpoint_ref),
        checkpoint_label=str(checkpoint_label),
        dimensions=dimensions,
        evidence_summary=_evidence_summary(phase100_closure_manifest, phase101_enforcement_snapshot, phase102_drift_review, strict_audit_verification, immutable_manifest_verification, architecture_classification, scan, len(deduped_findings)),
        findings=deduped_findings,
        release_blocked=not authority_values["release_unblocked"],
        metadata_only=not any(authority_values.values()) and not any(code.startswith("metadata_marker_detected") for code in deduped_findings),
        custody_clean_or_fail_closed=status in {
            ProviderInvocationDenialCustodyCheckpointStatus.DENIAL_CUSTODY_CHECKPOINT_CLEAN,
            ProviderInvocationDenialCustodyCheckpointStatus.DENIAL_CUSTODY_CHECKPOINT_BLOCKED,
            ProviderInvocationDenialCustodyCheckpointStatus.DENIAL_CUSTODY_CHECKPOINT_INCOMPLETE,
            ProviderInvocationDenialCustodyCheckpointStatus.DENIAL_CUSTODY_CHECKPOINT_CONTRADICTED,
        },
        audit_verified=_verification_passed(strict_audit, strict=True),
        immutable_verified=_verification_passed(immutable),
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
    digest = compute_provider_invocation_denial_custody_checkpoint_digest(checkpoint)
    return replace(checkpoint, custody_checkpoint_id=f"provider-invocation-denial-custody-checkpoint:{digest}", custody_digest=digest)


def compute_provider_invocation_denial_custody_checkpoint_digest(checkpoint: ProviderInvocationDenialCustodyCheckpoint | Mapping[str, Any]) -> str:
    data = dict(_mapping(checkpoint))
    data.pop("custody_digest", None)
    if data.get("custody_checkpoint_id") == "provider-invocation-denial-custody-checkpoint:pending-digest" or str(data.get("custody_checkpoint_id", "")).startswith("provider-invocation-denial-custody-checkpoint:sha256:"):
        data["custody_checkpoint_id"] = "provider-invocation-denial-custody-checkpoint:pending-digest"
    return _digest_from_data(data)


def validate_provider_invocation_denial_custody_checkpoint(checkpoint: ProviderInvocationDenialCustodyCheckpoint | Mapping[str, Any]) -> tuple[ProviderInvocationDenialCustodyCheckpointFinding, ...]:
    data = _mapping(checkpoint)
    if not data:
        return (ProviderInvocationDenialCustodyCheckpointFinding("denial_custody_checkpoint_malformed", "invalid"),)
    findings = [ProviderInvocationDenialCustodyCheckpointFinding(code=code, category=code.split(":", 1)[0]) for code in _tuple_str(data.get("findings", ()))]
    if data.get("custody_digest") and compute_provider_invocation_denial_custody_checkpoint_digest(data) != data.get("custody_digest"):
        findings.append(ProviderInvocationDenialCustodyCheckpointFinding("custody_digest_mismatch", "integrity"))
    return tuple(findings)


def provider_invocation_denial_custody_checkpoint_is_metadata_only(checkpoint: ProviderInvocationDenialCustodyCheckpoint | Mapping[str, Any]) -> bool:
    data = _mapping(checkpoint)
    return bool(data and data.get("metadata_only") is True and data.get("artifact_bodies_read") is False and all(data.get(field_name) is False for field_name in _AUTHORITY_FIELDS if field_name != "allowlist_broadened"))


def provider_invocation_denial_custody_checkpoint_clean_or_fail_closed(checkpoint: ProviderInvocationDenialCustodyCheckpoint | Mapping[str, Any]) -> bool:
    data = _mapping(checkpoint)
    return bool(data and data.get("custody_clean_or_fail_closed") is True and data.get("checkpoint_status") in {ProviderInvocationDenialCustodyCheckpointStatus.DENIAL_CUSTODY_CHECKPOINT_CLEAN, ProviderInvocationDenialCustodyCheckpointStatus.DENIAL_CUSTODY_CHECKPOINT_BLOCKED, ProviderInvocationDenialCustodyCheckpointStatus.DENIAL_CUSTODY_CHECKPOINT_INCOMPLETE, ProviderInvocationDenialCustodyCheckpointStatus.DENIAL_CUSTODY_CHECKPOINT_CONTRADICTED})


def provider_invocation_denial_custody_checkpoint_blocks_release(checkpoint: ProviderInvocationDenialCustodyCheckpoint | Mapping[str, Any]) -> bool:
    data = _mapping(checkpoint)
    return bool(data and data.get("release_blocked") is True and data.get("release_unblocked") is False and data.get("clearance_granted") is False)


def provider_invocation_denial_custody_checkpoint_audit_verified(checkpoint: ProviderInvocationDenialCustodyCheckpoint | Mapping[str, Any]) -> bool:
    data = _mapping(checkpoint)
    return bool(data and data.get("audit_verified") is True)


def provider_invocation_denial_custody_checkpoint_immutable_verified(checkpoint: ProviderInvocationDenialCustodyCheckpoint | Mapping[str, Any]) -> bool:
    data = _mapping(checkpoint)
    return bool(data and data.get("immutable_verified") is True)


def provider_invocation_denial_custody_checkpoint_contains_no_provider(checkpoint: ProviderInvocationDenialCustodyCheckpoint | Mapping[str, Any]) -> bool:
    data = _mapping(checkpoint)
    return bool(data and data.get("no_provider") is True and data.get("provider_invocation_performed") is False)


def provider_invocation_denial_custody_checkpoint_contains_no_network(checkpoint: ProviderInvocationDenialCustodyCheckpoint | Mapping[str, Any]) -> bool:
    data = _mapping(checkpoint)
    return bool(data and data.get("no_network") is True and data.get("network_egress_performed") is False)


def provider_invocation_denial_custody_checkpoint_contains_no_export(checkpoint: ProviderInvocationDenialCustodyCheckpoint | Mapping[str, Any]) -> bool:
    data = _mapping(checkpoint)
    return bool(data and data.get("no_export") is True and data.get("export_io_performed") is False)


def provider_invocation_denial_custody_checkpoint_contains_no_prompt_text(checkpoint: ProviderInvocationDenialCustodyCheckpoint | Mapping[str, Any]) -> bool:
    data = _mapping(checkpoint)
    return bool(data and data.get("no_prompt_text") is True and data.get("prompt_text_included") is False)


def provider_invocation_denial_custody_checkpoint_contains_no_secret(checkpoint: ProviderInvocationDenialCustodyCheckpoint | Mapping[str, Any]) -> bool:
    data = _mapping(checkpoint)
    return bool(data and data.get("no_secret") is True and data.get("secret_material_detected") is False and data.get("sensitive_material_detected") is False)


def provider_invocation_denial_custody_checkpoint_contains_no_endpoint(checkpoint: ProviderInvocationDenialCustodyCheckpoint | Mapping[str, Any]) -> bool:
    data = _mapping(checkpoint)
    return bool(data and data.get("no_endpoint") is True and data.get("endpoint_material_detected") is False)


def provider_invocation_denial_custody_checkpoint_contains_no_client(checkpoint: ProviderInvocationDenialCustodyCheckpoint | Mapping[str, Any]) -> bool:
    data = _mapping(checkpoint)
    return bool(data and data.get("no_client") is True and data.get("client_material_detected") is False)


def provider_invocation_denial_custody_checkpoint_contains_no_runtime_authority(checkpoint: ProviderInvocationDenialCustodyCheckpoint | Mapping[str, Any]) -> bool:
    data = _mapping(checkpoint)
    return bool(data and data.get("no_runtime_authority") is True and data.get("runtime_authority_detected") is False)


def provider_invocation_denial_custody_checkpoint_grants_no_clearance(checkpoint: ProviderInvocationDenialCustodyCheckpoint | Mapping[str, Any]) -> bool:
    data = _mapping(checkpoint)
    return bool(data and data.get("no_clearance") is True and data.get("clearance_granted") is False)


def provider_invocation_denial_custody_checkpoint_grants_no_unblock(checkpoint: ProviderInvocationDenialCustodyCheckpoint | Mapping[str, Any]) -> bool:
    data = _mapping(checkpoint)
    return bool(data and data.get("no_unblock") is True and data.get("release_unblocked") is False)


def provider_invocation_denial_custody_checkpoint_ready(checkpoint: ProviderInvocationDenialCustodyCheckpoint | Mapping[str, Any]) -> bool:
    data = _mapping(checkpoint)
    return bool(
        data
        and data.get("checkpoint_status") == ProviderInvocationDenialCustodyCheckpointStatus.DENIAL_CUSTODY_CHECKPOINT_CLEAN
        and not validate_provider_invocation_denial_custody_checkpoint(checkpoint)
        and provider_invocation_denial_custody_checkpoint_is_metadata_only(checkpoint)
        and provider_invocation_denial_custody_checkpoint_clean_or_fail_closed(checkpoint)
        and provider_invocation_denial_custody_checkpoint_blocks_release(checkpoint)
        and provider_invocation_denial_custody_checkpoint_audit_verified(checkpoint)
        and provider_invocation_denial_custody_checkpoint_immutable_verified(checkpoint)
        and provider_invocation_denial_custody_checkpoint_contains_no_provider(checkpoint)
        and provider_invocation_denial_custody_checkpoint_contains_no_network(checkpoint)
        and provider_invocation_denial_custody_checkpoint_contains_no_export(checkpoint)
        and provider_invocation_denial_custody_checkpoint_contains_no_prompt_text(checkpoint)
        and provider_invocation_denial_custody_checkpoint_contains_no_secret(checkpoint)
        and provider_invocation_denial_custody_checkpoint_contains_no_endpoint(checkpoint)
        and provider_invocation_denial_custody_checkpoint_contains_no_client(checkpoint)
        and provider_invocation_denial_custody_checkpoint_contains_no_runtime_authority(checkpoint)
        and provider_invocation_denial_custody_checkpoint_grants_no_clearance(checkpoint)
        and provider_invocation_denial_custody_checkpoint_grants_no_unblock(checkpoint)
    )


def explain_provider_invocation_denial_custody_checkpoint_findings(checkpoint: ProviderInvocationDenialCustodyCheckpoint | Mapping[str, Any]) -> tuple[str, ...]:
    data = _mapping(checkpoint)
    if not data:
        return ("denial_custody_checkpoint_malformed",)
    return _dedupe(_tuple_str(data.get("findings", ())) + tuple(finding.code for finding in validate_provider_invocation_denial_custody_checkpoint(checkpoint)))


def summarize_provider_invocation_denial_custody_checkpoint(checkpoint: ProviderInvocationDenialCustodyCheckpoint | Mapping[str, Any]) -> Mapping[str, Any]:
    data = _mapping(checkpoint)
    evidence = _mapping(data.get("evidence_summary", {}))
    dimensions = _mapping(data.get("dimensions", {}))
    return {
        "custody_checkpoint_id": data.get("custody_checkpoint_id", ""),
        "checkpoint_status": data.get("checkpoint_status", ""),
        "phase100_closure_manifest_id": evidence.get("phase100_closure_manifest_id", ""),
        "phase100_closure_digest": evidence.get("phase100_closure_digest", ""),
        "phase101_enforcement_snapshot_id": evidence.get("phase101_enforcement_snapshot_id", ""),
        "phase101_enforcement_digest": evidence.get("phase101_enforcement_digest", ""),
        "phase102_drift_review_id": evidence.get("phase102_drift_review_id", ""),
        "phase102_drift_digest": evidence.get("phase102_drift_digest", ""),
        "strict_audit_status": evidence.get("strict_audit_status", ""),
        "strict_audit_command_result": evidence.get("strict_audit_command_result", ""),
        "immutable_manifest_status": evidence.get("immutable_manifest_status", ""),
        "immutable_manifest_command_result": evidence.get("immutable_manifest_command_result", ""),
        "architecture_classification_digest": evidence.get("architecture_classification_digest", ""),
        "prompt_boundary_scan_target_count": evidence.get("prompt_boundary_scan_target_count", 0),
        "finding_count": evidence.get("finding_count", 0),
        "phase100_closure_custody": dimensions.get("phase100_closure_custody", ""),
        "phase101_enforcement_custody": dimensions.get("phase101_enforcement_custody", ""),
        "phase102_drift_review_custody": dimensions.get("phase102_drift_review_custody", ""),
        "strict_audit_verification_custody": dimensions.get("strict_audit_verification_custody", ""),
        "immutable_manifest_verification_custody": dimensions.get("immutable_manifest_verification_custody", ""),
        "release_blocked": data.get("release_blocked", False),
        "metadata_only": data.get("metadata_only", False),
        "audit_verified": data.get("audit_verified", False),
        "immutable_verified": data.get("immutable_verified", False),
        "no_provider": data.get("no_provider", False),
        "no_network": data.get("no_network", False),
        "no_export": data.get("no_export", False),
        "no_clearance": data.get("no_clearance", False),
        "no_unblock": data.get("no_unblock", False),
        "custody_digest": data.get("custody_digest", ""),
    }
