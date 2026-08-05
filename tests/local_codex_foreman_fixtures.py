from __future__ import annotations
import json, os, stat, subprocess, sys, textwrap
from pathlib import Path
from sentientos.maintenance_local_codex_foreman import LocalCodexForemanConfig, EFFECT_AUTHORITIES
from sentientos import maintenance_task_journal as journal

def make_fake_cli(tmp_path:Path, mode='success')->Path:
    p=tmp_path/'fake_codex.py'
    code = r"""#!/usr/bin/env python3
import json, os, sys, time, subprocess, signal
from pathlib import Path
if '--version' in sys.argv:
    print('codex-cli 9.9.9-fake'); raise SystemExit(0)
if sys.argv[:3]==[sys.argv[0],'exec','resume'] and '--help' in sys.argv:
    print('Usage: codex exec resume SESSION --jsonl --cwd --sandbox --final-message-file --final-output-schema --color; stdin prompt session thread resume') ; raise SystemExit(0)
if sys.argv[:2]==[sys.argv[0],'exec'] and '--help' in sys.argv:
    print('Usage: codex exec --jsonl --cwd --sandbox --final-message-file --final-output-schema --color; stdin prompt session thread final message schema workspace-write') ; raise SystemExit(0)
mode=os.environ.get('FAKE_CODEX_MODE','success'); data=sys.stdin.buffer.read()
if mode=='auth': print('authentication unavailable', file=sys.stderr); raise SystemExit(42)
if mode=='malformed': print('{bad', flush=True); raise SystemExit(0)
tid='thread-ok'
if 'resume' in sys.argv: tid=sys.argv[sys.argv.index('resume')+1]
print(json.dumps({'type':'thread.started','thread_id':tid}), flush=True)
print(json.dumps({'type':'turn.started','thread_id':tid}), flush=True)
if mode=='conflict': print(json.dumps({'type':'turn.completed','thread_id':'other'}), flush=True); raise SystemExit(0)
if mode=='timeout':
    subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])
    time.sleep(60)
if mode=='interrupt': raise SystemExit(9)
if mode=='out_of_scope': Path('outside.txt').write_text('bad\n')
if mode=='many_files':
    Path('allowed.txt').write_text('ok\n'); Path('extra.txt').write_text('x\n')
if mode=='many_lines': Path('allowed.txt').write_text('\n'.join(str(i) for i in range(50)))
if mode not in ('nochange','blocked','failed','out_of_scope','many_files','many_lines'):
    Path('allowed.txt').write_text('implemented\n')
status='implemented'
if mode=='blocked': status='blocked'
if mode=='failed': status='failed'
final={'status':status,'summary':'done','reported_changed_paths':['allowed.txt'],'reported_commands':[],'reported_tests':[],'blocker_codes':[],'recommended_validation':['pytest'], 'continuation_note':''}
if '--final-message-file' in sys.argv: Path(sys.argv[sys.argv.index('--final-message-file')+1]).write_text(json.dumps(final))
print(json.dumps({'type':'item.completed','thread_id':tid,'message':'progress'}), flush=True)
print(json.dumps({'type':'turn.completed','thread_id':tid,'usage':{'input_tokens':1}}), flush=True)
"""
    p.write_text(code)
    p.chmod(0o755); return p

def make_repo(tmp_path:Path)->tuple[Path,str]:
    tmp_path.mkdir(parents=True, exist_ok=True); r=tmp_path/'repo'; r.mkdir(); subprocess.run(['git','init'],cwd=r,check=True,capture_output=True); subprocess.run(['git','config','user.email','a@b.c'],cwd=r,check=True); subprocess.run(['git','config','user.name','T'],cwd=r,check=True)
    (r/'allowed.txt').write_text('base\n'); subprocess.run(['git','add','allowed.txt'],cwd=r,check=True); subprocess.run(['git','commit','-m','base'],cwd=r,check=True,capture_output=True); sha=subprocess.run(['git','rev-parse','HEAD'],cwd=r,text=True,capture_output=True,check=True).stdout.strip(); return r,sha

def make_lease(sha:str)->dict:
    l={'schema_version':'sentientos.maintenance_task_authority_lease:v1','lease_id':'lease1','lease_digest':'','task_id':'task1','candidate_id':'cand1','candidate_revision_digest':'sha256:c','canonical_candidate_digest':'sha256:cc','candidate_set_digest':'sha256:cs','selection_digest':'sha256:ss','selector_policy_digest':'sha256:p','operator_grant_id':'grant','operator_grant_digest':'sha256:g','repository_identity':'repo','base_sha':sha,'objective_digest':'sha256:o','admitted_scope_digest':'sha256:s','admitted_subject_paths':['allowed.txt'],'forbidden_path_patterns':['.git/**'],'authority_classes':['implementation_agent_session',*sorted(EFFECT_AUTHORITIES)],'validation_expectations':['pytest'],'maximum_file_count':1,'maximum_changed_line_count':10,'maximum_implementation_seconds':10,'maximum_validation_seconds':0,'maximum_wall_clock_seconds':1000,'maximum_attempts':1,'maximum_corrective_retries':0,'not_before':'2026','expires_at':'9999','grant_generation':'g','issued_at':'2026','lease_status':'active','reason_codes':[]}
    l['lease_digest']=journal.sha256_digest({k:v for k,v in l.items() if k!='lease_digest'}); return l

def make_session(lease): return {'session_id':'session1','attempt_id':'attempt1','attempt_ordinal':1,'corrective_retry_ordinal':0,'task_id':lease['task_id']}
def make_request(lease, root:Path):
    (root/'instruction.txt').write_text('change allowed.txt')
    raw=(root/'instruction.txt').read_bytes(); import hashlib
    return {'requested_authority_classes':['implementation_agent_session',*sorted(EFFECT_AUTHORITIES)],'external_instruction_artifact_reference':'instruction.txt','external_instruction_artifact_digest':'sha256:'+hashlib.sha256(raw).hexdigest(),'explicit_constraints':[]}
def make_config(tmp_path:Path, repo:Path, fake:Path, mode='success'):
    auth=tmp_path/'codex_home'; auth.mkdir()
    c=LocalCodexForemanConfig(configuration_id='cfg',repository_identity='repo',repository_root=repo,external_workspace_root=tmp_path/'workspaces',external_state_root=tmp_path/'state',codex_executable=fake,git_executable=Path('/usr/bin/git') if Path('/usr/bin/git').exists() else Path('git'),codex_home=auth, environment_name_allowlist=('FAKE_CODEX_MODE',), process_timeout_seconds=1.0)
    os.environ['FAKE_CODEX_MODE']=mode
    return c
