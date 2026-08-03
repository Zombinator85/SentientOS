from __future__ import annotations

import json
import os
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pytest

from sentientos.behavioral_witness import MAX_PER_NODE, MAX_PER_RUN, build_witness, digest

_ACTIVE_REPORTER: "PytestCollectionReporter | None" = None


class BehavioralWitnessRecorder:
    def __init__(self, reporter: "PytestCollectionReporter", node_id: str) -> None:
        self._reporter = reporter
        self._node_id = node_id

    def record(self, contract_id: str, witness_kind: str, facts: object) -> None:
        self._reporter.record_witness(self._node_id, contract_id, witness_kind, facts)


@pytest.fixture
def behavioral_witness(request: Any) -> BehavioralWitnessRecorder:
    if _ACTIVE_REPORTER is None:
        raise RuntimeError("behavioral_witness requires scripts.run_tests provenance context")
    return BehavioralWitnessRecorder(_ACTIVE_REPORTER, str(request.node.nodeid))


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
    def __init__(self, report_path: Path, repository_sha: str = "test-repository-sha", run_id: str = "test-run-id") -> None:
        self._report_path = report_path
        self._stats = _CollectionStats()
        self._reporter_ok = True
        self._reporter_error: dict[str, str] | None = None
        self._selected_node_ids: list[str] = []
        self._node_outcomes: dict[str, dict[str, object]] = {}
        self._repository_sha = repository_sha
        self._run_id = run_id
        self._active_call_node: str | None = None
        self._witnesses: dict[tuple[str, str, str], dict[str, object]] = {}
        self._collection_started = False
        self._collection_completed = False
        self._collection_error = False
        self._session_finish_reached = False

    def pytest_collection(self) -> None:
        self._collection_started = True

    def pytest_collectreport(self, report: Any) -> None:
        if getattr(report, "failed", False):
            self._collection_error = True

    def record_witness(self, node_id: str, contract_id: str, witness_kind: str, facts: object) -> None:
        if self._active_call_node != node_id:
            raise RuntimeError("behavioral witnesses may only be recorded during the current call phase")
        witness = build_witness(repository_sha=self._repository_sha, run_id=self._run_id,
                                node_id=node_id, contract_id=contract_id,
                                witness_kind=witness_kind, facts=facts)
        key = (node_id, contract_id, witness_kind)
        prior = self._witnesses.get(key)
        if prior is not None and prior != witness:
            raise ValueError("conflicting behavioral witness for node, contract, and kind")
        if prior is not None:
            return
        if sum(key_[0] == node_id for key_ in self._witnesses) >= MAX_PER_NODE or len(self._witnesses) >= MAX_PER_RUN:
            raise ValueError("behavioral witness count bound exceeded")
        self._witnesses[key] = witness

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_call(self, item: Any) -> Any:
        self._active_call_node = str(item.nodeid)
        try:
            yield
        finally:
            self._active_call_node = None

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

    def _safe_hook(self, fn: Callable[[], None]) -> None:
        try:
            fn()
        except Exception as exc:
            self._record_error(exc)

    def pytest_deselected(self, items: list[object]) -> None:
        self._safe_hook(lambda: self._handle_pytest_deselected(items))

    def _handle_pytest_deselected(self, items: list[object]) -> None:
        self._stats.tests_deselected += len(items)

    def pytest_collection_modifyitems(self, session: Any, config: Any, items: list[object]) -> None:
        self._safe_hook(lambda: self._handle_pytest_collection_modifyitems(session, config, items))

    def _handle_pytest_collection_modifyitems(self, session: Any, config: Any, items: list[object]) -> None:
        self._collection_started = True
        self._collection_completed = True
        self._stats.tests_selected = len(items)
        self._selected_node_ids = [str(getattr(item, "nodeid")) for item in items]
        if session.testscollected is not None:
            self._stats.tests_collected = session.testscollected
        else:
            self._stats.tests_collected = self._stats.tests_selected + self._stats.tests_deselected

    def pytest_sessionfinish(self, session: Any, exitstatus: int) -> None:
        self._safe_hook(lambda: self._handle_pytest_sessionfinish(session, exitstatus))

    def _handle_pytest_sessionfinish(self, session: Any, exitstatus: int) -> None:
        self._session_finish_reached = True
        if not self._collection_error and self._stats.tests_selected is not None:
            self._collection_completed = True
        if isinstance(getattr(session, "testscollected", None), int):
            self._stats.tests_collected = session.testscollected
        if self._stats.tests_selected is None:
            self._stats.tests_selected = len(getattr(session, "items", []))
        if self._stats.tests_collected is None:
            if session.testscollected is not None:
                self._stats.tests_collected = session.testscollected
            else:
                self._stats.tests_collected = self._stats.tests_selected + self._stats.tests_deselected
        witnesses = [self._witnesses[key] for key in sorted(self._witnesses)]
        per_node = {node: sum(w["node_id"] == node for w in witnesses) for node in self._selected_node_ids}
        call_phase_outcome_count = len(self._node_outcomes)
        reporter_status = "complete" if self._reporter_ok and self._session_finish_reached else "incomplete"
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
            "reporter_loaded": True,
            "reporter_status": reporter_status,
            "collection_started": self._collection_started,
            "collection_completed": self._collection_completed,
            "collection_error": self._collection_error,
            "session_finish_reached": self._session_finish_reached,
            "call_phase_outcome_count": call_phase_outcome_count,
            "selected_node_ids": self._selected_node_ids,
            "node_outcomes": [self._node_outcomes[node] for node in self._selected_node_ids if node in self._node_outcomes],
            "behavioral_witnesses": witnesses,
            "behavioral_witness_count": len(witnesses),
            "behavioral_witness_digest": digest(witnesses),
            "behavioral_witness_counts_by_node": per_node,
            "behavioral_witness_reporter_status": "complete" if self._reporter_ok else "incomplete",
        }
        self._report_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def pytest_runtest_logreport(self, report: Any) -> None:
        self._safe_hook(lambda: self._handle_pytest_runtest_logreport(report))

    def _handle_pytest_runtest_logreport(self, report: Any) -> None:
        if report.when != "call":
            return
        nodeid = str(getattr(report, "nodeid", "<unknown>"))
        if report.passed:
            outcome = "xpassed" if getattr(report, "wasxfail", False) else "passed"
        elif report.failed:
            outcome = "xfailed" if getattr(report, "wasxfail", False) else "failed"
        else:
            outcome = "xfailed" if getattr(report, "wasxfail", False) else "skipped"
        self._node_outcomes[nodeid] = {"node_id": nodeid, "phase": "call", "outcome": outcome}
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


def pytest_configure(config: Any) -> None:
    global _ACTIVE_REPORTER
    report_path = os.getenv("SENTIENTOS_PYTEST_REPORT_PATH")
    if not report_path:
        return
    reporter = PytestCollectionReporter(Path(report_path), os.getenv("SENTIENTOS_REPOSITORY_SHA", ""), os.getenv("SENTIENTOS_TEST_RUN_ID", ""))
    _ACTIVE_REPORTER = reporter
    config.pluginmanager.register(reporter, "sentientos-pytest-collection-reporter")
