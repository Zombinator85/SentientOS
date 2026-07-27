"""Operator-confirmed, durable-at-most-once rollback of one diagnostic execution."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, cast

from sentientos.host_local_diagnostic_execution_runtime import (
    ARTIFACT_NAME,
    FORBIDDEN_FLAGS,
    NO_BROAD_AUTHORITY,
    TARGET_FILES,
    validate_fresh_execution_authority,
    validate_persisted_execution_bundle,
)
from sentientos.host_local_diagnostic_execution_source_runtime import _canon, _dict, _path_findings, _raw_sha, _sha, digest_record
from sentientos.local_diagnostic_effect import (
    run_local_diagnostic_exact_rollback_wing,
    validate_local_diagnostic_exact_rollback_receipt,
    validate_local_diagnostic_exact_rollback_request,
    validate_local_diagnostic_exact_rollback_result,
    validate_local_diagnostic_rollback_audit_receipt,
    validate_local_diagnostic_rollback_postcondition_check,
)
from sentientos.local_effect_transaction_ledger import (
    build_transaction_ledger_from_local_diagnostic_records,
    validate_local_effect_transaction_ledger,
    validate_local_effect_transaction_lifecycle_report,
)

SCHEMA_VERSION = "host_local_diagnostic_rollback_runtime.v1"
ROLLBACK_SCOPE = "local_diagnostic_exact_rollback"


@dataclass(frozen=True)
class RollbackOutcome:
    status: str
    findings: tuple[str, ...]
    records: Mapping[str, Any]
    bundle_root: str = ""
    rollback_call_count: int = 0
    replayed: bool = False
    reconciled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _challenge(records: Mapping[str, Any], bundle_digest: str, snapshot: Mapping[str, Any], verification: Mapping[str, Any], rollback_time: str) -> dict[str, Any]:
    request = _dict(records["runtime_request"])
    source = _dict(records["source_records"])
    posture = _dict(source["current_authority_posture"])
    receipt = json.loads(bytes.fromhex(str(_dict(records["target_snapshots"])["effect_receipt.json"]["bytes_hex"])))
    plan = json.loads(bytes.fromhex(str(_dict(records["target_snapshots"])["rollback_plan.json"]["bytes_hex"])))
    value = {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": "host_local_diagnostic_rollback_confirmation_challenge",
        "completed_execution_bundle_digest": bundle_digest,
        "execution_id": Path(str(request.get("correlation_id", ""))).name or request["source_request_id"],
        "correlation_id": request["correlation_id"],
        "source_request_id": request["source_request_id"],
        "source_request_digest": request["source_request_digest"],
        "grant_id": posture["grant_id"],
        "grant_digest": posture["grant_digest"],
        "fresh_snapshot_digest": snapshot.get("digest"),
        "fresh_verification_digest": verification.get("digest"),
        "historical_artifact_path": receipt["output_path"],
        "historical_artifact_digest": receipt["artifact_digest"],
        "rollback_plan_id": plan["plan_id"],
        "rollback_plan_digest": plan["digest"],
        "rollback_operation": "delete_exact_local_diagnostic_artifact_only",
        "required_authority_scope": ROLLBACK_SCOPE,
        "rollback_time": rollback_time,
        **NO_BROAD_AUTHORITY,
    }
    value["confirmation_challenge_id"] = "hldrr-challenge-" + hashlib.sha256(_canon(value).encode()).hexdigest()[:24]
    value["confirmation_challenge_digest"] = digest_record(value)
    return value


def _snapshot(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {"path": str(path), "size_bytes": len(raw), "sha256": _raw_sha(raw), "bytes_hex": raw.hex(), "exists": True}


def _live_findings(records: Mapping[str, Any], *, after: bool = False) -> list[str]:
    findings: list[str] = []
    snapshots = _dict(records.get("target_snapshots"))
    for name in TARGET_FILES:
        historical = _dict(snapshots.get(name))
        path = Path(str(historical.get("path", "")))
        if after and name == ARTIFACT_NAME:
            if path.exists() or path.is_symlink():
                findings.append("rolled_back_artifact_still_exists")
            continue
        if path.is_symlink() or not path.is_file():
            findings.append("live_target_missing_or_substituted:" + name)
        else:
            raw = path.read_bytes()
            if _raw_sha(raw) != historical.get("sha256") or len(raw) != historical.get("size_bytes"):
                findings.append("live_target_changed:" + name)
    return findings


class HostLocalDiagnosticRollbackRuntimeCoordinator:
    def __init__(self, rollback: Callable[..., Any] = run_local_diagnostic_exact_rollback_wing, failure_hook: Callable[[str], None] | None = None) -> None:
        self.rollback = rollback
        self.failure_hook = failure_hook

    def preflight(self, *, execution_bundle_root: str | Path, expected_execution_bundle_digest: str, current_snapshot: Mapping[str, Any], current_verification: Mapping[str, Any], rollback_time: str) -> RollbackOutcome:
        loaded = validate_persisted_execution_bundle(execution_bundle_root, expected_final_bundle_digest=expected_execution_bundle_digest)
        findings = list(loaded.findings)
        records = loaded.records
        if loaded.status != "host_local_diagnostic_execution_completed":
            findings.append("completed_execution_required")
        result = _dict(records.get("runtime_result"))
        closure = _dict(_dict(records.get("transaction_records")).get("closure_report"))
        if result.get("rollback_performed") is not False or closure.get("lifecycle_status") != "local_effect_lifecycle_rollback_pending":
            findings.append("execution_not_rollback_pending")
        authority, authority_findings = validate_fresh_execution_authority(_dict(records.get("source_records")), current_snapshot, current_verification, rollback_time)
        findings.extend(authority_findings)
        checked = set(current_verification.get("checked_scope_labels", ()))
        if ROLLBACK_SCOPE not in checked:
            findings.append("missing_exact_rollback_scope")
        findings.extend(_live_findings(records))
        challenge = _challenge(records, expected_execution_bundle_digest, current_snapshot, current_verification, rollback_time) if records else {}
        status = "host_local_diagnostic_rollback_preflight_ready" if not findings else "blocked_host_local_diagnostic_rollback_preflight"
        return RollbackOutcome(status, tuple(sorted(set(findings))), {"execution_records": records, "fresh_current_snapshot": dict(current_snapshot), "fresh_current_verification": dict(current_verification), "fresh_authority_validation": authority, "confirmation_challenge": challenge})

    def rollback_execution(self, *, execution_bundle_root: str | Path, expected_execution_bundle_digest: str, current_snapshot: Mapping[str, Any], current_verification: Mapping[str, Any], rollback_time: str, output_root: str | Path, confirm_exact_rollback: bool, confirm_execution_bundle_digest: str, confirm_artifact_path: str, confirmation_challenge_digest: str, correlation_id: str | None = None) -> RollbackOutcome:
        out = Path(output_root).resolve(strict=False)
        replay = self._replay(out, expected_execution_bundle_digest, correlation_id)
        if replay is not None:
            return replay
        # Recovery precedes live preflight because a returned rollback has
        # already made the historical artifact intentionally absent.
        if out.is_dir():
            with (out / ".rollback.lock").open("a+b") as recovery_lock:
                fcntl.flock(recovery_lock.fileno(), fcntl.LOCK_EX)
                replay = self._replay(out, expected_execution_bundle_digest, correlation_id)
                if replay is not None:
                    return replay
                for intent in sorted(out.glob("*.intent")):
                    states = sorted(intent.glob("[0-9][0-9]_*.json"))
                    if not states:
                        continue
                    identity = _dict(json.loads(states[0].read_text()).get("identity"))
                    if identity.get("execution_bundle_digest") != expected_execution_bundle_digest or (correlation_id and identity.get("correlation_id") != correlation_id):
                        continue
                    loaded = validate_persisted_execution_bundle(execution_bundle_root, expected_final_bundle_digest=expected_execution_bundle_digest)
                    authority, fresh = validate_fresh_execution_authority(_dict(loaded.records.get("source_records")), current_snapshot, current_verification, rollback_time)
                    if ROLLBACK_SCOPE not in set(current_verification.get("checked_scope_labels", ())): fresh.append("missing_exact_rollback_scope")
                    if loaded.findings or fresh:
                        return RollbackOutcome("blocked_host_local_diagnostic_rollback_recovery_authority", tuple(sorted(set(loaded.findings + tuple(fresh)))), {})
                    challenge = _challenge(loaded.records, expected_execution_bundle_digest, current_snapshot, current_verification, rollback_time)
                    recovery = {"execution_records": loaded.records, "fresh_current_snapshot": dict(current_snapshot), "fresh_current_verification": dict(current_verification), "fresh_authority_validation": authority, "confirmation_challenge": challenge}
                    return self._reconcile(intent, out, intent.name.removesuffix(".intent"), identity, loaded.records, recovery, challenge)
        pre = self.preflight(execution_bundle_root=execution_bundle_root, expected_execution_bundle_digest=expected_execution_bundle_digest, current_snapshot=current_snapshot, current_verification=current_verification, rollback_time=rollback_time)
        if pre.status != "host_local_diagnostic_rollback_preflight_ready":
            return pre
        challenge = _dict(pre.records["confirmation_challenge"])
        if not (confirm_exact_rollback and confirm_execution_bundle_digest == expected_execution_bundle_digest and str(Path(confirm_artifact_path).resolve(strict=False)) == str(Path(challenge["historical_artifact_path"]).resolve(strict=False)) and confirmation_challenge_digest == challenge["confirmation_challenge_digest"]):
            return RollbackOutcome("blocked_host_local_diagnostic_rollback_confirmation", ("operator_confirmation_missing_or_mismatched",), {})
        records = _dict(pre.records["execution_records"])
        artifact = Path(challenge["historical_artifact_path"])
        root, path_findings = _path_findings(out, may_not_exist=True)
        if path_findings or root == artifact.parent or root in artifact.parents or artifact.parent in root.parents:
            return RollbackOutcome("blocked_host_local_diagnostic_rollback_target", tuple(path_findings + ["rollback_roots_overlap"]), {})
        identity_data = {"execution_bundle_digest": expected_execution_bundle_digest, "artifact_path": str(artifact), "artifact_digest": challenge["historical_artifact_digest"], "rollback_plan_digest": challenge["rollback_plan_digest"], "snapshot_digest": challenge["fresh_snapshot_digest"], "verification_digest": challenge["fresh_verification_digest"], "rollback_time": rollback_time, "confirmation_digest": confirmation_challenge_digest, "correlation_id": correlation_id or challenge["correlation_id"]}
        rollback_id = "hldrr-" + hashlib.sha256(_canon(identity_data).encode()).hexdigest()[:24]
        root.mkdir(parents=True, exist_ok=True)
        with (root / ".rollback.lock").open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            replay = self._replay(root, expected_execution_bundle_digest, identity_data["correlation_id"])
            if replay is not None:
                return replay
            intent = root / (rollback_id + ".intent")
            if intent.exists():
                return self._reconcile(intent, root, rollback_id, identity_data, records, pre.records, challenge)
            siblings = {p.name: _snapshot(p) for p in artifact.parent.iterdir() if p.is_file() and p.name != ARTIFACT_NAME}
            intent.mkdir()
            history: list[dict[str, Any]] = []
            self._state(intent, history, "prepared", identity_data, {"unrelated_siblings_before": siblings})
            if self.failure_hook: self.failure_hook("prepared")
            findings = _live_findings(records)
            _, fresh = validate_fresh_execution_authority(_dict(records["source_records"]), current_snapshot, current_verification, rollback_time)
            if ROLLBACK_SCOPE not in set(current_verification.get("checked_scope_labels", ())): fresh.append("missing_exact_rollback_scope")
            if findings or fresh:
                return RollbackOutcome("blocked_host_local_diagnostic_rollback_revalidation", tuple(sorted(set(findings + fresh))), {})
            self._state(intent, history, "invocation_committed", identity_data)
            if self.failure_hook: self.failure_hook("invocation_committed")
            tx = _dict(records["transaction_records"])
            plan = json.loads(bytes.fromhex(str(_dict(records["target_snapshots"])["rollback_plan.json"]["bytes_hex"])))
            effect_receipt = json.loads(bytes.fromhex(str(_dict(records["target_snapshots"])["effect_receipt.json"]["bytes_hex"])))
            result = self.rollback(effect_receipt, plan, output_dir_scope=artifact.parent, allow_missing_artifact=False, dry_run=False, created_at=rollback_time)
            returned = {k: _dict(v) for k, v in result._asdict().items()}
            self._state(intent, history, "rollback_returned", identity_data, {"rollback_records": returned})
            if self.failure_hook: self.failure_hook("rollback_returned")
            return self._finalize(intent, root, rollback_id, identity_data, records, pre.records, challenge, history, returned, direct=True)

    def _state(self, root: Path, history: list[dict[str, Any]], state: str, identity: Mapping[str, Any], evidence: Mapping[str, Any] | None = None) -> None:
        record = {"schema_version": SCHEMA_VERSION, "state": state, "identity": dict(identity), "previous_state_digest": history[-1]["digest"] if history else "", **dict(evidence or {})}
        record["digest"] = digest_record(record); history.append(record)
        path = root / f"{len(history):02d}_{state}.json"; path.write_text(_canon(record) + "\n"); fd = os.open(path, os.O_RDONLY); os.fsync(fd); os.close(fd)

    def _history(self, intent: Path, identity: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
        history: list[dict[str, Any]] = []; findings: list[str] = []
        try:
            for path in sorted(intent.glob("[0-9][0-9]_*.json")):
                record = json.loads(path.read_text())
                if record.get("digest") != digest_record(record) or record.get("identity") != dict(identity) or record.get("previous_state_digest") != (history[-1]["digest"] if history else ""):
                    findings.append("intent_chain_invalid")
                history.append(record)
        except (OSError, ValueError, json.JSONDecodeError): findings.append("intent_chain_invalid")
        return history, findings

    def _reconcile(self, intent: Path, root: Path, rollback_id: str, identity: Mapping[str, Any], execution: Mapping[str, Any], pre: Mapping[str, Any], challenge: Mapping[str, Any]) -> RollbackOutcome:
        history, findings = self._history(intent, identity)
        if findings: return RollbackOutcome("host_local_diagnostic_rollback_ambiguous", tuple(findings), {})
        states = [x["state"] for x in history]
        if states == ["prepared"]: return RollbackOutcome("host_local_diagnostic_rollback_prepared_retryable", ("prepared_revalidation_required",), {}, rollback_call_count=0)
        if "rollback_returned" in states:
            returned = _dict(next(x for x in history if x["state"] == "rollback_returned").get("rollback_records"))
            if self._rollback_evidence_findings(returned) or _live_findings(execution, after=True):
                return RollbackOutcome("host_local_diagnostic_rollback_ambiguous", ("rollback_returned_evidence_incomplete_or_ambiguous",), {})
            return self._finalize(intent, root, rollback_id, identity, execution, pre, challenge, history, returned, direct=False)
        if "invocation_committed" in states:
            return RollbackOutcome("host_local_diagnostic_rollback_ambiguous", ("rollback_retry_forbidden_after_invocation_commit",), {}, rollback_call_count=0)
        return RollbackOutcome("host_local_diagnostic_rollback_ambiguous", ("illegal_intent_state",), {})

    def _rollback_evidence_findings(self, records: Mapping[str, Any]) -> list[str]:
        findings: list[str] = []
        for name, validator in (("request", validate_local_diagnostic_exact_rollback_request), ("result", validate_local_diagnostic_exact_rollback_result), ("receipt", validate_local_diagnostic_exact_rollback_receipt), ("postcondition_check", validate_local_diagnostic_rollback_postcondition_check), ("audit_receipt", validate_local_diagnostic_rollback_audit_receipt)):
            check = validator(_dict(records.get(name))); findings.extend(name + ":" + f for f in check.findings)
        if _dict(records.get("result")).get("rollback_status") != "local_diagnostic_exact_rollback_performed" or _dict(records.get("receipt")).get("real_rollback_performed") is not True:
            findings.append("rollback_not_performed")
        return findings

    def _finalize(self, intent: Path, root: Path, rollback_id: str, identity: Mapping[str, Any], execution: Mapping[str, Any], pre: Mapping[str, Any], challenge: Mapping[str, Any], history: list[dict[str, Any]], returned: Mapping[str, Any], *, direct: bool) -> RollbackOutcome:
        findings = self._rollback_evidence_findings(returned) + _live_findings(execution, after=True)
        before = _dict(history[0].get("unrelated_siblings_before")); artifact = Path(str(identity["artifact_path"]))
        after = {p.name: _snapshot(p) for p in artifact.parent.iterdir() if p.is_file() and p.name != ARTIFACT_NAME}
        if before != after: findings.append("unrelated_sibling_changed")
        if findings: return RollbackOutcome("host_local_diagnostic_rollback_ambiguous", tuple(sorted(set(findings))), {})
        tx = _dict(execution["transaction_records"]); rr = _dict(returned)
        snapshots = _dict(execution["target_snapshots"])
        def historical(name: str) -> dict[str, Any]:
            return dict(cast(Mapping[str, Any], json.loads(bytes.fromhex(str(_dict(snapshots[name])["bytes_hex"])))))
        lifecycle = build_transaction_ledger_from_local_diagnostic_records(effect_receipt=historical("effect_receipt.json"), postcondition_check=historical("postcondition_check.json"), production_audit=historical("production_audit.json"), rollback_plan=historical("rollback_plan.json"), exact_rollback_request=rr["request"], exact_rollback_result=rr["result"], exact_rollback_receipt=rr["receipt"], rollback_postcondition_check=rr["postcondition_check"], rollback_audit=rr["audit_receipt"], created_at=str(identity["rollback_time"]))
        # The transaction coordinator's closure records are the canonical complete source set.
        closure = _dict(tx["closure_report"])
        if closure.get("lifecycle_status") != "local_effect_lifecycle_rollback_pending": findings.append("historical_lifecycle_not_pending")
        self._state(intent, history, "observation_persisted", identity)
        self._state(intent, history, "finalized", identity)
        records = {"embedded_execution_records": execution, "expected_execution_bundle_digest": identity["execution_bundle_digest"], "fresh_current_snapshot": pre["fresh_current_snapshot"], "fresh_current_verification": pre["fresh_current_verification"], "fresh_authority_validation": pre["fresh_authority_validation"], "confirmation_challenge": challenge, "operator_confirmation": {"present": True, "confirmed_bundle_digest": identity["execution_bundle_digest"], "confirmed_artifact_path": identity["artifact_path"], "confirmed_challenge_digest": identity["confirmation_digest"], "exact_rollback_scope": ROLLBACK_SCOPE, **NO_BROAD_AUTHORITY}, "rollback_intent_history": history, "rollback_records": returned, "updated_transaction_ledger": lifecycle.ledger.to_dict(), "updated_lifecycle_report": lifecycle.lifecycle_report.to_dict(), "pre_rollback_artifact_snapshot": _dict(execution["target_snapshots"])[ARTIFACT_NAME], "post_rollback_snapshot": {"path": str(artifact), "exists": False}, "unrelated_siblings_before": before, "unrelated_siblings_after": after, "runtime_result": {"status": "host_local_diagnostic_rollback_completed", "historical_diagnostic_write": True, "rollback_invoked_historically": True, "rollback_invoked_by_current_coordinator": direct, "prior_invocation_reconciled": not direct, "exact_file_mutation": "deleted:" + str(artifact), "rollback_call_count": 1 if direct else 0, "exact_diagnostic_rollback_authorized": True, **NO_BROAD_AUTHORITY}}
        bundle = self._persist(root, rollback_id, records, str(identity["correlation_id"]))
        return RollbackOutcome("host_local_diagnostic_rollback_completed", (), records, str(bundle), 1 if direct else 0, False, not direct)

    def _persist(self, root: Path, rollback_id: str, records: Mapping[str, Any], correlation_id: str) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix=".hldrr-", dir=root)); files: list[str] = []
        for name, value in sorted(records.items()):
            path = tmp / (name + ".json"); path.write_text(_canon(value) + "\n"); files.append(path.name)
        summary = {"schema_version": SCHEMA_VERSION, "status": "host_local_diagnostic_rollback_completed", "rollback_id": rollback_id}; (tmp / "summary.json").write_text(_canon(summary) + "\n"); files.append("summary.json")
        content = {"schema_version": SCHEMA_VERSION, "artifact_kind": "host_local_diagnostic_rollback_content_manifest", "files": [{"relative_filename": n, "size_bytes": len((tmp/n).read_bytes()), "sha256": _raw_sha((tmp/n).read_bytes())} for n in sorted(files)]}; content["content_manifest_digest"] = _sha(content); (tmp/"content_manifest.json").write_text(_canon(content)+"\n")
        receipt = {"schema_version": SCHEMA_VERSION, "rollback_id": rollback_id, "content_manifest_digest": content["content_manifest_digest"], "runtime_result_digest": _sha(records["runtime_result"])}; receipt["digest"] = digest_record(receipt); (tmp/"runtime_receipt.json").write_text(_canon(receipt)+"\n")
        finals = files + ["content_manifest.json", "runtime_receipt.json"]; manifest = {"schema_version": SCHEMA_VERSION, "artifact_kind": "host_local_diagnostic_rollback_bundle_manifest", "files": [{"relative_filename": n, "size_bytes": len((tmp/n).read_bytes()), "sha256": _raw_sha((tmp/n).read_bytes())} for n in sorted(finals)]}; manifest["bundle_digest"] = _sha(manifest); (tmp/"bundle_manifest.json").write_text(_canon(manifest)+"\n")
        bundle = root/rollback_id; os.replace(tmp, bundle)
        pointer = {"rollback_id": rollback_id, "correlation_id": correlation_id, "execution_bundle_digest": records["expected_execution_bundle_digest"], "bundle_digest": manifest["bundle_digest"]}
        _atomic_json(root/"latest.json", pointer); index = root/"replay_index.json"; mapping = json.loads(index.read_text()) if index.exists() else {}; mapping[correlation_id] = pointer; _atomic_json(index, mapping)
        return bundle

    def _replay(self, root: Path, execution_digest: str, correlation_id: str | None) -> RollbackOutcome | None:
        if not correlation_id or not (root/"replay_index.json").is_file(): return None
        try:
            pointer = json.loads((root/"replay_index.json").read_text()).get(correlation_id)
            if not pointer: return None
            if pointer.get("execution_bundle_digest") != execution_digest: return RollbackOutcome("host_local_diagnostic_rollback_bundle_invalid", ("replay_execution_digest_mismatch",), {})
            loaded = validate_persisted_rollback_bundle(root/pointer["rollback_id"], expected_final_bundle_digest=pointer["bundle_digest"], expected_execution_bundle_digest=execution_digest)
            if loaded.status != "host_local_diagnostic_rollback_completed": return loaded
            return RollbackOutcome(loaded.status, (), loaded.records, loaded.bundle_root, 0, True, bool(_dict(loaded.records["runtime_result"]).get("prior_invocation_reconciled")))
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc: return RollbackOutcome("host_local_diagnostic_rollback_bundle_invalid", ("replay_index_invalid:"+type(exc).__name__,), {})


def _atomic_json(path: Path, value: Any) -> None:
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".tmp-"); os.close(fd); Path(name).write_text(_canon(value)+"\n"); os.replace(name, path)


def validate_persisted_rollback_bundle(bundle_root: str | Path, *, expected_final_bundle_digest: str | None = None, expected_execution_bundle_digest: str | None = None) -> RollbackOutcome:
    root, findings = _path_findings(bundle_root); records: dict[str, Any] = {}
    try:
        actual = {p.name for p in root.iterdir()}
        if any(p.is_symlink() for p in root.iterdir()): findings.append("symlinked_bundle_artifact")
        manifest = json.loads((root/"bundle_manifest.json").read_text()); check = dict(manifest); claimed = check.pop("bundle_digest", None)
        if claimed != _sha(check) or (expected_final_bundle_digest and claimed != expected_final_bundle_digest): findings.append("bundle_digest_mismatch")
        entries = manifest.get("files", []); names = [e.get("relative_filename") for e in entries]
        if len(names) != len(set(names)) or set(names)|{"bundle_manifest.json"} != actual: findings.append("exact_final_manifest_membership_mismatch")
        for entry in entries:
            name = str(entry.get("relative_filename", "")); path = root/name
            if Path(name).name != name or path.is_symlink(): findings.append("manifest_path_rejected:"+name); continue
            raw = path.read_bytes()
            if len(raw) != entry.get("size_bytes") or _raw_sha(raw) != entry.get("sha256"): findings.append("manifest_file_mismatch:"+name)
        content = json.loads((root/"content_manifest.json").read_text()); ccheck = dict(content); cdigest = ccheck.pop("content_manifest_digest", None)
        if cdigest != _sha(ccheck): findings.append("content_manifest_digest_mismatch")
        for entry in content.get("files", []):
            raw=(root/entry["relative_filename"]).read_bytes()
            if len(raw)!=entry["size_bytes"] or _raw_sha(raw)!=entry["sha256"]: findings.append("content_manifest_file_mismatch")
        receipt=json.loads((root/"runtime_receipt.json").read_text())
        if receipt.get("digest")!=digest_record(receipt) or receipt.get("content_manifest_digest")!=cdigest: findings.append("runtime_receipt_invalid")
        for path in root.glob("*.json"):
            if path.name not in ("bundle_manifest.json","content_manifest.json","runtime_receipt.json","summary.json"): records[path.stem]=json.loads(path.read_text())
    except Exception as exc: findings.append("bundle_decode_failed:"+type(exc).__name__)
    if expected_execution_bundle_digest and records.get("expected_execution_bundle_digest") != expected_execution_bundle_digest: findings.append("execution_bundle_digest_mismatch")
    embedded = _dict(records.get("embedded_execution_records")); runtime = _dict(records.get("runtime_result")); history = records.get("rollback_intent_history", [])
    if _dict(embedded.get("runtime_result")).get("status") != "host_local_diagnostic_execution_completed" or _dict(embedded.get("transaction_records")).get("closure_report", {}).get("lifecycle_status") != "local_effect_lifecycle_rollback_pending": findings.append("embedded_execution_invalid")
    previous=""
    for state in history:
        if state.get("digest")!=digest_record(state) or state.get("previous_state_digest")!=previous: findings.append("intent_chain_invalid")
        previous=str(state.get("digest", ""))
    if tuple(x.get("state") for x in history) != ("prepared","invocation_committed","rollback_returned","observation_persisted","finalized"): findings.append("intent_state_sequence_invalid")
    findings += HostLocalDiagnosticRollbackRuntimeCoordinator()._rollback_evidence_findings(_dict(records.get("rollback_records")))
    for name, validator in (("updated_transaction_ledger",validate_local_effect_transaction_ledger),("updated_lifecycle_report",validate_local_effect_transaction_lifecycle_report)):
        validation=validator(_dict(records.get(name))); findings.extend(name+":"+x for x in validation.findings)
    if _dict(records.get("updated_lifecycle_report")).get("lifecycle_status") != "local_effect_lifecycle_complete_with_rollback": findings.append("updated_lifecycle_not_complete")
    required=("historical_diagnostic_write","rollback_invoked_historically","exact_diagnostic_rollback_authorized")
    if any(runtime.get(x) is not True for x in required) or any(runtime.get(x) is not False for x in FORBIDDEN_FLAGS): findings.append("runtime_flags_invalid")
    if runtime.get("rollback_invoked_by_current_coordinator") == runtime.get("prior_invocation_reconciled"): findings.append("direct_reconciled_posture_invalid")
    status="host_local_diagnostic_rollback_completed" if not findings else "host_local_diagnostic_rollback_bundle_invalid"
    return RollbackOutcome(status, tuple(sorted(set(findings))), records, str(root), 0, True)


def validate_live_rollback_postcondition(bundle_root: str | Path, *, expected_final_bundle_digest: str | None = None) -> RollbackOutcome:
    loaded=validate_persisted_rollback_bundle(bundle_root,expected_final_bundle_digest=expected_final_bundle_digest); findings=list(loaded.findings)
    if not findings: findings.extend(_live_findings(_dict(loaded.records["embedded_execution_records"]),after=True))
    return RollbackOutcome("host_local_diagnostic_rollback_live_postcondition_valid" if not findings else "host_local_diagnostic_rollback_live_postcondition_invalid",tuple(sorted(set(findings))),loaded.records,loaded.bundle_root,0,True)
