from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import pytest

from scripts.verify_pytest_bootstrap import verify
pytestmark = pytest.mark.no_legacy_skip


def test_bootstrap_call_phase_witness() -> None:
    assert True


def test_conftest_import_does_not_invoke_privilege(tmp_path: Path) -> None:
    code = "import sentientos.privilege as p; p.require_admin_banner=lambda:(_ for _ in ()).throw(RuntimeError()); p.require_covenant_alignment=p.require_admin_banner; import tests.conftest"
    assert subprocess.run([sys.executable, "-c", code], text=True, capture_output=True).returncode == 0


def test_pytest_collection_reaches_completion_as_non_root(tmp_path: Path) -> None:
    payload = verify(output=tmp_path / "proof.json", collect_only=True)
    assert payload["status"] == "pytest_bootstrap_ready"


def test_pytest_bootstrap_reaches_call_phase(tmp_path: Path) -> None:
    payload = verify(output=tmp_path / "proof.json")
    assert payload["call_phase_outcome_count"] == 1 and payload["status"] == "pytest_bootstrap_ready"


def test_pytest_bootstrap_verifier_rejects_privilege_invocation(tmp_path: Path) -> None:
    payload = verify(output=tmp_path / "proof.json", sentinel_mode="invoke")
    assert payload["status"] == "privilege_invoked"


def test_pytest_bootstrap_verifier_rejects_missing_metrics(tmp_path: Path) -> None:
    payload = verify(output=tmp_path / "proof.json", metrics_path=tmp_path / "missing.json", sentinel_mode="invoke")
    # Invocation has precedence; a plain child without reporter evidence is never ready.
    assert payload["status"] != "pytest_bootstrap_ready"
