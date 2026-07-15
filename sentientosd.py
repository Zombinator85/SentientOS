from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from sentientos.boot_ceremony import (
    BootAnnouncer,
    BootCeremonyError,
    CeremonialScript,
    EventEmitter,
    FirstContact,
)
from sentientos.boot_chronicler import build_boot_ceremony_link
from sentientos.contract_sentinel import ContractSentinel
from sentientos.control_plane_kernel import (
    AuthorityClass,
    ControlActionRequest,
    LifecyclePhase,
    get_control_plane_kernel,
)
from sentientos.forge_daemon import ForgeDaemon
from sentientos.forge_merge_train import ForgeMergeTrain
from sentientos.local_model import LocalModel
from sentientos.local_model_authority import build_local_model_authority_map
from sentientos.governed_local_model_invocation import GovernedLocalModelInvoker
from sentientos.genesis_model_advice import GenesisModelAdviceCoordinator
from codex.amendments import (
    RepositoryMutationHandoffPlan,
    runtime_cycle as runtime_spec_cycle,
    runtime_next_repository_mutation_handoff,
)
from codex.integrity_daemon import runtime_guard as runtime_integrity_guard
from sentientos.codex_healer import runtime_monitor as runtime_healer_monitor
from sentientos.genesis_forge import CovenantVow, TelemetryStream, runtime_expand as runtime_genesis_expand
from sentientos.governed_improvement_signal_plane import SignalPlaneEvaluation, collect_repository_evidence, evaluate_signal_plane, persist_runtime_artifacts
from sentientos.repository_mutation_handoff import (
    build_repository_mutation_handoff,
    resolve_observed_source_revision,
    resolve_runtime_handoff_root,
    write_handoff_json,
)

LOGGER = logging.getLogger(__name__)


def resolve_improvement_evidence_sources(
    repo_root: Path,
    *,
    manifest_path: Path | None = None,
    max_sources: int = 16,
) -> list[dict[str, Any]]:
    """Resolve bounded read-only repository evidence sources for maintenance ticks."""

    root = repo_root.resolve()
    candidates: list[dict[str, Any]] = []
    configured = manifest_path or (
        Path(os.environ["SENTIENTOS_IMPROVEMENT_EVIDENCE_MANIFEST"])
        if os.environ.get("SENTIENTOS_IMPROVEMENT_EVIDENCE_MANIFEST")
        else None
    )
    if configured is not None and configured.exists():
        payload = json.loads(configured.read_text(encoding="utf-8"))
        rows = payload.get("sources", payload) if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise ValueError("malformed_improvement_evidence_manifest")
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("malformed_improvement_evidence_source")
            candidates.append(dict(row))
    else:
        defaults = [
            ("run_tests", root / "glow" / "test_runs" / "test_run_provenance.json"),
            ("coverage", root / "coverage.json"),
            ("mypy", root / "glow" / "mypy" / "mypy_output.txt"),
            ("covenant", root / "glow" / "integrity" / "findings.json"),
            ("capability_gap", root / "glow" / "capabilities" / "observations.json"),
        ]
        candidates.extend(
            {"source_kind": kind, "path": path.as_posix()}
            for kind, path in defaults
            if path.exists()
        )
    out: list[dict[str, Any]] = []
    for row in candidates:
        path = Path(str(row.get("path", "")))
        resolved = path if path.is_absolute() else root / path
        resolved = resolved.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"improvement_evidence_source_outside_repo:{resolved}") from exc
        if not resolved.exists():
            continue
        out.append({**row, "path": resolved.as_posix()})
        if len(out) > max_sources:
            raise ValueError("too_many_improvement_evidence_sources")
    return sorted(out, key=lambda item: (str(item.get("source_kind")), str(item.get("path"))))


class RuntimeMaintenanceSurfaces:
    """Runtime facade that closes sentientosd loop calls onto real subsystem methods."""

    def __init__(self, repo_root: Path, *, repository_mutation_handoff_root: Path | None = None, improvement_evidence_sources: list[dict[str, Any]] | None = None, runtime_state_root: Path | None = None, governed_local_invoker: GovernedLocalModelInvoker | None = None, genesis_advice_source: GenesisModelAdviceCoordinator | None = None) -> None:
        self._repo_root = Path(repo_root)
        self._repository_mutation_handoff_root = repository_mutation_handoff_root
        self._improvement_evidence_sources = list(improvement_evidence_sources or [])
        self._runtime_state_root = runtime_state_root or Path(os.environ.get("SENTIENTOS_RUNTIME_STATE_ROOT", "/tmp/sentientos-runtime-state"))
        self._identify_admitted = False
        self._governed_local_invoker = governed_local_invoker
        self._genesis_advice_source = genesis_advice_source
        self._feedback: dict[str, Any] = {
            "schema": "runtime_maintenance_feedback:v1",
            "degraded": False,
            "surfaces": {},
        }

    def identify_improvement_signals(self) -> SignalPlaneEvaluation:
        records = collect_repository_evidence(repo_root=self._repo_root, artifacts=self._improvement_evidence_sources)
        evaluation = evaluate_signal_plane(records, repo_root=self._repo_root)
        artifacts = persist_runtime_artifacts(self._runtime_state_root, evaluation, tick_id=datetime.now(timezone.utc).isoformat())
        self._identify_admitted = True
        self._feedback["surfaces"]["governed_improvement_signal_plane"] = {
            "status": "degraded" if evaluation.summary.get("degraded") else "ok",
            "batch_id": evaluation.batch.batch_id,
            "batch_digest": evaluation.batch.batch_digest,
            "input_counts_by_source": dict(evaluation.summary.get("input_counts_by_source", {})),
            "routed_counts_by_disposition": dict(evaluation.summary.get("routed_counts_by_disposition", {})),
            "proposal_count": evaluation.summary.get("proposal_count", 0),
            "blocked_invalid_count": evaluation.summary.get("blocked_invalid_count", 0),
            "adoption_performed": False,
            "repository_mutation_performed": False,
            "provider_network_git_operation_performed": False,
            "runtime_artifacts": artifacts,
        }
        self._current_signal_evaluation = evaluation
        self._refresh_feedback()
        return evaluation

    def expand(self) -> list[Any]:
        evaluation = getattr(self, "_current_signal_evaluation", evaluate_signal_plane((), repo_root=self._repo_root))
        genesis_inputs = evaluation.genesis_inputs
        telemetry_streams = [
            TelemetryStream(
                name=str(item.get("name")),
                capability=str(item.get("capability")),
                description=str(item.get("description")),
                sample_payload=dict(item.get("sample_payload") or {}),
            )
            for item in genesis_inputs.get("telemetry_streams", [])
            if isinstance(item, dict)
        ]
        vows = [
            CovenantVow(capability=str(item.get("capability")), description=str(item.get("description")))
            for item in genesis_inputs.get("vows", [])
            if isinstance(item, dict)
        ]
        if not self._identify_admitted:
            outcomes = []
        else:
            try:
                outcomes = runtime_genesis_expand(
                    self._repo_root,
                    telemetry_streams=telemetry_streams,
                    vows=vows,
                    proposal_only=True,
                    advice_source=self._genesis_advice_source,
                )
            except TypeError as exc:
                if "advice_source" not in str(exc):
                    raise
                outcomes = runtime_genesis_expand(
                    self._repo_root,
                    telemetry_streams=telemetry_streams,
                    vows=vows,
                    proposal_only=True,
                )
        failed = sum(1 for item in outcomes if str(getattr(item, "status", "")).lower() in {"failed", "deferred_degraded_audit_trust"})
        advice_feedback = dict(getattr(self._genesis_advice_source, "feedback", {}) or {})
        self._feedback["surfaces"]["genesis_forge"] = {
            "status": "degraded" if failed else "ok",
            "failed_or_deferred": failed,
            "outcome_count": len(outcomes),
            "governed_genesis_model_advice": {
                "authority_map_id": getattr(getattr(self._governed_local_invoker, "authority_map", None), "map_id", None),
                "authority_map_digest": getattr(getattr(self._governed_local_invoker, "authority_map", None), "map_digest", None),
                "eligible_model_count": int(getattr(getattr(self._governed_local_invoker, "authority_map", None), "summary", {}).get("eligible_count", 0)) if self._governed_local_invoker else 0,
                "advice_enabled": self._genesis_advice_source is not None,
                **advice_feedback,
                "forbidden_downstream_effects": {"approved": False, "adopted": False, "lineage_integrated": False, "repository_mutation_performed": False},
            },
        }
        self._refresh_feedback()
        return cast(list[Any], outcomes)

    def cycle(self) -> dict[str, Any]:
        evaluation = getattr(self, "_current_signal_evaluation", evaluate_signal_plane((), repo_root=self._repo_root))
        if not self._identify_admitted:
            state = {"panel": "Spec Amendments", "pending": [], "approved": [], "runtime_signal_count": 0, "blocked_by_identify_stage": True}
        else:
            state = cast(dict[str, Any], runtime_spec_cycle(self._repo_root / "integration", signals=evaluation.amendment_inputs))
        pending_items = state.get("pending", [])
        approved_items = state.get("approved", [])
        pending = len(pending_items) if isinstance(pending_items, list) else 0
        self._feedback["surfaces"]["spec_amender"] = {
            "status": "ok",
            "pending": pending,
            "approved": len(approved_items) if isinstance(approved_items, list) else 0,
        }
        self._refresh_feedback()
        return state

    def guard(self) -> dict[str, Any]:
        health = runtime_integrity_guard(self._repo_root / "integration")
        status = str(health.get("status", "unknown")).lower()
        quarantined = int(health.get("quarantined", 0) or 0)
        degraded = status in {"alert", "quarantined"} or quarantined > 0
        self._feedback["surfaces"]["integrity_daemon"] = {
            "status": "degraded" if degraded else "ok",
            "health_status": status,
            "quarantined": quarantined,
            "passed": int(health.get("passed", 0) or 0),
        }
        self._refresh_feedback()
        typed_health: dict[str, Any] = health
        return typed_health

    def monitor(self) -> list[dict[str, Any]]:
        events = runtime_healer_monitor(self._repo_root / "integration")
        quarantined = sum(1 for event in events if bool(event.get("quarantined")))
        statuses = sorted({str(event.get("status", "unknown")) for event in events})
        self._feedback["surfaces"]["codex_healer"] = {
            "status": "degraded" if quarantined else "ok",
            "events": len(events),
            "quarantined_events": quarantined,
            "statuses": statuses,
        }
        self._refresh_feedback()
        return cast(list[dict[str, Any]], events)

    def next_repository_mutation_handoff(self) -> RepositoryMutationHandoffPlan | None:
        return runtime_next_repository_mutation_handoff(self._repo_root / "integration", approved_only=True)

    def emit_repository_mutation_handoff(self, plan: RepositoryMutationHandoffPlan) -> dict[str, Any]:
        observed_revision, _warnings = resolve_observed_source_revision(self._repo_root)
        handoff = build_repository_mutation_handoff(
            plan.proposal,
            repo_root=self._repo_root,
            source_revision=observed_revision,
        )
        output_dir = resolve_runtime_handoff_root(self._repo_root, self._repository_mutation_handoff_root)
        write_handoff_json(handoff, output_dir / f"{handoff['handoff_id'].replace(':', '_')}.json")
        self._feedback["surfaces"]["repository_mutation_handoff"] = {
            "status": "ok",
            "handoff_status": handoff.get("handoff_status"),
            "proposal_id": handoff.get("proposal_id"),
            "metadata_only": True,
        }
        self._refresh_feedback()
        return cast(dict[str, Any], handoff)

    def governance_feedback(self) -> dict[str, Any]:
        return dict(self._feedback)

    def _refresh_feedback(self) -> None:
        surfaces = self._feedback.get("surfaces", {})
        degraded = any(
            isinstance(surface, dict) and str(surface.get("status", "ok")) == "degraded"
            for surface in surfaces.values()
        )
        self._feedback["degraded"] = degraded


def _maintenance_degradation_signal(
    *,
    tick_id: str,
    surface: str,
    correlation_id: str,
    phase_before: Any,
    phase_at_failure: Any,
    exc: BaseException,
) -> dict[str, Any]:
    return {
        "event_type": "runtime_maintenance_degradation",
        "schema": "runtime_maintenance_degradation:v1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tick_id": tick_id,
        "correlation_id": correlation_id,
        "phase": LifecyclePhase.MAINTENANCE.value,
        "phase_before": getattr(phase_before, "value", str(phase_before)),
        "phase_at_failure": getattr(phase_at_failure, "value", str(phase_at_failure)),
        "surface": surface,
        "actor": "sentientosd",
        "severity": "blocking",
        "disposition": "fail_stop_degraded",
        "stopped_active_cycle": True,
        "retry_attempted": False,
        "follow_up_enqueued": False,
        "reinterpreted_as_goal": False,
        "failure_type": type(exc).__name__,
        "failure_message": str(exc),
    }


def _record_maintenance_degradation(*, kernel: Any, signal: dict[str, Any]) -> None:
    logging.getLogger("sentientos.degradation").error(json.dumps(signal, sort_keys=True))
    append = getattr(kernel, "_append", None)
    if callable(append):
        try:
            append(signal)
        except Exception:
            LOGGER.warning(
                "Failed to append runtime maintenance degradation signal",
                extra={"correlation_id": signal.get("correlation_id"), "surface": signal.get("surface")},
                exc_info=True,
            )


def _run_maintenance_tick(
    *,
    kernel: Any,
    runtime_surfaces: RuntimeMaintenanceSurfaces,
    contract_sentinel: ContractSentinel,
    forge_daemon: ForgeDaemon,
    merge_train: ForgeMergeTrain,
) -> None:
    LOGGER.debug("SentientOS daemon tick")
    phase_before = getattr(kernel, "phase", LifecyclePhase.RUNTIME)
    tick_id = datetime.now(timezone.utc).isoformat()
    current_surface = "maintenance_start"
    current_correlation_id = f"{tick_id}:{current_surface}"

    try:
        kernel.set_phase(LifecyclePhase.MAINTENANCE, actor="sentientosd")
        feedback = runtime_surfaces.governance_feedback()
        current_surface = "identify_improvement_signals"
        current_correlation_id = f"{tick_id}:identify_improvement_signals"
        identify = getattr(runtime_surfaces, "identify_improvement_signals", None)
        identify_allowed = True
        if callable(identify):
            decision, _identify_result = kernel.admit_and_execute(
                ControlActionRequest(
                    action_kind="identify_improvement_signals",
                    authority_class=AuthorityClass.PROPOSAL_EVALUATION,
                    actor="sentientosd",
                    target_subsystem="governed_improvement_signal_plane",
                    requested_phase=LifecyclePhase.MAINTENANCE,
                    metadata={"correlation_id": current_correlation_id},
                ),
                execute=identify,
            )
            identify_allowed = bool(getattr(decision, "allowed", False))
        if not identify_allowed:
            runtime_surfaces._identify_admitted = False
            runtime_surfaces._feedback["surfaces"]["governed_improvement_signal_plane"] = {"status": "degraded", "blocked_by_admission": True}
            _record_maintenance_degradation(
                kernel=kernel,
                signal={
                    "event": "runtime_maintenance_degradation",
                    "tick_id": tick_id,
                    "surface": current_surface,
                    "correlation_id": current_correlation_id,
                    "reason": "identify_improvement_signals_not_admitted",
                    "phase_before": str(getattr(phase_before, "value", phase_before)),
                },
            )
            safe_phase = phase_before if isinstance(phase_before, LifecyclePhase) else LifecyclePhase.RUNTIME
            if safe_phase == LifecyclePhase.MAINTENANCE:
                safe_phase = LifecyclePhase.RUNTIME
            kernel.set_phase(safe_phase, actor="sentientosd")
            return
        if identify_allowed:
            feedback = runtime_surfaces.governance_feedback()
            current_surface = "expand"
            current_correlation_id = f"{tick_id}:expand"
            kernel.admit_and_execute(
                ControlActionRequest(
                    action_kind="expand",
                    authority_class=AuthorityClass.PROPOSAL_EVALUATION,
                    actor="sentientosd",
                    target_subsystem="genesis_forge",
                    requested_phase=LifecyclePhase.MAINTENANCE,
                    startup_symbol="GenesisForge",
                    metadata={"runtime_feedback": feedback, "correlation_id": current_correlation_id},
                ),
                execute=runtime_surfaces.expand,
            )
            feedback = runtime_surfaces.governance_feedback()
            current_surface = "cycle"
            current_correlation_id = f"{tick_id}:cycle"
            kernel.admit_and_execute(
                ControlActionRequest(
                    action_kind="cycle",
                    authority_class=AuthorityClass.SPEC_AMENDMENT,
                    actor="sentientosd",
                    target_subsystem="spec_amender",
                    requested_phase=LifecyclePhase.MAINTENANCE,
                    startup_symbol="SpecAmender",
                    metadata={"runtime_feedback": feedback, "correlation_id": current_correlation_id},
                ),
                execute=runtime_surfaces.cycle,
            )
            feedback = runtime_surfaces.governance_feedback()
            current_surface = "guard"
            current_correlation_id = f"{tick_id}:guard"
            kernel.admit_and_execute(
                ControlActionRequest(
                    action_kind="guard",
                    authority_class=AuthorityClass.PROPOSAL_EVALUATION,
                    actor="sentientosd",
                    target_subsystem="integrity_daemon",
                    requested_phase=LifecyclePhase.MAINTENANCE,
                    startup_symbol="IntegrityDaemon",
                    metadata={"runtime_feedback": feedback, "correlation_id": current_correlation_id},
                ),
                execute=runtime_surfaces.guard,
            )
        feedback = runtime_surfaces.governance_feedback()
        current_surface = "monitor"
        current_correlation_id = f"{tick_id}:monitor"
        kernel.admit_and_execute(
            ControlActionRequest(
                action_kind="monitor",
                authority_class=AuthorityClass.REPAIR,
                actor="sentientosd",
                target_subsystem="codex_healer",
                requested_phase=LifecyclePhase.MAINTENANCE,
                startup_symbol="CodexHealer",
                metadata={"runtime_feedback": feedback, "correlation_id": current_correlation_id},
            ),
            execute=runtime_surfaces.monitor,
        )
        # Sentinel runs after integrity guard so contract artifacts are trustworthy, before forge daemon so queued repairs execute same tick.
        if os.getenv("SENTIENTOS_SENTINEL_ENABLED", "0") == "1":
            current_surface = "sentinel_tick"
            current_correlation_id = f"{tick_id}:sentinel_tick"
            contract_sentinel.tick()
        feedback = runtime_surfaces.governance_feedback()
        current_surface = "forge_tick"
        current_correlation_id = f"{tick_id}:forge_tick"
        kernel.admit_and_execute(
            ControlActionRequest(
                action_kind="forge_tick",
                authority_class=AuthorityClass.REPAIR,
                actor="sentientosd",
                target_subsystem="forge_daemon",
                requested_phase=LifecyclePhase.MAINTENANCE,
                metadata={"runtime_feedback": feedback, "correlation_id": current_correlation_id},
            ),
            execute=forge_daemon.run_tick,
        )
        feedback = runtime_surfaces.governance_feedback()
        current_surface = "merge_tick"
        current_correlation_id = f"{tick_id}:merge_tick"
        kernel.admit_and_execute(
            ControlActionRequest(
                action_kind="merge_tick",
                authority_class=AuthorityClass.REPAIR,
                actor="sentientosd",
                target_subsystem="forge_merge_train",
                requested_phase=LifecyclePhase.MAINTENANCE,
                metadata={"runtime_feedback": feedback, "correlation_id": current_correlation_id},
            ),
            execute=merge_train.tick,
        )
        kernel.set_phase(LifecyclePhase.RUNTIME, actor="sentientosd")

        current_surface = "repository_mutation_handoff"
        current_correlation_id = f"{tick_id}:repository_mutation_handoff"
        plan = runtime_surfaces.next_repository_mutation_handoff() if identify_allowed else None
        if plan:
            LOGGER.info("Codex amendment ready for repository mutation handoff review: %s", plan.message)
            runtime_surfaces.emit_repository_mutation_handoff(plan)
    except Exception as exc:
        signal = _maintenance_degradation_signal(
            tick_id=tick_id,
            surface=current_surface,
            correlation_id=current_correlation_id,
            phase_before=phase_before,
            phase_at_failure=getattr(kernel, "phase", "unknown"),
            exc=exc,
        )
        _record_maintenance_degradation(kernel=kernel, signal=signal)
        safe_phase = phase_before if isinstance(phase_before, LifecyclePhase) else LifecyclePhase.RUNTIME
        if safe_phase == LifecyclePhase.MAINTENANCE:
            safe_phase = LifecyclePhase.RUNTIME
        try:
            kernel.set_phase(safe_phase, actor="sentientosd")
        except Exception:
            LOGGER.warning(
                "Failed to restore runtime phase after maintenance degradation",
                extra={"correlation_id": current_correlation_id, "surface": current_surface},
                exc_info=True,
            )
        return


async def run_loop(shutdown_event: asyncio.Event, interval_seconds: int = 60) -> None:
    """Run the autonomous Codex maintenance loop."""

    emitter = EventEmitter(LOGGER)
    announcer = BootAnnouncer(emitter)
    ceremony = CeremonialScript(announcer)
    try:
        ceremony.perform()
    except BootCeremonyError:
        LOGGER.critical("Boot ceremony failed. Aborting startup.")
        raise
    first_contact = FirstContact(emitter)
    first_contact.affirm_integrity()
    first_contact.invite_conversation()
    build_boot_ceremony_link(emitter).narrate()
    model = LocalModel.autoload()
    forge_daemon = ForgeDaemon()
    merge_train = ForgeMergeTrain(repo_root=forge_daemon.repo_root)
    contract_sentinel = ContractSentinel()
    kernel = get_control_plane_kernel()
    repo_root = Path.cwd()
    authority_map = build_local_model_authority_map()
    governed_invoker = GovernedLocalModelInvoker(model=model, authority_map=authority_map, runtime_root=repo_root / "sentientos_data" / "runtime")
    genesis_advice = GenesisModelAdviceCoordinator(invoker=governed_invoker, runtime_root=repo_root / "sentientos_data" / "runtime")
    runtime_surfaces = RuntimeMaintenanceSurfaces(
        repo_root,
        improvement_evidence_sources=resolve_improvement_evidence_sources(repo_root),
        governed_local_invoker=governed_invoker,
        genesis_advice_source=genesis_advice,
    )
    kernel.set_phase(LifecyclePhase.RUNTIME, actor="sentientosd")
    LOGGER.info("SentientOS daemon initialised with %s", model.describe())

    while not shutdown_event.is_set():
        _run_maintenance_tick(
            kernel=kernel,
            runtime_surfaces=runtime_surfaces,
            contract_sentinel=contract_sentinel,
            forge_daemon=forge_daemon,
            merge_train=merge_train,
        )

        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            continue

    kernel.set_phase(LifecyclePhase.SHUTDOWN, actor="sentientosd")
    LOGGER.info("SentientOS daemon shutting down")


def _install_signal_handlers(loop: asyncio.AbstractEventLoop, shutdown_event: asyncio.Event) -> None:
    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, shutdown_event.set)


def main(interval_seconds: int = 60) -> None:
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s - %(message)s")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    shutdown_event = asyncio.Event()
    _install_signal_handlers(loop, shutdown_event)
    try:
        loop.run_until_complete(run_loop(shutdown_event, interval_seconds=interval_seconds))
    finally:
        with suppress(RuntimeError):
            loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


if __name__ == "__main__":
    main()
