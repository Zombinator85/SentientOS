from __future__ import annotations

from sentientos import github_checks
from sentientos.github_checks import PRRef, PRChecks, CheckRun


def test_detect_capabilities(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(github_checks.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    caps = github_checks.detect_capabilities()
    assert caps == {"gh": True, "token": True}


def test_wait_for_checks_pending_to_success(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    pr = PRRef(number=1, url="https://github.com/o/r/pull/1", head_sha="abc", branch="b", created_at="2026-01-01T00:00:00Z")
    rows = [
        PRChecks(pr=pr, checks=[CheckRun(name="ci", status="in_progress", conclusion="", details_url="")], overall="pending"),
        PRChecks(pr=pr, checks=[CheckRun(name="ci", status="completed", conclusion="success", details_url="")], overall="success"),
    ]

    def fake_fetch(**_kwargs):
        return rows.pop(0)

    monkeypatch.setattr(github_checks, "fetch_pr_checks", fake_fetch)
    monkeypatch.setattr(github_checks.time, "sleep", lambda _s: None)
    final, timing = github_checks.wait_for_pr_checks(pr, timeout_seconds=30, poll_interval_seconds=1)
    assert final.overall == "success"
    assert timing["timed_out"] is False


def test_wait_for_checks_pending_to_failure(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    pr = PRRef(number=2, url="https://github.com/o/r/pull/2", head_sha="def", branch="b", created_at="2026-01-01T00:00:00Z")
    rows = [
        PRChecks(pr=pr, checks=[CheckRun(name="ci", status="in_progress", conclusion="", details_url="")], overall="pending"),
        PRChecks(pr=pr, checks=[CheckRun(name="ci", status="completed", conclusion="failure", details_url="")], overall="failure"),
    ]

    def fake_fetch(**_kwargs):
        return rows.pop(0)

    monkeypatch.setattr(github_checks, "fetch_pr_checks", fake_fetch)
    monkeypatch.setattr(github_checks.time, "sleep", lambda _s: None)
    final, timing = github_checks.wait_for_pr_checks(pr, timeout_seconds=30, poll_interval_seconds=1)
    assert final.overall == "failure"
    assert timing["timed_out"] is False
