from __future__ import annotations

import importlib
import json
import sys
from typing import Any

import pytest
import capability_ledger
import capability_ledger_cli
import reflexion_loop
from log_utils import read_json


@pytest.mark.no_legacy_skip
def test_capability_ledger_does_not_change_plan_order(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    importlib.reload(capability_ledger)
    importlib.reload(reflexion_loop)

    recorded_entries: list[tuple[Any, dict[str, Any], str, str | bool]] = []

    def fake_append_json(path, entry, *, emotion="neutral", consent=True):
        recorded_entries.append((path, entry, emotion, consent))

    monkeypatch.setattr(capability_ledger, "append_json", fake_append_json)
    importlib.reload(reflexion_loop)

    goal = {"id": "plan-001", "text": "demo goal", "plan": ["a", "b", "c"]}
    result = {"status": "finished"}

    monkeypatch.setattr(reflexion_loop.mm, "latest_observation", lambda include_embedding=False: None)
    monkeypatch.setattr(reflexion_loop.mm, "append_memory", lambda *_, **__: None)

    insight = reflexion_loop.record_insight(goal, result)

    assert goal["plan"] == ["a", "b", "c"]
    assert insight["status"] == "success"
    assert recorded_entries, "capability ledger entry was not recorded"
    _, entry, emotion, consent = recorded_entries[0]
    assert entry["axis"] == capability_ledger.CapabilityAxis.INTERNAL_COHERENCE.value
    assert entry["delta"].endswith("status=success")
    assert emotion == "neutral"
    assert consent == "epistemic"


def test_capability_ledger_inspection_matches_storage(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    importlib.reload(capability_ledger)

    ledger = capability_ledger.CapabilityGrowthLedger()
    first = capability_ledger.CapabilityLedgerEntry(
        axis=capability_ledger.CapabilityAxis.STRUCTURAL_RICHNESS,
        measurement_method="test/probe_structures",
        delta="added-new-schema",
    )
    second = capability_ledger.CapabilityLedgerEntry(
        axis=capability_ledger.CapabilityAxis.EXPRESSIVE_RANGE,
        measurement_method="test/probe_expressive",
        delta="documented-additional-tone",
    )

    ledger.record(first)
    ledger.record(second)

    stored_entries = read_json(ledger.path)
    assert stored_entries, "ledger should contain recorded entries"

    axis_filtered = ledger.inspect(axis=capability_ledger.CapabilityAxis.STRUCTURAL_RICHNESS)
    assert axis_filtered == (stored_entries[0],)

    window_start = stored_entries[0]["timestamp"]
    window_end = stored_entries[-1]["timestamp"]

    windowed_entries = ledger.inspect(since=window_start, until=window_end)
    assert windowed_entries == tuple(stored_entries)
    assert read_json(ledger.path) == stored_entries


def test_capability_ledger_version_metadata(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    importlib.reload(capability_ledger)

    monkeypatch.setattr(capability_ledger, "_read_version_id", lambda: "v9")
    monkeypatch.setattr(capability_ledger, "_read_git_commit", lambda: "commit-abc")

    ledger = capability_ledger.CapabilityGrowthLedger()
    auto = capability_ledger.CapabilityLedgerEntry(
        axis=capability_ledger.CapabilityAxis.CAPABILITY_COVERAGE,
        measurement_method="auto-fill",
        delta="auto-detected",
    )
    explicit = capability_ledger.CapabilityLedgerEntry(
        axis=capability_ledger.CapabilityAxis.INTERNAL_COHERENCE,
        measurement_method="explicit",
        delta="explicit-version",
        version_id="caller-version",
    )
    commit_only = capability_ledger.CapabilityLedgerEntry(
        axis=capability_ledger.CapabilityAxis.EXPRESSIVE_RANGE,
        measurement_method="commit-only",
        delta="commit-detected",
        git_commit="caller-commit",
    )

    ledger.record(auto)
    ledger.record(explicit)
    ledger.record(commit_only)

    stored_entries = read_json(ledger.path)
    assert len(stored_entries) == 3

    assert stored_entries[0]["version_id"] == "v9"
    assert stored_entries[0]["git_commit"] == "commit-abc"
    assert stored_entries[1]["version_id"] == "caller-version"
    assert stored_entries[1]["git_commit"] == "commit-abc"
    assert stored_entries[2]["version_id"] == "v9"
    assert stored_entries[2]["git_commit"] == "caller-commit"

    version_filtered = ledger.inspect(version_id="caller-version")
    assert version_filtered == (stored_entries[1],)

    commit_filtered = ledger.inspect(git_commit="caller-commit")
    assert commit_filtered == (stored_entries[2],)

    assert ledger.inspect() == tuple(stored_entries)


def test_inspection_remains_read_only(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    importlib.reload(capability_ledger)
    importlib.reload(reflexion_loop)

    goal = {"id": "plan-002", "text": "inspect goal", "plan": ["first", "second", "third"]}
    result = {"status": "finished"}

    monkeypatch.setattr(reflexion_loop.mm, "latest_observation", lambda include_embedding=False: None)
    monkeypatch.setattr(reflexion_loop.mm, "append_memory", lambda *_, **__: None)

    insight = reflexion_loop.record_insight(goal, result)
    ledger = capability_ledger.CapabilityGrowthLedger()
    before_inspection = read_json(ledger.path)

    inspection = ledger.inspect()

    assert goal["plan"] == ["first", "second", "third"]
    assert insight["status"] == "success"
    assert inspection == tuple(before_inspection)
    assert read_json(ledger.path) == before_inspection


def test_capability_ledger_export_is_deterministic(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    importlib.reload(capability_ledger)
    importlib.reload(capability_ledger_cli)
    importlib.reload(reflexion_loop)

    goal = {"id": "plan-003", "text": "export goal", "plan": ["alpha", "beta", "gamma"]}
    result = {"status": "finished"}

    monkeypatch.setattr(reflexion_loop.mm, "latest_observation", lambda include_embedding=False: None)
    monkeypatch.setattr(reflexion_loop.mm, "append_memory", lambda *_, **__: None)

    reflexion_loop.record_insight(goal, result)

    ledger = capability_ledger.CapabilityGrowthLedger()
    manual_entry = capability_ledger.CapabilityLedgerEntry(
        axis=capability_ledger.CapabilityAxis.CAPABILITY_COVERAGE,
        measurement_method="manual/export",
        delta="documented",
        version_id="export-version",
        git_commit="export-commit",
    )
    ledger.record(manual_entry)

    stored_before = read_json(ledger.path)
    expected_json = json.dumps(list(capability_ledger.inspect()), separators=(",", ":")) + "\n"

    monkeypatch.setattr(sys, "argv", ["capability-ledger", "--format", "json"])
    capability_ledger_cli.main()

    json_output = capsys.readouterr().out
    assert json_output == expected_json
    assert read_json(ledger.path) == stored_before
    assert goal["plan"] == ["alpha", "beta", "gamma"]

    filtered_expected = "".join(
        json.dumps(row, separators=(",", ":")) + "\n"
        for row in capability_ledger.inspect(version_id="export-version")
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "capability-ledger",
            "--format",
            "jsonl",
            "--version-id",
            "export-version",
            "--git-commit",
            "export-commit",
        ],
    )
    capability_ledger_cli.main()
    jsonl_output = capsys.readouterr().out
    assert jsonl_output == filtered_expected
    assert read_json(ledger.path) == stored_before
    assert goal["plan"] == ["alpha", "beta", "gamma"]
