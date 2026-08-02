"""Self-contained, read-only custody for one diagnostic execution and rollback."""
from __future__ import annotations

import fcntl
import ctypes
import errno
import hashlib
import json
import os
import stat
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from sentientos.host_local_diagnostic_execution_runtime import (
    ARTIFACT_NAME,
    FORBIDDEN_FLAGS,
    validate_persisted_execution_bundle,
)
from sentientos.host_local_diagnostic_execution_source_runtime import _canon, _dict, _raw_sha, _sha, digest_record
from sentientos.host_local_diagnostic_rollback_runtime import ROLLBACK_SCOPE, validate_persisted_rollback_bundle

SCHEMA_VERSION = "host_local_diagnostic_lifecycle_closure.v1"
EXECUTION_PATH = "bundles/execution"
ROLLBACK_PATH = "bundles/rollback"
OUTER_FILES = ("closure_report.json", "summary.json", "receipt.json")
_HEX = frozenset("0123456789abcdef")
_STAGING_PREFIX = ".hldlc-"
_STAGING_IDENTITY_PREFIX = ".hldlc-staging-identity-"
_STAGING_IDENTITY = "host_local_diagnostic_lifecycle_closure_staging.v1"


@dataclass(frozen=True)
class ClosureOutcome:
    status: str
    findings: tuple[str, ...]
    records: Mapping[str, Any]
    packet_root: str = ""
    replayed: bool = False
    publication_posture: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def derive_closure_id(execution_bundle_digest: str, rollback_bundle_digest: str, closure_time: str) -> str:
    """Derive the sole closure identity from validated bundle digests and time."""
    identity = {
        "execution_bundle_digest": execution_bundle_digest,
        "rollback_bundle_digest": rollback_bundle_digest,
        "closure_time": closure_time,
    }
    return "hldlc-" + hashlib.sha256(_canon(identity).encode()).hexdigest()[:24]


def _json(path: Path) -> dict[str, Any]:
    value = _dict(json.loads(path.read_text()))
    return dict(value)


def _bundle_digest(root: Path) -> str:
    return str(_json(root / "bundle_manifest.json").get("bundle_digest", ""))


def _safe_root(value: str | Path, *, create: bool = False) -> tuple[Path, list[str]]:
    path = Path(value).resolve(strict=False)
    findings: list[str] = []
    if path.exists() and (path.is_symlink() or not path.is_dir()):
        findings.append("unsafe_root")
    if any(parent.is_symlink() for parent in [path, *path.parents] if parent.exists()):
        findings.append("symlinked_root")
    if create and not findings:
        path.mkdir(parents=True, exist_ok=True)
    return path, findings


def _cross_validate(execution: Mapping[str, Any], rollback: Mapping[str, Any], execution_digest: str) -> tuple[dict[str, Any], list[str]]:
    findings: list[str] = []
    req = _dict(execution.get("runtime_request")); tx = _dict(execution.get("transaction_records"))
    historical = _dict(tx.get("closure_report")); snapshots = _dict(execution.get("target_snapshots"))
    artifact = _dict(snapshots.get(ARTIFACT_NAME)); plan_snap = _dict(snapshots.get("rollback_plan.json"))
    try:
        plan = _dict(json.loads(bytes.fromhex(str(plan_snap.get("bytes_hex", "")))))
    except (ValueError, json.JSONDecodeError):
        plan = {}; findings.append("rollback_plan_snapshot_invalid")
    runtime = _dict(rollback.get("runtime_result")); challenge = _dict(rollback.get("confirmation_challenge"))
    confirmation = _dict(rollback.get("operator_confirmation")); embedded = _dict(rollback.get("embedded_execution_records"))
    lifecycle = _dict(rollback.get("updated_lifecycle_report")); post = _dict(rollback.get("post_rollback_snapshot"))
    rb_request = _dict(_dict(rollback.get("rollback_records")).get("request"))
    execution_id = "hlder-" + hashlib.sha256(_canon({k: v for k, v in req.items() if k != "schema_version"}).encode()).hexdigest()[:24]
    pairs = {
        "execution_id": (execution_id, runtime.get("execution_id"), challenge.get("execution_id"), confirmation.get("execution_id")),
        "source_request_id": (req.get("source_request_id"), runtime.get("source_request_id"), challenge.get("source_request_id"), confirmation.get("source_request_id")),
        "source_request_digest": (req.get("source_request_digest"), runtime.get("source_request_digest"), challenge.get("source_request_digest"), confirmation.get("source_request_digest")),
        "correlation_id": (req.get("correlation_id"), runtime.get("correlation_id"), challenge.get("correlation_id"), confirmation.get("correlation_id")),
        "execution_bundle_digest": (execution_digest, rollback.get("expected_execution_bundle_digest"), runtime.get("execution_bundle_digest"), challenge.get("completed_execution_bundle_digest"), confirmation.get("confirmed_bundle_digest")),
        "artifact_path": (artifact.get("path"), challenge.get("historical_artifact_path"), confirmation.get("confirmed_artifact_path"), post.get("path")),
        "artifact_digest": (artifact.get("sha256"), challenge.get("historical_artifact_digest")),
        "rollback_plan_id": (plan.get("plan_id"), challenge.get("rollback_plan_id"), rb_request.get("source_rollback_plan_id")),
        "rollback_plan_digest": (plan.get("digest"), challenge.get("rollback_plan_digest"), rb_request.get("source_rollback_plan_digest")),
    }
    for name, values in pairs.items():
        if not values[0] or any(value != values[0] for value in values[1:]):
            findings.append("cross_bundle_" + name + "_mismatch")
    if _canon(embedded) != _canon(execution): findings.append("embedded_execution_substitution")
    if historical.get("lifecycle_status") != "local_effect_lifecycle_rollback_pending": findings.append("historical_lifecycle_not_rollback_pending")
    if lifecycle.get("lifecycle_status") != "local_effect_lifecycle_complete_with_rollback": findings.append("final_lifecycle_not_complete_with_rollback")
    if runtime.get("status") != "host_local_diagnostic_rollback_completed" or runtime.get("historical_diagnostic_write") is not True or runtime.get("rollback_invoked_historically") is not True: findings.append("rollback_completion_invalid")
    if confirmation.get("exact_rollback_scope") != ROLLBACK_SCOPE or runtime.get("exact_diagnostic_rollback_authorized") is not True: findings.append("exact_rollback_scope_missing")
    if post != {"path": artifact.get("path"), "exists": False}: findings.append("artifact_deletion_boundary_invalid")
    if rollback.get("unrelated_siblings_before") != rollback.get("unrelated_siblings_after"): findings.append("unrelated_siblings_not_preserved")
    if any(_dict(record).get(flag) is not False for record in (runtime, confirmation) for flag in FORBIDDEN_FLAGS): findings.append("broader_authority_present")
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION, "artifact_kind": "host_local_diagnostic_lifecycle_closure_report",
        "execution_id": execution_id, "rollback_id": runtime.get("rollback_id"),
        "source_request_id": req.get("source_request_id"), "source_request_digest": req.get("source_request_digest"), "correlation_id": req.get("correlation_id"),
        "execution_bundle_digest": execution_digest, "artifact_path": artifact.get("path"), "artifact_digest": artifact.get("sha256"),
        "rollback_plan_id": plan.get("plan_id"), "rollback_plan_digest": plan.get("digest"), "execution_time": req.get("execution_time"), "rollback_time": None,
        "historical_lifecycle": historical.get("lifecycle_status"), "final_lifecycle": lifecycle.get("lifecycle_status"),
        "rollback_posture": "direct" if runtime.get("rollback_invoked_by_current_coordinator") is True else "reconciled",
        "historical_execution_call_count": 1, "historical_rollback_call_count": 1,
        "closure_processing_execution_call_count": 0, "closure_processing_rollback_call_count": 0,
        "mutation_boundary": runtime.get("exact_file_mutation"), "unrelated_siblings_preserved": rollback.get("unrelated_siblings_before") == rollback.get("unrelated_siblings_after"),
        "runtime_owned_files_preserved": True, "broader_authority": False,
        "authenticity_note": "Unkeyed digests provide integrity binding, not authorship or external authenticity.",
    }
    history = rollback.get("rollback_intent_history", [])
    if isinstance(history, list) and history:
        report["rollback_time"] = _dict(_dict(history[0]).get("identity")).get("rollback_time")
    return report, findings


def _identity(report: Mapping[str, Any], closure_id: str, closure_time: str, execution_digest: str, rollback_digest: str) -> dict[str, Any]:
    return {
        "closure_id": closure_id, "closure_time": closure_time,
        "execution_id": report.get("execution_id"), "rollback_id": report.get("rollback_id"),
        "source_request_id": report.get("source_request_id"), "source_request_digest": report.get("source_request_digest"),
        "correlation_id": report.get("correlation_id"), "execution_bundle_digest": execution_digest,
        "rollback_bundle_digest": rollback_digest, "final_lifecycle": report.get("final_lifecycle"),
    }


def _entry(root: Path, name: str) -> dict[str, Any]:
    raw = (root / name).read_bytes()
    return {"relative_filename": name, "size_bytes": len(raw), "sha256": _raw_sha(raw)}


def _manifest(root: Path, names: list[str], kind: str, digest_name: str, metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
    value: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "artifact_kind": kind, **dict(metadata or {}), "files": [_entry(root, name) for name in sorted(names)]}
    value[digest_name] = _sha(value)
    return value


def _valid_sha(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("sha256:") and len(value) == 71 and set(value[7:]) <= _HEX


def _validate_manifest(root: Path, manifest: Mapping[str, Any], *, kind: str, digest_name: str, expected_names: set[str], metadata: Mapping[str, Any] | None = None) -> list[str]:
    findings: list[str] = []
    exact = {"schema_version", "artifact_kind", "files", digest_name} | set((metadata or {}).keys())
    if set(manifest) != exact or manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("artifact_kind") != kind:
        findings.append(kind + "_schema_invalid")
    if metadata and any(manifest.get(k) != v for k, v in metadata.items()): findings.append(kind + "_identity_invalid")
    check = dict(manifest); claimed = check.pop(digest_name, None)
    if not _valid_sha(claimed) or claimed != _sha(check): findings.append(kind + "_digest_invalid")
    entries = manifest.get("files")
    if not isinstance(entries, list): return findings + [kind + "_entries_invalid"]
    names: list[str] = []
    for raw_entry in entries:
        if not isinstance(raw_entry, dict) or set(raw_entry) != {"relative_filename", "size_bytes", "sha256"}:
            findings.append(kind + "_entry_schema_invalid"); continue
        name = raw_entry.get("relative_filename"); size = raw_entry.get("size_bytes"); digest = raw_entry.get("sha256")
        if not isinstance(name, str): findings.append(kind + "_path_invalid"); continue
        pure = PurePosixPath(name)
        path = root / name
        if not name or pure.is_absolute() or ".." in pure.parts or "." in pure.parts or "\\" in name or path.is_symlink() or not path.is_file():
            findings.append(kind + "_path_invalid:" + name); continue
        names.append(name)
        raw = path.read_bytes()
        if isinstance(size, bool) or not isinstance(size, int) or size < 0 or not _valid_sha(digest) or size != len(raw) or digest != _raw_sha(raw): findings.append(kind + "_file_invalid:" + name)
    if len(names) != len(set(names)) or set(names) != expected_names: findings.append(kind + "_membership_invalid")
    return findings


def _packet_files(root: Path) -> tuple[set[str], list[str]]:
    findings: list[str] = []
    names: set[str] = set()
    for path in root.rglob("*"):
        if path.is_symlink(): findings.append("symlinked_packet_artifact")
        elif path.is_file(): names.add(path.relative_to(root).as_posix())
    return names, findings


def _snapshot_finding(prefix: str, before: tuple[_StagingMemberCustody, ...], after: tuple[_StagingMemberCustody, ...]) -> str:
    difference = _packet_snapshot_difference(before, after)
    mapping = {
        "lifecycle_packet_membership_changed_before_commit": prefix + "membership_changed",
        "lifecycle_packet_member_identity_changed_before_commit": prefix + "member_identity_changed",
        "lifecycle_packet_member_metadata_changed_before_commit": prefix + "member_metadata_changed",
        "lifecycle_packet_member_bytes_changed_before_commit": prefix + "member_bytes_changed",
    }
    return mapping.get(difference, "")


def _descriptor_adapter(fd: int, callback: Any) -> Any:
    """Invoke a read-only path API through an unresolved, identity-checked fd alias."""
    alias = Path("/proc/self/fd") / str(fd)
    try:
        expected = _metadata(os.fstat(fd))
        if _metadata(os.stat(alias, follow_symlinks=True)) != expected:
            raise OSError("descriptor adapter identity mismatch")
        result = callback(alias)
        if _metadata(os.fstat(fd)) != expected or _metadata(os.stat(alias, follow_symlinks=True)) != expected:
            raise OSError("descriptor adapter identity changed")
        return result
    except OSError as exc:
        raise _StagingCustodyMismatch("lifecycle_descriptor_adapter_unavailable") from exc


def _validate_nested_bound(packet_fd: int, role: str, execution_digest: str = "", expected_member: _StagingMemberCustody | None = None) -> Any:
    bundles_fd = _open_directory("bundles", dir_fd=packet_fd)
    try:
        nested_fd = _open_directory(role, dir_fd=bundles_fd)
        try:
            entry = os.stat(role, dir_fd=bundles_fd, follow_symlinks=False)
            expected = _metadata(os.fstat(nested_fd))
            if _metadata(entry) != expected or (expected_member is not None and _metadata(entry) != ((expected_member.device, expected_member.inode, expected_member.object_type), expected_member.mode, expected_member.size, expected_member.modification_time_ns)):
                raise _StagingCustodyMismatch(f"nested_{role}_root_identity_changed")
            before = _packet_snapshot(nested_fd)
            if role == "execution":
                digest = _descriptor_adapter(nested_fd, lambda path: _bundle_digest(path))
                result = _descriptor_adapter(nested_fd, lambda path: validate_persisted_execution_bundle(path, expected_final_bundle_digest=digest))
            else:
                digest = _descriptor_adapter(nested_fd, lambda path: _bundle_digest(path))
                result = _descriptor_adapter(nested_fd, lambda path: validate_persisted_rollback_bundle(path, expected_final_bundle_digest=digest, expected_execution_bundle_digest=execution_digest))
            after = _packet_snapshot(nested_fd)
            rebound = os.stat(role, dir_fd=bundles_fd, follow_symlinks=False)
            if _metadata(rebound) != expected or _metadata(os.fstat(nested_fd)) != expected:
                raise _StagingCustodyMismatch(f"nested_{role}_root_identity_changed")
            if before != after:
                raise _StagingCustodyMismatch(f"nested_{role}_tree_changed_during_validation")
            return digest, result
        finally:
            os.close(nested_fd)
    finally:
        os.close(bundles_fd)


def _validate_lifecycle_closure_bound(packet_fd: int, logical_packet_path: Path, logical_packet_basename: str, *, expected_packet_digest: str | None = None, initial_snapshot: tuple[_StagingMemberCustody, ...] | None = None) -> ClosureOutcome:
    findings: list[str] = []; records: dict[str, Any] = {}
    root_expected = _metadata(os.fstat(packet_fd))
    try:
        if initial_snapshot is None:
            initial_snapshot = _packet_snapshot(packet_fd)
        _publication_hook("lifecycle_validation_after_initial_snapshot", logical_packet_path)
        initial_members = {member.relative_path: member for member in initial_snapshot}
        execution_digest, ev = _validate_nested_bound(packet_fd, "execution", expected_member=initial_members.get(EXECUTION_PATH))
        _publication_hook("lifecycle_validation_after_nested_execution", logical_packet_path)
        rollback_digest, rv = _validate_nested_bound(packet_fd, "rollback", execution_digest, initial_members.get(ROLLBACK_PATH))
        _publication_hook("lifecycle_validation_after_nested_rollback", logical_packet_path)
        findings.extend("nested_execution:" + x for x in ev.findings); findings.extend("nested_rollback:" + x for x in rv.findings)
        base_report, cross = _cross_validate(ev.records, rv.records, execution_digest); findings.extend(cross)
        def semantic(alias: Path) -> tuple[dict[str, Any], set[str]]:
            actual, path_findings = _packet_files(alias); findings.extend(path_findings)
            report = _json(alias / "closure_report.json"); summary = _json(alias / "summary.json"); receipt = _json(alias / "receipt.json")
            content = _json(alias / "content_manifest.json"); final = _json(alias / "final_manifest.json")
            times = {record.get("closure_time") for record in (report, summary, receipt, final)}
            if len(times) != 1 or not isinstance(next(iter(times), None), str) or not next(iter(times), ""):
                findings.append("closure_time_custody_mismatch"); closure_time = ""
            else: closure_time = str(next(iter(times)))
            derived_id = derive_closure_id(execution_digest, rollback_digest, closure_time)
            ids = {record.get("closure_id") for record in (report, summary, receipt, final)}
            if ids != {derived_id} or logical_packet_basename != derived_id: findings.append("closure_identity_custody_mismatch")
            identity = _identity(base_report, derived_id, closure_time, execution_digest, rollback_digest)
            expected_report = {**base_report, **identity}; expected_report["digest"] = digest_record(expected_report)
            if report != expected_report: findings.append("closure_report_invalid")
            expected_summary = {"schema_version": SCHEMA_VERSION, "artifact_kind": "host_local_diagnostic_lifecycle_closure_summary", "status": "host_local_diagnostic_lifecycle_closed", **identity}; expected_summary["digest"] = digest_record(expected_summary)
            if summary != expected_summary: findings.append("summary_invalid")
            nested_names = {name for name in actual if name.startswith(EXECUTION_PATH + "/") or name.startswith(ROLLBACK_PATH + "/")}
            content_names = nested_names | {"closure_report.json", "summary.json"}
            findings.extend(_validate_manifest(alias, content, kind="host_local_diagnostic_lifecycle_closure_content_manifest", digest_name="content_manifest_digest", expected_names=content_names))
            expected_receipt = {"schema_version": SCHEMA_VERSION, "artifact_kind": "host_local_diagnostic_lifecycle_closure_receipt", **identity, "closure_report_digest": _sha(report), "summary_digest": _sha(summary), "content_manifest_digest": content.get("content_manifest_digest")}; expected_receipt["digest"] = digest_record(expected_receipt)
            if receipt != expected_receipt: findings.append("receipt_invalid")
            final_names = content_names | {"content_manifest.json", "receipt.json"}
            findings.extend(_validate_manifest(alias, final, kind="host_local_diagnostic_lifecycle_closure_final_manifest", digest_name="packet_digest", expected_names=final_names, metadata=identity))
            if actual != final_names | {"final_manifest.json"}: findings.append("exact_packet_membership_invalid")
            if expected_packet_digest is not None and final.get("packet_digest") != expected_packet_digest: findings.append("expected_packet_digest_mismatch")
            return {"closure_report": report, "summary": summary, "receipt": receipt, "content_manifest": content, "final_manifest": final}, actual
        records, _ = _descriptor_adapter(packet_fd, semantic)
        _publication_hook("lifecycle_validation_before_terminal_snapshot", logical_packet_path)
        terminal = _packet_snapshot(packet_fd)
        difference = _snapshot_finding("lifecycle_validation_packet_", initial_snapshot, terminal)
        if difference: findings.append(difference)
        if _metadata(os.fstat(packet_fd)) != root_expected:
            findings.append("lifecycle_validation_packet_root_metadata_changed")
    except _StagingCustodyMismatch as exc:
        findings.append({
            "lifecycle_packet_membership_changed_before_commit": "lifecycle_validation_packet_membership_changed",
            "lifecycle_packet_member_identity_changed_before_commit": "lifecycle_validation_packet_member_identity_changed",
            "lifecycle_packet_member_metadata_changed_before_commit": "lifecycle_validation_packet_member_metadata_changed",
            "lifecycle_packet_member_bytes_changed_before_commit": "lifecycle_validation_packet_member_bytes_changed",
        }.get(exc.finding, exc.finding))
    except Exception as exc:
        findings.append("packet_decode_failed:" + type(exc).__name__)
    status = "host_local_diagnostic_lifecycle_closure_valid" if not findings else "host_local_diagnostic_lifecycle_closure_invalid"
    return ClosureOutcome(status, tuple(sorted(set(findings))), records, str(logical_packet_path), True, "validated" if not findings else "rejected")


def validate_lifecycle_closure(packet_root: str | Path, *, expected_packet_digest: str | None = None) -> ClosureOutcome:
    logical, findings = _safe_root(packet_root)
    if findings:
        return ClosureOutcome("host_local_diagnostic_lifecycle_closure_invalid", tuple(findings), {}, str(logical), True, "rejected")
    try:
        packet_fd = _open_directory(logical)
    except OSError:
        return ClosureOutcome("host_local_diagnostic_lifecycle_closure_invalid", ("lifecycle_validation_packet_root_identity_changed",), {}, str(logical), True, "rejected")
    try:
        expected = _metadata(os.fstat(packet_fd))
        _publication_hook("lifecycle_validation_after_packet_root_open", logical)
        if not _source_root_bound(logical, packet_fd, expected):
            return ClosureOutcome("host_local_diagnostic_lifecycle_closure_invalid", ("lifecycle_validation_packet_root_identity_changed",), {}, str(logical), True, "rejected")
        result = _validate_lifecycle_closure_bound(packet_fd, logical, logical.name, expected_packet_digest=expected_packet_digest)
        final_findings = list(result.findings)
        try:
            named = _metadata(os.stat(logical, follow_symlinks=False)); opened = _metadata(os.fstat(packet_fd))
            if named[0] != expected[0] or opened[0] != expected[0]: final_findings.append("lifecycle_validation_packet_root_identity_changed")
            elif named != expected or opened != expected: final_findings.append("lifecycle_validation_packet_root_metadata_changed")
        except OSError: final_findings.append("lifecycle_validation_packet_root_identity_changed")
        if final_findings:
            return ClosureOutcome("host_local_diagnostic_lifecycle_closure_invalid", tuple(sorted(set(final_findings))), result.records, str(logical), True, "rejected")
        return result
    finally:
        os.close(packet_fd)


# Small named hooks deliberately provide deterministic test interception points.
def _publication_hook(event: str, path: Path) -> None:
    """Internal no-op boundary hook used only by explicitly injected tests."""


def _copy_bundle(source: Path, destination: Path) -> None:
    raise RuntimeError("pathname bundle copying is forbidden")


def _safe_basename(name: str) -> bool:
    return name not in {"", ".", ".."} and Path(name).name == name and PurePosixPath(name).parts == (name,) and "\\" not in name


def _atomic_rename_noreplace(source_dir_fd: int, source_name: str, destination_dir_fd: int, destination_name: str) -> None:
    """Atomically rename descriptor-relative entries without replacing a destination."""
    if not _safe_basename(source_name) or not _safe_basename(destination_name):
        raise ValueError("unsafe atomic rename basename")
    try:
        renameat2 = ctypes.CDLL(None, use_errno=True).renameat2
    except AttributeError as exc:
        raise _AtomicNoReplaceUnsupported("libc renameat2 unavailable") from exc
    renameat2.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    renameat2.restype = ctypes.c_int
    if renameat2(source_dir_fd, os.fsencode(source_name), destination_dir_fd, os.fsencode(destination_name), 1) == 0:
        return
    error = ctypes.get_errno()
    if error in {errno.EEXIST, errno.ENOTEMPTY}:
        raise _AtomicDestinationConflict(destination_name)
    if error in {errno.ENOSYS, errno.EINVAL, errno.ENOTSUP, errno.EOPNOTSUPP}:
        raise _AtomicNoReplaceUnsupported(os.strerror(error))
    raise OSError(error, os.strerror(error))


def _publish_packet(staged_name: str, destination_name: str, *, staging_fd: int, root_fd: int) -> None:
    _atomic_rename_noreplace(staging_fd, staged_name, root_fd, destination_name)


def _publish_latest(staged_name: str, destination_name: str, root_fd: int) -> None:
    _atomic_rename_noreplace(root_fd, staged_name, root_fd, destination_name)


def _pointer(identity: Mapping[str, Any], packet_digest: str) -> dict[str, Any]:
    value = {"schema_version": SCHEMA_VERSION, "artifact_kind": "host_local_diagnostic_lifecycle_closure_pointer", **dict(identity), "packet_digest": packet_digest}
    value["digest"] = digest_record(value)
    return value


def _staging_record(closure_id: str, staging_name: str, publication_root: Path) -> dict[str, Any]:
    value = {
        "artifact_kind": _STAGING_IDENTITY,
        "closure_id": closure_id,
        "publication_root": str(publication_root),
        "staging_name": staging_name,
    }
    value["digest"] = digest_record(value)
    return value


def _valid_staging_record(record: Mapping[str, Any], *, out: Path, staging_name: str) -> tuple[bool, str]:
    check = dict(record); claimed = check.pop("digest", None)
    closure_id = check.get("closure_id")
    safe_name = (
        isinstance(staging_name, str)
        and staging_name.startswith(_STAGING_PREFIX)
        and not staging_name.startswith(_STAGING_IDENTITY_PREFIX)
        and Path(staging_name).name == staging_name
        and PurePosixPath(staging_name).parts == (staging_name,)
    )
    valid_id = isinstance(closure_id, str) and closure_id.startswith("hldlc-") and len(closure_id) == 30 and set(closure_id[6:]) <= _HEX
    valid = (
        set(record) == {"artifact_kind", "closure_id", "publication_root", "staging_name", "digest"}
        and check.get("artifact_kind") == _STAGING_IDENTITY
        and valid_id and safe_name
        and check.get("publication_root") == str(out)
        and check.get("staging_name") == staging_name
        and claimed == digest_record(record)
    )
    return valid, str(closure_id or "")


@dataclass(frozen=True)
class _StagingMemberCustody:
    relative_path: str
    basename: str
    device: int
    inode: int
    object_type: str
    mode: int
    size: int
    modification_time_ns: int
    exact_bytes: bytes = b""
    digest: str = ""
    expected_child_membership: tuple[str, ...] = ()


@dataclass(frozen=True)
class _StagingCandidateCustody:
    kind: str
    basename: str
    device: int
    inode: int
    object_type: str
    mode: int
    size: int
    modification_time_ns: int
    exact_bytes: bytes = b""
    digest: str = ""
    associated_staging_basename: str = ""
    staging_identity_record: tuple[tuple[str, Any], ...] = ()
    expected_immediate_membership: tuple[str, ...] = ()
    nested_members: tuple[_StagingMemberCustody, ...] = ()


class _StagingCustodyMismatch(Exception):
    def __init__(self, finding: str) -> None:
        super().__init__(finding); self.finding = finding


class _AtomicDestinationConflict(Exception):
    pass


class _AtomicNoReplaceUnsupported(Exception):
    pass


@dataclass(frozen=True)
class _PreparedFileCustody:
    basename: str
    descriptor: int
    device: int
    inode: int
    object_type: str
    mode: int
    size: int
    modification_time_ns: int
    exact_bytes: bytes
    digest: str
    parent_role: str


@dataclass(frozen=True)
class _SourceMemberPlan:
    relative_path: str
    basename: str
    parent_path: str
    role: str
    object_type: str
    device: int
    inode: int
    mode: int
    size: int
    modification_time_ns: int
    child_membership: tuple[str, ...] = ()
    digest: str = ""


_MAX_PACKET_ENTRIES = 4096
_MAX_PACKET_BYTES = 256 * 1024 * 1024
_MAX_PACKET_DEPTH = 32
_MAX_PACKET_PATH = 4096


def _metadata(info: os.stat_result) -> tuple[tuple[int, int, str], int, int, int]:
    return _fs_identity(info), stat.S_IMODE(info.st_mode), info.st_size, info.st_mtime_ns


def _source_root_bound(path: Path, fd: int, expected: tuple[tuple[int, int, str], int, int, int]) -> bool:
    try:
        return _metadata(os.fstat(fd)) == expected == _metadata(os.stat(path, follow_symlinks=False))
    except OSError:
        return False


def _safe_relative(relative: str) -> bool:
    pure = PurePosixPath(relative)
    return (
        bool(relative) and not pure.is_absolute() and len(relative) <= _MAX_PACKET_PATH
        and len(pure.parts) <= _MAX_PACKET_DEPTH and all(_safe_basename(part) for part in pure.parts)
    )


def _read_fd(fd: int, maximum: int) -> bytes:
    chunks: list[bytes] = []; total = 0
    os.lseek(fd, 0, os.SEEK_SET)
    while True:
        chunk = os.read(fd, min(131072, maximum + 1 - total))
        if not chunk: break
        chunks.append(chunk); total += len(chunk)
        if total > maximum: raise _StagingCustodyMismatch("lifecycle_source_plan_byte_bound_exceeded")
    return b"".join(chunks)


def _build_source_plan(root_fd: int, role: str) -> tuple[_SourceMemberPlan, ...]:
    plans: list[_SourceMemberPlan] = []; total = 0
    def walk(parent_fd: int, parent_path: str) -> None:
        nonlocal total
        names = tuple(sorted(os.listdir(parent_fd)))
        for name in names:
            relative = f"{parent_path}/{name}" if parent_path else name
            if not _safe_basename(name) or not _safe_relative(relative):
                raise _StagingCustodyMismatch("lifecycle_source_member_symlink_or_unsupported")
            entry = os.stat(name, dir_fd=parent_fd, follow_symlinks=False); kind = _fs_type(entry.st_mode)
            if kind == "directory":
                child_fd = _open_directory(name, dir_fd=parent_fd)
                try:
                    opened = os.fstat(child_fd)
                    if _metadata(opened) != _metadata(entry): raise _StagingCustodyMismatch("lifecycle_source_member_identity_changed_before_copy")
                    children = tuple(sorted(os.listdir(child_fd)))
                    plans.append(_SourceMemberPlan(relative, name, parent_path, role, kind, opened.st_dev, opened.st_ino, stat.S_IMODE(opened.st_mode), opened.st_size, opened.st_mtime_ns, children))
                    walk(child_fd, relative)
                    if _metadata(os.fstat(child_fd)) != _metadata(opened) or _metadata(os.stat(name, dir_fd=parent_fd, follow_symlinks=False)) != _metadata(opened):
                        raise _StagingCustodyMismatch("lifecycle_source_member_metadata_changed_during_copy")
                finally: os.close(child_fd)
            elif kind == "regular":
                fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd)
                try:
                    opened = os.fstat(fd)
                    if _metadata(opened) != _metadata(entry): raise _StagingCustodyMismatch("lifecycle_source_member_identity_changed_before_copy")
                    raw = _read_fd(fd, _MAX_PACKET_BYTES - total); terminal = os.fstat(fd)
                    if _metadata(terminal) != _metadata(opened) or _metadata(os.stat(name, dir_fd=parent_fd, follow_symlinks=False)) != _metadata(opened):
                        raise _StagingCustodyMismatch("lifecycle_source_member_metadata_changed_during_copy")
                    total += len(raw)
                    plans.append(_SourceMemberPlan(relative, name, parent_path, role, kind, opened.st_dev, opened.st_ino, stat.S_IMODE(opened.st_mode), opened.st_size, opened.st_mtime_ns, digest=_raw_sha(raw)))
                finally: os.close(fd)
            else: raise _StagingCustodyMismatch("lifecycle_source_member_symlink_or_unsupported")
            if len(plans) > _MAX_PACKET_ENTRIES: raise _StagingCustodyMismatch("lifecycle_source_plan_entry_bound_exceeded")
    walk(root_fd, "")
    return tuple(plans)


def _fs_type(mode: int) -> str:
    if stat.S_ISREG(mode): return "regular"
    if stat.S_ISDIR(mode): return "directory"
    if stat.S_ISLNK(mode): return "symlink"
    return "unsupported"


def _fs_identity(info: os.stat_result) -> tuple[int, int, str]:
    return info.st_dev, info.st_ino, _fs_type(info.st_mode)


def _directory_flags() -> int:
    return os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)


def _open_directory(name: str | Path, *, dir_fd: int | None = None) -> int:
    return os.open(name, _directory_flags(), dir_fd=dir_fd)


def _mkdir_at(parent_fd: int, name: str, hint: Path) -> int:
    if not _safe_basename(name): raise _StagingCustodyMismatch("lifecycle_destination_directory_conflict")
    _publication_hook("lifecycle_copy_before_destination_directory_create", hint)
    try: os.mkdir(name, 0o700, dir_fd=parent_fd)
    except FileExistsError as exc: raise _StagingCustodyMismatch("lifecycle_destination_directory_conflict") from exc
    fd = _open_directory(name, dir_fd=parent_fd); opened = os.fstat(fd); entry = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if _metadata(opened) != _metadata(entry) or stat.S_IMODE(opened.st_mode) != 0o700:
        os.close(fd); raise _StagingCustodyMismatch("lifecycle_destination_member_identity_mismatch")
    _publication_hook("lifecycle_copy_after_destination_directory_create", hint)
    return fd


def _open_relative_directory(root_fd: int, relative: str) -> tuple[int, list[int]]:
    current = root_fd; opened: list[int] = []
    if relative:
        for part in PurePosixPath(relative).parts:
            current = _open_directory(part, dir_fd=current); opened.append(current)
    return current, opened


def _copy_planned_bundle(source_fd: int, destination_parent_fd: int, destination_name: str, plan: tuple[_SourceMemberPlan, ...], role: str, hint_root: Path) -> None:
    destination_fd = _mkdir_at(destination_parent_fd, destination_name, hint_root / destination_name)
    destination_dirs: dict[str, int] = {"": destination_fd}
    try:
        for member in plan:
            source_parent, source_opened = _open_relative_directory(source_fd, member.parent_path)
            try:
                if member.object_type == "directory":
                    destination_parent = destination_dirs[member.parent_path]
                    child = _mkdir_at(destination_parent, member.basename, hint_root / destination_name / member.relative_path)
                    info = os.fstat(child)
                    if _metadata(info) != (((member.device, member.inode, "directory")), member.mode, member.size, member.modification_time_ns):
                        # Destination metadata intentionally differs from the source; only its private mode is authoritative.
                        if stat.S_IMODE(info.st_mode) != 0o700: raise _StagingCustodyMismatch("lifecycle_destination_member_identity_mismatch")
                    destination_dirs[member.relative_path] = child
                    source_entry = os.stat(member.basename, dir_fd=source_parent, follow_symlinks=False)
                    source_child = _open_directory(member.basename, dir_fd=source_parent)
                    try:
                        if _metadata(source_entry) != ((member.device, member.inode, member.object_type), member.mode, member.size, member.modification_time_ns) or _metadata(os.fstat(source_child)) != _metadata(source_entry) or tuple(sorted(os.listdir(source_child))) != member.child_membership:
                            raise _StagingCustodyMismatch("lifecycle_source_member_identity_changed_before_copy")
                    finally: os.close(source_child)
                    continue
                _publication_hook("lifecycle_copy_before_source_member_open", hint_root / destination_name / member.relative_path)
                try: entry = os.stat(member.basename, dir_fd=source_parent, follow_symlinks=False)
                except OSError as exc: raise _StagingCustodyMismatch("lifecycle_source_member_identity_changed_before_copy") from exc
                expected = ((member.device, member.inode, member.object_type), member.mode, member.size, member.modification_time_ns)
                if _metadata(entry) != expected: raise _StagingCustodyMismatch("lifecycle_source_member_identity_changed_before_copy")
                try: source_member_fd = os.open(member.basename, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=source_parent)
                except OSError as exc: raise _StagingCustodyMismatch("lifecycle_source_member_symlink_or_unsupported") from exc
                try:
                    if _metadata(os.fstat(source_member_fd)) != expected: raise _StagingCustodyMismatch("lifecycle_source_member_identity_changed_before_copy")
                    _publication_hook("lifecycle_copy_after_source_member_open", hint_root / destination_name / member.relative_path)
                    destination_parent = destination_dirs[member.parent_path]
                    _publication_hook("lifecycle_copy_before_destination_member_create", hint_root / destination_name / member.relative_path)
                    try: destination_member_fd = os.open(member.basename, os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=destination_parent)
                    except FileExistsError as exc: raise _StagingCustodyMismatch("lifecycle_destination_file_conflict") from exc
                    try:
                        _publication_hook("lifecycle_copy_after_destination_member_create", hint_root / destination_name / member.relative_path)
                        digest = hashlib.sha256(); copied = 0
                        while True:
                            chunk = os.read(source_member_fd, 131072)
                            if not chunk: break
                            copied += len(chunk); digest.update(chunk); offset = 0
                            while offset < len(chunk):
                                written = os.write(destination_member_fd, chunk[offset:])
                                if written <= 0: raise OSError("short descriptor-relative write")
                                offset += written
                        _publication_hook("lifecycle_copy_before_source_member_finalize", hint_root / destination_name / member.relative_path)
                        terminal = os.fstat(source_member_fd); rebound = os.stat(member.basename, dir_fd=source_parent, follow_symlinks=False)
                        if _metadata(terminal) != expected or _metadata(rebound) != expected:
                            finding = "lifecycle_source_member_identity_changed_before_copy" if _fs_identity(terminal) != expected[0] or _fs_identity(rebound) != expected[0] else "lifecycle_source_member_metadata_changed_during_copy"
                            raise _StagingCustodyMismatch(finding)
                        actual_digest = "sha256:" + digest.hexdigest()
                        if copied != member.size or actual_digest != member.digest: raise _StagingCustodyMismatch("lifecycle_source_member_bytes_changed_during_copy")
                        os.fsync(destination_member_fd); destination_info = os.fstat(destination_member_fd); destination_entry = os.stat(member.basename, dir_fd=destination_parent, follow_symlinks=False)
                        if _fs_identity(destination_info) != _fs_identity(destination_entry) or stat.S_IMODE(destination_info.st_mode) != 0o600 or destination_info.st_size != member.size:
                            raise _StagingCustodyMismatch("lifecycle_destination_member_identity_mismatch")
                        raw = _read_fd(destination_member_fd, member.size)
                        if len(raw) != member.size or _raw_sha(raw) != member.digest: raise _StagingCustodyMismatch("lifecycle_destination_member_digest_mismatch")
                    finally: os.close(destination_member_fd)
                finally: os.close(source_member_fd)
            finally:
                for fd in reversed(source_opened): os.close(fd)
        for fd in destination_dirs.values(): _fsync_directory_fd(fd)
    finally:
        for relative, fd in reversed(tuple(destination_dirs.items())):
            os.close(fd)


def _packet_snapshot(packet_fd: int) -> tuple[_StagingMemberCustody, ...]:
    root = os.fstat(packet_fd)
    members: list[_StagingMemberCustody] = [_StagingMemberCustody("", "", root.st_dev, root.st_ino, "directory", stat.S_IMODE(root.st_mode), root.st_size, root.st_mtime_ns, expected_child_membership=tuple(sorted(os.listdir(packet_fd))))]
    total = 0
    def walk(parent_fd: int, prefix: str) -> None:
        nonlocal total
        for name in tuple(sorted(os.listdir(parent_fd))):
            relative = f"{prefix}/{name}" if prefix else name
            if not _safe_relative(relative): raise _StagingCustodyMismatch("lifecycle_packet_membership_changed_before_commit")
            entry = os.stat(name, dir_fd=parent_fd, follow_symlinks=False); kind = _fs_type(entry.st_mode)
            if kind == "directory":
                fd = _open_directory(name, dir_fd=parent_fd)
                try:
                    opened = os.fstat(fd)
                    if _metadata(opened) != _metadata(entry): raise _StagingCustodyMismatch("lifecycle_packet_member_identity_changed_before_commit")
                    children = tuple(sorted(os.listdir(fd)))
                    members.append(_StagingMemberCustody(relative, name, opened.st_dev, opened.st_ino, kind, stat.S_IMODE(opened.st_mode), opened.st_size, opened.st_mtime_ns, expected_child_membership=children)); walk(fd, relative)
                finally: os.close(fd)
            elif kind == "regular":
                raw, opened = _read_file_at(parent_fd, name); total += len(raw)
                members.append(_StagingMemberCustody(relative, name, opened.st_dev, opened.st_ino, kind, stat.S_IMODE(opened.st_mode), opened.st_size, opened.st_mtime_ns, digest=_raw_sha(raw)))
            else: raise _StagingCustodyMismatch("lifecycle_packet_membership_changed_before_commit")
            if len(members) > _MAX_PACKET_ENTRIES or total > _MAX_PACKET_BYTES: raise _StagingCustodyMismatch("lifecycle_packet_membership_changed_before_commit")
    walk(packet_fd, "")
    terminal = os.fstat(packet_fd)
    if _fs_identity(terminal) != _fs_identity(root): raise _StagingCustodyMismatch("lifecycle_packet_member_identity_changed_before_commit")
    return tuple(members)


def _manifest_from_snapshot(snapshot: tuple[_StagingMemberCustody, ...], names: list[str], kind: str, digest_name: str, metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
    files = {member.relative_path: member for member in snapshot if member.object_type == "regular"}
    value: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "artifact_kind": kind, **dict(metadata or {}), "files": [{"relative_filename": name, "size_bytes": files[name].size, "sha256": files[name].digest} for name in sorted(names)]}
    value[digest_name] = _sha(value)
    return value


def _packet_snapshot_difference(before: tuple[_StagingMemberCustody, ...], after: tuple[_StagingMemberCustody, ...]) -> str:
    before_paths = {x.relative_path for x in before}; after_paths = {x.relative_path for x in after}
    if before_paths != after_paths: return "lifecycle_packet_membership_changed_before_commit"
    for old, new in zip(before, after):
        if old.relative_path != new.relative_path: return "lifecycle_packet_membership_changed_before_commit"
        if (old.device, old.inode, old.object_type) != (new.device, new.inode, new.object_type): return "lifecycle_packet_member_identity_changed_before_commit"
        if old.object_type == "regular" and old.digest != new.digest: return "lifecycle_packet_member_bytes_changed_before_commit"
        if (old.mode, old.size, old.modification_time_ns, old.expected_child_membership) != (new.mode, new.size, new.modification_time_ns, new.expected_child_membership): return "lifecycle_packet_member_metadata_changed_before_commit"
    return ""


def _root_is_bound(out: Path, root_fd: int, expected: tuple[int, int, str]) -> bool:
    try:
        opened = os.fstat(root_fd); named = os.stat(out, follow_symlinks=False)
    except OSError:
        return False
    return stat.S_ISDIR(opened.st_mode) and _fs_identity(opened) == expected == _fs_identity(named)


def _read_file_at(parent_fd: int, name: str) -> tuple[bytes, os.stat_result]:
    entry = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if not stat.S_ISREG(entry.st_mode): raise ValueError("not_regular")
    fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd)
    try:
        before = os.fstat(fd)
        if _fs_identity(before) != _fs_identity(entry): raise ValueError("identity_changed")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 131072)
            if not chunk: break
            chunks.append(chunk)
        after = os.fstat(fd); rebound = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if (_fs_identity(before), before.st_size, before.st_mtime_ns) != (_fs_identity(after), after.st_size, after.st_mtime_ns) or _fs_identity(after) != _fs_identity(rebound): raise ValueError("identity_changed")
        return b"".join(chunks), after
    finally: os.close(fd)


def _snapshot_directory_at(parent_fd: int, name: str) -> tuple[os.stat_result, tuple[str, ...], tuple[_StagingMemberCustody, ...]]:
    entry = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if not stat.S_ISDIR(entry.st_mode): raise ValueError("not_directory")
    fd = _open_directory(name, dir_fd=parent_fd)
    try:
        opened = os.fstat(fd)
        if _fs_identity(opened) != _fs_identity(entry): raise ValueError("identity_changed")
        immediate = tuple(sorted(os.listdir(fd))); members: list[_StagingMemberCustody] = []
        def walk(current_fd: int, prefix: str) -> None:
            names = tuple(sorted(os.listdir(current_fd)))
            for child_name in names:
                info = os.stat(child_name, dir_fd=current_fd, follow_symlinks=False); kind = _fs_type(info.st_mode)
                relative = f"{prefix}/{child_name}" if prefix else child_name
                if kind == "regular":
                    raw, stable = _read_file_at(current_fd, child_name)
                    members.append(_StagingMemberCustody(relative, child_name, stable.st_dev, stable.st_ino, kind, stat.S_IMODE(stable.st_mode), stable.st_size, stable.st_mtime_ns, raw, _raw_sha(raw)))
                elif kind == "directory":
                    child_fd = _open_directory(child_name, dir_fd=current_fd)
                    try:
                        stable = os.fstat(child_fd)
                        if _fs_identity(stable) != _fs_identity(info): raise ValueError("identity_changed")
                        membership = tuple(sorted(os.listdir(child_fd)))
                        members.append(_StagingMemberCustody(relative, child_name, stable.st_dev, stable.st_ino, kind, stat.S_IMODE(stable.st_mode), stable.st_size, stable.st_mtime_ns, expected_child_membership=membership))
                        walk(child_fd, relative)
                    finally: os.close(child_fd)
                else: raise ValueError("unsupported_member")
        walk(fd, "")
        if _fs_identity(os.stat(name, dir_fd=parent_fd, follow_symlinks=False)) != _fs_identity(opened): raise ValueError("identity_changed")
        return opened, immediate, tuple(members)
    finally: os.close(fd)


def _read_relative_file(root_fd: int, directory_name: str, relative: str) -> tuple[bytes, os.stat_result]:
    fd = _open_directory(directory_name, dir_fd=root_fd); opened: list[int] = []
    try:
        current = fd; parts = PurePosixPath(relative).parts
        for part in parts[:-1]:
            current = _open_directory(part, dir_fd=current); opened.append(current)
        return _read_file_at(current, parts[-1])
    finally:
        for child in reversed(opened): os.close(child)
        os.close(fd)


def _classify_staging(out: Path, root_fd: int) -> tuple[tuple[_StagingCandidateCustody, ...], list[str]]:
    names = tuple(sorted(name for name in os.listdir(root_fd) if name.startswith(_STAGING_PREFIX)))
    findings: list[str] = []; prepared: dict[str, tuple[str, bytes, os.stat_result, Mapping[str, Any]]] = {}
    for name in names:
        if not name.startswith(_STAGING_IDENTITY_PREFIX): continue
        try:
            raw, info = _read_file_at(root_fd, name); record = _dict(json.loads(raw)); staging_name = str(record.get("staging_name", ""))
            valid, _ = _valid_staging_record(record, out=out, staging_name=staging_name)
            if not raw.endswith(b"\n") or raw != _canon(record).encode() + b"\n" or not valid or staging_name in prepared: raise ValueError("invalid_identity")
            prepared[staging_name] = name, raw, info, record
        except Exception as exc: findings.append(f"unsafe_staging_residue:{name}:{type(exc).__name__}")
    plans: list[_StagingCandidateCustody] = []
    for association, prepared_value in prepared.items():
        name, raw, info, prepared_record = prepared_value
        plans.append(_StagingCandidateCustody("prepared_identity", name, info.st_dev, info.st_ino, "regular", stat.S_IMODE(info.st_mode), info.st_size, info.st_mtime_ns, raw, _raw_sha(raw), association, tuple(sorted(prepared_record.items()))))
    for name in names:
        if name.startswith(_STAGING_IDENTITY_PREFIX): continue
        try:
            info, immediate, members = _snapshot_directory_at(root_fd, name)
            if name in prepared:
                if immediate: raise ValueError("associated_not_empty")
                kind = "prepared_directory"; record_items: tuple[tuple[str, Any], ...] = ()
            elif not immediate: kind = "reserved"; record_items = ()
            else:
                raw, _ = _read_relative_file(root_fd, name, "staging_identity.json"); record = _dict(json.loads(raw))
                valid, closure_id = _valid_staging_record(record, out=out, staging_name=name)
                if not raw.endswith(b"\n") or raw != _canon(record).encode() + b"\n" or not valid: raise ValueError("invalid_identity")
                if set(immediate) - {"staging_identity.json", closure_id}: raise ValueError("invalid_membership")
                kind = "canonical"; record_items = tuple(sorted(record.items()))
            plans.append(_StagingCandidateCustody(kind, name, info.st_dev, info.st_ino, "directory", stat.S_IMODE(info.st_mode), info.st_size, info.st_mtime_ns, associated_staging_basename=name if kind == "prepared_directory" else "", staging_identity_record=record_items, expected_immediate_membership=immediate, nested_members=members))
        except Exception as exc: findings.append(f"unsafe_staging_residue:{name}:{type(exc).__name__}")
    priority = {"prepared_identity": 0, "prepared_directory": 1, "reserved": 2, "canonical": 3}
    return tuple(sorted(plans, key=lambda plan: (priority[plan.kind], plan.basename))), findings


def _plan_difference(initial: tuple[_StagingCandidateCustody, ...], terminal: tuple[_StagingCandidateCustody, ...]) -> str:
    if {(x.kind, x.basename) for x in initial} != {(x.kind, x.basename) for x in terminal}: return "staging_reconciliation_candidate_set_changed"
    for before, after in zip(initial, terminal):
        if (before.device, before.inode, before.object_type, before.mode) != (after.device, after.inode, after.object_type, after.mode): return "staging_reconciliation_candidate_identity_changed"
        if before.exact_bytes != after.exact_bytes or before.digest != after.digest: return "staging_reconciliation_candidate_bytes_changed"
        if before.expected_immediate_membership != after.expected_immediate_membership or before.nested_members != after.nested_members: return "staging_reconciliation_candidate_membership_changed"
        if before != after: return "staging_reconciliation_candidate_identity_changed"
    return ""


def _verify_candidate(root_fd: int, plan: _StagingCandidateCustody) -> int | None:
    try:
        if plan.object_type == "regular":
            raw, info = _read_file_at(root_fd, plan.basename)
            if (_fs_identity(info), stat.S_IMODE(info.st_mode), info.st_size, info.st_mtime_ns, raw, _raw_sha(raw)) != ((plan.device, plan.inode, plan.object_type), plan.mode, plan.size, plan.modification_time_ns, plan.exact_bytes, plan.digest): raise _StagingCustodyMismatch("staging_reconciliation_candidate_bytes_changed")
            return None
        info, membership, members = _snapshot_directory_at(root_fd, plan.basename)
        if _fs_identity(info) != (plan.device, plan.inode, plan.object_type): raise _StagingCustodyMismatch("staging_reconciliation_candidate_identity_changed")
        if (stat.S_IMODE(info.st_mode), info.st_size, info.st_mtime_ns) != (plan.mode, plan.size, plan.modification_time_ns): raise _StagingCustodyMismatch("staging_reconciliation_candidate_metadata_changed")
        if membership != plan.expected_immediate_membership or members != plan.nested_members: raise _StagingCustodyMismatch("staging_reconciliation_candidate_membership_changed")
        return _open_directory(plan.basename, dir_fd=root_fd)
    except _StagingCustodyMismatch: raise
    except Exception as exc: raise _StagingCustodyMismatch("staging_reconciliation_candidate_identity_changed") from exc


def _remove_canonical(root_fd: int, plan: _StagingCandidateCustody, staging_fd: int) -> None:
    expected = {member.relative_path: member for member in plan.nested_members}
    def remove(parent_fd: int, prefix: str) -> None:
        direct = [member for path, member in expected.items() if PurePosixPath(path).parent.as_posix() == (prefix or ".")]
        if tuple(sorted(os.listdir(parent_fd))) != tuple(sorted(member.basename for member in direct)): raise _StagingCustodyMismatch("staging_reconciliation_candidate_membership_changed")
        for member in sorted(direct, key=lambda item: item.basename, reverse=True):
            _publication_hook("staging_reconciliation_before_remove_member", Path(plan.basename) / member.relative_path)
            try: entry = os.stat(member.basename, dir_fd=parent_fd, follow_symlinks=False)
            except OSError as exc: raise _StagingCustodyMismatch("staging_reconciliation_nested_member_identity_changed") from exc
            if _fs_identity(entry) != (member.device, member.inode, member.object_type): raise _StagingCustodyMismatch("staging_reconciliation_nested_member_identity_changed")
            if (stat.S_IMODE(entry.st_mode), entry.st_size, entry.st_mtime_ns) != (member.mode, member.size, member.modification_time_ns): raise _StagingCustodyMismatch("staging_reconciliation_nested_member_metadata_changed")
            if member.object_type == "regular":
                raw, stable = _read_file_at(parent_fd, member.basename)
                if raw != member.exact_bytes or _raw_sha(raw) != member.digest or (stable.st_size, stable.st_mtime_ns, stat.S_IMODE(stable.st_mode)) != (member.size, member.modification_time_ns, member.mode): raise _StagingCustodyMismatch("staging_reconciliation_nested_member_metadata_changed")
                os.unlink(member.basename, dir_fd=parent_fd)
            else:
                child_fd = _open_directory(member.basename, dir_fd=parent_fd)
                try:
                    opened = os.fstat(child_fd)
                    if _fs_identity(opened) != (member.device, member.inode, member.object_type): raise _StagingCustodyMismatch("staging_reconciliation_nested_member_identity_changed")
                    if (stat.S_IMODE(opened.st_mode), opened.st_size, opened.st_mtime_ns) != (member.mode, member.size, member.modification_time_ns) or tuple(sorted(os.listdir(child_fd))) != member.expected_child_membership: raise _StagingCustodyMismatch("staging_reconciliation_nested_member_metadata_changed")
                    remove(child_fd, member.relative_path)
                    rebound = os.stat(member.basename, dir_fd=parent_fd, follow_symlinks=False)
                    if _fs_identity(rebound) != _fs_identity(os.fstat(child_fd)): raise _StagingCustodyMismatch("staging_reconciliation_nested_member_identity_changed")
                    os.rmdir(member.basename, dir_fd=parent_fd)
                finally: os.close(child_fd)
    remove(staging_fd, "")


def _reconcile_staging(out: Path, root_fd: int, root_identity: tuple[int, int, str]) -> tuple[list[str], list[str]]:
    initial, findings = _classify_staging(out, root_fd)
    if findings: return findings, []
    _publication_hook("staging_reconciliation_classified", out)
    if not _root_is_bound(out, root_fd, root_identity): return ["staging_reconciliation_publication_root_identity_changed"], []
    terminal, terminal_findings = _classify_staging(out, root_fd)
    if terminal_findings: return ["staging_reconciliation_candidate_identity_changed"], []
    difference = _plan_difference(initial, terminal)
    if difference: return [difference], []
    _publication_hook("staging_reconciliation_terminal_validated", out)
    if not _root_is_bound(out, root_fd, root_identity): return ["staging_reconciliation_publication_root_identity_changed"], []
    removed: list[str] = []
    try:
        for plan in terminal:
            _publication_hook("staging_reconciliation_before_remove_candidate", out / plan.basename); directory_fd = _verify_candidate(root_fd, plan)
            if plan.kind == "prepared_identity": os.unlink(plan.basename, dir_fd=root_fd)
            elif plan.kind == "canonical":
                assert directory_fd is not None
                try: _remove_canonical(root_fd, plan, directory_fd)
                finally: os.close(directory_fd)
                if _fs_identity(os.stat(plan.basename, dir_fd=root_fd, follow_symlinks=False)) != (plan.device, plan.inode, plan.object_type): raise _StagingCustodyMismatch("staging_reconciliation_candidate_identity_changed")
                os.rmdir(plan.basename, dir_fd=root_fd)
            else:
                assert directory_fd is not None
                try:
                    if os.listdir(directory_fd): raise _StagingCustodyMismatch("staging_reconciliation_candidate_membership_changed")
                    if _fs_identity(os.stat(plan.basename, dir_fd=root_fd, follow_symlinks=False)) != _fs_identity(os.fstat(directory_fd)): raise _StagingCustodyMismatch("staging_reconciliation_candidate_identity_changed")
                    os.rmdir(plan.basename, dir_fd=root_fd)
                finally: os.close(directory_fd)
            removed.append(plan.basename); _publication_hook("staging_reconciled", out / plan.basename)
    except _StagingCustodyMismatch as exc:
        return [exc.finding, "staging_reconciliation_cleanup_posture:" + ("some_verified_candidates_removed" if removed else "zero_candidates_removed")], removed
    if not _root_is_bound(out, root_fd, root_identity): return ["staging_reconciliation_publication_root_identity_changed"], removed
    if any(name.startswith(_STAGING_PREFIX) for name in os.listdir(root_fd)): return ["staging_reconciliation_candidate_set_changed"], removed
    try: os.fsync(root_fd)
    except OSError as exc:
        if exc.errno not in {errno.EINVAL, errno.ENOTSUP, errno.EOPNOTSUPP}: raise
    return [], removed

def _flush_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        if exc.errno in {errno.EINVAL, errno.ENOTSUP, errno.EOPNOTSUPP}:
            return
        raise
    try:
        try:
            os.fsync(fd)
        except OSError as exc:
            if exc.errno not in {errno.EINVAL, errno.ENOTSUP, errno.EOPNOTSUPP}:
                raise
    finally:
        os.close(fd)


def _prepare_staging_identity(out: Path, staging: Path, closure_id: str) -> Path:
    raw = (_canon(_staging_record(closure_id, staging.name, out)) + "\n").encode()
    fd, name = tempfile.mkstemp(prefix=_STAGING_IDENTITY_PREFIX, dir=out)
    temporary = Path(name)
    try:
        offset = 0
        while offset < len(raw):
            written = os.write(fd, raw[offset:])
            if written <= 0:
                raise OSError("short staging identity write")
            offset += written
        os.fsync(fd)
    except BaseException:
        os.close(fd); temporary.unlink(missing_ok=True); raise
    os.close(fd)
    _publication_hook("staging_identity_prepared", temporary)
    os.replace(temporary, staging / "staging_identity.json")
    _flush_directory(staging); _flush_directory(out)
    _publication_hook("staging_identity_published", staging)
    return temporary


def _fsync_directory_fd(fd: int) -> None:
    try: os.fsync(fd)
    except OSError as exc:
        if exc.errno not in {errno.EINVAL, errno.ENOTSUP, errno.EOPNOTSUPP}: raise


def _write_file_at(parent_fd: int, name: str, raw: bytes) -> tuple[int, int, str]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(name, flags, 0o600, dir_fd=parent_fd)
    try:
        offset = 0
        while offset < len(raw):
            written = os.write(fd, raw[offset:])
            if written <= 0: raise OSError("short descriptor-relative write")
            offset += written
        os.fsync(fd); info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode): raise OSError("created entry is not regular")
        return _fs_identity(info)
    finally: os.close(fd)


def _prepare_file_at(parent_fd: int, name: str, raw: bytes, parent_role: str) -> _PreparedFileCustody:
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(name, flags, 0o600, dir_fd=parent_fd)
    try:
        offset = 0
        while offset < len(raw):
            written = os.write(fd, raw[offset:])
            if written <= 0: raise OSError("short descriptor-relative write")
            offset += written
        os.fsync(fd); opened = os.fstat(fd); entry = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(opened.st_mode) or _fs_identity(opened) != _fs_identity(entry): raise OSError("prepared file custody mismatch")
        os.lseek(fd, 0, os.SEEK_SET)
        if os.read(fd, len(raw) + 1) != raw: raise OSError("prepared file bytes mismatch")
        return _PreparedFileCustody(name, fd, opened.st_dev, opened.st_ino, "regular", stat.S_IMODE(opened.st_mode), opened.st_size, opened.st_mtime_ns, raw, _raw_sha(raw), parent_role)
    except BaseException:
        os.close(fd)
        raise


def _verify_prepared_file(parent_fd: int, prepared: _PreparedFileCustody, name: str | None = None) -> bool:
    basename = prepared.basename if name is None else name
    try:
        entry = os.stat(basename, dir_fd=parent_fd, follow_symlinks=False); opened = os.fstat(prepared.descriptor)
        metadata = (_fs_identity(entry), stat.S_IMODE(entry.st_mode), entry.st_size, entry.st_mtime_ns)
        expected = ((prepared.device, prepared.inode, prepared.object_type), prepared.mode, prepared.size, prepared.modification_time_ns)
        if metadata != expected or (_fs_identity(opened), stat.S_IMODE(opened.st_mode), opened.st_size, opened.st_mtime_ns) != expected: return False
        os.lseek(prepared.descriptor, 0, os.SEEK_SET); raw = b""
        while len(raw) <= prepared.size:
            chunk = os.read(prepared.descriptor, min(131072, prepared.size + 1 - len(raw)))
            if not chunk: break
            raw += chunk
        return raw == prepared.exact_bytes and _raw_sha(raw) == prepared.digest
    except OSError:
        return False


def _fd_alias(fd: int) -> Path:
    alias = Path("/proc/self/fd") / str(fd)
    if _fs_identity(alias.stat()) != _fs_identity(os.fstat(fd)): raise OSError("descriptor alias mismatch")
    return alias


def _validate_bound_packet(packet_fd: int, closure_id: str, *, expected_packet_digest: str | None = None) -> ClosureOutcome:
    # Construction already owns the descriptor; never resolve its adapter or expose it.
    return _validate_lifecycle_closure_bound(packet_fd, Path(closure_id), closure_id, expected_packet_digest=expected_packet_digest)


def _entry_exists_at(parent_fd: int, name: str) -> bool:
    try: os.stat(name, dir_fd=parent_fd, follow_symlinks=False); return True
    except FileNotFoundError: return False


def _reserve_directory(parent_fd: int, prefix: str) -> tuple[str, int]:
    for _ in range(128):
        name = prefix + os.urandom(16).hex()
        try: os.mkdir(name, 0o700, dir_fd=parent_fd)
        except FileExistsError: continue
        fd = _open_directory(name, dir_fd=parent_fd); opened = os.fstat(fd); entry = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if _fs_identity(opened) != _fs_identity(entry) or stat.S_IMODE(opened.st_mode) != 0o700:
            os.close(fd); raise OSError("reserved directory custody mismatch")
        return name, fd
    raise FileExistsError("staging namespace exhausted")


def _remove_tree_fd(parent_fd: int, name: str, expected: tuple[int, int, str]) -> None:
    fd = _open_directory(name, dir_fd=parent_fd)
    try:
        if _fs_identity(os.fstat(fd)) != expected: raise _StagingCustodyMismatch("publication_cleanup_identity_changed")
        for child in tuple(os.listdir(fd)):
            info = os.stat(child, dir_fd=fd, follow_symlinks=False)
            custody = (_fs_identity(info), stat.S_IMODE(info.st_mode), info.st_size, info.st_mtime_ns)
            if stat.S_ISDIR(info.st_mode):
                _publication_hook("lifecycle_cleanup_before_remove_directory", Path(name) / child)
                try:
                    rebound = os.stat(child, dir_fd=fd, follow_symlinks=False); child_fd = _open_directory(child, dir_fd=fd)
                except OSError as exc: raise _StagingCustodyMismatch("publication_cleanup_member_identity_changed") from exc
                try: verified = (_fs_identity(rebound), stat.S_IMODE(rebound.st_mode), rebound.st_size, rebound.st_mtime_ns) == custody and _fs_identity(os.fstat(child_fd)) == _fs_identity(info)
                finally: os.close(child_fd)
                if not verified: raise _StagingCustodyMismatch("publication_cleanup_member_identity_changed")
                _remove_tree_fd(fd, child, _fs_identity(info))
            elif stat.S_ISREG(info.st_mode):
                _publication_hook("lifecycle_cleanup_before_remove_member", Path(name) / child)
                try:
                    rebound = os.stat(child, dir_fd=fd, follow_symlinks=False); child_fd = os.open(child, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=fd)
                except OSError as exc: raise _StagingCustodyMismatch("publication_cleanup_member_identity_changed") from exc
                try: terminal = os.fstat(child_fd)
                finally: os.close(child_fd)
                terminal_custody = (_fs_identity(rebound), stat.S_IMODE(rebound.st_mode), rebound.st_size, rebound.st_mtime_ns)
                if terminal_custody != custody or _fs_identity(terminal) != _fs_identity(info):
                    finding = "publication_cleanup_member_identity_changed" if _fs_identity(rebound) != _fs_identity(info) else "publication_cleanup_member_metadata_changed"
                    raise _StagingCustodyMismatch(finding)
                os.unlink(child, dir_fd=fd)
            else: raise _StagingCustodyMismatch("publication_cleanup_unsupported_member")
        rebound = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if _fs_identity(rebound) != expected or os.listdir(fd): raise _StagingCustodyMismatch("publication_cleanup_identity_changed")
        os.rmdir(name, dir_fd=parent_fd)
    finally: os.close(fd)


def _write_pointer_at(root_fd: int, pointer: Mapping[str, Any]) -> tuple[int, int, str]:
    raw = (_canon(pointer) + "\n").encode(); name = ".latest-" + os.urandom(16).hex()
    prepared = _prepare_file_at(root_fd, name, raw, "publication_root")
    try:
        _publication_hook("lifecycle_pointer_prepared", Path(name))
        _publication_hook("lifecycle_pointer_before_commit", Path(name))
        if not _verify_prepared_file(root_fd, prepared): raise _StagingCustodyMismatch("lifecycle_pointer_source_changed_before_commit")
        _publish_latest(name, "latest.json", root_fd)
        if not _verify_prepared_file(root_fd, prepared, "latest.json"): raise _StagingCustodyMismatch("lifecycle_pointer_install_identity_mismatch")
        _fsync_directory_fd(root_fd); return prepared.device, prepared.inode, prepared.object_type
    except _AtomicDestinationConflict as exc: raise _StagingCustodyMismatch("lifecycle_pointer_destination_conflict") from exc
    except _AtomicNoReplaceUnsupported as exc: raise _StagingCustodyMismatch("lifecycle_atomic_noreplace_unsupported") from exc
    finally:
        os.close(prepared.descriptor)


def _root_blocked(finding: str) -> ClosureOutcome:
    return ClosureOutcome("blocked_host_local_diagnostic_lifecycle_closure", (finding,), {})


def _build_lifecycle_closure_bound(*, execution_root: Path, execution_fd: int, execution_identity: tuple[tuple[int, int, str], int, int, int], execution_bundle_digest: str, rollback_root: Path, rollback_fd: int, rollback_identity: tuple[tuple[int, int, str], int, int, int], rollback_bundle_digest: str, closure_time: str, output_root: str | Path, correlation_id: str | None = None) -> ClosureOutcome:
    out, findings = _safe_root(output_root)
    if findings or any(a == b or a in b.parents or b in a.parents for a, b in ((out, execution_root), (out, rollback_root))): return ClosureOutcome("blocked_host_local_diagnostic_lifecycle_closure", tuple(findings + ["roots_overlap"]), {})
    if not _source_root_bound(execution_root, execution_fd, execution_identity): return _root_blocked("lifecycle_execution_source_root_identity_changed")
    if not _source_root_bound(rollback_root, rollback_fd, rollback_identity): return _root_blocked("lifecycle_rollback_source_root_identity_changed")
    ev = _descriptor_adapter(execution_fd, lambda path: validate_persisted_execution_bundle(path, expected_final_bundle_digest=execution_bundle_digest))
    rv = _descriptor_adapter(rollback_fd, lambda path: validate_persisted_rollback_bundle(path, expected_final_bundle_digest=rollback_bundle_digest, expected_execution_bundle_digest=execution_bundle_digest))
    if not _source_root_bound(execution_root, execution_fd, execution_identity): return _root_blocked("lifecycle_execution_source_root_identity_changed")
    if not _source_root_bound(rollback_root, rollback_fd, rollback_identity): return _root_blocked("lifecycle_rollback_source_root_identity_changed")
    if ev.status != "host_local_diagnostic_execution_completed" or rv.status != "host_local_diagnostic_rollback_completed": return ClosureOutcome("blocked_host_local_diagnostic_lifecycle_closure", tuple(sorted(set(ev.findings + rv.findings))), {})
    base_report, cross = _cross_validate(ev.records, rv.records, execution_bundle_digest); historical_correlation = str(base_report.get("correlation_id", ""))
    if correlation_id is not None and correlation_id != historical_correlation: cross.append("correlation_override_mismatch")
    if cross: return ClosureOutcome("blocked_host_local_diagnostic_lifecycle_closure", tuple(sorted(set(cross))), {})
    try:
        if not _source_root_bound(execution_root, execution_fd, execution_identity) or not _source_root_bound(rollback_root, rollback_fd, rollback_identity): return _root_blocked("lifecycle_source_root_identity_changed_before_copy")
        execution_plan = _build_source_plan(execution_fd, "execution"); rollback_plan = _build_source_plan(rollback_fd, "rollback")
    except _StagingCustodyMismatch as exc: return _root_blocked(exc.finding)
    closure_id = derive_closure_id(execution_bundle_digest, rollback_bundle_digest, closure_time); identity = _identity(base_report, closure_id, closure_time, execution_bundle_digest, rollback_bundle_digest)
    out.mkdir(parents=True, exist_ok=True)
    with (out / ".closure.lock").open("a+b") as lock:
        _publication_hook("lock_waiting", out); fcntl.flock(lock.fileno(), fcntl.LOCK_EX); _publication_hook("locked_enter", out)
        try: root_fd = _open_directory(out)
        except OSError: return _root_blocked("staging_reconciliation_publication_root_identity_changed")
        try:
            root_identity = _fs_identity(os.fstat(root_fd))
            if not _root_is_bound(out, root_fd, root_identity): return _root_blocked("staging_reconciliation_publication_root_identity_changed")
            staging_findings, _ = _reconcile_staging(out, root_fd, root_identity)
            if staging_findings: return ClosureOutcome("blocked_host_local_diagnostic_lifecycle_closure", tuple(staging_findings), {})
            _publication_hook("lifecycle_publication_after_reconciliation", out)
            if not _root_is_bound(out, root_fd, root_identity): return _root_blocked("lifecycle_publication_root_identity_changed_after_reconciliation")
            if _entry_exists_at(root_fd, closure_id):
                packet_fd = _open_directory(closure_id, dir_fd=root_fd)
                try: loaded = _validate_bound_packet(packet_fd, closure_id)
                finally: os.close(packet_fd)
                loaded_final = _dict(loaded.records.get("final_manifest")); loaded_summary = _dict(loaded.records.get("summary"))
                if loaded.status != "host_local_diagnostic_lifecycle_closure_valid" or any(loaded_summary.get(k) != v for k, v in identity.items()): return _root_blocked("closure_identity_conflict")
                pointer = _pointer(identity, str(loaded_final.get("packet_digest", ""))); recovered = not _entry_exists_at(root_fd, "latest.json")
                if not recovered:
                    raw, _ = _read_file_at(root_fd, "latest.json")
                    if _dict(json.loads(raw)) != pointer: return _root_blocked("latest_pointer_conflict")
                else:
                    if not _root_is_bound(out, root_fd, root_identity): return _root_blocked("lifecycle_publication_root_identity_changed_before_pointer_publish")
                    _write_pointer_at(root_fd, pointer)
                if not _root_is_bound(out, root_fd, root_identity): return _root_blocked("lifecycle_publication_root_identity_changed_after_pointer_publish")
                _publication_hook("locked_exit", out)
                return ClosureOutcome(loaded.status, (), loaded.records, str(out / closure_id), True, "recovered" if recovered else "replayed")
            if _entry_exists_at(root_fd, "latest.json"): return _root_blocked("latest_pointer_conflict")
            _publication_hook("lifecycle_publication_before_staging_reservation", out)
            if not _root_is_bound(out, root_fd, root_identity): return _root_blocked("lifecycle_publication_root_identity_changed_before_staging_reservation")
            staging_name, staging_fd = _reserve_directory(root_fd, _STAGING_PREFIX); staging_identity = _fs_identity(os.fstat(staging_fd)); published = False; preserve_staging = False
            try:
                staging_path = out / staging_name; _publication_hook("staging_directory_reserved", staging_path); _publication_hook("lifecycle_publication_after_staging_reservation", staging_path)
                if not _root_is_bound(out, root_fd, root_identity): return _root_blocked("lifecycle_publication_root_identity_changed_after_staging_reservation")
                record_raw = (_canon(_staging_record(closure_id, staging_name, out)) + "\n").encode(); identity_name = _STAGING_IDENTITY_PREFIX + os.urandom(16).hex()
                prepared_identity = _prepare_file_at(root_fd, identity_name, record_raw, "publication_root")
                try:
                    _publication_hook("staging_identity_prepared", out / identity_name)
                    if not _root_is_bound(out, root_fd, root_identity) or _fs_identity(os.fstat(staging_fd)) != staging_identity: return _root_blocked("lifecycle_publication_root_identity_changed_before_staging_identity_publish")
                    if not _verify_prepared_file(root_fd, prepared_identity):
                        preserve_staging = True; return _root_blocked("lifecycle_staging_identity_source_changed")
                    try: _atomic_rename_noreplace(root_fd, identity_name, staging_fd, "staging_identity.json")
                    except _AtomicDestinationConflict:
                        preserve_staging = True; return _root_blocked("lifecycle_staging_identity_destination_conflict")
                    except _AtomicNoReplaceUnsupported:
                        preserve_staging = True; return _root_blocked("lifecycle_atomic_noreplace_unsupported")
                    if not _verify_prepared_file(staging_fd, prepared_identity, "staging_identity.json"):
                        preserve_staging = True; return _root_blocked("lifecycle_staging_identity_install_identity_mismatch")
                    _fsync_directory_fd(staging_fd); _fsync_directory_fd(root_fd)
                finally: os.close(prepared_identity.descriptor)
                _publication_hook("staging_identity_published", staging_path)
                os.mkdir(closure_id, 0o700, dir_fd=staging_fd); packet_fd = _open_directory(closure_id, dir_fd=staging_fd); packet_identity = _fs_identity(os.fstat(packet_fd))
                try:
                    _publication_hook("staging_created", staging_path)
                    if not _source_root_bound(execution_root, execution_fd, execution_identity) or not _source_root_bound(rollback_root, rollback_fd, rollback_identity): return _root_blocked("lifecycle_source_root_identity_changed_before_copy")
                    bundles_fd = _mkdir_at(packet_fd, "bundles", staging_path / closure_id / "bundles")
                    try:
                        _copy_planned_bundle(execution_fd, bundles_fd, "execution", execution_plan, "execution", staging_path / closure_id / "bundles")
                        if not _source_root_bound(execution_root, execution_fd, execution_identity): return _root_blocked("lifecycle_source_root_identity_changed_after_copy")
                        _copy_planned_bundle(rollback_fd, bundles_fd, "rollback", rollback_plan, "rollback", staging_path / closure_id / "bundles")
                        if not _source_root_bound(rollback_root, rollback_fd, rollback_identity): return _root_blocked("lifecycle_source_root_identity_changed_after_copy")
                        _fsync_directory_fd(bundles_fd)
                    finally: os.close(bundles_fd)
                    report = {**base_report, **identity}; report["digest"] = digest_record(report); _write_file_at(packet_fd, "closure_report.json", (_canon(report)+"\n").encode())
                    summary = {"schema_version": SCHEMA_VERSION, "artifact_kind": "host_local_diagnostic_lifecycle_closure_summary", "status": "host_local_diagnostic_lifecycle_closed", **identity}; summary["digest"] = digest_record(summary); _write_file_at(packet_fd, "summary.json", (_canon(summary)+"\n").encode())
                    construction_snapshot = _packet_snapshot(packet_fd); content_names = [member.relative_path for member in construction_snapshot if member.object_type == "regular"]; content = _manifest_from_snapshot(construction_snapshot, content_names, "host_local_diagnostic_lifecycle_closure_content_manifest", "content_manifest_digest"); _write_file_at(packet_fd, "content_manifest.json", (_canon(content)+"\n").encode())
                    receipt = {"schema_version": SCHEMA_VERSION, "artifact_kind": "host_local_diagnostic_lifecycle_closure_receipt", **identity, "closure_report_digest": _sha(report), "summary_digest": _sha(summary), "content_manifest_digest": content["content_manifest_digest"]}; receipt["digest"] = digest_record(receipt); _write_file_at(packet_fd, "receipt.json", (_canon(receipt)+"\n").encode())
                    pre_final_snapshot = _packet_snapshot(packet_fd); final_names = [member.relative_path for member in pre_final_snapshot if member.object_type == "regular"]; final = _manifest_from_snapshot(pre_final_snapshot, final_names, "host_local_diagnostic_lifecycle_closure_final_manifest", "packet_digest", identity); _write_file_at(packet_fd, "final_manifest.json", (_canon(final)+"\n").encode()); _fsync_directory_fd(packet_fd)
                    if not _root_is_bound(out, root_fd, root_identity): return _root_blocked("lifecycle_publication_root_identity_changed_before_staged_validation")
                    if not _source_root_bound(execution_root, execution_fd, execution_identity) or not _source_root_bound(rollback_root, rollback_fd, rollback_identity): return _root_blocked("lifecycle_source_root_identity_changed_before_copy")
                    staged_result = _validate_bound_packet(packet_fd, closure_id, expected_packet_digest=str(final["packet_digest"]))
                    if staged_result.status != "host_local_diagnostic_lifecycle_closure_valid": return ClosureOutcome("blocked_host_local_diagnostic_lifecycle_closure", staged_result.findings, {})
                    staged_snapshot = _packet_snapshot(packet_fd); _publication_hook("lifecycle_packet_after_staged_validation", staging_path / closure_id)
                    _publication_hook("lifecycle_publication_before_packet_publish", staging_path / closure_id)
                    if not _root_is_bound(out, root_fd, root_identity): return _root_blocked("lifecycle_publication_root_identity_changed_before_packet_publish")
                    source_info = os.stat(closure_id, dir_fd=staging_fd, follow_symlinks=False)
                    if _fs_identity(source_info) != packet_identity or stat.S_IMODE(source_info.st_mode) != stat.S_IMODE(os.fstat(packet_fd).st_mode):
                        preserve_staging = True; return _root_blocked("lifecycle_packet_source_changed_before_commit")
                    try: terminal_snapshot = _packet_snapshot(packet_fd)
                    except _StagingCustodyMismatch as exc:
                        preserve_staging = True; return _root_blocked(exc.finding)
                    difference = _packet_snapshot_difference(staged_snapshot, terminal_snapshot)
                    if difference:
                        preserve_staging = True; return _root_blocked(difference)
                    terminal_result = _validate_bound_packet(packet_fd, closure_id, expected_packet_digest=str(final["packet_digest"]))
                    if terminal_result.status != "host_local_diagnostic_lifecycle_closure_valid":
                        preserve_staging = True; return _root_blocked("lifecycle_packet_validation_changed_before_commit")
                    if not _source_root_bound(execution_root, execution_fd, execution_identity) or not _source_root_bound(rollback_root, rollback_fd, rollback_identity):
                        preserve_staging = True; return _root_blocked("lifecycle_source_root_identity_changed_before_copy")
                    try: _publish_packet(closure_id, closure_id, staging_fd=staging_fd, root_fd=root_fd)
                    except _AtomicDestinationConflict:
                        preserve_staging = True; return _root_blocked("lifecycle_packet_destination_conflict")
                    except _AtomicNoReplaceUnsupported:
                        preserve_staging = True; return _root_blocked("lifecycle_atomic_noreplace_unsupported")
                    published = True; _fsync_directory_fd(root_fd)
                    if _fs_identity(os.stat(closure_id, dir_fd=root_fd, follow_symlinks=False)) != packet_identity or _entry_exists_at(staging_fd, closure_id): return _root_blocked("lifecycle_packet_install_identity_mismatch")
                    _publication_hook("packet_published", out / closure_id); _publication_hook("lifecycle_publication_after_packet_publish", out / closure_id)
                    if not _root_is_bound(out, root_fd, root_identity): return _root_blocked("lifecycle_publication_root_identity_changed_after_packet_publish")
                    installed_snapshot = _packet_snapshot(packet_fd)
                    difference = _packet_snapshot_difference(staged_snapshot, installed_snapshot)
                    if difference: return _root_blocked(difference)
                    published_result = _validate_bound_packet(packet_fd, closure_id, expected_packet_digest=str(final["packet_digest"]))
                    if published_result.status != "host_local_diagnostic_lifecycle_closure_valid": return ClosureOutcome("blocked_host_local_diagnostic_lifecycle_closure", published_result.findings, {})
                    _publication_hook("lifecycle_publication_before_pointer_publish", out / "latest.json")
                    if not _root_is_bound(out, root_fd, root_identity): return _root_blocked("lifecycle_publication_root_identity_changed_before_pointer_publish")
                    try: _write_pointer_at(root_fd, _pointer(identity, str(final["packet_digest"])))
                    except _StagingCustodyMismatch as exc: return _root_blocked(exc.finding)
                    _publication_hook("lifecycle_publication_after_pointer_publish", out / "latest.json")
                    if not _root_is_bound(out, root_fd, root_identity): return _root_blocked("lifecycle_publication_root_identity_changed_after_pointer_publish")
                    if not _source_root_bound(execution_root, execution_fd, execution_identity) or not _source_root_bound(rollback_root, rollback_fd, rollback_identity): return _root_blocked("lifecycle_source_root_identity_changed_after_copy")
                except _StagingCustodyMismatch as exc:
                    preserve_staging = True
                    return _root_blocked(exc.finding)
                finally: os.close(packet_fd)
                if _fs_identity(os.stat(staging_name, dir_fd=root_fd, follow_symlinks=False)) != staging_identity: raise _StagingCustodyMismatch("publication_cleanup_identity_changed")
                try: _remove_tree_fd(root_fd, staging_name, staging_identity)
                except _StagingCustodyMismatch as exc:
                    return ClosureOutcome("blocked_host_local_diagnostic_lifecycle_closure", (exc.finding, "publication_committed_cleanup_blocked"), published_result.records, str(out / closure_id), False, "cleanup_blocked")
                _fsync_directory_fd(root_fd)
                if not _root_is_bound(out, root_fd, root_identity): return _root_blocked("lifecycle_publication_root_identity_changed_before_cleanup_complete")
                _publication_hook("locked_exit", out)
                return ClosureOutcome(published_result.status, published_result.findings, published_result.records, str(out / closure_id), False, "published")
            finally:
                os.close(staging_fd)
                if not published and not preserve_staging and _entry_exists_at(root_fd, staging_name):
                    # Preserve staged evidence on root-binding failure; otherwise bounded cleanup is safe.
                    if _root_is_bound(out, root_fd, root_identity): _remove_tree_fd(root_fd, staging_name, staging_identity)
        finally: os.close(root_fd)


def build_lifecycle_closure(*, execution_bundle_root: str | Path, execution_bundle_digest: str, rollback_bundle_root: str | Path, rollback_bundle_digest: str, closure_time: str, output_root: str | Path, correlation_id: str | None = None) -> ClosureOutcome:
    """Build a closure while source descriptors remain the sole copy read authority."""
    execution_root = Path(execution_bundle_root).resolve(); rollback_root = Path(rollback_bundle_root).resolve()
    try: execution_fd = _open_directory(execution_root)
    except OSError: return _root_blocked("lifecycle_execution_source_root_identity_changed")
    try:
        try: rollback_fd = _open_directory(rollback_root)
        except OSError: return _root_blocked("lifecycle_rollback_source_root_identity_changed")
        try:
            execution_identity = _metadata(os.fstat(execution_fd)); rollback_identity = _metadata(os.fstat(rollback_fd))
            if execution_identity[0][2] != "directory": return _root_blocked("lifecycle_execution_source_root_identity_changed")
            if rollback_identity[0][2] != "directory": return _root_blocked("lifecycle_rollback_source_root_identity_changed")
            return _build_lifecycle_closure_bound(execution_root=execution_root, execution_fd=execution_fd, execution_identity=execution_identity, execution_bundle_digest=execution_bundle_digest, rollback_root=rollback_root, rollback_fd=rollback_fd, rollback_identity=rollback_identity, rollback_bundle_digest=rollback_bundle_digest, closure_time=closure_time, output_root=output_root, correlation_id=correlation_id)
        finally: os.close(rollback_fd)
    finally: os.close(execution_fd)

def _latest_invalid(*findings: str) -> ClosureOutcome:
    return ClosureOutcome("host_local_diagnostic_lifecycle_closure_latest_invalid", tuple(sorted(set(findings))), {}, publication_posture="rejected")


def _safe_closure_basename(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 30 and value.startswith("hldlc-") and set(value[6:]) <= _HEX and _safe_basename(value)


def _read_pointer_custody(root_fd: int) -> _PreparedFileCustody:
    name = "latest.json"
    try: entry = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
    except FileNotFoundError as exc: raise _StagingCustodyMismatch("lifecycle_latest_pointer_missing") from exc
    if not stat.S_ISREG(entry.st_mode): raise _StagingCustodyMismatch("lifecycle_latest_pointer_not_regular")
    if entry.st_size > 1024 * 1024: raise _StagingCustodyMismatch("lifecycle_latest_pointer_too_large")
    try: fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=root_fd)
    except OSError as exc: raise _StagingCustodyMismatch("lifecycle_latest_pointer_identity_changed") from exc
    try:
        opened = os.fstat(fd); expected = _metadata(entry)
        if _metadata(opened) != expected: raise _StagingCustodyMismatch("lifecycle_latest_pointer_identity_changed")
        raw = _read_fd(fd, 1024 * 1024); terminal = os.fstat(fd)
        rebound = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        if _fs_identity(terminal) != expected[0] or _fs_identity(rebound) != expected[0]: raise _StagingCustodyMismatch("lifecycle_latest_pointer_identity_changed")
        if _metadata(terminal) != expected or _metadata(rebound) != expected: raise _StagingCustodyMismatch("lifecycle_latest_pointer_metadata_changed")
        return _PreparedFileCustody(name, fd, opened.st_dev, opened.st_ino, "regular", stat.S_IMODE(opened.st_mode), opened.st_size, opened.st_mtime_ns, raw, _raw_sha(raw), "publication_root")
    except BaseException:
        os.close(fd); raise


def _verify_read_custody(root_fd: int, custody: _PreparedFileCustody) -> str:
    try:
        entry = os.stat(custody.basename, dir_fd=root_fd, follow_symlinks=False); opened = os.fstat(custody.descriptor)
    except OSError: return "lifecycle_latest_pointer_identity_changed"
    expected = ((custody.device, custody.inode, custody.object_type), custody.mode, custody.size, custody.modification_time_ns)
    if _fs_identity(entry) != expected[0] or _fs_identity(opened) != expected[0]: return "lifecycle_latest_pointer_identity_changed"
    if _metadata(entry) != expected or _metadata(opened) != expected: return "lifecycle_latest_pointer_metadata_changed"
    try: raw = _read_fd(custody.descriptor, custody.size)
    except Exception: return "lifecycle_latest_pointer_bytes_changed"
    return "" if raw == custody.exact_bytes and _raw_sha(raw) == custody.digest else "lifecycle_latest_pointer_bytes_changed"


def load_latest_summary(output_root: str | Path) -> ClosureOutcome:
    logical = Path(output_root).absolute()
    try: root_fd = _open_directory(logical)
    except OSError: return _latest_invalid("lifecycle_latest_publication_root_identity_changed")
    pointer_custody: _PreparedFileCustody | None = None; lock_fd = -1; packet_fd = -1
    try:
        root_expected = _metadata(os.fstat(root_fd))
        _publication_hook("lifecycle_latest_after_publication_root_open", logical)
        if not _source_root_bound(logical, root_fd, root_expected): return _latest_invalid("lifecycle_latest_publication_root_identity_changed")
        try:
            lock_entry = os.stat(".closure.lock", dir_fd=root_fd, follow_symlinks=False)
            if not stat.S_ISREG(lock_entry.st_mode): raise OSError("unsafe lock")
            lock_fd = os.open(".closure.lock", os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=root_fd)
            if _metadata(os.fstat(lock_fd)) != _metadata(lock_entry): raise OSError("changed lock")
            fcntl.flock(lock_fd, fcntl.LOCK_SH)
        except OSError: return _latest_invalid("lifecycle_latest_lock_missing_or_unsafe")
        pointer_custody = _read_pointer_custody(root_fd)
        _publication_hook("lifecycle_latest_after_pointer_read", logical / "latest.json")
        try: pointer = _dict(json.loads(pointer_custody.exact_bytes))
        except Exception: return _latest_invalid("lifecycle_latest_pointer_invalid")
        exact = {"schema_version", "artifact_kind", "digest", "packet_digest", *(_identity({}, "", "", "", "").keys())}
        if set(pointer) != exact or pointer.get("schema_version") != SCHEMA_VERSION or pointer.get("artifact_kind") != "host_local_diagnostic_lifecycle_closure_pointer" or pointer.get("digest") != digest_record(pointer):
            return _latest_invalid("lifecycle_latest_pointer_invalid")
        closure_id = pointer.get("closure_id")
        if not _safe_closure_basename(closure_id): return _latest_invalid("lifecycle_latest_closure_id_unsafe")
        assert isinstance(closure_id, str)
        try: packet_entry = os.stat(closure_id, dir_fd=root_fd, follow_symlinks=False)
        except FileNotFoundError: return _latest_invalid("lifecycle_latest_packet_missing")
        if not stat.S_ISDIR(packet_entry.st_mode): return _latest_invalid("lifecycle_latest_packet_not_directory")
        _publication_hook("lifecycle_latest_before_packet_open", logical / closure_id)
        try: packet_fd = _open_directory(closure_id, dir_fd=root_fd)
        except OSError: return _latest_invalid("lifecycle_latest_packet_identity_changed")
        packet_expected = _metadata(os.fstat(packet_fd))
        if packet_expected != _metadata(packet_entry): return _latest_invalid("lifecycle_latest_packet_identity_changed")
        _publication_hook("lifecycle_latest_after_packet_open", logical / closure_id)
        initial = _packet_snapshot(packet_fd)
        result = _validate_lifecycle_closure_bound(packet_fd, logical / closure_id, closure_id, expected_packet_digest=str(pointer.get("packet_digest", "")), initial_snapshot=initial)
        _publication_hook("lifecycle_latest_after_packet_validation", logical / closure_id)
        if result.status != "host_local_diagnostic_lifecycle_closure_valid":
            mapped = []
            for finding in result.findings:
                mapped.append(finding.replace("lifecycle_validation_packet_", "lifecycle_latest_packet_"))
            return _latest_invalid(*mapped)
        summary = _dict(result.records.get("summary")); final = _dict(result.records.get("final_manifest"))
        if any(pointer.get(k) != summary.get(k) for k in _identity({}, "", "", "", "")):
            return _latest_invalid("lifecycle_latest_pointer_summary_identity_mismatch")
        if pointer.get("packet_digest") != final.get("packet_digest"):
            return _latest_invalid("lifecycle_latest_packet_digest_mismatch")
        _publication_hook("lifecycle_latest_before_terminal_rebind", logical)
        findings: list[str] = []
        try:
            named_root = _metadata(os.stat(logical, follow_symlinks=False)); opened_root = _metadata(os.fstat(root_fd))
            if named_root[0] != root_expected[0] or opened_root[0] != root_expected[0]: findings.append("lifecycle_latest_publication_root_identity_changed")
            elif named_root != root_expected or opened_root != root_expected: findings.append("lifecycle_latest_publication_root_metadata_changed")
        except OSError: findings.append("lifecycle_latest_publication_root_identity_changed")
        pointer_finding = _verify_read_custody(root_fd, pointer_custody)
        if pointer_finding: findings.append(pointer_finding)
        try:
            rebound_packet = _metadata(os.stat(closure_id, dir_fd=root_fd, follow_symlinks=False)); opened_packet = _metadata(os.fstat(packet_fd))
            if rebound_packet[0] != packet_expected[0] or opened_packet[0] != packet_expected[0]: findings.append("lifecycle_latest_packet_identity_changed")
            elif rebound_packet != packet_expected or opened_packet != packet_expected: findings.append("lifecycle_latest_packet_metadata_changed")
        except OSError: findings.append("lifecycle_latest_packet_identity_changed")
        terminal = _packet_snapshot(packet_fd); difference = _snapshot_finding("lifecycle_latest_packet_", initial, terminal)
        if difference: findings.append(difference)
        if findings: return _latest_invalid(*findings)
        return ClosureOutcome(result.status, (), result.records, str(logical / closure_id), True, "latest_replay")
    except _StagingCustodyMismatch as exc:
        return _latest_invalid(exc.finding)
    except Exception:
        return _latest_invalid("lifecycle_latest_pointer_invalid")
    finally:
        if packet_fd >= 0: os.close(packet_fd)
        if pointer_custody is not None: os.close(pointer_custody.descriptor)
        if lock_fd >= 0:
            try: fcntl.flock(lock_fd, fcntl.LOCK_UN)
            finally: os.close(lock_fd)
        os.close(root_fd)
