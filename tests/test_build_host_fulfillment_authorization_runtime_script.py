from pathlib import Path
import subprocess, sys
import pytest

pytestmark = pytest.mark.no_legacy_skip

def test_cli_shebang_and_help_direct():
    p=Path('scripts/build_host_fulfillment_authorization_runtime.py')
    assert p.read_bytes().startswith(b'#!/usr/bin/env python3\n')
    assert subprocess.run([str(p),'--help'], text=True, stdout=subprocess.PIPE).returncode == 0
    assert subprocess.run([sys.executable,str(p),'--help'], text=True, stdout=subprocess.PIPE).returncode == 0
