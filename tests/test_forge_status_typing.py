from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts import forge_status

pytestmark = pytest.mark.no_legacy_skip


def test_exit_code_treats_malformed_provenance_as_missing() -> None:
    assert forge_status._exit_code(
        {
            "provenance": {
                "integrity_status": "not-an-object",
                "attestation_snapshot": [],
            }
        }
    ) == 3


def test_audit_continuation_handles_malformed_recovery_state() -> None:
    view = forge_status._audit_continuation_view({"recovery_state": "not-an-object"})

    assert view["history_state"] == "unknown"
    assert view["reanchor_checkpoint"] is False


def test_script_entrypoint_resolves_package_imports() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [sys.executable, "scripts/forge_status.py", "--help"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "--repo-root" in completed.stdout
