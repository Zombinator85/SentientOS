from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class _CollectionStats:
    tests_collected: int | None = None
    tests_selected: int | None = None
    tests_deselected: int = 0
    tests_executed: int = 0


class PytestCollectionReporter:
    def __init__(self, report_path: Path) -> None:
        self._report_path = report_path
        self._stats = _CollectionStats()

    def pytest_deselected(self, items: list[object]) -> None:
        self._stats.tests_deselected += len(items)

    def pytest_collection_modifyitems(self, session, config, items: list[object]) -> None:
        self._stats.tests_selected = len(items)
        if session.testscollected is not None:
            self._stats.tests_collected = session.testscollected
        else:
            self._stats.tests_collected = self._stats.tests_selected + self._stats.tests_deselected

    def pytest_sessionfinish(self, session, exitstatus: int) -> None:
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
            "pytest_exit_code": exitstatus,
        }
        self._report_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def pytest_runtest_logreport(self, report) -> None:
        if report.when != "call":
            return
        if report.passed or report.failed or report.skipped:
            self._stats.tests_executed += 1


def pytest_configure(config) -> None:
    report_path = os.getenv("SENTIENTOS_PYTEST_REPORT_PATH")
    if not report_path:
        return
    reporter = PytestCollectionReporter(Path(report_path))
    config.pluginmanager.register(reporter, "sentientos-pytest-collection-reporter")
