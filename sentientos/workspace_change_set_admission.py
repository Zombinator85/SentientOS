"""Metadata-only admission for proposed workspace change sets.

This wing sits before workspace change-set preflight. It inspects caller-supplied
proposal metadata only and decides whether the proposal is eligible to be handed
to the existing preflight/planning wing. It never reads workspace target files,
checks target existence, computes filesystem digests, builds preflight/rollback/
transaction plans, executes, verifies replay, closes lifecycle state, cleans up,
or invokes subprocess, shell, network, provider, prompt, service, power,
hardware, package, driver, plugin, generated-code, or federation execution.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from sentientos.workspace_change_set_preflight import CHANGE_OPERATIONS, DEFAULT_CREATED_AT, WILDCARD_CHARS

ADMISSION_STATUSES = frozenset({
    "admission_accepted",
    "admission_accepted_with_warnings",
    "admission_blocked",
    "admission_contradicted",
    "admission_insufficient_metadata",
})

ADMISSION_REQUIRED_TARGET_FIELDS = ("target_id", "relative_target_path", "operation")
ADMISSION_PAYLOAD_BODY_KEYS = frozenset({
    "payload",
    "payload_text",
    "payload_body",
    "content",
    "body",
    "preimage",
    "preimage_body",
    "prompt",
    "prompt_text",
    "secret",
    "secrets",
    "provider_material",
    "runtime_handle",
    "file_content",
    "filesystem_content",
})
ADMISSION_FORBIDDEN_AUTHORITY_LABELS = frozenset({
    "cleanup",
    "delete",
    "file_delete",
    "directory_cleanup",
    "recursive_delete",
    "wildcard_delete",
    "unrelated_delete",
    "unrelated_file_delete",
    "subprocess",
    "subprocess_execution",
    "shell",
    "shell_execution",
    "network",
    "network_egress",
    "provider",
    "provider_invocation",
    "prompt",
    "prompt_assembly",
    "prompt_export",
    "prompt_assembly_export",
    "service",
    "service_control",
    "service_restart",
    "power",
    "power_control",
    "power_profile_mutation",
    "fan",
    "fan_pwm",
    "fan_pwm_write",
    "thermal",
    "thermal_actuation",
    "hardware",
    "hardware_control",
    "package",
    "package_install",
    "driver",
    "driver_install",
    "plugin",
    "plugin_execution",
    "generated_code",
    "generated_code_execution",
    "federation",
    "federation_execution",
    "federation_import_execution",
    "remote_execution",
})
ADMISSION_CONTRADICTION_FLAG_NAMES = frozenset({
    "metadata_only_false",
    "preflight_already_run",
    "preflight_performed",
    "transaction_plan_built",
    "rollback_plan_built",
    "execution_performed",
    "rollback_performed",
    "verification_replay_performed",
    "closure_built",
    "cleanup_performed",
    "target_write_performed",
    "host_mutation_performed",
    "subprocess_used",
    "shell_used",
    "network_used",
    "provider_invocation_performed",
    "prompt_assembly_performed",
    "service_control_performed",
    "power_control_performed",
    "fan_pwm_write_performed",
    "thermal_actuation_performed",
    "package_install_performed",
    "driver_install_performed",
    "plugin_execution_performed",
    "generated_code_execution_performed",
    "federation_execution_performed",
})
BOUNDARY_NOTES = (
    "metadata_only_admission",
    "non_authorizing_decision",
    "does_not_prove_workspace_state",
    "does_not_authorize_execution",
    "preflight_may_be_attempted_only_when_true",
)


@dataclass(frozen=True)
class WorkspaceChangeSetAdmissionPolicy:
    max_targets: int = 8
    max_payload_bytes_per_target: int = 65536
    max_total_payload_bytes: int = 262144
    allow_create: bool = True
    allow_update: bool = True
    allow_replace: bool = True
    metadata_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceChangeSetProposedTargetSummary:
    target_id: str
    relative_target_path: str
    normalized_relative_path: str
    operation: str
    declared_payload_byte_count: int | None = None
    declared_payload_digest: str | None = None
    payload_media_type: str | None = None
    requested_authority_labels: tuple[str, ...] = ()
    warning_codes: tuple[str, ...] = ()
    blocker_codes: tuple[str, ...] = ()
    metadata_only: bool = True
    payload_body_included: bool = False
    filesystem_read_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceChangeSetAdmissionFinding:
    code: str
    severity: str
    target_id: str | None = None
    relative_target_path: str | None = None
    authority_label: str | None = None
    detail: str | None = None
    metadata_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceChangeSetAdmissionRequest:
    request_id: str
    declared_target_count: int | None
    proposed_targets: tuple[WorkspaceChangeSetProposedTargetSummary, ...]
    requested_authority_labels: tuple[str, ...]
    proposal_flags: Mapping[str, Any]
    created_at: str
    digest: str
    metadata_only: bool = True
    admission_request_only: bool = True
    payload_bodies_included: bool = False
    workspace_files_read: bool = False
    preflight_performed: bool = False
    transaction_plan_built: bool = False
    execution_performed: bool = False
    rollback_performed: bool = False
    verification_replay_performed: bool = False
    lifecycle_closure_built: bool = False
    cleanup_performed: bool = False
    subprocess_used: bool = False
    shell_used: bool = False
    network_used: bool = False
    provider_invocation_performed: bool = False
    prompt_assembly_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["proposal_flags"] = dict(self.proposal_flags)
        return data


@dataclass(frozen=True)
class WorkspaceChangeSetAdmissionDecision:
    decision_id: str
    request_id: str
    admission_status: str
    proposed_target_count: int
    declared_target_count: int | None
    proposed_operation_types: tuple[str, ...]
    proposed_payload_byte_counts: tuple[int | None, ...]
    declared_payload_digests: tuple[str | None, ...]
    findings: tuple[WorkspaceChangeSetAdmissionFinding, ...]
    blocker_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    forbidden_authority_findings: tuple[str, ...]
    preflight_may_be_attempted_next: bool
    boundary_notes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    admission_only: bool = True
    non_authorizing: bool = True
    workspace_files_read: bool = False
    filesystem_existence_checked: bool = False
    filesystem_digests_computed: bool = False
    preflight_performed: bool = False
    transaction_plan_built: bool = False
    execution_performed: bool = False
    rollback_performed: bool = False
    verification_replay_performed: bool = False
    lifecycle_closure_built: bool = False
    cleanup_performed: bool = False
    subprocess_used: bool = False
    shell_used: bool = False
    network_used: bool = False
    provider_invocation_performed: bool = False
    prompt_assembly_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceChangeSetAdmissionWing:
    request: WorkspaceChangeSetAdmissionRequest
    decision: WorkspaceChangeSetAdmissionDecision
    artifact_path: str | None = None
    artifact_written: bool = False
    metadata_only: bool = True
    admission_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def _digest(prefix: str, payload: Mapping[str, Any]) -> str:
    data = dict(payload)
    data["digest"] = ""
    return prefix + hashlib.sha256(_canonical_json(data).encode("utf-8")).hexdigest()[:24]


def _normalize_label(value: Any) -> str:
    return str(value).strip().lower().replace("-", "_").replace("/", "_").replace(" ", "_")


def _tuple_labels(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (_normalize_label(value),) if value.strip() else ()
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return tuple(_normalize_label(item) for item in value if str(item).strip())
    return (_normalize_label(value),)


def _normalized_relative_path(path_text: str) -> str:
    text = path_text.replace("\\", "/")
    pure = PurePosixPath(text)
    parts: list[str] = []
    for part in pure.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            else:
                parts.append("..")
        else:
            parts.append(part)
    return "/".join(parts)


def _path_blockers(path_text: str) -> tuple[str, ...]:
    blockers: list[str] = []
    text = str(path_text)
    stripped = text.strip()
    normalized = _normalized_relative_path(text)
    parts = PurePosixPath(text.replace("\\", "/")).parts
    if not stripped:
        blockers.append("empty_target_path")
    if stripped in {".", "./", "\\"} or normalized == "":
        blockers.append("root_target_path")
    if PurePosixPath(text.replace("\\", "/")).is_absolute():
        blockers.append("absolute_target_path")
    if ".." in parts or normalized == ".." or normalized.startswith("../"):
        blockers.append("path_traversal")
    if any(ch in text for ch in WILDCARD_CHARS):
        blockers.append("wildcard_target_path")
    if stripped.endswith(("/", "\\")):
        blockers.append("directory_like_target_path")
    if text.startswith("workspace://outside") or text.startswith("outside:"):
        blockers.append("outside_workspace_claim")
    return tuple(dict.fromkeys(blockers))


def _metadata_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("boolean is not a byte count")
    number = int(value)
    if number < 0:
        raise ValueError("negative byte count")
    return number


def _target_from_mapping(raw: Mapping[str, Any], index: int) -> WorkspaceChangeSetProposedTargetSummary:
    target_id = str(raw.get("target_id", ""))
    path = str(raw.get("relative_target_path", raw.get("path", "")))
    operation = str(raw.get("operation", ""))
    try:
        byte_count = _metadata_int(raw.get("declared_payload_byte_count", raw.get("payload_byte_count")))
    except (TypeError, ValueError):
        byte_count = None
    digest = raw.get("declared_payload_digest", raw.get("payload_digest"))
    labels = _tuple_labels(raw.get("requested_authority_labels", raw.get("authority_labels")))
    body_included = any(key in raw and raw.get(key) not in (None, "") for key in ADMISSION_PAYLOAD_BODY_KEYS)
    summary = WorkspaceChangeSetProposedTargetSummary(
        target_id=target_id,
        relative_target_path=path,
        normalized_relative_path=_normalized_relative_path(path),
        operation=operation,
        declared_payload_byte_count=byte_count,
        declared_payload_digest=str(digest) if digest not in (None, "") else None,
        payload_media_type=str(raw.get("payload_media_type")) if raw.get("payload_media_type") else None,
        requested_authority_labels=labels,
        payload_body_included=body_included,
    )
    return summary if target_id else replace(summary, target_id=f"missing-target-id-{index}")


def build_workspace_change_set_admission_request(
    proposal: Mapping[str, Any],
    *,
    created_at: str = DEFAULT_CREATED_AT,
) -> WorkspaceChangeSetAdmissionRequest:
    raw_targets = proposal.get("proposed_targets", proposal.get("targets"))
    targets: tuple[WorkspaceChangeSetProposedTargetSummary, ...]
    if isinstance(raw_targets, Sequence) and not isinstance(raw_targets, (str, bytes, bytearray)):
        targets = tuple(_target_from_mapping(target if isinstance(target, Mapping) else {}, index) for index, target in enumerate(raw_targets))
    else:
        targets = ()
    declared_count_raw = proposal.get("declared_target_count", proposal.get("target_count"))
    try:
        declared_count = None if declared_count_raw is None else _metadata_int(declared_count_raw)
    except (TypeError, ValueError):
        declared_count = None
    labels = _tuple_labels(proposal.get("requested_authority_labels", proposal.get("authority_labels")))
    flags = proposal.get("proposal_flags", proposal.get("flags", {}))
    flag_map = dict(flags) if isinstance(flags, Mapping) else {}
    payload_bodies_included = any(key in proposal and proposal.get(key) not in (None, "") for key in ADMISSION_PAYLOAD_BODY_KEYS) or any(t.payload_body_included for t in targets)
    request_id = str(proposal.get("request_id") or "workspace-change-set-admission-request-" + hashlib.sha256(_canonical_json({"targets": [t.to_dict() for t in targets], "declared": declared_count, "labels": labels, "created_at": created_at}).encode("utf-8")).hexdigest()[:16])
    record = WorkspaceChangeSetAdmissionRequest(
        request_id=request_id,
        declared_target_count=declared_count,
        proposed_targets=targets,
        requested_authority_labels=labels,
        proposal_flags=flag_map,
        created_at=created_at,
        digest="",
        payload_bodies_included=payload_bodies_included,
    )
    return replace(record, digest=_digest("workspace-change-set-admission-request-", record.to_dict()))


def _finding(code: str, severity: str, target: WorkspaceChangeSetProposedTargetSummary | None = None, *, authority_label: str | None = None, detail: str | None = None) -> WorkspaceChangeSetAdmissionFinding:
    return WorkspaceChangeSetAdmissionFinding(
        code=code,
        severity=severity,
        target_id=target.target_id if target else None,
        relative_target_path=target.relative_target_path if target else None,
        authority_label=authority_label,
        detail=detail,
    )


def decide_workspace_change_set_admission(
    request: WorkspaceChangeSetAdmissionRequest,
    *,
    policy: WorkspaceChangeSetAdmissionPolicy | None = None,
    created_at: str = DEFAULT_CREATED_AT,
) -> WorkspaceChangeSetAdmissionDecision:
    policy = policy or WorkspaceChangeSetAdmissionPolicy()
    findings: list[WorkspaceChangeSetAdmissionFinding] = []
    if request.declared_target_count is None:
        findings.append(_finding("missing_declared_target_count", "insufficient_metadata"))
    if not request.proposed_targets:
        findings.append(_finding("missing_proposed_targets", "insufficient_metadata"))
    elif request.declared_target_count is not None and request.declared_target_count != len(request.proposed_targets):
        findings.append(_finding("declared_target_count_mismatch", "contradiction", detail=f"declared={request.declared_target_count}; supplied={len(request.proposed_targets)}"))
    if len(request.proposed_targets) > policy.max_targets:
        findings.append(_finding("target_count_over_limit", "blocker"))
    if request.payload_bodies_included:
        findings.append(_finding("payload_body_supplied_to_metadata_only_admission", "blocker"))

    seen_ids: set[str] = set()
    seen_paths: dict[str, WorkspaceChangeSetProposedTargetSummary] = {}
    total_bytes = 0
    for target in request.proposed_targets:
        if not target.target_id or target.target_id.startswith("missing-target-id-"):
            findings.append(_finding("missing_target_id", "insufficient_metadata", target))
        elif target.target_id in seen_ids:
            findings.append(_finding("duplicate_target_id", "blocker", target))
        seen_ids.add(target.target_id)
        if not target.relative_target_path:
            findings.append(_finding("missing_relative_target_path", "insufficient_metadata", target))
        if not target.operation:
            findings.append(_finding("missing_operation", "insufficient_metadata", target))
        elif target.operation not in CHANGE_OPERATIONS:
            findings.append(_finding("unsupported_operation", "blocker", target))
        if target.operation == "replace_file" and not policy.allow_replace:
            findings.append(_finding("replace_operation_not_allowed", "blocker", target))
        if target.operation == "create_file" and not policy.allow_create:
            findings.append(_finding("create_operation_not_allowed", "blocker", target))
        if target.operation == "update_file" and not policy.allow_update:
            findings.append(_finding("update_operation_not_allowed", "blocker", target))
        for code in _path_blockers(target.relative_target_path):
            findings.append(_finding(code, "blocker", target))
        normalized = target.normalized_relative_path
        if normalized and normalized in seen_paths:
            findings.append(_finding("duplicate_target_path", "blocker", target, detail=seen_paths[normalized].target_id))
        elif normalized:
            seen_paths[normalized] = target
        if target.declared_payload_byte_count is None:
            findings.append(_finding("declared_payload_byte_count_missing", "warning", target))
        else:
            total_bytes += target.declared_payload_byte_count
            if target.declared_payload_byte_count > policy.max_payload_bytes_per_target:
                findings.append(_finding("payload_bytes_over_per_target_limit", "blocker", target))
        if target.declared_payload_digest is None:
            findings.append(_finding("declared_payload_digest_missing", "warning", target))
        for label in target.requested_authority_labels:
            if label in ADMISSION_FORBIDDEN_AUTHORITY_LABELS:
                findings.append(_finding("forbidden_requested_authority", "blocker", target, authority_label=label))
    if total_bytes > policy.max_total_payload_bytes:
        findings.append(_finding("total_payload_bytes_over_limit", "blocker"))
    for label in request.requested_authority_labels:
        if label in ADMISSION_FORBIDDEN_AUTHORITY_LABELS:
            findings.append(_finding("forbidden_requested_authority", "blocker", authority_label=label))
    for flag, value in request.proposal_flags.items():
        normalized = _normalize_label(flag)
        if normalized in ADMISSION_CONTRADICTION_FLAG_NAMES and bool(value):
            findings.append(_finding(f"contradiction:{normalized}", "contradiction"))
        if normalized == "metadata_only" and value is False:
            findings.append(_finding("contradiction:metadata_only_false", "contradiction"))
    if request.metadata_only is False or policy.metadata_only is False:
        findings.append(_finding("contradiction:metadata_only_false", "contradiction"))

    blocker_codes = tuple(sorted({f.code for f in findings if f.severity == "blocker"}))
    warning_codes = tuple(sorted({f.code for f in findings if f.severity == "warning"}))
    insufficient = tuple(sorted({f.code for f in findings if f.severity == "insufficient_metadata"}))
    contradictions = tuple(sorted({f.code for f in findings if f.severity == "contradiction"}))
    forbidden = tuple(sorted({f.authority_label or f.code for f in findings if f.code == "forbidden_requested_authority"}))
    if contradictions:
        status = "admission_contradicted"
    elif insufficient:
        status = "admission_insufficient_metadata"
    elif blocker_codes:
        status = "admission_blocked"
    elif warning_codes:
        status = "admission_accepted_with_warnings"
    else:
        status = "admission_accepted"
    may_preflight = status in {"admission_accepted", "admission_accepted_with_warnings"}
    record = WorkspaceChangeSetAdmissionDecision(
        decision_id="workspace-change-set-admission-decision-" + hashlib.sha256(f"{request.request_id}\0{created_at}".encode("utf-8")).hexdigest()[:16],
        request_id=request.request_id,
        admission_status=status,
        proposed_target_count=len(request.proposed_targets),
        declared_target_count=request.declared_target_count,
        proposed_operation_types=tuple(sorted({target.operation for target in request.proposed_targets if target.operation})),
        proposed_payload_byte_counts=tuple(target.declared_payload_byte_count for target in request.proposed_targets),
        declared_payload_digests=tuple(target.declared_payload_digest for target in request.proposed_targets),
        findings=tuple(findings),
        blocker_codes=tuple(sorted(set(blocker_codes + insufficient + contradictions))),
        warning_codes=warning_codes,
        forbidden_authority_findings=forbidden,
        preflight_may_be_attempted_next=may_preflight,
        boundary_notes=BOUNDARY_NOTES,
        created_at=created_at,
        digest="",
    )
    return replace(record, digest=_digest("workspace-change-set-admission-decision-", record.to_dict()))


def build_workspace_change_set_admission_artifact(wing: WorkspaceChangeSetAdmissionWing | Mapping[str, Any]) -> dict[str, Any]:
    payload = wing.to_dict() if hasattr(wing, "to_dict") else dict(wing)
    # Never include caller-supplied proposal bodies; the request only contains compact summaries.
    return {
        "schema_version": "host-workspace-change-set-admission-wing.v1",
        "metadata_only": True,
        "admission_only": True,
        "request": payload["request"],
        "decision": payload["decision"],
        "artifact_written": bool(payload.get("artifact_written", False)),
        "artifact_path": payload.get("artifact_path"),
    }


def write_workspace_change_set_admission_artifact(wing: WorkspaceChangeSetAdmissionWing, output_path: str | Path) -> WorkspaceChangeSetAdmissionWing:
    path = Path(output_path).expanduser()
    artifact = build_workspace_change_set_admission_artifact(replace(wing, artifact_path=str(path), artifact_written=True))
    path.write_text(json.dumps(artifact, sort_keys=True, indent=2, ensure_ascii=True, default=str) + "\n", encoding="utf-8")
    return replace(wing, artifact_path=str(path), artifact_written=True)


def run_workspace_change_set_admission_wing(
    proposal: Mapping[str, Any],
    *,
    policy: WorkspaceChangeSetAdmissionPolicy | None = None,
    artifact_output_path: str | Path | None = None,
    created_at: str = DEFAULT_CREATED_AT,
) -> WorkspaceChangeSetAdmissionWing:
    request = build_workspace_change_set_admission_request(proposal, created_at=created_at)
    decision = decide_workspace_change_set_admission(request, policy=policy, created_at=created_at)
    wing = WorkspaceChangeSetAdmissionWing(request=request, decision=decision)
    if artifact_output_path is not None:
        wing = write_workspace_change_set_admission_artifact(wing, artifact_output_path)
    return wing


def summarize_workspace_change_set_admission_decision(decision: WorkspaceChangeSetAdmissionDecision) -> dict[str, Any]:
    return {
        "admission_status": decision.admission_status,
        "proposed_target_count": decision.proposed_target_count,
        "declared_target_count": decision.declared_target_count,
        "proposed_operation_types": decision.proposed_operation_types,
        "blocker_codes": decision.blocker_codes,
        "warning_codes": decision.warning_codes,
        "forbidden_authority_findings": decision.forbidden_authority_findings,
        "preflight_may_be_attempted_next": decision.preflight_may_be_attempted_next,
        "metadata_only": decision.metadata_only,
        "non_authorizing": decision.non_authorizing,
        "digest": decision.digest,
    }


__all__ = [
    "ADMISSION_STATUSES",
    "WorkspaceChangeSetAdmissionDecision",
    "WorkspaceChangeSetAdmissionFinding",
    "WorkspaceChangeSetAdmissionPolicy",
    "WorkspaceChangeSetAdmissionRequest",
    "WorkspaceChangeSetAdmissionWing",
    "WorkspaceChangeSetProposedTargetSummary",
    "build_workspace_change_set_admission_artifact",
    "build_workspace_change_set_admission_request",
    "decide_workspace_change_set_admission",
    "run_workspace_change_set_admission_wing",
    "summarize_workspace_change_set_admission_decision",
    "write_workspace_change_set_admission_artifact",
]
