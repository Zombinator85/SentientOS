from __future__ import annotations

import json
from pathlib import Path

from sentientos.signed_rollups import sign_rollups, verify_signed_rollups


def _write_rollup(path: Path, *, week: str, count: int) -> str:
    rel = f"glow/forge/rollups/orchestrator_ticks/rollup_{week}.json"
    target = path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"schema_version": 1, "stream": "orchestrator_ticks", "rollup_week": week, "row_count": count}, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return rel


def test_sign_and_verify_rollup_hmac(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_ROLLUP_SIGNING", "hmac-test")
    monkeypatch.setenv("SENTIENTOS_ROLLUP_PUBLIC_KEY_ID", "test-key")

    rel = _write_rollup(tmp_path, week="2026-01", count=2)
    signed = sign_rollups(tmp_path, [rel])
    assert len(signed) == 1

    ok, error = verify_signed_rollups(tmp_path, last_weeks=4)
    assert ok is True
    assert error is None


def test_rollup_tamper_fails_verification(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_ROLLUP_SIGNING", "hmac-test")
    rel = _write_rollup(tmp_path, week="2026-02", count=2)
    sign_rollups(tmp_path, [rel])

    (tmp_path / rel).write_text(json.dumps({"schema_version": 1, "row_count": 3}, sort_keys=True) + "\n", encoding="utf-8")

    ok, error = verify_signed_rollups(tmp_path, last_weeks=4)
    assert ok is False
    assert error is not None and "rollup_sha_mismatch" in error


def test_prev_linkage_across_weeks(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_ROLLUP_SIGNING", "hmac-test")
    first = _write_rollup(tmp_path, week="2026-03", count=1)
    second = _write_rollup(tmp_path, week="2026-04", count=2)
    sign_rollups(tmp_path, [first, second])

    ok, error = verify_signed_rollups(tmp_path, last_weeks=8)
    assert ok is True
    assert error is None
