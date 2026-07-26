from __future__ import annotations
import pytest
from typing import Any
from scripts.build_host_local_diagnostic_execution_source_runtime import main

pytestmark = pytest.mark.no_legacy_skip

def test_help(capsys: Any) -> None:
    assert main([])==0
    assert "evaluate" in capsys.readouterr().out

def test_invalid_bundle_is_nonzero(tmp_path: Any) -> None:
    assert main(["validate-bundle","--bundle-root",str(tmp_path/"missing")])==1
