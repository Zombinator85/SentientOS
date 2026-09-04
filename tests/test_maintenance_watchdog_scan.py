import pytest
pytestmark=pytest.mark.no_legacy_skip
from pathlib import Path
from sentientos import maintenance_loop_watchdog as w


def config(tmp_path: Path):
    roots={n:tmp_path/n for n in ('state','workspace','scratch','inbox')}
    for p in roots.values(): p.mkdir()
    return {'schema_version':w.CONFIG_SCHEMA,'repository_root':str(Path.cwd()),'state_root':str(roots['state']),'workspace_root':str(roots['workspace']),'scratch_root':str(roots['scratch']),'candidate_inbox_roots':[str(roots['inbox'])],'standing_grant':{'grant_id':'operator'},'selector_policy':{},'foreman_policy':{},'validation_policy':{},'implementation_backend':'local_codex','commissioned_local_activation':None,'commissioned_local_activation_digest':None,'landing_policy':{},'maximum_active_tasks':1,'maximum_actions':3,'maximum_wall_clock_seconds':10,'publication_retry_backoff_seconds':60,'base_sha':'a'*40,'tracked_base_ref':'refs/heads/main'}


def test_scan_is_deterministic_and_digest_bound(tmp_path):
    cfg=config(tmp_path)
    assert w.scan(cfg,evaluation_time='2026-01-01T00:00:00Z') == w.scan(cfg,evaluation_time='2026-01-01T00:00:00Z')
