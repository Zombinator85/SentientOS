from __future__ import annotations

from pathlib import Path

from sentientos.forge_daemon import ForgeDaemon
from sentientos.forge_queue import ForgeQueue, ForgeRequest


class _Report:
    def __init__(self) -> None:
        self.generated_at = "2026-01-01T00:00:00Z"
        self.outcome = "success"
        self.docket_path = None
        self.git_sha = "abc"
        self.failure_reasons: list[str] = []
        self.provenance_run_id = None
        self.provenance_path = None
        self.transaction_status = "committed"
        self.quarantine_ref = None
        self.regression_reasons = []
        self.publish_remote = {"checks_overall": "failure", "pr_url": "https://github.com/o/r/pull/1"}
        self.goal_id = "forge_smoke_noop"
        self.notes: list[str] = []


class _Forge:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root

    def run(self, goal: str, *, initiator: str, request_id: str | None, metadata: dict[str, object] | None):
        _ = goal, initiator, request_id, metadata
        return _Report()

    def _report_path(self, generated_at: str) -> Path:
        return self.repo_root / "glow/forge" / f"report_{generated_at}.json"


class _Sentinel:
    def __init__(self, *args, **kwargs) -> None:
        self.called = []

    def note_quarantine(self, *, domain: str, quarantine_ref: str | None, reasons: list[str]) -> None:
        self.called.append((domain, quarantine_ref, reasons))


def test_sentinel_cooldown_extension_on_failed_remote_checks(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "glow/forge").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/forge/policy.json").write_text(
        """{
  "allowlisted_goal_ids": ["forge_smoke_noop"],
  "allowlisted_requesters": ["ContractSentinel"],
  "allowlisted_autopublish_flags": [
    "auto_publish",
    "sentinel_allow_autopublish",
    "sentinel_allow_automerge",
    "retry_on_failure",
    "lineage"
  ]
}
""",
        encoding="utf-8",
    )
    queue = ForgeQueue(pulse_root=tmp_path / "pulse")
    request_id = queue.enqueue(
        ForgeRequest(
            request_id="",
            goal="forge_smoke_noop",
            goal_id="forge_smoke_noop",
            requested_by="ContractSentinel",
            autopublish_flags={"auto_publish": True, "sentinel_allow_autopublish": True, "sentinel_allow_automerge": True},
            metadata={"sentinel_triggered": True, "trigger_domain": "forge_observatory"},
        )
    )
    assert request_id

    sentinel = _Sentinel()
    monkeypatch.setenv("SENTIENTOS_FORGE_DAEMON_ENABLED", "1")
    monkeypatch.setattr("sentientos.forge_daemon.ContractSentinel", lambda repo_root, queue: sentinel)

    daemon = ForgeDaemon(queue=queue, forge=_Forge(tmp_path), repo_root=tmp_path)
    daemon.run_tick()

    assert sentinel.called
    domain, qref, reasons = sentinel.called[0]
    assert domain == "forge_observatory"
    assert qref == "https://github.com/o/r/pull/1"
    assert "remote_checks_gate" in reasons
