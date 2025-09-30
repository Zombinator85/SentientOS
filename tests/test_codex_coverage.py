from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from codex.coverage import CoverageAnalyzer
from codex.testcycles import TestSynthesizer
from coverage_dashboard import approve_coverage_proposal, coverage_panel_state


class ManualClock:
    def __init__(self) -> None:
        self.moment = datetime(2025, 1, 1, tzinfo=timezone.utc)

    def now(self) -> datetime:
        current = self.moment
        self.moment += timedelta(seconds=1)
        return current


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_coverage_analyzer_flags_gaps(tmp_path: Path) -> None:
    clock = ManualClock()
    synth = TestSynthesizer(
        repo_root=tmp_path,
        integration_root=tmp_path / "integration",
        now=clock.now,
    )
    analyzer = CoverageAnalyzer(
        repo_root=tmp_path,
        integration_root=tmp_path / "integration",
        pulse_root=tmp_path / "pulse" / "anomalies",
        synthesizer=synth,
        now=clock.now,
    )

    source_index = {
        "codex.module": {
            "functions": ["covered_func", "missing_func"],
            "branches": ["branch_a", "branch_b"],
            "integration_flows": ["flow_alpha"],
        }
    }
    test_results = {
        "codex.module": {
            "functions": ["covered_func"],
            "branches": ["branch_a"],
            "integration_flows": [],
        }
    }
    link_index = {
        "codex.module:missing_func": {"spec_id": "spec-coverage-1"},
        "codex.module:branch_b": "spec-coverage-1",
        "codex.module:flow_alpha": {"scaffold": "scaffold-alpha"},
    }

    coverage_map = analyzer.analyze(test_results, source_index, link_index=link_index)

    assert coverage_map["modules"], "Module coverage should be captured"
    module_entry = coverage_map["modules"][0]
    assert "missing_func" in module_entry["functions"]["untested"]
    assert module_entry["branches"]["missing"] == ["branch_b"]
    assert module_entry["integration_flows"]["missing"] == ["flow_alpha"]

    gap_ids = {gap["gap_id"] for gap in coverage_map["gaps"]}
    assert any(gap.endswith("missing_func") for gap in gap_ids)
    assert any(gap.endswith("branch_b") for gap in gap_ids)
    assert any(gap.endswith("flow_alpha") for gap in gap_ids)

    coverage_path = tmp_path / "integration" / "coverage_map.json"
    assert coverage_path.exists(), "Coverage map should be written to integration root"
    stored_map = json.loads(coverage_path.read_text(encoding="utf-8"))
    assert stored_map["gaps"], "Stored coverage map should include gaps"

    pulse_path = tmp_path / "pulse" / "anomalies" / "coverage_gaps.jsonl"
    events = _read_jsonl(pulse_path)
    assert events and events[0]["event_type"] == "coverage_gap_detected"

    log_entries = _read_jsonl(tmp_path / "integration" / "coverage_log.jsonl")
    assert any(entry["event"] == "coverage_delta" for entry in log_entries)

    pending = synth.pending()
    assert pending, "Coverage gaps should propose new tests"
    targets = {proposal.coverage_target for proposal in pending}
    assert "function:codex.module:missing_func" in targets


def test_coverage_dashboard_surfaces_map_and_gating(tmp_path: Path) -> None:
    clock = ManualClock()
    synth = TestSynthesizer(
        repo_root=tmp_path,
        integration_root=tmp_path / "integration",
        now=clock.now,
    )
    analyzer = CoverageAnalyzer(
        repo_root=tmp_path,
        integration_root=tmp_path / "integration",
        pulse_root=tmp_path / "pulse" / "anomalies",
        synthesizer=synth,
        now=clock.now,
    )

    source_index = {
        "codex.dashboard": {
            "functions": ["alpha", "beta"],
            "branches": [],
            "integration_flows": [],
        }
    }
    test_results = {
        "codex.dashboard": {
            "functions": ["alpha"],
            "branches": [],
            "integration_flows": [],
        }
    }
    link_index = {
        "codex.dashboard:beta": {
            "spec_id": "spec-dashboard",
            "scaffold": "scaffold-beta",
            "origin": "scaffold",
        }
    }

    coverage_map = analyzer.analyze(test_results, source_index, link_index=link_index)
    assert coverage_map["gaps"], "Initial run should report coverage gaps"

    gap_id = coverage_map["gaps"][0]["gap_id"]
    analyzer.record_feedback(gap_id, "critical", operator="aurora")

    analyzer.analyze(test_results, source_index, link_index=link_index)

    state = coverage_panel_state(analyzer, synthesizer=synth)
    assert state["panel"] == "Coverage Map"
    assert state["requires_operator_approval"], "Coverage remediation should be ledger gated"
    assert state["pending_proposals"], "Pending proposals must be reviewed"

    gap_feedback = state["coverage"]["gaps"][0].get("feedback", {})
    assert gap_feedback.get("critical") == 1
    assert gap_feedback.get("_last_operator") == "aurora"

    proposal_id = state["pending_proposals"][0]["proposal_id"]
    approve_coverage_proposal(proposal_id, operator="aurora", synthesizer=synth)
    assert synth.approved(), "Operator approval should promote proposal to active suite"

    improved_results = {
        "codex.dashboard": {
            "functions": ["alpha", "beta"],
            "branches": [],
            "integration_flows": [],
        }
    }
    improved_map = analyzer.analyze(improved_results, source_index, link_index=link_index)
    assert improved_map["overall"]["functions"]["coverage"] == pytest.approx(1.0)

    log_entries = _read_jsonl(tmp_path / "integration" / "coverage_log.jsonl")
    assert any(
        entry.get("event") == "coverage_delta" and entry.get("overall", {}).get("functions", {}).get("coverage") == pytest.approx(1.0)
        for entry in log_entries
    )
