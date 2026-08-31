from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts.mypy_baseline_common import (
    DEFAULT_MYPY_COMMAND,
    CANONICAL_MYPY_VERSION,
    MypyErrorRecord,
    STATUS_IMPROVED,
    STATUS_INVALID,
    STATUS_MATCHES,
    STATUS_MISSING,
    STATUS_REGRESSION,
    build_manifest,
    compare_records,
    load_manifest,
    manifest_to_text,
    parse_mypy_output,
    records_digest,
    normalize_mypy_version,
    sanitized_mypy_environment,
)
from scripts import build_mypy_baseline, check_mypy_baseline


pytestmark = pytest.mark.no_legacy_skip

WORKSPACE_TYPED_SURFACE_COMMAND = (
    "python -m mypy --follow-imports=skip --hide-error-context --no-color-output --show-column-numbers "
    "--show-error-codes sentientos/workspace_change_set_admission.py "
    "scripts/admit_workspace_change_set.py sentientos/workspace_change_set_preflight.py "
    "scripts/preflight_workspace_change_set.py sentientos/workspace_change_set_execution.py "
    "scripts/run_workspace_change_set_transaction.py sentientos/workspace_change_set_execution_verification.py "
    "scripts/verify_workspace_change_set_execution.py sentientos/workspace_change_set_lifecycle_closure.py "
    "scripts/build_workspace_change_set_lifecycle_closure.py sentientos/workspace_change_set_lifecycle_orchestrator.py "
    "scripts/run_workspace_change_set_lifecycle.py"
)


def test_parser_handles_normal_mypy_error_lines() -> None:
    records = parse_mypy_output('sentientos/example.py:12: error: Incompatible return value type [return-value]\n')
    assert records == [
        MypyErrorRecord(
            path="sentientos/example.py",
            line=12,
            column=None,
            code="return-value",
            message="Incompatible return value type",
        )
    ]


def test_parser_handles_error_codes_and_columns() -> None:
    records = parse_mypy_output('scripts/tool.py:7:9: error: Need type annotation for "x" [var-annotated]\n')
    assert records[0].column == 9
    assert records[0].code == "var-annotated"


def test_parser_ignores_summary_notes_and_noise_lines() -> None:
    output = "note: this is not an error\nFound 1 error in 1 file (checked 2 source files)\nscripts/tool.py:7:9: note: Revealed type is Any\n"
    assert parse_mypy_output(output) == []


def test_baseline_manifest_is_deterministic() -> None:
    records = [
        MypyErrorRecord("b.py", 2, None, "arg-type", "B"),
        MypyErrorRecord("a.py", 1, 3, None, "A"),
    ]
    first = manifest_to_text(build_manifest(records=records))
    second = manifest_to_text(build_manifest(records=list(reversed(records))))
    assert first == second


def test_digest_changes_when_normalized_errors_change() -> None:
    first = records_digest([MypyErrorRecord("a.py", 1, None, None, "A")])
    second = records_digest([MypyErrorRecord("a.py", 1, None, None, "B")])
    assert first != second


def test_check_passes_when_current_output_matches_baseline() -> None:
    record = MypyErrorRecord("a.py", 1, None, "attr-defined", "A")
    result = compare_records(baseline_records=[record], current_records=[record])
    assert result["status"] == STATUS_MATCHES
    assert result["new_errors"] == 0
    assert result["matched_existing_errors"] == 1


def test_check_reports_retired_errors_when_current_output_improves() -> None:
    record = MypyErrorRecord("a.py", 1, None, "attr-defined", "A")
    result = compare_records(baseline_records=[record], current_records=[])
    assert result["status"] == STATUS_IMPROVED
    assert result["retired_errors"] == 1


def test_check_fails_when_new_errors_appear() -> None:
    baseline = [MypyErrorRecord("a.py", 1, None, "attr-defined", "A")]
    current = [*baseline, MypyErrorRecord("new_file.py", 2, 4, "return-value", "B")]
    result = compare_records(baseline_records=baseline, current_records=current)
    assert result["status"] == STATUS_REGRESSION
    assert result["new_errors"] == 1
    assert result["affected_new_files"] == ["new_file.py"]




def test_line_drift_is_matched_as_existing_debt() -> None:
    baseline = [MypyErrorRecord("a.py", 10, 2, "attr-defined", "A")]
    current = [MypyErrorRecord("a.py", 22, 4, "attr-defined", "A")]
    result = compare_records(baseline_records=baseline, current_records=current)
    assert result["status"] == STATUS_MATCHES
    assert result["matched_existing_errors"] == 1
    assert result["matched_with_location_drift"] == 1
    assert result["drifted_files"] == ["a.py"]


def test_duplicate_over_baseline_count_is_new_error() -> None:
    baseline = [MypyErrorRecord("a.py", 10, 2, "attr-defined", "A")]
    current = [MypyErrorRecord("a.py", 10, 2, "attr-defined", "A"), MypyErrorRecord("a.py", 12, 1, "attr-defined", "A")]
    result = compare_records(baseline_records=baseline, current_records=current)
    assert result["status"] == STATUS_REGRESSION
    assert result["new_errors"] == 1


def test_different_code_or_message_is_new_error() -> None:
    baseline = [MypyErrorRecord("a.py", 10, 2, "attr-defined", "A")]
    current = [MypyErrorRecord("a.py", 10, 2, "return-value", "A")]
    result = compare_records(baseline_records=baseline, current_records=current)
    assert result["new_errors"] == 1
    assert result["retired_errors"] == 1

def test_check_fails_when_baseline_missing(tmp_path: Path, capsys) -> None:
    exit_code = check_mypy_baseline.main(["--baseline", str(tmp_path / "missing.json"), "--current-output-file", str(tmp_path / "unused.txt")])
    out = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert out["status"] == STATUS_MISSING


def test_check_fails_when_baseline_invalid(tmp_path: Path, capsys) -> None:
    baseline = tmp_path / "baseline.json"
    current = tmp_path / "current.txt"
    baseline.write_text('{"schema_version": 1, "digest": "bad", "errors": [], "total_error_count": 0, "affected_file_count": 0, "per_file_counts": {}}\n', encoding="utf-8")
    current.write_text("", encoding="utf-8")
    exit_code = check_mypy_baseline.main(["--baseline", str(baseline), "--current-output-file", str(current)])
    out = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert out["status"] == STATUS_INVALID


@pytest.mark.parametrize("raw", ["mypy 1.20.2 (compiled: yes)", "mypy 1.20.2 (compiled: no)", "mypy 1.20.2"])
def test_semantic_version_normalizes_build_annotations(raw: str) -> None:
    assert normalize_mypy_version(raw) == CANONICAL_MYPY_VERSION


@pytest.mark.parametrize("observed", ["1.18.2", "1.21.0"])
def test_checker_rejects_noncanonical_version_before_comparison(monkeypatch, tmp_path: Path, capsys, observed: str) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(manifest_to_text(build_manifest(records=[])), encoding="utf-8")
    monkeypatch.setattr(check_mypy_baseline, "_mypy_version", lambda: observed)
    monkeypatch.setattr(check_mypy_baseline, "_run_command", lambda command: pytest.fail("comparison must not run"))
    assert check_mypy_baseline.main(["--baseline", str(baseline)]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "mypy_baseline_toolchain_mismatch"
    assert result["expected_mypy_version"] == CANONICAL_MYPY_VERSION


def test_canonical_command_disables_site_packages_and_is_nonincremental() -> None:
    assert "--no-site-packages" in DEFAULT_MYPY_COMMAND
    assert "--no-incremental" in DEFAULT_MYPY_COMMAND
    assert DEFAULT_MYPY_COMMAND[DEFAULT_MYPY_COMMAND.index("--config-file") + 1] == "pyproject.toml"


def test_ambient_python_and_mypy_paths_are_sanitized() -> None:
    source = {"PATH": "/bin", "MYPYPATH": "/stubs", "PYTHONPATH": "/packages", "PYTHONHOME": "/other", "MYPY_CONFIG_FILE": "/other.ini", "MYPY_CACHE_DIR": "/cache"}
    first = sanitized_mypy_environment(source)
    second = sanitized_mypy_environment({**source, "MYPYPATH": "/different", "PYTHONPATH": "/different"})
    assert first == second
    assert all(key not in first for key in ("MYPYPATH", "PYTHONPATH", "PYTHONHOME", "MYPY_CONFIG_FILE", "MYPY_CACHE_DIR"))
    assert first["PYTHONNOUSERSITE"] == "1"


def test_unrelated_visible_stub_packages_cannot_change_type_resolution_posture(tmp_path: Path) -> None:
    one = tmp_path / "one"; two = tmp_path / "two"
    one.mkdir(); two.mkdir()
    (one / "unrelated.pyi").write_text("value: int\n", encoding="utf-8")
    (two / "unrelated.pyi").write_text("value: str\n", encoding="utf-8")
    assert sanitized_mypy_environment({**os.environ, "MYPYPATH": str(one), "PYTHONPATH": str(one)}) == sanitized_mypy_environment({**os.environ, "MYPYPATH": str(two), "PYTHONPATH": str(two)})


def test_manifest_rejects_other_contract_and_digest_tampering(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    manifest = build_manifest(records=[])
    manifest["toolchain_contract"]["site_packages_enabled"] = True
    baseline.write_text(manifest_to_text(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="baseline/toolchain incompatibility"):
        load_manifest(baseline)
    manifest = build_manifest(records=[])
    manifest["toolchain_contract_digest"] = "0" * 64
    baseline.write_text(manifest_to_text(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="contract digest"):
        load_manifest(baseline)


def test_canonical_version_is_accepted_before_matching(monkeypatch, tmp_path: Path, capsys) -> None:
    output = tmp_path / "current.txt"; output.write_text("", encoding="utf-8")
    baseline = tmp_path / "baseline.json"; baseline.write_text(manifest_to_text(build_manifest(records=[])), encoding="utf-8")
    monkeypatch.setattr(check_mypy_baseline, "_mypy_version", lambda: CANONICAL_MYPY_VERSION)
    assert check_mypy_baseline.main(["--baseline", str(baseline), "--current-output-file", str(output)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "mypy_baseline_clean"


def test_explicit_baseline_refresh_updates_records_and_digest(tmp_path: Path) -> None:
    output_file = tmp_path / "mypy.txt"
    baseline = tmp_path / "baseline.json"
    output_file.write_text("a.py:1: error: A [misc]\n", encoding="utf-8")
    assert build_mypy_baseline.main(["--mypy-output-file", str(output_file), "--output", str(baseline)]) == 0
    first = load_manifest(baseline)
    output_file.write_text("a.py:1: error: B [misc]\n", encoding="utf-8")
    assert build_mypy_baseline.main(["--mypy-output-file", str(output_file), "--output", str(baseline)]) == 0
    second = load_manifest(baseline)
    assert first["digest"] != second["digest"]
    assert second["errors"][0]["message"] == "B"


def test_reviewer_summary_is_compact_and_deterministic(tmp_path: Path, capsys) -> None:
    output_file = tmp_path / "mypy.txt"
    baseline = tmp_path / "baseline.json"
    output_file.write_text("a.py:1: error: A [misc]\n", encoding="utf-8")
    build_mypy_baseline.main(["--mypy-output-file", str(output_file), "--output", str(baseline)])
    capsys.readouterr()
    exit_code = check_mypy_baseline.main(["--baseline", str(baseline), "--current-output-file", str(output_file)])
    summary = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert list(summary) == sorted(summary)
    assert summary["status"] == STATUS_MATCHES
    assert summary["matched_existing_errors"] == 1


def test_targeted_typed_surface_command_remains_documented() -> None:
    docs = Path("docs/architecture/mypy_baseline_ratchet.md").read_text(encoding="utf-8")
    for token in WORKSPACE_TYPED_SURFACE_COMMAND.split():
        assert token in docs


def test_reviewer_index_links_are_updated() -> None:
    index = Path("docs/index.md").read_text(encoding="utf-8")
    quickstart = Path("docs/REVIEWER_QUICKSTART.md").read_text(encoding="utf-8")
    assert "mypy_baseline_ratchet.md" in index
    assert "mypy_baseline_ratchet.md" in quickstart
