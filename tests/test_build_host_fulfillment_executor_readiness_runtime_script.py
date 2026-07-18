from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
import pytest
pytestmark = pytest.mark.no_legacy_skip

def test_help_works_both_executable_and_python():
    p=Path('scripts/build_host_fulfillment_executor_readiness_runtime.py')
    r=subprocess.run([str(p),'--help'], text=True, capture_output=True, check=True)
    assert 'evaluate' in r.stdout and 'never executes' in r.stdout
    r2=subprocess.run([sys.executable,str(p),'--help'], text=True, capture_output=True, check=True)
    assert 'render-markdown' in r2.stdout

def test_loose_json_fails_closed(tmp_path):
    loose=tmp_path/'loose.json'; loose.write_text(json.dumps({'consumption_receipt':{'receipt_id':'r'}}))
    r=subprocess.run([sys.executable,'scripts/build_host_fulfillment_executor_readiness_runtime.py','evaluate','--consumption-runtime-json',str(loose),'--output-root',str(tmp_path/'out')], text=True, capture_output=True)
    assert r.returncode != 0 and 'loose JSON rejected' in r.stderr
