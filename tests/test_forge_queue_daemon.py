from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from sentientos.forge_daemon import ForgeDaemon
from sentientos.forge_pr_notes import build_pr_notes
from sentientos.forge_queue import (
    ForgeQueue,
    ForgeQueueCustodyError,
    ForgeReceiptLedgerError,
    ForgeRequest,
)


@pytest.fixture(autouse=True)
def _forge_events_are_local(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sentientos.event_stream.FORGE_EVENTS_PATH",
        tmp_path / "pulse" / "forge_events.jsonl")


class _FakeReport:
    def __init__(self, *, generated_at: str = "2025-01-01T00:00:00Z", outcome: str = "success") -> None:
        self.generated_at = generated_at
        self.notes: list[str] = []
        self.outcome = outcome
        self.docket_path: str | None = None
        self.git_sha = "abc123"
        self.failure_reasons: list[str] = []
        self.publish_remote: dict[str, object] = {}
        self.transaction_status = "completed"
        self.regression_reasons: list[str] = []
        self.provenance_run_id: str | None = None
        self.provenance_path: str | None = None
        self.goal_id = "adhoc"


class _FakeForge:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.runs: list[str] = []

    def run(self, goal: str, **_kwargs: object) -> _FakeReport:
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


def test_corrupt_receipt_ledger_cannot_requeue_request_or_reach_forge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue = ForgeQueue(pulse_root=tmp_path / "pulse")
    queue.enqueue(ForgeRequest(request_id="req-1", goal="forge_smoke_noop", goal_id="forge_smoke_noop"))
    queue.receipts_path.write_text('{"request_id":"req-1","status":"started"}\n{bad json\n', encoding="utf-8")
    forge = _FakeForge(tmp_path)
    daemon = ForgeDaemon(queue=queue, forge=forge, repo_root=tmp_path)
    monkeypatch.setenv("SENTIENTOS_FORGE_DAEMON_ENABLED", "1")

    with pytest.raises(ForgeReceiptLedgerError, match="receipt_ledger_json_invalid"):
        daemon.run_tick()

    assert forge.runs == []


def test_legacy_terminal_receipt_remains_consumed(tmp_path: Path) -> None:
    queue = ForgeQueue(pulse_root=tmp_path / "pulse")
    queue.enqueue(ForgeRequest(request_id="req-legacy", goal="forge_smoke_noop", goal_id="forge_smoke_noop"))
    queue.receipts_path.parent.mkdir(parents=True, exist_ok=True)
    queue.receipts_path.write_text('{"request_id":"req-legacy","status":"success"}\n', encoding="utf-8")

    assert queue.next_request() is None


@pytest.mark.parametrize("raw", [
    b'{"request_id":"r","request_id":"r","status":"success"}\n',
    b'[]\n',
    b'{"request_id":"r","status":NaN}\n',
    b"x" * (1_048_577),
    b'{"request_id":"r","status":"success"}\n' * 4097,
])
def test_invalid_receipt_identity_and_oversized_ledger_fail_closed(
    tmp_path: Path, raw: bytes,
) -> None:
    queue = ForgeQueue(pulse_root=tmp_path / "pulse")
    queue.enqueue(ForgeRequest(request_id="req-1", goal="forge_smoke_noop", goal_id="forge_smoke_noop"))
    queue.receipts_path.parent.mkdir(parents=True, exist_ok=True)
    queue.receipts_path.write_bytes(raw)

    with pytest.raises(ForgeReceiptLedgerError):
        queue.next_request()


def test_append_refuses_symlink_target_and_oversized_row(tmp_path: Path) -> None:
    queue = ForgeQueue(pulse_root=tmp_path / "pulse")
    queue.receipts_path.parent.mkdir(parents=True, exist_ok=True)
    external = tmp_path / "outside.jsonl"
    external.write_text("preserve\n", encoding="utf-8")
    queue.receipts_path.symlink_to(external)

    with pytest.raises(ForgeQueueCustodyError):
        queue.mark_finished("req-1", status="rejected_quarantine_custody",
            report_path=None, error="quarantine_json_invalid")
    assert external.read_text(encoding="utf-8") == "preserve\n"

    queue.receipts_path.unlink()
    with pytest.raises(ForgeQueueCustodyError, match="ledger_record_too_large"):
        queue.enqueue(ForgeRequest(request_id="large", goal="goal",
            metadata={"bounded": "x" * 70_000}))


def test_request_reader_rejects_symlink_and_oversized_custody(tmp_path: Path) -> None:
    queue = ForgeQueue(pulse_root=tmp_path / "pulse")
    queue.queue_path.parent.mkdir(parents=True, exist_ok=True)
    external = tmp_path / "outside-queue.jsonl"
    external.write_text('{"request_id":"r","goal":"forge_smoke_noop"}\n', encoding="utf-8")
    queue.queue_path.symlink_to(external)
    with pytest.raises(ForgeQueueCustodyError):
        queue.pending_requests()

    queue.queue_path.unlink()
    queue.queue_path.write_bytes(b"x" * (1_048_577))
    with pytest.raises(ForgeQueueCustodyError):
        queue.pending_requests()


def test_prune_validates_both_ledgers_before_replacing_either(tmp_path: Path) -> None:
    queue = ForgeQueue(pulse_root=tmp_path / "pulse")
    queue.enqueue(ForgeRequest(request_id="req-1", goal="forge_smoke_noop"))
    queue.receipts_path.parent.mkdir(parents=True, exist_ok=True)
    queue.receipts_path.write_bytes(b'{"request_id":"req-1","status":"started"}\n{bad\n')
    original_queue = queue.queue_path.read_bytes()
    original_receipts = queue.receipts_path.read_bytes()

    with pytest.raises(ForgeReceiptLedgerError):
        queue.prune(max_age_days=0, keep_last_n=1)

    assert queue.queue_path.read_bytes() == original_queue
    assert queue.receipts_path.read_bytes() == original_receipts


def test_prune_rejects_semantically_incomplete_ledgers_without_rewriting(
    tmp_path: Path,
) -> None:
    queue = ForgeQueue(pulse_root=tmp_path / "pulse")
    queue.enqueue(ForgeRequest(request_id="req-1", goal="forge_smoke_noop"))
    queue.receipts_path.parent.mkdir(parents=True, exist_ok=True)
    queue.receipts_path.write_text(
        '{"request_id":"req-1","status":"started"}\n', encoding="utf-8",
    )
    queue_bytes = queue.queue_path.read_bytes()
    receipt_bytes = queue.receipts_path.read_bytes()

    queue.queue_path.write_bytes(queue_bytes + b'{"request_id":"missing-goal"}\n')
    damaged_queue = queue.queue_path.read_bytes()
    with pytest.raises(ForgeQueueCustodyError, match="queue_ledger_identity_invalid"):
        queue.prune()
    assert queue.queue_path.read_bytes() == damaged_queue
    assert queue.receipts_path.read_bytes() == receipt_bytes

    queue.queue_path.write_bytes(queue_bytes)
    queue.receipts_path.write_text('{"status":"started"}\n', encoding="utf-8")
    damaged_receipts = queue.receipts_path.read_bytes()
    with pytest.raises(ForgeReceiptLedgerError, match="receipt_ledger_identity_invalid"):
        queue.prune()
    assert queue.queue_path.read_bytes() == queue_bytes
    assert queue.receipts_path.read_bytes() == damaged_receipts


def test_prune_preserves_complete_receipt_chain_for_retained_request(tmp_path: Path) -> None:
    queue = ForgeQueue(pulse_root=tmp_path / "pulse")
    old = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    current = datetime.now(timezone.utc).isoformat()
    queue.enqueue(ForgeRequest(request_id="req-drop", goal="old", requested_at=old))
    queue.enqueue(ForgeRequest(request_id="req-keep", goal="current", requested_at=current))
    queue.receipts_path.parent.mkdir(parents=True, exist_ok=True)
    stale_chain = [
        {"request_id": "req-keep", "status": "started", "started_at": old},
        {"request_id": "req-keep", "status": "success", "finished_at": old},
        {"request_id": "req-drop", "status": "success", "finished_at": old},
    ]
    queue.receipts_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in stale_chain),
        encoding="utf-8",
    )

    queue.prune(max_age_days=1, keep_last_n=1)

    assert [request.request_id for request in queue._load_requests()] == ["req-keep"]
    recovered = queue._read_receipt_rows()
    assert [(row["request_id"], row["status"]) for row in recovered] == [
        ("req-keep", "started"), ("req-keep", "success"),
    ]
    assert queue.next_request() is None


def test_interrupted_prune_leaves_only_inert_extra_receipts_and_retries_safely(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue = ForgeQueue(pulse_root=tmp_path / "pulse")
    old = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    current = datetime.now(timezone.utc).isoformat()
    queue.enqueue(ForgeRequest(request_id="req-drop", goal="old", requested_at=old))
    queue.enqueue(ForgeRequest(request_id="req-keep", goal="current", requested_at=current))
    queue.receipts_path.parent.mkdir(parents=True, exist_ok=True)
    receipts = [
        {"request_id": "req-drop", "status": "success", "finished_at": old},
        {"request_id": "req-keep", "status": "started", "started_at": old},
        {"request_id": "req-keep", "status": "success", "finished_at": old},
    ]
    queue.receipts_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in receipts),
        encoding="utf-8",
    )
    replace_jsonl = queue._replace_jsonl

    def interrupt_receipt_replace(path: Path, rows: list[dict[str, object]]) -> None:
        if path == queue.receipts_path:
            raise OSError("simulated interruption before receipt publication")
        replace_jsonl(path, rows)

    monkeypatch.setattr(queue, "_replace_jsonl", interrupt_receipt_replace)
    with pytest.raises(OSError, match="simulated interruption"):
        queue.prune(max_age_days=1, keep_last_n=1)

    assert [request.request_id for request in queue._load_requests()] == ["req-keep"]
    assert len(queue._read_receipt_rows()) == 3
    assert queue.next_request() is None

    monkeypatch.setattr(queue, "_replace_jsonl", replace_jsonl)
    queue.prune(max_age_days=1, keep_last_n=1)
    assert [(row["request_id"], row["status"]) for row in queue._read_receipt_rows()] == [
        ("req-keep", "started"), ("req-keep", "success"),
    ]
    assert queue.next_request() is None


def test_append_enforces_reader_row_bound_and_rejects_partial_tail(tmp_path: Path) -> None:
    queue = ForgeQueue(pulse_root=tmp_path / "pulse")
    queue.queue_path.parent.mkdir(parents=True, exist_ok=True)
    rows = b'{"request_id":"old","goal":"goal"}\n' * 4096
    queue.queue_path.write_bytes(rows)

    with pytest.raises(ForgeQueueCustodyError, match="ledger_row_limit_exceeded"):
        queue.enqueue(ForgeRequest(request_id="req-over-limit", goal="goal"))
    assert queue.queue_path.read_bytes() == rows

    queue.queue_path.write_bytes(b'{"request_id":"old","goal":"goal"}')
    with pytest.raises(ForgeQueueCustodyError, match="ledger_existing_tail_incomplete"):
        queue.enqueue(ForgeRequest(request_id="req-partial", goal="goal"))
    assert queue.queue_path.read_bytes() == b'{"request_id":"old","goal":"goal"}'

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
    queue.enqueue(ForgeRequest(request_id="req-1", goal="forge_smoke_noop", goal_id="forge_smoke_noop"))
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


def test_daemon_policy_rejects_non_allowlisted_goal(tmp_path: Path, monkeypatch) -> None:
    queue = ForgeQueue(pulse_root=tmp_path / "pulse")
    queue.enqueue(ForgeRequest(request_id="req-1", goal="unsafe_goal", goal_id="unsafe_goal"))
    forge = _FakeForge(tmp_path)

    policy_path = tmp_path / "glow" / "forge" / "policy.json"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(json.dumps({
        "allowlisted_goal_ids": ["forge_smoke_noop"],
        "allowlisted_autopublish_flags": [],
        "max_budget": {},
    }), encoding="utf-8")

    daemon = ForgeDaemon(queue=queue, forge=forge, repo_root=tmp_path)
    monkeypatch.setenv("SENTIENTOS_FORGE_DAEMON_ENABLED", "1")

    daemon.run_tick()

    assert forge.runs == []
    receipts = queue.recent_receipts(limit=5)
    assert any(receipt.status == "rejected_policy" for receipt in receipts)
