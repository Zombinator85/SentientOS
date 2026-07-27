from __future__ import annotations
import pytest
import json, shutil, subprocess, sys
from pathlib import Path

from sentientos.host_local_diagnostic_execution_runtime import HostLocalDiagnosticExecutionRuntimeCoordinator
from tests.host_local_diagnostic_execution_fixture import NOW, build_diagnostic_execution_fixture


pytestmark = pytest.mark.no_legacy_skip

def test_help_is_read_only(tmp_path: Path) -> None:
    script=Path(__file__).parents[1]/"scripts"/"run_host_local_diagnostic_execution_runtime.py"
    result=subprocess.run([sys.executable,str(script),"--help"],cwd=tmp_path,text=True,capture_output=True,check=False)
    assert result.returncode == 0
    assert "preflight" in result.stdout
    assert not any(path.name.startswith(("host_local_diagnostic", "execution")) for path in tmp_path.iterdir())


def test_cli_executes_valid_transaction_and_validates_historical_bundle(tmp_path: Path) -> None:
    fixture = build_diagnostic_execution_fixture(tmp_path)
    snapshot = tmp_path / "snapshot.json"; snapshot.write_text(json.dumps(fixture.snapshot, sort_keys=True))
    verification = tmp_path / "verification.json"; verification.write_text(json.dumps(fixture.verification, sort_keys=True))
    preflight = HostLocalDiagnosticExecutionRuntimeCoordinator().preflight(execution_source_bundle_root=fixture.source_bundle, expected_source_bundle_digest=fixture.source_digest, current_snapshot=fixture.snapshot, current_verification=fixture.verification, execution_time=NOW)
    challenge = preflight.records["confirmation_challenge"]
    script = Path(__file__).parents[1] / "scripts" / "run_host_local_diagnostic_execution_runtime.py"
    output = tmp_path / "executions"
    command = [sys.executable, str(script), "execute", "--execution-source-bundle-root", str(fixture.source_bundle), "--expected-source-bundle-digest", fixture.source_digest, "--current-snapshot-json", str(snapshot), "--current-verification-json", str(verification), "--execution-time", NOW, "--output-root", str(output), "--confirm-local-diagnostic-write", "--confirm-source-bundle-digest", fixture.source_digest, "--confirm-effect-output-dir", str(fixture.target), "--confirmation-challenge-digest", challenge["confirmation_challenge_digest"], "--correlation-id", "cli-proof"]
    executed = subprocess.run(command, cwd=tmp_path, text=True, capture_output=True, check=False)
    assert executed.returncode == 0, executed.stderr
    result = json.loads(executed.stdout)
    assert result["status"] == "host_local_diagnostic_execution_completed" and result["runner_call_count"] == 1
    shutil_source = fixture.source_bundle.parent
    shutil.rmtree(shutil_source)
    shutil.rmtree(fixture.target)
    validated = subprocess.run([sys.executable, str(script), "validate-bundle", "--bundle-root", result["bundle_root"]], cwd=tmp_path, text=True, capture_output=True, check=False)
    assert validated.returncode == 0, validated.stderr
    historical = json.loads(validated.stdout)
    assert historical["status"] == "host_local_diagnostic_execution_completed" and historical["replayed"] is True
