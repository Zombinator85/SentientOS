from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import generate_immutable_manifest
from sentientos.forge_merge_train import ForgeMergeTrain, TrainEntry, TrainState
from sentientos.scoped_canonical_trace_coherence import evaluate_scoped_trace_completeness
from sentientos.scoped_mutation_canonicality import evaluate_scoped_slice_non_canonical_paths


def _seed_manifest_inputs(tmp_path: Path) -> None:
    (tmp_path / "NEWLEGACY.txt").write_text("ok", encoding="utf-8")
    (tmp_path / "vow/config.yaml").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "vow/config.yaml").write_text("ok", encoding="utf-8")
    (tmp_path / "vow/invariants.yaml").write_text("ok", encoding="utf-8")
    (tmp_path / "vow/init.py").write_text("ok", encoding="utf-8")
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "scripts/audit_immutability_verifier.py").write_text("ok", encoding="utf-8")
    (tmp_path / "scripts/verify_audits.py").write_text("ok", encoding="utf-8")


def test_manifest_direct_write_path_is_non_canonical(tmp_path: Path) -> None:
    _seed_manifest_inputs(tmp_path)
    with pytest.raises(ValueError, match="non_canonical_mutation_path:sentientos.manifest.generate"):
        generate_immutable_manifest.generate_manifest(
            output=tmp_path / "vow/immutable_manifest.json",
            allow_missing_files=False,
            files=generate_immutable_manifest.DEFAULT_FILES,
            admission_context=None,
        )


def test_public_manifest_action_routes_through_typed_action_and_router(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    _seed_manifest_inputs(tmp_path)

    payload = generate_immutable_manifest.execute_manifest_generation_action(
        output=tmp_path / "vow/immutable_manifest.json",
        allow_missing_files=False,
        execution_source="sentientos.tests.test_scoped_mutation_canonical_dominance",
        execution_owner="pytest",
    )

    admission = payload["admission"]
    assert admission["typed_action_id"] == "sentientos.manifest.generate"
    assert admission["canonical_router"] == "constitutional_mutation_router.v1"
    assert admission["canonical_handler"] == "scripts.generate_immutable_manifest.generate_manifest"
    assert admission["path_status"] == "canonical_router"


def test_merge_train_internal_transition_rejects_non_canonical_direct_call(tmp_path: Path) -> None:
    train = ForgeMergeTrain(repo_root=tmp_path)
    entry = TrainEntry(
        run_id="run-1",
        pr_url="https://github.com/o/r/pull/11",
        pr_number=11,
        head_sha="abc",
        branch="forge/1",
        goal_id="forge_smoke_noop",
        campaign_id=None,
        status="ready",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        check_overall="success",
    )
    state = TrainState(entries=[entry], last_merged_pr=None, last_failure_at=None)
    with pytest.raises(RuntimeError, match="non_canonical_mutation_path:sentientos.merge_train.hold"):
        train._apply_hold_transition(state=state, entry=entry, pr_number=11)


def test_scoped_slice_detector_reports_no_bypass_violations() -> None:
    report = evaluate_scoped_slice_non_canonical_paths(Path.cwd())
    assert report["status"] == "ok", json.dumps(report, indent=2, sort_keys=True)


def test_manifest_trace_is_coherent_end_to_end(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    _seed_manifest_inputs(tmp_path)
    payload = generate_immutable_manifest.execute_manifest_generation_action(
        output=tmp_path / "vow/immutable_manifest.json",
        allow_missing_files=False,
        execution_source="sentientos.tests.test_scoped_mutation_canonical_dominance",
        execution_owner="pytest",
    )
    correlation_id = str(payload["admission"]["correlation_id"])

    trace = evaluate_scoped_trace_completeness(tmp_path)
    manifest_row = next(row for row in trace["actions"] if row["typed_action_identity"] == "sentientos.manifest.generate")
    assert manifest_row["status"] == "trace_complete", json.dumps(manifest_row, indent=2, sort_keys=True)
    assert manifest_row["correlation_id"] == correlation_id
    assert manifest_row["router_event"]["canonical_router"] == "constitutional_mutation_router.v1"
    assert manifest_row["router_event"]["path_status"] == "canonical_router"
    assert manifest_row["admission_decision_ref"] == f"kernel_decision:{correlation_id}"


def test_trace_check_detects_missing_merge_train_linkage(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    _seed_manifest_inputs(tmp_path)
    train = ForgeMergeTrain(repo_root=tmp_path)
    entry = TrainEntry(
        run_id="run-2",
        pr_url="https://github.com/o/r/pull/12",
        pr_number=12,
        head_sha="def",
        branch="forge/2",
        goal_id="forge_smoke_noop",
        campaign_id=None,
        status="ready",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        check_overall="success",
    )
    train.save_state(TrainState(entries=[entry], last_merged_pr=None, last_failure_at=None))
    assert train.hold(12) is True
    # Remove linkage field to emulate fragmented historical artifacts.
    train_events_path = tmp_path / "pulse/forge_train_events.jsonl"
    rows = [json.loads(line) for line in train_events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for row in rows:
        if row.get("event") == "train_held":
            row.pop("admission_decision_ref", None)
            break
    train_events_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")

    trace = evaluate_scoped_trace_completeness(tmp_path)
    hold_row = next(row for row in trace["actions"] if row["typed_action_identity"] == "sentientos.merge_train.hold")
    assert hold_row["status"] == "missing_canonical_linkage", json.dumps(hold_row, indent=2, sort_keys=True)
    assert any(item.get("kind") == "missing_admission_ref" for item in hold_row["linkage_findings"])


def test_non_canonical_merge_train_path_does_not_fabricate_canonical_trace(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    train = ForgeMergeTrain(repo_root=tmp_path)
    entry = TrainEntry(
        run_id="run-3",
        pr_url="https://github.com/o/r/pull/13",
        pr_number=13,
        head_sha="ghi",
        branch="forge/3",
        goal_id="forge_smoke_noop",
        campaign_id=None,
        status="ready",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        check_overall="success",
    )
    state = TrainState(entries=[entry], last_merged_pr=None, last_failure_at=None)
    with pytest.raises(RuntimeError, match="non_canonical_mutation_path:sentientos.merge_train.hold"):
        train._apply_hold_transition(state=state, entry=entry, pr_number=13)
    train_events_path = tmp_path / "pulse/forge_train_events.jsonl"
    if train_events_path.exists():
        assert "kernel_decision:" not in train_events_path.read_text(encoding="utf-8")
