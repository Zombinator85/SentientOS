import subprocess, pytest
from pathlib import Path
from sentientos.maintenance_local_codex_foreman import prepare_worktree
from tests.local_codex_foreman_fixtures import *
pytestmark=pytest.mark.no_legacy_skip
def test_prepare_creates_detached_clean_worktree_at_exact_base(tmp_path):
    repo,sha=make_repo(tmp_path); lease=make_lease(sha); cfg=make_config(tmp_path,repo,make_fake_cli(tmp_path)); w=prepare_worktree(cfg,lease,'s1'); assert w['initial_head']==sha and w['creation_status']=='created' and not subprocess.run(['git','branch','--show-current'],cwd=w['worktree_root'],text=True,capture_output=True).stdout.strip()
def test_prepare_exact_retry_reuses_same_clean_worktree(tmp_path):
    repo,sha=make_repo(tmp_path); lease=make_lease(sha); cfg=make_config(tmp_path,repo,make_fake_cli(tmp_path)); prepare_worktree(cfg,lease,'s1'); assert prepare_worktree(cfg,lease,'s1')['creation_status']=='reused'
def test_dirty_mismatched_or_symlinked_worktree_is_rejected(tmp_path):
    repo,sha=make_repo(tmp_path); lease=make_lease(sha); cfg=make_config(tmp_path,repo,make_fake_cli(tmp_path)); w=prepare_worktree(cfg,lease,'s1'); Path(w['worktree_root'],'x').write_text('dirty');
    with pytest.raises(ValueError): prepare_worktree(cfg,lease,'s1')
def test_foreman_does_not_create_branch_or_commit(tmp_path):
    repo,sha=make_repo(tmp_path); lease=make_lease(sha); cfg=make_config(tmp_path,repo,make_fake_cli(tmp_path)); w=prepare_worktree(cfg,lease,'s1'); assert subprocess.run(['git','rev-parse','HEAD'],cwd=w['worktree_root'],text=True,capture_output=True).stdout.strip()==sha
