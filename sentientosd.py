from __future__ import annotations

import asyncio
import logging
import os
import signal
from contextlib import suppress
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

    def expand(self) -> list[Any]:
        return runtime_genesis_expand(self._repo_root)

    def cycle(self) -> dict[str, Any]:
        return runtime_spec_cycle(self._repo_root / "integration")

    def guard(self) -> dict[str, Any]:
        return runtime_integrity_guard(self._repo_root / "integration")

    def monitor(self) -> list[dict[str, Any]]:
        return runtime_healer_monitor(self._repo_root / "integration")

    def next_commit(self) -> AmendmentCommitPlan | None:
        return runtime_next_commit(self._repo_root / "integration")

    def mark_committed(self, plan: AmendmentCommitPlan) -> None:
        runtime_mark_committed(plan, operator="sentientosd", root=self._repo_root / "integration")


def _run_maintenance_tick(
    *,
    kernel: Any,
    runtime_surfaces: RuntimeMaintenanceSurfaces,
    contract_sentinel: ContractSentinel,
    forge_daemon: ForgeDaemon,
    merge_train: ForgeMergeTrain,
) -> None:
    LOGGER.debug("SentientOS daemon tick")
    kernel.set_phase(LifecyclePhase.MAINTENANCE, actor="sentientosd")
    kernel.admit_and_execute(
        ControlActionRequest(
            action_kind="expand",
            authority_class=AuthorityClass.PROPOSAL_EVALUATION,
            actor="sentientosd",
            target_subsystem="genesis_forge",
            requested_phase=LifecyclePhase.MAINTENANCE,
            startup_symbol="GenesisForge",
        ),
        execute=runtime_surfaces.expand,
    )
    kernel.admit_and_execute(
        ControlActionRequest(
            action_kind="cycle",
            authority_class=AuthorityClass.SPEC_AMENDMENT,
            actor="sentientosd",
            target_subsystem="spec_amender",
            requested_phase=LifecyclePhase.MAINTENANCE,
            startup_symbol="SpecAmender",
        ),
        execute=runtime_surfaces.cycle,
    )
    kernel.admit_and_execute(
        ControlActionRequest(
            action_kind="guard",
            authority_class=AuthorityClass.PROPOSAL_EVALUATION,
            actor="sentientosd",
            target_subsystem="integrity_daemon",
            requested_phase=LifecyclePhase.MAINTENANCE,
            startup_symbol="IntegrityDaemon",
        ),
        execute=runtime_surfaces.guard,
    )
    kernel.admit_and_execute(
        ControlActionRequest(
            action_kind="monitor",
            authority_class=AuthorityClass.REPAIR,
            actor="sentientosd",
            target_subsystem="codex_healer",
            requested_phase=LifecyclePhase.MAINTENANCE,
            startup_symbol="CodexHealer",
        ),
        execute=runtime_surfaces.monitor,
    )
    kernel.set_phase(LifecyclePhase.RUNTIME, actor="sentientosd")
    # Sentinel runs after integrity guard so contract artifacts are trustworthy, before forge daemon so queued repairs execute same tick.
    if os.getenv("SENTIENTOS_SENTINEL_ENABLED", "0") == "1":
        contract_sentinel.tick()
    forge_daemon.run_tick()
    merge_train.tick()

    plan = runtime_surfaces.next_commit()
    if plan:
        LOGGER.info("Codex amendment ready for commit: %s", plan.message)
        if git_commit_push(plan.message):
            runtime_surfaces.mark_committed(plan)


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
