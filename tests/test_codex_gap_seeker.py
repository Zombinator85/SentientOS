"""Tests for the GapSeeker automation pipeline."""

from __future__ import annotations

from pathlib import Path

from codex.gap_seeker import (
    CoverageReader,
    GapAmender,
    GapReporter,
    GapResolutionError,
    GapSeeker,
    GapSignal,
    NarratorLink,
    RepoScanner,
)
from sentientos.codex_healer import RecoveryLedger


def _build_amender(ledger: RecoveryLedger, recorder: list) -> tuple[GapAmender, NarratorLink]:
    narrator = NarratorLink(ledger, on_record=recorder.append)

    def spec_handler(gap: GapSignal) -> dict[str, object]:
        recorder.append(("spec", gap.kind))
        return {"proposal": f"fix::{gap.kind}"}

    def genesis_handler(gap: GapSignal) -> dict[str, object]:
        recorder.append(("genesis", gap.kind))
        return {"scaffold": f"tests::{gap.kind}"}

    return GapAmender(spec_handler=spec_handler, genesis_handler=genesis_handler, narrator=narrator), narrator


def test_repo_scanner_is_lazy(tmp_path: Path) -> None:
    sample = tmp_path / "integrity_daemon.py"
    sample.write_text("""
def guard():
    # TODO: tighten guard rails
    raise NotImplementedError("pending")
""".strip(), encoding="utf-8")

    scanner = RepoScanner(tmp_path)
    iterator = scanner.iter_gaps()
    first = next(iterator)
    assert first.kind == "todo"
    second = next(iterator)
    assert second.kind == "unimplemented"


def test_gap_seeker_routes_repo_gaps_to_spec(tmp_path: Path) -> None:
    module_path = tmp_path / "integrity_daemon.py"
    module_path.write_text("""
def guard():
    # TODO: tighten guard rails
    raise NotImplementedError("pending")
""".strip(), encoding="utf-8")

    ledger = RecoveryLedger()
    record_log: list = []
    amender, narrator = _build_amender(ledger, record_log)

    seeker = GapSeeker(
        RepoScanner(tmp_path),
        CoverageReader(),
        GapReporter(),
        amender,
    )

    results = seeker.run_once()
    assert all(result.action == "spec" for result in results)
    assert {result.status for result in results} == {"amendment"}
    assert any(isinstance(entry, tuple) and entry[0] == "spec" for entry in record_log)
    summary = narrator.summary()
    assert "IntegrityDaemon" in summary
    assert ledger.entries


def test_gap_seeker_routes_missing_tests_to_genesis(tmp_path: Path) -> None:
    ledger = RecoveryLedger()
    record_log: list = []
    amender, narrator = _build_amender(ledger, record_log)

    coverage_report = {
        "files": {
            str(tmp_path / "integrity_daemon.py"): {"missing_lines": [12, 13, 14]},
        }
    }

    seeker = GapSeeker(
        RepoScanner(tmp_path),
        CoverageReader(),
        GapReporter(),
        amender,
    )

    results = seeker.run_once(coverage_report=coverage_report)
    assert len(results) == 1
    assert results[0].action == "genesis"
    assert results[0].status == "scaffolded"
    assert any(entry[0] == "genesis" for entry in record_log if isinstance(entry, tuple))
    summary = narrator.summary()
    assert "missing test" in summary
    assert ledger.entries[0]["status"] == "scaffolded"


def test_gap_seeker_handles_mypy_errors(tmp_path: Path) -> None:
    (tmp_path / "updater.py").write_text("pass", encoding="utf-8")

    ledger = RecoveryLedger()
    record_log: list = []
    amender, narrator = _build_amender(ledger, record_log)

    mypy_output = f"{tmp_path / 'updater.py'}:7: error: incompatible types"

    seeker = GapSeeker(
        RepoScanner(tmp_path),
        CoverageReader(),
        GapReporter(),
        amender,
    )

    results = seeker.run_once(mypy_output=mypy_output)
    assert len(results) == 1
    assert results[0].gap.kind == "type_error"
    assert results[0].action == "spec"
    assert ledger.entries[0]["status"] == "amendment"


def test_unfillable_gaps_are_logged(tmp_path: Path) -> None:
    ledger = RecoveryLedger()
    narrator = NarratorLink(ledger)

    gap = GapSignal(
        path=tmp_path / "updater.py",
        line=9,
        description="TODO: handle retries",
        severity="medium",
        kind="todo",
        source="repo",
    )

    def spec_handler(_: GapSignal) -> dict[str, object]:
        raise GapResolutionError("Blocked by external dependency")

    def genesis_handler(_: GapSignal) -> dict[str, object]:
        return {"scaffold": "noop"}

    amender = GapAmender(
        spec_handler=spec_handler,
        genesis_handler=genesis_handler,
        narrator=narrator,
    )

    resolutions = amender.process([gap])
    assert resolutions[0].status == "unfillable"
    assert ledger.entries[0]["status"] == "unfillable"
    assert narrator.summary() == "No gap closures recorded."

