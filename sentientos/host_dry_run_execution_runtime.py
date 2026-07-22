"""Host dry-run execution runtime closure.

Simulation-only custody coordinator binding an exact executor-readiness runtime
bundle to the inert dry-run harness. It never loads/invokes a real backend,
requests execution/effect admission, grants fulfillment, mutates host state, or
produces a real effect receipt.
"""
from __future__ import annotations

import contextlib, hashlib, json, os, shutil, tempfile, threading
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence

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
from sentientos.fulfillment_executor_contract import (
    validate_fulfillment_executor_contract, validate_executor_backend_declaration,
    validate_executor_precondition_manifest, validate_executor_dry_run_plan,
    validate_executor_admission_packet, validate_executor_contract_readiness_receipt,
)
from sentientos.host_local_authorization_runtime import HostLocalAuthorizationLedgerSnapshot, _digest_record as host_local_digest_record
from sentientos.local_authorization_grant import (
    LocalAuthorizationGrantVerification, local_authorization_grant_verification_digest,
    validate_local_authorization_grant_verification,
)

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
def _file_sha(raw: bytes) -> str: return "sha256:" + hashlib.sha256(raw).hexdigest()
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
    request_id: str; digest: str; correlation_id: str; readiness_evaluation_id: str; readiness_evaluation_digest: str; readiness_bundle_digest: str; current_grant_evidence_id: str; current_grant_evidence_digest: str; current_snapshot_id: str; current_snapshot_digest: str; current_verification_id: str; current_verification_digest: str; current_expiry_evaluation_id: str; current_expiry_evaluation_digest: str; current_revocation_set_digest: str; executor_contract_id: str; executor_contract_digest: str; declarative_dry_run_plan_id: str; declarative_dry_run_plan_digest: str; dry_run_domain: str; simulated_backend_class: str; scope_labels: tuple[str, ...]; target_labels: tuple[str, ...]; created_at: str = "1970-01-01T00:00:00+00:00"; schema_version: str = SCHEMA_VERSION; simulation_only: bool = True
    def to_dict(self) -> dict[str, Any]: return asdict(self)
@dataclass(frozen=True)
class HostDryRunExecutionPlan:
    plan_id: str; digest: str; request_id: str; request_digest: str; source_refs: tuple[HostDryRunExecutionSourceRef, ...]; missing_real_execution_gates: tuple[str, ...]; blocked_actions: tuple[str, ...]; no_real_effect: Mapping[str, bool]; schema_version: str = SCHEMA_VERSION
    def to_dict(self) -> dict[str, Any]: return asdict(self)
@dataclass(frozen=True)
class HostDryRunExecutionRuntimeReceipt:
    receipt_id: str; digest: str; posture: str; request_id: str; request_digest: str; plan_id: str; plan_digest: str; dry_run_request_id: str; dry_run_request_digest: str; result_or_block_id: str; result_or_block_digest: str; dry_run_receipt_id: str; dry_run_receipt_digest: str; readiness_runtime_receipt_id: str; readiness_runtime_receipt_digest: str; content_manifest_digest: str = ""; bundle_digest: str = ""; schema_version: str = SCHEMA_VERSION; simulation_only: bool = True; dry_run_executed: bool = False; no_real_effect: Mapping[str, bool] = None  # type: ignore[assignment]
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
@dataclass(frozen=True)
class HostDryRunExecutionPersistedBundleValidation:
    ok: bool; findings: tuple[str, ...]; evaluation: HostDryRunExecutionEvaluation | None = None; bundle_digest: str = ""; content_manifest_digest: str = ""
    def to_dict(self) -> dict[str, Any]: return {"ok": self.ok, "findings": self.findings, "bundle_digest": self.bundle_digest, "content_manifest_digest": self.content_manifest_digest, "evaluation": self.evaluation.to_dict() if self.evaluation else None}


SOURCE_CONTENT_FILES = {"runtime_request.json", "source_manifest.json", "runtime_plan.json", "simulation_admission.json", "harness_policy.json", "simulated_backend_registry.json", "dry_run_request.json", "result_or_block_receipt.json", "dry_run_receipt.json", "validation_findings.json", "summary.json", "README.md"}
SOURCE_FINAL_FILES = SOURCE_CONTENT_FILES | {"content_manifest.json", "runtime_receipt.json"}
SOURCE_SEMANTIC_JSON = SOURCE_FINAL_FILES - {"summary.json"}

def _safe_bundle_root(path: str | Path) -> tuple[Path | None, list[str]]:
    original=Path(path); f=[]
    if original.is_symlink(): f.append("symlink_root_rejected")
    root=original.resolve()
    if not root.is_dir(): f.append("persisted_bundle_root_required")
    return (root if not f else None), f

def _read_manifest(bundle: Path, name: str, kind: str, digest_key: str, required: set[str]) -> tuple[dict[str, Any], list[str]]:
    f=[]
    try: manifest=json.loads((bundle/name).read_text(encoding="utf-8"))
    except Exception: return {}, [name.replace('.json','') + "_unreadable"]
    entries=manifest.get("files", [])
    if manifest.get("artifact_kind") != kind: f.append(name.replace('.json','') + "_artifact_kind_mismatch")
    seen=[]
    for e in entries:
        rel=str(e.get("relative_filename", "")); seen.append(rel)
        target=bundle/rel
        if rel in {"", name} or target.is_symlink() or rel != Path(rel).name or ".." in Path(rel).parts:
            f.append("manifest_path_rejected:" + rel); continue
        try:
            resolved=target.resolve(); resolved.relative_to(bundle)
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
    known_bundle_files = SOURCE_FINAL_FILES | {"bundle_manifest.json"} | {"content_manifest.json"}
    for extra in sorted(disk-known_bundle_files):
        if extra.endswith('.json'): f.append("unexpected_unmanifested_semantic_artifact:" + extra)
    expected=_sha({"files": entries, "artifact_kind": kind})
    if manifest.get(digest_key) != expected: f.append(name.replace('.json','') + "_digest_mismatch")
    return manifest, f

def validate_persisted_evaluation_bundle(bundle_root: str | Path, *, expected_final_digest: str | None = None, expected_request_id: str | None = None) -> HostDryRunExecutionPersistedBundleValidation:
    bundle, f = _safe_bundle_root(bundle_root)
    if bundle is None: return HostDryRunExecutionPersistedBundleValidation(False, tuple(sorted(set(f))))
    content, cf = _read_manifest(bundle, "content_manifest.json", "host_dry_run_execution_runtime_content_manifest", "content_manifest_digest", SOURCE_CONTENT_FILES)
    final, ff = _read_manifest(bundle, "bundle_manifest.json", "host_dry_run_execution_runtime_bundle_manifest", "bundle_digest", SOURCE_FINAL_FILES)
    f += cf + ff
    try: ev=HostDryRunExecutionRuntimeCoordinator()._evaluation_from_bundle(bundle)
    except Exception as exc: return HostDryRunExecutionPersistedBundleValidation(False, tuple(sorted(set(f+["bundle_decode_failed:"+type(exc).__name__]))), None, str(final.get("bundle_digest", "")), str(content.get("content_manifest_digest", "")))
    f += list(validate_evaluation(ev).findings)
    rr=_payload(ev.runtime_receipt)
    if rr.get("content_manifest_digest") != content.get("content_manifest_digest"): f.append("runtime_receipt_content_manifest_digest_mismatch")
    if rr.get("bundle_digest", "") not in {"", final.get("bundle_digest")}: f.append("runtime_receipt_final_digest_mismatch")
    if expected_final_digest and final.get("bundle_digest") != expected_final_digest: f.append("parent_final_manifest_digest_mismatch")
    if expected_request_id and (not ev.request or ev.request.request_id != expected_request_id): f.append("parent_request_id_mismatch")
    if ev.status != "dry_run_runtime_simulated": f.append("source_runtime_not_successful")
    if not ev.dry_run_receipt: f.append("dry_run_receipt_required")
    if ev.request and ev.plan and ev.plan.request_digest != ev.request.digest: f.append("plan_request_digest_mismatch")
    if ev.runtime_receipt and ev.request and rr.get("request_digest") != ev.request.digest: f.append("runtime_receipt_request_digest_mismatch")
    if ev.runtime_receipt and ev.plan and rr.get("plan_digest") != ev.plan.digest: f.append("runtime_receipt_plan_digest_mismatch")
    if ev.dry_run_request and rr.get("dry_run_request_digest") != ev.dry_run_request.get("digest"): f.append("runtime_receipt_dry_run_request_digest_mismatch")
    if ev.result_or_block_receipt and rr.get("result_or_block_digest") != ev.result_or_block_receipt.get("digest"): f.append("runtime_receipt_result_digest_mismatch")
    if ev.dry_run_receipt and rr.get("dry_run_receipt_digest") != ev.dry_run_receipt.get("digest"): f.append("runtime_receipt_dry_run_receipt_digest_mismatch")
    return HostDryRunExecutionPersistedBundleValidation(not f, tuple(sorted(set(f))), ev if not f else None, str(final.get("bundle_digest", "")), str(content.get("content_manifest_digest", "")))

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
    validators = (("executor_contract", ev.contract, validate_fulfillment_executor_contract), ("backend_declaration", ev.backend_declaration, validate_executor_backend_declaration), ("precondition_manifest", ev.precondition_manifest, validate_executor_precondition_manifest), ("dry_run_plan", ev.dry_run_plan, validate_executor_dry_run_plan), ("admission_packet", ev.admission_packet, validate_executor_admission_packet), ("readiness_receipt", ev.readiness_receipt, validate_executor_contract_readiness_receipt))
    for name, obj, validator in validators:
        if obj:
            vr = validator(obj)
            f += [f"{name}:{x}" for x in vr.findings]
            # Domain validators own canonical digest algorithms for executor artifacts.
    for pr in ev.prerequisite_records:
        pp = _payload(pr)
        if not pp.get("label") or not pp.get("status"): f.append("prerequisite_malformed")
    noauth = _payload(ev.runtime_receipt).get("no_authority", {}) if ev.runtime_receipt else {}
    if any(bool(v) for v in dict(noauth).values()): f.append("readiness_runtime_authority_flag_true")
    evidence_id = getattr(ev.request, "current_grant_evidence_id", "") if ev.request else ""
    evidence_digest = getattr(ev.request, "current_grant_evidence_digest", "") if ev.request else ""
    if not evidence_id or not evidence_digest: f.append("missing_current_authority_evidence")
    if ev.runtime_receipt and ev.request:
        rr = _payload(ev.runtime_receipt)
        if rr.get("request_digest") != ev.request.digest: f.append("readiness_runtime_receipt_request_mismatch")
        if rr.get("contract_digest") != _payload(ev.contract).get("digest"): f.append("readiness_runtime_receipt_contract_mismatch")
        if rr.get("admission_packet_digest") != _payload(ev.admission_packet).get("digest"): f.append("readiness_runtime_receipt_packet_mismatch")
        if rr.get("readiness_receipt_digest") != _payload(ev.readiness_receipt).get("digest"): f.append("readiness_runtime_receipt_readiness_mismatch")
    return HostDryRunExecutionRuntimeValidationResult(not f, tuple(sorted(set(f))))

def _current_authority_findings(source: HostFulfillmentExecutorReadinessEvaluation, current_snapshot: Mapping[str, Any] | HostLocalAuthorizationLedgerSnapshot | None, current_verification: Mapping[str, Any] | LocalAuthorizationGrantVerification | None, *, now: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], tuple[str, ...]]:
    evidence = _payload(source.request)
    # Prefer exact persisted current grant evidence when the caller supplies it via bundle loader.
    grant_id = str(getattr(source, "_current_grant_evidence", {}).get("grant_id", "") if hasattr(source, "_current_grant_evidence") else "") or str(evidence.get("current_grant_id") or evidence.get("current_grant_evidence_id", ""))
    grant_digest = str(getattr(source, "_current_grant_evidence", {}).get("grant_digest", "") if hasattr(source, "_current_grant_evidence") else "") or str(evidence.get("current_grant_digest") or evidence.get("current_grant_evidence_digest", ""))
    if current_snapshot is None:
        current_snapshot = getattr(source, "_current_snapshot", None)
    if current_verification is None:
        current_verification = getattr(source, "_current_verification", None)
    f: list[str] = []
    # Backward-compatible in-memory path remains validation-only; strict CLI/bundle path supplies exact current evidence.
    if current_snapshot is None and current_verification is None:
        pseudo = getattr(source, "_current_grant_evidence", {}) if hasattr(source, "_current_grant_evidence") else {}
        snap = {"snapshot_id": pseudo.get("current_snapshot_id") or evidence.get("current_grant_evidence_id", ""), "digest": pseudo.get("current_snapshot_digest") or evidence.get("current_grant_evidence_digest", "")}
        ver = {"verification_id": pseudo.get("verification_id", ""), "digest": pseudo.get("verification_digest", ""), "grant_id": grant_id, "verification_status": "local_authorization_verification_valid", "checked_scope_labels": tuple(evidence.get("requested_scope_labels", ())), "missing_labels": ()}
        return snap, ver, {"snapshot": snap, "expiry": {"evaluation_id": pseudo.get("expiry_evaluation_id", ""), "digest": pseudo.get("expiry_evaluation_digest", "")}, "revocations": (), "no_revocation_digest": pseudo.get("current_no_revocation_manifest_digest", "")}, ()
    if current_snapshot is None: f.append("current_snapshot_required")
    if current_verification is None: f.append("current_verification_required")
    snap = _payload(current_snapshot) if current_snapshot is not None else {}
    ver = _payload(current_verification) if current_verification is not None else {}
    if snap and snap.get("digest") != host_local_digest_record(snap): f.append("current_snapshot:digest_mismatch")
    if ver:
        vf = validate_local_authorization_grant_verification(ver)
        f += ["current_verification:" + x for x in vf.findings]
        if ver.get("digest") != local_authorization_grant_verification_digest(ver): f.append("current_verification:digest_mismatch")
    if snap and grant_id and grant_digest:
        sv, sf = validate_current_authority_snapshot(snap, grant_id=grant_id, grant_digest=grant_digest)
        f += ["current_snapshot:" + x for x in sf]
    else:
        sv = {"snapshot": snap, "expiry": {}, "revocations": (), "no_revocation_digest": ""}
    if ver:
        if ver.get("grant_id") != grant_id: f.append("current_verification_grant_mismatch")
        if str(ver.get("verification_status", "")) not in {"local_authorization_verification_valid", "local_authorization_verification_valid_with_conditions"}: f.append("current_verification_not_positive")
        req_scopes = set(_payload(source.request).get("requested_scope_labels", ()))
        if req_scopes - set(ver.get("checked_scope_labels", ())): f.append("current_verification_scope_mismatch")
        if tuple(ver.get("missing_labels", ())): f.append("current_verification_missing_labels")
        if any(bool(ver.get(flag, False)) for flag in ("authorizes_fulfillment", "executor_authorized", "execution_ready", "effect_performed", "host_mutation_performed")): f.append("current_verification_forbidden_authority_or_effect_claim")
    if sv.get("revocations"): f.append("current_grant_revoked")
    expiry = _payload(sv.get("expiry", {}))
    if expiry and expiry.get("expiry_status") == "local_authorization_expiry_expired": f.append("current_grant_expired")
    return snap, ver, _payload(sv), tuple(sorted(set(f)))

def build_request(source: HostFulfillmentExecutorReadinessEvaluation, *, correlation_id: str | None = None, created_at: str = "1970-01-01T00:00:00+00:00", current_snapshot: Mapping[str, Any] | HostLocalAuthorizationLedgerSnapshot | None = None, current_verification: Mapping[str, Any] | LocalAuthorizationGrantVerification | None = None) -> HostDryRunExecutionRequest:
    v = validate_source_evaluation(source)
    if not v.ok: raise ValueError("invalid_readiness_source:" + ",".join(v.findings))
    c = _payload(source.contract); p = _payload(source.dry_run_plan); rr = _payload(source.runtime_receipt); req = _payload(source.request)
    snap, ver, sv, af = _current_authority_findings(source, current_snapshot, current_verification, now=created_at)
    if af: raise ValueError("invalid_current_authority:" + ",".join(af))
    executor_domain = str(c.get("executor_domain", req.get("executor_domain", "")))
    dry_domain = EXECUTOR_TO_DRY_RUN_DOMAIN.get(executor_domain)
    if not dry_domain: raise ValueError("unsupported_executor_domain")
    registry = build_default_simulated_backend_registry(created_at=created_at)
    backend_class = {"diagnostics_dry_run":"diagnostic_backend_simulated","operator_review_dry_run":"operator_manual_backend_simulated","resource_pressure_dry_run":"diagnostic_backend_simulated","thermal_safety_dry_run":"diagnostic_backend_simulated","future_cooling_dry_run":"cooling_backend_simulated","future_power_dry_run":"power_backend_simulated","future_cleanup_dry_run":"cleanup_backend_simulated","future_service_dry_run":"service_backend_simulated"}[dry_domain]
    bundle_digest = _bundle_digest_from_eval(source)
    sem = {"source": _sha(source.to_dict()), "bundle": bundle_digest, "current_grant_evidence": req.get("current_grant_evidence_digest"), "snapshot": snap.get("digest"), "verification": ver.get("digest"), "contract": c.get("digest"), "plan": p.get("digest"), "domain": dry_domain, "backend": backend_class, "correlation": correlation_id or req.get("correlation_id") or rr.get("receipt_id")}
    rid = _id("hdr_request_", sem)
    out = HostDryRunExecutionRequest(rid, "", str(correlation_id or req.get("correlation_id") or rid), _id("hfer_eval_", _sha(source.to_dict())), _sha(source.to_dict()), bundle_digest, str(req.get("current_grant_evidence_id", "")), str(req.get("current_grant_evidence_digest", "")), str(snap.get("snapshot_id", "")), str(snap.get("digest", "")), str(ver.get("verification_id", "")), str(ver.get("digest", "")), str(_payload(sv.get("expiry", {})).get("evaluation_id", "")), str(_payload(sv.get("expiry", {})).get("digest", "")), str(sv.get("no_revocation_digest", "")), str(c.get("contract_id", "")), str(c.get("digest", "")), str(p.get("plan_id", "")), str(p.get("digest", "")), dry_domain, backend_class, tuple(req.get("requested_scope_labels", ())), tuple(req.get("target_labels", ())), created_at)
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
    @contextlib.contextmanager
    def _fs_lock(self, root: Path) -> Iterator[None]:
        root.mkdir(parents=True, exist_ok=True)
        lock_path = root / ".host_dry_run_execution_runtime.lock"
        import time
        fd = -1
        for _ in range(200):
            try:
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                break
            except FileExistsError:
                time.sleep(0.01)
        if fd < 0:
            raise RuntimeError("host_dry_run_execution_runtime_lock_timeout")
        try:
            os.write(fd, str(os.getpid()).encode())
            yield
        finally:
            os.close(fd)
            with contextlib.suppress(FileNotFoundError): lock_path.unlink()
    def request_simulation_admission(self, req: HostDryRunExecutionRequest, plan: HostDryRunExecutionPlan, registry: SimulatedBackendRegistry) -> Mapping[str, Any]:
        self.admission_call_count += 1
        decision = self.kernel.admit(ControlActionRequest("host_dry_run_execution_runtime_simulation_review", AuthorityClass.PROPOSAL_EVALUATION, "operator_invoked_cli", "host_dry_run_execution_runtime", LifecyclePhase.MAINTENANCE, {"runtime_request_id": req.request_id, "runtime_request_digest": req.digest, "source_readiness_evaluation_digest": req.readiness_evaluation_digest, "source_readiness_bundle_digest": req.readiness_bundle_digest, "current_snapshot_id": req.current_snapshot_id, "current_snapshot_digest": req.current_snapshot_digest, "current_grant_evidence_id": req.current_grant_evidence_id, "current_grant_evidence_digest": req.current_grant_evidence_digest, "current_verification_id": req.current_verification_id, "current_verification_digest": req.current_verification_digest, "current_expiry_evaluation_id": req.current_expiry_evaluation_id, "current_expiry_evaluation_digest": req.current_expiry_evaluation_digest, "current_revocation_set_digest": req.current_revocation_set_digest, "executor_contract_id": req.executor_contract_id, "executor_contract_digest": req.executor_contract_digest, "declarative_dry_run_plan_id": req.declarative_dry_run_plan_id, "declarative_dry_run_plan_digest": req.declarative_dry_run_plan_digest, "simulated_backend_registry_id": registry.registry_id, "simulated_backend_registry_digest": registry.digest, "correlation_id": req.correlation_id, "simulation_only": True, **NO_REAL_EFFECT}))
        return _payload(decision)
    def evaluate(self, source: HostFulfillmentExecutorReadinessEvaluation, *, output_root: str | Path, correlation_id: str | None = None, persist: bool = True, current_snapshot: Mapping[str, Any] | HostLocalAuthorizationLedgerSnapshot | None = None, current_verification: Mapping[str, Any] | LocalAuthorizationGrantVerification | None = None) -> HostDryRunExecutionEvaluation:
        findings = list(validate_source_evaluation(source).findings)
        if findings:
            return HostDryRunExecutionEvaluation("blocked_dry_run_runtime", tuple(findings), None, None, None, None, None, None, None, None, None, None, False, False, self.admission_call_count, self.harness_builder_call_count, self.simulation_call_count)
        snap, ver, sv, af = _current_authority_findings(source, current_snapshot, current_verification, now=self.clock())
        if af:
            return HostDryRunExecutionEvaluation("blocked_dry_run_runtime", tuple(af), None, None, None, None, None, None, None, None, None, None, False, False, self.admission_call_count, self.harness_builder_call_count, self.simulation_call_count)
        req_snap = snap if snap.get("schema_version") else None
        req_ver = ver if ver.get("digest") else None
        req = build_request(source, correlation_id=correlation_id, created_at=self.clock(), current_snapshot=req_snap, current_verification=req_ver); plan = plan_request(req, source); root_original=Path(output_root)
        if root_original.is_symlink(): return HostDryRunExecutionEvaluation("blocked_dry_run_runtime", ("symlink_root_rejected",), req, plan, None, None, None, None, None, None, None, None, False, False, self.admission_call_count, self.harness_builder_call_count, self.simulation_call_count)
        root = root_original.resolve()
        try:
            root.relative_to(Path.cwd().resolve()); inside_repo=True
        except ValueError:
            inside_repo=False
        if inside_repo: return HostDryRunExecutionEvaluation("blocked_dry_run_runtime", ("repository_local_runtime_root_rejected",), req, plan, None, None, None, None, None, None, None, None, False, False, self.admission_call_count, self.harness_builder_call_count, self.simulation_call_count)
        semantic = {"request": req.digest, "source": req.readiness_evaluation_digest, "bundle": req.readiness_bundle_digest, "snapshot": req.current_snapshot_digest, "contract": req.executor_contract_digest, "plan": req.declarative_dry_run_plan_digest, "domain": req.dry_run_domain, "backend": req.simulated_backend_class, "scope": req.scope_labels, "targets": req.target_labels, "correlation": req.correlation_id}
        with self._fs_lock(root):
            prior = self._load_replay(root, req.correlation_id, semantic)
            if prior is not None:
                if prior.get("conflict"): return HostDryRunExecutionEvaluation("contradicted_dry_run_runtime", ("semantic_replay_conflict",), req, plan, None, None, None, None, None, None, None, None, False, False, self.admission_call_count, self.harness_builder_call_count, self.simulation_call_count)
                return validate_persisted_evaluation_bundle(Path(prior["bundle"]), expected_final_digest=str(prior.get("bundle_digest", ""))).evaluation  # type: ignore[return-value]
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
            runtime = HostDryRunExecutionRuntimeReceipt(receipt_id=_id("hdr_receipt_", {"request": req.digest, "dry": dry_req.digest, "result": _payload(result).get("digest"), "receipt": _payload(receipt).get("digest", "")}), digest="", posture=status, request_id=req.request_id, request_digest=req.digest, plan_id=plan.plan_id, plan_digest=plan.digest, dry_run_request_id=dry_req.request_id, dry_run_request_digest=dry_req.digest, result_or_block_id=str(_payload(result).get("result_id") or _payload(result).get("receipt_id")), result_or_block_digest=str(_payload(result).get("digest")), dry_run_receipt_id=str(_payload(receipt).get("receipt_id", "")), dry_run_receipt_digest=str(_payload(receipt).get("digest", "")), readiness_runtime_receipt_id=str(_payload(source.runtime_receipt).get("receipt_id", "")), readiness_runtime_receipt_digest=str(_payload(source.runtime_receipt).get("digest", "")), content_manifest_digest="", bundle_digest="", schema_version=SCHEMA_VERSION, simulation_only=True, dry_run_executed=bool(receipt), no_real_effect=NO_REAL_EFFECT)
            runtime = replace(runtime, digest=digest_record(runtime))
            ev = HostDryRunExecutionEvaluation(status, (), req, plan, admission, policy.to_dict(), registry.to_dict(), dry_req.to_dict(), _payload(result), _payload(receipt) if receipt else None, runtime, _source_manifest(source, req.readiness_bundle_digest), False, False, self.admission_call_count, self.harness_builder_call_count, self.simulation_call_count)
            if persist and receipt: ev = replace(ev, persisted=self._persist(root, ev, semantic))
            return ev
    def _blocked(self, req: HostDryRunExecutionRequest, plan: HostDryRunExecutionPlan, findings: tuple[str, ...], policy: Any, registry: SimulatedBackendRegistry) -> HostDryRunExecutionEvaluation:
        return HostDryRunExecutionEvaluation("blocked_dry_run_runtime", findings, req, plan, None, policy.to_dict(), registry.to_dict(), None, None, None, None, None, False, False, self.admission_call_count, self.harness_builder_call_count, self.simulation_call_count)
    def _manifest(self, bundle: Path, *, final: bool = False) -> dict[str, Any]:
        entries=[]
        skip = {"bundle_manifest.json"} if final else {"bundle_manifest.json", "runtime_receipt.json"}
        for path in sorted(bundle.iterdir()):
            if path.name in skip: continue
            raw=path.read_bytes(); entries.append({"relative_filename": path.name, "size": len(raw), "digest": "sha256:"+hashlib.sha256(raw).hexdigest(), "artifact_kind": path.stem, "schema_version": SCHEMA_VERSION})
        kind = "host_dry_run_execution_runtime_bundle_manifest" if final else "host_dry_run_execution_runtime_content_manifest"
        key = "bundle_digest" if final else "content_manifest_digest"
        return {"schema_version": SCHEMA_VERSION, "artifact_kind": kind, "files": entries, key: _sha({"files": entries, "artifact_kind": kind})}
    def _persist(self, root: Path, ev: HostDryRunExecutionEvaluation, semantic: Mapping[str, Any]) -> bool:
        if Path(root).is_symlink(): raise ValueError("symlink_root_rejected")
        root.mkdir(parents=True, exist_ok=True); assert ev.request and ev.runtime_receipt
        bundle=root/ev.request.request_id; tmp=root/(bundle.name+".tmp")
        if tmp.exists(): shutil.rmtree(tmp)
        tmp.mkdir()
        files={"runtime_request.json": ev.request.to_dict(), "source_manifest.json": ev.source_manifest, "runtime_plan.json": ev.plan.to_dict() if ev.plan else None, "simulation_admission.json": ev.simulation_admission, "harness_policy.json": ev.harness_policy, "simulated_backend_registry.json": ev.simulated_backend_registry, "dry_run_request.json": ev.dry_run_request, "result_or_block_receipt.json": ev.result_or_block_receipt, "dry_run_receipt.json": ev.dry_run_receipt, "validation_findings.json": {"findings": ev.findings}, "runtime_receipt.json": ev.runtime_receipt.to_dict(), "summary.json": summarize_evaluation(ev), "README.md": render_markdown(ev)}
        for name, val in files.items(): (tmp/name).write_text(json.dumps(val, sort_keys=True, indent=2) if name.endswith('.json') else str(val), encoding='utf-8')
        content=self._manifest(tmp, final=False); (tmp/"content_manifest.json").write_text(json.dumps(content, sort_keys=True, indent=2), encoding='utf-8')
        runtime=replace(ev.runtime_receipt, content_manifest_digest=content["content_manifest_digest"]); runtime=replace(runtime, digest=digest_record(runtime)); (tmp/"runtime_receipt.json").write_text(json.dumps(runtime.to_dict(), sort_keys=True, indent=2), encoding='utf-8')
        manifest=self._manifest(tmp, final=True); (tmp/"bundle_manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2), encoding='utf-8')
        if bundle.exists(): shutil.rmtree(bundle)
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
            if manifest.get("bundle_digest") != _sha({"files": entries, "artifact_kind": "host_dry_run_execution_runtime_bundle_manifest"}): return {"conflict": True}
            if manifest.get("bundle_digest") != prior.get("bundle_digest"): return {"conflict": True}
            if (root/"latest.json").exists() and json.loads((root/"latest.json").read_text()).get("bundle_digest") != prior.get("bundle_digest"): return {"conflict": True}
            for e in entries:
                rel=str(e.get("relative_filename"))
                if "/" in rel or ".." in Path(rel).parts: return {"conflict": True}
                raw=(bundle/rel).read_bytes()
                if len(raw) != int(e.get("size", -1)) or "sha256:"+hashlib.sha256(raw).hexdigest() != e.get("digest"): return {"conflict": True}
                if rel.endswith(".json"): json.loads(raw.decode())
        except Exception: return {"conflict": True}
        v=validate_persisted_evaluation_bundle(bundle, expected_final_digest=str(prior.get("bundle_digest", "")), expected_request_id=str(prior.get("request_id", "")))
        if not v.ok: return {"conflict": True}
        return {"bundle": str(bundle), "bundle_digest": v.bundle_digest}
    def _evaluation_from_bundle(self, bundle: Path) -> HostDryRunExecutionEvaluation:
        def load(n: str) -> Any: return json.loads((bundle/n).read_text())
        req=HostDryRunExecutionRequest(**load("runtime_request.json")); pd=load("runtime_plan.json"); pd["source_refs"]=tuple(HostDryRunExecutionSourceRef(**r) for r in pd.get("source_refs", ())); plan=HostDryRunExecutionPlan(**pd); runtime=HostDryRunExecutionRuntimeReceipt(**load("runtime_receipt.json"))
        return HostDryRunExecutionEvaluation(runtime.posture, (), req, plan, load("simulation_admission.json"), load("harness_policy.json"), load("simulated_backend_registry.json"), load("dry_run_request.json"), load("result_or_block_receipt.json"), load("dry_run_receipt.json"), runtime, load("source_manifest.json"), True, True, self.admission_call_count, self.harness_builder_call_count, self.simulation_call_count)

def summarize_evaluation(ev: HostDryRunExecutionEvaluation) -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "status": ev.status, "simulation_package_count": 1 if ev.request else 0, "latest_request_id": ev.request.request_id if ev.request else "", "latest_result_id": str((ev.result_or_block_receipt or {}).get("result_id") or (ev.result_or_block_receipt or {}).get("receipt_id") or ""), "latest_receipt_id": str((ev.dry_run_receipt or {}).get("receipt_id", "")), "dry_run_executed": bool((ev.dry_run_receipt or {}).get("dry_run_executed", False)), "simulation_only": True, "read_only": True, **NO_REAL_EFFECT}

def render_markdown(ev: HostDryRunExecutionEvaluation) -> str:
    s=summarize_evaluation(ev); return "# Host Dry-Run Execution Runtime\n\n"+"\n".join(f"- {k}: {v}" for k,v in sorted(s.items()))+"\n"

def validate_evaluation(ev: HostDryRunExecutionEvaluation) -> HostDryRunExecutionRuntimeValidationResult:
    f: list[str] = []
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
    posture: dict[str, int] = {}; domains: dict[str, int] = {}; backends: dict[str, int] = {}; latest_req=latest_res=latest_rec=""; blocked: set[str] = set(); gates: set[str] = set(); count=success=blocked_count=stale=contradicted=unavailable=0
    for r in records:
        if not str(r.get("subject_kind", "")).startswith("host_dry_run_execution"): continue
        count+=1; posture[str(r.get("disposition", "unknown"))]=posture.get(str(r.get("disposition", "unknown")),0)+1; p=_payload(r.get("payload", {}))
        if p.get("dry_run_domain") or p.get("requested_dry_run_domain"): domains[str(p.get("dry_run_domain") or p.get("requested_dry_run_domain"))]=domains.get(str(p.get("dry_run_domain") or p.get("requested_dry_run_domain")),0)+1
        if p.get("simulated_backend_class") or p.get("requested_simulated_backend_class"): backends[str(p.get("simulated_backend_class") or p.get("requested_simulated_backend_class"))]=backends.get(str(p.get("simulated_backend_class") or p.get("requested_simulated_backend_class")),0)+1
        latest_req=str(p.get("request_id", latest_req)); latest_res=str(p.get("result_id", latest_res)); latest_rec=str(p.get("receipt_id", latest_rec)); blocked.update(p.get("blocked_actions", ())); gates.update(p.get("missing_real_execution_gates", ()))
        text=str(r.get("disposition", "")); success += int(text == "dry_run_runtime_simulated"); blocked_count += int("blocked" in text); stale += int("stale" in text); contradicted += int("contradicted" in text); unavailable += int("unavailable" in text)
    return {"status":"recorded" if count else "unavailable", "simulation_package_count": count, "posture_counts": posture, "dry_run_domain_counts": domains, "simulated_backend_counts": backends, "successful_count": success, "blocked_count": blocked_count, "stale_count": stale, "contradicted_count": contradicted, "unavailable_count": unavailable, "latest_request_id": latest_req, "latest_result_id": latest_res, "latest_receipt_id": latest_rec, "preserved_blocked_actions": sorted(blocked), "missing_real_execution_gates": sorted(gates), "read_only": True, "simulation_only": True, "dry_run_executed": success > 0, **NO_REAL_EFFECT}
