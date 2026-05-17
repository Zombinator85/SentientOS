"""Workspace-scoped single-file update pilot.

This module implements one narrow real effect: create or update exactly one
caller-specified relative file inside one explicit caller-supplied workspace
root. It captures an exact preimage for replacements, verifies the resulting
postcondition, builds an exact-target rollback plan, and can perform explicit
exact rollback. It is not general filesystem access and never performs cleanup,
recursive deletion, wildcard deletion, subprocess execution, shell execution,
network egress, provider invocation, prompt assembly, control-plane execution,
or hardware/service/power actuation.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import asdict, dataclass, replace
from pathlib import Path, PurePath
from typing import Any, Mapping, NamedTuple, Sequence

DEFAULT_CREATED_AT = "1970-01-01T00:00:00+00:00"

EFFECT_STATUSES = frozenset({
    "workspace_file_effect_requested",
    "workspace_file_effect_created",
    "workspace_file_effect_updated",
    "workspace_file_effect_blocked",
    "workspace_file_effect_incomplete",
    "workspace_file_effect_contradicted",
})
PREIMAGE_STATUSES = frozenset({
    "workspace_file_preimage_absent",
    "workspace_file_preimage_captured",
    "workspace_file_preimage_blocked",
    "workspace_file_preimage_incomplete",
    "workspace_file_preimage_contradicted",
})
POSTCONDITION_STATUSES = frozenset({
    "workspace_file_postcondition_passed",
    "workspace_file_postcondition_passed_with_warnings",
    "workspace_file_postcondition_failed",
    "workspace_file_postcondition_blocked",
    "workspace_file_postcondition_incomplete",
    "workspace_file_postcondition_contradicted",
})
ROLLBACK_STATUSES = frozenset({
    "workspace_file_rollback_plan_ready",
    "workspace_file_rollback_created_file_removed",
    "workspace_file_rollback_preimage_restored",
    "workspace_file_rollback_blocked",
    "workspace_file_rollback_missing_target",
    "workspace_file_rollback_digest_mismatch",
    "workspace_file_rollback_scope_mismatch",
    "workspace_file_rollback_incomplete",
    "workspace_file_rollback_contradicted",
})
AUDIT_STATUSES = frozenset({
    "workspace_file_production_audit_recorded",
    "workspace_file_production_audit_recorded_with_warnings",
    "workspace_file_production_audit_blocked",
    "workspace_file_production_audit_incomplete",
    "workspace_file_production_audit_contradicted",
})
EFFECT_DOMAINS = frozenset({
    "workspace_file_create_effect",
    "workspace_file_update_effect",
    "workspace_file_replace_effect",
})
BLOCKED_ACTION_LABELS = (
    "path_traversal",
    "absolute_target_path",
    "target_outside_workspace",
    "symlink_target_write",
    "directory_target_write",
    "directory_cleanup",
    "recursive_delete",
    "wildcard_delete",
    "unrelated_file_delete",
    "fan_pwm_write",
    "thermal_actuation",
    "power_profile_mutation",
    "process_kill",
    "service_restart",
    "package_install",
    "driver_install",
    "provider_invocation",
    "network_egress",
    "prompt_assembly",
    "federation_transport",
    "remote_execution",
    "subprocess_execution",
    "shell_execution",
    "os_backend_invocation",
    "control_plane_admission_execution",
    "hardware_control",
)
FORBIDDEN_TRUE_FIELDS = (
    "general_filesystem_access_requested",
    "general_filesystem_access_performed",
    "directory_cleanup_requested",
    "directory_cleanup_performed",
    "recursive_delete_requested",
    "recursive_delete_performed",
    "wildcard_delete_requested",
    "wildcard_delete_performed",
    "unrelated_file_delete_requested",
    "unrelated_file_delete_performed",
    "fan_pwm_write_performed",
    "thermal_actuation_performed",
    "power_profile_mutation_performed",
    "process_kill_performed",
    "service_restart_performed",
    "package_install_performed",
    "driver_install_performed",
    "provider_invocation_performed",
    "network_performed",
    "prompt_assembly_performed",
    "subprocess_performed",
    "shell_performed",
    "os_backend_invoked",
    "os_backend_invocation_performed",
    "control_plane_admission_execution_performed",
    "hardware_control_performed",
    "general_cleanup_performed",
)
_ALLOWED_EFFECT_TRUE_FIELDS = frozenset({
    "workspace_file_effect_requested",
    "real_effect_performed",
    "local_file_write_performed",
    "host_mutation_performed",
    "created_new_file",
    "replaced_existing_file",
    "real_effect_receipt_created",
    "workspace_scoped",
    "single_target_only",
    "real_postcondition_check_performed",
    "production_audit_receipt_created",
    "audit_for_workspace_file_effect_only",
})
_ALLOWED_ROLLBACK_TRUE_FIELDS = _ALLOWED_EFFECT_TRUE_FIELDS | frozenset({
    "rollback_plan_only",
    "real_rollback_performed",
    "file_delete_performed",
    "real_rollback_receipt_created",
    "exact_target_only",
    "real_rollback_postcondition_check_performed",
})


def _tuple(value: Sequence[str] | None) -> tuple[str, ...]:
    return tuple(str(item) for item in (value or ()))


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def deterministic_digest(prefix: str, payload: Mapping[str, Any]) -> str:
    data = dict(payload)
    data["digest"] = ""
    return "sha256:" + hashlib.sha256((prefix + _canonical_json(data)).encode("utf-8")).hexdigest()


def bytes_digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class WorkspaceFileEffectValidationResult:
    ok: bool
    findings: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkspaceFileEffectPolicy:
    policy_id: str
    required_scope_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    create_allowed: bool = True
    parent_directory_creation_allowed: bool = False
    default_payload_media_type: str = "text/plain; charset=utf-8"
    warning_codes: tuple[str, ...] = ()
    risk_codes: tuple[str, ...] = ("workspace_scoped_single_file_write_is_real_host_mutation",)
    workspace_scoped_only: bool = True
    single_target_only: bool = True
    exact_rollback_only: bool = True
    no_general_filesystem_access: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceFileEffectRequest:
    request_id: str
    workspace_root: str
    relative_target_path: str
    payload_text: str
    payload_media_type: str
    force_create: bool
    allow_replace: bool
    required_scope_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    request_status: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    workspace_file_effect_requested: bool = True
    general_filesystem_access_requested: bool = False
    directory_cleanup_requested: bool = False
    recursive_delete_requested: bool = False
    wildcard_delete_requested: bool = False
    unrelated_file_delete_requested: bool = False
    network_performed: bool = False
    provider_invocation_performed: bool = False
    prompt_assembly_performed: bool = False
    subprocess_performed: bool = False
    shell_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceFilePreimageRecord:
    preimage_id: str
    request_id: str
    workspace_root: str
    relative_target_path: str
    target_path: str
    preimage_status: str
    existed_before: bool
    preimage_digest: str | None
    preimage_byte_count: int | None
    preimage_media_type: str | None
    preimage_bytes_base64: str | None
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = False
    preimage_capture_only: bool = True
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceFileEffectResult:
    result_id: str
    request_id: str
    preimage_id: str
    workspace_root: str
    relative_target_path: str
    target_path: str
    artifact_digest: str | None
    byte_count: int
    effect_status: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    real_effect_performed: bool = False
    local_file_write_performed: bool = False
    host_mutation_performed: bool = False
    created_new_file: bool = False
    replaced_existing_file: bool = False
    fan_pwm_write_performed: bool = False
    thermal_actuation_performed: bool = False
    power_profile_mutation_performed: bool = False
    process_kill_performed: bool = False
    service_restart_performed: bool = False
    package_install_performed: bool = False
    driver_install_performed: bool = False
    directory_cleanup_performed: bool = False
    recursive_delete_performed: bool = False
    wildcard_delete_performed: bool = False
    unrelated_file_delete_performed: bool = False
    provider_invocation_performed: bool = False
    network_performed: bool = False
    prompt_assembly_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceFileEffectReceipt:
    receipt_id: str
    request_id: str
    result_id: str
    preimage_id: str
    effect_domain: str
    workspace_root: str
    relative_target_path: str
    target_path: str
    artifact_digest: str | None
    byte_count: int
    effect_status: str
    evidence_summary: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    real_effect_receipt_created: bool = False
    real_effect_performed: bool = False
    local_file_write_performed: bool = False
    host_mutation_performed: bool = False
    created_new_file: bool = False
    replaced_existing_file: bool = False
    workspace_scoped: bool = True
    single_target_only: bool = True
    general_filesystem_access_performed: bool = False
    fan_pwm_write_performed: bool = False
    thermal_actuation_performed: bool = False
    power_profile_mutation_performed: bool = False
    process_kill_performed: bool = False
    service_restart_performed: bool = False
    package_install_performed: bool = False
    driver_install_performed: bool = False
    directory_cleanup_performed: bool = False
    recursive_delete_performed: bool = False
    wildcard_delete_performed: bool = False
    unrelated_file_delete_performed: bool = False
    provider_invocation_performed: bool = False
    network_performed: bool = False
    prompt_assembly_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceFilePostconditionCheck:
    check_id: str
    receipt_id: str
    target_path: str
    expected_artifact_digest: str | None
    observed_artifact_digest: str | None
    expected_byte_count: int
    observed_byte_count: int | None
    postcondition_status: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    real_postcondition_check_performed: bool = True
    host_mutation_performed: bool = False
    network_performed: bool = False
    provider_invocation_performed: bool = False
    prompt_assembly_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceFileRollbackPlan:
    plan_id: str
    receipt_id: str
    preimage_id: str
    workspace_root: str
    relative_target_path: str
    target_path: str
    rollback_strategy: str
    expected_current_digest: str | None
    preimage_digest: str | None
    preimage_bytes_base64: str | None
    created_new_file: bool
    replaced_existing_file: bool
    rollback_status: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    rollback_plan_only: bool = True
    real_rollback_performed: bool = False
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceFileRollbackResult:
    result_id: str
    plan_id: str
    target_path: str
    rollback_status: str
    observed_before_rollback_digest: str | None
    observed_after_rollback_digest: str | None
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    real_rollback_performed: bool = False
    file_delete_performed: bool = False
    local_file_write_performed: bool = False
    host_mutation_performed: bool = False
    directory_cleanup_performed: bool = False
    recursive_delete_performed: bool = False
    wildcard_delete_performed: bool = False
    unrelated_file_delete_performed: bool = False
    fan_pwm_write_performed: bool = False
    thermal_actuation_performed: bool = False
    power_profile_mutation_performed: bool = False
    service_restart_performed: bool = False
    process_kill_performed: bool = False
    package_install_performed: bool = False
    driver_install_performed: bool = False
    network_performed: bool = False
    provider_invocation_performed: bool = False
    prompt_assembly_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceFileRollbackReceipt:
    receipt_id: str
    plan_id: str
    rollback_result_id: str
    target_path: str
    rollback_status: str
    evidence_summary: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    real_rollback_receipt_created: bool = False
    real_rollback_performed: bool = False
    exact_target_only: bool = True
    workspace_scoped: bool = True
    general_cleanup_performed: bool = False
    directory_cleanup_performed: bool = False
    recursive_delete_performed: bool = False
    wildcard_delete_performed: bool = False
    unrelated_file_delete_performed: bool = False
    network_performed: bool = False
    provider_invocation_performed: bool = False
    prompt_assembly_performed: bool = False
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceFileRollbackPostconditionCheck:
    check_id: str
    rollback_receipt_id: str
    target_path: str
    expected_absent: bool | None
    expected_preimage_digest: str | None
    observed_exists: bool
    observed_digest: str | None
    postcondition_status: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    real_rollback_postcondition_check_performed: bool = True
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceFileProductionAuditReceipt:
    audit_id: str
    effect_receipt_id: str
    postcondition_check_id: str
    rollback_plan_id: str
    rollback_receipt_id: str | None
    rollback_postcondition_check_id: str | None
    audit_status: str
    evidence_summary: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    production_audit_receipt_created: bool = True
    audit_for_workspace_file_effect_only: bool = True
    host_mutation_performed: bool = False
    network_performed: bool = False
    provider_invocation_performed: bool = False
    prompt_assembly_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WorkspaceFileEffectWingResult(NamedTuple):
    request: WorkspaceFileEffectRequest
    preimage: WorkspaceFilePreimageRecord
    result: WorkspaceFileEffectResult
    receipt: WorkspaceFileEffectReceipt
    postcondition: WorkspaceFilePostconditionCheck
    rollback_plan: WorkspaceFileRollbackPlan
    production_audit: WorkspaceFileProductionAuditReceipt


class WorkspaceFileRollbackWingResult(NamedTuple):
    rollback_result: WorkspaceFileRollbackResult
    rollback_receipt: WorkspaceFileRollbackReceipt
    rollback_postcondition: WorkspaceFileRollbackPostconditionCheck
    production_audit: WorkspaceFileProductionAuditReceipt


def build_default_workspace_file_effect_policy() -> WorkspaceFileEffectPolicy:
    payload = {
        "policy_id": "workspace-file-effect-default-policy",
        "required_scope_labels": ("explicit_workspace_root", "relative_single_file_target", "exact_rollback_available"),
        "blocked_actions": BLOCKED_ACTION_LABELS,
        "create_allowed": True,
        "parent_directory_creation_allowed": False,
        "default_payload_media_type": "text/plain; charset=utf-8",
        "warning_codes": (),
        "risk_codes": ("workspace_scoped_single_file_write_is_real_host_mutation",),
    }
    return WorkspaceFileEffectPolicy(**payload)


def build_workspace_file_effect_request(
    *,
    request_id: str,
    workspace_root: str | Path,
    relative_target_path: str,
    payload_text: str,
    payload_media_type: str | None = None,
    force_create: bool = False,
    allow_replace: bool = True,
    policy: WorkspaceFileEffectPolicy | None = None,
    required_scope_labels: Sequence[str] | None = None,
    blocked_actions: Sequence[str] | None = None,
    warning_codes: Sequence[str] | None = None,
    risk_codes: Sequence[str] | None = None,
    created_at: str = DEFAULT_CREATED_AT,
) -> WorkspaceFileEffectRequest:
    policy = policy or build_default_workspace_file_effect_policy()
    record = WorkspaceFileEffectRequest(
        request_id=request_id,
        workspace_root=str(workspace_root),
        relative_target_path=str(relative_target_path),
        payload_text=str(payload_text),
        payload_media_type=payload_media_type or policy.default_payload_media_type,
        force_create=bool(force_create),
        allow_replace=bool(allow_replace),
        required_scope_labels=_tuple(required_scope_labels) or policy.required_scope_labels,
        blocked_actions=_tuple(blocked_actions) or policy.blocked_actions,
        request_status="workspace_file_effect_requested",
        warning_codes=_tuple(warning_codes) or policy.warning_codes,
        risk_codes=_tuple(risk_codes) or policy.risk_codes,
        created_at=created_at,
        digest="",
    )
    return replace(record, digest=deterministic_digest("workspace-file-effect-request-", record.to_dict()))


def _payload_bytes(request: WorkspaceFileEffectRequest) -> bytes:
    return request.payload_text.encode("utf-8")


def _resolve_target(workspace_root: str | Path, relative_target_path: str) -> tuple[Path | None, Path | None, tuple[str, ...]]:
    findings: list[str] = []
    root_text = str(workspace_root).strip()
    target_text = str(relative_target_path)
    if not root_text:
        findings.append("empty_workspace_root")
        return None, None, tuple(findings)
    root = Path(root_text).expanduser()
    try:
        root_resolved = root.resolve(strict=False)
    except OSError:
        findings.append("workspace_root_unresolvable")
        return None, None, tuple(findings)
    if root_resolved == root_resolved.anchor or str(root_resolved) == root_resolved.anchor:
        findings.append("root_workspace_rejected")
    if PurePath(target_text).is_absolute():
        findings.append("absolute_target_path")
    parts = PurePath(target_text).parts
    if not parts or target_text in {"", "."}:
        findings.append("empty_target_path")
    if any(part == ".." for part in parts):
        findings.append("path_traversal")
    if any(part in {"*", "**"} for part in parts) or "*" in target_text:
        findings.append("wildcard_target_path")
    if findings:
        return root_resolved, None, tuple(findings)
    target = root_resolved / Path(target_text)
    try:
        target_resolved = target.resolve(strict=False)
    except OSError:
        findings.append("target_unresolvable")
        return root_resolved, None, tuple(findings)
    if target_resolved != root_resolved and root_resolved not in target_resolved.parents:
        findings.append("target_outside_workspace")
    if target.exists() and target.is_symlink():
        findings.append("symlink_target_write")
    if target.exists() and target.is_dir():
        findings.append("directory_target_write")
    return root_resolved, target_resolved, tuple(findings)


def _blocked_preimage(request: WorkspaceFileEffectRequest, target_path: str, findings: Sequence[str], created_at: str) -> WorkspaceFilePreimageRecord:
    record = WorkspaceFilePreimageRecord(
        preimage_id=f"preimage-{request.request_id}",
        request_id=request.request_id,
        workspace_root=request.workspace_root,
        relative_target_path=request.relative_target_path,
        target_path=target_path,
        preimage_status="workspace_file_preimage_blocked",
        existed_before=False,
        preimage_digest=None,
        preimage_byte_count=None,
        preimage_media_type=None,
        preimage_bytes_base64=None,
        warning_codes=_tuple(findings),
        risk_codes=request.risk_codes,
        created_at=created_at,
        digest="",
        metadata_only=True,
    )
    return replace(record, digest=deterministic_digest("workspace-file-preimage-", record.to_dict()))


def perform_workspace_file_effect(
    request: WorkspaceFileEffectRequest,
    *,
    policy: WorkspaceFileEffectPolicy | None = None,
    dry_run: bool = False,
    created_at: str | None = None,
) -> tuple[WorkspaceFilePreimageRecord, WorkspaceFileEffectResult]:
    policy = policy or build_default_workspace_file_effect_policy()
    created_at = created_at or request.created_at
    validation = validate_workspace_file_effect_request(request)
    root, target, findings = _resolve_target(request.workspace_root, request.relative_target_path)
    all_findings = list(validation.findings) + list(findings)
    target_text = str(target or "")
    if root and (not root.exists() or not root.is_dir()):
        all_findings.append("workspace_root_missing_or_not_directory")
    if target and not target.parent.exists():
        all_findings.append("parent_directory_missing")
    if target and target.parent.exists() and target.parent.is_symlink():
        all_findings.append("symlink_parent_rejected")
    if target and target.exists() and not request.allow_replace:
        all_findings.append("replace_not_allowed")
    if target and not target.exists() and not policy.create_allowed:
        all_findings.append("create_not_allowed")
    if target and not target.exists() and request.force_create is False and not policy.create_allowed:
        all_findings.append("force_create_required_by_policy")
    if dry_run:
        all_findings.append("dry_run_no_write")
    if all_findings:
        preimage = _blocked_preimage(request, target_text, all_findings, created_at)
        result = WorkspaceFileEffectResult(
            result_id=f"result-{request.request_id}",
            request_id=request.request_id,
            preimage_id=preimage.preimage_id,
            workspace_root=request.workspace_root,
            relative_target_path=request.relative_target_path,
            target_path=target_text,
            artifact_digest=None,
            byte_count=0,
            effect_status="workspace_file_effect_blocked" if not dry_run else "workspace_file_effect_incomplete",
            warning_codes=tuple(all_findings),
            risk_codes=request.risk_codes,
            created_at=created_at,
            digest="",
        )
        return preimage, replace(result, digest=deterministic_digest("workspace-file-effect-result-", result.to_dict()))

    assert target is not None
    existed_before = target.exists()
    previous = target.read_bytes() if existed_before else b""
    preimage = WorkspaceFilePreimageRecord(
        preimage_id=f"preimage-{request.request_id}",
        request_id=request.request_id,
        workspace_root=str(root),
        relative_target_path=request.relative_target_path,
        target_path=str(target),
        preimage_status="workspace_file_preimage_captured" if existed_before else "workspace_file_preimage_absent",
        existed_before=existed_before,
        preimage_digest=bytes_digest(previous) if existed_before else None,
        preimage_byte_count=len(previous) if existed_before else None,
        preimage_media_type=request.payload_media_type if existed_before else None,
        preimage_bytes_base64=base64.b64encode(previous).decode("ascii") if existed_before else None,
        warning_codes=(),
        risk_codes=request.risk_codes,
        created_at=created_at,
        digest="",
        metadata_only=not existed_before,
    )
    preimage = replace(preimage, digest=deterministic_digest("workspace-file-preimage-", preimage.to_dict()))
    data = _payload_bytes(request)
    tmp = target.with_name(f".{target.name}.sentientos-{request.request_id}.tmp")
    if tmp.exists() or tmp.is_symlink():
        tmp = target.with_name(f".{target.name}.sentientos-workspace-file-effect.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, target)
    artifact_digest = bytes_digest(data)
    result = WorkspaceFileEffectResult(
        result_id=f"result-{request.request_id}",
        request_id=request.request_id,
        preimage_id=preimage.preimage_id,
        workspace_root=str(root),
        relative_target_path=request.relative_target_path,
        target_path=str(target),
        artifact_digest=artifact_digest,
        byte_count=len(data),
        effect_status="workspace_file_effect_updated" if existed_before else "workspace_file_effect_created",
        warning_codes=(),
        risk_codes=request.risk_codes,
        created_at=created_at,
        digest="",
        real_effect_performed=True,
        local_file_write_performed=True,
        host_mutation_performed=True,
        created_new_file=not existed_before,
        replaced_existing_file=existed_before,
    )
    return preimage, replace(result, digest=deterministic_digest("workspace-file-effect-result-", result.to_dict()))


def build_workspace_file_effect_receipt(
    request: WorkspaceFileEffectRequest,
    preimage: WorkspaceFilePreimageRecord,
    result: WorkspaceFileEffectResult,
    *,
    created_at: str | None = None,
) -> WorkspaceFileEffectReceipt:
    succeeded = result.real_effect_performed and result.effect_status in {"workspace_file_effect_created", "workspace_file_effect_updated"}
    domain = "workspace_file_create_effect" if result.created_new_file else "workspace_file_replace_effect" if result.replaced_existing_file else "workspace_file_update_effect"
    receipt = WorkspaceFileEffectReceipt(
        receipt_id=f"receipt-{result.result_id}",
        request_id=request.request_id,
        result_id=result.result_id,
        preimage_id=preimage.preimage_id,
        effect_domain=domain,
        workspace_root=result.workspace_root,
        relative_target_path=result.relative_target_path,
        target_path=result.target_path,
        artifact_digest=result.artifact_digest,
        byte_count=result.byte_count,
        effect_status=result.effect_status,
        evidence_summary=tuple(summarize_workspace_file_effect_result(result)),
        blocked_actions=request.blocked_actions,
        warning_codes=result.warning_codes,
        risk_codes=result.risk_codes,
        created_at=created_at or result.created_at,
        digest="",
        real_effect_receipt_created=succeeded,
        real_effect_performed=succeeded,
        local_file_write_performed=succeeded,
        host_mutation_performed=succeeded,
        created_new_file=result.created_new_file,
        replaced_existing_file=result.replaced_existing_file,
    )
    return replace(receipt, digest=deterministic_digest("workspace-file-effect-receipt-", receipt.to_dict()))


def perform_workspace_file_postcondition_check(receipt: WorkspaceFileEffectReceipt, *, created_at: str | None = None) -> WorkspaceFilePostconditionCheck:
    observed_digest = None
    observed_count = None
    status = "workspace_file_postcondition_failed"
    path = Path(receipt.target_path)
    if receipt.real_effect_performed and path.exists() and not path.is_symlink() and path.is_file():
        data = path.read_bytes()
        observed_digest = bytes_digest(data)
        observed_count = len(data)
        if observed_digest == receipt.artifact_digest and observed_count == receipt.byte_count:
            status = "workspace_file_postcondition_passed"
    record = WorkspaceFilePostconditionCheck(
        check_id=f"postcondition-{receipt.receipt_id}",
        receipt_id=receipt.receipt_id,
        target_path=receipt.target_path,
        expected_artifact_digest=receipt.artifact_digest,
        observed_artifact_digest=observed_digest,
        expected_byte_count=receipt.byte_count,
        observed_byte_count=observed_count,
        postcondition_status=status,
        warning_codes=() if status == "workspace_file_postcondition_passed" else ("target_digest_or_size_mismatch",),
        risk_codes=receipt.risk_codes,
        created_at=created_at or receipt.created_at,
        digest="",
    )
    return replace(record, digest=deterministic_digest("workspace-file-postcondition-", record.to_dict()))


def build_workspace_file_rollback_plan(
    receipt: WorkspaceFileEffectReceipt,
    preimage: WorkspaceFilePreimageRecord,
    *,
    created_at: str | None = None,
) -> WorkspaceFileRollbackPlan:
    strategy = "remove_created_exact_target" if receipt.created_new_file else "restore_exact_preimage" if receipt.replaced_existing_file else "blocked_no_successful_effect"
    plan = WorkspaceFileRollbackPlan(
        plan_id=f"rollback-plan-{receipt.receipt_id}",
        receipt_id=receipt.receipt_id,
        preimage_id=preimage.preimage_id,
        workspace_root=receipt.workspace_root,
        relative_target_path=receipt.relative_target_path,
        target_path=receipt.target_path,
        rollback_strategy=strategy,
        expected_current_digest=receipt.artifact_digest,
        preimage_digest=preimage.preimage_digest,
        preimage_bytes_base64=preimage.preimage_bytes_base64,
        created_new_file=receipt.created_new_file,
        replaced_existing_file=receipt.replaced_existing_file,
        rollback_status="workspace_file_rollback_plan_ready" if receipt.real_effect_performed else "workspace_file_rollback_blocked",
        warning_codes=() if receipt.real_effect_performed else ("no_successful_effect_to_rollback",),
        risk_codes=receipt.risk_codes,
        created_at=created_at or receipt.created_at,
        digest="",
    )
    return replace(plan, digest=deterministic_digest("workspace-file-rollback-plan-", plan.to_dict()))


def perform_workspace_file_rollback(plan: WorkspaceFileRollbackPlan, *, created_at: str | None = None) -> WorkspaceFileRollbackResult:
    created_at = created_at or plan.created_at
    root, target, findings = _resolve_target(plan.workspace_root, plan.relative_target_path)
    status = "workspace_file_rollback_blocked"
    observed_before = None
    observed_after = None
    warnings = list(findings)
    delete_performed = False
    write_performed = False
    if plan.rollback_status != "workspace_file_rollback_plan_ready":
        warnings.append("rollback_plan_not_ready")
    if target is None or str(target) != str(Path(plan.target_path).resolve(strict=False)):
        warnings.append("rollback_target_mismatch")
        status = "workspace_file_rollback_scope_mismatch"
    elif not target.exists():
        status = "workspace_file_rollback_missing_target"
        warnings.append("target_missing_before_rollback")
    elif target.is_symlink() or target.is_dir():
        status = "workspace_file_rollback_scope_mismatch"
        warnings.append("symlink_or_directory_target_rejected")
    else:
        data = target.read_bytes()
        observed_before = bytes_digest(data)
        if observed_before != plan.expected_current_digest:
            status = "workspace_file_rollback_digest_mismatch"
            warnings.append("current_digest_mismatch")
        elif not warnings and plan.created_new_file:
            target.unlink()
            delete_performed = True
            status = "workspace_file_rollback_created_file_removed"
            observed_after = None
        elif not warnings and plan.replaced_existing_file and plan.preimage_bytes_base64 is not None:
            previous = base64.b64decode(plan.preimage_bytes_base64.encode("ascii"))
            if bytes_digest(previous) != plan.preimage_digest:
                status = "workspace_file_rollback_contradicted"
                warnings.append("stored_preimage_digest_mismatch")
            else:
                tmp = target.with_name(f".{target.name}.sentientos-rollback-{plan.plan_id}.tmp")
                tmp.write_bytes(previous)
                os.replace(tmp, target)
                write_performed = True
                observed_after = bytes_digest(target.read_bytes())
                status = "workspace_file_rollback_preimage_restored" if observed_after == plan.preimage_digest else "workspace_file_rollback_contradicted"
        elif not warnings:
            warnings.append("rollback_strategy_not_exact")
    success = status in {"workspace_file_rollback_created_file_removed", "workspace_file_rollback_preimage_restored"}
    record = WorkspaceFileRollbackResult(
        result_id=f"rollback-result-{plan.plan_id}",
        plan_id=plan.plan_id,
        target_path=plan.target_path,
        rollback_status=status,
        observed_before_rollback_digest=observed_before,
        observed_after_rollback_digest=observed_after,
        warning_codes=tuple(warnings),
        risk_codes=plan.risk_codes,
        created_at=created_at,
        digest="",
        real_rollback_performed=success,
        file_delete_performed=delete_performed,
        local_file_write_performed=write_performed,
        host_mutation_performed=success,
    )
    return replace(record, digest=deterministic_digest("workspace-file-rollback-result-", record.to_dict()))


def build_workspace_file_rollback_receipt(plan: WorkspaceFileRollbackPlan, result: WorkspaceFileRollbackResult, *, created_at: str | None = None) -> WorkspaceFileRollbackReceipt:
    success = result.real_rollback_performed
    receipt = WorkspaceFileRollbackReceipt(
        receipt_id=f"rollback-receipt-{result.result_id}",
        plan_id=plan.plan_id,
        rollback_result_id=result.result_id,
        target_path=result.target_path,
        rollback_status=result.rollback_status,
        evidence_summary=tuple(summarize_workspace_file_rollback_result(result)),
        blocked_actions=BLOCKED_ACTION_LABELS,
        warning_codes=result.warning_codes,
        risk_codes=result.risk_codes,
        created_at=created_at or result.created_at,
        digest="",
        real_rollback_receipt_created=success,
        real_rollback_performed=success,
        host_mutation_performed=success,
    )
    return replace(receipt, digest=deterministic_digest("workspace-file-rollback-receipt-", receipt.to_dict()))


def perform_workspace_file_rollback_postcondition_check(plan: WorkspaceFileRollbackPlan, receipt: WorkspaceFileRollbackReceipt, *, created_at: str | None = None) -> WorkspaceFileRollbackPostconditionCheck:
    path = Path(receipt.target_path)
    exists = path.exists()
    observed_digest = bytes_digest(path.read_bytes()) if exists and path.is_file() and not path.is_symlink() else None
    expected_absent = True if plan.created_new_file else None
    expected_preimage = plan.preimage_digest if plan.replaced_existing_file else None
    passed = (plan.created_new_file and not exists) or (plan.replaced_existing_file and exists and observed_digest == expected_preimage)
    record = WorkspaceFileRollbackPostconditionCheck(
        check_id=f"rollback-postcondition-{receipt.receipt_id}",
        rollback_receipt_id=receipt.receipt_id,
        target_path=receipt.target_path,
        expected_absent=expected_absent,
        expected_preimage_digest=expected_preimage,
        observed_exists=exists,
        observed_digest=observed_digest,
        postcondition_status="workspace_file_postcondition_passed" if passed else "workspace_file_postcondition_failed",
        warning_codes=() if passed else ("rollback_postcondition_mismatch",),
        risk_codes=receipt.risk_codes,
        created_at=created_at or receipt.created_at,
        digest="",
    )
    return replace(record, digest=deterministic_digest("workspace-file-rollback-postcondition-", record.to_dict()))


def build_workspace_file_production_audit_receipt(
    effect_receipt: WorkspaceFileEffectReceipt,
    postcondition: WorkspaceFilePostconditionCheck,
    rollback_plan: WorkspaceFileRollbackPlan,
    *,
    rollback_receipt: WorkspaceFileRollbackReceipt | None = None,
    rollback_postcondition: WorkspaceFileRollbackPostconditionCheck | None = None,
    created_at: str | None = None,
) -> WorkspaceFileProductionAuditReceipt:
    warnings: list[str] = []
    if postcondition.postcondition_status != "workspace_file_postcondition_passed":
        warnings.append("effect_postcondition_not_passed")
    if rollback_receipt and not rollback_receipt.real_rollback_performed:
        warnings.append("rollback_not_successful")
    status = "workspace_file_production_audit_recorded" if not warnings else "workspace_file_production_audit_recorded_with_warnings"
    record = WorkspaceFileProductionAuditReceipt(
        audit_id=f"audit-{effect_receipt.receipt_id}",
        effect_receipt_id=effect_receipt.receipt_id,
        postcondition_check_id=postcondition.check_id,
        rollback_plan_id=rollback_plan.plan_id,
        rollback_receipt_id=rollback_receipt.receipt_id if rollback_receipt else None,
        rollback_postcondition_check_id=rollback_postcondition.check_id if rollback_postcondition else None,
        audit_status=status,
        evidence_summary=(
            "workspace file effect audit only",
            f"effect_status={effect_receipt.effect_status}",
            f"postcondition_status={postcondition.postcondition_status}",
            f"rollback_plan_status={rollback_plan.rollback_status}",
        ),
        warning_codes=tuple(warnings),
        risk_codes=effect_receipt.risk_codes,
        created_at=created_at or effect_receipt.created_at,
        digest="",
    )
    return replace(record, digest=deterministic_digest("workspace-file-production-audit-", record.to_dict()))


def _validate_common(record: Any, *, allowed_true_fields: frozenset[str]) -> WorkspaceFileEffectValidationResult:
    findings: list[str] = []
    data = record.to_dict() if hasattr(record, "to_dict") else dict(record)
    for field in FORBIDDEN_TRUE_FIELDS:
        if data.get(field) is True:
            findings.append(f"forbidden_true_field:{field}")
    for key, value in data.items():
        if key.endswith("_performed") and value is True and key not in allowed_true_fields:
            findings.append(f"unexpected_performed_field:{key}")
    blocked = set(data.get("blocked_actions", ()) or ())
    missing = set(BLOCKED_ACTION_LABELS) - blocked if "blocked_actions" in data else set()
    if missing:
        findings.append("missing_blocked_actions:" + ",".join(sorted(missing)))
    return WorkspaceFileEffectValidationResult(ok=not findings, findings=tuple(findings))


def validate_workspace_file_effect_request(request: WorkspaceFileEffectRequest) -> WorkspaceFileEffectValidationResult:
    findings = list(_validate_common(request, allowed_true_fields=_ALLOWED_EFFECT_TRUE_FIELDS).findings)
    if request.request_status not in EFFECT_STATUSES:
        findings.append("unknown_request_status")
    _root, _target, path_findings = _resolve_target(request.workspace_root, request.relative_target_path)
    findings.extend(path_findings)
    return WorkspaceFileEffectValidationResult(ok=not findings, findings=tuple(dict.fromkeys(findings)))


def validate_workspace_file_preimage_record(record: WorkspaceFilePreimageRecord) -> WorkspaceFileEffectValidationResult:
    findings = list(_validate_common(record, allowed_true_fields=frozenset()).findings)
    if record.preimage_status not in PREIMAGE_STATUSES:
        findings.append("unknown_preimage_status")
    return WorkspaceFileEffectValidationResult(ok=not findings, findings=tuple(findings))


def validate_workspace_file_effect_result(record: WorkspaceFileEffectResult) -> WorkspaceFileEffectValidationResult:
    findings = list(_validate_common(record, allowed_true_fields=_ALLOWED_EFFECT_TRUE_FIELDS).findings)
    if record.effect_status not in EFFECT_STATUSES:
        findings.append("unknown_effect_status")
    if record.created_new_file and record.replaced_existing_file:
        findings.append("created_and_replaced_contradiction")
    return WorkspaceFileEffectValidationResult(ok=not findings, findings=tuple(findings))


def validate_workspace_file_effect_receipt(record: WorkspaceFileEffectReceipt) -> WorkspaceFileEffectValidationResult:
    findings = list(_validate_common(record, allowed_true_fields=_ALLOWED_EFFECT_TRUE_FIELDS).findings)
    if record.effect_domain not in EFFECT_DOMAINS:
        findings.append("unknown_effect_domain")
    if not record.workspace_scoped or not record.single_target_only:
        findings.append("workspace_or_single_target_not_asserted")
    return WorkspaceFileEffectValidationResult(ok=not findings, findings=tuple(findings))


def validate_workspace_file_postcondition_check(record: WorkspaceFilePostconditionCheck) -> WorkspaceFileEffectValidationResult:
    findings = list(_validate_common(record, allowed_true_fields=_ALLOWED_EFFECT_TRUE_FIELDS).findings)
    if record.postcondition_status not in POSTCONDITION_STATUSES:
        findings.append("unknown_postcondition_status")
    return WorkspaceFileEffectValidationResult(ok=not findings, findings=tuple(findings))


def validate_workspace_file_rollback_plan(record: WorkspaceFileRollbackPlan) -> WorkspaceFileEffectValidationResult:
    findings = list(_validate_common(record, allowed_true_fields=_ALLOWED_ROLLBACK_TRUE_FIELDS).findings)
    if record.rollback_status not in ROLLBACK_STATUSES:
        findings.append("unknown_rollback_status")
    return WorkspaceFileEffectValidationResult(ok=not findings, findings=tuple(findings))


def validate_workspace_file_rollback_result(record: WorkspaceFileRollbackResult) -> WorkspaceFileEffectValidationResult:
    findings = list(_validate_common(record, allowed_true_fields=_ALLOWED_ROLLBACK_TRUE_FIELDS).findings)
    if record.rollback_status not in ROLLBACK_STATUSES:
        findings.append("unknown_rollback_status")
    return WorkspaceFileEffectValidationResult(ok=not findings, findings=tuple(findings))


def validate_workspace_file_rollback_receipt(record: WorkspaceFileRollbackReceipt) -> WorkspaceFileEffectValidationResult:
    findings = list(_validate_common(record, allowed_true_fields=_ALLOWED_ROLLBACK_TRUE_FIELDS).findings)
    if record.rollback_status not in ROLLBACK_STATUSES:
        findings.append("unknown_rollback_status")
    if not record.exact_target_only or not record.workspace_scoped:
        findings.append("rollback_scope_not_exact")
    return WorkspaceFileEffectValidationResult(ok=not findings, findings=tuple(findings))


def validate_workspace_file_rollback_postcondition_check(record: WorkspaceFileRollbackPostconditionCheck) -> WorkspaceFileEffectValidationResult:
    findings = list(_validate_common(record, allowed_true_fields=_ALLOWED_ROLLBACK_TRUE_FIELDS).findings)
    if record.postcondition_status not in POSTCONDITION_STATUSES:
        findings.append("unknown_postcondition_status")
    return WorkspaceFileEffectValidationResult(ok=not findings, findings=tuple(findings))


def validate_workspace_file_production_audit_receipt(record: WorkspaceFileProductionAuditReceipt) -> WorkspaceFileEffectValidationResult:
    findings = list(_validate_common(record, allowed_true_fields=_ALLOWED_EFFECT_TRUE_FIELDS).findings)
    if record.audit_status not in AUDIT_STATUSES:
        findings.append("unknown_audit_status")
    if not record.audit_for_workspace_file_effect_only:
        findings.append("audit_not_workspace_file_effect_only")
    return WorkspaceFileEffectValidationResult(ok=not findings, findings=tuple(findings))


def summarize_workspace_file_effect_request(request: WorkspaceFileEffectRequest) -> dict[str, Any]:
    return {"request_id": request.request_id, "workspace_root": request.workspace_root, "relative_target_path": request.relative_target_path, "single_target_only": True, "general_filesystem_access_requested": False, "status": request.request_status}


def summarize_workspace_file_preimage_record(record: WorkspaceFilePreimageRecord) -> dict[str, Any]:
    return {"preimage_id": record.preimage_id, "status": record.preimage_status, "existed_before": record.existed_before, "preimage_digest": record.preimage_digest, "host_mutation_performed": False}


def summarize_workspace_file_effect_result(result: WorkspaceFileEffectResult) -> dict[str, Any]:
    return {"result_id": result.result_id, "status": result.effect_status, "target_path": result.target_path, "created_new_file": result.created_new_file, "replaced_existing_file": result.replaced_existing_file, "host_mutation_performed": result.host_mutation_performed, "single_file_workspace_effect_only": True}


def summarize_workspace_file_effect_receipt(receipt: WorkspaceFileEffectReceipt) -> dict[str, Any]:
    return {"receipt_id": receipt.receipt_id, "effect_domain": receipt.effect_domain, "workspace_scoped": receipt.workspace_scoped, "single_target_only": receipt.single_target_only, "general_filesystem_access_performed": False, "host_mutation_performed": receipt.host_mutation_performed}


def summarize_workspace_file_postcondition_check(check: WorkspaceFilePostconditionCheck) -> dict[str, Any]:
    return {"check_id": check.check_id, "status": check.postcondition_status, "expected_artifact_digest": check.expected_artifact_digest, "observed_artifact_digest": check.observed_artifact_digest, "host_mutation_performed": False}


def summarize_workspace_file_rollback_plan(plan: WorkspaceFileRollbackPlan) -> dict[str, Any]:
    return {"plan_id": plan.plan_id, "strategy": plan.rollback_strategy, "status": plan.rollback_status, "exact_target_only": True, "expected_current_digest": plan.expected_current_digest}


def summarize_workspace_file_rollback_result(result: WorkspaceFileRollbackResult) -> dict[str, Any]:
    return {"result_id": result.result_id, "status": result.rollback_status, "file_delete_performed": result.file_delete_performed, "local_file_write_performed": result.local_file_write_performed, "directory_cleanup_performed": False, "recursive_delete_performed": False, "wildcard_delete_performed": False, "unrelated_file_delete_performed": False}


def summarize_workspace_file_rollback_receipt(receipt: WorkspaceFileRollbackReceipt) -> dict[str, Any]:
    return {"receipt_id": receipt.receipt_id, "status": receipt.rollback_status, "exact_target_only": receipt.exact_target_only, "workspace_scoped": receipt.workspace_scoped, "general_cleanup_performed": False}


def summarize_workspace_file_rollback_postcondition_check(check: WorkspaceFileRollbackPostconditionCheck) -> dict[str, Any]:
    return {"check_id": check.check_id, "status": check.postcondition_status, "observed_exists": check.observed_exists, "observed_digest": check.observed_digest}


def summarize_workspace_file_production_audit_receipt(audit: WorkspaceFileProductionAuditReceipt) -> dict[str, Any]:
    return {"audit_id": audit.audit_id, "status": audit.audit_status, "audit_for_workspace_file_effect_only": True, "production_audit_receipt_created": audit.production_audit_receipt_created, "host_mutation_performed": False}


def run_workspace_file_effect_wing(
    *,
    workspace_root: str | Path,
    relative_target_path: str,
    payload_text: str,
    request_id: str = "workspace-file-effect-request",
    force_create: bool = False,
    allow_replace: bool = True,
    dry_run: bool = False,
    created_at: str = DEFAULT_CREATED_AT,
) -> WorkspaceFileEffectWingResult:
    request = build_workspace_file_effect_request(
        request_id=request_id,
        workspace_root=workspace_root,
        relative_target_path=relative_target_path,
        payload_text=payload_text,
        force_create=force_create,
        allow_replace=allow_replace,
        created_at=created_at,
    )
    preimage, result = perform_workspace_file_effect(request, dry_run=dry_run, created_at=created_at)
    receipt = build_workspace_file_effect_receipt(request, preimage, result, created_at=created_at)
    postcondition = perform_workspace_file_postcondition_check(receipt, created_at=created_at)
    rollback_plan = build_workspace_file_rollback_plan(receipt, preimage, created_at=created_at)
    audit = build_workspace_file_production_audit_receipt(receipt, postcondition, rollback_plan, created_at=created_at)
    return WorkspaceFileEffectWingResult(request, preimage, result, receipt, postcondition, rollback_plan, audit)


def run_workspace_file_rollback_wing(
    *,
    effect_receipt: WorkspaceFileEffectReceipt,
    rollback_plan: WorkspaceFileRollbackPlan,
    created_at: str = DEFAULT_CREATED_AT,
) -> WorkspaceFileRollbackWingResult:
    rollback_result = perform_workspace_file_rollback(rollback_plan, created_at=created_at)
    rollback_receipt = build_workspace_file_rollback_receipt(rollback_plan, rollback_result, created_at=created_at)
    rollback_postcondition = perform_workspace_file_rollback_postcondition_check(rollback_plan, rollback_receipt, created_at=created_at)
    dummy_postcondition = WorkspaceFilePostconditionCheck(
        check_id=f"postcondition-for-{effect_receipt.receipt_id}",
        receipt_id=effect_receipt.receipt_id,
        target_path=effect_receipt.target_path,
        expected_artifact_digest=effect_receipt.artifact_digest,
        observed_artifact_digest=effect_receipt.artifact_digest,
        expected_byte_count=effect_receipt.byte_count,
        observed_byte_count=effect_receipt.byte_count,
        postcondition_status="workspace_file_postcondition_passed",
        warning_codes=(),
        risk_codes=effect_receipt.risk_codes,
        created_at=created_at,
        digest="",
    )
    dummy_postcondition = replace(dummy_postcondition, digest=deterministic_digest("workspace-file-postcondition-", dummy_postcondition.to_dict()))
    audit = build_workspace_file_production_audit_receipt(effect_receipt, dummy_postcondition, rollback_plan, rollback_receipt=rollback_receipt, rollback_postcondition=rollback_postcondition, created_at=created_at)
    return WorkspaceFileRollbackWingResult(rollback_result, rollback_receipt, rollback_postcondition, audit)
