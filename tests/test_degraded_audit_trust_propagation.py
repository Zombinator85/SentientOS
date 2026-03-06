from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from sentientos.audit_recovery import RecoveryCheckpoint, append_checkpoint, break_fingerprint
from sentientos.audit_trust_runtime import evaluate_audit_trust, write_audit_trust_artifacts
from sentientos.runtime_governor import get_runtime_governor, reset_runtime_governor


def _entry(ts: str, data: object, prev_hash: str) -> dict[str, object]:
    digest = hashlib.sha256()
    digest.update(ts.encode("utf-8"))
    digest.update(json.dumps(data, sort_keys=True).encode("utf-8"))
    digest.update(prev_hash.encode("utf-8"))
    rolling = digest.hexdigest()
    return {
        "timestamp": ts,
        "data": data,
        "prev_hash": prev_hash,
        "rolling_hash": rolling,
    }


def _write_audit_log(root: Path, *, broken: bool) -> tuple[Path, str]:
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    config_dir = root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs / "audit.jsonl"

    ts1 = datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat()
    first = _entry(ts1, {"event": "a"}, "0" * 64)
    ts2 = datetime(2026, 1, 2, tzinfo=timezone.utc).isoformat()
    prev = "f" * 64 if broken else str(first["rolling_hash"])
    second = _entry(ts2, {"event": "b"}, prev)

    log_path.write_text(json.dumps(first) + "\n" + json.dumps(second) + "\n", encoding="utf-8")
    (config_dir / "master_files.json").write_text(json.dumps({"logs/audit.jsonl": {}}), encoding="utf-8")
    return log_path, str(first["rolling_hash"])


def test_governor_degraded_trust_gates_high_impact_actions(monkeypatch, tmp_path: Path) -> None:
    _write_audit_log(tmp_path, broken=True)
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.1")
    reset_runtime_governor()
    governor = get_runtime_governor()

    restart = governor.admit_action("restart_daemon", "local", "c1", metadata={"daemon_name": "d"})
    federated = governor.admit_action("federated_control", "peer", "c2", metadata={"subject": "node"})
    amendment = governor.admit_action("amendment_apply", "runtime_shell", "c3", metadata={"subject": "a"})
    control = governor.admit_action("control_plane_task", "operator", "c4", metadata={"subject": "TASK_EXECUTION"})

    assert restart.allowed is True
    assert restart.reason == "degraded_audit_trust_tightened"
    assert federated.allowed is False
    assert federated.reason == "degraded_audit_trust_federation_blocked"
    assert amendment.allowed is False
    assert amendment.reason == "degraded_audit_trust_amendment_deferred"
    assert control.allowed is False
    assert control.reason == "degraded_audit_trust_control_plane_escalation_required"


def test_audit_trust_restores_only_after_explicit_reanchor(tmp_path: Path) -> None:
    _, trusted_head = _write_audit_log(tmp_path, broken=True)
    state_before = evaluate_audit_trust(tmp_path, context="test")
    assert state_before.degraded_audit_trust is True

    fp = break_fingerprint(
        path="logs/audit.jsonl",
        line_number=2,
        expected_prev_hash=trusted_head,
        found_prev_hash="f" * 64,
    )
    checkpoint = RecoveryCheckpoint(
        checkpoint_id="reanchor:test123",
        created_at="2026-01-03T00:00:00Z",
        break_fingerprint=fp,
        break_path="logs/audit.jsonl",
        break_line=2,
        expected_prev_hash=trusted_head,
        found_prev_hash="f" * 64,
        trusted_history_head_hash=trusted_head,
        continuation_anchor_prev_hash=trusted_head,
        continuation_log_path="logs/audit_continuation.jsonl",
        reason="unit test reanchor",
        status="active",
    )
    append_checkpoint(tmp_path, checkpoint)
    (tmp_path / "logs" / "audit_continuation.jsonl").write_text(
        json.dumps({"timestamp": "2026-01-03T00:00:01Z", "data": {"event": "continuation"}, "prev_hash": trusted_head}) + "\n",
        encoding="utf-8",
    )

    state_after = evaluate_audit_trust(tmp_path, context="test")
    assert state_after.degraded_audit_trust is False
    assert state_after.history_state == "reanchored_continuation"
    assert state_after.checkpoint_id == checkpoint.checkpoint_id


def test_audit_trust_artifacts_are_append_only_and_deterministic(tmp_path: Path) -> None:
    _write_audit_log(tmp_path, broken=False)
    state = evaluate_audit_trust(tmp_path, context="determinism")
    paths1 = write_audit_trust_artifacts(tmp_path, state, actor="test")
    paths2 = write_audit_trust_artifacts(tmp_path, state, actor="test")

    assert paths1 == paths2

    snapshot = json.loads((tmp_path / paths1["snapshot"]).read_text(encoding="utf-8"))
    assert isinstance(snapshot.get("state_signature"), str)

    transitions = (tmp_path / paths1["transitions"]).read_text(encoding="utf-8").strip().splitlines()
    assert len(transitions) == 2
    first = json.loads(transitions[0])
    second = json.loads(transitions[1])
    assert first["transition"] == "changed"
    assert second["transition"] == "unchanged"
    assert first["state_signature"] == second["state_signature"]
