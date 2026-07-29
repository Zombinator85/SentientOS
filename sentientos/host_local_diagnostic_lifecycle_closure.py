"""Self-contained, read-only custody for one diagnostic execution and rollback."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
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
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX); destination = out / closure_id
        if destination.exists():
            loaded = validate_lifecycle_closure(destination)
            loaded_final = _dict(loaded.records.get("final_manifest")); loaded_summary = _dict(loaded.records.get("summary"))
            if loaded.status != "host_local_diagnostic_lifecycle_closure_valid" or any(loaded_summary.get(k) != v for k, v in identity.items()): return ClosureOutcome("blocked_host_local_diagnostic_lifecycle_closure", ("closure_identity_conflict",), {})
            pointer = _pointer(identity, str(loaded_final.get("packet_digest", "")))
            latest = out / "latest.json"
            recovered = not latest.exists()
            if latest.exists() and _json(latest) != pointer: return ClosureOutcome("blocked_host_local_diagnostic_lifecycle_closure", ("latest_pointer_conflict",), {})
            if not latest.exists(): _write_pointer(out, pointer)
            return ClosureOutcome(loaded.status, (), loaded.records, loaded.packet_root, True, "recovered" if recovered else "replayed")
        if (out / "latest.json").exists(): return ClosureOutcome("blocked_host_local_diagnostic_lifecycle_closure", ("latest_pointer_conflict",), {})
        temporary_parent = Path(tempfile.mkdtemp(prefix=".hldlc-", dir=out)); staged = temporary_parent / closure_id
        try:
            staged.mkdir()
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
            _write_pointer(out, _pointer(identity, str(final["packet_digest"])))
        finally:
            shutil.rmtree(temporary_parent, ignore_errors=True)
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
