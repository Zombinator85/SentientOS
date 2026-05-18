from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.no_legacy_skip

from scripts import run_workspace_change_set_transaction as cli


def test_requires_workspace_root_and_target(capsys):
    with pytest.raises(SystemExit):
        cli.main([])


def test_dry_run_writes_no_targets(tmp_path, capsys):
    code = cli.main(['--workspace-root', str(tmp_path), '--target', 'demo.txt=hello', '--dry-run', '--summary'])
    out = capsys.readouterr().out
    assert code == 0
    assert 'dry-run' in out
    assert not (tmp_path / 'demo.txt').exists()


def test_default_guarded_mode_executes_and_builds_ledger_posture(tmp_path, capsys):
    code = cli.main(['--workspace-root', str(tmp_path), '--target', 'demo.txt=hello', '--target', 'docs.txt=docs', '--summary'])
    out = capsys.readouterr().out
    assert code == 0
    assert (tmp_path / 'demo.txt').read_text() == 'hello'
    assert 'ledger_status: workspace_change_set_execution_closed_after_execute' in out
    assert 'general_filesystem_access_performed: false' in out


def test_rollback_after_execute_removes_created_targets(tmp_path, capsys):
    code = cli.main(['--workspace-root', str(tmp_path), '--target', 'demo.txt=hello', '--rollback-after-execute', '--summary'])
    assert code == 0
    assert not (tmp_path / 'demo.txt').exists()
    assert 'closed_after_rollback' in capsys.readouterr().out


def test_ledger_output_writes_one_explicit_artifact(tmp_path):
    output = tmp_path / 'ledger.json'
    code = cli.main(['--workspace-root', str(tmp_path), '--target', 'demo.txt=hello', '--ledger-output', str(output)])
    assert code == 0
    assert output.exists()
    payload = json.loads(output.read_text())
    assert payload['explicit_ledger_artifact_only'] is True
    assert payload['host_mutation_performed'] is False
    assert (tmp_path / 'demo.txt').exists()


def test_unsafe_target_path_rejected(tmp_path):
    code = cli.main(['--workspace-root', str(tmp_path), '--target', '../escape.txt=bad', '--summary'])
    assert code == 2
    assert not (tmp_path.parent / 'escape.txt').exists()
