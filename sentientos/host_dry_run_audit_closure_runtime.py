"""Replay-safe metadata-only closure over persisted host dry-run runtime bundles."""
from __future__ import annotations
import contextlib, hashlib, json, os, shutil, tempfile, time, threading
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from sentientos.dry_run_audit_closure import (
    DryRunAuditClosureWingRecords, build_dry_run_audit_closure_wing,
    dry_run_audit_closure_digest, validate_dry_run_audit_closure_chain,
    validate_dry_run_audit_closure_receipt, validate_dry_run_closure_bundle,
    validate_dry_run_effect_verification, validate_dry_run_postcondition_verification,
    validate_dry_run_rollback_rehearsal,
)
from sentientos.host_dry_run_execution_runtime import (
    NO_REAL_EFFECT as SOURCE_NO_REAL_EFFECT, HostDryRunExecutionRuntimeCoordinator,
    HostDryRunExecutionEvaluation, validate_persisted_evaluation_bundle,
)
from sentientos.dry_run_execution_harness import validate_dry_run_execution_receipt
from sentientos.world_state_board import WorldStateSourceKind, digest as world_digest

SCHEMA_VERSION = "host_dry_run_audit_closure_runtime.v2"
LEGACY_SCHEMA_VERSION = "host_dry_run_audit_closure_runtime.v1"
NO_REAL_EFFECT = {**SOURCE_NO_REAL_EFFECT, "metadata_only": True, "simulation_only": True, "production_audit_receipt_created": False, "real_effect_receipt_created": False, "real_postcondition_check_performed": False, "real_rollback_performed": False}
_LOCKS: dict[str, threading.Lock] = {}

def _canon(o: Any) -> str: return json.dumps(o, sort_keys=True, separators=(",", ":"), default=str)
def _sha(o: Any) -> str: return "sha256:" + hashlib.sha256(_canon(o).encode()).hexdigest()
def _file_sha(raw: bytes) -> str: return "sha256:" + hashlib.sha256(raw).hexdigest()
def _id(prefix: str, o: Any) -> str: return prefix + hashlib.sha256(_canon(o).encode()).hexdigest()[:24]
def _payload(o: Any) -> dict[str, Any]:
    if o is None: return {}
    if hasattr(o, "to_dict"): return dict(o.to_dict())
    if hasattr(o, "__dataclass_fields__"): return asdict(o)
    return dict(o)
def _semantic_payload(o: Any) -> dict[str, Any]:
    p=_payload(o); p.pop("digest", None); p.pop("created_at", None); p.pop("observed_at", None); return p
def digest_record(o: Any) -> str: return _sha(_semantic_payload(o))

@dataclass(frozen=True)
class HostDryRunAuditClosureBudget:
    max_file_count: int = 48; max_artifact_size: int = 524288; max_bundle_size: int = 2097152
    def to_dict(self) -> dict[str, Any]: return asdict(self)
@dataclass(frozen=True)
class HostDryRunAuditClosureSourceRef:
    ref_id: str; digest: str; kind: str; size: int; required: bool = True
    def to_dict(self) -> dict[str, Any]: return asdict(self)
@dataclass(frozen=True)
class HostDryRunAuditClosureRequest:
    request_id: str; digest: str; correlation_id: str; source_runtime_request_id: str; source_runtime_request_digest: str; source_runtime_receipt_id: str; source_runtime_receipt_digest: str; source_bundle_digest: str; source_bundle_root: str; created_at: str = "1970-01-01T00:00:00+00:00"; schema_version: str = SCHEMA_VERSION; metadata_only: bool = True; simulation_only: bool = True
    def to_dict(self) -> dict[str, Any]: return asdict(self)
@dataclass(frozen=True)
class HostDryRunAuditClosurePlan:
    plan_id: str; digest: str; request_id: str; request_digest: str; source_refs: tuple[HostDryRunAuditClosureSourceRef, ...]; blocked_actions: tuple[str, ...]; schema_version: str = SCHEMA_VERSION; metadata_only: bool = True; simulation_only: bool = True
    def to_dict(self) -> dict[str, Any]: return asdict(self)
@dataclass(frozen=True)
class HostDryRunAuditClosureRuntimeReceipt:
    receipt_id: str; digest: str; posture: str; request_id: str; request_digest: str; plan_id: str; plan_digest: str; source_runtime_receipt_id: str; source_runtime_receipt_digest: str; dry_run_receipt_id: str; dry_run_receipt_digest: str; effect_verification_id: str; effect_verification_digest: str; postcondition_verification_id: str; postcondition_verification_digest: str; rollback_rehearsal_id: str; rollback_rehearsal_digest: str; audit_closure_receipt_id: str; audit_closure_receipt_digest: str; closure_bundle_id: str; closure_bundle_digest: str; content_manifest_digest: str = ""; schema_version: str = SCHEMA_VERSION; metadata_only: bool = True; simulation_only: bool = True; dry_run_executed: bool = True; no_real_effect: Mapping[str, bool] | None = None
    def to_dict(self) -> dict[str, Any]:
        d=asdict(self); d["no_real_effect"] = dict(self.no_real_effect or NO_REAL_EFFECT); return d
@dataclass(frozen=True)
class HostDryRunAuditClosureEvaluation:
    status: str; findings: tuple[str, ...]; request: HostDryRunAuditClosureRequest | None; source_manifest: Mapping[str, Any] | None; source_bundle_reference: Mapping[str, Any] | None; plan: HostDryRunAuditClosurePlan | None; effect_verification: Mapping[str, Any] | None; postcondition_verification: Mapping[str, Any] | None; rollback_rehearsal: Mapping[str, Any] | None; audit_closure_receipt: Mapping[str, Any] | None; closure_bundle: Mapping[str, Any] | None; source_dry_run_receipt: Mapping[str, Any] | None; validation_findings: Mapping[str, Any] | None; runtime_receipt: HostDryRunAuditClosureRuntimeReceipt | None; persisted: bool = False; replayed: bool = False; builder_call_count: int = 0
    def to_dict(self) -> dict[str, Any]: return asdict(self)
@dataclass(frozen=True)
class HostDryRunAuditClosureRuntimeSummary:
    summary_id: str; status: str; latest_request_id: str = ""; latest_receipt_id: str = ""; metadata_only: bool = True; simulation_only: bool = True
    def to_dict(self) -> dict[str, Any]: return asdict(self)
@dataclass(frozen=True)
class HostDryRunAuditClosureRuntimeValidationResult:
    ok: bool; findings: tuple[str, ...]
    def to_dict(self) -> dict[str, Any]: return asdict(self)
@dataclass(frozen=True)
class HostDryRunAuditClosurePersistedBundleValidation:
    ok: bool; findings: tuple[str, ...]; evaluation: HostDryRunAuditClosureEvaluation | None = None; final_bundle_digest: str = ""; content_manifest_digest: str = ""
    def to_dict(self) -> dict[str, Any]: return {"ok": self.ok, "findings": self.findings, "final_bundle_digest": self.final_bundle_digest, "content_manifest_digest": self.content_manifest_digest, "evaluation": self.evaluation.to_dict() if self.evaluation else None}


CLOSURE_CONTENT_FILES = {"runtime_request.json", "source_manifest.json", "source_bundle_reference.json", "source_dry_run_receipt.json", "runtime_plan.json", "dry_run_effect_verification.json", "simulated_postcondition_verification.json", "simulated_rollback_rehearsal.json", "dry_run_audit_closure_receipt.json", "dry_run_closure_bundle.json", "validation_findings.json", "summary.json", "README.md"}
CLOSURE_FINAL_FILES = CLOSURE_CONTENT_FILES | {"content_manifest.json", "runtime_receipt.json"}

def _safe_bundle_root(path: str | Path) -> tuple[Path | None, list[str]]:
    original=Path(path); f=[]
    if original.is_symlink(): f.append("symlink_root_rejected")
    root=original.resolve()
    if not root.is_dir(): f.append("persisted_closure_bundle_root_required")
    return (root if not f else None), f

def _read_manifest(bundle: Path, name: str, kind: str, digest_key: str, required: set[str]) -> tuple[dict[str, Any], list[str]]:
    f=[]
    try: manifest=json.loads((bundle/name).read_text(encoding="utf-8"))
    except Exception: return {}, [name.replace('.json','') + "_unreadable"]
    entries=manifest.get("files", []); seen=[]
    if manifest.get("artifact_kind") != kind: f.append(name.replace('.json','') + "_artifact_kind_mismatch")
    for e in entries:
        rel=str(e.get("relative_filename", "")); seen.append(rel); target=bundle/rel
        if rel in {"", name} or target.is_symlink() or rel != Path(rel).name or ".." in Path(rel).parts:
            f.append("manifest_path_rejected:" + rel); continue
        try: target.resolve().relative_to(bundle)
        except Exception: f.append("manifest_path_escape:" + rel); continue
        if not target.exists(): f.append("manifested_file_missing:" + rel); continue
        raw=target.read_bytes()
        if len(raw) != int(e.get("size", -1)): f.append("manifest_size_mismatch:" + rel)
        if _file_sha(raw) != e.get("digest"): f.append("manifest_digest_mismatch:" + rel)
    if len(seen) != len(set(seen)): f.append("duplicate_manifest_entry")
    if set(seen) != required:
        for missing in sorted(required-set(seen)): f.append("required_artifact_omitted:" + missing)
        for extra in sorted(set(seen)-required): f.append("unexpected_manifested_artifact:" + extra)
    disk={x.name for x in bundle.iterdir() if x.is_file() and not x.name.startswith('.')}
    for missing in sorted(required-disk): f.append("required_artifact_missing:" + missing)
    known_bundle_files = CLOSURE_FINAL_FILES | {"final_bundle_manifest.json"} | {"content_manifest.json"}
    for extra in sorted(disk-known_bundle_files):
        if extra.endswith('.json'): f.append("unexpected_unmanifested_semantic_artifact:" + extra)
    if manifest.get(digest_key) != _sha({"files": entries, "artifact_kind": kind}): f.append(name.replace('.json','') + "_digest_mismatch")
    return manifest, f

def validate_persisted_closure_bundle(bundle_root: str | Path, *, expected_final_digest: str | None = None, expected_request_id: str | None = None) -> HostDryRunAuditClosurePersistedBundleValidation:
    bundle, f = _safe_bundle_root(bundle_root)
    if bundle is None: return HostDryRunAuditClosurePersistedBundleValidation(False, tuple(sorted(set(f))))
    content, cf = _read_manifest(bundle, "content_manifest.json", "host_dry_run_audit_closure_runtime_content_manifest", "content_manifest_digest", CLOSURE_CONTENT_FILES)
    final, ff = _read_manifest(bundle, "final_bundle_manifest.json", "host_dry_run_audit_closure_runtime_final_bundle_manifest", "final_bundle_digest", CLOSURE_FINAL_FILES)
    f += cf + ff
    # Strict v2 replay rejects legacy v1 or bundles without the embedded source receipt.
    for mf in (content, final):
        if mf.get("schema_version") == LEGACY_SCHEMA_VERSION: f.append("legacy_v1_closure_bundle_rejected")
        elif mf.get("schema_version") != SCHEMA_VERSION: f.append("closure_bundle_schema_version_mismatch")
    if not (bundle/"source_dry_run_receipt.json").exists(): f.append("embedded_source_dry_run_receipt_required")
    try: ev=HostDryRunAuditClosureRuntimeCoordinator()._evaluation_from_bundle(bundle)
    except Exception as exc: return HostDryRunAuditClosurePersistedBundleValidation(False, tuple(sorted(set(f+["closure_bundle_decode_failed:"+type(exc).__name__]))), None, str(final.get("final_bundle_digest", "")), str(content.get("content_manifest_digest", "")))
    f += list(validate_evaluation(ev).findings)
    rr=_payload(ev.runtime_receipt)
    if rr.get("content_manifest_digest") != content.get("content_manifest_digest"): f.append("runtime_receipt_content_manifest_digest_mismatch")
    if expected_final_digest and final.get("final_bundle_digest") != expected_final_digest: f.append("parent_final_manifest_digest_mismatch")
    if expected_request_id and (not ev.request or ev.request.request_id != expected_request_id): f.append("parent_request_id_mismatch")
    if ev.request and ev.plan and ev.plan.request_digest != ev.request.digest: f.append("plan_request_digest_mismatch")
    if ev.runtime_receipt and ev.request and rr.get("request_digest") != ev.request.digest: f.append("runtime_receipt_request_digest_mismatch")
    if ev.runtime_receipt and ev.plan and rr.get("plan_digest") != ev.plan.digest: f.append("runtime_receipt_plan_digest_mismatch")
    if ev.runtime_receipt:
        pairs=(("effect_verification", ev.effect_verification), ("postcondition_verification", ev.postcondition_verification), ("rollback_rehearsal", ev.rollback_rehearsal), ("audit_closure_receipt", ev.audit_closure_receipt), ("closure_bundle", ev.closure_bundle))
        for name,obj in pairs:
            if obj and rr.get(name+"_digest") != obj.get("digest"): f.append("runtime_receipt_"+name+"_digest_mismatch")
    if ev.effect_verification and ev.postcondition_verification and ev.rollback_rehearsal and ev.audit_closure_receipt and ev.closure_bundle:
        source_receipt=ev.source_dry_run_receipt or {}
        recv=validate_dry_run_execution_receipt(source_receipt); f += ["source_receipt:" + x for x in recv.findings]
        if source_receipt.get("receipt_id") != rr.get("dry_run_receipt_id") or source_receipt.get("digest") != rr.get("dry_run_receipt_digest"): f.append("runtime_receipt_source_dry_run_receipt_parent_mismatch")
        chain=validate_dry_run_audit_closure_chain(source_receipt, ev.effect_verification, ev.postcondition_verification, ev.rollback_rehearsal, ev.audit_closure_receipt, ev.closure_bundle)
        f += list(chain.findings)
    return HostDryRunAuditClosurePersistedBundleValidation(not f, tuple(sorted(set(f))), ev if not f else None, str(final.get("final_bundle_digest", "")), str(content.get("content_manifest_digest", "")))

def _blocked(findings: Sequence[str], req: HostDryRunAuditClosureRequest | None = None, plan: HostDryRunAuditClosurePlan | None = None, source_manifest: Mapping[str, Any] | None = None) -> HostDryRunAuditClosureEvaluation:
    return HostDryRunAuditClosureEvaluation("blocked_host_dry_run_audit_closure_runtime", tuple(sorted(set(findings))), req, source_manifest, None, plan, None, None, None, None, None, None, {"findings": tuple(sorted(set(findings)))}, None)

class HostDryRunAuditClosureRuntimeCoordinator:
    def __init__(self, *, runtime_state_root: str | Path | None = None, clock: Any | None = None, budget: HostDryRunAuditClosureBudget | None = None) -> None:
        self.runtime_state_root=Path(runtime_state_root or "/tmp/host_dry_run_audit_closure_runtime_state").resolve(); self.clock=clock or (lambda:"1970-01-01T00:00:00+00:00"); self.budget=budget or HostDryRunAuditClosureBudget(); self.builder_call_count=0
    @contextlib.contextmanager
    def _fs_lock(self, root: Path) -> Iterator[None]:
        root.mkdir(parents=True, exist_ok=True); key=str(root.resolve()); lock=_LOCKS.setdefault(key, threading.Lock())
        with lock:
            lock_path=root/".host_dry_run_audit_closure_runtime.lock"; fd=-1
            for _ in range(200):
                try: fd=os.open(lock_path, os.O_CREAT|os.O_EXCL|os.O_WRONLY); break
                except FileExistsError: time.sleep(0.01)
            if fd < 0: raise RuntimeError("host_dry_run_audit_closure_runtime_lock_timeout")
            try: os.write(fd, str(os.getpid()).encode()); yield
            finally:
                os.close(fd)
                with contextlib.suppress(FileNotFoundError): lock_path.unlink()
    def _read_source_bundle(self, bundle_root: str | Path) -> tuple[HostDryRunExecutionEvaluation | None, dict[str, Any], list[str]]:
        f: list[str]=[]; source_validation=validate_persisted_evaluation_bundle(bundle_root)
        if not source_validation.ok or source_validation.evaluation is None: return None, {}, ["source_artifact_custody_mismatch" if "manifest_digest_mismatch" in x else "source:" + x for x in source_validation.findings]
        bundle=Path(bundle_root).resolve(); ev=source_validation.evaluation
        mf_path=bundle/"bundle_manifest.json"
        try: manifest=json.loads(mf_path.read_text(encoding="utf-8")); entries=manifest.get("files", [])
        except Exception: return ev, {}, ["source_final_bundle_manifest_unreadable"]
        if len(entries) > self.budget.max_file_count: f.append("source_bundle_file_count_exceeded")
        for e in entries:
            rel=str(e.get("relative_filename", ""))
            if "/" in rel or ".." in Path(rel).parts or (bundle/rel).resolve().parent != bundle: f.append("source_bundle_traversal_or_escape:" + rel); continue
            raw=(bundle/rel).read_bytes()
            if len(raw) > self.budget.max_artifact_size: f.append("source_artifact_size_exceeded:" + rel)
            if len(raw) != int(e.get("size", -1)) or _file_sha(raw) != e.get("digest"): f.append("source_artifact_custody_mismatch:" + rel)
            if rel.endswith(".json"):
                try: json.loads(raw.decode())
                except Exception: f.append("source_artifact_json_invalid:" + rel)
        if manifest.get("bundle_digest") != _sha({"files": entries, "artifact_kind": "host_dry_run_execution_runtime_bundle_manifest"}): f.append("source_final_bundle_manifest_digest_mismatch")
        vr=validate_persisted_evaluation_bundle(bundle); f.extend("source:" + x for x in vr.findings)
        s=summarize_source(ev)
        if ev.status != "dry_run_runtime_simulated": f.append("source_runtime_not_successful")
        if not s.get("dry_run_executed"): f.append("source_dry_run_not_executed")
        for k,expected in SOURCE_NO_REAL_EFFECT.items():
            if s.get(k) != expected: f.append("source_forbidden_real_effect_flag:" + k)
        return ev, {"schema_version": SCHEMA_VERSION, "source_bundle_root": str(bundle), "source_bundle_digest": manifest.get("bundle_digest", ""), "files": entries}, f
    def build_request(self, source: HostDryRunExecutionEvaluation, manifest: Mapping[str, Any], *, correlation_id: str | None = None) -> HostDryRunAuditClosureRequest:
        sr=_payload(source.runtime_receipt); rq=_payload(source.request); sem={"source_request": rq.get("digest"), "source_receipt": sr.get("digest"), "bundle": manifest.get("source_bundle_digest"), "correlation": correlation_id or rq.get("correlation_id") or sr.get("receipt_id")}
        req=HostDryRunAuditClosureRequest(_id("hdr_closure_request_", sem), "", str(sem["correlation"]), str(rq.get("request_id", "")), str(rq.get("digest", "")), str(sr.get("receipt_id", "")), str(sr.get("digest", "")), str(manifest.get("source_bundle_digest", "")), str(manifest.get("source_bundle_root", "")), self.clock())
        return replace(req, digest=digest_record(req))
    def plan(self, req: HostDryRunAuditClosureRequest, manifest: Mapping[str, Any]) -> HostDryRunAuditClosurePlan:
        refs=tuple(HostDryRunAuditClosureSourceRef(str(e.get("relative_filename")), str(e.get("digest")), str(e.get("artifact_kind", Path(str(e.get("relative_filename"))).stem)), int(e.get("size", 0))) for e in manifest.get("files", ()))
        plan=HostDryRunAuditClosurePlan(_id("hdr_closure_plan_", {"request": req.digest, "refs": [r.to_dict() for r in refs]}), "", req.request_id, req.digest, refs, tuple(sorted(NO_REAL_EFFECT.keys())))
        return replace(plan, digest=digest_record(plan))
    def evaluate(self, *, dry_run_runtime_bundle_root: str | Path, output_root: str | Path, correlation_id: str | None = None, persist: bool = True) -> HostDryRunAuditClosureEvaluation:
        source, manifest, findings = self._read_source_bundle(dry_run_runtime_bundle_root)
        if source is None or findings: return _blocked(findings, source_manifest=manifest)
        req=self.build_request(source, manifest, correlation_id=correlation_id); plan=self.plan(req, manifest); root_original=Path(output_root)
        if root_original.is_symlink(): return _blocked(("symlink_root_rejected",), req, plan, manifest)
        root=root_original.resolve()
        try:
            root.relative_to(Path.cwd().resolve()); inside_repo=True
        except ValueError:
            inside_repo=False
        if inside_repo: return _blocked(("repository_local_runtime_root_rejected",), req, plan, manifest)
        semantic={"request": req.digest, "source_bundle": req.source_bundle_digest, "source_receipt": req.source_runtime_receipt_digest, "correlation": req.correlation_id}
        with self._fs_lock(root):
            prior=self._load_replay(root, req.correlation_id, semantic)
            if prior is not None:
                if prior.get("conflict"): return _blocked(("semantic_replay_conflict",), req, plan, manifest)
                return validate_persisted_closure_bundle(Path(prior["bundle"]), expected_final_digest=str(prior.get("bundle_digest", ""))).evaluation  # type: ignore[return-value]
            self.builder_call_count += 1
            records=build_dry_run_audit_closure_wing(source.dry_run_receipt or {}, created_at=self.clock())
            validation=validate_closure_records(source, records)
            status="host_dry_run_audit_closure_runtime_closed" if validation.ok else "contradicted_host_dry_run_audit_closure_runtime"
            runtime=HostDryRunAuditClosureRuntimeReceipt(_id("hdr_closure_receipt_", {"request": req.digest, "bundle": records.closure_bundle.digest}), "", status, req.request_id, req.digest, plan.plan_id, plan.digest, req.source_runtime_receipt_id, req.source_runtime_receipt_digest, str((source.dry_run_receipt or {}).get("receipt_id", "")), str((source.dry_run_receipt or {}).get("digest", "")), records.effect_verification.verification_id, records.effect_verification.digest, records.postcondition_verification.verification_id, records.postcondition_verification.digest, records.rollback_rehearsal.rehearsal_id, records.rollback_rehearsal.digest, records.audit_closure_receipt.receipt_id, records.audit_closure_receipt.digest, records.closure_bundle.bundle_id, records.closure_bundle.digest, no_real_effect=NO_REAL_EFFECT)
            runtime=replace(runtime, digest=digest_record(runtime))
            ev=HostDryRunAuditClosureEvaluation(status, validation.findings, req, manifest, {"source_bundle_root": req.source_bundle_root, "source_bundle_digest": req.source_bundle_digest}, plan, records.effect_verification.to_dict(), records.postcondition_verification.to_dict(), records.rollback_rehearsal.to_dict(), records.audit_closure_receipt.to_dict(), records.closure_bundle.to_dict(), dict(source.dry_run_receipt or {}), validation.to_dict(), runtime, builder_call_count=self.builder_call_count)
            if persist and validation.ok: ev=replace(ev, persisted=self._persist(root, ev, semantic))
            return ev
    def _manifest(self, bundle: Path, *, final: bool=False) -> dict[str, Any]:
        skip={"final_bundle_manifest.json"} if final else {"runtime_receipt.json", "final_bundle_manifest.json"}; files=[]
        for path in sorted(p for p in bundle.iterdir() if p.is_file() and p.name not in skip and not p.name.startswith(".")):
            raw=path.read_bytes(); files.append({"relative_filename": path.name, "size": len(raw), "digest": _file_sha(raw), "artifact_kind": path.stem, "schema_version": SCHEMA_VERSION})
        kind="host_dry_run_audit_closure_runtime_final_bundle_manifest" if final else "host_dry_run_audit_closure_runtime_content_manifest"; key="final_bundle_digest" if final else "content_manifest_digest"
        return {"schema_version": SCHEMA_VERSION, "artifact_kind": kind, "files": files, key: _sha({"files": files, "artifact_kind": kind})}
    def _persist(self, root: Path, ev: HostDryRunAuditClosureEvaluation, semantic: Mapping[str, Any]) -> bool:
        if Path(root).is_symlink(): raise ValueError("symlink_root_rejected")
        root.mkdir(parents=True, exist_ok=True); assert ev.request and ev.runtime_receipt
        bundle=root/ev.request.request_id; tmp=Path(tempfile.mkdtemp(prefix=bundle.name+".", dir=str(root)))
        files={"runtime_request.json": ev.request.to_dict(), "source_manifest.json": ev.source_manifest, "source_bundle_reference.json": ev.source_bundle_reference, "source_dry_run_receipt.json": ev.source_dry_run_receipt, "runtime_plan.json": ev.plan.to_dict() if ev.plan else None, "dry_run_effect_verification.json": ev.effect_verification, "simulated_postcondition_verification.json": ev.postcondition_verification, "simulated_rollback_rehearsal.json": ev.rollback_rehearsal, "dry_run_audit_closure_receipt.json": ev.audit_closure_receipt, "dry_run_closure_bundle.json": ev.closure_bundle, "validation_findings.json": ev.validation_findings, "runtime_receipt.json": ev.runtime_receipt.to_dict(), "summary.json": summarize_evaluation(ev), "README.md": render_markdown(ev)}
        for name,val in files.items(): (tmp/name).write_text(json.dumps(val, sort_keys=True, indent=2) if name.endswith('.json') else str(val), encoding='utf-8')
        content=self._manifest(tmp); (tmp/"content_manifest.json").write_text(json.dumps(content, sort_keys=True, indent=2), encoding='utf-8')
        runtime=replace(ev.runtime_receipt, content_manifest_digest=content["content_manifest_digest"]); runtime=replace(runtime, digest=digest_record(runtime)); (tmp/"runtime_receipt.json").write_text(json.dumps(runtime.to_dict(), sort_keys=True, indent=2), encoding='utf-8')
        final=self._manifest(tmp, final=True); (tmp/"final_bundle_manifest.json").write_text(json.dumps(final, sort_keys=True, indent=2), encoding='utf-8')
        if bundle.exists(): shutil.rmtree(bundle)
        os.replace(tmp, bundle)
        latest={"request_id": ev.request.request_id, "request_digest": ev.request.digest, "runtime_receipt_id": runtime.receipt_id, "runtime_receipt_digest": runtime.digest, "bundle_digest": final["final_bundle_digest"], "posture": runtime.posture}
        (root/"latest.json.tmp").write_text(json.dumps(latest, sort_keys=True, indent=2)); os.replace(root/"latest.json.tmp", root/"latest.json")
        idx=root/"replay_index.json"; data=json.loads(idx.read_text()) if idx.exists() else {}; data[ev.request.correlation_id]={**latest, "semantic": json.loads(_canon(semantic))}; (root/"replay_index.json.tmp").write_text(json.dumps(data, sort_keys=True, indent=2)); os.replace(root/"replay_index.json.tmp", idx); return True
    def _load_replay(self, root: Path, correlation_id: str, semantic: Mapping[str, Any]) -> Mapping[str, Any] | None:
        idx=root/"replay_index.json"
        if not idx.exists(): return None
        try: data=json.loads(idx.read_text()); prior=data.get(correlation_id)
        except Exception: return {"conflict": True}
        if not prior: return None
        if prior.get("semantic") != json.loads(_canon(semantic)):
            prior_sem=dict(prior.get("semantic", {})); new_sem=dict(json.loads(_canon(semantic)))
            prior_sem.pop("source_bundle", None); new_sem.pop("source_bundle", None)
            if prior_sem != new_sem: return {"conflict": True}
        bundle=root/str(prior.get("request_id", ""))
        try:
            manifest=json.loads((bundle/"final_bundle_manifest.json").read_text()); entries=manifest.get("files", [])
            if manifest.get("final_bundle_digest") != _sha({"files": entries, "artifact_kind": "host_dry_run_audit_closure_runtime_final_bundle_manifest"}) or manifest.get("final_bundle_digest") != prior.get("bundle_digest"): return {"conflict": True}
            for e in entries:
                rel=str(e.get("relative_filename")); raw=(bundle/rel).read_bytes()
                if "/" in rel or ".." in Path(rel).parts or len(raw) != int(e.get("size", -1)) or _file_sha(raw) != e.get("digest"): return {"conflict": True}
                if rel.endswith(".json"): json.loads(raw.decode())
        except Exception: return {"conflict": True}
        v=validate_persisted_closure_bundle(bundle, expected_final_digest=str(prior.get("bundle_digest", "")), expected_request_id=str(prior.get("request_id", "")))
        if not v.ok: return {"conflict": True}
        return {"bundle": str(bundle), "bundle_digest": v.final_bundle_digest}
    def _evaluation_from_bundle(self, bundle: Path) -> HostDryRunAuditClosureEvaluation:
        def load(n: str) -> Any: return json.loads((bundle/n).read_text())
        req=HostDryRunAuditClosureRequest(**load("runtime_request.json")); pd=load("runtime_plan.json"); pd["source_refs"]=tuple(HostDryRunAuditClosureSourceRef(**r) for r in pd.get("source_refs", ())); plan=HostDryRunAuditClosurePlan(**pd); runtime=HostDryRunAuditClosureRuntimeReceipt(**load("runtime_receipt.json"))
        return HostDryRunAuditClosureEvaluation(runtime.posture, tuple(load("validation_findings.json").get("findings", ())), req, load("source_manifest.json"), load("source_bundle_reference.json"), plan, load("dry_run_effect_verification.json"), load("simulated_postcondition_verification.json"), load("simulated_rollback_rehearsal.json"), load("dry_run_audit_closure_receipt.json"), load("dry_run_closure_bundle.json"), load("source_dry_run_receipt.json"), load("validation_findings.json"), runtime, True, True, self.builder_call_count)

def _with_flags(o: Any) -> dict[str, Any]:
    p=_payload(o); p.update(NO_REAL_EFFECT); return p

def summarize_source(ev: HostDryRunExecutionEvaluation) -> dict[str, Any]:
    s={"dry_run_executed": bool((ev.dry_run_receipt or {}).get("dry_run_executed", False)), "simulation_only": bool(_payload(ev.runtime_receipt).get("simulation_only", False))}
    for k,v in SOURCE_NO_REAL_EFFECT.items(): s[k]=bool((ev.dry_run_receipt or {}).get(k, _payload(ev.runtime_receipt).get("no_real_effect", {}).get(k, False)))
    return s

def validate_closure_records(source: HostDryRunExecutionEvaluation, records: DryRunAuditClosureWingRecords) -> HostDryRunAuditClosureRuntimeValidationResult:
    f=[]; receipt=source.dry_run_receipt or {}
    if not receipt: f.append("dry_run_receipt_required")
    for x in validate_dry_run_effect_verification(records.effect_verification).findings: f.append("effect:" + x)
    for x in validate_dry_run_postcondition_verification(records.postcondition_verification).findings: f.append("postcondition:" + x)
    for x in validate_dry_run_rollback_rehearsal(records.rollback_rehearsal).findings: f.append("rollback:" + x)
    for x in validate_dry_run_audit_closure_receipt(records.audit_closure_receipt).findings: f.append("audit:" + x)
    for x in validate_dry_run_closure_bundle(records.closure_bundle).findings: f.append("bundle:" + x)
    recv=validate_dry_run_execution_receipt(receipt); f += ["source_receipt:" + x for x in recv.findings]
    ch=validate_dry_run_audit_closure_chain(receipt, *records); f.extend(ch.findings)
    return HostDryRunAuditClosureRuntimeValidationResult(not f, tuple(sorted(set(f))))

def validate_evaluation(ev: HostDryRunAuditClosureEvaluation) -> HostDryRunAuditClosureRuntimeValidationResult:
    f=list(ev.findings)
    if ev.request and ev.request.digest != digest_record(ev.request): f.append("runtime_request_digest_mismatch")
    if ev.plan and ev.plan.digest != digest_record(ev.plan): f.append("runtime_plan_digest_mismatch")
    if ev.runtime_receipt and ev.runtime_receipt.digest != digest_record(ev.runtime_receipt): f.append("runtime_receipt_digest_mismatch")
    for k,v in NO_REAL_EFFECT.items():
        for p in (ev.effect_verification, ev.postcondition_verification, ev.rollback_rehearsal, ev.audit_closure_receipt, ev.closure_bundle, ev.source_dry_run_receipt, _payload(ev.runtime_receipt)):
            if p and k in p and p.get(k) != v: f.append("forbidden_real_effect_flag:" + k)
    return HostDryRunAuditClosureRuntimeValidationResult(not f, tuple(sorted(set(f))))

def summarize_evaluation(ev: HostDryRunAuditClosureEvaluation) -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "status": ev.status, "summary_id": _id("hdr_closure_summary_", {"request": ev.request.digest if ev.request else "", "status": ev.status}), "latest_request_id": ev.request.request_id if ev.request else "", "latest_receipt_id": ev.runtime_receipt.receipt_id if ev.runtime_receipt else "", "source_bundle_digest": ev.request.source_bundle_digest if ev.request else "", **NO_REAL_EFFECT}

def render_markdown(ev: HostDryRunAuditClosureEvaluation) -> str:
    s=summarize_evaluation(ev); return "# Host Dry-Run Audit Closure Runtime\n\n" + "\n".join(f"- {k}: {v}" for k,v in sorted(s.items())) + "\n"

def world_state_records(ev: HostDryRunAuditClosureEvaluation, *, observed_at: str = "1970-01-01T00:00:00+00:00") -> list[dict[str, Any]]:
    items=[("review", "host_dry_run_audit_closure_runtime_request", ev.request.to_dict() if ev.request else None), ("review", "host_dry_run_audit_closure_effect_verification", ev.effect_verification), ("review", "host_dry_run_audit_closure_postcondition_verification", ev.postcondition_verification), ("review", "host_dry_run_audit_closure_rollback_rehearsal", ev.rollback_rehearsal), ("review", "host_dry_run_audit_closure_receipt", ev.audit_closure_receipt), ("review", "host_dry_run_audit_closure_bundle", ev.closure_bundle), ("review", "host_dry_run_audit_closure_runtime_receipt", ev.runtime_receipt.to_dict() if ev.runtime_receipt else None)]
    out=[]
    for stage, kind, obj in items:
        if not obj: continue
        p=_payload(obj); p.update(NO_REAL_EFFECT); sid=str(p.get("request_id") or p.get("verification_id") or p.get("rehearsal_id") or p.get("receipt_id") or p.get("bundle_id") or kind)
        out.append({"source_kind": WorldStateSourceKind.FULFILLMENT.value, "schema_version": SCHEMA_VERSION, "observed_at": observed_at, "source_id": f"hdrac:{sid}:{kind}", "subject_id": sid, "subject_kind": kind, "stage": stage, "disposition": ev.status, "evidence_strength": "recorded", "payload": p, "effect_claimed": False, "effect_proven": False, "digest": world_digest(p)})
    return out

def dashboard_projection(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest=""; count=0
    for r in records:
        if not str(r.get("subject_kind", "")).startswith("host_dry_run_audit_closure"): continue
        count+=1; p=_payload(r.get("payload", {})); latest=str(p.get("request_id") or latest)
    return {"read_only": True, "record_count": count, "latest_request_id": latest, **NO_REAL_EFFECT}

def load_latest_evaluation(output_root: str | Path) -> HostDryRunAuditClosureEvaluation | None:
    root=Path(output_root).resolve(); latest=root/"latest.json"
    if not latest.exists(): return None
    data=json.loads(latest.read_text(encoding="utf-8")); v=validate_persisted_closure_bundle(root/str(data.get("request_id")), expected_final_digest=str(data.get("bundle_digest", "")), expected_request_id=str(data.get("request_id", ""))); return v.evaluation if v.ok else None
