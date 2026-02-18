from __future__ import annotations

import json
from pathlib import Path

from sentientos.forge_merge_train import ForgeMergeTrain, TrainEntry, TrainState
from sentientos.forge_queue import ForgeQueue, ForgeRequest
from sentientos.github_merge import MergeResult, RebaseResult


class _Ops:
    def __init__(self) -> None:
        self.behind = False
        self.rebase = RebaseResult(ok=True, conflict=False, message="ok", new_head_sha="newsha", suspect_files=[])
        self.checks = "success"
        self.wait = ("success", False)
        self.merge = MergeResult(ok=True, conflict=False, message="ok")

    def checks_for(self, entry: TrainEntry) -> tuple[str, str | None, str | None]:
        _ = entry
        return (self.checks, None, None)

    def wait_for_checks(self, entry: TrainEntry, timeout_seconds: int = 1800) -> tuple[str, bool]:
        _ = entry, timeout_seconds
        return self.wait

    def is_branch_behind_base(self, entry: TrainEntry, base_branch: str) -> bool:
        _ = entry, base_branch
        return self.behind

    def rebase_branch(self, entry: TrainEntry, base_branch: str) -> RebaseResult:
        _ = entry, base_branch
        return self.rebase

    def merge_pull_request(self, entry: TrainEntry, strategy: str) -> MergeResult:
        _ = entry, strategy
        return self.merge


def _entry(status: str = "ready") -> TrainEntry:
    return TrainEntry(
        run_id="run-1",
        pr_url="https://github.com/o/r/pull/11",
        pr_number=11,
        head_sha="abc",
        branch="forge/1",
        goal_id="forge_smoke_noop",
        campaign_id=None,
        status=status,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        check_overall="success",
    )


def test_state_persistence_roundtrip(tmp_path: Path) -> None:
    train = ForgeMergeTrain(repo_root=tmp_path)
    state = TrainState(entries=[_entry()], last_merged_pr=None, last_failure_at=None)
    train.save_state(state)

    loaded = train.load_state()

    assert len(loaded.entries) == 1
    assert loaded.entries[0].pr_number == 11


def test_tick_selects_ready_fifo(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_TRAIN_ENABLED", "1")
    ops = _Ops()
    train = ForgeMergeTrain(repo_root=tmp_path, github_ops=ops)
    train.save_state(TrainState(entries=[_entry("held"), _entry("ready")]))

    result = train.tick()

    assert result["status"] in {"mergeable", "merged"}


def test_rebase_conflict_marks_held_and_writes_docket(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_TRAIN_ENABLED", "1")
    ops = _Ops()
    ops.behind = True
    ops.rebase = RebaseResult(ok=False, conflict=True, message="conflict", new_head_sha=None, suspect_files=["a.py"])
    train = ForgeMergeTrain(repo_root=tmp_path, github_ops=ops)
    train.save_state(TrainState(entries=[_entry("ready")]))

    result = train.tick()

    assert result["status"] == "held"
    dockets = list((tmp_path / "glow/forge").glob("merge_train_docket_*.json"))
    assert dockets
    payload = json.loads(dockets[0].read_text(encoding="utf-8"))
    assert payload["suspected_conflict_files"] == ["a.py"]


def test_checks_fail_retry_then_failed(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_TRAIN_ENABLED", "1")
    ops = _Ops()
    ops.checks = "failure"
    train = ForgeMergeTrain(repo_root=tmp_path, github_ops=ops)
    policy = train.load_policy()
    policy.cooldown_minutes_on_failure = 0
    train.save_policy(policy)
    train.save_state(TrainState(entries=[_entry("ready")]))

    first = train.tick()
    second = train.tick()

    assert first["status"] in {"held", "failed"}
    assert second["status"] == "failed"


def test_ingest_from_receipts_and_max_active(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_TRAIN_ENABLED", "1")
    monkeypatch.setenv("SENTIENTOS_FORGE_MAX_RUNS_PER_DAY", "10")
    monkeypatch.setenv("SENTIENTOS_FORGE_MAX_RUNS_PER_HOUR", "10")
    queue = ForgeQueue(pulse_root=tmp_path / "pulse")
    queue.enqueue(ForgeRequest(request_id="", goal="forge_smoke_noop", goal_id="forge_smoke_noop"))
    queue.mark_finished(
        "forge-ignored",
        status="success",
        report_path=None,
        publish_status="ready_to_merge",
        publish_pr_url="https://github.com/o/r/pull/22",
        publish_checks_overall="success",
        provenance_run_id="run-x",
    )
    ops = _Ops()
    train = ForgeMergeTrain(repo_root=tmp_path, queue=queue, github_ops=ops)
    policy = train.load_policy()
    policy.enabled = True
    policy.max_active_prs = 0
    train.save_policy(policy)

    result = train.tick()

    assert result["status"] == "max_active_exceeded"
