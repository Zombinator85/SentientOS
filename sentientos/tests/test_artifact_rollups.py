from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sentientos.artifact_retention import RetentionPolicy, run_retention


def test_rollups_are_deterministic(tmp_path: Path) -> None:
    pulse = tmp_path / "pulse"
    pulse.mkdir(parents=True, exist_ok=True)
    stream = pulse / "orchestrator_ticks.jsonl"
    stream.write_text(
        "\n".join(
            [
                json.dumps({"generated_at": "2025-12-20T00:00:00Z", "status": "ok", "n": 1}, sort_keys=True),
                json.dumps({"generated_at": "2025-12-20T01:00:00Z", "status": "ok", "n": 2}, sort_keys=True),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    policy = RetentionPolicy(
        enabled=True,
        keep_days_ticks=10,
        keep_days_sweeps=10,
        keep_days_runs=10,
        keep_days_catalog=180,
        archive_dir=Path("glow/forge/archive"),
        rollup_interval_days=7,
    )

    now = datetime(2026, 1, 10, tzinfo=timezone.utc)
    first = run_retention(tmp_path, policy=policy, now=now)
    second = run_retention(tmp_path, policy=policy, now=now)

    assert first.rollup_files == second.rollup_files
    rollup = tmp_path / first.rollup_files[0]
    payload_one = json.loads(rollup.read_text(encoding="utf-8"))
    payload_two = json.loads(rollup.read_text(encoding="utf-8"))
    assert payload_one["content_sha256"] == payload_two["content_sha256"]
    assert payload_one["row_count"] == 2
