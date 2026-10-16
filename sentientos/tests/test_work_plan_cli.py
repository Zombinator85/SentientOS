#  _____  _             _
# |  __ \| |           (_)
# | |__) | |_   _  __ _ _ _ __   __ _
# |  ___/| | | | |/ _` | | '_ \ / _` |
# | |    | | |_| | (_| | | | | | (_| |
# |_|    |_\__,_|\__, |_|_| |_|\__, |
#                  __/ |         __/ |
#                 |___/         |___/ 

from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from scripts import work_plan_run
from sentientos.goal_executor import GoalExecutor
from sentientos.risk_budget import RiskBudget
from sentientos.work_plan import (
    Task,
    WorkPlan,
    WorkPlanError,
    persist_work_plan,
    persist_work_plan_evidence,
    work_plan_id_from_evidence,
)


def _canonical_plan() -> tuple[WorkPlan, dict[str, object]]:
    created_at = "2026-10-16T09:00:00Z"
    evidence_binding: dict[str, object] = {
        "goal_graph_hash": "graph-digest",
        "allocation_artifact_path": "glow/forge/allocations/allocation.json",
    }
    plan = WorkPlan(
        schema_version=1,
        plan_id=work_plan_id_from_evidence(
            created_at,
            str(evidence_binding["goal_graph_hash"]),
            str(evidence_binding["allocation_artifact_path"]),
            evidence_binding,
        ),
        created_at=created_at,
        context="orchestrator_tick",
        selected_goals=("g1",),
        tasks=(Task(1, "g1:diagnostic", "g1", "diagnostic", (), None,
            0, 0, {}, (), False),),
    )
    return plan, evidence_binding


def test_canonical_cli_plan_without_evidence_fails_before_execution_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, _ = _canonical_plan()
    relative_path = persist_work_plan(tmp_path, plan)
    monkeypatch.setattr(work_plan_run, "load_quarantine_state",
        lambda _root: pytest.fail("policy must not be read before evidence"))
    monkeypatch.setattr(sys, "argv", [
        "work_plan_run", str(tmp_path / relative_path), "--repo-root", str(tmp_path)])

    with pytest.raises(WorkPlanError, match="work_plan_evidence_unreadable"):
        work_plan_run.main()


def test_canonical_cli_passes_verified_evidence_digest_to_executor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, evidence_binding = _canonical_plan()
    relative_path = persist_work_plan(tmp_path, plan)
    _, expected_digest = persist_work_plan_evidence(
        tmp_path, plan, evidence_binding)
    monkeypatch.setattr(work_plan_run, "load_quarantine_state",
        lambda _root: SimpleNamespace(active=False))
    monkeypatch.setattr(work_plan_run, "compute_integrity_pressure",
        lambda _root: SimpleNamespace(level=0))
    monkeypatch.setattr(work_plan_run, "derive_throughput_policy",
        lambda **_kwargs: SimpleNamespace(mode="normal", allow_forge_mutation=True))
    monkeypatch.setattr(work_plan_run, "resolve_posture",
        lambda: SimpleNamespace(posture="balanced"))
    monkeypatch.setattr(work_plan_run, "compute_risk_budget",
        lambda **_kwargs: RiskBudget())
    monkeypatch.setattr(work_plan_run, "emit_policy_fingerprint",
        lambda _root: SimpleNamespace(policy_hash="policy-digest"))
    monkeypatch.setattr(work_plan_run, "evaluate_integrity",
        lambda _root, *, policy_hash: SimpleNamespace(
            mutation_allowed=True, policy_hash=policy_hash))
    observed: list[str | None] = []

    def execute(_executor: object, _plan: WorkPlan, _state: object, *,
                expected_evidence_digest: str | None = None) -> SimpleNamespace:
        observed.append(expected_evidence_digest)
        return SimpleNamespace(to_dict=lambda: {"status": "ok"})

    monkeypatch.setattr(GoalExecutor, "execute_plan", execute)
    monkeypatch.setattr(sys, "argv", [
        "work_plan_run", str(tmp_path / relative_path), "--repo-root", str(tmp_path)])

    assert work_plan_run.main() == 0
    assert observed == [expected_digest]


def test_cli_execution_uses_current_integrity_pressure_to_bound_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, evidence_binding = _canonical_plan()
    relative_path = persist_work_plan(tmp_path, plan)
    persist_work_plan_evidence(tmp_path, plan, evidence_binding)
    observed_pressure: list[int] = []
    observed_state: list[object] = []

    monkeypatch.setattr(work_plan_run, "load_quarantine_state",
        lambda _root: SimpleNamespace(active=False))
    monkeypatch.setattr(work_plan_run, "compute_integrity_pressure",
        lambda _root: SimpleNamespace(level=3))

    def derive_policy(*, integrity_pressure_level: int, quarantine: object):
        del quarantine
        observed_pressure.append(integrity_pressure_level)
        return SimpleNamespace(mode="lockdown", allow_forge_mutation=False)

    monkeypatch.setattr(work_plan_run, "derive_throughput_policy", derive_policy)
    monkeypatch.setattr(work_plan_run, "resolve_posture",
        lambda: SimpleNamespace(posture="balanced"))
    monkeypatch.setattr(work_plan_run, "compute_risk_budget",
        lambda **_kwargs: RiskBudget(pressure_level=3, operating_mode="lockdown"))
    monkeypatch.setattr(work_plan_run, "emit_policy_fingerprint",
        lambda _root: SimpleNamespace(policy_hash="policy-digest"))
    monkeypatch.setattr(work_plan_run, "evaluate_integrity",
        lambda _root, *, policy_hash: SimpleNamespace(
            mutation_allowed=False, policy_hash=policy_hash))

    def capture_execution(_executor: object, _plan: WorkPlan, state: object, *,
                          expected_evidence_digest: str | None = None) -> SimpleNamespace:
        del expected_evidence_digest
        observed_state.append(state)
        return SimpleNamespace(to_dict=lambda: {"status": "ok"})

    monkeypatch.setattr(GoalExecutor, "execute_plan", capture_execution)
    monkeypatch.setattr(sys, "argv", [
        "work_plan_run", str(tmp_path / relative_path), "--repo-root", str(tmp_path)])

    assert work_plan_run.main() == 0
    assert observed_pressure == [3]
    assert len(observed_state) == 1
    state = observed_state[0]
    assert state.operating_mode == "lockdown"  # type: ignore[attr-defined]
    assert state.allow_mutation is False  # type: ignore[attr-defined]
    assert state.pressure_level == 3  # type: ignore[attr-defined]
