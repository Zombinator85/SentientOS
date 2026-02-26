from __future__ import annotations

from sentientos.consistency_checks import compare_tick_vs_replay


def test_consistency_reason_precedence_is_deterministic() -> None:
    tick = {
        "policy_hash": "a",
        "integrity_status_hash": "tick-hash",
        "integrity_overall": "ok",
        "path": "glow/forge/integrity/status_a.json",
    }
    replay = {
        "policy_hash": "b",
        "integrity_status_hash": "replay-hash",
        "integrity_overall": "fail",
        "path": "glow/forge/replay/replay_a.json",
    }

    result = compare_tick_vs_replay(tick, replay)

    assert result.status == "fail"
    assert result.reason == "policy_hash_mismatch"
    assert result.evidence_paths == ["glow/forge/integrity/status_a.json", "glow/forge/replay/replay_a.json"]


def test_consistency_detects_replay_fail_tick_nonfail() -> None:
    tick = {"policy_hash": "a", "integrity_status_hash": "h", "integrity_overall": "warn"}
    replay = {"policy_hash": "a", "integrity_status_hash": "h", "integrity_overall": "fail"}

    result = compare_tick_vs_replay(tick, replay)

    assert result.status == "fail"
    assert result.reason == "replay_fail_tick_nonfail"
