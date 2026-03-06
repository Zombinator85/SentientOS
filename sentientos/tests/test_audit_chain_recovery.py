from __future__ import annotations

import json
from pathlib import Path

from sentientos.audit_chain_gate import verify_audit_chain
from sentientos.audit_recovery import break_fingerprint, checkpoint_id_from_payload, load_checkpoints
from scripts import audit_chain_reanchor


def _entry(ts: str, data: dict[str, object], prev_hash: str) -> dict[str, object]:
    import hashlib

    h = hashlib.sha256()
    h.update(ts.encode("utf-8"))
    h.update(json.dumps(data, sort_keys=True).encode("utf-8"))
    h.update(prev_hash.encode("utf-8"))
    digest = h.hexdigest()
    return {"timestamp": ts, "data": data, "prev_hash": prev_hash, "rolling_hash": digest}


def test_break_state_detected_without_checkpoint(tmp_path: Path) -> None:
    (tmp_path / "logs").mkdir(parents=True, exist_ok=True)
    bad = {"timestamp": "2026-01-01T00:00:00Z", "data": {"a": 1}, "prev_hash": "bad", "rolling_hash": "bad"}
    (tmp_path / "logs/audit.jsonl").write_text(json.dumps(bad) + "\n", encoding="utf-8")

    result = verify_audit_chain(tmp_path)
    assert result.status == "broken"
    assert result.recovery_state is not None
    assert result.recovery_state["history_state"] == "broken_preserved"
    assert result.recovery_state["degraded_audit_trust"] is True


def test_reanchor_checkpoint_creation_and_trusted_continuation(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "logs").mkdir(parents=True, exist_ok=True)
    e1 = _entry("2026-01-01T00:00:00Z", {"a": 1}, "0" * 64)
    bad = {"timestamp": "2026-01-01T00:00:01Z", "data": {"a": 2}, "prev_hash": "bad", "rolling_hash": "bad"}
    (tmp_path / "logs/audit.jsonl").write_text(json.dumps(e1) + "\n" + json.dumps(bad) + "\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    rc = audit_chain_reanchor.main(["--reason", "incident-001", "--continuation-log", "pulse/audit/privileged_audit.runtime.jsonl"])
    assert rc == 0

    checkpoints = load_checkpoints(tmp_path)
    assert checkpoints
    checkpoint = checkpoints[-1]

    runtime = tmp_path / "pulse/audit/privileged_audit.runtime.jsonl"
    runtime.parent.mkdir(parents=True, exist_ok=True)
    c1 = _entry("2026-01-01T00:01:00Z", {"tool": "runtime"}, checkpoint.continuation_anchor_prev_hash)
    runtime.write_text(json.dumps(c1) + "\n", encoding="utf-8")

    result = verify_audit_chain(tmp_path)
    assert result.status == "reanchored"
    assert result.ok is True
    assert result.recovery_state is not None
    assert result.recovery_state["history_state"] == "reanchored_continuation"
    assert result.recovery_state["continuation_descends_from_anchor"] is True


def test_reanchor_preserves_broken_history_segment(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "logs").mkdir(parents=True, exist_ok=True)
    broken_text = '{"timestamp":"2026-01-01T00:00:00Z","data":{"a":1},"prev_hash":"bad","rolling_hash":"bad"}\n'
    path = tmp_path / "logs/audit.jsonl"
    path.write_text(broken_text, encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    rc = audit_chain_reanchor.main(["--reason", "preserve-test"])
    assert rc == 0
    assert path.read_text(encoding="utf-8") == broken_text


def test_recovery_identifiers_are_deterministic() -> None:
    fp1 = break_fingerprint(path="logs/audit.jsonl", line_number=4, expected_prev_hash="a", found_prev_hash="b")
    fp2 = break_fingerprint(path="logs/audit.jsonl", line_number=4, expected_prev_hash="a", found_prev_hash="b")
    assert fp1 == fp2

    payload = {
        "created_at": "2026-01-01T00:00:00Z",
        "break_fingerprint": fp1,
        "trusted_history_head_hash": "h1",
        "continuation_anchor_prev_hash": "h1",
        "continuation_log_path": "pulse/audit/privileged_audit.runtime.jsonl",
        "reason": "test",
        "break_path": "logs/audit.jsonl",
        "break_line": 4,
        "expected_prev_hash": "a",
        "found_prev_hash": "b",
    }
    assert checkpoint_id_from_payload(payload) == checkpoint_id_from_payload(payload)
