"""Self-contained, read-only custody for one diagnostic execution and rollback."""
from __future__ import annotations

import fcntl
import errno
import hashlib
import json
import os
import shutil
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


def validate_lifecycle_closure(packet_root: str | Path, *, expected_packet_digest: str | None = None) -> ClosureOutcome:
    root, findings = _safe_root(packet_root); records: dict[str, Any] = {}
    try:
        actual, path_findings = _packet_files(root); findings.extend(path_findings)
        execution_digest = _bundle_digest(root / EXECUTION_PATH); rollback_digest = _bundle_digest(root / ROLLBACK_PATH)
        ev = validate_persisted_execution_bundle(root / EXECUTION_PATH, expected_final_bundle_digest=execution_digest)
        rv = validate_persisted_rollback_bundle(root / ROLLBACK_PATH, expected_final_bundle_digest=rollback_digest, expected_execution_bundle_digest=execution_digest)
        findings.extend("nested_execution:" + x for x in ev.findings); findings.extend("nested_rollback:" + x for x in rv.findings)
        base_report, cross = _cross_validate(ev.records, rv.records, execution_digest); findings.extend(cross)
        report = _json(root / "closure_report.json"); summary = _json(root / "summary.json"); receipt = _json(root / "receipt.json")
        content = _json(root / "content_manifest.json"); final = _json(root / "final_manifest.json")
        times = {record.get("closure_time") for record in (report, summary, receipt, final)}
        if len(times) != 1 or not isinstance(next(iter(times), None), str) or not next(iter(times), ""):
            findings.append("closure_time_custody_mismatch"); closure_time = ""
        else: closure_time = str(next(iter(times)))
        derived_id = derive_closure_id(execution_digest, rollback_digest, closure_time)
        ids = {record.get("closure_id") for record in (report, summary, receipt, final)}
        if ids != {derived_id} or root.name != derived_id: findings.append("closure_identity_custody_mismatch")
        identity = _identity(base_report, derived_id, closure_time, execution_digest, rollback_digest)
        expected_report = {**base_report, **identity}; expected_report["digest"] = digest_record(expected_report)
        if report != expected_report: findings.append("closure_report_invalid")
        expected_summary = {"schema_version": SCHEMA_VERSION, "artifact_kind": "host_local_diagnostic_lifecycle_closure_summary", "status": "host_local_diagnostic_lifecycle_closed", **identity}; expected_summary["digest"] = digest_record(expected_summary)
        if summary != expected_summary: findings.append("summary_invalid")
        nested_names = {name for name in actual if name.startswith(EXECUTION_PATH + "/") or name.startswith(ROLLBACK_PATH + "/")}
        content_names = nested_names | {"closure_report.json", "summary.json"}
        findings.extend(_validate_manifest(root, content, kind="host_local_diagnostic_lifecycle_closure_content_manifest", digest_name="content_manifest_digest", expected_names=content_names))
        expected_receipt = {"schema_version": SCHEMA_VERSION, "artifact_kind": "host_local_diagnostic_lifecycle_closure_receipt", **identity, "closure_report_digest": _sha(report), "summary_digest": _sha(summary), "content_manifest_digest": content.get("content_manifest_digest")}; expected_receipt["digest"] = digest_record(expected_receipt)
        if receipt != expected_receipt: findings.append("receipt_invalid")
        final_names = content_names | {"content_manifest.json", "receipt.json"}
        findings.extend(_validate_manifest(root, final, kind="host_local_diagnostic_lifecycle_closure_final_manifest", digest_name="packet_digest", expected_names=final_names, metadata=identity))
        if actual != final_names | {"final_manifest.json"}: findings.append("exact_packet_membership_invalid")
        packet_digest = final.get("packet_digest")
        if expected_packet_digest is not None and packet_digest != expected_packet_digest: findings.append("expected_packet_digest_mismatch")
        records = {"closure_report": report, "summary": summary, "receipt": receipt, "content_manifest": content, "final_manifest": final}
    except Exception as exc:
        findings.append("packet_decode_failed:" + type(exc).__name__)
    status = "host_local_diagnostic_lifecycle_closure_valid" if not findings else "host_local_diagnostic_lifecycle_closure_invalid"
    return ClosureOutcome(status, tuple(sorted(set(findings))), records, str(root), True, "validated" if not findings else "rejected")


# Small named hooks deliberately provide deterministic test interception points.
def _publication_hook(event: str, path: Path) -> None:
    """Internal no-op boundary hook used only by explicitly injected tests."""


def _copy_bundle(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination)


def _publish_packet(staged: Path, destination: Path) -> None:
    os.replace(staged, destination)


def _publish_latest(staged: Path, destination: Path) -> None:
    os.replace(staged, destination)


def _pointer(identity: Mapping[str, Any], packet_digest: str) -> dict[str, Any]:
    value = {"schema_version": SCHEMA_VERSION, "artifact_kind": "host_local_diagnostic_lifecycle_closure_pointer", **dict(identity), "packet_digest": packet_digest}
    value["digest"] = digest_record(value)
    return value


def _write_pointer(out: Path, pointer: Mapping[str, Any]) -> None:
    fd, name = tempfile.mkstemp(dir=out, prefix=".latest-")
    os.close(fd); staged = Path(name)
    try:
        staged.write_text(_canon(pointer) + "\n")
        _publish_latest(staged, out / "latest.json")
    finally:
        staged.unlink(missing_ok=True)


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
            if _fs_identity(entry) != (member.device, member.inode, member.object_type) or stat.S_IMODE(entry.st_mode) != member.mode: raise _StagingCustodyMismatch("staging_reconciliation_nested_member_identity_changed")
            if member.object_type == "regular":
                raw, stable = _read_file_at(parent_fd, member.basename)
                if raw != member.exact_bytes or _raw_sha(raw) != member.digest or stable.st_size != member.size: raise _StagingCustodyMismatch("staging_reconciliation_nested_member_identity_changed")
                os.unlink(member.basename, dir_fd=parent_fd)
            else:
                child_fd = _open_directory(member.basename, dir_fd=parent_fd)
                try:
                    if _fs_identity(os.fstat(child_fd)) != (member.device, member.inode, member.object_type) or tuple(sorted(os.listdir(child_fd))) != member.expected_child_membership: raise _StagingCustodyMismatch("staging_reconciliation_nested_member_identity_changed")
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


def build_lifecycle_closure(*, execution_bundle_root: str | Path, execution_bundle_digest: str, rollback_bundle_root: str | Path, rollback_bundle_digest: str, closure_time: str, output_root: str | Path, correlation_id: str | None = None) -> ClosureOutcome:
    execution_root = Path(execution_bundle_root).resolve(); rollback_root = Path(rollback_bundle_root).resolve(); out, findings = _safe_root(output_root)
    if findings or any(a == b or a in b.parents or b in a.parents for a, b in ((out, execution_root), (out, rollback_root))): return ClosureOutcome("blocked_host_local_diagnostic_lifecycle_closure", tuple(findings + ["roots_overlap"]), {})
    ev = validate_persisted_execution_bundle(execution_root, expected_final_bundle_digest=execution_bundle_digest)
    rv = validate_persisted_rollback_bundle(rollback_root, expected_final_bundle_digest=rollback_bundle_digest, expected_execution_bundle_digest=execution_bundle_digest)
    if ev.status != "host_local_diagnostic_execution_completed" or rv.status != "host_local_diagnostic_rollback_completed": return ClosureOutcome("blocked_host_local_diagnostic_lifecycle_closure", tuple(sorted(set(ev.findings + rv.findings))), {})
    base_report, cross = _cross_validate(ev.records, rv.records, execution_bundle_digest)
    historical_correlation = str(base_report.get("correlation_id", ""))
    if correlation_id is not None and correlation_id != historical_correlation: cross.append("correlation_override_mismatch")
    if cross: return ClosureOutcome("blocked_host_local_diagnostic_lifecycle_closure", tuple(sorted(set(cross))), {})
    closure_id = derive_closure_id(execution_bundle_digest, rollback_bundle_digest, closure_time)
    identity = _identity(base_report, closure_id, closure_time, execution_bundle_digest, rollback_bundle_digest)
    out.mkdir(parents=True, exist_ok=True)
    with (out / ".closure.lock").open("a+b") as lock:
        _publication_hook("lock_waiting", out)
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX); destination = out / closure_id
        _publication_hook("locked_enter", out)
        try:
            root_fd = _open_directory(out)
        except OSError:
            return ClosureOutcome("blocked_host_local_diagnostic_lifecycle_closure", ("staging_reconciliation_publication_root_identity_changed",), {})
        try:
            root_info = os.fstat(root_fd); root_identity = _fs_identity(root_info)
            if not stat.S_ISDIR(root_info.st_mode) or not _root_is_bound(out, root_fd, root_identity):
                return ClosureOutcome("blocked_host_local_diagnostic_lifecycle_closure", ("staging_reconciliation_publication_root_identity_changed",), {})
            staging_findings, _ = _reconcile_staging(out, root_fd, root_identity)
            if staging_findings:
                _publication_hook("locked_exit", out)
                return ClosureOutcome("blocked_host_local_diagnostic_lifecycle_closure", tuple(staging_findings), {})
            if destination.exists():
                loaded = validate_lifecycle_closure(destination)
                loaded_final = _dict(loaded.records.get("final_manifest")); loaded_summary = _dict(loaded.records.get("summary"))
                if loaded.status != "host_local_diagnostic_lifecycle_closure_valid" or any(loaded_summary.get(k) != v for k, v in identity.items()): return ClosureOutcome("blocked_host_local_diagnostic_lifecycle_closure", ("closure_identity_conflict",), {})
                pointer = _pointer(identity, str(loaded_final.get("packet_digest", "")))
                latest = out / "latest.json"
                recovered = not latest.exists()
                if latest.exists() and _json(latest) != pointer: return ClosureOutcome("blocked_host_local_diagnostic_lifecycle_closure", ("latest_pointer_conflict",), {})
                if not latest.exists(): _write_pointer(out, pointer)
                _publication_hook("locked_exit", out)
                return ClosureOutcome(loaded.status, (), loaded.records, loaded.packet_root, True, "recovered" if recovered else "replayed")
            if (out / "latest.json").exists(): return ClosureOutcome("blocked_host_local_diagnostic_lifecycle_closure", ("latest_pointer_conflict",), {})
            temporary_parent = Path(tempfile.mkdtemp(prefix=_STAGING_PREFIX, dir=out)); staged = temporary_parent / closure_id
            temporary_identity: Path | None = None
            try:
                _publication_hook("staging_directory_reserved", temporary_parent)
                temporary_identity = _prepare_staging_identity(out, temporary_parent, closure_id)
                staged.mkdir()
                _publication_hook("staging_created", temporary_parent)
                _copy_bundle(execution_root, staged / EXECUTION_PATH); _copy_bundle(rollback_root, staged / ROLLBACK_PATH)
                report = {**base_report, **identity}; report["digest"] = digest_record(report); (staged / "closure_report.json").write_text(_canon(report) + "\n")
                summary = {"schema_version": SCHEMA_VERSION, "artifact_kind": "host_local_diagnostic_lifecycle_closure_summary", "status": "host_local_diagnostic_lifecycle_closed", **identity}; summary["digest"] = digest_record(summary); (staged / "summary.json").write_text(_canon(summary) + "\n")
                content_names = [p.relative_to(staged).as_posix() for p in staged.rglob("*") if p.is_file()]
                content = _manifest(staged, content_names, "host_local_diagnostic_lifecycle_closure_content_manifest", "content_manifest_digest"); (staged / "content_manifest.json").write_text(_canon(content) + "\n")
                receipt = {"schema_version": SCHEMA_VERSION, "artifact_kind": "host_local_diagnostic_lifecycle_closure_receipt", **identity, "closure_report_digest": _sha(report), "summary_digest": _sha(summary), "content_manifest_digest": content["content_manifest_digest"]}; receipt["digest"] = digest_record(receipt); (staged / "receipt.json").write_text(_canon(receipt) + "\n")
                final_names = [p.relative_to(staged).as_posix() for p in staged.rglob("*") if p.is_file()]
                final = _manifest(staged, final_names, "host_local_diagnostic_lifecycle_closure_final_manifest", "packet_digest", identity); (staged / "final_manifest.json").write_text(_canon(final) + "\n")
                staged_result = validate_lifecycle_closure(staged, expected_packet_digest=str(final["packet_digest"]))
                if staged_result.status != "host_local_diagnostic_lifecycle_closure_valid": return ClosureOutcome("blocked_host_local_diagnostic_lifecycle_closure", staged_result.findings, {})
                _publish_packet(staged, destination)
                published = validate_lifecycle_closure(destination, expected_packet_digest=str(final["packet_digest"]))
                if published.status != "host_local_diagnostic_lifecycle_closure_valid": return ClosureOutcome("blocked_host_local_diagnostic_lifecycle_closure", published.findings, {})
                _publication_hook("packet_published", destination)
                _write_pointer(out, _pointer(identity, str(final["packet_digest"])))
            finally:
                if temporary_identity is not None:
                    temporary_identity.unlink(missing_ok=True)
                shutil.rmtree(temporary_parent, ignore_errors=True)
            _publication_hook("locked_exit", out)
        finally:
            os.close(root_fd)
    return ClosureOutcome(published.status, published.findings, published.records, published.packet_root, False, "published")


def load_latest_summary(output_root: str | Path) -> ClosureOutcome:
    root = Path(output_root).resolve(strict=False)
    try:
        pointer = _json(root / "latest.json")
        exact = {"schema_version", "artifact_kind", "digest", "packet_digest", *(_identity({}, "", "", "", "").keys())}
        if set(pointer) != exact or pointer.get("schema_version") != SCHEMA_VERSION or pointer.get("artifact_kind") != "host_local_diagnostic_lifecycle_closure_pointer" or pointer.get("digest") != digest_record(pointer): raise ValueError("pointer_invalid")
        closure_id = str(pointer.get("closure_id", ""))
        result = validate_lifecycle_closure(root / closure_id, expected_packet_digest=str(pointer.get("packet_digest", "")))
        summary = _dict(result.records.get("summary")); final = _dict(result.records.get("final_manifest"))
        if result.status != "host_local_diagnostic_lifecycle_closure_valid" or any(pointer.get(k) != summary.get(k) for k in _identity({}, "", "", "", "")) or pointer.get("packet_digest") != final.get("packet_digest"): raise ValueError("pointer_identity_invalid")
        return ClosureOutcome(result.status, (), result.records, result.packet_root, True, "latest_replay")
    except Exception as exc:
        return ClosureOutcome("host_local_diagnostic_lifecycle_closure_latest_invalid", (type(exc).__name__,), {}, publication_posture="rejected")
