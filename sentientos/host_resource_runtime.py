# mypy: disable-error-code="no-untyped-call,var-annotated,dict-item,arg-type"
"""Admitted, bounded read-only host resource observation runtime.

This module composes existing safe collectors, resource pressure evaluation, and
proposal-only policy receipts. It never mutates host state and never grants
fulfillment, adoption, privilege, Git, repository, model, network, or actuation
authority.
"""
from __future__ import annotations

import concurrent.futures as cf
import hashlib, json, math, os, re, tempfile, time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from sentientos.control_plane_kernel import AuthorityClass, ControlActionRequest, ControlActionDecision, ControlPlaneKernel, LifecyclePhase, get_control_plane_kernel
from sentientos.host_collectors import HostCollectorResult, collect_cpu_observation, collect_disk_observation, collect_fan_pwm_observation, collect_memory_observation, collect_network_interface_observation, collect_platform_observation, collect_process_observation, collect_service_manager_observation, collect_thermal_sensor_observation, validate_host_collector_result
from sentientos.host_resource_governor import HostResourcePressureReport, HostResourceTelemetrySnapshot, build_host_resource_telemetry_from_collector_results, evaluate_host_resource_pressure, host_resource_report_digest, summarize_host_resource_pressure, validate_host_resource_pressure_report
from sentientos.host_resource_policy import HostResourcePolicyDecision, HostResourceProposalReceipt, build_host_resource_proposal_receipts, evaluate_host_resource_policy, summarize_host_resource_policy_decision, summarize_host_resource_proposal_receipt, validate_host_resource_policy_decision, validate_host_resource_proposal_receipt
from sentientos.world_state_board import WorldStateSourceKind, digest

SCHEMA_VERSION = "host_resource_observation_runtime.v1"
CollectorCallable = Callable[..., HostCollectorResult]
STATUSES = {"available", "partial", "unavailable", "error", "timeout", "invalid", "unsupported", "skipped"}
FORBIDDEN_TEXT = re.compile(r"([A-Za-z]:\\\\|/home/|/tmp/|/workspace/|SENTIENTOS_|TOKEN|PASSWORD|SECRET|Traceback|cmdline|environ|[0-9a-f]{2}(:[0-9a-f]{2}){5})", re.I)

@dataclass(frozen=True)
class HostObservationBudget:
    max_collectors: int = 9
    per_collector_timeout_seconds: float = 1.0
    total_deadline_seconds: float = 5.0
    max_workers: int = 4
    retry_count: int = 0
    max_serialized_result_bytes: int = 65536
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostObservationCollectorSpec:
    collector_id: str
    required: bool
    supported_platforms: tuple[str, ...]
    order: int
    function: CollectorCallable = field(compare=False, repr=False)
    description: str = "read-only telemetry"
    def to_dict(self) -> dict[str, Any]:
        return {"collector_id": self.collector_id, "required": self.required, "supported_platforms": self.supported_platforms, "order": self.order, "description": self.description}

@dataclass(frozen=True)
class HostObservationPlan:
    plan_id: str
    budget: HostObservationBudget
    collectors: tuple[HostObservationCollectorSpec, ...]
    semantic_digest: str
    authority_class: str = AuthorityClass.OBSERVATION.value
    effect_authority: bool = False
    def to_dict(self) -> dict[str, Any]:
        return {"plan_id": self.plan_id, "semantic_digest": self.semantic_digest, "budget": self.budget.to_dict(), "collectors": [c.to_dict() for c in self.collectors], "authority_class": self.authority_class, "effect_authority": False, "does_not_mutate_host": True}

@dataclass(frozen=True)
class HostObservationEpoch:
    epoch_id: str
    correlation_id: str
    plan_id: str
    admission_decision_ref: str
    admission_outcome: str
    results: tuple[HostCollectorResult, ...]
    status_counts: Mapping[str, int]
    required_failed: tuple[str, ...]
    optional_failed: tuple[str, ...]
    timed_out_collectors: tuple[str, ...]
    validation_findings: tuple[str, ...]
    semantic_digest: str
    observed_at: str
    collectors_called: int
    effect_authority: bool = False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostResourceRuntimeEvaluation:
    evaluation_id: str
    plan: HostObservationPlan
    epoch: HostObservationEpoch
    snapshot: HostResourceTelemetrySnapshot
    pressure_report: HostResourcePressureReport
    policy_decision: HostResourcePolicyDecision
    proposal_receipts: tuple[HostResourceProposalReceipt, ...]
    validation_findings: tuple[str, ...]
    semantic_digest: str
    no_effect_authority: bool = True
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostResourceRuntimeReceipt:
    receipt_id: str
    evaluation_id: str
    bundle_digest: str
    artifact_root: str
    artifact_paths: Mapping[str, str]
    semantic_digest: str
    no_effect_authority: bool = True
    repository_mutation_performed: bool = False
    host_mutation_performed: bool = False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostResourceRuntimeValidationResult:
    ok: bool
    findings: tuple[str, ...] = ()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=lambda x: asdict(x) if hasattr(x, "__dataclass_fields__") else str(x))

def _id(prefix: str, value: Any) -> str: return prefix + hashlib.sha256(canonical_json(value).encode()).hexdigest()[:24]

def _now() -> str: return datetime.now(timezone.utc).isoformat()

def default_collector_specs() -> tuple[HostObservationCollectorSpec, ...]:
    allp = ("linux", "darwin", "windows", "unknown")
    return tuple(sorted((
        HostObservationCollectorSpec("platform", True, allp, 10, collect_platform_observation),
        HostObservationCollectorSpec("disk", True, allp, 20, collect_disk_observation),
        HostObservationCollectorSpec("memory", True, allp, 30, collect_memory_observation),
        HostObservationCollectorSpec("cpu", True, allp, 40, collect_cpu_observation),
        HostObservationCollectorSpec("process", False, ("linux",), 50, collect_process_observation),
        HostObservationCollectorSpec("network_interfaces", False, ("linux",), 60, collect_network_interface_observation),
        HostObservationCollectorSpec("service_manager", False, allp, 70, collect_service_manager_observation),
        HostObservationCollectorSpec("thermal_sensors", False, ("linux",), 80, collect_thermal_sensor_observation),
        HostObservationCollectorSpec("fan_pwm", False, ("linux",), 90, collect_fan_pwm_observation),
    ), key=lambda s: (s.order, s.collector_id)))

def build_observation_plan(*, budget: HostObservationBudget | None = None, specs: Sequence[HostObservationCollectorSpec] | None = None) -> HostObservationPlan:
    b = budget or HostObservationBudget(); cs = tuple(sorted(specs or default_collector_specs(), key=lambda s: (s.order, s.collector_id)))[: b.max_collectors]
    sem = {"budget": b.to_dict(), "collectors": [c.to_dict() for c in cs]}
    return HostObservationPlan(_id("hop_", sem), b, cs, _id("hops_", sem))

def _unsupported_result(spec: HostObservationCollectorSpec, observed_at: str) -> HostCollectorResult:
    return HostCollectorResult(spec.collector_id, "unavailable", observed_at, "unsupported_platform", values={"unsupported_platform": True}, warnings=("unsupported_platform",))

def _exception_result(spec: HostObservationCollectorSpec, observed_at: str, exc: BaseException) -> HostCollectorResult:
    return HostCollectorResult(spec.collector_id, "error", observed_at, "contained_exception", findings=(), warnings=("collector_exception_contained",), values={"exception_label": type(exc).__name__})

def _timeout_result(spec: HostObservationCollectorSpec, observed_at: str) -> HostCollectorResult:
    return HostCollectorResult(spec.collector_id, "error", observed_at, "bounded_timeout", warnings=("collector_timeout",), values={"timeout": True})

def redact_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 8: return "<redacted:too_deep>"
    if isinstance(value, Mapping):
        out = {}
        for k, v in value.items():
            key = str(k)
            if key.lower() in {"address", "cmdline", "environ", "environment", "username", "user", "path", "absolute_path", "traceback"}:
                out[key] = "<redacted>"
            elif key == "path_label":
                out[key] = "runtime-root"
            elif key == "name" and isinstance(v, str) and depth > 1:
                out[key] = _id("local_label_", v)[:24]
            else:
                out[key] = redact_value(v, depth=depth+1)
        return out
    if isinstance(value, (list, tuple)): return [redact_value(v, depth=depth+1) for v in value[:128]]
    if isinstance(value, float): return value if math.isfinite(value) else None
    if isinstance(value, str): return FORBIDDEN_TEXT.sub("<redacted>", value)[:2048]
    return value

def sanitize_result(result: HostCollectorResult) -> HostCollectorResult:
    d = result.to_dict(); d = redact_value(d)
    return HostCollectorResult(**d)

def validate_plan(plan: HostObservationPlan) -> HostResourceRuntimeValidationResult:
    f=[]; ids=[c.collector_id for c in plan.collectors]
    if len(ids) != len(set(ids)): f.append("duplicate_collector_id")
    if len(ids) > plan.budget.max_collectors: f.append("collector_count_exceeds_budget")
    if plan.budget.per_collector_timeout_seconds <= 0 or plan.budget.total_deadline_seconds <= 0 or plan.budget.max_workers < 1: f.append("invalid_budget")
    return HostResourceRuntimeValidationResult(not f, tuple(f))

def validate_epoch(epoch: HostObservationEpoch) -> HostResourceRuntimeValidationResult:
    f=list(epoch.validation_findings)
    for r in epoch.results:
        f.extend(f"{r.collector_id}:{x}" for x in validate_host_collector_result(r).findings)
        blob=canonical_json(r.to_dict())
        if FORBIDDEN_TEXT.search(blob): f.append(f"{r.collector_id}:privacy_pattern_unredacted")
        if len(blob.encode()) > 65536: f.append(f"{r.collector_id}:oversized_result")
    return HostResourceRuntimeValidationResult(not f, tuple(sorted(set(f))))

def validate_evaluation(e: HostResourceRuntimeEvaluation) -> HostResourceRuntimeValidationResult:
    f=list(e.validation_findings)
    f.extend(validate_epoch(e.epoch).findings)
    f.extend(validate_host_resource_pressure_report(e.pressure_report, e.snapshot).findings)
    f.extend(validate_host_resource_policy_decision(e.policy_decision).findings)
    for r in e.proposal_receipts: f.extend(validate_host_resource_proposal_receipt(r).findings)
    if not e.no_effect_authority: f.append("effect_authority_true")
    return HostResourceRuntimeValidationResult(not f, tuple(sorted(set(f))))

class HostResourceRuntimeCoordinator:
    def __init__(self, *, kernel: ControlPlaneKernel | None = None, runtime_state_root: Path | str | None = None, plan: HostObservationPlan | None = None, clock: Callable[[], str] | None = None) -> None:
        self.kernel=kernel or get_control_plane_kernel(); self.runtime_state_root=Path(runtime_state_root or os.getenv("SENTIENTOS_RUNTIME_STATE_ROOT", tempfile.gettempdir()+"/sentientos_runtime")); self.plan=plan or build_observation_plan(); self.clock=clock or _now; self._epochs_by_correlation: dict[str, HostResourceRuntimeEvaluation] = {}; self.collector_call_count=0
    def request_admission(self, correlation_id: str) -> ControlActionDecision:
        return self.kernel.admit(ControlActionRequest("host_resource_observation_epoch", AuthorityClass.OBSERVATION, "sentientosd", "host_resource_observation_runtime", LifecyclePhase.MAINTENANCE, {"correlation_id": correlation_id, "no_effect_authority": True}))
    def run_cycle(self, *, correlation_id: str, decision: ControlActionDecision | None = None) -> HostResourceRuntimeEvaluation | None:
        if correlation_id in self._epochs_by_correlation: return self._epochs_by_correlation[correlation_id]
        decision = decision or self.request_admission(correlation_id)
        if not decision.allowed: return None
        observed_at=self.clock(); results=[]; timeouts=[]; findings=[]; start=time.monotonic(); platform_label=os.name if os.name != "posix" else ("linux" if Path('/proc').exists() else "unknown")
        with cf.ThreadPoolExecutor(max_workers=min(self.plan.budget.max_workers, max(1, len(self.plan.collectors)))) as ex:
            futs={}
            for spec in self.plan.collectors:
                if platform_label not in spec.supported_platforms and "unknown" not in spec.supported_platforms:
                    results.append(_unsupported_result(spec, observed_at)); continue
                futs[ex.submit(spec.function, observed_at=observed_at)] = spec; self.collector_call_count += 1
            for fut, spec in list(futs.items()):
                remaining = self.plan.budget.total_deadline_seconds - (time.monotonic()-start)
                if remaining <= 0: fut.cancel(); results.append(_timeout_result(spec, observed_at)); timeouts.append(spec.collector_id); continue
                try: raw=fut.result(timeout=min(self.plan.budget.per_collector_timeout_seconds, remaining))
                except cf.TimeoutError: fut.cancel(); results.append(_timeout_result(spec, observed_at)); timeouts.append(spec.collector_id); continue
                except BaseException as exc: results.append(_exception_result(spec, observed_at, exc)); continue
                results.append(sanitize_result(raw))
        ordered_results=tuple(sorted(results, key=lambda r: [s.order for s in self.plan.collectors if s.collector_id==r.collector_id][0] if any(s.collector_id==r.collector_id for s in self.plan.collectors) else 999))
        counts={s:0 for s in STATUSES}
        required_failed=[]; optional_failed=[]
        required={s.collector_id for s in self.plan.collectors if s.required}
        for r in ordered_results:
            counts[r.status if r.status in counts else "invalid"] += 1
            bad = r.status in {"error", "unavailable"} or bool(validate_host_collector_result(r).findings)
            if bad and r.collector_id in required: required_failed.append(r.collector_id)
            elif bad: optional_failed.append(r.collector_id)
        snapshot=build_host_resource_telemetry_from_collector_results(ordered_results, snapshot_id=_id("hrs_", {"plan": self.plan.semantic_digest, "results": [redact_value(r.to_dict()) for r in ordered_results]}))
        pressure=evaluate_host_resource_pressure(snapshot); decision2=evaluate_host_resource_policy(pressure); receipts=build_host_resource_proposal_receipts(decision2, created_at=observed_at)
        epoch_sem={"correlation_id": correlation_id, "plan": self.plan.semantic_digest, "admission": decision.admission_decision_ref, "results": [{k:v for k,v in redact_value(r.to_dict()).items() if k not in {"observed_at"}} for r in ordered_results]}
        epoch=HostObservationEpoch(_id("hoe_", epoch_sem), correlation_id, self.plan.plan_id, decision.admission_decision_ref, decision.outcome.value, ordered_results, counts, tuple(sorted(required_failed)), tuple(sorted(optional_failed)), tuple(sorted(timeouts)), tuple(findings), observed_at, self.collector_call_count, False, _id("hoes_", epoch_sem))
        ev_sem={"epoch": epoch.semantic_digest, "snapshot": snapshot.snapshot_id, "pressure": pressure.report_id, "policy": decision2.decision_id, "receipts": [r.receipt_id for r in receipts]}
        evaluation=HostResourceRuntimeEvaluation(_id("hre_", ev_sem), self.plan, epoch, snapshot, pressure, decision2, receipts, validate_epoch(epoch).findings, _id("hres_", ev_sem), True)
        self._epochs_by_correlation[correlation_id]=evaluation
        return evaluation
    def persist_bundle(self, evaluation: HostResourceRuntimeEvaluation, *, tick_id: str) -> HostResourceRuntimeReceipt:
        return persist_evidence_bundle(self.runtime_state_root, evaluation, tick_id=tick_id)

def summary_for_evaluation(e: HostResourceRuntimeEvaluation) -> dict[str, Any]:
    return {"status": "degraded" if e.epoch.required_failed or e.validation_findings else "ok", "evaluation_id": e.evaluation_id, "epoch_id": e.epoch.epoch_id, "plan_id": e.plan.plan_id, "collector_status_counts": dict(e.epoch.status_counts), "required_failed": e.epoch.required_failed, "optional_failed": e.epoch.optional_failed, "timed_out_collectors": e.epoch.timed_out_collectors, "snapshot_id": e.snapshot.snapshot_id, "pressure_labels": e.pressure_report.pressure_labels, "policy_status": e.policy_decision.status, "proposal_receipt_count": len(e.proposal_receipts), "proposal_receipts": [r.receipt_id for r in e.proposal_receipts], "no_effect_authority": True, "host_mutation_performed": False, "repository_mutation_performed": False, "semantic_digest": e.semantic_digest}

def world_state_records(e: HostResourceRuntimeEvaluation) -> list[dict[str, Any]]:
    base={"source_kind": WorldStateSourceKind.RESOURCE_GOVERNOR.value, "subject_kind": "host_resource_observation_runtime", "effect_claimed": False, "effect_proven": False, "observed_at": e.epoch.observed_at}
    return [
        {**base,"source_id":"host_resource_runtime:plan","subject_id":"host_resource_observation_plan","stage":"observation","disposition":"recorded","payload":e.plan.to_dict(),"digest":digest(e.plan.to_dict())},
        {**base,"source_id":"host_resource_runtime:epoch","subject_id":"host_resource_observation_epoch","stage":"observation","disposition":"degraded" if e.epoch.required_failed else "recorded","payload":{"epoch_id":e.epoch.epoch_id,"status_counts":dict(e.epoch.status_counts),"collectors_called":e.epoch.collectors_called,"timed_out_collectors":e.epoch.timed_out_collectors,"admission":e.epoch.admission_decision_ref},"digest":digest({"epoch":e.epoch.semantic_digest})},
        {**base,"source_id":"host_resource_runtime:snapshot","subject_id":"host_resource_snapshot","stage":"observation","disposition":"recorded","payload":e.snapshot.to_dict(),"digest":digest(e.snapshot.to_dict())},
        {**base,"source_id":"host_resource_runtime:pressure","subject_id":"host_resource_pressure","stage":"proposal","disposition":"recorded","payload":summarize_host_resource_pressure(e.pressure_report),"digest":host_resource_report_digest(e.pressure_report)},
        {**base,"source_id":"host_resource_runtime:policy","subject_id":"host_resource_policy","stage":"proposal","disposition":e.policy_decision.status,"payload":summarize_host_resource_policy_decision(e.policy_decision),"digest":digest(e.policy_decision.to_dict())},
        {**base,"source_id":"host_resource_runtime:receipts","subject_id":"host_resource_proposal_receipts","stage":"proposal","disposition":"recorded","payload":{"receipt_count": len(e.proposal_receipts), "receipt_ids": [r.receipt_id for r in e.proposal_receipts], "receipts": [summarize_host_resource_proposal_receipt(r) for r in e.proposal_receipts]},"digest":digest([r.to_dict() for r in e.proposal_receipts])},
    ]

def render_markdown(e: HostResourceRuntimeEvaluation) -> str:
    s=summary_for_evaluation(e)
    return "\n".join(["# Host Resource Observation Runtime", "", f"- Evaluation: `{e.evaluation_id}`", f"- Admission: `{e.epoch.admission_outcome}` / `{e.epoch.admission_decision_ref}`", f"- Collectors: `{s['collector_status_counts']}`", f"- Pressure: `{', '.join(e.pressure_report.pressure_labels)}`", f"- Policy: `{e.policy_decision.status}`", "- Effects: `none`; proposals are not fulfillment.", ""])

def persist_evidence_bundle(root: Path | str, e: HostResourceRuntimeEvaluation, *, tick_id: str) -> HostResourceRuntimeReceipt:
    root=Path(root) / "host_resource_runtime" / _id("tick_", {"tick": tick_id, "evaluation": e.evaluation_id})
    root.mkdir(parents=True, exist_ok=True)
    items={"plan":e.plan.to_dict(),"epoch":e.epoch.to_dict(),"collector_results":[r.to_dict() for r in e.epoch.results],"resource_snapshot":e.snapshot.to_dict(),"pressure_report":e.pressure_report.to_dict(),"policy_decision":e.policy_decision.to_dict(),"proposal_receipts":[r.to_dict() for r in e.proposal_receipts],"summary":summary_for_evaluation(e)}
    paths={}
    for name,obj in items.items():
        target=root/f"{name}.json"; tmp=target.with_suffix(".json.tmp"); tmp.write_text(json.dumps(redact_value(obj), sort_keys=True, indent=2), encoding="utf-8"); tmp.replace(target); paths[name]=target.as_posix()
    md=root/"summary.md"; tmp=md.with_suffix(".md.tmp"); tmp.write_text(render_markdown(e), encoding="utf-8"); tmp.replace(md); paths["markdown"]=md.as_posix()
    bdig=digest(items); latest=Path(root).parent/"latest.json"; t=latest.with_suffix(".json.tmp"); t.write_text(json.dumps(redact_value({"bundle_digest":bdig,"summary":items["summary"],"artifact_paths":paths}), sort_keys=True, indent=2), encoding="utf-8"); t.replace(latest)
    return HostResourceRuntimeReceipt(_id("hrrc_", {"evaluation":e.evaluation_id,"bundle":bdig}), e.evaluation_id, bdig, root.as_posix(), paths, e.semantic_digest)
