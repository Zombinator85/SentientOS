from __future__ import annotations

import json
from types import SimpleNamespace

from scripts.pytest_collection_reporter import PytestCollectionReporter


def test_reporter_handles_missing_wasxfail_attribute(tmp_path):
    report_path = tmp_path / "report.json"
    reporter = PytestCollectionReporter(report_path)

    report = SimpleNamespace(nodeid="tests/test_x.py::test_ok", when="call", passed=True, failed=False, skipped=False)
    reporter.pytest_runtest_logreport(report)

    session = SimpleNamespace(testscollected=1, items=[object()])
    reporter.pytest_sessionfinish(session, 0)

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["reporter_ok"] is True
    assert payload["reporter_error"] is None
    assert payload["tests_executed"] == 1
    assert payload["tests_passed"] == 1
    assert payload["selected_node_ids"] == []
    assert payload["node_outcomes"] == []


def test_reporter_records_exact_selected_nodes_and_call_outcomes(tmp_path):
    report_path = tmp_path / "report.json"
    reporter = PytestCollectionReporter(report_path)
    item = SimpleNamespace(nodeid="tests/test_x.py::test_ok")
    session = SimpleNamespace(testscollected=1, items=[item])
    reporter.pytest_collection_modifyitems(session, None, [item])
    reporter.pytest_runtest_logreport(SimpleNamespace(nodeid=item.nodeid, when="setup", passed=True, failed=False, skipped=False))
    reporter.pytest_runtest_logreport(SimpleNamespace(nodeid=item.nodeid, when="call", passed=True, failed=False, skipped=False))
    reporter.pytest_sessionfinish(session, 0)
    payload = json.loads(report_path.read_text())
    assert payload["selected_node_ids"] == [item.nodeid]
    assert payload["node_outcomes"][0]["outcome"] == "passed"


def test_reporter_records_single_error_and_continues(tmp_path):
    report_path = tmp_path / "report.json"
    reporter = PytestCollectionReporter(report_path)

    reporter.pytest_runtest_logreport(None)
    reporter.pytest_runtest_logreport(None)

    session = SimpleNamespace(testscollected=0, items=[])
    reporter.pytest_sessionfinish(session, 0)

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["reporter_ok"] is False
    assert payload["reporter_error"]["type"] == "AttributeError"
    assert "when" in payload["reporter_error"]["message"]
