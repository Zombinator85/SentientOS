from __future__ import annotations

import multiprocessing as mp
from pathlib import Path

import pytest

from sentientos import maintenance_task_journal as mtj

pytestmark = pytest.mark.no_legacy_skip

ROOT = Path(__file__).resolve().parents[1]
BASE = "5c601d398281009d4a46ce55d6ea499a9beb2711"


def _task() -> str:
    return mtj.derive_task_id(candidate_ref="candidate", base_sha=BASE, objective="objective", admitted_scope_digest="sha256:scope")


def _worker(root: str, idx: int, out: mp.Queue) -> None:  # type: ignore[type-arg]
    t = _task()
    res = mtj.append_event(Path(root), "attempt_heartbeat", task_id=t, payload={"idx": idx}, recorded_at=f"2026-08-04T00:00:{idx:02d}+00:00", repo_root=ROOT)
    out.put(res.status)


def _attempt_worker(root: str, idx: int, out: mp.Queue) -> None:  # type: ignore[type-arg]
    t = _task()
    res = mtj.append_event(Path(root), "attempt_started", task_id=t, payload={"attempt_id": f"a{idx}", "scope_digest": "sha256:scope"}, recorded_at=f"2026-08-04T00:00:{idx:02d}+00:00", repo_root=ROOT)
    out.put((res.status, res.reason_code))


def _seed(root: Path) -> str:
    t = _task()
    assert mtj.append_event(root, "task_created", task_id=t, payload={"candidate_ref": "candidate", "base_sha": BASE, "admitted_scope_digest": "sha256:scope"}, recorded_at="2026-08-04T00:00:00+00:00", repo_root=ROOT).status == "event_appended"
    assert mtj.append_event(root, "authority_lease_bound", task_id=t, payload={"lease_id": "l1", "scope_digest": "sha256:scope"}, recorded_at="2026-08-04T00:00:01+00:00", repo_root=ROOT).status == "event_appended"
    assert mtj.append_event(root, "attempt_started", task_id=t, payload={"attempt_id": "a0", "scope_digest": "sha256:scope"}, recorded_at="2026-08-04T00:00:02+00:00", repo_root=ROOT).status == "event_appended"
    return t


def test_process_concurrent_appends_preserve_chain_and_sequence(tmp_path: Path) -> None:
    root = tmp_path / "state"; root.mkdir(); t = _seed(root)
    q: mp.Queue = mp.Queue()
    procs = [mp.Process(target=_worker, args=(str(root), i, q)) for i in range(1, 7)]
    for p in procs: p.start()
    for p in procs: p.join(10)
    statuses = [q.get(timeout=1) for _ in procs]
    assert statuses.count("event_appended") == 6
    replay = mtj.replay_journal(mtj.journal_path_for(root, t, repo_root=ROOT))
    assert replay.integrity_status == "journal_ready"
    assert [e.sequence for e in replay.events] == list(range(1, 10))


def test_process_concurrent_attempt_start_has_one_winner(tmp_path: Path) -> None:
    root = tmp_path / "state"; root.mkdir(); t = _task()
    mtj.append_event(root, "task_created", task_id=t, payload={"candidate_ref": "candidate", "base_sha": BASE, "admitted_scope_digest": "sha256:scope"}, recorded_at="2026-08-04T00:00:00+00:00", repo_root=ROOT)
    mtj.append_event(root, "authority_lease_bound", task_id=t, payload={"lease_id": "l1", "scope_digest": "sha256:scope"}, recorded_at="2026-08-04T00:00:01+00:00", repo_root=ROOT)
    q: mp.Queue = mp.Queue()
    procs = [mp.Process(target=_attempt_worker, args=(str(root), i, q)) for i in range(1, 3)]
    for p in procs: p.start()
    for p in procs: p.join(10)
    results = [q.get(timeout=1) for _ in procs]
    assert sum(1 for status, _ in results if status == "event_appended") == 1
    assert sum(1 for status, reason in results if status == "transition_rejected" and reason == "attempt_already_active") == 1
    snapshot = mtj.materialize_snapshot(root, t, repo_root=ROOT)
    assert snapshot["active_attempt"] is not None
    assert len(snapshot["completed_attempts"]) == 0
    assert mtj.replay_journal(mtj.journal_path_for(root, t, repo_root=ROOT)).integrity_status == "journal_ready"
