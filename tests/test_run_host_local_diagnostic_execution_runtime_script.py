from __future__ import annotations
import pytest
import subprocess, sys
from pathlib import Path


pytestmark = pytest.mark.no_legacy_skip

def test_help_is_read_only(tmp_path: Path) -> None:
    script=Path(__file__).parents[1]/"scripts"/"run_host_local_diagnostic_execution_runtime.py"
    result=subprocess.run([sys.executable,str(script),"--help"],cwd=tmp_path,text=True,capture_output=True,check=False)
    assert result.returncode == 0
    assert "preflight" in result.stdout
    assert not any(path.name.startswith(("host_local_diagnostic", "execution")) for path in tmp_path.iterdir())
