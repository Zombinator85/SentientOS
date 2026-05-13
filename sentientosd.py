from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
from sentientos.utils import git_commit_push
from codex.amendments import (
    AmendmentCommitPlan,
    runtime_cycle as runtime_spec_cycle,
    runtime_mark_committed,
    runtime_next_commit,
)
from codex.integrity_daemon import runtime_guard as runtime_integrity_guard
from sentientos.codex_healer import runtime_monitor as runtime_healer_monitor
from sentientos.genesis_forge import runtime_expand as runtime_genesis_expand

LOGGER = logging.getLogger(__name__)


class RuntimeMaintenanceSurfaces:
    """Runtime facade that closes sentientosd loop calls onto real subsystem methods."""

    def __init__(self, repo_root: Path) -> None:
        self._repo_root = Path(repo_root)
        self._feedback: dict[str, Any] = {
            "schema": "runtime_maintenance_feedback:v1",
            "degraded": False,
            "surfaces": {},
        }

    def expand(self) -> list[Any]:
        outcomes = runtime_genesis_expand(self._repo_root)
        failed = sum(1 for item in outcomes if str(getattr(item, "status", "")).lower() in {"failed", "deferred_degraded_audit_trust"})
        self._feedback["surfaces"]["genesis_forge"] = {
            "status": "degraded" if failed else "ok",
            "failed_or_deferred": failed,
            "outcome_count": len(outcomes),
        }
        self._refresh_feedback()
        return outcomes

    def cycle(self) -> dict[str, Any]:
        state = runtime_spec_cycle(self._repo_root / "integration")
        pending = len(state.get("pending", [])) if isinstance(state.get("pending"), list) else 0
        self._feedback["surfaces"]["spec_amender"] = {
            "status": "ok",
            "pending": pending,
            "approved": len(state.get("approved", [])) if isinstance(state.get("approved"), list) else 0,
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
        return health

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
        return events

    def next_commit(self) -> AmendmentCommitPlan | None:
        return runtime_next_commit(self._repo_root / "integration")

    def mark_committed(self, plan: AmendmentCommitPlan) -> None:
        runtime_mark_committed(plan, operator="sentientosd", root=self._repo_root / "integration")

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

        current_surface = "commit_plan"
        current_correlation_id = f"{tick_id}:commit_plan"
        plan = runtime_surfaces.next_commit()
        if plan:
            LOGGER.info("Codex amendment ready for commit: %s", plan.message)
            if git_commit_push(plan.message):
                runtime_surfaces.mark_committed(plan)
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
    runtime_surfaces = RuntimeMaintenanceSurfaces(Path.cwd())
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
