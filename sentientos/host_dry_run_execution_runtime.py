# mypy: ignore-errors
"""Host dry-run execution runtime closure.

Simulation-only custody coordinator binding an exact executor-readiness runtime
bundle to the inert dry-run harness. It never loads/invokes a real backend,
requests execution/effect admission, grants fulfillment, mutates host state, or
produces a real effect receipt.
"""
from __future__ import annotations

import hashlib, json, os, shutil, tempfile, threading
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from sentientos.control_plane_kernel import AuthorityClass, ControlActionRequest, LifecyclePhase, get_control_plane_kernel
from sentientos.dry_run_execution_harness import (
    DryRunExecutionBlockReceipt, DryRunExecutionReceipt, DryRunExecutionRequest,
    DryRunExecutionResult, SimulatedBackendRegistry, build_default_dry_run_harness_policy,
    build_default_simulated_backend_registry, build_dry_run_execution_block_receipt,
    build_dry_run_execution_receipt, build_dry_run_execution_request,
    dry_run_execution_block_receipt_digest, dry_run_execution_receipt_digest,
    dry_run_execution_request_digest, dry_run_execution_result_digest,
    run_dry_run_execution, validate_dry_run_execution_block_receipt,
    validate_dry_run_execution_receipt, validate_dry_run_execution_request,
    validate_dry_run_execution_result, validate_simulated_backend_registry,
)
from sentientos.host_fulfillment_executor_readiness_runtime import (
    HostFulfillmentExecutorReadinessEvaluation, HostFulfillmentExecutorReadinessReceipt,
    validate_current_authority_snapshot, _dict as _readiness_dict, world_state_records as readiness_world_state_records,
)
from sentientos.world_state_board import WorldStateSourceKind, digest as world_digest

SCHEMA_VERSION = "host_dry_run_execution_runtime.v1"
READY_POSTURES = {"ready_for_executor_contract_review", "ready_for_executor_contract_review_with_conditions"}
EXECUTOR_TO_DRY_RUN_DOMAIN = {
    "diagnostics_executor_contract": "diagnostics_dry_run",
    "operator_review_executor_contract": "operator_review_dry_run",
    "resource_pressure_executor_contract": "resource_pressure_dry_run",
    "thermal_safety_executor_contract": "thermal_safety_dry_run",
    "future_cooling_executor_contract": "future_cooling_dry_run",
    "future_power_executor_contract": "future_power_dry_run",
    "future_cleanup_executor_contract": "future_cleanup_dry_run",
    "future_service_executor_contract": "future_service_dry_run",
}
NO_REAL_EFFECT = {
    "executor_implemented": False,
    "real_executor_invoked": False,
    "backend_loaded": False,
    "backend_invoked": False,
    "real_backend_invoked": False,
    "control_plane_execution_admission_granted": False,
    "fulfillment_granted": False,
    "real_fulfillment_performed": False,
    "privileged_effect_admission_granted": False,
    "effect_performed": False,
    "real_effect_performed": False,
    "host_mutation_performed": False,
}
_LOCKS: dict[str, threading.Lock] = {}

def _canon(o: Any) -> str: return json.dumps(o, sort_keys=True, separators=(",", ":"), default=str)
def _sha(o: Any) -> str: return "sha256:" + hashlib.sha256(_canon(o).encode()).hexdigest()
def _id(prefix: str, o: Any) -> str: return prefix + hashlib.sha256(_canon(o).encode()).hexdigest()[:24]
def _payload(o: Any) -> dict[str, Any]:
    if o is None: return {}
    if hasattr(o, "to_dict"): return dict(o.to_dict())
    if hasattr(o, "__dataclass_fields__"): return asdict(o)
    return dict(o)
def _semantic(d: Mapping[str, Any]) -> dict[str, Any]:
    p = dict(d); p.pop("created_at", None); p.pop("observed_at", None); p.pop("digest", None); return p
def digest_record(o: Any) -> str: return _sha(_semantic(_payload(o)))

@dataclass(frozen=True)
class HostDryRunExecutionBudget:
    max_records: int = 64; max_serialized_bytes: int = 524288; max_file_count: int = 32; max_artifact_size: int = 262144
    def to_dict(self) -> dict[str, Any]: return asdict(self)
@dataclass(frozen=True)
class HostDryRunExecutionSourceRef:
    ref_id: str; digest: str; kind: str; required: bool = True
    def to_dict(self) -> dict[str, Any]: return asdict(self)
@dataclass(frozen=True)
class HostDryRunExecutionRequest:
    request_id: str; digest: str; correlation_id: str; readiness_evaluation_id: str; readiness_evaluation_digest: str; readiness_bundle_digest: str; current_snapshot_id: str; current_snapshot_digest: str; executor_contract_id: str; executor_contract_digest: str; declarative_dry_run_plan_id: str; declarative_dry_run_plan_digest: str; dry_run_domain: str; simulated_backend_class: str; scope_labels: tuple[str, ...]; target_labels: tuple[str, ...]; created_at: str = "1970-01-01T00:00:00+00:00"; schema_version: str = SCHEMA_VERSION; simulation_only: bool = True
    def to_dict(self) -> dict[str, Any]: return asdict(self)
@dataclass(frozen=True)
class HostDryRunExecutionPlan:
    plan_id: str; digest: str; request_id: str; request_digest: str; source_refs: tuple[HostDryRunExecutionSourceRef, ...]; missing_real_execution_gates: tuple[str, ...]; blocked_actions: tuple[str, ...]; no_real_effect: Mapping[str, bool]; schema_version: str = SCHEMA_VERSION
    def to_dict(self) -> dict[str, Any]: return asdict(self)
@dataclass(frozen=True)
class HostDryRunExecutionRuntimeReceipt:
    receipt_id: str; digest: str; posture: str; request_id: str; request_digest: str; plan_id: str; plan_digest: str; dry_run_request_id: str; dry_run_request_digest: str; result_or_block_id: str; result_or_block_digest: str; dry_run_receipt_id: str; dry_run_receipt_digest: str; readiness_runtime_receipt_id: str; readiness_runtime_receipt_digest: str; bundle_digest: str = ""; schema_version: str = SCHEMA_VERSION; simulation_only: bool = True; dry_run_executed: bool = False; no_real_effect: Mapping[str, bool] = None  # type: ignore[assignment]
    def to_dict(self) -> dict[str, Any]:
        d = asdict(self); d["no_real_effect"] = dict(self.no_real_effect or NO_REAL_EFFECT); return d
@dataclass(frozen=True)
class HostDryRunExecutionEvaluation:
    status: str; findings: tuple[str, ...]; request: HostDryRunExecutionRequest | None; plan: HostDryRunExecutionPlan | None; simulation_admission: Mapping[str, Any] | None; harness_policy: Mapping[str, Any] | None; simulated_backend_registry: Mapping[str, Any] | None; dry_run_request: Mapping[str, Any] | None; result_or_block_receipt: Mapping[str, Any] | None; dry_run_receipt: Mapping[str, Any] | None; runtime_receipt: HostDryRunExecutionRuntimeReceipt | None; source_manifest: Mapping[str, Any] | None = None; persisted: bool = False; replayed: bool = False; admission_call_count: int = 0; harness_builder_call_count: int = 0; simulation_call_count: int = 0
    def to_dict(self) -> dict[str, Any]: return asdict(self)
@dataclass(frozen=True)
class HostDryRunExecutionRuntimeSummary:
    summary_id: str; status: str; simulation_package_count: int; latest_request_id: str = ""; latest_result_id: str = ""; latest_receipt_id: str = ""; simulation_only: bool = True; read_only: bool = True
    def to_dict(self) -> dict[str, Any]: return asdict(self)
@dataclass(frozen=True)
class HostDryRunExecutionRuntimeValidationResult:
    ok: bool; findings: tuple[str, ...]
    def to_dict(self) -> dict[str, Any]: return asdict(self)

def _bundle_digest_from_eval(ev: HostFulfillmentExecutorReadinessEvaluation) -> str:
    return _sha({"readiness_evaluation": ev.to_dict()})

def _source_manifest(ev: HostFulfillmentExecutorReadinessEvaluation, bundle_digest: str) -> dict[str, Any]:
    refs = []
    for kind, obj in (("readiness_request", ev.request), ("readiness_plan", ev.plan), ("current_authority_evidence", getattr(ev.request, "current_grant_evidence_id", "")), ("executor_contract", ev.contract), ("backend_declaration", ev.backend_declaration), ("precondition_manifest", ev.precondition_manifest), ("declarative_dry_run_plan", ev.dry_run_plan), ("future_execution_admission_packet", ev.admission_packet), ("executor_contract_readiness_receipt", ev.readiness_receipt), ("readiness_runtime_receipt", ev.runtime_receipt)):
        p = _payload(obj) if not isinstance(obj, str) else {"id": obj}
        refs.append({"kind": kind, "ref_id": str(p.get("request_id") or p.get("plan_id") or p.get("contract_id") or p.get("declaration_id") or p.get("manifest_id") or p.get("packet_id") or p.get("receipt_id") or p.get("id") or kind), "digest": str(p.get("digest") or _sha(p)), "required": True})
    return {"schema_version": SCHEMA_VERSION, "manifest_id": _id("hdr_source_manifest_", refs), "readiness_bundle_digest": bundle_digest, "refs": refs, **NO_REAL_EFFECT}

def validate_source_evaluation(ev: HostFulfillmentExecutorReadinessEvaluation) -> HostDryRunExecutionRuntimeValidationResult:
    f: list[str] = []
    if not isinstance(ev, HostFulfillmentExecutorReadinessEvaluation): return HostDryRunExecutionRuntimeValidationResult(False, ("complete_typed_readiness_evaluation_required",))
    if ev.status not in READY_POSTURES: f.append("readiness_posture_not_simulatable")
    for name in ("request", "plan", "metadata_admission", "contract", "backend_declaration", "precondition_manifest", "dry_run_plan", "admission_packet", "readiness_receipt", "runtime_receipt"):
        if getattr(ev, name) is None: f.append(f"missing_{name}")
    if not ev.runtime_receipt: f.append("missing_runtime_receipt")
    for p in (ev.request, ev.plan, ev.runtime_receipt):
        if p and _payload(p).get("digest") != digest_record(p): f.append(f"{type(p).__name__}:digest_mismatch")
    noauth = _payload(ev.runtime_receipt).get("no_authority", {}) if ev.runtime_receipt else {}
    if any(bool(v) for v in dict(noauth).values()): f.append("readiness_runtime_authority_flag_true")
    evidence_id = getattr(ev.request, "current_grant_evidence_id", "") if ev.request else ""
    evidence_digest = getattr(ev.request, "current_grant_evidence_digest", "") if ev.request else ""
    if not evidence_id or not evidence_digest: f.append("missing_current_authority_evidence")
    # The complete persisted readiness bundle is represented here by the full evaluation graph.
    return HostDryRunExecutionRuntimeValidationResult(not f, tuple(sorted(set(f))))

def build_request(source: HostFulfillmentExecutorReadinessEvaluation, *, correlation_id: str | None = None, created_at: str = "1970-01-01T00:00:00+00:00") -> HostDryRunExecutionRequest:
    v = validate_source_evaluation(source)
    if not v.ok: raise ValueError("invalid_readiness_source:" + ",".join(v.findings))
    c = _payload(source.contract); p = _payload(source.dry_run_plan); rr = _payload(source.runtime_receipt); req = _payload(source.request)
    executor_domain = str(c.get("executor_domain", req.get("executor_domain", "")))
    dry_domain = EXECUTOR_TO_DRY_RUN_DOMAIN.get(executor_domain)
    if not dry_domain: raise ValueError("unsupported_executor_domain")
    registry = build_default_simulated_backend_registry(created_at=created_at)
    backend_class = {"diagnostics_dry_run":"diagnostic_backend_simulated","operator_review_dry_run":"operator_manual_backend_simulated","resource_pressure_dry_run":"diagnostic_backend_simulated","thermal_safety_dry_run":"diagnostic_backend_simulated","future_cooling_dry_run":"cooling_backend_simulated","future_power_dry_run":"power_backend_simulated","future_cleanup_dry_run":"cleanup_backend_simulated","future_service_dry_run":"service_backend_simulated"}[dry_domain]
    bundle_digest = _bundle_digest_from_eval(source)
    sem = {"source": _sha(source.to_dict()), "bundle": bundle_digest, "snapshot": req.get("current_grant_evidence_digest"), "contract": c.get("digest"), "plan": p.get("digest"), "domain": dry_domain, "backend": backend_class, "correlation": correlation_id or req.get("correlation_id") or rr.get("receipt_id")}
    rid = _id("hdr_request_", sem)
    out = HostDryRunExecutionRequest(rid, "", str(correlation_id or req.get("correlation_id") or rid), _id("hfer_eval_", _sha(source.to_dict())), _sha(source.to_dict()), bundle_digest, str(req.get("current_grant_evidence_id", "")), str(req.get("current_grant_evidence_digest", "")), str(c.get("contract_id", "")), str(c.get("digest", "")), str(p.get("plan_id", "")), str(p.get("digest", "")), dry_domain, backend_class, tuple(req.get("requested_scope_labels", ())), tuple(req.get("target_labels", ())), created_at)
    return replace(out, digest=digest_record(out))

def plan_request(req: HostDryRunExecutionRequest, source: HostFulfillmentExecutorReadinessEvaluation) -> HostDryRunExecutionPlan:
    refs = tuple(HostDryRunExecutionSourceRef(k, str(d), k) for k, d in (("runtime_request", req.digest), ("readiness_evaluation", req.readiness_evaluation_digest), ("readiness_bundle", req.readiness_bundle_digest), ("current_snapshot", req.current_snapshot_digest), ("executor_contract", req.executor_contract_digest), ("declarative_dry_run_plan", req.declarative_dry_run_plan_digest), ("readiness_runtime_receipt", _payload(source.runtime_receipt).get("digest", ""))))
    missing = ("future_execution_admission_required", "real_executor_implementation_required", "privileged_effect_admission_required", "real_effect_receipt_required")
    blocked = tuple(sorted(set(_payload(source.readiness_receipt).get("blocked_actions", ()) or _payload(source.request).get("blocked_actions", ()))))
    out = HostDryRunExecutionPlan(_id("hdr_plan_", {"request": req.digest, "refs": [r.to_dict() for r in refs]}), "", req.request_id, req.digest, refs, missing, blocked, NO_REAL_EFFECT)
    return replace(out, digest=digest_record(out))

class HostDryRunExecutionRuntimeCoordinator:
    def __init__(self, *, runtime_state_root: str | Path | None = None, kernel: Any | None = None, clock: Callable[[], str] | None = None):
        self.runtime_state_root = Path(runtime_state_root or os.getenv("SENTIENTOS_RUNTIME_STATE_ROOT") or tempfile.gettempdir()+"/sentientos_runtime")
        self.kernel = kernel or get_control_plane_kernel(); self.clock = clock or (lambda: "1970-01-01T00:00:00+00:00")
        self.admission_call_count = 0; self.harness_builder_call_count = 0; self.simulation_call_count = 0
    def request_simulation_admission(self, req: HostDryRunExecutionRequest, plan: HostDryRunExecutionPlan, registry: SimulatedBackendRegistry) -> Mapping[str, Any]:
        self.admission_call_count += 1
        decision = self.kernel.admit(ControlActionRequest("host_dry_run_execution_runtime_simulation_review", AuthorityClass.PROPOSAL_EVALUATION, "operator_invoked_cli", "host_dry_run_execution_runtime", LifecyclePhase.MAINTENANCE, {"runtime_request_id": req.request_id, "runtime_request_digest": req.digest, "source_readiness_evaluation_digest": req.readiness_evaluation_digest, "source_readiness_bundle_digest": req.readiness_bundle_digest, "current_snapshot_id": req.current_snapshot_id, "current_snapshot_digest": req.current_snapshot_digest, "current_authority_evidence_digest": req.current_snapshot_digest, "executor_contract_id": req.executor_contract_id, "executor_contract_digest": req.executor_contract_digest, "declarative_dry_run_plan_id": req.declarative_dry_run_plan_id, "declarative_dry_run_plan_digest": req.declarative_dry_run_plan_digest, "simulated_backend_registry_id": registry.registry_id, "simulated_backend_registry_digest": registry.digest, "correlation_id": req.correlation_id, "simulation_only": True, **NO_REAL_EFFECT}))
        return _payload(decision)
    def evaluate(self, source: HostFulfillmentExecutorReadinessEvaluation, *, output_root: str | Path, correlation_id: str | None = None, persist: bool = True) -> HostDryRunExecutionEvaluation:
        findings = list(validate_source_evaluation(source).findings)
        if findings:
            return HostDryRunExecutionEvaluation("blocked_dry_run_runtime", tuple(findings), None, None, None, None, None, None, None, None, None, None, False, False, self.admission_call_count, self.harness_builder_call_count, self.simulation_call_count)
        req = build_request(source, correlation_id=correlation_id, created_at=self.clock()); plan = plan_request(req, source); root = Path(output_root).resolve()
        if str(root).startswith(str(Path.cwd().resolve())): return HostDryRunExecutionEvaluation("blocked_dry_run_runtime", ("repository_local_runtime_root_rejected",), req, plan, None, None, None, None, None, None, None, None, False, False, self.admission_call_count, self.harness_builder_call_count, self.simulation_call_count)
        semantic = {"request": req.digest, "source": req.readiness_evaluation_digest, "bundle": req.readiness_bundle_digest, "snapshot": req.current_snapshot_digest, "contract": req.executor_contract_digest, "plan": req.declarative_dry_run_plan_digest, "domain": req.dry_run_domain, "backend": req.simulated_backend_class, "scope": req.scope_labels, "targets": req.target_labels, "correlation": req.correlation_id}
        lock = _LOCKS.setdefault(str(root), threading.Lock())
        with lock:
            prior = self._load_replay(root, req.correlation_id, semantic)
            if prior is not None:
                if prior.get("conflict"): return HostDryRunExecutionEvaluation("contradicted_dry_run_runtime", ("semantic_replay_conflict",), req, plan, None, None, None, None, None, None, None, None, False, False, self.admission_call_count, self.harness_builder_call_count, self.simulation_call_count)
                return self._evaluation_from_bundle(Path(prior["bundle"]))
            policy = build_default_dry_run_harness_policy(); registry = build_default_simulated_backend_registry(created_at=self.clock())
            rv = validate_simulated_backend_registry(registry)
            if not rv.ok: return self._blocked(req, plan, tuple(rv.findings), policy, registry)
            admission = self.request_simulation_admission(req, plan, registry)
            if admission.get("outcome") != "allow" or admission.get("authority_class") != AuthorityClass.PROPOSAL_EVALUATION.value:
                return HostDryRunExecutionEvaluation("blocked_dry_run_runtime", ("simulation_admission_not_allowed",), req, plan, admission, policy.to_dict(), registry.to_dict(), None, None, None, None, _source_manifest(source, req.readiness_bundle_digest), False, False, self.admission_call_count, self.harness_builder_call_count, self.simulation_call_count)
            readiness_receipt = source.readiness_receipt or {}
            dry_req0 = build_dry_run_execution_request(readiness_receipt, requested_dry_run_domain=req.dry_run_domain, requested_simulated_backend_class=req.simulated_backend_class, requested_scope_labels=req.scope_labels, created_at=self.clock()); self.harness_builder_call_count += 1
            dry_req = replace(dry_req0, readiness_runtime_receipt_id=_payload(source.runtime_receipt).get("receipt_id", ""), readiness_runtime_receipt_digest=_payload(source.runtime_receipt).get("digest", ""), executor_contract_digest=req.executor_contract_digest, declarative_dry_run_plan_id=req.declarative_dry_run_plan_id, declarative_dry_run_plan_digest=req.declarative_dry_run_plan_digest, current_snapshot_id=req.current_snapshot_id, current_snapshot_digest=req.current_snapshot_digest, simulated_backend_registry_id=registry.registry_id, simulated_backend_registry_digest=registry.digest)
            dry_req = replace(dry_req, digest=dry_run_execution_request_digest(dry_req))
            result = run_dry_run_execution(dry_req, registry, created_at=self.clock()); self.simulation_call_count += 1
            if isinstance(result, DryRunExecutionResult):
                result = replace(result, request_digest=dry_req.digest, simulated_backend_digest=next((_sha(r.to_dict()) for r in registry.backend_records if r.backend_id == result.simulated_backend_id), "")); result = replace(result, digest=dry_run_execution_result_digest(result))
                receipt = build_dry_run_execution_receipt(dry_req, result, created_at=self.clock()); self.harness_builder_call_count += 1
                receipt = replace(receipt, request_digest=dry_req.digest, result_digest=result.digest); receipt = replace(receipt, digest=dry_run_execution_receipt_digest(receipt))
                status = "dry_run_runtime_simulated"
            else:
                receipt = None; status = "blocked_dry_run_runtime"
                result = replace(result, request_digest=dry_req.digest, finding_digests=tuple(_sha(x) for x in result.block_reason_codes)); result = replace(result, digest=dry_run_execution_block_receipt_digest(result))
            runtime = HostDryRunExecutionRuntimeReceipt(_id("hdr_receipt_", {"request": req.digest, "dry": dry_req.digest, "result": _payload(result).get("digest"), "receipt": _payload(receipt).get("digest", "")}), "", status, req.request_id, req.digest, plan.plan_id, plan.digest, dry_req.request_id, dry_req.digest, str(_payload(result).get("result_id") or _payload(result).get("receipt_id")), str(_payload(result).get("digest")), str(_payload(receipt).get("receipt_id", "")), str(_payload(receipt).get("digest", "")), str(_payload(source.runtime_receipt).get("receipt_id", "")), str(_payload(source.runtime_receipt).get("digest", "")), "", SCHEMA_VERSION, True, bool(receipt), NO_REAL_EFFECT)
            runtime = replace(runtime, digest=digest_record(runtime))
            ev = HostDryRunExecutionEvaluation(status, (), req, plan, admission, policy.to_dict(), registry.to_dict(), dry_req.to_dict(), _payload(result), _payload(receipt) if receipt else None, runtime, _source_manifest(source, req.readiness_bundle_digest), False, False, self.admission_call_count, self.harness_builder_call_count, self.simulation_call_count)
            if persist and receipt: ev = replace(ev, persisted=self._persist(root, ev, semantic))
            return ev
    def _blocked(self, req, plan, findings, policy, registry):
        return HostDryRunExecutionEvaluation("blocked_dry_run_runtime", findings, req, plan, None, policy.to_dict(), registry.to_dict(), None, None, None, None, None, False, False, self.admission_call_count, self.harness_builder_call_count, self.simulation_call_count)
    def _manifest(self, bundle: Path) -> dict[str, Any]:
        entries=[]
        for path in sorted(bundle.iterdir()):
            if path.name == "bundle_manifest.json": continue
            raw=path.read_bytes(); entries.append({"relative_filename": path.name, "size": len(raw), "digest": "sha256:"+hashlib.sha256(raw).hexdigest(), "artifact_kind": path.stem, "schema_version": SCHEMA_VERSION})
        return {"schema_version": SCHEMA_VERSION, "artifact_kind": "host_dry_run_execution_runtime_bundle_manifest", "files": entries, "bundle_digest": _sha({"files": entries})}
    def _persist(self, root: Path, ev: HostDryRunExecutionEvaluation, semantic: Mapping[str, Any]) -> bool:
        if root.exists() and root.is_symlink(): raise ValueError("symlink_escape_rejected")
        root.mkdir(parents=True, exist_ok=True); assert ev.request and ev.runtime_receipt
        bundle=root/ev.request.request_id; tmp=root/(bundle.name+".tmp")
        if tmp.exists(): shutil.rmtree(tmp)
        tmp.mkdir()
        files={"runtime_request.json": ev.request.to_dict(), "source_manifest.json": ev.source_manifest, "runtime_plan.json": ev.plan.to_dict() if ev.plan else None, "simulation_admission.json": ev.simulation_admission, "harness_policy.json": ev.harness_policy, "simulated_backend_registry.json": ev.simulated_backend_registry, "dry_run_request.json": ev.dry_run_request, "result_or_block_receipt.json": ev.result_or_block_receipt, "dry_run_receipt.json": ev.dry_run_receipt, "validation_findings.json": {"findings": ev.findings}, "runtime_receipt.json": ev.runtime_receipt.to_dict(), "summary.json": summarize_evaluation(ev), "README.md": render_markdown(ev)}
        for name, val in files.items(): (tmp/name).write_text(json.dumps(val, sort_keys=True, indent=2) if name.endswith('.json') else str(val), encoding='utf-8')
        manifest=self._manifest(tmp); (tmp/"bundle_manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2), encoding='utf-8')
        runtime=replace(ev.runtime_receipt, bundle_digest=manifest["bundle_digest"]); runtime=replace(runtime, digest=digest_record(runtime)); (tmp/"runtime_receipt.json").write_text(json.dumps(runtime.to_dict(), sort_keys=True, indent=2), encoding='utf-8')
        manifest=self._manifest(tmp); (tmp/"bundle_manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2), encoding='utf-8')
        os.replace(tmp, bundle)
        latest={"request_id": ev.request.request_id, "request_digest": ev.request.digest, "runtime_receipt_id": runtime.receipt_id, "runtime_receipt_digest": runtime.digest, "bundle_digest": manifest["bundle_digest"], "posture": ev.status}
        (root/"latest.json.tmp").write_text(json.dumps(latest, sort_keys=True, indent=2)); os.replace(root/"latest.json.tmp", root/"latest.json")
        idx=root/"replay_index.json"; data=json.loads(idx.read_text()) if idx.exists() else {}; data[ev.request.correlation_id]={**latest,"semantic":json.loads(_canon(semantic))}; (root/"replay_index.json.tmp").write_text(json.dumps(data, sort_keys=True, indent=2)); os.replace(root/"replay_index.json.tmp", idx)
        return True
    def _load_replay(self, root: Path, correlation_id: str, semantic: Mapping[str, Any]) -> Mapping[str, Any] | None:
        idx=root/"replay_index.json"
        if not idx.exists(): return None
        try: data=json.loads(idx.read_text()); prior=data.get(correlation_id)
        except Exception: return {"conflict": True}
        if not prior: return None
        if prior.get("semantic") != json.loads(_canon(semantic)): return {"conflict": True}
        bundle=root/str(prior.get("request_id"));
        if not bundle.exists() or bundle.is_symlink(): return {"conflict": True}
        try:
            manifest=json.loads((bundle/"bundle_manifest.json").read_text()); entries=manifest.get("files", [])
            if manifest.get("bundle_digest") != _sha({"files": entries}): return {"conflict": True}
            for e in entries:
                rel=str(e.get("relative_filename"))
                if "/" in rel or ".." in Path(rel).parts: return {"conflict": True}
                raw=(bundle/rel).read_bytes()
                if len(raw) != int(e.get("size", -1)) or "sha256:"+hashlib.sha256(raw).hexdigest() != e.get("digest"): return {"conflict": True}
                if rel.endswith(".json"): json.loads(raw.decode())
        except Exception: return {"conflict": True}
        return {"bundle": str(bundle)}
    def _evaluation_from_bundle(self, bundle: Path) -> HostDryRunExecutionEvaluation:
        def load(n): return json.loads((bundle/n).read_text())
        req=HostDryRunExecutionRequest(**load("runtime_request.json")); plan=HostDryRunExecutionPlan(**load("runtime_plan.json")); runtime=HostDryRunExecutionRuntimeReceipt(**load("runtime_receipt.json"))
        return HostDryRunExecutionEvaluation(runtime.posture, (), req, plan, load("simulation_admission.json"), load("harness_policy.json"), load("simulated_backend_registry.json"), load("dry_run_request.json"), load("result_or_block_receipt.json"), load("dry_run_receipt.json"), runtime, load("source_manifest.json"), True, True, self.admission_call_count, self.harness_builder_call_count, self.simulation_call_count)

def summarize_evaluation(ev: HostDryRunExecutionEvaluation) -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "status": ev.status, "simulation_package_count": 1 if ev.request else 0, "latest_request_id": ev.request.request_id if ev.request else "", "latest_result_id": str((ev.result_or_block_receipt or {}).get("result_id") or (ev.result_or_block_receipt or {}).get("receipt_id") or ""), "latest_receipt_id": str((ev.dry_run_receipt or {}).get("receipt_id", "")), "dry_run_executed": bool((ev.dry_run_receipt or {}).get("dry_run_executed", False)), "simulation_only": True, "read_only": True, **NO_REAL_EFFECT}

def render_markdown(ev: HostDryRunExecutionEvaluation) -> str:
    s=summarize_evaluation(ev); return "# Host Dry-Run Execution Runtime\n\n"+"\n".join(f"- {k}: {v}" for k,v in sorted(s.items()))+"\n"

def validate_evaluation(ev: HostDryRunExecutionEvaluation) -> HostDryRunExecutionRuntimeValidationResult:
    f=[]
    if ev.request and ev.request.digest != digest_record(ev.request): f.append("runtime_request_digest_mismatch")
    if ev.plan and ev.plan.digest != digest_record(ev.plan): f.append("runtime_plan_digest_mismatch")
    if ev.dry_run_request and not validate_dry_run_execution_request(ev.dry_run_request).ok: f += list(validate_dry_run_execution_request(ev.dry_run_request).findings)
    if ev.dry_run_receipt and not validate_dry_run_execution_receipt(ev.dry_run_receipt).ok: f += list(validate_dry_run_execution_receipt(ev.dry_run_receipt).findings)
    if ev.runtime_receipt and ev.runtime_receipt.digest != digest_record(ev.runtime_receipt): f.append("runtime_receipt_digest_mismatch")
    for name, val in NO_REAL_EFFECT.items():
        if summarize_evaluation(ev).get(name) != val: f.append("forbidden_real_effect_flag:"+name)
    return HostDryRunExecutionRuntimeValidationResult(not f, tuple(sorted(set(f))))

def world_state_records(ev: HostDryRunExecutionEvaluation, *, observed_at: str = "1970-01-01T00:00:00+00:00") -> list[dict[str, Any]]:
    items=[("proposal","host_dry_run_execution_runtime_request", ev.request.to_dict() if ev.request else None), ("review","host_dry_run_execution_simulation_admission", ev.simulation_admission), ("review","host_dry_run_execution_simulated_backend_registry", ev.simulated_backend_registry), ("rehearsal","host_dry_run_execution_request", ev.dry_run_request), ("rehearsal","host_dry_run_execution_result_or_block_receipt", ev.result_or_block_receipt), ("rehearsal","host_dry_run_execution_receipt", ev.dry_run_receipt), ("review","host_dry_run_execution_runtime_receipt", ev.runtime_receipt.to_dict() if ev.runtime_receipt else None)]
    out=[]
    for stage, kind, obj in items:
        if not obj: continue
        p=_payload(obj); p.update(NO_REAL_EFFECT); sid=str(p.get("request_id") or p.get("result_id") or p.get("receipt_id") or p.get("registry_id") or kind)
        out.append({"source_kind": WorldStateSourceKind.FULFILLMENT.value, "schema_version": SCHEMA_VERSION, "observed_at": observed_at, "source_id": f"hdr:{sid}:{kind}", "subject_id": sid, "subject_kind": kind, "stage": stage, "disposition": ev.status, "evidence_strength": "recorded", "payload": p, "effect_claimed": False, "effect_proven": False, "digest": world_digest(p)})
    return out

def dashboard_projection(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    posture={}; domains={}; backends={}; latest_req=latest_res=latest_rec=""; blocked=set(); gates=set(); count=success=blocked_count=stale=contradicted=unavailable=0
    for r in records:
        if not str(r.get("subject_kind", "")).startswith("host_dry_run_execution"): continue
        count+=1; posture[str(r.get("disposition", "unknown"))]=posture.get(str(r.get("disposition", "unknown")),0)+1; p=_payload(r.get("payload", {}))
        if p.get("dry_run_domain") or p.get("requested_dry_run_domain"): domains[str(p.get("dry_run_domain") or p.get("requested_dry_run_domain"))]=domains.get(str(p.get("dry_run_domain") or p.get("requested_dry_run_domain")),0)+1
        if p.get("simulated_backend_class") or p.get("requested_simulated_backend_class"): backends[str(p.get("simulated_backend_class") or p.get("requested_simulated_backend_class"))]=backends.get(str(p.get("simulated_backend_class") or p.get("requested_simulated_backend_class")),0)+1
        latest_req=str(p.get("request_id", latest_req)); latest_res=str(p.get("result_id", latest_res)); latest_rec=str(p.get("receipt_id", latest_rec)); blocked.update(p.get("blocked_actions", ())); gates.update(p.get("missing_real_execution_gates", ()))
        text=str(r.get("disposition", "")); success += int(text == "dry_run_runtime_simulated"); blocked_count += int("blocked" in text); stale += int("stale" in text); contradicted += int("contradicted" in text); unavailable += int("unavailable" in text)
    return {"status":"recorded" if count else "unavailable", "simulation_package_count": count, "posture_counts": posture, "dry_run_domain_counts": domains, "simulated_backend_counts": backends, "successful_count": success, "blocked_count": blocked_count, "stale_count": stale, "contradicted_count": contradicted, "unavailable_count": unavailable, "latest_request_id": latest_req, "latest_result_id": latest_res, "latest_receipt_id": latest_rec, "preserved_blocked_actions": sorted(blocked), "missing_real_execution_gates": sorted(gates), "read_only": True, "simulation_only": True, "dry_run_executed": success > 0, **NO_REAL_EFFECT}
