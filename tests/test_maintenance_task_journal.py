from __future__ import annotations

import importlib
import json
import shutil
import socket
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos import maintenance_task_journal as mtj

ROOT = Path(__file__).resolve().parents[1]
BASE = "5c601d398281009d4a46ce55d6ea499a9beb2711"


def ext(tmp_path: Path) -> Path:
    p = tmp_path / "state"
    p.mkdir()
    return p


def task() -> str:
    return mtj.derive_task_id(candidate_ref="opaque:candidate", base_sha=BASE, objective="do task", admitted_scope_digest="sha256:scope")


def append(root: Path, typ: str, payload: dict, *, task_id: str | None = None, event_id: str | None = None, recorded_at: str = "2026-08-04T00:00:00+00:00") -> mtj.AppendResult:
    return mtj.append_event(root, typ, task_id=task_id or task(), payload=payload, event_id=event_id, recorded_at=recorded_at, repository_sha=BASE, repo_root=ROOT)


def create(root: Path) -> str:
    tid = task()
    r = append(root, "task_created", {"candidate_ref": "opaque:candidate", "base_sha": BASE, "admitted_scope_digest": "sha256:scope"}, task_id=tid)
    assert r.status == "event_appended"
    return tid


def read_lines(root: Path, tid: str) -> list[dict]:
    return [json.loads(line) for line in mtj.journal_path_for(root, tid, repo_root=ROOT).read_text().splitlines()]


def test_event_chain_detects_mutation_reordering_and_deletion(tmp_path: Path) -> None:
    root = ext(tmp_path); tid = create(root)
    append(root, "authority_lease_bound", {"lease_id": "l1", "scope_digest": "sha256:scope"}, task_id=tid)
    append(root, "attempt_started", {"attempt_id": "a1", "scope_digest": "sha256:scope"}, task_id=tid)
    path = mtj.journal_path_for(root, tid, repo_root=ROOT)
    original = read_lines(root, tid)
    mutated = [dict(row) for row in original]
    mutated[0]["payload"]["candidate_ref"] = "changed"
    path.write_text("\n".join(json.dumps(r, sort_keys=True, separators=(",", ":")) for r in mutated) + "\n")
    assert mtj.replay_journal(path).integrity_status == "journal_digest_mismatch"
    path.write_text("\n".join(json.dumps(r, sort_keys=True, separators=(",", ":")) for r in [original[1], original[0], original[2]]) + "\n")
    assert mtj.replay_journal(path).integrity_status == "journal_sequence_invalid"
    path.write_text("\n".join(json.dumps(r, sort_keys=True, separators=(",", ":")) for r in [original[0], original[2]]) + "\n")
    assert mtj.replay_journal(path).integrity_status in {"journal_sequence_invalid", "journal_chain_broken", "journal_digest_mismatch"}


def test_exact_duplicate_append_is_idempotent(tmp_path: Path) -> None:
    root = ext(tmp_path); tid = task()
    payload = {"candidate_ref": "opaque:candidate", "base_sha": BASE, "admitted_scope_digest": "sha256:scope"}
    first = append(root, "task_created", payload, task_id=tid, event_id="event-1")
    assert first.status == "event_appended"
    duplicate = append(root, "task_created", payload, task_id=tid, event_id="event-1")
    assert duplicate.status == "event_already_recorded"
    assert len(read_lines(root, tid)) == 1


def test_conflicting_duplicate_event_is_rejected(tmp_path: Path) -> None:
    root = ext(tmp_path); tid = task()
    assert append(root, "task_created", {"candidate_ref": "opaque:candidate", "base_sha": BASE}, task_id=tid, event_id="same").status == "event_appended"
    conflict = append(root, "task_created", {"candidate_ref": "different", "base_sha": BASE}, task_id=tid, event_id="same")
    assert conflict.status == "event_conflict"
    assert conflict.reason_code == "duplicate_event_conflict"


def test_partial_final_record_preserves_prior_valid_history(tmp_path: Path) -> None:
    root = ext(tmp_path); tid = create(root)
    path = mtj.journal_path_for(root, tid, repo_root=ROOT)
    path.write_bytes(path.read_bytes() + b'{"partial"')
    replay = mtj.replay_journal(path)
    assert replay.integrity_status == "journal_tail_incomplete"
    assert replay.last_valid_sequence == 1
    assert len(replay.events) == 1


def test_midstream_corruption_fails_closed(tmp_path: Path) -> None:
    root = ext(tmp_path); tid = create(root)
    append(root, "authority_lease_bound", {"lease_id": "l1", "scope_digest": "sha256:scope"}, task_id=tid)
    append(root, "authority_lease_revoked", {"lease_id": "l1"}, task_id=tid)
    path = mtj.journal_path_for(root, tid, repo_root=ROOT)
    lines = path.read_text().splitlines()
    lines[1] = "not json"
    path.write_text("\n".join(lines) + "\n")
    replay = mtj.replay_journal(path)
    assert replay.integrity_status == "journal_record_invalid"
    assert replay.last_valid_sequence == 1


def test_state_root_inside_repository_is_rejected() -> None:
    with pytest.raises(ValueError, match="state_root_inside_repository_rejected"):
        mtj.resolve_state_root(ROOT, repo_root=ROOT)


def test_import_creates_no_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    before = set(tmp_path.iterdir())
    importlib.reload(mtj)
    after = set(tmp_path.iterdir())
    assert after == before


def test_no_effect_sentinels_for_journal_operations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = ext(tmp_path); tid = task()
    def forbidden(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("forbidden effect")
    monkeypatch.setattr(socket.socket, "connect", forbidden, raising=True)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    assert create(root) == tid
    assert append(root, "authority_lease_bound", {"lease_id": "l1", "scope_digest": "sha256:scope"}, task_id=tid).status == "event_appended"
    snap = mtj.materialize_snapshot(root, tid, root / "snapshot.json", repo_root=ROOT)
    assert snap["journal_integrity_status"] == "journal_ready"
    assert not (ROOT / "maintenance_tasks").exists()
