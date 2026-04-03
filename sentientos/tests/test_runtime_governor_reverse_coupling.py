from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentientos.audit_trust_runtime import AuditTrustState
from sentientos.runtime_governor import get_runtime_governor, reset_runtime_governor


@pytest.fixture(autouse=True)
def _governor_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo"
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(repo_root))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_ENFORCEMENT_PROFILE", "federation-enforce")
    repo_root.mkdir(parents=True, exist_ok=True)
    reset_runtime_governor()
    return repo_root


@pytest.fixture(autouse=True)
def _stable_audit_trust(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sentientos.runtime_governor.evaluate_audit_trust",
        lambda repo_root, context: AuditTrustState(
            schema_version=1,
            evaluated_at="2026-01-01T00:00:00Z",
            context=context,
            status="ok",
            history_state="healthy_continuation",
            degraded_audit_trust=False,
            checkpoint_id="ckpt-1",
            continuation_descends_from_anchor=True,
            trust_boundary_explicit=True,
            trusted_history_head_hash="abc123",
            report_break_count=0,
        ),
    )
    monkeypatch.setattr(
        "sentientos.runtime_governor.write_audit_trust_artifacts",
        lambda repo_root, trust_state, actor: {
            "snapshot": "glow/runtime/audit_trust_state.json",
            "transitions": "glow/runtime/audit_trust_transitions.jsonl",
            "decisions": "glow/runtime/audit_trust_decisions.jsonl",
        },
    )


def _write_merge_train_state(repo_root: Path, *, status: str, last_error: str | None) -> None:
    _write_merge_train_entries(
        repo_root,
        entries=[
            {
                "run_id": "run-1",
                "pr_url": "https://github.com/o/r/pull/11",
                "pr_number": 11,
                "head_sha": "abc",
                "branch": "forge/1",
                "goal_id": "forge_smoke_noop",
                "campaign_id": None,
                "status": status,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
                "check_overall": "success",
                "last_error": last_error,
            }
        ],
    )


def _write_merge_train_entries(repo_root: Path, *, entries: list[dict[str, object]]) -> None:
    path = repo_root / "glow/forge/merge_train.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"entries": entries}
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")


def test_merge_train_integrity_failure_degrades_runtime_admission(_governor_env: Path) -> None:
    _write_merge_train_state(_governor_env, status="held", last_error="remote_doctrine_failed")
    governor = get_runtime_governor()

    decision = governor.admit_action("control_plane_task", "operator", "corr-1", metadata={"scope": "local"})

    assert decision.allowed is False
    observability_rows = (_governor_env.parent / "governor/observability.jsonl").read_text(encoding="utf-8").splitlines()
    latest = json.loads(observability_rows[-1])
    reason_chain = latest.get("runtime_posture", {}).get("reason_chain", [])
    runtime_feedback_reasons = {
        str(item.get("reason"))
        for item in reason_chain
        if isinstance(item, dict) and item.get("dimension") == "runtime_feedback"
    }
    assert "runtime_feedback_degraded_maintenance" in runtime_feedback_reasons


def test_merge_train_nominal_does_not_degrade_runtime_admission(_governor_env: Path) -> None:
    _write_merge_train_state(_governor_env, status="ready", last_error=None)
    governor = get_runtime_governor()

    decision = governor.admit_action("control_plane_task", "operator", "corr-2", metadata={"scope": "local"})

    assert decision.allowed is True


def test_runtime_and_evolution_disagreement_is_legible(_governor_env: Path) -> None:
    _write_merge_train_state(_governor_env, status="held", last_error="remote_doctrine_failed")
    governor = get_runtime_governor()

    decision = governor.admit_action(
        "control_plane_task",
        "operator",
        "corr-3",
        metadata={"scope": "local", "runtime_feedback": {"degraded": False, "source": "runtime_probe"}},
    )

    assert decision.allowed is False
    observability_rows = (_governor_env.parent / "governor/observability.jsonl").read_text(encoding="utf-8").splitlines()
    latest = json.loads(observability_rows[-1])
    reason_chain = latest.get("runtime_posture", {}).get("reason_chain", [])
    runtime_feedback_rows = [
        item
        for item in reason_chain
        if isinstance(item, dict) and item.get("dimension") == "runtime_feedback"
    ]
    assert runtime_feedback_rows
    details = runtime_feedback_rows[0].get("details", {})
    assert details.get("surface_disagreement") is True
    assert details.get("runtime_local_degraded") is False
    assert details.get("evolution_signal_degraded") is True
    reconciliation = details.get("reconciliation")
    assert isinstance(reconciliation, dict)
    assert reconciliation.get("state") == "none"
    assert reconciliation.get("rule") == "latest_entry_authoritative"


def test_stale_merge_train_failure_no_longer_poisons_runtime_admission(_governor_env: Path) -> None:
    _write_merge_train_entries(
        _governor_env,
        entries=[
            {
                "run_id": "run-1",
                "pr_url": "https://github.com/o/r/pull/11",
                "pr_number": 11,
                "head_sha": "abc",
                "branch": "forge/1",
                "goal_id": "forge_smoke_noop",
                "campaign_id": None,
                "status": "held",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
                "check_overall": "failure",
                "last_error": "remote_doctrine_failed",
            },
            {
                "run_id": "run-2",
                "pr_url": "https://github.com/o/r/pull/12",
                "pr_number": 12,
                "head_sha": "def",
                "branch": "forge/2",
                "goal_id": "forge_smoke_noop",
                "campaign_id": None,
                "status": "ready",
                "created_at": "2026-01-01T00:10:00Z",
                "updated_at": "2026-01-01T00:10:00Z",
                "check_overall": "success",
                "last_error": None,
            },
        ],
    )
    governor = get_runtime_governor()

    decision = governor.admit_action("control_plane_task", "operator", "corr-4", metadata={"scope": "local"})

    assert decision.allowed is True
    observability_rows = (_governor_env.parent / "governor/observability.jsonl").read_text(encoding="utf-8").splitlines()
    latest = json.loads(observability_rows[-1])
    reason_chain = latest.get("runtime_posture", {}).get("reason_chain", [])
    runtime_feedback_rows = [
        item
        for item in reason_chain
        if isinstance(item, dict) and item.get("dimension") == "runtime_feedback"
    ]
    assert runtime_feedback_rows
    details = runtime_feedback_rows[0].get("details", {})
    reconciliation = details.get("reconciliation")
    assert isinstance(reconciliation, dict)
    assert reconciliation.get("state") == "reconciled"
    assert reconciliation.get("disagreement_kind") == "stale_evolution_failure_cleared"
