import json

import pytest

from sentientos import maintenance_loop_watchdog as watchdog
from tests.test_maintenance_watchdog_scan import config

pytestmark = pytest.mark.no_legacy_skip


def test_scan_uses_canonical_journals_and_artifacts_not_summary_files(tmp_path):
    cfg = config(tmp_path)
    for name in ("active_tasks", "interrupted_operations", "validation_ready",
                 "commit_ready", "publication_queue"):
        (tmp_path / "state" / f"{name}.json").write_text('[{"actionable":true}]')
    scanned = watchdog.scan(cfg, evaluation_time="2026-08-06T00:00:00Z")
    assert scanned["observations"]["active_tasks"] == []
    assert watchdog.decide(cfg, scanned)["transition"] == "idle"


def test_artifact_journal_disagreement_blocks(tmp_path):
    cfg = config(tmp_path)
    tasks = tmp_path / "state" / "maintenance_tasks"
    tasks.mkdir()
    tasks.joinpath("task.jsonl").write_text(json.dumps({"not": "a canonical event"}) + "\n")
    scanned = watchdog.scan(cfg, evaluation_time="2026-08-06T00:00:00Z")
    assert scanned["observations"]["integrity_failures"]
    assert watchdog.decide(cfg, scanned)["transition"] == "integrity_failure"
