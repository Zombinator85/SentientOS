"""Self-contained, read-only custody for one diagnostic execution and rollback."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
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


@dataclass(frozen=True)
class ClosureOutcome:
    status: str
    findings: tuple[str, ...]
    records: Mapping[str, Any]
    packet_root: str = ""
    replayed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _json(path: Path) -> dict[str, Any]:
    value = _dict(json.loads(path.read_text()))
    return dict(value)


def _bundle_digest(root: Path) -> str:
    return str(_json(root / "bundle_manifest.json").get("bundle_digest", ""))


def _safe_root(value: str | Path, *, create: bool = False) -> tuple[Path, list[str]]:
    path = Path(value).resolve(strict=False)
    findings: list[str] = []
    if path.exists() and (path.is_symlink() or not path.is_dir()): findings.append("unsafe_root")
    if any(parent.is_symlink() for parent in [path, *path.parents] if parent.exists()): findings.append("symlinked_root")
    if create and not findings: path.mkdir(parents=True, exist_ok=True)
    return path, findings


def _cross_validate(execution: Mapping[str, Any], rollback: Mapping[str, Any], execution_digest: str) -> tuple[dict[str, Any], list[str]]:
    findings: list[str] = []
    req = _dict(execution.get("runtime_request")); tx = _dict(execution.get("transaction_records"))
    closure = _dict(tx.get("closure_report")); snapshots = _dict(execution.get("target_snapshots"))
    artifact = _dict(snapshots.get(ARTIFACT_NAME)); plan_snap = _dict(snapshots.get("rollback_plan.json"))
    try: plan = _dict(json.loads(bytes.fromhex(str(plan_snap.get("bytes_hex", "")))))
    except (ValueError, json.JSONDecodeError): plan = {}; findings.append("rollback_plan_snapshot_invalid")
    runtime = _dict(rollback.get("runtime_result")); challenge = _dict(rollback.get("confirmation_challenge"))
    confirmation = _dict(rollback.get("operator_confirmation")); embedded = _dict(rollback.get("embedded_execution_records"))
    lifecycle = _dict(rollback.get("updated_lifecycle_report")); post = _dict(rollback.get("post_rollback_snapshot"))
    rb_records = _dict(rollback.get("rollback_records")); rb_request = _dict(rb_records.get("request"))
    execution_id = "hlder-" + hashlib.sha256(_canon({k:v for k,v in req.items() if k != "schema_version"}).encode()).hexdigest()[:24]
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
        if not values[0] or any(value != values[0] for value in values[1:]): findings.append("cross_bundle_" + name + "_mismatch")
    if _canon(embedded) != _canon(execution): findings.append("embedded_execution_substitution")
    if closure.get("lifecycle_status") != "local_effect_lifecycle_rollback_pending": findings.append("historical_lifecycle_not_rollback_pending")
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
        "rollback_plan_id": plan.get("plan_id"), "rollback_plan_digest": plan.get("digest"),
        "execution_time": req.get("execution_time"), "rollback_time": None,
        "historical_lifecycle": closure.get("lifecycle_status"), "final_lifecycle": lifecycle.get("lifecycle_status"),
        "rollback_posture": "direct" if runtime.get("rollback_invoked_by_current_coordinator") is True else "reconciled",
        "historical_execution_call_count": 1, "historical_rollback_call_count": 1,
        "closure_processing_execution_call_count": 0, "closure_processing_rollback_call_count": 0,
        "mutation_boundary": runtime.get("exact_file_mutation"), "unrelated_siblings_preserved": rollback.get("unrelated_siblings_before") == rollback.get("unrelated_siblings_after"),
        "runtime_owned_files_preserved": True, "broader_authority": False,
        "authenticity_note": "Unkeyed digests provide integrity binding, not authorship or external authenticity.",
    }
    history = rollback.get("rollback_intent_history", [])
    if isinstance(history, list) and history: report["rollback_time"] = _dict(_dict(history[0]).get("identity")).get("rollback_time")
    report["digest"] = digest_record(report)
    return report, findings


def _manifest(root: Path, names: list[str], kind: str, digest_name: str) -> dict[str, Any]:
    value: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "artifact_kind": kind, "files": []}
    for name in sorted(names):
        raw = (root / name).read_bytes(); value["files"].append({"relative_filename": name, "size_bytes": len(raw), "sha256": _raw_sha(raw)})
    value[digest_name] = _sha(value)
    return value


def validate_lifecycle_closure(packet_root: str | Path, *, expected_packet_digest: str | None = None) -> ClosureOutcome:
    root, findings = _safe_root(packet_root); records: dict[str, Any] = {}
    try:
        paths = list(root.rglob("*")); actual = {p.relative_to(root).as_posix() for p in paths if p.is_file()}
        if any(p.is_symlink() for p in paths): findings.append("symlinked_packet_artifact")
        manifest = _json(root / "final_manifest.json"); check = dict(manifest); claimed = check.pop("packet_digest", None)
        if claimed != _sha(check) or (expected_packet_digest and claimed != expected_packet_digest): findings.append("packet_digest_mismatch")
        entries = manifest.get("files", []); names = [str(_dict(e).get("relative_filename", "")) for e in entries]
        if len(names) != len(set(names)) or set(names) | {"final_manifest.json"} != actual: findings.append("exact_final_manifest_membership_mismatch")
        for entry in entries:
            entry = _dict(entry); name = str(entry.get("relative_filename", "")); path = root / name
            if not name or name.startswith("/") or ".." in Path(name).parts or path.is_symlink() or not path.is_file(): findings.append("manifest_path_rejected:" + name); continue
            raw = path.read_bytes()
            if set(entry) != {"relative_filename", "size_bytes", "sha256"} or len(raw) != entry.get("size_bytes") or _raw_sha(raw) != entry.get("sha256"): findings.append("manifest_file_mismatch:" + name)
        content = _json(root / "content_manifest.json"); ccheck = dict(content); cdigest = ccheck.pop("content_manifest_digest", None)
        centries = content.get("files", []); cnames = [str(_dict(e).get("relative_filename", "")) for e in centries]
        expected_content = sorted(actual - {"final_manifest.json", "content_manifest.json", "receipt.json"})
        if len(cnames) != len(set(cnames)) or sorted(cnames) != expected_content or cdigest != _sha(ccheck): findings.append("content_manifest_invalid")
        execution_digest = _bundle_digest(root / EXECUTION_PATH); rollback_digest = _bundle_digest(root / ROLLBACK_PATH)
        summary = _json(root / "summary.json"); receipt = _json(root / "receipt.json"); report = _json(root / "closure_report.json")
        ev = validate_persisted_execution_bundle(root / EXECUTION_PATH, expected_final_bundle_digest=str(summary.get("execution_bundle_digest", "")))
        rv = validate_persisted_rollback_bundle(root / ROLLBACK_PATH, expected_final_bundle_digest=str(summary.get("rollback_bundle_digest", "")), expected_execution_bundle_digest=execution_digest)
        findings.extend("nested_execution:" + x for x in ev.findings); findings.extend("nested_rollback:" + x for x in rv.findings)
        expected_report, cross = _cross_validate(ev.records, rv.records, execution_digest); findings.extend(cross)
        if report != expected_report: findings.append("closure_report_invalid")
        expected_summary = {"schema_version": SCHEMA_VERSION, "artifact_kind": "host_local_diagnostic_lifecycle_closure_summary", "status": "host_local_diagnostic_lifecycle_closed", "closure_id": summary.get("closure_id"), "closure_time": summary.get("closure_time"), "execution_id": report.get("execution_id"), "rollback_id": report.get("rollback_id"), "correlation_id": report.get("correlation_id"), "execution_bundle_digest": execution_digest, "rollback_bundle_digest": rollback_digest, "final_lifecycle": report.get("final_lifecycle")}
        expected_summary["digest"] = digest_record(expected_summary)
        if summary != expected_summary: findings.append("summary_invalid")
        expected_receipt = {"schema_version": SCHEMA_VERSION, "artifact_kind": "host_local_diagnostic_lifecycle_closure_receipt", "closure_id": summary.get("closure_id"), "closure_time": summary.get("closure_time"), "execution_bundle_digest": execution_digest, "rollback_bundle_digest": rollback_digest, "closure_report_digest": _sha(report), "summary_digest": _sha(summary), "content_manifest_digest": cdigest}
        expected_receipt["digest"] = digest_record(expected_receipt)
        if receipt != expected_receipt: findings.append("receipt_invalid")
        records = {"closure_report": report, "summary": summary, "receipt": receipt, "content_manifest": content, "final_manifest": manifest}
    except Exception as exc: findings.append("packet_decode_failed:" + type(exc).__name__)
    status = "host_local_diagnostic_lifecycle_closure_valid" if not findings else "host_local_diagnostic_lifecycle_closure_invalid"
    return ClosureOutcome(status, tuple(sorted(set(findings))), records, str(root), True)


def build_lifecycle_closure(*, execution_bundle_root: str | Path, execution_bundle_digest: str, rollback_bundle_root: str | Path, rollback_bundle_digest: str, closure_time: str, output_root: str | Path, correlation_id: str | None = None) -> ClosureOutcome:
    execution_root = Path(execution_bundle_root).resolve(); rollback_root = Path(rollback_bundle_root).resolve(); out, findings = _safe_root(output_root, create=True)
    if findings or any(a == b or a in b.parents or b in a.parents for a,b in ((out,execution_root),(out,rollback_root))): return ClosureOutcome("blocked_host_local_diagnostic_lifecycle_closure", tuple(findings + ["roots_overlap"]), {})
    ev = validate_persisted_execution_bundle(execution_root, expected_final_bundle_digest=execution_bundle_digest)
    rv = validate_persisted_rollback_bundle(rollback_root, expected_final_bundle_digest=rollback_bundle_digest, expected_execution_bundle_digest=execution_bundle_digest)
    if ev.status != "host_local_diagnostic_execution_completed" or rv.status != "host_local_diagnostic_rollback_completed": return ClosureOutcome("blocked_host_local_diagnostic_lifecycle_closure", tuple(sorted(set(ev.findings + rv.findings))), {})
    report, cross = _cross_validate(ev.records, rv.records, execution_bundle_digest)
    if cross: return ClosureOutcome("blocked_host_local_diagnostic_lifecycle_closure", tuple(sorted(set(cross))), {})
    identity = {"execution_bundle_digest": execution_bundle_digest, "rollback_bundle_digest": rollback_bundle_digest, "closure_time": closure_time}
    closure_id = "hldlc-" + hashlib.sha256(_canon(identity).encode()).hexdigest()[:24]; correlation = correlation_id or str(report["correlation_id"])
    out.mkdir(parents=True, exist_ok=True)
    with (out / ".closure.lock").open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX); destination = out / closure_id
        if destination.exists():
            loaded = validate_lifecycle_closure(destination)
            summary = _dict(loaded.records.get("summary"))
            if loaded.status == "host_local_diagnostic_lifecycle_closure_valid" and summary.get("closure_time") == closure_time and summary.get("correlation_id") == correlation: return ClosureOutcome(loaded.status, (), loaded.records, loaded.packet_root, True)
            return ClosureOutcome("blocked_host_local_diagnostic_lifecycle_closure", ("closure_identity_conflict",), {})
        if (out / "latest.json").exists():
            old = _json(out / "latest.json")
            if old.get("correlation_id") == correlation: return ClosureOutcome("blocked_host_local_diagnostic_lifecycle_closure", ("correlation_reuse_conflict",), {})
        tmp = Path(tempfile.mkdtemp(prefix=".hldlc-", dir=out))
        try:
            shutil.copytree(execution_root, tmp / EXECUTION_PATH); shutil.copytree(rollback_root, tmp / ROLLBACK_PATH)
            (tmp / "closure_report.json").write_text(_canon(report) + "\n")
            summary = {"schema_version": SCHEMA_VERSION, "artifact_kind": "host_local_diagnostic_lifecycle_closure_summary", "status": "host_local_diagnostic_lifecycle_closed", "closure_id": closure_id, "closure_time": closure_time, "execution_id": report["execution_id"], "rollback_id": report["rollback_id"], "correlation_id": correlation, "execution_bundle_digest": execution_bundle_digest, "rollback_bundle_digest": rollback_bundle_digest, "final_lifecycle": report["final_lifecycle"]}; summary["digest"] = digest_record(summary)
            (tmp / "summary.json").write_text(_canon(summary) + "\n")
            content_names = [p.relative_to(tmp).as_posix() for p in tmp.rglob("*") if p.is_file()]
            content = _manifest(tmp, content_names, "host_local_diagnostic_lifecycle_closure_content_manifest", "content_manifest_digest"); (tmp / "content_manifest.json").write_text(_canon(content) + "\n")
            receipt = {"schema_version": SCHEMA_VERSION, "artifact_kind": "host_local_diagnostic_lifecycle_closure_receipt", "closure_id": closure_id, "closure_time": closure_time, "execution_bundle_digest": execution_bundle_digest, "rollback_bundle_digest": rollback_bundle_digest, "closure_report_digest": _sha(report), "summary_digest": _sha(summary), "content_manifest_digest": content["content_manifest_digest"]}; receipt["digest"] = digest_record(receipt); (tmp / "receipt.json").write_text(_canon(receipt) + "\n")
            final_names = [p.relative_to(tmp).as_posix() for p in tmp.rglob("*") if p.is_file()]; final = _manifest(tmp, final_names, "host_local_diagnostic_lifecycle_closure_final_manifest", "packet_digest"); (tmp / "final_manifest.json").write_text(_canon(final) + "\n")
            os.replace(tmp, destination)
            pointer = {"schema_version": SCHEMA_VERSION, "artifact_kind": "host_local_diagnostic_lifecycle_closure_pointer", "closure_id": closure_id, "correlation_id": correlation, "packet_digest": final["packet_digest"]}; pointer["digest"] = digest_record(pointer)
            fd,name=tempfile.mkstemp(dir=out,prefix=".latest-"); os.close(fd); Path(name).write_text(_canon(pointer)+"\n"); os.replace(name,out/"latest.json")
        except Exception:
            shutil.rmtree(tmp, ignore_errors=True); raise
    return validate_lifecycle_closure(destination, expected_packet_digest=str(final["packet_digest"]))


def load_latest_summary(output_root: str | Path) -> ClosureOutcome:
    root = Path(output_root).resolve(strict=False)
    try:
        pointer = _json(root / "latest.json")
        if pointer.get("schema_version") != SCHEMA_VERSION or pointer.get("artifact_kind") != "host_local_diagnostic_lifecycle_closure_pointer" or pointer.get("digest") != digest_record(pointer): raise ValueError("pointer_invalid")
        result = validate_lifecycle_closure(root / str(pointer.get("closure_id", "")), expected_packet_digest=str(pointer.get("packet_digest", "")))
        if result.status != "host_local_diagnostic_lifecycle_closure_valid" or _dict(result.records.get("summary")).get("correlation_id") != pointer.get("correlation_id"): raise ValueError("pointer_identity_invalid")
        return result
    except Exception as exc:
        return ClosureOutcome("host_local_diagnostic_lifecycle_closure_latest_invalid", (type(exc).__name__,), {})
