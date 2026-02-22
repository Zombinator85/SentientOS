from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from sentientos.artifact_catalog import resolve_entry_path
from sentientos.artifact_retention import RetentionPolicy, run_retention


def test_archive_moves_append_redirects_and_catalog_resolution(tmp_path: Path) -> None:
    tick_dir = tmp_path / "glow/forge/orchestrator/ticks"
    tick_dir.mkdir(parents=True, exist_ok=True)
    old_tick = tick_dir / "tick_old.json"
    old_tick.write_text('{"generated_at":"2020-01-01T00:00:00Z","status":"ok"}\n', encoding="utf-8")
    os.utime(old_tick, (1577836800, 1577836800))

    policy = RetentionPolicy(
        enabled=True,
        keep_days_ticks=1,
        keep_days_sweeps=1,
        keep_days_runs=1,
        keep_days_catalog=180,
        archive_dir=Path("glow/forge/archive"),
        rollup_interval_days=7,
    )

    run_retention(tmp_path, policy=policy, now=datetime(2026, 1, 10, tzinfo=timezone.utc))

    redirects = (tmp_path / "glow/forge/archive/redirects.jsonl").read_text(encoding="utf-8").splitlines()
    assert redirects
    mapped = json.loads(redirects[-1])
    assert mapped["old_path"] == "glow/forge/orchestrator/ticks/tick_old.json"
    assert mapped["new_path"].startswith("glow/forge/archive/tick/")
    assert not old_tick.exists()
    assert (tmp_path / mapped["new_path"]).exists()

    entry = {"path": mapped["old_path"]}
    resolved = resolve_entry_path(tmp_path, entry)
    assert resolved == mapped["new_path"]


def test_no_delete_recent_files(tmp_path: Path) -> None:
    tick_dir = tmp_path / "glow/forge/orchestrator/ticks"
    tick_dir.mkdir(parents=True, exist_ok=True)
    fresh = tick_dir / "tick_new.json"
    fresh.write_text('{"generated_at":"2026-01-09T00:00:00Z","status":"ok"}\n', encoding="utf-8")

    policy = RetentionPolicy(
        enabled=True,
        keep_days_ticks=30,
        keep_days_sweeps=30,
        keep_days_runs=30,
        keep_days_catalog=180,
        archive_dir=Path("glow/forge/archive"),
        rollup_interval_days=7,
    )
    result = run_retention(tmp_path, policy=policy, now=datetime(2026, 1, 10, tzinfo=timezone.utc))
    assert result.archived_items == 0
    assert fresh.exists()
