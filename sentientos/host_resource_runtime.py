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
from sentientos.governed_local_model_resource_allocation import GovernedLocalModelResourceLedger
from sentientos.world_state_board import WorldStateSourceKind, digest, record_digest
from sentientos.local_runtime_provisioning import semantic_digest

SCHEMA_VERSION = "host_resource_observation_runtime.v1"
RESOURCE_CONSUMPTION_WORLD_STATE_SCHEMA = "sentientos.resource_consumption_world_state_record:v2"
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
        observed_at=self.clock(); results=[]; timeouts=[]; findings=[]; cycle_collectors_called=0; start=time.monotonic(); platform_label=os.name if os.name != "posix" else ("linux" if Path('/proc').exists() else "unknown")
        # Do not use the executor as a context manager here: its implicit
        # ``shutdown(wait=True)`` would make a timed-out collector hold the
        # maintenance tick open until the worker returns.  The observation
        # budget is a real upper bound for the coordinator, so timed-out work
        # is cancelled where possible and late worker results are discarded.
        ex = cf.ThreadPoolExecutor(max_workers=min(self.plan.budget.max_workers, max(1, len(self.plan.collectors))))
        try:
            futs={}
            for spec in self.plan.collectors:
                if platform_label not in spec.supported_platforms and "unknown" not in spec.supported_platforms:
                    results.append(_unsupported_result(spec, observed_at)); continue
                futs[ex.submit(spec.function, observed_at=observed_at)] = spec; self.collector_call_count += 1; cycle_collectors_called += 1
            for fut, spec in list(futs.items()):
                remaining = self.plan.budget.total_deadline_seconds - (time.monotonic()-start)
                if remaining <= 0: fut.cancel(); results.append(_timeout_result(spec, observed_at)); timeouts.append(spec.collector_id); continue
                try: raw=fut.result(timeout=min(self.plan.budget.per_collector_timeout_seconds, remaining))
                except cf.TimeoutError: fut.cancel(); results.append(_timeout_result(spec, observed_at)); timeouts.append(spec.collector_id); continue
                except BaseException as exc: results.append(_exception_result(spec, observed_at, exc)); continue
                results.append(sanitize_result(raw))
        finally:
            ex.shutdown(wait=False, cancel_futures=True)
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
        epoch = HostObservationEpoch(
            epoch_id=_id("hoe_", epoch_sem),
            correlation_id=correlation_id,
            plan_id=self.plan.plan_id,
            admission_decision_ref=decision.admission_decision_ref,
            admission_outcome=decision.outcome.value,
            results=ordered_results,
            status_counts=counts,
            required_failed=tuple(sorted(required_failed)),
            optional_failed=tuple(sorted(optional_failed)),
            timed_out_collectors=tuple(sorted(timeouts)),
            validation_findings=tuple(findings),
            semantic_digest=_id("hoes_", epoch_sem),
            observed_at=observed_at,
            collectors_called=cycle_collectors_called,
            effect_authority=False,
        )
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
    records = [
        {**base,"source_id":"host_resource_runtime:plan","subject_id":"host_resource_observation_plan","stage":"observation","disposition":"recorded","payload":e.plan.to_dict(),"digest":digest(e.plan.to_dict())},
        {**base,"source_id":"host_resource_runtime:epoch","subject_id":"host_resource_observation_epoch","stage":"observation","disposition":"degraded" if e.epoch.required_failed else "recorded","payload":{"epoch_id":e.epoch.epoch_id,"status_counts":dict(e.epoch.status_counts),"collectors_called":e.epoch.collectors_called,"timed_out_collectors":e.epoch.timed_out_collectors,"admission":e.epoch.admission_decision_ref},"digest":digest({"epoch":e.epoch.semantic_digest})},
        {**base,"source_id":"host_resource_runtime:snapshot","subject_id":"host_resource_snapshot","stage":"observation","disposition":"recorded","payload":e.snapshot.to_dict(),"digest":digest(e.snapshot.to_dict())},
        {**base,"source_id":"host_resource_runtime:pressure","subject_id":"host_resource_pressure","stage":"proposal","disposition":"recorded","payload":summarize_host_resource_pressure(e.pressure_report),"digest":host_resource_report_digest(e.pressure_report)},
        {**base,"source_id":"host_resource_runtime:policy","subject_id":"host_resource_policy","stage":"proposal","disposition":e.policy_decision.status,"payload":summarize_host_resource_policy_decision(e.policy_decision),"digest":digest(e.policy_decision.to_dict())},
        {**base,"source_id":"host_resource_runtime:receipts","subject_id":"host_resource_proposal_receipts","stage":"proposal","disposition":"recorded","payload":{"receipt_count": len(e.proposal_receipts), "receipt_ids": [r.receipt_id for r in e.proposal_receipts], "receipts": [summarize_host_resource_proposal_receipt(r) for r in e.proposal_receipts]},"digest":digest([r.to_dict() for r in e.proposal_receipts])},
    ]
    return [{**item, "digest": record_digest(item)} for item in records]

def resource_consumption_world_state_records(*, ledger: GovernedLocalModelResourceLedger,
                                              invocation_receipts: Sequence[Mapping[str, Any]] = (),
                                              observed_at: str | None = None,
                                              max_receipts: int = 256,
                                              max_invocation_receipts: int = 256,
                                              max_attempts: int = 64,
                                              source_identity: Mapping[str, str] | None = None,
                                              verified_chat_process_generation_attributions: Sequence[Mapping[str, Any]] = (),
                                              verified_chat_process_recovery_transitions: Sequence[Mapping[str, Any]] = (),
                                              verified_chat_process_runtime_observation: Mapping[str, Any] | None = None,
                                              verified_serving_operation_attempts: Sequence[Mapping[str, Any]] = (),
                                              verified_serving_operation_history: Sequence[Mapping[str, Any]] = ()) -> list[dict[str, Any]]:
    """Project existing allocation/consumption custody as later evidence.

    The projection carries exact ledger identities and invocation linkage. It
    deliberately reports measured receipt fields only; host-wide telemetry is
    not attributed to an invocation without an independent receipt.
    """
    snapshot = ledger.observation_snapshot()
    if (max_receipts < 1 or max_receipts > 256 or max_invocation_receipts < 1
            or max_invocation_receipts > 256 or max_attempts < 1 or max_attempts > 128):
        raise ValueError("resource_observation_bounds_invalid")
    selected_source_identity = dict(source_identity or {})
    if (set(selected_source_identity) - {"installation_identity", "provisioning_id", "manifest_digest"}
            or any(not isinstance(key, str) or not isinstance(value, str) or not value or len(value) > 512
                   for key, value in selected_source_identity.items())):
        raise ValueError("resource_source_identity_invalid")
    raw_receipts = tuple(snapshot["receipts"])
    if len(invocation_receipts) > 256:
        raise ValueError("resource_invocation_receipt_bound_exceeded")
    if len(verified_chat_process_generation_attributions) > 256:
        raise ValueError("chat_process_generation_attribution_bound_exceeded")
    if len(verified_chat_process_recovery_transitions) > 256:
        raise ValueError("chat_process_recovery_transition_bound_exceeded")
    if len(verified_serving_operation_attempts) > 256:
        raise ValueError("serving_operation_attempt_bound_exceeded")
    invocation_by_id: dict[str, Mapping[str, Any]] = {}
    for invocation in invocation_receipts:
        if not isinstance(invocation, Mapping):
            raise ValueError("resource_invocation_receipt_invalid")
        receipt_id = invocation.get("receipt_id")
        receipt_digest = invocation.get("receipt_digest")
        if not isinstance(receipt_id, str) or not receipt_id or not isinstance(receipt_digest, str) or not receipt_digest:
            raise ValueError("resource_invocation_receipt_identity_invalid")
        if receipt_id in invocation_by_id:
            if dict(invocation_by_id[receipt_id]) != dict(invocation):
                raise ValueError("resource_invocation_receipt_identity_conflict")
            raise ValueError("resource_invocation_receipt_duplicate")
        invocation_by_id[receipt_id] = invocation
    generation_attribution_by_receipt: dict[str, Mapping[str, Any]] = {}
    attribution_fields = {"invocation_receipt_id", "invocation_receipt_digest",
        "invocation_request_id", "invocation_request_digest", "chat_process_handoff",
        "attribution_posture", "currentness_posture"}
    for attribution in verified_chat_process_generation_attributions:
        if not isinstance(attribution, Mapping) or set(attribution) != attribution_fields:
            raise ValueError("chat_process_generation_attribution_invalid")
        receipt_id, receipt_digest = (attribution.get("invocation_receipt_id"),
                                      attribution.get("invocation_receipt_digest"))
        invocation = invocation_by_id.get(str(receipt_id))
        request = invocation.get("request") if isinstance(invocation, Mapping) else None
        handoff = attribution.get("chat_process_handoff")
        if (not isinstance(receipt_id, str) or not isinstance(receipt_digest, str)
                or not isinstance(attribution.get("invocation_request_id"), str)
                or not isinstance(attribution.get("invocation_request_digest"), str)
                or not isinstance(handoff, Mapping)
                or handoff.get("status") != "runtime_launcher_process_and_source_bound"
                or not isinstance(handoff.get("process_instance_id"), str)
                or not isinstance(handoff.get("software_generation_digest"), str)
                or attribution.get("attribution_posture")
                    != "invocation_receipt_and_historical_chat_handoff_verified"
                or attribution.get("currentness_posture")
                    != "historical_process_identity_not_reobserved_during_recovery"
                or not isinstance(request, Mapping)
                or invocation.get("receipt_digest") != receipt_digest
                or invocation.get("status") != "admitted_completed"
                or not isinstance(invocation.get("effects"), Mapping)
                or invocation["effects"].get("local_model_inference") is not True
                or not isinstance(invocation.get("output_digest"), str)
                or request.get("request_id") != attribution.get("invocation_request_id")
                or request.get("request_digest") != attribution.get("invocation_request_digest")):
            raise ValueError("chat_process_generation_attribution_binding_invalid")
        prior = generation_attribution_by_receipt.get(receipt_id)
        if prior is not None:
            if dict(prior) != dict(attribution):
                raise ValueError("chat_process_generation_attribution_identity_conflict")
            raise ValueError("chat_process_generation_attribution_duplicate")
        generation_attribution_by_receipt[receipt_id] = attribution
    allocation_by_digest = {str(item.get("allocation_digest")): item for item in snapshot["allocations"] if isinstance(item, Mapping)}
    ledger_receipts = {str(item.get("receipt_digest")): item for item in raw_receipts if isinstance(item, Mapping)}
    attempt_by_id = {str(item.get("attempt_id")): item for item in snapshot["attempts"] if isinstance(item, Mapping)}
    lineage_findings: list[str] = []
    linked_effect_receipts: dict[str, str] = {}
    for invocation in invocation_receipts[-max_invocation_receipts:]:
        allocation_digest = invocation.get("resource_allocation_digest")
        attempt_id = invocation.get("resource_attempt_id")
        receipt_digests = tuple(invocation.get("resource_consumption_receipt_digests") or ())
        # Historical receipts predating resource custody have no linkage and
        # remain valid invocation evidence; they cannot be verified as resource
        # linked, but must not be reported as a lineage failure.
        if allocation_digest is None and attempt_id is None and not receipt_digests:
            continue
        allocation = allocation_by_digest.get(str(allocation_digest))
        if allocation is None:
            lineage_findings.append(f"allocation_missing:{allocation_digest}")
        attempt = attempt_by_id.get(str(attempt_id))
        if attempt is None:
            lineage_findings.append(f"attempt_missing:{attempt_id}")
        elif allocation is not None and attempt.get("allocation_id") != allocation.get("allocation_id"):
            lineage_findings.append(f"attempt_allocation_substitution:{attempt_id}")
        linked = [item for item in raw_receipts if isinstance(item, Mapping) and item.get("attempt_id") == attempt_id]
        if not receipt_digests or any(digest not in ledger_receipts for digest in receipt_digests):
            lineage_findings.append(f"consumption_receipt_missing:{attempt_id}")
        if linked and not set(receipt_digests).issubset({str(item.get("receipt_digest")) for item in linked}):
            lineage_findings.append(f"consumption_attempt_lineage_mismatch:{attempt_id}")
        for digest in receipt_digests:
            linked_receipt = ledger_receipts.get(str(digest))
            if linked_receipt is None:
                continue
            if linked_receipt.get("attempt_id") != attempt_id:
                lineage_findings.append(f"consumption_attempt_substitution:{attempt_id}")
            if allocation is not None and linked_receipt.get("allocation_digest") != allocation.get("allocation_digest"):
                lineage_findings.append(f"consumption_allocation_substitution:{attempt_id}")
            if allocation is not None and linked_receipt.get("principal_binding_digest") != allocation.get("principal_binding_digest"):
                lineage_findings.append(f"consumption_principal_substitution:{attempt_id}")
        reconciled = [item for item in linked if item.get("state") == "reconciled"]
        matching_reconciled = [item for item in reconciled if item.get("effect_receipt_digest") == invocation.get("receipt_digest")]
        if len(matching_reconciled) != 1:
            lineage_findings.append(f"effect_receipt_mismatch:{attempt_id}")
        effect_digest = str(invocation.get("receipt_digest"))
        prior_attempt = linked_effect_receipts.get(effect_digest)
        if prior_attempt is not None and prior_attempt != str(attempt_id):
            lineage_findings.append(f"effect_receipt_reused:{effect_digest}")
        linked_effect_receipts[effect_digest] = str(attempt_id)
    invocation_by_effect = {str(item.get("receipt_digest")): item for item in invocation_receipts[-max_invocation_receipts:]}
    for item in raw_receipts:
        if not isinstance(item, Mapping) or item.get("state") != "reconciled":
            continue
        effect_digest = item.get("effect_receipt_digest")
        if effect_digest is not None and effect_digest not in invocation_by_effect:
            lineage_findings.append(f"invocation_receipt_missing:{effect_digest}")
    receipt_states_by_attempt: dict[str, set[str]] = {}
    for item in raw_receipts:
        if isinstance(item, Mapping):
            receipt_states_by_attempt.setdefault(str(item.get("attempt_id")), set()).add(str(item.get("state")))
    incomplete_attempt_ids: list[str] = []
    for attempt in snapshot["attempts"]:
        if not isinstance(attempt, Mapping):
            continue
        attempt_id = str(attempt.get("attempt_id"))
        states = receipt_states_by_attempt.get(attempt_id, set())
        status = attempt.get("status")
        if (status == "provisional" or
                status == "begun" and "reconciled" not in states or
                status == "restored" and "attempted_not_begun" not in states):
            incomplete_attempt_ids.append(attempt_id)
    receipts = []
    for receipt in raw_receipts[-min(max_receipts, 16):]:
        item = dict(receipt)
        measurement = dict(item.get("resource_specific_measurement", {}))
        measurement_posture = {
            "call_units": "measured" if measurement.get("call_units_consumed") in (0, 1) else "unknown",
            "generated_output_size": "measured" if isinstance(measurement.get("generated_output_size_bytes"), int) else "unknown",
            "returned_output_size": "measured" if isinstance(measurement.get("returned_output_size_bytes"), int) else "unknown",
            "latency": "measured" if isinstance(measurement.get("latency_ms"), int) else "unknown",
            "token_count": "unknown",
            "shared_host_cpu_gpu": "unknown_without_independent_observation",
        }
        receipts.append({key: item.get(key) for key in (
            "receipt_id", "receipt_digest", "allocation_digest", "principal_binding_digest", "attempt_id",
            "state", "observed_at", "previous_receipt_digest", "effect_receipt_digest",
            "resource_specific_measurement")})
        receipts[-1]["measurement_posture"] = measurement_posture
    all_allocations = tuple(snapshot["allocations"])
    all_attempts = tuple(snapshot["attempts"])
    selected_allocations = all_allocations[-16:]
    selected_attempts = all_attempts[-max_attempts:]
    selected_invocations = tuple(invocation_receipts[-min(max_invocation_receipts, 16):])
    compact_invocations = tuple({
        "receipt_id": invocation.get("receipt_id"),
        "receipt_digest": invocation.get("receipt_digest"),
        "request_id": (invocation.get("request", {}).get("request_id")
            if isinstance(invocation.get("request"), Mapping) else None),
        "request_digest": (invocation.get("request", {}).get("request_digest")
            if isinstance(invocation.get("request"), Mapping) else None),
        "status": invocation.get("status"), "purpose": invocation.get("purpose"),
        "model_id": (invocation.get("request", {}).get("model_id")
            if isinstance(invocation.get("request"), Mapping) else None),
        "model_artifact_digest": (invocation.get("request", {}).get("model_artifact_digest")
            if isinstance(invocation.get("request"), Mapping) else None),
        "observed_at": invocation.get("observed_at"),
        "resource_allocation_digest": invocation.get("resource_allocation_digest"),
        "resource_attempt_id": invocation.get("resource_attempt_id"),
        "resource_consumption_receipt_digests": invocation.get("resource_consumption_receipt_digests"),
        "chat_process_handoff_digest": (
            generation_attribution_by_receipt.get(str(invocation.get("receipt_id")), {})
                .get("chat_process_handoff", {}).get("handoff_digest")
            if isinstance(generation_attribution_by_receipt.get(str(invocation.get("receipt_id")), {}).get(
                "chat_process_handoff"), Mapping) else None),
    } for invocation in selected_invocations)
    selected_generation_attributions = tuple(
        dict(generation_attribution_by_receipt[str(invocation.get("receipt_id"))])
        for invocation in selected_invocations
        if str(invocation.get("receipt_id")) in generation_attribution_by_receipt)
    retention_incomplete = (len(all_allocations) > 16 or len(all_attempts) > max_attempts
        or len(raw_receipts) > min(max_receipts, 16)
        or len(invocation_receipts) > min(max_invocation_receipts, 16)
        or len(incomplete_attempt_ids) > 64 or len(set(lineage_findings)) > 64)
    bounded_lineage_findings = tuple(sorted(set(lineage_findings)))
    bounded_incomplete_attempt_ids = tuple(sorted(incomplete_attempt_ids))
    payload = {"ledger_schema": snapshot["schema"], "ledger_digest": snapshot["ledger_digest"],
               "source_identity": selected_source_identity,
               "allocations": tuple(dict(item) for item in selected_allocations),
               "allocation_count": len(all_allocations),
               "attempts": tuple(dict(item) for item in selected_attempts),
               "attempt_count": len(all_attempts),
               "consumption_receipts": tuple(receipts),
               "consumption_receipt_count": len(raw_receipts),
               "invocation_receipts": compact_invocations,
               "invocation_receipt_count": len(invocation_receipts),
               "verified_chat_process_generation_attributions": selected_generation_attributions,
               "chat_process_generation_posture": (
                   "unknown_no_completed_invocations" if not any(
                       item.get("status") == "admitted_completed"
                       and isinstance(item.get("effects"), Mapping)
                       and item["effects"].get("local_model_inference") is True
                       for item in invocation_receipts)
                   else "verified" if len(generation_attribution_by_receipt) == sum(
                       1 for item in invocation_receipts
                       if item.get("status") == "admitted_completed"
                       and isinstance(item.get("effects"), Mapping)
                       and item["effects"].get("local_model_inference") is True)
                   else "partial_legacy_or_unavailable" if generation_attribution_by_receipt
                   else "unknown_legacy_or_unavailable"),
               "attribution_posture": "receipt_bound_only",
               "shared_host_usage_attribution": "unknown_without_independent_observation",
               "retention_posture": "bounded_tail_incomplete" if retention_incomplete else "complete",
               "recovery_posture": "incomplete_attempts_present" if incomplete_attempt_ids else "reconciled_or_restored",
               "incomplete_attempt_ids": bounded_incomplete_attempt_ids[:64],
               "incomplete_attempt_count": len(bounded_incomplete_attempt_ids),
               "lineage_posture": "verified" if not lineage_findings else "degraded",
               "lineage_findings": bounded_lineage_findings[:64],
               "lineage_finding_count": len(bounded_lineage_findings)}
    record = {"source_kind": WorldStateSourceKind.RESOURCE_GOVERNOR.value,
             "source_id": "governed_local_model_resource_consumption",
             "schema_version": RESOURCE_CONSUMPTION_WORLD_STATE_SCHEMA,
             "subject_kind": "causal_resource_consumption",
             "subject_id": str(snapshot["ledger_digest"]), "stage": "observation",
             "disposition": "recorded" if not lineage_findings and payload["recovery_posture"] == "reconciled_or_restored" else "degraded", "evidence_strength": "receipt_bound" if not lineage_findings and payload["recovery_posture"] == "reconciled_or_restored" else "incomplete",
             "effect_claimed": False, "effect_proven": False,
             # The ledger receipt's event time is historical custody. Do not
             # let a restart/reprojection timestamp make old consumption
             # appear to be a fresh observation to epistemic consumers.
             "observed_at": None, "retrieved_at": observed_at, "payload": payload}
    output = [{**record, "digest": record_digest(record)}]
    for attribution in selected_generation_attributions:
        handoff = attribution["chat_process_handoff"]
        invocation = invocation_by_id[str(attribution["invocation_receipt_id"])]
        request = invocation.get("request") if isinstance(invocation, Mapping) else {}
        payload = {
            "invocation_receipt_id": attribution["invocation_receipt_id"],
            "invocation_receipt_digest": attribution["invocation_receipt_digest"],
            "invocation_request_id": attribution["invocation_request_id"],
            "invocation_request_digest": attribution["invocation_request_digest"],
            "chat_process_handoff": dict(handoff),
            "verified_chat_process_generation_attributions": [dict(attribution)],
            "software_generation_digest": handoff.get("software_generation_digest"),
            "process_instance_id": handoff.get("process_instance_id"),
            "process_startup_timestamp": handoff.get("startup_timestamp"),
            "invocation_observed_at": invocation.get("observed_at"),
            "invocation_time_posture": "receipt_custody_metadata_not_in_semantic_digest",
            "attribution_posture": attribution["attribution_posture"],
            "process_currentness": attribution["currentness_posture"],
            "invocation_status": invocation.get("status"),
            "resource_allocation_digest": invocation.get("resource_allocation_digest"),
            "resource_attempt_id": invocation.get("resource_attempt_id"),
            "resource_consumption_receipt_digests": list(
                invocation.get("resource_consumption_receipt_digests") or ()),
            "resource_effect_receipt_digest": invocation.get("receipt_digest"),
            "resource_lineage_posture": "invocation_bound_ledger_reconciliation_is_sibling_evidence",
            "model_id": request.get("model_id") if isinstance(request, Mapping) else None,
            "model_artifact_digest": request.get("model_artifact_digest") if isinstance(request, Mapping) else None,
            "active_model_identity": request.get("active_model_identity") if isinstance(request, Mapping) else None,
            "installation_identity": selected_source_identity.get("installation_identity"),
            "provisioning_id": selected_source_identity.get("provisioning_id"),
            "manifest_digest": selected_source_identity.get("manifest_digest"),
            "historical_only": True,
            "effect_authority": False,
        }
        source_id = ("chat_process_invocation:" + str(attribution["invocation_receipt_id"])
            + ":" + str(attribution["invocation_receipt_digest"])
            + ":" + str(handoff.get("handoff_digest", "")))
        upstream = request.get("upstream_evidence") if isinstance(request, Mapping) else None
        serving = (upstream.get("current_serving_lifetime")
            if isinstance(upstream, Mapping) else None)
        serving_fields = ("serving_session_id", "serving_operation_id", "installation_identity",
            "activation_state_semantic_digest", "activation_generation",
            "activation_predecessor_state_digest", "activation_receipt_id",
            "activation_receipt_semantic_digest", "serving_receipt_id",
            "serving_receipt_semantic_digest", "serving_operation_attempt_id",
            "serving_operation_attempt_semantic_digest", "model_serving_admission_ref",
            "authority_map_digest", "artifact_id", "artifact_sha256", "runtime_id")
        serving_binding = ({key: serving[key] for key in serving_fields if key in serving}
            if isinstance(serving, Mapping) else {})
        payload["chat_model_serving_lineage"] = {
            "invocation_receipt_id": attribution["invocation_receipt_id"],
            "invocation_receipt_digest": attribution["invocation_receipt_digest"],
            "invocation_request_id": attribution["invocation_request_id"],
            "invocation_request_digest": attribution["invocation_request_digest"],
            "installation_identity": selected_source_identity.get("installation_identity"),
            "provisioning_id": selected_source_identity.get("provisioning_id"),
            "resource_allocation_digest": invocation.get("resource_allocation_digest"),
            "resource_attempt_id": invocation.get("resource_attempt_id"),
            "resource_consumption_receipt_digests": list(
                invocation.get("resource_consumption_receipt_digests") or ()),
            "resource_linkage_digest": invocation.get("resource_linkage_digest"),
            "software_handoff_id": handoff.get("handoff_id"),
            "software_handoff_digest": handoff.get("handoff_digest"),
            "software_process_instance_id": handoff.get("process_instance_id"),
            "software_generation_digest": handoff.get("software_generation_digest"),
            "software_generation_startup_timestamp": handoff.get("startup_timestamp"),
            "serving_identity": serving_binding,
            "active_model_identity": (request.get("active_model_identity")
                if isinstance(request, Mapping) else None),
            "model_id": request.get("model_id") if isinstance(request, Mapping) else None,
            "model_artifact_digest": request.get("model_artifact_digest")
                if isinstance(request, Mapping) else None,
            "relation_posture": "co_bound_by_completed_invocation_request_and_receipt",
            "currentness": "historical_only",
            "effect_authority": False,
        }
        item = {
            "source_kind": WorldStateSourceKind.RESOURCE_GOVERNOR.value,
            "source_id": source_id,
            "subject_kind": "chat_process_software_generation_invocation",
            "subject_id": str(handoff.get("process_instance_id")),
            "stage": "observation", "disposition": "recorded",
            "evidence_strength": "child_handoff_bound_completed_invocation_receipt",
            "effect_claimed": False, "effect_proven": False,
            "observed_at": None, "retrieved_at": observed_at,
            "payload": payload,
        }
        output.append({**item, "digest": record_digest(item)})
    recovery_required_fields = {
        "request_id", "request_semantic_digest", "intent_id", "intent_semantic_digest",
        "approval_id", "approval_semantic_digest", "installation_identity",
        "runtime_supervisor_generation", "prior_serving_operation_id",
        "replacement_serving_operation_id", "prior_serving_receipt_id",
        "prior_serving_receipt_semantic_digest", "attempt_phase_digest", "readiness_phase_digest",
        "completion_phase_digest", "attempt_started_at", "readiness_observed_at",
        "snapshot_advanced_at", "advanced_snapshot_digest", "decision_outcome_claimed",
        "decision_reference_claimed", "decision_posture", "predecessor_chat_process_handoff",
        "successor_chat_process_handoff", "handoff_lineage_posture", "terminal_receipt_digest",
        "terminal_status", "successor_serving_receipt_id",
        "successor_serving_receipt_semantic_digest", "successor_serving_session_id",
        "successor_serving_receipt_posture", "predecessor_serving_operation_binding_posture",
        "successor_serving_operation_binding_posture", "successor_configured_serving_operation_id",
        "phase_posture", "phase_evidence_posture", "runtime_currentness", "effect_authority",
        "inference_performed",
    }
    seen_recovery: dict[str, Mapping[str, Any]] = {}
    for transition in verified_chat_process_recovery_transitions:
        if not isinstance(transition, Mapping) or set(transition) != recovery_required_fields:
            raise ValueError("chat_process_recovery_transition_shape_invalid")
        request_id = transition.get("request_id")
        attempt_digest = transition.get("attempt_phase_digest")
        if (not isinstance(request_id, str) or not request_id
                or not isinstance(attempt_digest, str) or re.fullmatch(r"[0-9a-f]{64}", attempt_digest) is None
                or transition.get("installation_identity") != selected_source_identity.get("installation_identity")
                or transition.get("decision_posture") != "phase_claim_not_reauthorized"
                or transition.get("phase_evidence_posture")
                    != "canonical_installation_custody_and_digest_chain_checked_not_independently_signed"
                or transition.get("runtime_currentness")
                    != "historical_process_identity_not_reobserved_during_recovery"
                or transition.get("successor_serving_receipt_posture") not in {
                    "verified_historical_custody", "verified_historical_custody_and_operation_binding",
                    "verified_receipt_legacy_handoff_operation_unknown", "legacy_or_missing"}
                or transition.get("predecessor_serving_operation_binding_posture") not in {
                    "exact_handoff_launch_operation_binding", "legacy_handoff_operation_unknown",
                    "handoff_unavailable"}
                or transition.get("successor_serving_operation_binding_posture") not in {
                    "exact_handoff_launch_operation_binding", "legacy_handoff_operation_unknown",
                    "handoff_unavailable"}
                or any(transition.get(key) is not None and (
                    not isinstance(transition.get(key), str) or not transition.get(key)
                    or len(transition[key]) > 128) for key in (
                        "prior_serving_operation_id", "replacement_serving_operation_id",
                        "successor_configured_serving_operation_id"))
                or (transition.get("predecessor_serving_operation_binding_posture")
                    == "exact_handoff_launch_operation_binding"
                    and (not isinstance(transition.get("predecessor_chat_process_handoff"), Mapping)
                        or transition["predecessor_chat_process_handoff"].get(
                            "configured_serving_operation_id")
                            != transition.get("prior_serving_operation_id")))
                or (transition.get("successor_serving_operation_binding_posture")
                    == "exact_handoff_launch_operation_binding"
                    and (not isinstance(transition.get("successor_chat_process_handoff"), Mapping)
                        or transition["successor_chat_process_handoff"].get(
                            "configured_serving_operation_id")
                            != transition.get("replacement_serving_operation_id")
                        or transition.get("successor_configured_serving_operation_id")
                            != transition.get("replacement_serving_operation_id")))
                or transition.get("effect_authority") is not False
                or transition.get("inference_performed") is not False):
            raise ValueError("chat_process_recovery_transition_binding_invalid")
        prior_transition = seen_recovery.get(request_id)
        if prior_transition is not None:
            if dict(prior_transition) != dict(transition):
                raise ValueError("chat_process_recovery_transition_identity_conflict")
            raise ValueError("chat_process_recovery_transition_duplicate")
        seen_recovery[request_id] = transition
    for transition in verified_chat_process_recovery_transitions:
        request_id = str(transition["request_id"])
        payload = {
            "installation_identity": selected_source_identity.get("installation_identity"),
            "provisioning_id": selected_source_identity.get("provisioning_id"),
            "manifest_digest": selected_source_identity.get("manifest_digest"),
            "chat_process_recovery_transition": dict(transition),
            "phase_event_times": {
                "attempt_started_at": transition.get("attempt_started_at"),
                "readiness_observed_at": transition.get("readiness_observed_at"),
                "snapshot_advanced_at": transition.get("snapshot_advanced_at"),
            },
            "observation_time": None,
            "retrieval_time": observed_at,
            "historical_only": True,
            "phase_claim_is_not_reauthorization": True,
            "runtime_currentness": transition.get("runtime_currentness"),
            "effect_authority": False,
            "inference_performed": False,
        }
        terminal_present = isinstance(transition.get("terminal_receipt_digest"), str)
        transition_evidence_digest = (
            transition.get("terminal_receipt_digest")
            or transition.get("completion_phase_digest")
            or transition.get("readiness_phase_digest")
            or attempt_digest)
        if (not isinstance(transition_evidence_digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", transition_evidence_digest) is None):
            raise ValueError("chat_process_recovery_transition_evidence_identity_invalid")
        item = {
            "source_kind": WorldStateSourceKind.RUNTIME_SUPERVISOR.value,
            "source_id": ("chat_process_recovery:" + str(selected_source_identity.get("installation_identity", ""))
                + ":" + request_id + ":" + transition_evidence_digest),
            "subject_kind": "chat_process_recovery_transition",
            "subject_id": request_id,
            "stage": "observation",
            "disposition": "recorded" if terminal_present else "incomplete",
            "evidence_strength": "phase_chain_with_terminal_receipt" if terminal_present
                else "phase_chain_terminal_receipt_missing",
            "effect_claimed": False,
            "effect_proven": False,
            "observed_at": None,
            "retrieved_at": observed_at,
            "payload": payload,
        }
        output.append({**item, "digest": record_digest(item)})
    if verified_chat_process_runtime_observation is not None:
        runtime = verified_chat_process_runtime_observation
        base_runtime_fields = {
            "schema_version", "installation_identity", "runtime_supervisor_generation", "observed_at",
            "runtime_status", "reason_code", "handoff_id", "handoff_digest", "process_instance_id",
            "process_id", "parent_process_id", "software_generation_digest", "source_generation_scope",
            "currentness_posture", "independent_signature", "effect_authority",
            "observation_semantic_digest",
        }
        runtime_schema = runtime.get("schema_version") if isinstance(runtime, Mapping) else None
        if runtime_schema == "sentientos.chat_process_runtime_observation:v1":
            runtime_fields = base_runtime_fields
        elif runtime_schema in {"sentientos.chat_process_runtime_observation:v2",
                "sentientos.chat_process_runtime_observation:v3"}:
            runtime_fields = base_runtime_fields | {"configured_serving_receipt_posture", "serving_receipt"}
            if runtime_schema == "sentientos.chat_process_runtime_observation:v3":
                runtime_fields = runtime_fields | {"configured_serving_operation_id"}
        else:
            runtime_fields = set()
        serving = runtime.get("serving_receipt") if isinstance(runtime, Mapping) else None
        serving_posture = runtime.get("configured_serving_receipt_posture") if isinstance(runtime, Mapping) else None
        serving_valid = (
            (runtime_schema == "sentientos.chat_process_runtime_observation:v1"
                and serving is None and serving_posture is None)
            or (runtime_schema in {"sentientos.chat_process_runtime_observation:v2",
                    "sentientos.chat_process_runtime_observation:v3"}
                and (
                    (serving_posture == "selected_receipt_for_configured_operation"
                        and isinstance(serving, Mapping)
                        and serving.get("selection_posture") == serving_posture
                        and serving.get("model_loaded_in_receipt") is True
                        and isinstance(serving.get("receipt_id"), str)
                        and isinstance(serving.get("receipt_semantic_digest"), str)
                        and isinstance(serving.get("serving_operation_id"), str)
                        and isinstance(serving.get("model_identity_in_receipt"), Mapping))
                    or (serving is None and serving_posture in {
                        "not_observed", "configured_operation_not_verified",
                        "configured_operation_receipt_unavailable",
                        "configured_operation_receipt_invalid", "runtime_not_verified"})
                ))
        )
        operation_binding_valid = (
            runtime_schema != "sentientos.chat_process_runtime_observation:v3"
            or (runtime.get("configured_serving_operation_id") is None
                or isinstance(runtime.get("configured_serving_operation_id"), str)
                and bool(runtime.get("configured_serving_operation_id"))
                and len(runtime["configured_serving_operation_id"]) <= 128)
            and (serving is None
                or runtime.get("configured_serving_operation_id")
                    == serving.get("serving_operation_id"))
        )
        if (not isinstance(runtime, Mapping) or set(runtime) != runtime_fields
                or not serving_valid or not operation_binding_valid
                or runtime.get("installation_identity") != selected_source_identity.get("installation_identity")
                or runtime.get("runtime_status") not in {"running_observed", "not_verified"}
                or runtime.get("currentness_posture") != "runtime_owner_observed_at_recorded_event_time"
                or runtime.get("independent_signature") is not False
                or runtime.get("effect_authority") is not False
                or not isinstance(runtime.get("observation_semantic_digest"), str)
                or re.fullmatch(r"[0-9a-f]{64}", runtime["observation_semantic_digest"]) is None
                or not isinstance(runtime.get("handoff_digest"), str)
                or re.fullmatch(r"[0-9a-f]{64}", runtime["handoff_digest"]) is None
                or not isinstance(runtime.get("observed_at"), str)
                or runtime.get("observation_semantic_digest")
                    != semantic_digest({key: value for key, value in runtime.items()
                        if key != "observation_semantic_digest"})):
            raise ValueError("chat_process_runtime_observation_binding_invalid")
        linked_invocations: list[dict[str, Any]] = []
        for attribution in selected_generation_attributions:
            handoff = attribution.get("chat_process_handoff")
            if (not isinstance(handoff, Mapping)
                    or handoff.get("handoff_id") != runtime.get("handoff_id")
                    or handoff.get("handoff_digest") != runtime.get("handoff_digest")
                    or handoff.get("process_instance_id") != runtime.get("process_instance_id")):
                continue
            invocation = invocation_by_id.get(str(attribution.get("invocation_receipt_id")))
            request = invocation.get("request") if isinstance(invocation, Mapping) else None
            if not isinstance(invocation, Mapping) or not isinstance(request, Mapping):
                raise ValueError("chat_process_runtime_invocation_join_missing")
            linked_invocations.append({
                "invocation_receipt_id": invocation.get("receipt_id"),
                "invocation_receipt_digest": invocation.get("receipt_digest"),
                "invocation_request_id": request.get("request_id"),
                "invocation_request_digest": request.get("request_digest"),
                "resource_allocation_digest": invocation.get("resource_allocation_digest"),
                "resource_attempt_id": invocation.get("resource_attempt_id"),
                "resource_consumption_receipt_digests": list(
                    invocation.get("resource_consumption_receipt_digests") or ()),
                "resource_effect_receipt_digest": invocation.get("receipt_digest"),
                "model_id": request.get("model_id"),
                "model_artifact_digest": request.get("model_artifact_digest"),
                "active_model_identity_at_invocation": request.get("active_model_identity"),
                "linkage_posture": "exact_shared_verified_chat_process_handoff",
                "current_model_claimed": False,
            })
        if len(linked_invocations) > 16:
            raise ValueError("chat_process_runtime_invocation_join_bound_exceeded")
        runtime_projection_digest = digest({
            "runtime_observation_semantic_digest": runtime["observation_semantic_digest"],
            "linked_invocation_receipts": linked_invocations,
        })
        item = {
            "source_kind": WorldStateSourceKind.RUNTIME_SUPERVISOR.value,
            "source_id": ("chat_process_runtime_observation:"
                + runtime["installation_identity"] + ":" + runtime_projection_digest),
            "subject_kind": "chat_process_runtime_generation_observation",
            "subject_id": str(runtime.get("process_instance_id", "")),
            "stage": "observation",
            "disposition": "recorded",
            "evidence_strength": "runtime_owner_child_handoff_checked_at_event_time"
                if runtime["runtime_status"] == "running_observed"
                else "runtime_owner_child_identity_not_verified_at_event_time",
            "effect_claimed": False, "effect_proven": False,
            "observed_at": None,
            "retrieved_at": observed_at,
            "payload": {
                "installation_identity": runtime["installation_identity"],
                "provisioning_id": selected_source_identity.get("provisioning_id"),
                "manifest_digest": selected_source_identity.get("manifest_digest"),
                "chat_process_runtime_observation": dict(runtime),
                "linked_invocation_receipts": linked_invocations,
                "invocation_linkage_posture": "exact_shared_chat_process_handoff"
                    if linked_invocations else "no_matching_retained_invocation_receipts",
                "event_time": runtime["observed_at"],
                "event_time_posture": "runtime_owner_observation_not_current_liveness",
                "currentness": "unknown_after_observation_time",
                "historical_only": True,
                "effect_authority": False,
            },
        }
        output.append({**item, "digest": record_digest(item)})
    seen_serving_attempts: dict[str, Mapping[str, Any]] = {}
    expected_attempt_fields = {
        "schema_version", "attempt_id", "installation_identity", "serving_operation_id",
        "activation_state_semantic_digest", "activation_generation", "model_id",
        "operation_intent_digest", "admission_decision_ref", "reserved_at", "attempt_posture",
        "current_model_claimed", "inference_performed", "effect_authority",
        "independent_signature", "attempt_semantic_digest",
    }
    for attempt in verified_serving_operation_attempts:
        if not isinstance(attempt, Mapping) or set(attempt) != expected_attempt_fields:
            raise ValueError("serving_operation_attempt_shape_invalid")
        attempt_id = attempt.get("attempt_id")
        attempt_digest = attempt.get("attempt_semantic_digest")
        if (attempt.get("schema_version") != "sentientos.local_model_serving_operation_attempt:v1"
                or not isinstance(attempt_id, str) or not attempt_id
                or not isinstance(attempt_digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", attempt_digest) is None
                or attempt.get("installation_identity")
                    != selected_source_identity.get("installation_identity")
                or not isinstance(attempt.get("serving_operation_id"), str)
                or not attempt.get("serving_operation_id")
                or attempt.get("attempt_posture") != "durably_reserved_before_model_load"
                or attempt.get("current_model_claimed") is not False
                or attempt.get("inference_performed") is not False
                or attempt.get("effect_authority") is not False
                or attempt.get("independent_signature") is not False
                or attempt_digest != semantic_digest({
                    key: value for key, value in attempt.items()
                    if key != "attempt_semantic_digest"})):
            raise ValueError("serving_operation_attempt_binding_invalid")
        identity = {
            "installation_identity": attempt["installation_identity"],
            "serving_operation_id": attempt["serving_operation_id"],
            "activation_state_semantic_digest": attempt["activation_state_semantic_digest"],
        }
        if attempt_id != "serving-attempt-" + semantic_digest(identity)[:24]:
            raise ValueError("serving_operation_attempt_identity_mismatch")
        previous_attempt = seen_serving_attempts.get(attempt_id)
        if previous_attempt is not None:
            if dict(previous_attempt) != dict(attempt):
                raise ValueError("serving_operation_attempt_identity_conflict")
            raise ValueError("serving_operation_attempt_duplicate")
        seen_serving_attempts[attempt_id] = attempt
        item = {
            "source_kind": WorldStateSourceKind.RUNTIME_SUPERVISOR.value,
            "source_id": "serving_operation_attempt:" + attempt_id + ":" + attempt_digest,
            "subject_kind": "serving_operation_attempt",
            "subject_id": attempt_id,
            "stage": "attempt",
            "disposition": "recorded",
            "evidence_strength": "durable_reservation_model_load_outcome_unknown",
            "effect_claimed": False, "effect_proven": False,
            "observed_at": None, "retrieved_at": observed_at,
            "payload": {
                "installation_identity": attempt["installation_identity"],
                "provisioning_id": selected_source_identity.get("provisioning_id"),
                "manifest_digest": selected_source_identity.get("manifest_digest"),
                "serving_operation_attempt": dict(attempt),
                "event_time": attempt["reserved_at"],
                "event_time_posture": "reservation_time_not_model_load_time",
                "model_load_outcome": "unknown",
                "resource_consumption_measurements": "unknown",
                "current_model_claimed": False,
                "inference_performed": False,
                "effect_authority": False,
                "independent_signature": False,
                "historical_only": True,
            },
        }
        output.append({**item, "digest": record_digest(item)})
    for history in verified_serving_operation_history:
        if (not isinstance(history, Mapping)
                or set(history) != {"status", "attempt", "attempt_semantic_digest", "receipt",
                    "receipt_semantic_digest", "history_semantic_digest"}
                or history.get("history_semantic_digest") != semantic_digest({
                    key: value for key, value in history.items()
                    if key != "history_semantic_digest"})):
            raise ValueError("serving_operation_history_binding_invalid")
        attempt = history.get("attempt")
        receipt = history.get("receipt")
        status = history.get("status")
        if attempt is not None:
            if (not isinstance(attempt, Mapping)
                    or attempt.get("installation_identity")
                        != selected_source_identity.get("installation_identity")
                    or attempt.get("attempt_semantic_digest")
                        != history.get("attempt_semantic_digest")):
                raise ValueError("serving_operation_history_attempt_invalid")
            subject_id = str(attempt.get("attempt_id"))
            operation_id = str(attempt.get("serving_operation_id"))
        else:
            if not isinstance(receipt, Mapping) or status != "legacy_receipt_without_reservation":
                raise ValueError("serving_operation_history_legacy_invalid")
            binding = receipt.get("binding")
            if (not isinstance(binding, Mapping)
                    or binding.get("installation_identity")
                        != selected_source_identity.get("installation_identity")):
                raise ValueError("serving_operation_history_receipt_invalid")
            subject_id = str(receipt.get("receipt_id"))
            operation_id = str(binding.get("serving_operation_id"))
        if status not in {"serving_receipt_verified", "reservation_outcome_unknown",
                          "legacy_receipt_without_reservation"}:
            raise ValueError("serving_operation_history_status_invalid")
        if receipt is not None:
            if (not isinstance(receipt, Mapping)
                    or receipt.get("receipt_semantic_digest")
                        != history.get("receipt_semantic_digest")):
                raise ValueError("serving_operation_history_receipt_invalid")
            binding = receipt.get("binding")
            if not isinstance(binding, Mapping) or binding.get("serving_operation_id") != operation_id:
                raise ValueError("serving_operation_history_operation_mismatch")
            loaded_at = receipt.get("model_loaded_at")
            event_time_posture = "owner_observed_model_load_time"
            evidence_strength = "owner_receipt_model_loaded_historical"
            receipt_id = receipt.get("receipt_id")
            receipt_digest = receipt.get("receipt_semantic_digest")
            model_identity = receipt.get("binding", {}).get("observed_loaded_model_identity")
            serving_session_id = receipt.get("session_id")
        else:
            if status != "reservation_outcome_unknown" or attempt is None:
                raise ValueError("serving_operation_history_missing_receipt_invalid")
            loaded_at = attempt.get("reserved_at")
            event_time_posture = "reservation_time_model_load_outcome_unknown"
            evidence_strength = "durable_serving_operation_reservation_outcome_unknown"
            receipt_id = receipt_digest = serving_session_id = model_identity = None
            binding = {}
        payload = {
            "installation_identity": selected_source_identity.get("installation_identity"),
            "provisioning_id": selected_source_identity.get("provisioning_id"),
            "manifest_digest": selected_source_identity.get("manifest_digest"),
            "serving_operation_id": operation_id,
            "attempt_id": attempt.get("attempt_id") if isinstance(attempt, Mapping) else None,
            "attempt_semantic_digest": history.get("attempt_semantic_digest"),
            "receipt_id": receipt_id,
            "receipt_semantic_digest": receipt_digest,
            "serving_session_id": serving_session_id,
            "activation_state_semantic_digest": binding.get("activation_state_semantic_digest",
                attempt.get("activation_state_semantic_digest") if isinstance(attempt, Mapping) else None),
            "activation_generation": binding.get("activation_generation",
                attempt.get("activation_generation") if isinstance(attempt, Mapping) else None),
            "model_id": binding.get("model_id",
                attempt.get("model_id") if isinstance(attempt, Mapping) else None),
            "artifact_id": binding.get("artifact_id"),
            "runtime_id": binding.get("runtime_id"),
            "observed_loaded_model_identity": model_identity,
            "event_time": loaded_at,
            "event_time_posture": event_time_posture,
            "serving_history_status": status,
            "current_model_claimed": False,
            "inference_performed": False,
            "effect_authority": False,
            "resource_consumption_measurements": "unknown",
            "historical_only": True,
        }
        item = {
            "source_kind": WorldStateSourceKind.RUNTIME_SUPERVISOR.value,
            "source_id": "serving_operation_history:" + history["history_semantic_digest"],
            "subject_kind": "serving_operation_history",
            "subject_id": subject_id,
            "stage": "history",
            "disposition": "recorded",
            "evidence_strength": evidence_strength,
            "effect_claimed": False, "effect_proven": False,
            "observed_at": None, "retrieved_at": observed_at,
            "payload": payload,
        }
        output.append({**item, "digest": record_digest(item)})
    return output


def resource_invocation_proposal_lineage_records(records: Sequence[Mapping[str, Any]],
        *, max_records: int = 16, include_model_replacement: bool = True) -> list[dict[str, Any]]:
    """Join selected strategy/model inference records to projected resource custody.

    This is a read-only cross-source reconciliation. It emits historical
    attribution only; the invocation receipt is not an external consequence,
    and missing or tail-truncated ledger evidence stays degraded.
    """
    if not 1 <= max_records <= 32:
        raise ValueError("resource_proposal_join_bound_invalid")
    from sentientos.local_model_authority import digest_payload

    resource_rows = [dict(item) for item in records
        if item.get("source_kind") == WorldStateSourceKind.RESOURCE_GOVERNOR.value
        and item.get("subject_kind") == "causal_resource_consumption"]
    proposal_rows = [dict(item) for item in records
        if item.get("source_kind") == "embodiment"
        and item.get("subject_kind") == "embodied_strategy_proposal"]
    model_replacement_candidates: dict[str, dict[str, Any]] = {}
    if include_model_replacement:
        for run in records:
            if (run.get("source_kind") != "embodiment"
                    or run.get("subject_kind") != "developmental_model_replacement_experiment"
                    or not isinstance(run.get("payload"), Mapping)):
                continue
            run_payload = run["payload"]
            observations = run_payload.get("observations", ())
            if not isinstance(observations, (list, tuple)):
                continue
            for observation in observations[:5]:
                if not isinstance(observation, Mapping) or observation.get(
                        "resource_attribution_posture") != "linkage_digest_bound_ledger_reconciliation_pending":
                    continue
                semantic_observation = {key: value for key, value in observation.items()
                    if key not in {"observation_id", "observation_digest"}}
                candidate_findings = []
                if (run.get("digest") != record_digest(run)
                        or observation.get("observation_digest") != "sha256:" + digest_payload(semantic_observation)):
                    candidate_findings.append("model_replacement_source_binding_invalid")
                consumption = observation.get("resource_consumption_receipt_digests")
                if not isinstance(consumption, (list, tuple)):
                    candidate_findings.append("model_replacement_resource_linkage_shape_invalid")
                    consumption = ()
                request_context = {"experiment_condition": observation.get("condition_id"),
                    "experiment_protocol_id": run_payload.get("protocol_id"),
                    "history_record_ids": list(observation.get("history_record_ids") or ()),
                    "history_record_digests": list(observation.get("history_record_digests") or ()),
                    "history_withheld": observation.get("history_withheld")}
                linkage = {"posture": "invocation_receipt_bound_ledger_corroboration_not_performed",
                    "request_id": observation.get("request_id"),
                    "request_digest": observation.get("request_digest"),
                    "purpose": "resident_developmental_model_replacement_experiment",
                    "model_id": observation.get("model_id"),
                    "model_artifact_digest": observation.get("model_artifact_digest"),
                    "allocation_digest": observation.get("resource_allocation_digest"),
                    "attempt_id": observation.get("resource_attempt_id"),
                    "consumption_receipt_digests": list(consumption),
                    "linkage_digest": observation.get("resource_linkage_digest"),
                    "effect_receipt_id": observation.get("inference_receipt_id"),
                    "effect_receipt_digest": observation.get("inference_receipt_digest")}
                candidate_id = str(observation.get("observation_id") or "")
                synthetic = {"source_kind": "embodiment",
                    "source_id": "model-replacement-invocation-candidate:" + candidate_id,
                    "subject_id": candidate_id, "subject_kind": "embodied_strategy_proposal",
                    "payload": {"resource_linkage": linkage,
                        "invocation_request_context_linkage": request_context,
                        "invocation_receipt_id": linkage["effect_receipt_id"],
                        "invocation_receipt_digest": linkage["effect_receipt_digest"],
                        "active_model_identity_digest": observation.get("model_identity_digest"),
                        "declared_software_generation": run_payload.get("software_generation_identity"),
                        "software_generation_posture": run_payload.get("software_generation_posture"),
                        "software_execution_provenance_digest": None,
                        "_lineage_findings": candidate_findings,
                        "_model_replacement_run_id": run_payload.get("run_id"),
                        "_model_replacement_run_digest": run_payload.get("run_digest"),
                        "_model_replacement_source_record_id": run.get("source_id"),
                        "_model_replacement_source_record_digest": run.get("digest"),
                        "_model_replacement_condition": observation.get("condition_id"),
                        "_model_identity_digest": observation.get("model_identity_digest"),
                        "_model_provenance_digest": observation.get("model_provenance_manifest_digest"),
                        "_causal_context_id": observation.get("causal_context_id"),
                        "_causal_context_digest": observation.get("causal_context_digest")}}
                synthetic["digest"] = record_digest(synthetic)
                model_replacement_candidates[str(synthetic["source_id"])] = synthetic["payload"]
                proposal_rows.append(synthetic)
    linked_candidates = [item for item in proposal_rows
        if isinstance(item.get("payload"), Mapping)
        and isinstance(item["payload"].get("resource_linkage"), Mapping)
        and (item["payload"]["resource_linkage"].get("posture") != "legacy_or_unlinked_invocation"
            or any(item["payload"]["resource_linkage"].get(key) for key in (
                "allocation_digest", "attempt_id", "consumption_receipt_digests", "linkage_digest")))]
    receipt_event_times: dict[str, set[str]] = {}
    for resource in resource_rows:
        resource_payload = resource.get("payload")
        if (resource.get("digest") != record_digest(resource)
                or not isinstance(resource_payload, Mapping)
                or resource_payload.get("lineage_posture") != "verified"
                or resource_payload.get("recovery_posture") != "reconciled_or_restored"
                or resource_payload.get("retention_posture") != "complete"):
            continue
        for receipt in resource_payload.get("consumption_receipts", ()):
            if (isinstance(receipt, Mapping) and isinstance(receipt.get("receipt_digest"), str)
                    and isinstance(receipt.get("observed_at"), str)):
                receipt_event_times.setdefault(str(receipt["receipt_digest"]), set()).add(
                    str(receipt["observed_at"]))

    def candidate_event_order(item: Mapping[str, Any]) -> tuple[int, datetime, str]:
        unknown_time = datetime.min.replace(tzinfo=timezone.utc)
        payload = item.get("payload")
        linkage = payload.get("resource_linkage") if isinstance(payload, Mapping) else None
        receipt_digests = linkage.get("consumption_receipt_digests") if isinstance(linkage, Mapping) else None
        if not isinstance(receipt_digests, (tuple, list)) or not receipt_digests:
            return (0, unknown_time, str(item.get("source_id", "")))
        instants: list[datetime] = []
        for receipt_digest in receipt_digests:
            candidates = receipt_event_times.get(str(receipt_digest), set())
            if len(candidates) != 1:
                return (0, unknown_time, str(item.get("source_id", "")))
            try:
                event_time = datetime.fromisoformat(next(iter(candidates)).replace("Z", "+00:00"))
                if event_time.tzinfo is None or event_time.utcoffset() is None:
                    return (0, unknown_time, str(item.get("source_id", "")))
                instants.append(event_time.astimezone(timezone.utc))
            except (OverflowError, OSError, ValueError):
                return (0, unknown_time, str(item.get("source_id", "")))
        return (1, max(instants), str(item.get("source_id", "")))

    # Keep the newest receipt-bound events inside the projection bound. Unknown
    # or conflicting timestamps sort before actual parsed event times; they do
    # not receive a synthetic current timestamp. Omission remains digest-bound.
    linked_candidates.sort(key=candidate_event_order)
    omitted_candidates = linked_candidates[:-max_records]
    proposal_rows = linked_candidates[-max_records:]
    output: list[dict[str, Any]] = []
    for proposal in proposal_rows[-max_records:]:
        payload = proposal.get("payload")
        if not isinstance(payload, Mapping):
            continue
        linkage = payload.get("resource_linkage")
        if not isinstance(linkage, Mapping):
            continue
        findings: list[str] = []
        findings.extend(str(item) for item in linkage.get("_lineage_findings", ())
            if isinstance(item, str))
        if linkage.get("posture") != "invocation_receipt_bound_ledger_corroboration_not_performed":
            findings.append("invocation_resource_linkage_posture_unrecognized")
        allocations: list[Mapping[str, Any]] = []
        ledger_receipts: list[Mapping[str, Any]] = []
        if proposal.get("digest") != record_digest(proposal):
            findings.append("strategy_proposal_record_digest_invalid")
        matches: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
        for resource in resource_rows:
            resource_payload = resource.get("payload")
            if resource.get("digest") != record_digest(resource) or not isinstance(resource_payload, Mapping):
                continue
            for invocation in resource_payload.get("invocation_receipts", ()):
                if (isinstance(invocation, Mapping)
                        and invocation.get("receipt_id") == linkage.get("effect_receipt_id")
                        and invocation.get("receipt_digest") == linkage.get("effect_receipt_digest")):
                    matches.append((resource, invocation))
        resource_record: Mapping[str, Any] | None = None
        invocation_row: Mapping[str, Any] | None = None
        if len(matches) != 1:
            findings.append("resource_invocation_projection_missing_or_ambiguous")
        else:
            resource_record, invocation_row = matches[0]
            resource_payload = resource_record["payload"]
            raw_expected_receipts = linkage.get("consumption_receipt_digests", ())
            expected_receipts = tuple(str(item) for item in raw_expected_receipts) if isinstance(
                raw_expected_receipts, (list, tuple)) else ()
            if (invocation_row.get("request_id") != linkage.get("request_id")
                    or invocation_row.get("request_digest") != linkage.get("request_digest")
                    or invocation_row.get("purpose") != linkage.get("purpose")
                    or invocation_row.get("model_id") != linkage.get("model_id")
                    or invocation_row.get("model_artifact_digest") != linkage.get("model_artifact_digest")
                    or invocation_row.get("resource_allocation_digest") != linkage.get("allocation_digest")
                    or invocation_row.get("resource_attempt_id") != linkage.get("attempt_id")
                    or tuple(invocation_row.get("resource_consumption_receipt_digests") or ()) != expected_receipts):
                findings.append("resource_invocation_linkage_substitution")
            if (resource_payload.get("lineage_posture") != "verified"
                    or resource_payload.get("recovery_posture") != "reconciled_or_restored"
                    or resource_payload.get("retention_posture") != "complete"
                    or resource_payload.get("incomplete_attempt_count") != 0):
                findings.append("resource_ledger_projection_incomplete")
            allocations = [item for item in resource_payload.get("allocations", ())
                if isinstance(item, Mapping) and item.get("allocation_digest") == linkage.get("allocation_digest")]
            if len(allocations) != 1:
                findings.append("resource_allocation_missing_or_ambiguous")
            attempts = [item for item in resource_payload.get("attempts", ())
                if isinstance(item, Mapping) and item.get("attempt_id") == linkage.get("attempt_id")]
            if len(attempts) != 1 or (allocations and attempts
                    and attempts[0].get("allocation_id") != allocations[0].get("allocation_id")):
                findings.append("resource_attempt_missing_or_substituted")
            ledger_receipts = [item for item in resource_payload.get("consumption_receipts", ())
                if isinstance(item, Mapping) and item.get("receipt_digest") in expected_receipts]
            if (len(ledger_receipts) != len(expected_receipts)
                    or len({item.get("receipt_digest") for item in ledger_receipts}) != len(expected_receipts)
                    or any(item.get("attempt_id") != linkage.get("attempt_id")
                        or item.get("allocation_digest") != linkage.get("allocation_digest")
                        or (allocations and item.get("principal_binding_digest") != allocations[0].get("principal_binding_digest"))
                        for item in ledger_receipts)):
                findings.append("resource_consumption_receipt_missing_or_substituted")
            reconciled = [item for item in ledger_receipts if item.get("state") == "reconciled"
                and item.get("effect_receipt_digest") == linkage.get("effect_receipt_digest")]
            if len(reconciled) != 1:
                findings.append("resource_effect_receipt_not_reconciled")
            if resource_record.get("digest") != record_digest(resource_record):
                findings.append("resource_world_state_record_digest_invalid")

        semantic_linkage = {key: linkage.get(key) for key in (
            "request_id", "request_digest", "purpose", "model_id", "model_artifact_digest",
            "allocation_digest", "attempt_id", "consumption_receipt_digests", "linkage_digest",
            "effect_receipt_id", "effect_receipt_digest")}
        if not isinstance(semantic_linkage["consumption_receipt_digests"], (list, tuple)):
            findings.append("invocation_consumption_linkage_shape_invalid")
            expected_receipt_digests: tuple[str, ...] = ()
        else:
            expected_receipt_digests = tuple(str(item)
                for item in semantic_linkage["consumption_receipt_digests"])
        authenticated_linkage = {"receipt_digest": semantic_linkage["effect_receipt_digest"],
            "allocation_digest": semantic_linkage["allocation_digest"],
            "attempt_id": semantic_linkage["attempt_id"],
            "consumption_receipt_digests": expected_receipt_digests}
        if (not semantic_linkage["effect_receipt_id"]
                or not semantic_linkage["effect_receipt_digest"]
                or not semantic_linkage["allocation_digest"]
                or not semantic_linkage["attempt_id"]
                or not expected_receipt_digests
                or semantic_linkage["linkage_digest"] != digest_payload(authenticated_linkage)):
            findings.append("invocation_resource_linkage_digest_invalid")
        resource_ref = ({"source_id": resource_record.get("source_id"),
            "record_digest": resource_record.get("digest"),
            "ledger_digest": resource_record.get("payload", {}).get("ledger_digest")}
            if resource_record is not None else None)
        allocation_identity = None
        if resource_record is not None and len(allocations) == 1:
            allocation = allocations[0]
            allocation_identity = {key: allocation.get(key) for key in (
                "allocation_id", "allocation_digest", "principal_id", "principal_binding_digest",
                "principal_epoch", "resource_kind", "epoch", "policy_digest")}
        request_context = payload.get("invocation_request_context_linkage")
        task_context = ({key: request_context.get(key) for key in (
            "experiment_condition", "experiment_protocol_id", "history_record_ids",
            "history_record_digests")}
            if isinstance(request_context, Mapping) else None)
        join = {"source_kind": WorldStateSourceKind.RESOURCE_GOVERNOR.value,
            "source_id": "strategy-resource-lineage:" + digest({
                "proposal_id": proposal.get("subject_id"),
                "invocation_receipt_digest": linkage.get("effect_receipt_digest")})[:24],
            "schema_version": "sentientos.strategy_invocation_resource_lineage:v1",
            "subject_id": str(proposal.get("subject_id", "")),
            "subject_kind": "strategy_invocation_resource_lineage",
            "stage": "observation", "disposition": "verified" if not findings else "degraded",
            "evidence_strength": "reconciled_resource_lineage" if not findings else "incomplete_resource_lineage",
            "effect_claimed": False, "effect_proven": False,
            "observed_at": None, "retrieved_at": resource_record.get("retrieved_at") if resource_record else None,
            "payload": {"strategy_proposal_id": proposal.get("subject_id"),
                "strategy_proposal_record_digest": proposal.get("digest"),
                "invocation_receipt_id": payload.get("invocation_receipt_id"),
                "invocation_receipt_digest": linkage.get("effect_receipt_digest"),
                "resource_linkage": semantic_linkage, "resource_record": resource_ref,
                "allocation_identity": allocation_identity,
                "principal_id": (allocation_identity.get("principal_id")
                    if allocation_identity is not None else None),
                "principal_binding_digest": (allocation_identity.get("principal_binding_digest")
                    if allocation_identity is not None else None),
                "model_attribution": {"model_id": linkage.get("model_id"),
                    "model_artifact_digest": linkage.get("model_artifact_digest"),
                    "active_model_identity_digest": payload.get("active_model_identity_digest")},
                "software_attribution": {"declared_generation": payload.get("declared_software_generation"),
                    "generation_posture": payload.get("software_generation_posture"),
                    "execution_provenance_digest": payload.get("software_execution_provenance_digest")},
                "task_context": task_context,
                "event_times": sorted(str(item.get("observed_at")) for item in ledger_receipts
                    if isinstance(item.get("observed_at"), str)) if resource_record is not None else [],
                "lineage_findings": sorted(set(findings)),
                "shared_host_cpu_gpu_attribution": "unknown_without_independent_observation",
                "interpretation": "resource_use_for_strategy_inference_not_external_consequence",
                "current_truth": False, "authority": False},
        }
        model_candidate = model_replacement_candidates.get(str(proposal.get("source_id", "")))
        if model_candidate is not None:
            join["source_id"] = "model-replacement-resource-lineage:" + digest({
                "observation_id": model_candidate.get("invocation_receipt_id"),
                "invocation_receipt_digest": linkage.get("effect_receipt_digest")})[:24]
            join["schema_version"] = "sentientos.model_replacement_invocation_resource_lineage:v1"
            join["subject_kind"] = "model_replacement_invocation_resource_lineage"
            join["payload"].pop("strategy_proposal_id", None)
            join["payload"].pop("strategy_proposal_record_digest", None)
            join["payload"].update({
                "model_replacement_run_id": model_candidate.get("_model_replacement_run_id"),
                "model_replacement_run_digest": model_candidate.get("_model_replacement_run_digest"),
                "model_replacement_source_record_id": model_candidate.get("_model_replacement_source_record_id"),
                "model_replacement_source_record_digest": model_candidate.get(
                    "_model_replacement_source_record_digest"),
                "model_replacement_condition": model_candidate.get("_model_replacement_condition"),
                "model_identity_digest": model_candidate.get("_model_identity_digest"),
                "model_provenance_manifest_digest": model_candidate.get("_model_provenance_digest"),
                "causal_context_id": model_candidate.get("_causal_context_id"),
                "causal_context_digest": model_candidate.get("_causal_context_digest")})
        join["digest"] = record_digest(join)
        if len(json.dumps(join, sort_keys=True, separators=(",", ":")).encode("utf-8")) > 32_768:
            raise ValueError("resource_proposal_join_record_oversized")
        output.append(join)
    if omitted_candidates:
        retained_identity_digest = digest([(str(item.get("source_id", "")),
            str(item.get("digest", ""))) for item in linked_candidates])
        overflow = {"source_kind": WorldStateSourceKind.RESOURCE_GOVERNOR.value,
            "source_id": "resource-lineage-retention:" + retained_identity_digest[:24],
            "schema_version": "sentientos.resource_invocation_lineage_retention:v1",
            "subject_id": retained_identity_digest,
            "subject_kind": "resource_invocation_lineage_retention",
            "stage": "observation", "disposition": "degraded",
            "evidence_strength": "bounded_projection_omission",
            "effect_claimed": False, "effect_proven": False, "observed_at": None,
            "payload": {"selected_candidate_count": len(linked_candidates),
                "projected_candidate_count": len(proposal_rows),
                "omitted_candidate_count": len(omitted_candidates),
                "candidate_set_digest": retained_identity_digest,
                "omitted_candidate_identities": [{"source_id": str(item.get("source_id", "")),
                    "record_digest": str(item.get("digest", ""))} for item in omitted_candidates],
                "current_truth": False, "authority": False}}
        overflow["digest"] = record_digest(overflow)
        output.append(overflow)
    return output

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
