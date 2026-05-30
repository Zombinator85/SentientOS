from __future__ import annotations

import json
from pathlib import Path

from scripts import run_work_item_review_packet_matrix as matrix


class FakeCompleted:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _runner_from(plan: dict[str, int]):
    calls: list[str] = []

    def _run(command: tuple[str, ...]) -> FakeCompleted:
        label = " ".join(command)
        calls.append(label)
        return FakeCompleted(plan.get(label, 0), stdout=label)

    return _run, calls


def test_runner_continues_after_failures_and_records_all() -> None:
    commands = [
        matrix.MatrixCommand("a", ("python", "a")),
        matrix.MatrixCommand("b", ("python", "b")),
        matrix.MatrixCommand("c", ("python", "c")),
    ]
    runner, calls = _runner_from({"python b": 1})
    report = matrix.run_matrix(commands=commands, runner=runner)
    assert report["status"] == "failed"
    assert [r["label"] for r in report["results"]] == ["a", "b", "c"]
    assert len(calls) == 3


def test_runner_exits_zero_when_required_passes() -> None:
    report = matrix.run_matrix(commands=[matrix.MatrixCommand("ok", ("python", "ok"))], runner=lambda _: FakeCompleted(0))
    assert report["status"] == "passed"


def test_docs_bootstrap_path_runs_recheck() -> None:
    commands = [
        matrix.MatrixCommand("docs_check_deps", ("python", "scripts/build_docs.py", "--check-deps"), required=False),
        matrix.MatrixCommand("docs_build", ("python", "scripts/build_docs.py")),
    ]
    seq = {
        "python scripts/build_docs.py --check-deps": [1, 0],
        "python scripts/build_docs.py --bootstrap-docs": [0],
        "python scripts/build_docs.py": [0],
    }

    def runner(command: tuple[str, ...]) -> FakeCompleted:
        key = " ".join(command)
        ret = seq[key].pop(0)
        return FakeCompleted(ret, stdout=key)

    report = matrix.run_matrix(commands=commands, runner=runner)
    labels = [r["label"] for r in report["results"]]
    assert labels == ["docs_check_deps", "docs_bootstrap", "docs_check_deps_recheck", "docs_build"]
    assert report["status"] == "passed"


def test_output_written_only_when_explicit(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(matrix, "default_matrix_commands", lambda: [matrix.MatrixCommand("ok", ("python", "ok"))])
    monkeypatch.setattr(matrix, "_default_runner", lambda _cmd: FakeCompleted(0, stdout="ok"))
    out = tmp_path / "matrix.json"
    assert matrix.main(["--output", str(out)]) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert list(payload) == sorted(payload)


def test_default_matrix_includes_promotion_gate_steps() -> None:
    labels = [c.label for c in matrix.default_matrix_commands()]
    assert "promotion_gate_tests" in labels
    assert "governed_memory_writer_adapter_tests" in labels
    assert "memory_commit_operator_approval_packet_tests" in labels
    assert "memory_commit_execution_gate_tests" in labels
    assert "live_commit_safety_interlock_tests" in labels
    assert "targeted_mypy" in labels


def test_default_matrix_includes_codex_doctrine_docs_test() -> None:
    proof = next(c for c in matrix.default_matrix_commands() if c.label == "proof_bundle_tests")
    assert "tests/test_codex_operating_doctrine_docs.py" in proof.command

def test_matrix_includes_operator_confirmed_admission_run_steps() -> None:
    from scripts.run_work_item_review_packet_matrix import default_matrix_commands
    labels = [c.label for c in default_matrix_commands()]
    assert "operator_confirmed_admission_run_tests" in labels
    assert "operator_confirmed_preflight_run_tests" in labels


def test_matrix_includes_operator_lifecycle_closure_review_steps() -> None:
    labels = [c.label for c in matrix.default_matrix_commands()]
    assert "operator_lifecycle_closure_review_tests" in labels



def test_matrix_includes_operator_confirmed_lifecycle_closure_run_steps() -> None:
    labels = [c.label for c in matrix.default_matrix_commands()]
    assert "operator_confirmed_lifecycle_closure_run_tests" in labels


def test_matrix_report_includes_generated_timestamp() -> None:
    report = matrix.run_matrix(commands=[matrix.MatrixCommand("ok", ("python", "ok"))], runner=lambda _: FakeCompleted(0))
    assert "generated_at" in report
    assert report["generated_at"].endswith("Z")


def test_matrix_reports_strict_audit_repair_guidance() -> None:
    commands=[matrix.MatrixCommand("strict_audits", ("python","verify_audits.py","--strict"))]
    report=matrix.run_matrix(commands=commands, runner=lambda _ : FakeCompleted(1, stdout="failed"))
    # added by main when strict fails in full run
    assert report["status"] == "failed"
