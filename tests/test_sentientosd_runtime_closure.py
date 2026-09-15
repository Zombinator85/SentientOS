from __future__ import annotations

"""Runtime-closure matrix for sentientosd governance tick.

- GenesisForge.expand    -> sentientos.genesis_forge.runtime_expand (real GenesisForge.expand call)
- SpecAmender.cycle      -> codex.amendments.runtime_cycle (real SpecAmender dashboard state)
- IntegrityDaemon.guard  -> codex.integrity_daemon.runtime_guard (real IntegrityDaemon.health)
- CodexHealer.monitor    -> sentientos.codex_healer.runtime_monitor (real CodexHealer.run)
"""

from dataclasses import dataclass
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import sentientosd

from sentientos.control_plane_kernel import (
    AuthorityClass,
    ControlActionRequest,
    ControlPlaneKernel,
    LifecyclePhase,
)
from sentientos.runtime_governor import PostureRuleEvaluation, RuntimeGovernor
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

    def next_repository_mutation_handoff(self):
        return None

    def mark_committed(self, _plan) -> None:
        raise AssertionError("should not commit in this test")

    def governance_feedback(self) -> dict[str, object]:
        return {"schema": "runtime_maintenance_feedback:v1", "degraded": False, "surfaces": {}}


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
    assert forge.calls == 0
    assert merge.calls == 0

    rows = [json.loads(line) for line in (tmp_path / "decisions.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(row.get("action_kind") == "forge_tick" and row.get("final_disposition") == "deny" for row in rows)
    assert any(row.get("action_kind") == "merge_tick" and row.get("final_disposition") == "deny" for row in rows)


class _FailingRuntimeSurfaceSpy(_RuntimeSurfaceSpy):
    def __init__(self, *, fail_surface: str) -> None:
        super().__init__()
        self.fail_surface = fail_surface
        self.next_handoff_calls = 0
        self.mark_committed_calls = 0

    def expand(self) -> list[object]:
        self.expand_calls += 1
        if self.fail_surface == "expand":
            raise RuntimeError("boom-expand")
        return []

    def cycle(self) -> dict[str, object]:
        self.cycle_calls += 1
        if self.fail_surface == "cycle":
            raise RuntimeError("boom-cycle")
        return {}

    def guard(self) -> dict[str, object]:
        self.guard_calls += 1
        if self.fail_surface == "guard":
            raise RuntimeError("boom-guard")
        return {}

    def monitor(self) -> list[dict[str, object]]:
        self.monitor_calls += 1
        if self.fail_surface == "monitor":
            raise RuntimeError("boom-monitor")
        return []

    def next_repository_mutation_handoff(self):
        self.next_handoff_calls += 1
        if self.fail_surface == "handoff_plan":
            raise RuntimeError("boom-handoff-plan")
        return None

    def mark_committed(self, _plan) -> None:
        self.mark_committed_calls += 1
        raise AssertionError("mark_committed should not run during degradation tests")


class _FailingForgeDaemonStub(_ForgeDaemonStub):
    def run_tick(self) -> None:
        self.calls += 1
        raise RuntimeError("boom-forge")


class _FailingMergeTrainStub(_MergeTrainStub):
    def tick(self) -> None:
        self.calls += 1
        raise RuntimeError("boom-merge")


def _decision_rows(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _maintenance_degradations(path: Path) -> list[dict[str, object]]:
    return [row for row in _decision_rows(path) if row.get("event_type") == "runtime_maintenance_degradation"]


@pytest.mark.parametrize(
    ("fail_surface", "expected_counts"),
    [
        ("expand", {"expand": 1, "cycle": 0, "guard": 0, "monitor": 0, "forge": 0, "merge": 0, "next_handoff": 0}),
        ("cycle", {"expand": 1, "cycle": 1, "guard": 0, "monitor": 0, "forge": 0, "merge": 0, "next_handoff": 0}),
        ("guard", {"expand": 1, "cycle": 1, "guard": 1, "monitor": 0, "forge": 0, "merge": 0, "next_handoff": 0}),
        ("monitor", {"expand": 1, "cycle": 1, "guard": 1, "monitor": 1, "forge": 0, "merge": 0, "next_handoff": 0}),
    ],
)
def test_maintenance_tick_failure_surfaces_fail_stop_once_and_restore_runtime(
    tmp_path: Path,
    fail_surface: str,
    expected_counts: dict[str, int],
) -> None:
    decisions_path = tmp_path / "decisions.jsonl"
    kernel = ControlPlaneKernel(
        runtime_governor=_GovernorStub(allow=True),  # type: ignore[arg-type]
        decisions_path=decisions_path,
    )
    surfaces = _FailingRuntimeSurfaceSpy(fail_surface=fail_surface)
    forge = _ForgeDaemonStub()
    merge = _MergeTrainStub()

    _run_maintenance_tick(
        kernel=kernel,
        runtime_surfaces=surfaces,  # type: ignore[arg-type]
        contract_sentinel=_SentinelStub(),  # type: ignore[arg-type]
        forge_daemon=forge,  # type: ignore[arg-type]
        merge_train=merge,  # type: ignore[arg-type]
    )

    assert surfaces.expand_calls == expected_counts["expand"]
    assert surfaces.cycle_calls == expected_counts["cycle"]
    assert surfaces.guard_calls == expected_counts["guard"]
    assert surfaces.monitor_calls == expected_counts["monitor"]
    assert forge.calls == expected_counts["forge"]
    assert merge.calls == expected_counts["merge"]
    assert surfaces.next_handoff_calls == expected_counts["next_handoff"]
    assert surfaces.mark_committed_calls == 0
    assert kernel.phase == LifecyclePhase.RUNTIME

    degradations = _maintenance_degradations(decisions_path)
    assert len(degradations) == 1
    degradation = degradations[0]
    assert degradation == {
        **degradation,
        "event_type": "runtime_maintenance_degradation",
        "schema": "runtime_maintenance_degradation:v1",
        "surface": fail_surface,
        "actor": "sentientosd",
        "severity": "blocking",
        "disposition": "fail_stop_degraded",
        "stopped_active_cycle": True,
        "retry_attempted": False,
        "follow_up_enqueued": False,
        "reinterpreted_as_goal": False,
        "failure_type": "RuntimeError",
        "failure_message": f"boom-{fail_surface}",
        "phase": "maintenance",
        "phase_before": "runtime",
        "phase_at_failure": "maintenance",
    }
    assert degradation["correlation_id"] == f"{degradation['tick_id']}:{fail_surface}"


@pytest.mark.parametrize(
    ("fail_surface", "forge_factory", "merge_factory", "expected_forge", "expected_merge"),
    [
        ("forge_tick", _FailingForgeDaemonStub, _MergeTrainStub, 1, 0),
        ("merge_tick", _ForgeDaemonStub, _FailingMergeTrainStub, 1, 1),
    ],
)
def test_maintenance_tick_forge_merge_failure_fail_stop_once_and_no_retry(
    tmp_path: Path,
    fail_surface: str,
    forge_factory,
    merge_factory,
    expected_forge: int,
    expected_merge: int,
) -> None:
    decisions_path = tmp_path / "decisions.jsonl"
    kernel = ControlPlaneKernel(
        runtime_governor=_GovernorStub(allow=True),  # type: ignore[arg-type]
        decisions_path=decisions_path,
    )
    surfaces = _FailingRuntimeSurfaceSpy(fail_surface="none")
    forge = forge_factory()
    merge = merge_factory()

    _run_maintenance_tick(
        kernel=kernel,
        runtime_surfaces=surfaces,  # type: ignore[arg-type]
        contract_sentinel=_SentinelStub(),  # type: ignore[arg-type]
        forge_daemon=forge,  # type: ignore[arg-type]
        merge_train=merge,  # type: ignore[arg-type]
    )

    assert (surfaces.expand_calls, surfaces.cycle_calls, surfaces.guard_calls, surfaces.monitor_calls) == (1, 1, 1, 1)
    assert forge.calls == expected_forge
    assert merge.calls == expected_merge
    assert surfaces.next_handoff_calls == 0
    assert surfaces.mark_committed_calls == 0
    assert kernel.phase == LifecyclePhase.RUNTIME

    degradations = _maintenance_degradations(decisions_path)
    assert len(degradations) == 1
    assert degradations[0]["surface"] == fail_surface
    assert degradations[0]["retry_attempted"] is False
    assert degradations[0]["follow_up_enqueued"] is False
    assert degradations[0]["reinterpreted_as_goal"] is False


def test_maintenance_tick_handoff_plan_failure_degrades_without_new_action(tmp_path: Path) -> None:
    decisions_path = tmp_path / "decisions.jsonl"
    kernel = ControlPlaneKernel(
        runtime_governor=_GovernorStub(allow=True),  # type: ignore[arg-type]
        decisions_path=decisions_path,
    )
    surfaces = _FailingRuntimeSurfaceSpy(fail_surface="handoff_plan")
    forge = _ForgeDaemonStub()
    merge = _MergeTrainStub()

    _run_maintenance_tick(
        kernel=kernel,
        runtime_surfaces=surfaces,  # type: ignore[arg-type]
        contract_sentinel=_SentinelStub(),  # type: ignore[arg-type]
        forge_daemon=forge,  # type: ignore[arg-type]
        merge_train=merge,  # type: ignore[arg-type]
    )

    assert (surfaces.expand_calls, surfaces.cycle_calls, surfaces.guard_calls, surfaces.monitor_calls) == (1, 1, 1, 1)
    assert forge.calls == 1
    assert merge.calls == 1
    assert surfaces.next_handoff_calls == 1
    assert surfaces.mark_committed_calls == 0
    assert kernel.phase == LifecyclePhase.RUNTIME
    degradations = _maintenance_degradations(decisions_path)
    assert len(degradations) == 1
    assert degradations[0]["surface"] == "repository_mutation_handoff"
    assert degradations[0]["phase_at_failure"] == "runtime"

def test_runtime_feedback_degradation_is_reused_for_later_maintenance_gating(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("SENTIENTOS_ENFORCEMENT_RUNTIME_GOVERNOR", "enforce")

    def _nominal_eval(self, *, action_class: str, metadata: dict[str, object] | None):
        del self, action_class, metadata
        return (
            PostureRuleEvaluation(
                dimension="test_nominal",
                reason="allowed",
                restriction_class="none",
                blocks=False,
                precedence=1,
                details={},
            ),
            {},
        )

    monkeypatch.setattr(RuntimeGovernor, "_evaluate_audit_trust_posture", _nominal_eval)
    monkeypatch.setattr(RuntimeGovernor, "_evaluate_pulse_epoch_posture", _nominal_eval)

    call_counts = {"expand": 0, "cycle": 0, "guard": 0, "monitor": 0}

    def _fake_expand(_root, *, telemetry_streams=None, vows=None, proposal_only=True):  # noqa: ANN001
        call_counts["expand"] += 1
        return []

    def _fake_cycle(_root, *, signals=()):  # noqa: ANN001
        call_counts["cycle"] += 1
        return {"panel": "Spec Amendments", "pending": [], "approved": [], "items": []}

    def _fake_guard(_root):
        call_counts["guard"] += 1
        return {"daemon": "IntegrityDaemon", "status": "alert", "quarantined": 1, "passed": 0}

    def _fake_monitor(_root):
        call_counts["monitor"] += 1
        return []

    monkeypatch.setattr("sentientosd.runtime_genesis_expand", _fake_expand)
    monkeypatch.setattr("sentientosd.runtime_spec_cycle", _fake_cycle)
    monkeypatch.setattr("sentientosd.runtime_integrity_guard", _fake_guard)
    monkeypatch.setattr("sentientosd.runtime_healer_monitor", _fake_monitor)

    kernel = ControlPlaneKernel(runtime_governor=RuntimeGovernor(), decisions_path=tmp_path / "decisions.jsonl")
    surfaces = RuntimeMaintenanceSurfaces(tmp_path)
    forge = _ForgeDaemonStub()
    merge = _MergeTrainStub()
    sentinel = _SentinelStub()

    _run_maintenance_tick(
        kernel=kernel,
        runtime_surfaces=surfaces,
        contract_sentinel=sentinel,  # type: ignore[arg-type]
        forge_daemon=forge,  # type: ignore[arg-type]
        merge_train=merge,  # type: ignore[arg-type]
    )
    assert call_counts == {"expand": 1, "cycle": 1, "guard": 1, "monitor": 1}

    _run_maintenance_tick(
        kernel=kernel,
        runtime_surfaces=surfaces,
        contract_sentinel=sentinel,  # type: ignore[arg-type]
        forge_daemon=forge,  # type: ignore[arg-type]
        merge_train=merge,  # type: ignore[arg-type]
    )
    assert call_counts["expand"] == 1
    assert call_counts["cycle"] == 1
    assert call_counts["guard"] == 1
    assert call_counts["monitor"] == 2

    rows = [json.loads(line) for line in (tmp_path / "decisions.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(
        row.get("action_kind") == "expand"
        and row.get("final_disposition") == "deny"
        and any("runtime_governor:runtime_feedback_degraded_maintenance" in reason for reason in row.get("reason_codes", []))
        for row in rows
    )


def test_maintenance_tick_emits_handoff_without_git_or_mark_committed(tmp_path: Path, monkeypatch) -> None:
    kernel = ControlPlaneKernel(
        runtime_governor=_GovernorStub(allow=True),  # type: ignore[arg-type]
        decisions_path=tmp_path / "decisions.jsonl",
    )

    class _Plan:
        message = "review"
        proposal = {
            "proposal_id": "p1",
            "status": "approved",
            "ledger_entry": "ledger",
            "approved_paths": ["a.txt"],
            "summary": "review",
        }

    class _HandoffSpy(_RuntimeSurfaceSpy):
        def __init__(self) -> None:
            super().__init__()
            self.handoff_calls = 0
            self.mark_committed_calls = 0

        def next_repository_mutation_handoff(self):
            return _Plan()

        def emit_repository_mutation_handoff(self, plan) -> dict[str, object]:
            self.handoff_calls += 1
            assert plan is not None
            return {"metadata_only": True}

        def mark_committed(self, _plan) -> None:
            self.mark_committed_calls += 1
            raise AssertionError("sentientosd must not mark committed after handoff")

    surfaces = _HandoffSpy()
    _run_maintenance_tick(
        kernel=kernel,
        runtime_surfaces=surfaces,  # type: ignore[arg-type]
        contract_sentinel=_SentinelStub(),  # type: ignore[arg-type]
        forge_daemon=_ForgeDaemonStub(),  # type: ignore[arg-type]
        merge_train=_MergeTrainStub(),  # type: ignore[arg-type]
    )
    assert surfaces.handoff_calls == 1
    assert surfaces.mark_committed_calls == 0
    assert not _maintenance_degradations(tmp_path / "decisions.jsonl")

def test_sentientosd_has_no_host_fulfillment_consumption_runtime_calls() -> None:
    import sentientosd
    text = open(sentientosd.__file__, encoding='utf-8').read()
    assert 'HostFulfillmentAuthorizationRuntimeCoordinator' not in text
    assert 'host_fulfillment_authorization_consumption' not in text

def test_sentientosd_has_no_host_fulfillment_executor_readiness_runtime_calls() -> None:
    import sentientosd
    text = open(sentientosd.__file__, encoding='utf-8').read()
    assert 'HostFulfillmentExecutorReadinessRuntimeCoordinator' not in text
    assert 'host_fulfillment_executor_contract_readiness_metadata_evaluation' not in text
def test_overlapping_watchdog_and_wake_adoptions_start_neither(monkeypatch) -> None:
    started: list[str] = []
    class Owner:
        def __init__(self, _config): pass
        def start(self): started.append("started")
    monkeypatch.setattr(sentientosd, "load_adoption", lambda path: {"enabled": True})
    monkeypatch.setattr(sentientosd, "load_wake_adoption", lambda path: {"enabled": True})
    monkeypatch.setattr(sentientosd, "MaintenanceSchedulerOwner", Owner)
    monkeypatch.setattr(sentientosd, "MaintenanceWakeOwner", Owner)
    scheduler_owner, wake_owner, successor_owner, overlapping = sentientosd._start_maintenance_daemon_owners("scheduler", "wake")
    assert overlapping is True and scheduler_owner is None and wake_owner is None and successor_owner is None and started == []


def test_successor_mode_uses_production_canonical_builder(monkeypatch, tmp_path) -> None:
    from sentientos import maintenance_successor_generation_adoption as successor
    cfg = {"enabled": True, "shutdown_timeout_seconds": 1}
    monkeypatch.setattr(sentientosd, "load_successor_adoption", lambda _path: cfg)
    monkeypatch.setattr(successor, "validate_config", lambda value: dict(value))
    monkeypatch.setattr(successor.MaintenanceSuccessorGenerationOwner, "start", lambda self: True)
    _, _, owner, overlapping = sentientosd._start_maintenance_daemon_owners(None, None, "successor")
    assert overlapping is False and owner is not None and callable(owner._builder)
def test_blocked_resident_startup_never_starts_ungated_successor_owner(monkeypatch) -> None:
    calls: list[object] = []
    monkeypatch.setattr(sentientosd, "_start_maintenance_daemon_owners", lambda *args: calls.append(args))
    result = sentientosd._start_maintenance_daemon_owners_after_resident_decision(
        None, None, "/external/pending-successor.json", None, resident_blocked=True)
    assert result == (None, None, None, False)
    assert calls == []


def test_blocked_enabled_resident_posture_runs_zero_maintenance_ticks(monkeypatch, tmp_path) -> None:
    counters = {name: 0 for name in ("tick", "scheduler", "wake", "successor", "automatic")}

    class CountingEvent(asyncio.Event):
        loop_decisions = 0
        def set(self) -> None:
            self.loop_decisions += 1
            super().set()

    class Kernel:
        def set_phase(self, *_args, **_kwargs): pass

    class Surfaces:
        def __init__(self, *_args, **_kwargs):
            self._feedback = {"surfaces": {}}

    class ResidentController:
        def __init__(self, _config): pass

    def owner(name):
        class ForbiddenOwner:
            def __init__(self, *_args, **_kwargs):
                counters[name] += 1
            def start(self):
                counters[name] += 1
                return True
        return ForbiddenOwner

    monkeypatch.setattr(sentientosd.CeremonialScript, "perform", lambda self: None)
    monkeypatch.setattr(sentientosd.FirstContact, "affirm_integrity", lambda self: None)
    monkeypatch.setattr(sentientosd.FirstContact, "invite_conversation", lambda self: None)
    monkeypatch.setattr(sentientosd, "build_boot_ceremony_link", lambda _emitter: SimpleNamespace(narrate=lambda: None))
    monkeypatch.setattr(sentientosd.LocalModel, "autoload", lambda: SimpleNamespace(describe=lambda: "test"))
    monkeypatch.setattr(sentientosd, "ForgeDaemon", lambda: SimpleNamespace(repo_root=tmp_path))
    monkeypatch.setattr(sentientosd, "ForgeMergeTrain", lambda **_kwargs: SimpleNamespace())
    monkeypatch.setattr(sentientosd, "ContractSentinel", lambda: SimpleNamespace())
    monkeypatch.setattr(sentientosd, "get_control_plane_kernel", lambda: Kernel())
    monkeypatch.setattr(sentientosd, "build_local_model_authority_map", lambda: {})
    monkeypatch.setattr(sentientosd, "GovernedLocalModelInvoker", lambda **_kwargs: SimpleNamespace())
    monkeypatch.setattr(sentientosd, "GenesisModelAdviceCoordinator", lambda **_kwargs: SimpleNamespace())
    monkeypatch.setattr(sentientosd, "resolve_improvement_evidence_sources", lambda _root: ())
    monkeypatch.setattr(sentientosd, "RuntimeMaintenanceSurfaces", Surfaces)
    monkeypatch.setattr(sentientosd, "load_resident_adoption", lambda _path: {
        "successor_adoption_config_path": str(tmp_path / "successor.json"),
        "automatic_continuity_config_path": str(tmp_path / "automatic.json"),
    })
    monkeypatch.setattr(sentientosd, "MaintenanceResidentRuntimeAdoptionController", ResidentController)
    monkeypatch.setattr(sentientosd, "_prepare_resident_runtime_startup",
                        lambda _controller: (_ for _ in ()).throw(ValueError("reconciliation_failed")))
    monkeypatch.setattr(sentientosd, "MaintenanceSchedulerOwner", owner("scheduler"))
    monkeypatch.setattr(sentientosd, "MaintenanceWakeOwner", owner("wake"))
    monkeypatch.setattr(sentientosd, "MaintenanceSuccessorGenerationOwner", owner("successor"))
    monkeypatch.setattr(sentientosd, "MaintenanceAuthorityContinuityAutoDerivationOwner", owner("automatic"))
    monkeypatch.setattr(sentientosd, "_run_maintenance_tick",
                        lambda **_kwargs: counters.__setitem__("tick", counters["tick"] + 1))
    monkeypatch.setenv("SENTIENTOS_MAINTENANCE_SCHEDULER_ADOPTION_CONFIG", str(tmp_path / "scheduler.json"))
    monkeypatch.setenv("SENTIENTOS_MAINTENANCE_WAKE_ADOPTION_CONFIG", str(tmp_path / "wake.json"))
    monkeypatch.setenv("SENTIENTOS_MAINTENANCE_SUCCESSOR_GENERATION_ADOPTION_CONFIG", str(tmp_path / "successor.json"))
    monkeypatch.setenv("SENTIENTOS_MAINTENANCE_AUTHORITY_CONTINUITY_AUTO_DERIVATION_CONFIG", str(tmp_path / "automatic.json"))
    monkeypatch.setenv("SENTIENTOS_MAINTENANCE_RESIDENT_RUNTIME_ADOPTION_CONFIG", str(tmp_path / "resident.json"))

    shutdown = CountingEvent()
    asyncio.run(sentientosd.run_loop(shutdown, interval_seconds=0))
    assert shutdown.loop_decisions >= 1
    assert counters == {name: 0 for name in counters}
