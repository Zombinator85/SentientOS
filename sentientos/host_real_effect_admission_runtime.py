"""Replay-safe metadata-only host real-effect admission runtime.

Consumes exact strict-v2 host dry-run audit closure runtime bundles and persists
real-effect implementation-planning admission evidence. This module never
implements, loads, invokes, executes, fulfills, mutates host state, or starts a
control-plane/effect path.
"""
from __future__ import annotations

import contextlib, hashlib, json, os, shutil, tempfile, threading, time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from sentientos.host_dry_run_audit_closure_runtime import (
    SCHEMA_VERSION as CLOSURE_SCHEMA_VERSION,
    HostDryRunAuditClosureEvaluation,
    validate_persisted_closure_bundle,
)
from sentientos.real_effect_admission import (
    ADMISSION_STATUSES,
    RealEffectAdmissionBundle,
    RealEffectCapabilityAdmissionDecision,
    RealEffectCapabilityBlockReceipt,
    RealEffectCapabilityCandidate,
    RealEffectImplementationPlanScaffold,
    build_real_effect_admission_wing,
    real_effect_admission_bundle_digest,
    real_effect_capability_admission_decision_digest,
    real_effect_capability_block_receipt_digest,
    real_effect_capability_candidate_digest,
    real_effect_implementation_plan_scaffold_digest,
    summarize_real_effect_admission_bundle,
    summarize_real_effect_capability_admission_decision,
    summarize_real_effect_capability_block_receipt,
    summarize_real_effect_capability_candidate,
    summarize_real_effect_implementation_plan_scaffold,
    validate_real_effect_admission_bundle,
    validate_real_effect_capability_admission_decision,
    validate_real_effect_capability_block_receipt,
    validate_real_effect_capability_candidate,
    validate_real_effect_implementation_plan_scaffold,
)

SCHEMA_VERSION = "host_real_effect_admission_runtime.v1"
NO_AUTHORITY: dict[str, bool] = {
    "metadata_only": True,
    "admission_runtime_only": True,
    "implementation_not_started": True,
    "authorizes_implementation": False,
    "authorizes_execution": False,
    "backend_loaded": False,
    "backend_invoked": False,
    "real_backend_implemented": False,
    "real_fulfillment_performed": False,
    "real_effect_performed": False,
    "host_mutation_performed": False,
    "control_plane_admission_execution_performed": False,
}
_LOCKS: dict[str, threading.Lock] = {}


def _canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)

def _sha(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canon(value).encode()).hexdigest()

def _file_sha(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()

def _payload(value: Any) -> dict[str, Any]:
    if value is None: return {}
    if hasattr(value, "to_dict"): return dict(value.to_dict())
    if hasattr(value, "__dataclass_fields__"): return asdict(value)
    return dict(value)

def _semantic(value: Any) -> dict[str, Any]:
    p = _payload(value); p.pop("digest", None); p.pop("created_at", None); p.pop("source_bundle_root", None); return p

def digest_record(value: Any) -> str:
    return _sha(_semantic(value))

def _id(prefix: str, value: Any) -> str:
    return prefix + hashlib.sha256(_canon(value).encode()).hexdigest()[:24]

@dataclass(frozen=True)
class HostRealEffectAdmissionRuntimeRequest:
    request_id: str; digest: str; correlation_id: str; source_closure_request_id: str; source_closure_request_digest: str; source_closure_bundle_id: str; source_closure_bundle_digest: str; source_closure_final_manifest_digest: str; source_closure_root: str; admission_domain: str | None = None; requested_implementation_tier: str | None = None; created_at: str = "1970-01-01T00:00:00+00:00"; schema_version: str = SCHEMA_VERSION; metadata_only: bool = True
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostRealEffectAdmissionRuntimePlan:
    plan_id: str; digest: str; request_id: str; request_digest: str; blocked_actions: tuple[str, ...]; source_closure_final_manifest_digest: str; schema_version: str = SCHEMA_VERSION; metadata_only: bool = True; plan_only: bool = True
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostRealEffectAdmissionRuntimeReceipt:
    receipt_id: str; digest: str; runtime_status: str; request_id: str; request_digest: str; plan_id: str; plan_digest: str; candidate_id: str; candidate_digest: str; decision_id: str; decision_digest: str; admission_bundle_id: str; admission_bundle_digest: str; source_closure_final_manifest_digest: str; content_manifest_digest: str = ""; schema_version: str = SCHEMA_VERSION; metadata_only: bool = True; authorizes_implementation: bool = False; authorizes_execution: bool = False; backend_loaded: bool = False; backend_invoked: bool = False; real_fulfillment_performed: bool = False; real_effect_performed: bool = False; host_mutation_performed: bool = False; control_plane_admission_execution_performed: bool = False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostRealEffectAdmissionRuntimeEvaluation:
    status: str; findings: tuple[str, ...]; request: HostRealEffectAdmissionRuntimeRequest | None; plan: HostRealEffectAdmissionRuntimePlan | None; source_closure_reference: Mapping[str, Any] | None; source_closure_bundle: Mapping[str, Any] | None; candidate: Mapping[str, Any] | None; decision: Mapping[str, Any] | None; plan_or_block_receipt: Mapping[str, Any] | None; admission_bundle: Mapping[str, Any] | None; validation_findings: Mapping[str, Any] | None; runtime_receipt: HostRealEffectAdmissionRuntimeReceipt | None; persisted: bool = False; replayed: bool = False; builder_call_count: int = 0
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostRealEffectAdmissionRuntimeValidation:
    ok: bool; findings: tuple[str, ...]; evaluation: HostRealEffectAdmissionRuntimeEvaluation | None = None; final_bundle_digest: str = ""; content_manifest_digest: str = ""
    def to_dict(self) -> dict[str, Any]: return {"ok": self.ok, "findings": self.findings, "final_bundle_digest": self.final_bundle_digest, "content_manifest_digest": self.content_manifest_digest, "evaluation": self.evaluation.to_dict() if self.evaluation else None}

CONTENT_FILES = {"runtime_request.json","runtime_plan.json","source_closure_reference.json","source_dry_run_closure_bundle.json","candidate.json","admission_decision.json","plan_or_block_receipt.json","real_effect_admission_bundle.json","validation_findings.json","summary.json","README.md"}
FINAL_FILES = CONTENT_FILES | {"runtime_receipt.json","content_manifest.json"}
SEMANTIC_FILES = {name for name in FINAL_FILES | {"final_bundle_manifest.json"} if name.endswith((".json", ".md"))}
FORBIDDEN_FALSE_FLAGS = {
    "authorizes_implementation",
    "authorizes_execution",
    "backend_loaded",
    "backend_invoked",
    "real_backend_implemented",
    "real_fulfillment_performed",
    "real_effect_performed",
    "host_mutation_performed",
    "control_plane_admission_execution_performed",
    "fan_pwm_write_performed",
    "thermal_actuation_performed",
    "power_profile_mutation_performed",
    "process_kill_performed",
    "service_restart_performed",
    "package_install_performed",
    "driver_install_performed",
    "file_cleanup_performed",
    "file_delete_performed",
    "network_performed",
    "provider_invocation_performed",
    "prompt_assembly_performed",
    "subprocess_execution_performed",
    "shell_execution_performed",
    "os_backend_invoked",
    "real_effect_receipt_created",
    "real_postcondition_check_performed",
    "real_rollback_performed",
    "production_audit_receipt_created",
}


def _blocked(findings: Sequence[str]) -> HostRealEffectAdmissionRuntimeEvaluation:
    f=tuple(sorted(set(findings)))
    return HostRealEffectAdmissionRuntimeEvaluation("blocked_host_real_effect_admission_runtime", f, None, None, None, None, None, None, None, None, {"findings": f}, None)

class HostRealEffectAdmissionRuntimeCoordinator:
    def __init__(self, *, clock: Any | None = None) -> None:
        self.clock=clock or (lambda:"1970-01-01T00:00:00+00:00"); self.builder_call_count=0
    @contextlib.contextmanager
    def _fs_lock(self, root: Path) -> Iterator[None]:
        root.mkdir(parents=True, exist_ok=True); lock=_LOCKS.setdefault(str(root.resolve()), threading.Lock())
        with lock:
            lp=root/".host_real_effect_admission_runtime.lock"; fd=-1
            for _ in range(200):
                try: fd=os.open(lp, os.O_CREAT|os.O_EXCL|os.O_WRONLY); break
                except FileExistsError: time.sleep(0.01)
            if fd < 0: raise RuntimeError("host_real_effect_admission_runtime_lock_timeout")
            try: os.write(fd, str(os.getpid()).encode()); yield
            finally:
                os.close(fd)
                with contextlib.suppress(FileNotFoundError): lp.unlink()
    def _read_source(self, root: str | Path) -> tuple[HostDryRunAuditClosureEvaluation | None, dict[str, Any], list[str]]:
        v=validate_persisted_closure_bundle(root)
        if not v.ok or v.evaluation is None:
            return None, {"final_manifest_digest": v.final_bundle_digest}, ["source_closure:"+x for x in v.findings]
        ev=v.evaluation; bundle=_payload(ev.closure_bundle)
        f=[]
        if ev.status != "host_dry_run_audit_closure_runtime_closed": f.append("source_closure_not_closed")
        if bundle.get("bundle_status") not in {"dry_run_closure_bundle_ready","dry_run_closure_bundle_ready_with_warnings"}: f.append("source_closure_bundle_not_ready")
        if Path(root).resolve().is_file(): f.append("loose_source_rejected")
        ref={"schema_version": CLOSURE_SCHEMA_VERSION, "source_closure_root": str(Path(root).resolve()), "source_closure_final_manifest_digest": v.final_bundle_digest, "content_manifest_digest": v.content_manifest_digest, "source_closure_request_id": ev.request.request_id if ev.request else "", "source_closure_request_digest": ev.request.digest if ev.request else "", "source_closure_bundle_id": bundle.get("bundle_id", ""), "source_closure_bundle_digest": bundle.get("digest", "")}
        return ev, ref, f
    def build_request(self, source: HostDryRunAuditClosureEvaluation, ref: Mapping[str, Any], *, correlation_id: str | None, admission_domain: str | None, requested_implementation_tier: str | None) -> HostRealEffectAdmissionRuntimeRequest:
        sem={"source_request": ref.get("source_closure_request_digest"), "source_bundle": ref.get("source_closure_bundle_digest"), "final": ref.get("source_closure_final_manifest_digest"), "correlation": correlation_id or ref.get("source_closure_request_id"), "domain": admission_domain, "tier": requested_implementation_tier}
        req=HostRealEffectAdmissionRuntimeRequest(_id("hrea_request_", sem), "", str(sem["correlation"]), str(ref.get("source_closure_request_id","")), str(ref.get("source_closure_request_digest","")), str(ref.get("source_closure_bundle_id","")), str(ref.get("source_closure_bundle_digest","")), str(ref.get("source_closure_final_manifest_digest","")), str(ref.get("source_closure_root","")), admission_domain, requested_implementation_tier, self.clock())
        return replace(req, digest=digest_record(req))
    def plan(self, req: HostRealEffectAdmissionRuntimeRequest) -> HostRealEffectAdmissionRuntimePlan:
        p=HostRealEffectAdmissionRuntimePlan(_id("hrea_plan_", {"request": req.digest}), "", req.request_id, req.digest, tuple(sorted(NO_AUTHORITY)), req.source_closure_final_manifest_digest)
        return replace(p, digest=digest_record(p))
    def evaluate(self, *, closure_bundle_root: str | Path, output_root: str | Path, correlation_id: str | None = None, admission_domain: str | None = None, requested_implementation_tier: str | None = None, persist: bool = True) -> HostRealEffectAdmissionRuntimeEvaluation:
        root=Path(output_root).resolve()
        if correlation_id and not Path(closure_bundle_root).exists():
            replay = self._load_replay_by_correlation(root, correlation_id)
            if replay is not None:
                if replay.get("conflict"): return _blocked(("semantic_replay_conflict",))
                ev=validate_persisted_admission_bundle(Path(str(replay["bundle"])), expected_final_digest=str(replay.get("bundle_digest","")).strip()).evaluation
                if ev is not None: return ev
        src, ref, f = self._read_source(closure_bundle_root)
        if src is None or f: return _blocked(f)
        req=self.build_request(src, ref, correlation_id=correlation_id, admission_domain=admission_domain, requested_implementation_tier=requested_implementation_tier); plan=self.plan(req)
        try: root.relative_to(Path.cwd().resolve()); return _blocked(("repository_local_runtime_root_rejected",))
        except ValueError: pass
        semantic={"correlation": req.correlation_id, "source_request": req.source_closure_request_digest, "source_bundle": req.source_closure_bundle_digest, "final": req.source_closure_final_manifest_digest, "domain": req.admission_domain, "tier": req.requested_implementation_tier}
        with self._fs_lock(root):
            prior=self._load_replay(root, req.correlation_id, semantic)
            if prior is not None:
                if prior.get("conflict"): return _blocked(("semantic_replay_conflict",))
                ev=validate_persisted_admission_bundle(Path(str(prior["bundle"])), expected_final_digest=str(prior.get("bundle_digest",""))).evaluation
                return ev if ev is not None else _blocked(("persisted_replay_invalid",))
            self.builder_call_count += 1
            wing=build_real_effect_admission_wing(src.closure_bundle or {}, admission_domain=admission_domain, requested_implementation_tier=requested_implementation_tier, created_at=self.clock())
            val=validate_runtime_records(wing.candidate, wing.decision, wing.plan_or_block_receipt, wing.admission_bundle)
            status="host_real_effect_admission_runtime_recorded" if val.ok else "contradicted_host_real_effect_admission_runtime"
            receipt=HostRealEffectAdmissionRuntimeReceipt(_id("hrea_receipt_", {"request": req.digest, "bundle": wing.admission_bundle.digest}), "", status, req.request_id, req.digest, plan.plan_id, plan.digest, wing.candidate.candidate_id, wing.candidate.digest, wing.decision.decision_id, wing.decision.digest, wing.admission_bundle.bundle_id, wing.admission_bundle.digest, req.source_closure_final_manifest_digest)
            receipt=replace(receipt, digest=digest_record(receipt))
            ev=HostRealEffectAdmissionRuntimeEvaluation(status, val.findings, req, plan, ref, _payload(src.closure_bundle), wing.candidate.to_dict(), wing.decision.to_dict(), wing.plan_or_block_receipt.to_dict(), wing.admission_bundle.to_dict(), val.to_dict(), receipt, builder_call_count=self.builder_call_count)
            if persist and val.ok: ev=replace(ev, persisted=self._persist(root, ev, semantic))
            return ev
    def _manifest(self, bundle: Path, *, final: bool=False) -> dict[str, Any]:
        skip={"final_bundle_manifest.json"} if final else {"runtime_receipt.json","content_manifest.json","final_bundle_manifest.json"}; files=[]
        for p in sorted(x for x in bundle.iterdir() if x.is_file() and x.name not in skip and not x.name.startswith('.')):
            raw=p.read_bytes(); files.append({"relative_filename": p.name, "size": len(raw), "digest": _file_sha(raw), "artifact_kind": p.stem, "schema_version": SCHEMA_VERSION})
        kind="host_real_effect_admission_runtime_final_manifest" if final else "host_real_effect_admission_runtime_content_manifest"; key="final_bundle_digest" if final else "content_manifest_digest"
        return {"schema_version": SCHEMA_VERSION, "artifact_kind": kind, "files": files, key: _sha({"files": files, "artifact_kind": kind})}
    def _persist(self, root: Path, ev: HostRealEffectAdmissionRuntimeEvaluation, semantic: Mapping[str, Any]) -> bool:
        assert ev.request and ev.runtime_receipt
        root.mkdir(parents=True, exist_ok=True); bundle=root/ev.request.request_id; tmp=Path(tempfile.mkdtemp(prefix=bundle.name+".", dir=str(root)))
        files={"runtime_request.json": ev.request.to_dict(), "runtime_plan.json": ev.plan.to_dict() if ev.plan else None, "source_closure_reference.json": ev.source_closure_reference, "source_dry_run_closure_bundle.json": ev.source_closure_bundle, "candidate.json": ev.candidate, "admission_decision.json": ev.decision, "plan_or_block_receipt.json": ev.plan_or_block_receipt, "real_effect_admission_bundle.json": ev.admission_bundle, "validation_findings.json": ev.validation_findings, "runtime_receipt.json": ev.runtime_receipt.to_dict(), "summary.json": summarize_evaluation(ev), "README.md": render_markdown(ev)}
        for n,v in files.items(): (tmp/n).write_text(json.dumps(v, sort_keys=True, indent=2) if n.endswith('.json') else str(v), encoding='utf-8')
        content=self._manifest(tmp); (tmp/"content_manifest.json").write_text(json.dumps(content, sort_keys=True, indent=2), encoding='utf-8')
        receipt=replace(ev.runtime_receipt, content_manifest_digest=content["content_manifest_digest"]); receipt=replace(receipt, digest=digest_record(receipt)); (tmp/"runtime_receipt.json").write_text(json.dumps(receipt.to_dict(), sort_keys=True, indent=2), encoding='utf-8')
        final=self._manifest(tmp, final=True); (tmp/"final_bundle_manifest.json").write_text(json.dumps(final, sort_keys=True, indent=2), encoding='utf-8')
        if bundle.exists(): shutil.rmtree(bundle)
        os.replace(tmp, bundle)
        latest={"request_id": ev.request.request_id, "request_digest": ev.request.digest, "runtime_receipt_id": receipt.receipt_id, "runtime_receipt_digest": receipt.digest, "bundle_digest": final["final_bundle_digest"], "posture": receipt.runtime_status}
        (root/"latest.json.tmp").write_text(json.dumps(latest, sort_keys=True, indent=2)); os.replace(root/"latest.json.tmp", root/"latest.json")
        idx=root/"replay_index.json"; data=json.loads(idx.read_text()) if idx.exists() else {}; data[ev.request.correlation_id]={**latest, "semantic": json.loads(_canon(semantic))}; (root/"replay_index.json.tmp").write_text(json.dumps(data, sort_keys=True, indent=2)); os.replace(root/"replay_index.json.tmp", idx)
        return True

    def _load_replay_by_correlation(self, root: Path, correlation_id: str) -> Mapping[str, Any] | None:
        idx=root/"replay_index.json"
        if not idx.exists(): return None
        try: prior=json.loads(idx.read_text()).get(correlation_id)
        except Exception: return {"conflict": True}
        if not prior: return None
        bundle=root/str(prior.get("request_id", ""))
        v=validate_persisted_admission_bundle(bundle, expected_final_digest=str(prior.get("bundle_digest","")), expected_request_id=str(prior.get("request_id","")))
        if not v.ok: return {"conflict": True}
        return {"bundle": str(bundle), "bundle_digest": v.final_bundle_digest}
    def _load_replay(self, root: Path, correlation_id: str, semantic: Mapping[str, Any]) -> Mapping[str, Any] | None:
        idx=root/"replay_index.json"
        if not idx.exists(): return None
        try: data=json.loads(idx.read_text()); prior=data.get(correlation_id)
        except Exception: return {"conflict": True}
        if not prior: return None
        if prior.get("semantic") != json.loads(_canon(semantic)): return {"conflict": True}
        bundle=root/str(prior.get("request_id", "")); v=validate_persisted_admission_bundle(bundle, expected_final_digest=str(prior.get("bundle_digest","")), expected_request_id=str(prior.get("request_id","")))
        if not v.ok: return {"conflict": True}
        return {"bundle": str(bundle), "bundle_digest": v.final_bundle_digest}
    def _evaluation_from_bundle(self, bundle: Path) -> HostRealEffectAdmissionRuntimeEvaluation:
        def load(n: str) -> Any: return json.loads((bundle/n).read_text(encoding='utf-8'))
        req=HostRealEffectAdmissionRuntimeRequest(**load("runtime_request.json")); plan=HostRealEffectAdmissionRuntimePlan(**load("runtime_plan.json")); receipt=HostRealEffectAdmissionRuntimeReceipt(**load("runtime_receipt.json"))
        return HostRealEffectAdmissionRuntimeEvaluation(receipt.runtime_status, tuple(load("validation_findings.json").get("findings", ())), req, plan, load("source_closure_reference.json"), load("source_dry_run_closure_bundle.json"), load("candidate.json"), load("admission_decision.json"), load("plan_or_block_receipt.json"), load("real_effect_admission_bundle.json"), load("validation_findings.json"), receipt, True, True, self.builder_call_count)

@dataclass(frozen=True)
class SimpleValidation:
    ok: bool; findings: tuple[str, ...]
    def to_dict(self) -> dict[str, Any]: return asdict(self)

def validate_runtime_records(candidate: Any, decision: Any, plan_or_block: Any, bundle: Any) -> SimpleValidation:
    f=[]
    for prefix,res in (("candidate:", validate_real_effect_capability_candidate(candidate)), ("decision:", validate_real_effect_capability_admission_decision(decision)), ("bundle:", validate_real_effect_admission_bundle(bundle))): f += [prefix+x for x in res.findings]
    p=_payload(plan_or_block)
    if "plan_id" in p: f += ["plan:"+x for x in validate_real_effect_implementation_plan_scaffold(plan_or_block).findings]
    else: f += ["block:"+x for x in validate_real_effect_capability_block_receipt(plan_or_block).findings]
    for obj in (candidate, decision, plan_or_block, bundle):
        p=_payload(obj)
        for k,v in NO_AUTHORITY.items():
            if k in p and p.get(k) != v: f.append("authority_flag_mismatch:"+k)
    return SimpleValidation(not f, tuple(sorted(set(f))))

def validate_evaluation(ev: HostRealEffectAdmissionRuntimeEvaluation) -> SimpleValidation:
    f=list(ev.findings)
    if ev.request and ev.request.digest != digest_record(ev.request): f.append("runtime_request_digest_mismatch")
    if ev.plan and ev.plan.digest != digest_record(ev.plan): f.append("runtime_plan_digest_mismatch")
    if ev.runtime_receipt and ev.runtime_receipt.digest != digest_record(ev.runtime_receipt): f.append("runtime_receipt_digest_mismatch")
    if ev.candidate and ev.decision and ev.plan_or_block_receipt and ev.admission_bundle: f += list(validate_runtime_records(ev.candidate, ev.decision, ev.plan_or_block_receipt, ev.admission_bundle).findings)
    return SimpleValidation(not f, tuple(sorted(set(f))))

def _all_payloads(ev: HostRealEffectAdmissionRuntimeEvaluation) -> tuple[Mapping[str, Any], ...]:
    payloads: list[Mapping[str, Any]] = []
    for value in (ev.request, ev.plan, ev.source_closure_reference, ev.source_closure_bundle, ev.candidate, ev.decision, ev.plan_or_block_receipt, ev.admission_bundle, ev.validation_findings, ev.runtime_receipt):
        if value is None:
            continue
        payloads.append(_payload(value))
    return tuple(payloads)

def _validate_no_authority_flags(ev: HostRealEffectAdmissionRuntimeEvaluation) -> list[str]:
    f: list[str] = []
    for payload in _all_payloads(ev):
        for key in ("metadata_only",):
            if key in payload and payload.get(key) is not True:
                f.append("authority_flag_mismatch:"+key)
        for key in FORBIDDEN_FALSE_FLAGS:
            if key in payload and payload.get(key) is not False:
                f.append("authority_flag_mismatch:"+key)
        if payload.get("implementation_not_started") is False:
            f.append("authority_flag_mismatch:implementation_not_started")
    return f

def _validate_deep_lineage(ev: HostRealEffectAdmissionRuntimeEvaluation) -> list[str]:
    f: list[str] = []
    if not (ev.request and ev.plan and ev.runtime_receipt and ev.source_closure_reference and ev.source_closure_bundle and ev.candidate and ev.decision and ev.plan_or_block_receipt and ev.admission_bundle):
        return ["persisted_semantic_records_missing"]
    req=_payload(ev.request); plan=_payload(ev.plan); receipt=_payload(ev.runtime_receipt)
    ref=dict(ev.source_closure_reference); closure=dict(ev.source_closure_bundle)
    cand=dict(ev.candidate); dec=dict(ev.decision); pob=dict(ev.plan_or_block_receipt); adm=dict(ev.admission_bundle)
    if plan.get("request_id") != req.get("request_id") or plan.get("request_digest") != req.get("digest"): f.append("runtime_request_plan_linkage_mismatch")
    for key in ("source_closure_request_id","source_closure_request_digest","source_closure_bundle_id","source_closure_bundle_digest","source_closure_final_manifest_digest"):
        if req.get(key) != ref.get(key): f.append("source_closure_reference_request_mismatch:"+key)
    if ref.get("source_closure_bundle_id") != closure.get("bundle_id") or ref.get("source_closure_bundle_digest") != closure.get("digest"):
        f.append("embedded_closure_bundle_reference_mismatch")
    if cand.get("source_dry_run_closure_bundle_id") != ref.get("source_closure_bundle_id") or cand.get("source_dry_run_closure_bundle_digest") != ref.get("source_closure_bundle_digest"):
        f.append("candidate_source_closure_mismatch")
    if dec.get("candidate_id") != cand.get("candidate_id") or dec.get("source_dry_run_closure_bundle_id") != cand.get("source_dry_run_closure_bundle_id"):
        f.append("decision_candidate_lineage_mismatch")
    if dec.get("admission_domain") != cand.get("admission_domain") or dec.get("implementation_tier") != cand.get("requested_implementation_tier"):
        f.append("decision_candidate_policy_mismatch")
    if pob.get("candidate_id") != cand.get("candidate_id") or pob.get("decision_id") != dec.get("decision_id") or pob.get("admission_domain") != dec.get("admission_domain"):
        f.append("plan_or_block_lineage_mismatch")
    if "plan_id" in pob and (pob.get("implementation_tier") != dec.get("implementation_tier")):
        f.append("plan_scaffold_tier_mismatch")
    if adm.get("candidate_id") != cand.get("candidate_id") or adm.get("decision_id") != dec.get("decision_id") or adm.get("admission_domain") != dec.get("admission_domain"):
        f.append("admission_bundle_lineage_mismatch")
    eligible=dec.get("admission_status") in {"real_effect_admission_eligible_for_planning","real_effect_admission_eligible_with_conditions"}
    if eligible and ("plan_id" not in pob or adm.get("plan_id") != pob.get("plan_id") or adm.get("block_receipt_id") is not None):
        f.append("eligible_decision_requires_plan_scaffold")
    if not eligible and ("receipt_id" not in pob or adm.get("block_receipt_id") != pob.get("receipt_id") or adm.get("plan_id") is not None):
        f.append("blocked_decision_requires_block_receipt")
    expected_bundle_status=dec.get("admission_status")
    if str(expected_bundle_status).endswith(("blocked","incomplete","contradicted")) and expected_bundle_status in ADMISSION_STATUSES:
        expected_bundle_status=expected_bundle_status
    if adm.get("bundle_status") != expected_bundle_status: f.append("admission_bundle_status_mismatch")
    for name, obj, digest_fn in (("candidate", cand, real_effect_capability_candidate_digest), ("decision", dec, real_effect_capability_admission_decision_digest), ("admission_bundle", adm, real_effect_admission_bundle_digest)):
        if obj.get("digest") != digest_fn(obj): f.append(name+"_digest_mismatch")
    if "plan_id" in pob and pob.get("digest") != real_effect_implementation_plan_scaffold_digest(pob): f.append("plan_digest_mismatch")
    if "receipt_id" in pob and pob.get("digest") != real_effect_capability_block_receipt_digest(pob): f.append("block_receipt_digest_mismatch")
    receipt_pairs={"request": req, "plan": plan, "candidate": cand, "decision": dec, "admission_bundle": adm}
    for prefix, obj in receipt_pairs.items():
        id_key = "bundle_id" if prefix == "admission_bundle" else prefix + "_id"
        if receipt.get(prefix+"_id") != obj.get(id_key) or receipt.get(prefix+"_digest") != obj.get("digest"):
            f.append("runtime_receipt_parent_mismatch:"+prefix)
    if receipt.get("source_closure_final_manifest_digest") != req.get("source_closure_final_manifest_digest"):
        f.append("runtime_receipt_source_final_manifest_digest_mismatch")
    if ev.status != receipt.get("runtime_status") or receipt.get("runtime_status") != "host_real_effect_admission_runtime_recorded":
        f.append("runtime_status_mismatch")
    return f + _validate_no_authority_flags(ev)

def validate_persisted_admission_bundle(bundle_root: str | Path, *, expected_final_digest: str | None = None, expected_request_id: str | None = None) -> HostRealEffectAdmissionRuntimeValidation:
    raw_bundle=Path(bundle_root); f=[]
    if raw_bundle.is_symlink(): f.append("persisted_admission_bundle_root_symlink_rejected")
    if any(part == ".." for part in raw_bundle.parts): f.append("persisted_admission_bundle_traversal_rejected")
    bundle=raw_bundle.resolve()
    if not bundle.is_dir(): return HostRealEffectAdmissionRuntimeValidation(False, tuple(sorted(set(f+["persisted_admission_bundle_root_required"]))))
    with contextlib.suppress(ValueError):
        bundle.relative_to(Path.cwd().resolve()); f.append("repository_local_runtime_root_rejected")
    for child in bundle.iterdir():
        if child.is_file() and child.name.endswith((".json", ".md")) and child.name not in SEMANTIC_FILES:
            f.append("unexpected_unmanifested_semantic_file:"+child.name)
    manifests={}
    for name, kind, key, required in (("content_manifest.json","host_real_effect_admission_runtime_content_manifest","content_manifest_digest",CONTENT_FILES),("final_bundle_manifest.json","host_real_effect_admission_runtime_final_manifest","final_bundle_digest",FINAL_FILES)):
        if (bundle/name).is_symlink(): f.append("manifest_symlink_rejected:"+name); continue
        try: m=json.loads((bundle/name).read_text(encoding='utf-8')); manifests[name]=m
        except Exception: f.append(name.replace('.json','')+"_unreadable"); continue
        entries=m.get("files", [])
        if m.get("schema_version") != SCHEMA_VERSION: f.append(name.replace('.json','')+"_schema_version_mismatch")
        if m.get("artifact_kind") != kind: f.append(name.replace('.json','')+"_artifact_kind_mismatch")
        seen=[]
        for e in entries:
            rel=str(e.get("relative_filename", "")); seen.append(rel); p=bundle/rel
            if seen.count(rel) > 1: f.append("duplicate_manifest_entry:"+rel)
            if rel != Path(rel).name or rel in {"", name}: f.append("manifest_path_rejected:"+rel); continue
            if p.is_symlink(): f.append("manifested_artifact_symlink_rejected:"+rel); continue
            if not p.exists(): f.append("manifested_file_missing:"+rel); continue
            raw=p.read_bytes()
            if len(raw) != int(e.get("size", -1)): f.append("manifest_size_mismatch:"+rel)
            if _file_sha(raw) != e.get("digest"): f.append("manifest_digest_mismatch:"+rel)
            if e.get("schema_version") != SCHEMA_VERSION: f.append("manifest_entry_schema_version_mismatch:"+rel)
            if e.get("artifact_kind") != Path(rel).stem: f.append("manifest_entry_artifact_kind_mismatch:"+rel)
        if set(seen) != required:
            for missing in sorted(required-set(seen)): f.append("required_artifact_omitted:"+missing)
            for extra in sorted(set(seen)-required): f.append("unexpected_manifested_artifact:"+extra)
        if m.get(key) != _sha({"files": entries, "artifact_kind": kind}): f.append(name.replace('.json','')+"_digest_mismatch")
    try: ev=HostRealEffectAdmissionRuntimeCoordinator()._evaluation_from_bundle(bundle)
    except Exception as exc: return HostRealEffectAdmissionRuntimeValidation(False, tuple(sorted(set(f+["admission_bundle_decode_failed:"+type(exc).__name__]))), None, str(manifests.get("final_bundle_manifest.json",{}).get("final_bundle_digest","")), str(manifests.get("content_manifest.json",{}).get("content_manifest_digest","")))
    f += list(validate_evaluation(ev).findings)
    f += _validate_deep_lineage(ev)
    final_digest=str(manifests.get("final_bundle_manifest.json",{}).get("final_bundle_digest","")); content_digest=str(manifests.get("content_manifest.json",{}).get("content_manifest_digest",""))
    if expected_final_digest and final_digest != expected_final_digest: f.append("expected_final_manifest_digest_mismatch")
    if expected_request_id and (not ev.request or ev.request.request_id != expected_request_id): f.append("expected_request_id_mismatch")
    if ev.runtime_receipt and ev.runtime_receipt.content_manifest_digest != content_digest: f.append("runtime_receipt_content_manifest_digest_mismatch")
    return HostRealEffectAdmissionRuntimeValidation(not f, tuple(sorted(set(f))), ev if not f else None, final_digest, content_digest)

def summarize_evaluation(ev: HostRealEffectAdmissionRuntimeEvaluation) -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "status": ev.status, "summary_id": _id("hrea_summary_", {"request": ev.request.digest if ev.request else "", "status": ev.status}), "latest_request_id": ev.request.request_id if ev.request else "", "source_closure_final_manifest_digest": ev.request.source_closure_final_manifest_digest if ev.request else "", "candidate_summary": summarize_real_effect_capability_candidate(ev.candidate or {}), "decision_summary": summarize_real_effect_capability_admission_decision(ev.decision or {}), "plan_scaffold_summary": summarize_real_effect_implementation_plan_scaffold(ev.plan_or_block_receipt or {}) if ev.plan_or_block_receipt and "plan_id" in ev.plan_or_block_receipt else None, "block_receipt_summary": summarize_real_effect_capability_block_receipt(ev.plan_or_block_receipt or {}) if ev.plan_or_block_receipt and "receipt_id" in ev.plan_or_block_receipt else None, "admission_bundle_summary": summarize_real_effect_admission_bundle(ev.admission_bundle or {}), **NO_AUTHORITY}

def render_markdown(ev: HostRealEffectAdmissionRuntimeEvaluation) -> str:
    s=summarize_evaluation(ev); return "# Host Real Effect Admission Runtime\n\n" + "\n".join(f"- {k}: {v}" for k,v in sorted(s.items())) + "\n"

def load_latest_evaluation(output_root: str | Path) -> HostRealEffectAdmissionRuntimeEvaluation | None:
    latest=Path(output_root).resolve()/"latest.json"
    if not latest.exists(): return None
    data=json.loads(latest.read_text(encoding='utf-8')); v=validate_persisted_admission_bundle(latest.parent/str(data.get("request_id","")), expected_final_digest=str(data.get("bundle_digest","")), expected_request_id=str(data.get("request_id","")))
    return v.evaluation if v.ok else None
