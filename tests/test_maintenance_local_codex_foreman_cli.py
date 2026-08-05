import json, subprocess, sys, os, pytest
from pathlib import Path
from tests.local_codex_foreman_fixtures import *
pytestmark=pytest.mark.no_legacy_skip
def write_bundle(tmp_path, mode='success'):
    repo,sha=make_repo(tmp_path); fake=make_fake_cli(tmp_path,mode); cfg=make_config(tmp_path,repo,fake,mode); lease=make_lease(sha); sess=make_session(lease); art=tmp_path/'art'; art.mkdir(); req=make_request(lease,art)
    cp=tmp_path/'cfg.json'; cp.write_text(json.dumps(cfg.to_dict())); lp=tmp_path/'lease.json'; lp.write_text(json.dumps(lease)); sp=tmp_path/'sess.json'; sp.write_text(json.dumps(sess)); rp=tmp_path/'req.json'; rp.write_text(json.dumps(req)); return cp,lp,rp,sp,art
def call(cmd,*args): return subprocess.run([sys.executable,'scripts/maintenance_local_codex_foreman.py',cmd,*args],cwd=Path.cwd(),text=True,capture_output=True)
def test_cli_probe_prepare_run_inspect_round_trip(tmp_path):
    cp,lp,rp,sp,art=write_bundle(tmp_path); base=['--foreman-configuration',str(cp),'--lease',str(lp),'--request',str(rp),'--session',str(sp),'--instruction-artifact-root',str(art)]; assert call('probe','--foreman-configuration',str(cp)).returncode==0; assert call('prepare',*base).returncode==0; r=call('run',*base); assert r.returncode==0; assert call('inspect',*base).returncode==0
def test_cli_resume_cancel_and_failure_classifications(tmp_path):
    cp,lp,rp,sp,art=write_bundle(tmp_path,'auth'); base=['--foreman-configuration',str(cp),'--lease',str(lp),'--request',str(rp),'--session',str(sp),'--instruction-artifact-root',str(art)]; assert call('run',*base).returncode!=0; assert call('cancel',*base).returncode==0
def test_cli_invalid_authority_or_configuration_returns_nonzero(tmp_path):
    bad=tmp_path/'bad.json'; bad.write_text('{}'); assert call('probe','--foreman-configuration',str(bad)).returncode!=0
