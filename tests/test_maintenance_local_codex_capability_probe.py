import pytest
from sentientos.maintenance_local_codex_foreman import probe_local_codex_cli
from tests.local_codex_foreman_fixtures import *
pytestmark=pytest.mark.no_legacy_skip
def test_probe_binds_version_help_and_executable_identity(tmp_path):
    repo,sha=make_repo(tmp_path); cfg=make_config(tmp_path,repo,make_fake_cli(tmp_path)); p=probe_local_codex_cli(cfg); assert p['status']=='capability_probe_ready' and p['version_digest'] and p['exec_help_digest'] and p['executable_digest']
def test_probe_rejects_missing_required_exec_capability(tmp_path):
    repo,sha=make_repo(tmp_path); fake=tmp_path/'bad.py'; fake.write_text('#!/usr/bin/env python3\nimport sys\nprint("bad")\n'); fake.chmod(0o755); cfg=make_config(tmp_path,repo,fake); assert probe_local_codex_cli(cfg)['status']=='foreman_cli_incompatible'
def test_probe_rejects_dangerous_or_obsolete_flags(tmp_path):
    repo,sha=make_repo(tmp_path); cfg=make_config(tmp_path,repo,make_fake_cli(tmp_path)); assert probe_local_codex_cli(cfg,['--full-auto'])['status']=='foreman_cli_incompatible'
