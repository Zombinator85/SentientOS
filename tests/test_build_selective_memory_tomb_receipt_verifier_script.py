from __future__ import annotations

import json
import pytest
import subprocess
import sys
from pathlib import Path

pytestmark = pytest.mark.no_legacy_skip

SCRIPT = "scripts/build_selective_memory_tomb_receipt_verifier.py"
FIXTURE = "tests/fixtures/selective_memory_tomb_receipt_verifier/valid_tomb_after_distillation_observed_receipt.json"
BLOCKED = "tests/fixtures/selective_memory_tomb_receipt_verifier/missing_distillation_packet_blocked.json"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, SCRIPT, *args], check=False, text=True, capture_output=True)


def test_cli_build_default_and_validate() -> None:
    built = _run("build-default")
    assert built.returncode == 0
    assert json.loads(built.stdout)["policy"]["schema_version"] == "selective-memory-tomb-receipt-verifier.v1"
    validated = _run("validate")
    assert validated.returncode == 0
    assert json.loads(validated.stdout)["ok"] is True


def test_cli_evaluate_summarize_and_output(tmp_path: Path) -> None:
    evaluated = _run("evaluate", "--input", FIXTURE)
    assert evaluated.returncode == 0
    payload = json.loads(evaluated.stdout)
    assert payload["status"] == "selective_memory_tomb_receipt_verifier_ready"
    output = tmp_path / "summary.json"
    summarized = _run("summarize", "--input", FIXTURE, "--output", str(output), "--summary")
    assert summarized.returncode == 0
    summary = json.loads(output.read_text(encoding="utf-8"))
    assert summary["summary_counts"]["claim_count"] == 1


def test_cli_inspect_fixture() -> None:
    inspected = _run("inspect-fixture", "--fixture-name", "valid_tomb_noop_receipt.json")
    assert inspected.returncode == 0
    assert json.loads(inspected.stdout)["tomb_claim"]["tomb_claim_type"] == "tomb_noop_receipt"


def test_cli_exits_nonzero_for_blocked() -> None:
    blocked = _run("evaluate", "--input", BLOCKED)
    assert blocked.returncode == 1
    assert "blocked_missing_distillation_packet" in blocked.stdout
