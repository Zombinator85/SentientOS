import json
import warnings

import pytest

from sentientos import optional_deps
from sentientos.helpers import compute_system_diagnostics

pytestmark = pytest.mark.no_legacy_skip


def _register_missing_dependency(monkeypatch) -> None:
    dep = optional_deps.OptionalDependency(
        package="missing-dep",
        module_name="missing_dep",
        features=("missing_feature",),
        import_probe=lambda: None,
        install_hint="pip install missing-dep",
        missing_behavior="warn_once",
    )
    monkeypatch.setitem(optional_deps.OPTIONAL_DEPENDENCIES, "missing-dep", dep)
    optional_deps.reset_optional_dependency_state()


def test_optional_import_warns_once(monkeypatch, caplog) -> None:
    _register_missing_dependency(monkeypatch)
    caplog.set_level("WARNING", logger="sentientos.optional_deps")

    optional_deps.optional_import("missing-dep", feature="missing_feature")
    optional_deps.optional_import("missing-dep", feature="missing_feature")

    warnings_seen = [record for record in caplog.records if "missing-dep" in record.message]
    assert len(warnings_seen) == 1


def test_optional_import_avoids_python_warnings(monkeypatch) -> None:
    _register_missing_dependency(monkeypatch)
    with warnings.catch_warnings(record=True) as caught:
        optional_deps.optional_import("missing-dep", feature="missing_feature")
    assert caught == []


def test_optional_dependency_report_is_json_serializable() -> None:
    report = compute_system_diagnostics()
    json.dumps(report)
    assert "optional_dependencies" in report
    assert "features" in report["optional_dependencies"]


def test_optional_dependency_report_marks_missing(monkeypatch) -> None:
    _register_missing_dependency(monkeypatch)
    report = optional_deps.optional_dependency_report()
    feature = next(
        entry for entry in report["features"] if entry["feature"] == "missing_feature"
    )
    assert feature["enabled"] is False


def test_optional_import_returns_module_when_available() -> None:
    module = optional_deps.optional_import("pyyaml", feature="runtime_config")
    assert module is not None
