from __future__ import annotations

import json
import os
import traceback
from dataclasses import dataclass
from pathlib import Path


@dataclass
class _CollectionStats:
    tests_collected: int | None = None
    tests_selected: int | None = None
    tests_deselected: int = 0
    tests_executed: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    tests_skipped: int = 0
    tests_xfailed: int = 0
    tests_xpassed: int = 0


class PytestCollectionReporter:
    def __init__(self, report_path: Path) -> None:
        self._report_path = report_path
        self._stats = _CollectionStats()
        self._reporter_ok = True
        self._reporter_error: dict[str, str] | None = None

    def _record_error(self, exc: BaseException) -> None:
        self._reporter_ok = False
        if self._reporter_error is not None:
            return
        trace_excerpt = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__, limit=5)).strip()
        self._reporter_error = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": trace_excerpt,
        }

    def _safe_hook(self, fn) -> None:
        try:
            fn()
        except Exception as exc:
            self._record_error(exc)

    def pytest_deselected(self, items: list[object]) -> None:
        self._safe_hook(lambda: self._handle_pytest_deselected(items))

    def _handle_pytest_deselected(self, items: list[object]) -> None:
        self._stats.tests_deselected += len(items)

    def pytest_collection_modifyitems(self, session, config, items: list[object]) -> None:
        self._safe_hook(lambda: self._handle_pytest_collection_modifyitems(session, config, items))

    def _handle_pytest_collection_modifyitems(self, session, config, items: list[object]) -> None:
        self._stats.tests_selected = len(items)
        if session.testscollected is not None:
            self._stats.tests_collected = session.testscollected
        else:
            self._stats.tests_collected = self._stats.tests_selected + self._stats.tests_deselected

    def pytest_sessionfinish(self, session, exitstatus: int) -> None:
        self._safe_hook(lambda: self._handle_pytest_sessionfinish(session, exitstatus))

    def _handle_pytest_sessionfinish(self, session, exitstatus: int) -> None:
        if self._stats.tests_selected is None:
            self._stats.tests_selected = len(getattr(session, "items", []))
        if self._stats.tests_collected is None:
            if session.testscollected is not None:
                self._stats.tests_collected = session.testscollected
            else:
                self._stats.tests_collected = self._stats.tests_selected + self._stats.tests_deselected
        payload = {
            "tests_collected": self._stats.tests_collected,
            "tests_selected": self._stats.tests_selected,
            "tests_executed": self._stats.tests_executed,
            "tests_failed": self._stats.tests_failed,
            "tests_passed": self._stats.tests_passed,
            "tests_skipped": self._stats.tests_skipped,
            "tests_xfailed": self._stats.tests_xfailed,
            "tests_xpassed": self._stats.tests_xpassed,
            "pytest_exit_code": exitstatus,
            "reporter_ok": self._reporter_ok,
            "reporter_error": self._reporter_error,
        }
        self._report_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def pytest_runtest_logreport(self, report) -> None:
        self._safe_hook(lambda: self._handle_pytest_runtest_logreport(report))

    def _handle_pytest_runtest_logreport(self, report) -> None:
        if report.when != "call":
            return
        if report.passed or report.failed or report.skipped:
            self._stats.tests_executed += 1
        if report.passed:
            if getattr(report, "wasxfail", False):
                self._stats.tests_xpassed += 1
            else:
                self._stats.tests_passed += 1
            return
        if report.failed:
            if getattr(report, "wasxfail", False):
                self._stats.tests_xfailed += 1
            else:
                self._stats.tests_failed += 1
            return
        if report.skipped:
            if getattr(report, "wasxfail", False):
                self._stats.tests_xfailed += 1
            else:
                self._stats.tests_skipped += 1


def pytest_configure(config) -> None:
    report_path = os.getenv("SENTIENTOS_PYTEST_REPORT_PATH")
    if not report_path:
        return
    reporter = PytestCollectionReporter(Path(report_path))
    config.pluginmanager.register(reporter, "sentientos-pytest-collection-reporter")
