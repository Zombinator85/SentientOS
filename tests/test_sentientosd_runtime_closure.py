from __future__ import annotations

"""Runtime-closure matrix for sentientosd governance tick.

- GenesisForge.expand    -> sentientos.genesis_forge.runtime_expand (real GenesisForge.expand call)
- SpecAmender.cycle      -> codex.amendments.runtime_cycle (real SpecAmender dashboard state)
- IntegrityDaemon.guard  -> codex.integrity_daemon.runtime_guard (real IntegrityDaemon.health)
- CodexHealer.monitor    -> sentientos.codex_healer.runtime_monitor (real CodexHealer.run)
"""

from dataclasses import dataclass
from pathlib import Path

import pytest

from sentientos.control_plane_kernel import (
    AuthorityClass,
    ControlActionRequest,
    ControlPlaneKernel,
    LifecyclePhase,
)
from sentientosd import RuntimeMaintenanceSurfaces, _run_maintenance_tick

pytestmark = pytest.mark.no_legacy_skip


@dataclass
class _GovernorDecisionStub:
    allowed: bool
    reason: str
    correlation_id: str

    def to_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "mode": "test",
            "reason_hash": "stub",
            "correlation_id": self.correlation_id,
        }


class _GovernorStub:
    def __init__(self, *, allow: bool) -> None:
        self._allow = allow

    def admit_action(self, _action_class: str, _actor: str, correlation_id: str, *, metadata: dict[str, object]):
        del metadata
        return _GovernorDecisionStub(
            allowed=self._allow,
            reason="ok" if self._allow else "blocked_for_test",
            correlation_id=correlation_id,
        )


class _ForgeDaemonStub:
    def __init__(self) -> None:
        self.calls = 0

    def run_tick(self) -> None:
        self.calls += 1


class _MergeTrainStub:
    def __init__(self) -> None:
        self.calls = 0

    def tick(self) -> None:
        self.calls += 1


class _SentinelStub:
    def tick(self) -> None:  # pragma: no cover - env-gated in code under test
        raise AssertionError("sentinel should stay disabled in this test")


class _RuntimeSurfaceSpy:
    def __init__(self) -> None:
        self.expand_calls = 0
        self.cycle_calls = 0
        self.guard_calls = 0
        self.monitor_calls = 0

    def expand(self) -> list[object]:
        self.expand_calls += 1
        return []

    def cycle(self) -> dict[str, object]:
        self.cycle_calls += 1
        return {}

    def guard(self) -> dict[str, object]:
        self.guard_calls += 1
        return {}

    def monitor(self) -> list[dict[str, object]]:
        self.monitor_calls += 1
        return []

    def next_commit(self):
        return None

    def mark_committed(self, _plan) -> None:
        raise AssertionError("should not commit in this test")


def test_maintenance_tick_invokes_all_runtime_surfaces(tmp_path: Path) -> None:
    kernel = ControlPlaneKernel(
        runtime_governor=_GovernorStub(allow=True),  # type: ignore[arg-type]
        decisions_path=tmp_path / "decisions.jsonl",
    )
    surfaces = _RuntimeSurfaceSpy()
    forge = _ForgeDaemonStub()
    merge = _MergeTrainStub()
    _run_maintenance_tick(
        kernel=kernel,
        runtime_surfaces=surfaces,  # type: ignore[arg-type]
        contract_sentinel=_SentinelStub(),  # type: ignore[arg-type]
        forge_daemon=forge,  # type: ignore[arg-type]
        merge_train=merge,  # type: ignore[arg-type]
    )
    assert surfaces.expand_calls == 1
    assert surfaces.cycle_calls == 1
    assert surfaces.guard_calls == 1
    assert surfaces.monitor_calls == 1
    assert forge.calls == 1
    assert merge.calls == 1


def test_runtime_surfaces_close_to_real_callable_paths(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    kernel = ControlPlaneKernel(
        runtime_governor=_GovernorStub(allow=True),  # type: ignore[arg-type]
        decisions_path=tmp_path / "decisions.jsonl",
    )
    kernel.set_phase(LifecyclePhase.MAINTENANCE, actor="test")
    surfaces = RuntimeMaintenanceSurfaces(tmp_path)

    expand_decision, expand_result = kernel.admit_and_execute(
        ControlActionRequest(
            action_kind="expand",
            authority_class=AuthorityClass.PROPOSAL_EVALUATION,
            actor="test",
            target_subsystem="genesis_forge",
            requested_phase=LifecyclePhase.MAINTENANCE,
            startup_symbol="GenesisForge",
            metadata={"correlation_id": "t-expand"},
        ),
        execute=surfaces.expand,
    )
    assert expand_decision.allowed is True
    assert isinstance(expand_result, list)

    cycle_decision, cycle_result = kernel.admit_and_execute(
        ControlActionRequest(
            action_kind="cycle",
            authority_class=AuthorityClass.SPEC_AMENDMENT,
            actor="test",
            target_subsystem="spec_amender",
            requested_phase=LifecyclePhase.MAINTENANCE,
            startup_symbol="SpecAmender",
            metadata={"correlation_id": "t-cycle"},
        ),
        execute=surfaces.cycle,
    )
    assert cycle_decision.allowed is True
    assert cycle_result["panel"] == "Spec Amendments"

    guard_decision, guard_result = kernel.admit_and_execute(
        ControlActionRequest(
            action_kind="guard",
            authority_class=AuthorityClass.PROPOSAL_EVALUATION,
            actor="test",
            target_subsystem="integrity_daemon",
            requested_phase=LifecyclePhase.MAINTENANCE,
            startup_symbol="IntegrityDaemon",
            metadata={"correlation_id": "t-guard"},
        ),
        execute=surfaces.guard,
    )
    assert guard_decision.allowed is True
    assert guard_result["daemon"] == "IntegrityDaemon"

    monitor_decision, monitor_result = kernel.admit_and_execute(
        ControlActionRequest(
            action_kind="monitor",
            authority_class=AuthorityClass.REPAIR,
            actor="test",
            target_subsystem="codex_healer",
            requested_phase=LifecyclePhase.MAINTENANCE,
            startup_symbol="CodexHealer",
            metadata={"correlation_id": "t-monitor"},
        ),
        execute=surfaces.monitor,
    )
    assert monitor_decision.allowed is True
    assert isinstance(monitor_result, list)


def test_startup_only_surfaces_are_not_callable_without_runtime_mediation(tmp_path: Path) -> None:
    kernel = ControlPlaneKernel(
        runtime_governor=_GovernorStub(allow=True),  # type: ignore[arg-type]
        decisions_path=tmp_path / "decisions.jsonl",
    )
    kernel.set_phase(LifecyclePhase.RUNTIME, actor="test")
    executed = {"called": False}
    decision, result = kernel.admit_and_execute(
        ControlActionRequest(
            action_kind="monitor",
            authority_class=AuthorityClass.REPAIR,
            actor="test",
            target_subsystem="codex_healer",
            requested_phase=LifecyclePhase.RUNTIME,
            startup_symbol="CodexHealer",
            metadata={"correlation_id": "t-no-mediation"},
        ),
        execute=lambda: executed.__setitem__("called", True),
    )
    assert decision.allowed is False
    assert "startup_mediation_required" in decision.reason_codes
    assert result is None
    assert executed["called"] is False


def test_governor_denial_prevents_daemon_loop_side_effects(tmp_path: Path) -> None:
    kernel = ControlPlaneKernel(
        runtime_governor=_GovernorStub(allow=False),  # type: ignore[arg-type]
        decisions_path=tmp_path / "decisions.jsonl",
    )
    surfaces = _RuntimeSurfaceSpy()
    forge = _ForgeDaemonStub()
    merge = _MergeTrainStub()
    _run_maintenance_tick(
        kernel=kernel,
        runtime_surfaces=surfaces,  # type: ignore[arg-type]
        contract_sentinel=_SentinelStub(),  # type: ignore[arg-type]
        forge_daemon=forge,  # type: ignore[arg-type]
        merge_train=merge,  # type: ignore[arg-type]
    )
    assert surfaces.expand_calls == 0
    assert surfaces.cycle_calls == 0
    assert surfaces.guard_calls == 0
    assert surfaces.monitor_calls == 0
    assert forge.calls == 1
    assert merge.calls == 1
