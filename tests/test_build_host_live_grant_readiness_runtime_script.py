from __future__ import annotations
import pytest
pytestmark = pytest.mark.no_legacy_skip
from scripts import build_host_live_grant_readiness_runtime as cli

def test_plan_and_loose_evaluate_fails_closed(capsys):
    assert cli.main(['plan','--summary']) == 0
    assert 'host_live_grant_readiness_runtime' in capsys.readouterr().out
    assert cli.main(['evaluate','--summary']) == 2
    assert 'typed_controlled_authorization_runtime_input_required' in capsys.readouterr().out

def test_render_markdown_no_authority(capsys):
    assert cli.main(['render-markdown']) == 0
    out = capsys.readouterr().out
    assert 'No local grant issued' in out
