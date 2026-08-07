from __future__ import annotations
import json, subprocess
from pathlib import Path
from sentientos import maintenance_candidate as candidates
from sentientos import maintenance_loop_watchdog as watchdog
from sentientos import maintenance_task_authority_lease as authority
from sentientos.maintenance_local_codex_foreman import EFFECT_AUTHORITIES, LocalCodexForemanConfig
from tests.local_codex_foreman_fixtures import make_fake_cli

NOW='2026-08-06T00:00:00Z'

def setup(tmp_path:Path, mode:str='success', validation_expectations=None, closed_loop=False, process_real_health=False):
    repo=tmp_path/'repo'; repo.mkdir(); subprocess.run(['git','init'],cwd=repo,check=True,capture_output=True)
    subprocess.run(['git','config','user.email','a@b.c'],cwd=repo,check=True); subprocess.run(['git','config','user.name','T'],cwd=repo,check=True)
    if process_real_health:
        archive = subprocess.run(
            ['git', '-c', 'filter.lfs.required=false', '-c', 'filter.lfs.smudge=cat',
             'archive', '--format=tar', 'HEAD'], check=True, capture_output=True,
        ).stdout
        subprocess.run(['tar', '-xf', '-'], cwd=repo, input=archive, check=True)
        (repo/'tests'/'conftest.py').unlink()
        subprocess.run(['rm', '-rf', str(repo/'glow'/'test_runs')], check=True)
        subprocess.run(['rm', '-rf', str(repo/'escrow')], check=True)
        (repo/'.git'/'info'/'exclude').write_text('glow/test_runs/\n')
        (repo/'tests'/'test_health_target.py').write_text(
            'def test_allowed_text():\n    assert False, "repair test_health_target.py"\n'
        )
        dist_info = repo/'sentientos-1.2.0.dist-info'
        dist_info.mkdir()
        (dist_info/'METADATA').write_text('Metadata-Version: 2.1\nName: sentientos\nVersion: 1.2.0\n')
        (dist_info/'direct_url.json').write_text(json.dumps({
            'url': repo.as_uri(), 'dir_info': {'editable': True},
        }))
        tracked = ['.']
    else:
        (repo/'allowed.txt').write_text('base\n')
        scripts = repo/'scripts'; scripts.mkdir()
        (scripts/'maintenance_loop_watchdog.py').write_bytes(Path('scripts/maintenance_loop_watchdog.py').read_bytes())
        tracked = ['allowed.txt','scripts/maintenance_loop_watchdog.py']
    subprocess.run(['git','add',*tracked],cwd=repo,check=True); subprocess.run(['git','commit','-m','base'],cwd=repo,check=True,capture_output=True)
    sha=subprocess.run(['git','rev-parse','HEAD'],cwd=repo,text=True,capture_output=True,check=True).stdout.strip()
    roots={n:tmp_path/n for n in ('state','workspace','scratch','inbox','codex_home')}
    for root in roots.values(): root.mkdir(mode=0o700)
    fake=make_fake_cli(tmp_path,mode)
    auth=['implementation_agent_session',*sorted(EFFECT_AUTHORITIES)]
    if closed_loop: auth += ['repository_commit','remote_repository_read','remote_ref_publish']
    target_path = 'tests/test_health_target.py' if process_real_health else 'allowed.txt'
    allowed_kinds = ['code', 'test_failure'] if process_real_health else ['code']
    candidate=candidates.adapt_explicit_candidate({'source_reference':'watchdog-test','base_repository_sha':sha,'objective':'Change allowed.txt deterministically','bounded_description':'Change only allowed.txt','candidate_kind':'code','declared_subject_paths':[target_path],'declared_validation_expectations':validation_expectations or ['git_diff_check'],'evidence_references':['operator:test'],'requested_authority_classes':auth,'declared_constraints':['bounded'],'estimated_file_count':1,'estimated_changed_line_count':10,'estimated_implementation_seconds':10,'estimated_validation_seconds':10},base_repository_sha=sha).to_dict()
    (roots['inbox']/'candidate.json').write_text(json.dumps(candidate,sort_keys=True))
    selector={'repository_base_sha':sha,'allowed_path_prefixes':[target_path],'forbidden_path_patterns':['.git/**'],'available_authority_classes':auth,'maximum_file_count':2,'maximum_estimated_changed_lines':20,'maximum_implementation_seconds':30,'maximum_validation_seconds':30,'allowed_candidate_kinds':allowed_kinds}
    grant=authority.seal_grant({'grant_id':'grant','operator_reference':'operator:test','approval_reference':'approval:test','repository_identity':'repo','allowed_base_sha':sha,'allowed_base_sha_rule':'exact','allowed_candidate_kinds':allowed_kinds,'allowed_path_prefixes':[target_path],'forbidden_path_patterns':['.git/**'],'allowed_authority_classes':auth,'maximum_file_count':2,'maximum_changed_line_count':20,'maximum_implementation_seconds':30,'maximum_validation_seconds':30,'maximum_wall_clock_seconds':3600,'maximum_attempts':2,'maximum_corrective_retries':1,'not_before':'2026-01-01T00:00:00Z','expires_at':'2027-01-01T00:00:00Z','grant_generation':'g1','explicit_constraints':['bounded'],'landing_terms':({'publication_mode':'fast_forward_base_ref','remote_name':'origin','base_ref':'refs/heads/main','head_ref_prefix':'sentientos/maintenance','commit_title':'[codex:sentientos] test closed loop','commit_identity_reference':'codex'} if closed_loop else {})})
    remote = None
    if closed_loop:
        remote=tmp_path/'remote.git'; subprocess.run(['git','init','--bare',str(remote)],check=True,capture_output=True)
        if process_real_health:
            subprocess.run(['git', 'config', 'lfs.allowincompletepush', 'true'], cwd=repo, check=True)
            subprocess.run(['git', 'config', 'filter.lfs.required', 'false'], cwd=repo, check=True)
            subprocess.run(['git', 'config', 'filter.lfs.smudge', 'cat'], cwd=repo, check=True)
        subprocess.run(['git','branch','-M','main'],cwd=repo,check=True); subprocess.run(['git','remote','add','origin',str(remote)],cwd=repo,check=True); subprocess.run(['git','push','-u','origin','main'],cwd=repo,check=True,capture_output=True)
    fc=LocalCodexForemanConfig(configuration_id='watchdog-test',repository_identity='repo',repository_root=repo,external_workspace_root=roots['workspace'],external_state_root=roots['state'],codex_executable=fake,git_executable=Path('/usr/bin/git'),codex_home=roots['codex_home'],environment_name_allowlist=('FAKE_CODEX_CONTENT','FAKE_CODEX_CORRECTIVE_CONTENT','FAKE_CODEX_MODE','FAKE_CODEX_TARGET'),process_timeout_seconds=30.0 if process_real_health else 2.0)
    cfg={'schema_version':watchdog.CONFIG_SCHEMA,'repository_root':str(repo),'state_root':str(roots['state']),'workspace_root':str(roots['workspace']),'scratch_root':str(roots['scratch']),'candidate_inbox_roots':[str(roots['inbox'])],'standing_grant':grant,'selector_policy':selector,'foreman_policy':fc.to_dict(),'validation_policy':{},'landing_policy':({'policy_id':'p','repository_identity':'repo','canonical_repository_root':str(repo),'external_state_root':str(roots['state']),'git_executable':'git','publication_client_executable':str(Path('tests/fixtures/fake_publication_client.py').resolve()),'commit_author_name':'Codex','commit_author_email':'codex@example.test','commit_committer_name':'Codex','commit_committer_email':'codex@example.test','commit_identity_reference':'codex','maximum_publication_attempts':1,'environment_name_allowlist':['PATH','HOME','TMPDIR','FAKE_PR_ROOT','FAKE_HEAD_SHA','FAKE_PR_MODE']} if closed_loop else {}),'maximum_active_tasks':1,'maximum_actions':10,'maximum_wall_clock_seconds':30,'publication_retry_backoff_seconds':0,'base_sha':sha,'tracked_base_ref':('refs/remotes/origin/main' if closed_loop else 'HEAD')}
    return watchdog.validate_config(cfg),roots,repo
