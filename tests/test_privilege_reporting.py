from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import pytest

from privilege_lint.metrics import MetricsCollector
from privilege_lint.reporting import (
    ErrorHandler,
    JSONFormatEngine,
    LintExecution,
    MarkdownFormatEngine,
    NarratorLink,
    PrivilegeReport,
    ReportRouter,
    ReviewBoardHook,
    YAMLFormatEngine,
)
import privilege_lint


def _stub_execution(issues: list[str]) -> LintExecution:
    metrics = MetricsCollector()
    metrics.finish()
    return LintExecution(
        metrics=metrics,
        issues=issues,
        timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
        checked_files=[Path("/repo/app.py")],
        project_root=Path("/repo"),
        config_hash="abc123",
        report_json_enabled=True,
        sarif_enabled=False,
    )


class StubRunner:
    def __init__(self, issues: list[str]) -> None:
        self.issues = issues
        self.calls: list[tuple[list[str], dict[str, object]]] = []

    def __call__(self, paths, **kwargs) -> LintExecution:  # type: ignore[override]
        self.calls.append((list(paths), kwargs))
        return _stub_execution(self.issues)


def _make_router(tmp_path: Path, issues: list[str]) -> ReportRouter:
    runner = StubRunner(issues)
    engines = [JSONFormatEngine(), YAMLFormatEngine(), MarkdownFormatEngine()]
    return ReportRouter(
        engines={engine.format_name: engine for engine in engines},
        runner=runner,
        error_handler=ErrorHandler(),
        archive_root=tmp_path,
        default_paths=["/repo"],
        logger=logging.getLogger("privilege-test"),
    )


def test_report_router_generates_requested_format(tmp_path: Path) -> None:
    router = _make_router(tmp_path, ["app.py:1: missing banner"])
    report, rendered, archive_path, fmt = router.generate("yaml")
    assert fmt == "yaml"
    assert report.status == "violation"
    assert "missing banner" in rendered
    assert archive_path.suffix == ".yaml"
    assert archive_path.read_text(encoding="utf-8") == rendered


def test_report_router_falls_back_to_default_on_error(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    router = _make_router(tmp_path, [])
    report, _, archive_path, fmt = router.generate("xml")
    assert fmt == "json"
    assert report.passed
    assert archive_path.suffix == ".json"
    assert any("defaulting" in record.message for record in caplog.records)


def test_narrator_link_announces_states(tmp_path: Path) -> None:
    messages: list[str] = []
    link = NarratorLink(messages.append)
    clean_report = PrivilegeReport(
        status="clean",
        timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
        issues=[],
        metrics={"files": 1, "cache_hits": 0, "runtime": 0, "rules": {}},
        checked_files=["app.py"],
    )
    link.announce_boot(clean_report, archive_path=tmp_path / "clean.json")
    link.narrate_amendment(clean_report, spec_id="spec-1", proposal_id="amend-1")
    assert any("Sanctuary Privilege: intact" in msg for msg in messages)
    assert any("privilege intact" in msg.lower() for msg in messages)


def test_review_board_hook_invokes_narrator(tmp_path: Path) -> None:
    reports: list[str] = []
    runner = StubRunner([])
    engines = [JSONFormatEngine(), YAMLFormatEngine(), MarkdownFormatEngine()]
    router = ReportRouter(
        engines={engine.format_name: engine for engine in engines},
        runner=runner,
        error_handler=ErrorHandler(),
        archive_root=tmp_path,
        default_paths=["/repo"],
        logger=logging.getLogger("privilege-test"),
    )
    narrator = NarratorLink(reports.append)
    hook = ReviewBoardHook(router, narrator=narrator)
    report = hook.enforce(spec_id="spec-1", proposal_id="amend-1")
    assert report.passed
    assert reports, "Narrator should emit amendment status"


def test_privilege_lint_report_cli(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    stub_report = PrivilegeReport(
        status="clean",
        timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
        issues=[],
        metrics={"files": 0, "cache_hits": 0, "runtime": 0, "rules": {}},
        checked_files=[],
    )

    class StubRouter:
        def generate(self, fmt: str | None = None, *, paths=None, max_workers=None, mypy: bool = False):
            path = tmp_path / "report.json"
            payload = "{\n  \"status\": \"clean\"\n}"
            path.write_text(payload, encoding="utf-8")
            return stub_report, payload, path, fmt or "json"

    monkeypatch.setattr(
        "privilege_lint.reporting.report_router.create_default_router",
        lambda logger=None: StubRouter(),
    )
    with pytest.raises(SystemExit) as excinfo:
        privilege_lint.cli(["report", "--format", "json"])
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert "\"status\": \"clean\"" in captured.out
