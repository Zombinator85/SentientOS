from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from codex.implementations import Implementor
from codex.refinements import Refiner
from codex.specs import SpecProposal
from codex.testcycles import TestCycleManager, TestSynthesizer
from generated_tests_dashboard import generated_tests_panel_state


class ManualClock:
    def __init__(self) -> None:
        self.moment = datetime(2025, 5, 1, tzinfo=timezone.utc)

    def now(self) -> datetime:
        current = self.moment
        self.moment += timedelta(minutes=1)
        return current


def _proposal(spec_id: str) -> SpecProposal:
    return SpecProposal(
        spec_id=spec_id,
        title="Codex test cycle",
        objective="Exercise synthesized test loops",
        directives=["Implement base function"],
        testing_requirements=["Codex must propose tests"],
        trigger_key="cycle::test",
        trigger_context={"source": "test"},
        status="queued",
    )


def _bootstrap(tmp_path: Path) -> tuple[Implementor, Refiner, TestSynthesizer, TestCycleManager, SpecProposal, ManualClock]:
    clock = ManualClock()
    implementor = Implementor(
        repo_root=tmp_path,
        integration_root=tmp_path / "integration",
        now=clock.now,
    )
    refiner = Refiner(
        repo_root=tmp_path,
        integration_root=tmp_path / "integration",
        implementor=implementor,
        now=clock.now,
    )
    synthesizer = TestSynthesizer(
        repo_root=tmp_path,
        integration_root=tmp_path / "integration",
        now=clock.now,
    )
    proposal = _proposal("spec-test-cycle")
    implementor.draft_from_scaffold(
        proposal,
        {
            "paths": {
                "daemon": "codex/generated_daemon.py",
                "test": "tests/test_generated_daemon.py",
            }
        },
    )
    manager = TestCycleManager(
        implementor=implementor,
        refiner=refiner,
        synthesizer=synthesizer,
        run_tests=lambda _: True,
    )
    return implementor, refiner, synthesizer, manager, proposal, clock


def _read_log(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_synthesizer_generates_pending_tests(tmp_path: Path) -> None:
    implementor, _refiner, synthesizer, manager, proposal, _clock = _bootstrap(tmp_path)
    record = implementor.load_record(proposal.spec_id)
    target_paths = [block.target_path for block in record.blocks if block.target_path]

    proposals = manager.propose_from_failure(
        proposal.spec_id,
        failure="branch not covered",
        feedback="Add missing guard",
        coverage_target="branch",
        implementation_paths=target_paths,
        operator="aurora",
    )

    assert proposals, "Synthesizer should emit at least one proposal"
    pending_dir = tmp_path / "tests" / "generated" / "pending"
    template_files = list(pending_dir.glob("*.py.tmpl"))
    assert template_files, "Pending directory should contain generated templates"
    template_text = template_files[0].read_text(encoding="utf-8")
    assert proposal.spec_id in template_text
    assert "Add missing guard" in template_text

    log_entries = _read_log(tmp_path / "integration" / "test_cycle_log.jsonl")
    assert any(entry["action"] == "test_proposed" for entry in log_entries)

    dashboard = generated_tests_panel_state(synthesizer)
    assert dashboard["panel"] == "Generated Tests"
    assert dashboard["pending"], "Dashboard should surface pending proposals"


def test_operator_gating_before_tests_run(tmp_path: Path) -> None:
    implementor, refiner, synthesizer, _manager, proposal, _clock = _bootstrap(tmp_path)
    record = implementor.load_record(proposal.spec_id)
    target_paths = [block.target_path for block in record.blocks if block.target_path]
    synthesizer.propose_tests(
        proposal.spec_id,
        failure_context="runtime error",
        feedback="Tighten validation",
        implementation_paths=target_paths,
        coverage_target="regression",
        operator="aurora",
    )

    run_invocations: list[list[str]] = []

    def _run_tests(paths: list[Path]) -> bool:
        run_invocations.append([str(path) for path in paths])
        return True

    manager = TestCycleManager(
        implementor=implementor,
        refiner=refiner,
        synthesizer=synthesizer,
        run_tests=_run_tests,
    )

    with pytest.raises(RuntimeError):
        manager.run_round(
            proposal.spec_id,
            operator="aurora",
            change_summary="Apply validation guard",
            failure="runtime error",
        )

    pending = synthesizer.pending(spec_id=proposal.spec_id)
    approved = synthesizer.approve(pending[0].proposal_id, operator="aurora")
    result = manager.run_round(
        proposal.spec_id,
        operator="aurora",
        change_summary="Apply validation guard",
        failure="runtime error",
    )

    assert result["status"] == "passed"
    assert run_invocations, "Test runner should execute after approval"
    executed_paths = run_invocations[-1]
    assert any(approved.test_path in path for path in executed_paths)


def test_refinement_runs_against_existing_and_new_tests(tmp_path: Path) -> None:
    implementor, refiner, synthesizer, _manager, proposal, _clock = _bootstrap(tmp_path)
    record = implementor.load_record(proposal.spec_id)
    target_paths = [block.target_path for block in record.blocks if block.target_path]
    proposals = synthesizer.propose_tests(
        proposal.spec_id,
        failure_context="assertion failure",
        feedback="cover failure path",
        implementation_paths=target_paths,
        coverage_target="branch",
        operator="aurora",
    )
    synthesizer.approve(proposals[0].proposal_id, operator="aurora")

    invocation_log: list[list[str]] = []

    def _run_tests(paths: list[Path]) -> bool:
        invocation_log.append([str(path) for path in paths])
        return False

    manager = TestCycleManager(
        implementor=implementor,
        refiner=refiner,
        synthesizer=synthesizer,
        run_tests=_run_tests,
    )

    result = manager.run_round(
        proposal.spec_id,
        operator="aurora",
        change_summary="broaden coverage",
        failure="assertion failure",
    )

    assert result["status"] == "refined"
    record = implementor.load_record(proposal.spec_id)
    assert record.pending_version == result["version_id"]
    assert invocation_log, "Test runner should be invoked"
    executed = invocation_log[-1]
    assert any("tests/generated" in path for path in executed)

    log_entries = _read_log(tmp_path / "integration" / "test_cycle_log.jsonl")
    actions = {entry["action"] for entry in log_entries}
    assert {"tests_triggered", "refinement_generated"}.issubset(actions)


def test_cycle_halt_and_final_rejection(tmp_path: Path) -> None:
    implementor, refiner, synthesizer, manager, proposal, _clock = _bootstrap(tmp_path)

    halt_result = manager.run_round(
        proposal.spec_id,
        operator="aurora",
        change_summary="noop",
        failure="halt",
        halt=True,
    )
    assert halt_result["status"] == "halted"

    refiner.flag_final_rejected(
        proposal.spec_id,
        "v1",
        operator="aurora",
        reason="Operator rejected refinement",
    )

    rejection_result = manager.run_round(
        proposal.spec_id,
        operator="aurora",
        change_summary="noop",
        failure="halt",
    )
    assert rejection_result["status"] == "final_rejected"
