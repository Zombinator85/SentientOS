from __future__ import annotations

import json
from pathlib import Path

from sentientos.forge_daemon import ForgeDaemon
from sentientos.forge_pr_notes import build_pr_notes
from sentientos.forge_queue import ForgeQueue, ForgeRequest


class _FakeReport:
    def __init__(self, *, generated_at: str = "2025-01-01T00:00:00Z", outcome: str = "success") -> None:
        self.generated_at = generated_at
        self.notes: list[str] = []
        self.outcome = outcome
        self.docket_path: str | None = None
        self.git_sha = "abc123"
        self.failure_reasons: list[str] = []
        self.goal_id = "adhoc"


class _FakeForge:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.runs: list[str] = []

    def run(self, goal: str) -> _FakeReport:
        self.runs.append(goal)
        return _FakeReport()

    def _report_path(self, generated_at: str) -> Path:
        path = self.repo_root / "glow" / "forge" / f"report_{generated_at.replace(':', '-')}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"generated_at": generated_at}), encoding="utf-8")
        return path


def test_queue_read_tolerates_corrupt_lines(tmp_path: Path) -> None:
    queue = ForgeQueue(pulse_root=tmp_path / "pulse")
    queue.enqueue(ForgeRequest(request_id="req-1", goal="a", priority=100))
    queue.queue_path.write_text(queue.queue_path.read_text(encoding="utf-8") + "{bad json\n", encoding="utf-8")

    pending = queue.pending_requests()

    assert [item.request_id for item in pending] == ["req-1"]


def test_next_request_priority_then_fifo(tmp_path: Path) -> None:
    queue = ForgeQueue(pulse_root=tmp_path / "pulse")
    queue.enqueue(ForgeRequest(request_id="req-low", goal="low", priority=100, requested_at="2025-01-01T00:00:03Z"))
    queue.enqueue(ForgeRequest(request_id="req-high-old", goal="high-old", priority=5, requested_at="2025-01-01T00:00:01Z"))
    queue.enqueue(ForgeRequest(request_id="req-high-new", goal="high-new", priority=5, requested_at="2025-01-01T00:00:02Z"))

    next_request = queue.next_request()

    assert next_request is not None
    assert next_request.request_id == "req-high-old"


def test_daemon_lock_prevents_concurrent_run(tmp_path: Path, monkeypatch) -> None:
    queue = ForgeQueue(pulse_root=tmp_path / "pulse")
    queue.enqueue(ForgeRequest(request_id="req-1", goal="goal"))
    forge = _FakeForge(tmp_path)
    daemon = ForgeDaemon(queue=queue, forge=forge, repo_root=tmp_path)
    daemon.lock_path.parent.mkdir(parents=True, exist_ok=True)
    daemon.lock_path.write_text(json.dumps({"request_id": "other", "started_at": "2099-01-01T00:00:00Z"}), encoding="utf-8")
    monkeypatch.setenv("SENTIENTOS_FORGE_DAEMON_ENABLED", "1")

    daemon.run_tick()

    assert forge.runs == []


def test_daemon_writes_receipt_with_report_path(tmp_path: Path, monkeypatch) -> None:
    queue = ForgeQueue(pulse_root=tmp_path / "pulse")
    queue.enqueue(ForgeRequest(request_id="req-1", goal="goal"))
    forge = _FakeForge(tmp_path)
    daemon = ForgeDaemon(queue=queue, forge=forge, repo_root=tmp_path)
    monkeypatch.setenv("SENTIENTOS_FORGE_DAEMON_ENABLED", "1")

    daemon.run_tick()

    receipts = queue.recent_receipts(limit=5)
    assert any(receipt.status == "success" for receipt in receipts)
    finished = [receipt for receipt in receipts if receipt.status == "success"][0]
    assert finished.report_path is not None
    assert Path(finished.report_path).exists()


def test_pr_notes_generator_avoids_placeholder_content() -> None:
    body = build_pr_notes(
        diff_stats={"files_added": 1, "files_modified": 2, "files_removed": 0},
        touched_paths=["sentientos/forge_daemon.py", "tests/test_forge_queue_daemon.py"],
        key_actions=["placeholder PR body", "wired daemon tick"],
        tests_run=["python -m scripts.run_tests -q"],
        risks=["tbd", "rollback: revert forge daemon wiring"],
    )

    assert "placeholder PR body" not in body.lower()
    assert "What changed" in body
    assert "wired daemon tick" in body
