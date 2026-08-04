from __future__ import annotations

from pathlib import Path

import pytest

from sentientos import maintenance_task_journal as mtj

pytestmark = pytest.mark.no_legacy_skip

ROOT = Path(__file__).resolve().parents[1]
BASE = "5c601d398281009d4a46ce55d6ea499a9beb2711"


def ext(tmp_path: Path) -> Path:
    p = tmp_path / "state"; p.mkdir(); return p


def tid() -> str:
    return mtj.derive_task_id(candidate_ref="candidate", base_sha=BASE, objective="objective", admitted_scope_digest="sha256:scope")


def app(root: Path, typ: str, payload: dict, *, task: str | None = None) -> mtj.AppendResult:
    return mtj.append_event(root, typ, task_id=task or tid(), payload=payload, recorded_at="2026-08-04T00:00:00+00:00", repository_sha=BASE, repo_root=ROOT)


def create(root: Path) -> str:
    t = tid(); assert app(root, "task_created", {"candidate_ref": "candidate", "base_sha": BASE, "admitted_scope_digest": "sha256:scope"}, task=t).status == "event_appended"; return t


def legal_attempt(root: Path, t: str) -> None:
    assert app(root, "authority_lease_bound", {"lease_id": "l1", "scope_digest": "sha256:scope", "expires_at": "2026-08-05T00:00:00+00:00"}, task=t).status == "event_appended"
    assert app(root, "attempt_started", {"attempt_id": "a1", "scope_digest": "sha256:scope"}, task=t).status == "event_appended"


def test_replay_produces_byte_identical_snapshot(tmp_path: Path) -> None:
    root = ext(tmp_path); t = create(root); legal_attempt(root, t)
    app(root, "attempt_heartbeat", {"heartbeat": 1}, task=t)
    app(root, "agent_session_bound", {"agent_session_ref_id": mtj.derive_agent_session_ref_id(t, "a1", "local-fake")}, task=t)
    app(root, "implementation_completed", {"result": "ok"}, task=t)
    app(root, "validation_passed", {"validation_ref_id": mtj.derive_validation_ref_id(t, "a1", "sha256:validation")}, task=t)
    app(root, "ready_to_commit_recorded", {"plan_digest": "sha256:plan"}, task=t)
    app(root, "commit_recorded", {"commit_ref_id": mtj.derive_commit_ref_id(t, "abc123"), "commit_sha": "abc123"}, task=t)
    app(root, "publication_started", {"publication_ref_id": mtj.derive_publication_ref_id(t, "origin/main")}, task=t)
    app(root, "publication_failed", {"reason": "synthetic"}, task=t)
    app(root, "recovery_started", {"mode": "inspect"}, task=t)
    app(root, "recovery_completed", {"mode": "inspect"}, task=t)
    app(root, "publication_succeeded", {"publication_ref_id": mtj.derive_publication_ref_id(t, "origin/main")}, task=t)
    app(root, "task_closed", {"reason": "done"}, task=t)
    a = mtj.canonical_json_bytes(mtj.materialize_snapshot(root, t, root / "a.json", repo_root=ROOT))
    b = mtj.canonical_json_bytes(mtj.materialize_snapshot(root, t, root / "b.json", repo_root=ROOT))
    assert a == b
    assert mtj.replay_journal(mtj.journal_path_for(root, t, repo_root=ROOT)).integrity_status == "journal_ready"


def test_illegal_transition_is_rejected_with_stable_reason(tmp_path: Path) -> None:
    root = ext(tmp_path); t = create(root)
    res = app(root, "attempt_started", {"attempt_id": "a1", "scope_digest": "sha256:scope"}, task=t)
    assert res.status == "transition_rejected"
    assert res.reason_code == "missing_authority_lease"


def test_only_one_active_lease_and_attempt_are_allowed(tmp_path: Path) -> None:
    root = ext(tmp_path); t = create(root)
    assert app(root, "authority_lease_bound", {"lease_id": "l1", "scope_digest": "sha256:scope"}, task=t).status == "event_appended"
    second = app(root, "authority_lease_bound", {"lease_id": "l2", "scope_digest": "sha256:scope"}, task=t)
    assert second.reason_code == "authority_lease_already_active"
    assert app(root, "attempt_started", {"attempt_id": "a1", "scope_digest": "sha256:scope"}, task=t).status == "event_appended"
    second_attempt = app(root, "attempt_started", {"attempt_id": "a2", "scope_digest": "sha256:scope"}, task=t)
    assert second_attempt.reason_code == "attempt_already_active"


def test_retry_uses_new_attempt_without_expanding_lease(tmp_path: Path) -> None:
    root = ext(tmp_path); t = create(root); legal_attempt(root, t)
    app(root, "implementation_failed", {"reason": "synthetic"}, task=t)
    reused = app(root, "attempt_started", {"attempt_id": "a1", "scope_digest": "sha256:scope"}, task=t)
    assert reused.reason_code == "attempt_id_reused"
    widened = app(root, "attempt_started", {"attempt_id": "a2", "scope_digest": "sha256:wider"}, task=t)
    assert widened.reason_code == "authority_lease_scope_expanded"
    ok = app(root, "attempt_started", {"attempt_id": "a2", "scope_digest": "sha256:scope"}, task=t)
    assert ok.status == "event_appended"


def test_closed_task_cannot_return_to_active_state(tmp_path: Path) -> None:
    root = ext(tmp_path); t = create(root)
    assert app(root, "task_closed", {"reason": "no-op"}, task=t).status == "event_appended"
    assert app(root, "authority_lease_bound", {"lease_id": "l1", "scope_digest": "sha256:scope"}, task=t).reason_code == "task_terminal"


def test_lease_expiry_uses_explicit_evaluation_time(tmp_path: Path) -> None:
    root = ext(tmp_path); t = create(root)
    app(root, "authority_lease_bound", {"lease_id": "l1", "scope_digest": "sha256:scope", "expires_at": "2026-08-04T12:00:00+00:00"}, task=t)
    events = mtj.replay_journal(mtj.journal_path_for(root, t, repo_root=ROOT)).events
    assert mtj.reduce_events(events, evaluation_time="2026-08-04T11:00:00+00:00")["lease_status"] == "active"
    assert mtj.reduce_events(events, evaluation_time="2026-08-04T13:00:00+00:00")["lease_status"] == "expired"
