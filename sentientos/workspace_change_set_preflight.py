"""Read-only workspace change-set preflight and planning records.

This wing validates bounded manifests of explicit workspace targets and prepares
metadata-only rollback/transaction plans for a future executor. It never writes
workspace targets, never rolls back, never invokes runners/orchestrators, and
never performs provider, network, shell, subprocess, service, power, hardware,
fan/PWM, thermal, cleanup, deletion, OS-backend, or control-plane execution.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

MANIFEST_STATUSES = frozenset({
    "workspace_change_set_manifest_recorded",
    "workspace_change_set_manifest_recorded_with_warnings",
    "workspace_change_set_manifest_blocked",
    "workspace_change_set_manifest_incomplete",
    "workspace_change_set_manifest_contradicted",
})
TARGET_STATUSES = frozenset({
    "workspace_change_target_declared",
    "workspace_change_target_declared_with_warnings",
    "workspace_change_target_blocked",
    "workspace_change_target_incomplete",
    "workspace_change_target_contradicted",
})
PREFLIGHT_STATUSES = frozenset({
    "workspace_change_target_preflight_passed",
    "workspace_change_target_preflight_passed_with_warnings",
    "workspace_change_target_preflight_blocked",
    "workspace_change_target_preflight_missing_parent",
    "workspace_change_target_preflight_missing_target",
    "workspace_change_target_preflight_symlink",
    "workspace_change_target_preflight_directory",
    "workspace_change_target_preflight_outside_workspace",
    "workspace_change_target_preflight_contradicted",
})
REPORT_STATUSES = frozenset({
    "workspace_change_set_preflight_passed",
    "workspace_change_set_preflight_passed_with_warnings",
    "workspace_change_set_preflight_blocked",
    "workspace_change_set_preflight_incomplete",
    "workspace_change_set_preflight_contradicted",
})
ROLLBACK_PLAN_STATUSES = frozenset({
    "workspace_change_set_rollback_plan_ready",
    "workspace_change_set_rollback_plan_ready_with_warnings",
    "workspace_change_set_rollback_plan_blocked",
    "workspace_change_set_rollback_plan_incomplete",
    "workspace_change_set_rollback_plan_contradicted",
})
TRANSACTION_PLAN_STATUSES = frozenset({
    "workspace_change_set_transaction_plan_ready",
    "workspace_change_set_transaction_plan_ready_with_warnings",
    "workspace_change_set_transaction_plan_blocked",
    "workspace_change_set_transaction_plan_incomplete",
    "workspace_change_set_transaction_plan_contradicted",
})
BLOCK_RECEIPT_STATUSES = frozenset({
    "workspace_change_set_block_receipt_recorded",
    "workspace_change_set_block_receipt_incomplete",
    "workspace_change_set_block_receipt_contradicted",
})
CHANGE_OPERATIONS = frozenset({"create_file", "update_file", "replace_file"})
WILDCARD_CHARS = frozenset("*?[]{}")
DEFAULT_CREATED_AT = "1970-01-01T00:00:00+00:00"
BLOCKED_ACTION_LABELS = (
    "multi_file_execution",
    "target_write",
    "target_rollback",
    "general_filesystem_access",
    "directory_cleanup",
    "recursive_delete",
    "wildcard_delete",
    "unrelated_file_delete",
    "path_traversal",
    "absolute_target_path",
    "target_outside_workspace",
    "symlink_target_write",
    "directory_target_write",
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
FORBIDDEN_FLAG_NAMES = (
    "target_write_performed",
    "target_rollback_performed",
    "host_mutation_performed",
    "subprocess_used",
    "shell_used",
    "network_used",
    "provider_invocation_performed",
    "prompt_assembly_performed",
    "hardware_control_performed",
    "service_control_performed",
    "power_control_performed",
    "fan_pwm_write_performed",
    "thermal_actuation_performed",
    "cleanup_performed",
    "recursive_delete_performed",
    "wildcard_delete_performed",
    "unrelated_file_delete_performed",
    "os_backend_invocation_performed",
    "control_plane_admission_execution_performed",
)


@dataclass(frozen=True)
class WorkspaceChangeSetValidationResult:
    ok: bool
    status: str
    findings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceChangeSetPolicy:
    max_targets: int = 8
    max_payload_bytes_per_target: int = 65536
    max_total_payload_bytes: int = 262144
    require_parent_exists: bool = True
    allow_replace: bool = True
    allow_create: bool = True
    reject_symlink_targets: bool = True
    reject_directory_targets: bool = True
    reject_wildcard_targets: bool = True
    read_existing_target_digest: bool = True
    mutation_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceChangeTargetDeclaration:
    target_id: str
    relative_target_path: str
    operation: str
    payload_text: str
    payload_media_type: str
    allow_replace: bool
    allow_create: bool
    required_scope_labels: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    target_declaration_only: bool = True
    target_write_performed: bool = False
    target_rollback_performed: bool = False
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceChangeSetManifest:
    manifest_id: str
    workspace_root: str
    targets: tuple[WorkspaceChangeTargetDeclaration, ...]
    target_count: int
    total_payload_bytes: int
    manifest_status: str
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    manifest_only: bool = True
    mutation_allowed: bool = False
    target_write_performed: bool = False
    host_mutation_performed: bool = False
    subprocess_used: bool = False
    shell_used: bool = False
    network_used: bool = False
    provider_invocation_performed: bool = False
    prompt_assembly_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceChangeTargetPreflight:
    preflight_id: str
    target_id: str
    workspace_root: str
    relative_target_path: str
    resolved_target_path: str
    operation: str
    preflight_status: str
    parent_exists: bool
    target_exists: bool
    target_is_symlink: bool
    target_is_directory: bool
    target_inside_workspace: bool
    existing_digest: str | None
    existing_byte_count: int | None
    payload_digest: str
    payload_byte_count: int
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    preflight_only: bool = True
    read_only: bool = True
    target_write_performed: bool = False
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceChangeSetPreflightReport:
    report_id: str
    manifest_id: str
    target_preflight_ids: tuple[str, ...]
    report_status: str
    passed_target_ids: tuple[str, ...]
    blocked_target_ids: tuple[str, ...]
    missing_parent_target_ids: tuple[str, ...]
    missing_existing_target_ids: tuple[str, ...]
    duplicate_target_ids: tuple[str, ...]
    contradiction_codes: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    preflight_report_only: bool = True
    read_only: bool = True
    mutation_allowed: bool = False
    target_write_performed: bool = False
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceChangeSetRollbackPlan:
    plan_id: str
    manifest_id: str
    preflight_report_id: str
    target_rollback_entries: tuple[dict[str, Any], ...]
    rollback_strategy: str
    rollback_plan_status: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    rollback_plan_only: bool = True
    rollback_not_performed: bool = True
    target_rollback_performed: bool = False
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceChangeSetTransactionPlan:
    plan_id: str
    manifest_id: str
    preflight_report_id: str
    rollback_plan_id: str
    planned_target_order: tuple[str, ...]
    transaction_plan_status: str
    execution_strategy: str
    rollback_strategy: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    transaction_plan_only: bool = True
    execution_not_started: bool = True
    mutation_allowed: bool = False
    target_write_performed: bool = False
    target_rollback_performed: bool = False
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceChangeSetBlockReceipt:
    receipt_id: str
    manifest_id: str | None
    block_status: str
    block_reason_codes: tuple[str, ...]
    blocked_target_ids: tuple[str, ...]
    missing_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    block_receipt_only: bool = True
    execution_not_started: bool = True
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def _digest(prefix: str, payload: Mapping[str, Any]) -> str:
    data = dict(payload)
    data["digest"] = ""
    return prefix + hashlib.sha256(_canonical_json(data).encode("utf-8")).hexdigest()[:24]


def payload_digest(payload_text: str) -> str:
    return "sha256:" + hashlib.sha256(payload_text.encode("utf-8")).hexdigest()


def file_digest(path: Path) -> tuple[str, int]:
    data = path.read_bytes()
    return "sha256:" + hashlib.sha256(data).hexdigest(), len(data)


def build_default_workspace_change_set_policy() -> WorkspaceChangeSetPolicy:
    return WorkspaceChangeSetPolicy()


def _normalized_relative_path(path_text: str) -> str:
    path_text = path_text.replace("\\", "/")
    pure = PurePosixPath(path_text)
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


def _target_path_findings(relative_target_path: str, policy: WorkspaceChangeSetPolicy) -> tuple[str, ...]:
    findings: list[str] = []
    if not relative_target_path or relative_target_path.strip() == "":
        findings.append("empty_target_path")
    if Path(relative_target_path).is_absolute() or PurePosixPath(relative_target_path).is_absolute():
        findings.append("absolute_target_path")
    normalized = _normalized_relative_path(relative_target_path)
    parts = PurePosixPath(relative_target_path.replace("\\", "/")).parts
    if ".." in parts or normalized == ".." or normalized.startswith("../"):
        findings.append("path_traversal")
    if policy.reject_wildcard_targets and any(ch in relative_target_path for ch in WILDCARD_CHARS):
        findings.append("wildcard_target_path")
    return tuple(findings)


def _inside_workspace(workspace_root: Path, target_path: Path) -> bool:
    try:
        target_path.resolve(strict=False).relative_to(workspace_root.resolve(strict=False))
        return True
    except ValueError:
        return False


def _workspace_findings(workspace_root: str | Path) -> tuple[str, ...]:
    text = str(workspace_root)
    findings: list[str] = []
    if not text or text.strip() == "":
        findings.append("empty_workspace_root")
    else:
        root = Path(text).expanduser()
        if root.resolve(strict=False) == Path(root.anchor or "/").resolve(strict=False):
            findings.append("root_workspace_refused")
    return tuple(findings)


def _payload_byte_count(text: str) -> int:
    return len(text.encode("utf-8"))


def build_workspace_change_target_declaration(
    *,
    target_id: str | None = None,
    relative_target_path: str,
    operation: str = "create_file",
    payload_text: str,
    payload_media_type: str = "text/plain; charset=utf-8",
    allow_replace: bool = True,
    allow_create: bool = True,
    required_scope_labels: Sequence[str] = ("workspace_change_set_preflight",),
    warning_codes: Sequence[str] = (),
    risk_codes: Sequence[str] = (),
    created_at: str = DEFAULT_CREATED_AT,
) -> WorkspaceChangeTargetDeclaration:
    target_id = target_id or "workspace-change-target-" + hashlib.sha256(f"{relative_target_path}\0{operation}\0{payload_text}\0{created_at}".encode("utf-8")).hexdigest()[:16]
    record = WorkspaceChangeTargetDeclaration(
        target_id=target_id,
        relative_target_path=relative_target_path,
        operation=operation,
        payload_text=payload_text,
        payload_media_type=payload_media_type,
        allow_replace=allow_replace,
        allow_create=allow_create,
        required_scope_labels=tuple(required_scope_labels),
        warning_codes=tuple(warning_codes),
        risk_codes=tuple(risk_codes),
        created_at=created_at,
        digest="",
    )
    return replace(record, digest=_digest("workspace-change-target-", record.to_dict()))


def validate_workspace_change_target_declaration(target: WorkspaceChangeTargetDeclaration, policy: WorkspaceChangeSetPolicy | None = None) -> WorkspaceChangeSetValidationResult:
    policy = policy or build_default_workspace_change_set_policy()
    findings: list[str] = []
    if target.operation not in CHANGE_OPERATIONS:
        findings.append("unsupported_operation")
    findings.extend(_target_path_findings(target.relative_target_path, policy))
    if _payload_byte_count(target.payload_text) > policy.max_payload_bytes_per_target:
        findings.append("payload_bytes_over_per_target_limit")
    findings.extend(_contradiction_findings(target))
    status = "workspace_change_target_declared" if not findings else "workspace_change_target_blocked"
    if any(f.startswith("contradiction:") for f in findings):
        status = "workspace_change_target_contradicted"
    return WorkspaceChangeSetValidationResult(not findings, status, tuple(findings))


def _contradiction_findings(record: Any) -> tuple[str, ...]:
    findings: list[str] = []
    for flag in FORBIDDEN_FLAG_NAMES:
        if bool(getattr(record, flag, False)):
            findings.append(f"contradiction:{flag}")
    if getattr(record, "mutation_allowed", False):
        findings.append("contradiction:mutation_allowed")
    if getattr(record, "metadata_only", True) is False:
        findings.append("contradiction:metadata_only_false")
    if getattr(record, "read_only", True) is False:
        findings.append("contradiction:read_only_false")
    if getattr(record, "rollback_not_performed", True) is False:
        findings.append("contradiction:rollback_performed")
    if getattr(record, "execution_not_started", True) is False:
        findings.append("contradiction:execution_started")
    return tuple(findings)


def build_workspace_change_set_manifest(
    *,
    workspace_root: str | Path,
    targets: Sequence[WorkspaceChangeTargetDeclaration],
    policy: WorkspaceChangeSetPolicy | None = None,
    manifest_id: str | None = None,
    created_at: str = DEFAULT_CREATED_AT,
) -> WorkspaceChangeSetManifest:
    policy = policy or build_default_workspace_change_set_policy()
    total_payload_bytes = sum(_payload_byte_count(target.payload_text) for target in targets)
    findings: list[str] = []
    findings.extend(_workspace_findings(workspace_root))
    if not targets:
        findings.append("empty_target_manifest")
    if len(targets) > policy.max_targets:
        findings.append("target_count_over_limit")
    if total_payload_bytes > policy.max_total_payload_bytes:
        findings.append("total_payload_bytes_over_limit")
    normalized_seen: dict[str, str] = {}
    duplicate_ids: list[str] = []
    for target in targets:
        validation = validate_workspace_change_target_declaration(target, policy)
        findings.extend(validation.findings)
        normalized = _normalized_relative_path(target.relative_target_path)
        if normalized in normalized_seen:
            duplicate_ids.extend([normalized_seen[normalized], target.target_id])
            findings.append("duplicate_target_path")
        else:
            normalized_seen[normalized] = target.target_id
    status = "workspace_change_set_manifest_recorded"
    if findings:
        status = "workspace_change_set_manifest_blocked"
    if any(f.startswith("contradiction:") for f in findings):
        status = "workspace_change_set_manifest_contradicted"
    blocked = tuple(sorted(set(BLOCKED_ACTION_LABELS + tuple(f for f in findings if f in BLOCKED_ACTION_LABELS))))
    risk_codes = tuple(sorted(set(findings + duplicate_ids)))
    manifest_id = manifest_id or "workspace-change-set-manifest-" + hashlib.sha256(f"{workspace_root}\0{created_at}\0{len(targets)}".encode("utf-8")).hexdigest()[:16]
    record = WorkspaceChangeSetManifest(
        manifest_id=manifest_id,
        workspace_root=str(workspace_root),
        targets=tuple(targets),
        target_count=len(targets),
        total_payload_bytes=total_payload_bytes,
        manifest_status=status,
        blocked_actions=blocked,
        warning_codes=(),
        risk_codes=risk_codes,
        created_at=created_at,
        digest="",
    )
    return replace(record, digest=_digest("workspace-change-set-manifest-", record.to_dict()))


def validate_workspace_change_set_manifest(manifest: WorkspaceChangeSetManifest, policy: WorkspaceChangeSetPolicy | None = None) -> WorkspaceChangeSetValidationResult:
    findings = list(_contradiction_findings(manifest))
    policy = policy or build_default_workspace_change_set_policy()
    rebuilt = build_workspace_change_set_manifest(workspace_root=manifest.workspace_root, targets=manifest.targets, policy=policy, manifest_id=manifest.manifest_id, created_at=manifest.created_at)
    findings.extend(rebuilt.risk_codes)
    if manifest.manifest_status not in MANIFEST_STATUSES:
        findings.append("unknown_manifest_status")
    status = manifest.manifest_status if not findings else "workspace_change_set_manifest_blocked"
    if any(f.startswith("contradiction:") for f in findings):
        status = "workspace_change_set_manifest_contradicted"
    return WorkspaceChangeSetValidationResult(not findings, status, tuple(sorted(set(findings))))


def preflight_workspace_change_target(
    *,
    workspace_root: str | Path,
    target: WorkspaceChangeTargetDeclaration,
    policy: WorkspaceChangeSetPolicy | None = None,
    created_at: str = DEFAULT_CREATED_AT,
) -> WorkspaceChangeTargetPreflight:
    policy = policy or build_default_workspace_change_set_policy()
    root = Path(workspace_root).expanduser()
    normalized = _normalized_relative_path(target.relative_target_path)
    target_path = root / normalized
    parent_exists = target_path.parent.exists()
    target_exists = target_path.exists()
    target_is_symlink = target_path.is_symlink()
    target_is_directory = target_path.is_dir()
    target_inside = _inside_workspace(root, target_path)
    findings: list[str] = []
    findings.extend(_workspace_findings(workspace_root))
    findings.extend(validate_workspace_change_target_declaration(target, policy).findings)
    if not target_inside:
        findings.append("target_outside_workspace")
    if policy.require_parent_exists and not parent_exists:
        findings.append("missing_parent_directory")
    if policy.reject_symlink_targets and target_is_symlink:
        findings.append("symlink_target")
    if policy.reject_directory_targets and target_is_directory:
        findings.append("directory_target")
    if target.operation in {"update_file", "replace_file"} and not target_exists:
        findings.append("missing_existing_target")
    if target.operation == "create_file" and target_exists and not target.allow_replace:
        findings.append("create_target_exists_replace_disallowed")
    existing_digest: str | None = None
    existing_byte_count: int | None = None
    if policy.read_existing_target_digest and target_exists and target_inside and not target_is_symlink and not target_is_directory:
        existing_digest, existing_byte_count = file_digest(target_path)
    status = "workspace_change_target_preflight_passed"
    if "symlink_target" in findings:
        status = "workspace_change_target_preflight_symlink"
    elif "directory_target" in findings:
        status = "workspace_change_target_preflight_directory"
    elif "missing_parent_directory" in findings:
        status = "workspace_change_target_preflight_missing_parent"
    elif "missing_existing_target" in findings:
        status = "workspace_change_target_preflight_missing_target"
    elif "target_outside_workspace" in findings:
        status = "workspace_change_target_preflight_outside_workspace"
    elif findings:
        status = "workspace_change_target_preflight_blocked"
    if any(f.startswith("contradiction:") for f in findings):
        status = "workspace_change_target_preflight_contradicted"
    record = WorkspaceChangeTargetPreflight(
        preflight_id="workspace-change-target-preflight-" + hashlib.sha256(f"{target.target_id}\0{workspace_root}\0{created_at}".encode("utf-8")).hexdigest()[:16],
        target_id=target.target_id,
        workspace_root=str(workspace_root),
        relative_target_path=target.relative_target_path,
        resolved_target_path=str(target_path.resolve(strict=False)),
        operation=target.operation,
        preflight_status=status,
        parent_exists=parent_exists,
        target_exists=target_exists,
        target_is_symlink=target_is_symlink,
        target_is_directory=target_is_directory,
        target_inside_workspace=target_inside,
        existing_digest=existing_digest,
        existing_byte_count=existing_byte_count,
        payload_digest=payload_digest(target.payload_text),
        payload_byte_count=_payload_byte_count(target.payload_text),
        warning_codes=(),
        risk_codes=tuple(sorted(set(findings))),
        created_at=created_at,
        digest="",
    )
    return replace(record, digest=_digest("workspace-change-target-preflight-", record.to_dict()))


def validate_workspace_change_target_preflight(preflight: WorkspaceChangeTargetPreflight) -> WorkspaceChangeSetValidationResult:
    findings = list(_contradiction_findings(preflight))
    if preflight.preflight_status not in PREFLIGHT_STATUSES:
        findings.append("unknown_preflight_status")
    if not preflight.read_only:
        findings.append("contradiction:preflight_not_read_only")
    status = preflight.preflight_status if not findings else "workspace_change_target_preflight_contradicted"
    return WorkspaceChangeSetValidationResult(not findings, status, tuple(findings))


def _duplicate_target_ids(targets: Sequence[WorkspaceChangeTargetDeclaration]) -> tuple[str, ...]:
    seen: dict[str, str] = {}
    duplicates: list[str] = []
    for target in targets:
        normalized = _normalized_relative_path(target.relative_target_path)
        if normalized in seen:
            duplicates.extend([seen[normalized], target.target_id])
        else:
            seen[normalized] = target.target_id
    return tuple(sorted(set(duplicates)))


def build_workspace_change_set_preflight_report(
    *,
    manifest: WorkspaceChangeSetManifest,
    target_preflights: Sequence[WorkspaceChangeTargetPreflight],
    created_at: str = DEFAULT_CREATED_AT,
) -> WorkspaceChangeSetPreflightReport:
    passed_statuses = {"workspace_change_target_preflight_passed", "workspace_change_target_preflight_passed_with_warnings"}
    passed = tuple(p.target_id for p in target_preflights if p.preflight_status in passed_statuses)
    blocked = tuple(p.target_id for p in target_preflights if p.preflight_status not in passed_statuses)
    missing_parent = tuple(p.target_id for p in target_preflights if p.preflight_status == "workspace_change_target_preflight_missing_parent")
    missing_existing = tuple(p.target_id for p in target_preflights if p.preflight_status == "workspace_change_target_preflight_missing_target")
    duplicate_ids = _duplicate_target_ids(manifest.targets)
    contradiction_codes = tuple(sorted(set(code for p in target_preflights for code in p.risk_codes if code.startswith("contradiction:"))))
    risks = tuple(sorted(set(manifest.risk_codes + tuple(code for p in target_preflights for code in p.risk_codes))))
    status = "workspace_change_set_preflight_passed"
    if blocked or duplicate_ids or manifest.manifest_status.endswith("blocked"):
        status = "workspace_change_set_preflight_blocked"
    if manifest.manifest_status.endswith("contradicted") or contradiction_codes:
        status = "workspace_change_set_preflight_contradicted"
    record = WorkspaceChangeSetPreflightReport(
        report_id="workspace-change-set-preflight-report-" + hashlib.sha256(f"{manifest.manifest_id}\0{created_at}".encode("utf-8")).hexdigest()[:16],
        manifest_id=manifest.manifest_id,
        target_preflight_ids=tuple(p.preflight_id for p in target_preflights),
        report_status=status,
        passed_target_ids=passed,
        blocked_target_ids=blocked,
        missing_parent_target_ids=missing_parent,
        missing_existing_target_ids=missing_existing,
        duplicate_target_ids=duplicate_ids,
        contradiction_codes=contradiction_codes,
        blocked_actions=tuple(sorted(set(BLOCKED_ACTION_LABELS))),
        warning_codes=(),
        risk_codes=risks,
        created_at=created_at,
        digest="",
    )
    return replace(record, digest=_digest("workspace-change-set-preflight-report-", record.to_dict()))


def validate_workspace_change_set_preflight_report(report: WorkspaceChangeSetPreflightReport) -> WorkspaceChangeSetValidationResult:
    findings = list(_contradiction_findings(report))
    if report.report_status not in REPORT_STATUSES:
        findings.append("unknown_report_status")
    if report.report_status == "workspace_change_set_preflight_contradicted":
        findings.extend(report.contradiction_codes)
    status = report.report_status if not findings else "workspace_change_set_preflight_contradicted"
    return WorkspaceChangeSetValidationResult(not findings, status, tuple(sorted(set(findings))))


def build_workspace_change_set_rollback_plan(
    *,
    manifest: WorkspaceChangeSetManifest,
    preflight_report: WorkspaceChangeSetPreflightReport,
    target_preflights: Sequence[WorkspaceChangeTargetPreflight],
    created_at: str = DEFAULT_CREATED_AT,
) -> WorkspaceChangeSetRollbackPlan:
    target_by_id = {target.target_id: target for target in manifest.targets}
    entries: list[dict[str, Any]] = []
    for preflight in target_preflights:
        target = target_by_id[preflight.target_id]
        existed_before = preflight.target_exists
        strategy = "restore_preimage_digest" if existed_before else "remove_created_file"
        entries.append({
            "target_id": target.target_id,
            "relative_target_path": target.relative_target_path,
            "operation": target.operation,
            "expected_post_write_digest": preflight.payload_digest,
            "existing_digest": preflight.existing_digest,
            "existed_before": existed_before,
            "rollback_strategy": strategy,
            "preimage_available": bool(preflight.existing_digest) if existed_before else True,
            "notes": ("metadata-only rollback plan; rollback not performed",),
            "warnings": (),
        })
    status = "workspace_change_set_rollback_plan_ready" if preflight_report.report_status in {"workspace_change_set_preflight_passed", "workspace_change_set_preflight_passed_with_warnings"} else "workspace_change_set_rollback_plan_blocked"
    if preflight_report.report_status == "workspace_change_set_preflight_contradicted":
        status = "workspace_change_set_rollback_plan_contradicted"
    record = WorkspaceChangeSetRollbackPlan(
        plan_id="workspace-change-set-rollback-plan-" + hashlib.sha256(f"{manifest.manifest_id}\0{preflight_report.report_id}\0{created_at}".encode("utf-8")).hexdigest()[:16],
        manifest_id=manifest.manifest_id,
        preflight_report_id=preflight_report.report_id,
        target_rollback_entries=tuple(entries),
        rollback_strategy="metadata_preimage_digest_plan_only",
        rollback_plan_status=status,
        warning_codes=(),
        risk_codes=preflight_report.risk_codes,
        created_at=created_at,
        digest="",
    )
    return replace(record, digest=_digest("workspace-change-set-rollback-plan-", record.to_dict()))


def validate_workspace_change_set_rollback_plan(plan: WorkspaceChangeSetRollbackPlan) -> WorkspaceChangeSetValidationResult:
    findings = list(_contradiction_findings(plan))
    if plan.rollback_plan_status not in ROLLBACK_PLAN_STATUSES:
        findings.append("unknown_rollback_plan_status")
    if not plan.rollback_not_performed:
        findings.append("contradiction:rollback_not_performed_false")
    status = plan.rollback_plan_status if not findings else "workspace_change_set_rollback_plan_contradicted"
    return WorkspaceChangeSetValidationResult(not findings, status, tuple(sorted(set(findings))))


def build_workspace_change_set_transaction_plan(
    *,
    manifest: WorkspaceChangeSetManifest,
    preflight_report: WorkspaceChangeSetPreflightReport,
    rollback_plan: WorkspaceChangeSetRollbackPlan,
    created_at: str = DEFAULT_CREATED_AT,
) -> WorkspaceChangeSetTransactionPlan:
    status = "workspace_change_set_transaction_plan_ready" if rollback_plan.rollback_plan_status in {"workspace_change_set_rollback_plan_ready", "workspace_change_set_rollback_plan_ready_with_warnings"} else "workspace_change_set_transaction_plan_blocked"
    if rollback_plan.rollback_plan_status == "workspace_change_set_rollback_plan_contradicted" or preflight_report.report_status == "workspace_change_set_preflight_contradicted":
        status = "workspace_change_set_transaction_plan_contradicted"
    record = WorkspaceChangeSetTransactionPlan(
        plan_id="workspace-change-set-transaction-plan-" + hashlib.sha256(f"{manifest.manifest_id}\0{rollback_plan.plan_id}\0{created_at}".encode("utf-8")).hexdigest()[:16],
        manifest_id=manifest.manifest_id,
        preflight_report_id=preflight_report.report_id,
        rollback_plan_id=rollback_plan.plan_id,
        planned_target_order=tuple(target.target_id for target in manifest.targets),
        transaction_plan_status=status,
        execution_strategy="future_executor_metadata_plan_only_no_execution",
        rollback_strategy=rollback_plan.rollback_strategy,
        warning_codes=(),
        risk_codes=rollback_plan.risk_codes,
        created_at=created_at,
        digest="",
    )
    return replace(record, digest=_digest("workspace-change-set-transaction-plan-", record.to_dict()))


def validate_workspace_change_set_transaction_plan(plan: WorkspaceChangeSetTransactionPlan) -> WorkspaceChangeSetValidationResult:
    findings = list(_contradiction_findings(plan))
    if plan.transaction_plan_status not in TRANSACTION_PLAN_STATUSES:
        findings.append("unknown_transaction_plan_status")
    status = plan.transaction_plan_status if not findings else "workspace_change_set_transaction_plan_contradicted"
    return WorkspaceChangeSetValidationResult(not findings, status, tuple(sorted(set(findings))))


def build_workspace_change_set_block_receipt(
    *,
    manifest_id: str | None = None,
    block_reason_codes: Sequence[str] = (),
    blocked_target_ids: Sequence[str] = (),
    missing_labels: Sequence[str] = (),
    warning_codes: Sequence[str] = (),
    risk_codes: Sequence[str] = (),
    created_at: str = DEFAULT_CREATED_AT,
) -> WorkspaceChangeSetBlockReceipt:
    status = "workspace_change_set_block_receipt_recorded" if block_reason_codes or blocked_target_ids else "workspace_change_set_block_receipt_incomplete"
    record = WorkspaceChangeSetBlockReceipt(
        receipt_id="workspace-change-set-block-receipt-" + hashlib.sha256(f"{manifest_id}\0{created_at}\0{','.join(block_reason_codes)}".encode("utf-8")).hexdigest()[:16],
        manifest_id=manifest_id,
        block_status=status,
        block_reason_codes=tuple(block_reason_codes),
        blocked_target_ids=tuple(blocked_target_ids),
        missing_labels=tuple(missing_labels),
        blocked_actions=tuple(sorted(set(BLOCKED_ACTION_LABELS))),
        warning_codes=tuple(warning_codes),
        risk_codes=tuple(risk_codes),
        created_at=created_at,
        digest="",
    )
    return replace(record, digest=_digest("workspace-change-set-block-receipt-", record.to_dict()))


def validate_workspace_change_set_block_receipt(receipt: WorkspaceChangeSetBlockReceipt) -> WorkspaceChangeSetValidationResult:
    findings = list(_contradiction_findings(receipt))
    if receipt.block_status not in BLOCK_RECEIPT_STATUSES:
        findings.append("unknown_block_receipt_status")
    status = receipt.block_status if not findings else "workspace_change_set_block_receipt_contradicted"
    return WorkspaceChangeSetValidationResult(not findings, status, tuple(sorted(set(findings))))


def summarize_workspace_change_set_manifest(manifest: WorkspaceChangeSetManifest) -> dict[str, Any]:
    return {
        "manifest_id": manifest.manifest_id,
        "manifest_status": manifest.manifest_status,
        "target_count": manifest.target_count,
        "total_payload_bytes": manifest.total_payload_bytes,
        "metadata_only": manifest.metadata_only,
        "mutation_allowed": manifest.mutation_allowed,
        "target_write_performed": manifest.target_write_performed,
        "digest": manifest.digest,
    }


def summarize_workspace_change_set_preflight_report(report: WorkspaceChangeSetPreflightReport) -> dict[str, Any]:
    return {
        "report_id": report.report_id,
        "report_status": report.report_status,
        "passed_targets": len(report.passed_target_ids),
        "blocked_targets": len(report.blocked_target_ids),
        "preflight_report_only": report.preflight_report_only,
        "read_only": report.read_only,
        "target_write_performed": report.target_write_performed,
        "host_mutation_performed": report.host_mutation_performed,
        "digest": report.digest,
    }


def summarize_workspace_change_set_rollback_plan(plan: WorkspaceChangeSetRollbackPlan) -> dict[str, Any]:
    return {
        "plan_id": plan.plan_id,
        "rollback_plan_status": plan.rollback_plan_status,
        "rollback_strategy": plan.rollback_strategy,
        "entry_count": len(plan.target_rollback_entries),
        "metadata_only": plan.metadata_only,
        "rollback_not_performed": plan.rollback_not_performed,
        "target_rollback_performed": plan.target_rollback_performed,
        "digest": plan.digest,
    }


def summarize_workspace_change_set_transaction_plan(plan: WorkspaceChangeSetTransactionPlan) -> dict[str, Any]:
    return {
        "plan_id": plan.plan_id,
        "transaction_plan_status": plan.transaction_plan_status,
        "planned_target_count": len(plan.planned_target_order),
        "execution_strategy": plan.execution_strategy,
        "transaction_plan_only": plan.transaction_plan_only,
        "execution_not_started": plan.execution_not_started,
        "target_write_performed": plan.target_write_performed,
        "target_rollback_performed": plan.target_rollback_performed,
        "digest": plan.digest,
    }


def summarize_workspace_change_set_block_receipt(receipt: WorkspaceChangeSetBlockReceipt) -> dict[str, Any]:
    return {
        "receipt_id": receipt.receipt_id,
        "block_status": receipt.block_status,
        "blocked_target_count": len(receipt.blocked_target_ids),
        "block_receipt_only": receipt.block_receipt_only,
        "execution_not_started": receipt.execution_not_started,
        "host_mutation_performed": receipt.host_mutation_performed,
        "digest": receipt.digest,
    }


def run_workspace_change_set_preflight_wing(
    *,
    workspace_root: str | Path,
    targets: Sequence[WorkspaceChangeTargetDeclaration],
    policy: WorkspaceChangeSetPolicy | None = None,
    created_at: str = DEFAULT_CREATED_AT,
) -> dict[str, Any]:
    policy = policy or build_default_workspace_change_set_policy()
    manifest = build_workspace_change_set_manifest(workspace_root=workspace_root, targets=targets, policy=policy, created_at=created_at)
    target_preflights = tuple(preflight_workspace_change_target(workspace_root=workspace_root, target=target, policy=policy, created_at=created_at) for target in targets)
    report = build_workspace_change_set_preflight_report(manifest=manifest, target_preflights=target_preflights, created_at=created_at)
    rollback_plan = build_workspace_change_set_rollback_plan(manifest=manifest, preflight_report=report, target_preflights=target_preflights, created_at=created_at)
    transaction_plan = build_workspace_change_set_transaction_plan(manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, created_at=created_at)
    block_receipt = None
    if report.report_status not in {"workspace_change_set_preflight_passed", "workspace_change_set_preflight_passed_with_warnings"}:
        block_receipt = build_workspace_change_set_block_receipt(
            manifest_id=manifest.manifest_id,
            block_reason_codes=report.risk_codes or (report.report_status,),
            blocked_target_ids=report.blocked_target_ids,
            risk_codes=report.risk_codes,
            created_at=created_at,
        )
    return {
        "metadata_only": True,
        "preflight_planning_only": True,
        "read_only": True,
        "mutation_allowed": False,
        "target_write_performed": False,
        "target_rollback_performed": False,
        "host_mutation_performed": False,
        "runner_orchestrator_invoked": False,
        "subprocess_used": False,
        "shell_used": False,
        "network_used": False,
        "provider_invocation_performed": False,
        "prompt_assembly_performed": False,
        "blocked_actions": tuple(sorted(set(BLOCKED_ACTION_LABELS))),
        "policy": policy.to_dict(),
        "manifest": manifest.to_dict(),
        "target_preflights": tuple(preflight.to_dict() for preflight in target_preflights),
        "preflight_report": report.to_dict(),
        "rollback_plan": rollback_plan.to_dict(),
        "transaction_plan": transaction_plan.to_dict(),
        "block_receipt": block_receipt.to_dict() if block_receipt else None,
        "summary": {
            "manifest": summarize_workspace_change_set_manifest(manifest),
            "preflight_report": summarize_workspace_change_set_preflight_report(report),
            "rollback_plan": summarize_workspace_change_set_rollback_plan(rollback_plan),
            "transaction_plan": summarize_workspace_change_set_transaction_plan(transaction_plan),
            "block_receipt": summarize_workspace_change_set_block_receipt(block_receipt) if block_receipt else None,
            "prepares_multi_target_changes": True,
            "executes_multi_target_changes": False,
            "reads_only_declared_targets": True,
            "target_writes": False,
            "rollback_performed": False,
        },
    }
