from __future__ import annotations
import json, os, subprocess
from pathlib import Path
import pytest

pytestmark = pytest.mark.no_legacy_skip
from sentientos.codex_landing_evidence_binding import *

def git(repo: Path, *args: str):
    return subprocess.run(['git', *args], cwd=repo, check=True, text=True, capture_output=True).stdout.strip()

def repo(tmp_path: Path) -> Path:
    r=tmp_path/'r'; r.mkdir(); git(r,'init'); git(r,'config','user.email','a@b.c'); git(r,'config','user.name','A'); (r/'a.txt').write_text('base'); git(r,'add','.'); git(r,'commit','-m','base'); return r

def test_workspace_binding_deterministic_and_byte_invalidation(tmp_path: Path):
    r=repo(tmp_path); m=tmp_path/'m.json'; m.write_text('{"status":"passed","required_failure_count":0}')
    (r/'a.txt').write_text('one')
    b1=create_workspace_binding(r,intended_paths=['a.txt'],intended_commit_title='title',focused_test_commands=['python -m scripts.run_tests -q tests/x.py'],targeted_mypy_commands=['mypy x'],matrix_json_path=m)
    b2=create_workspace_binding(r,intended_paths=['./a.txt'],intended_commit_title='title',focused_test_commands=['python -m scripts.run_tests -q tests/x.py'],targeted_mypy_commands=['mypy x'],matrix_json_path=m)
    assert b1.changed_path_manifest_digest == b2.changed_path_manifest_digest
    (r/'a.txt').write_text('two')
    b3=create_workspace_binding(r,intended_paths=['a.txt'],intended_commit_title='title',matrix_json_path=m)
    assert b3.changed_path_manifest_digest != b1.changed_path_manifest_digest

def test_rejects_duplicate_traversal_git_unknown_runtime(tmp_path: Path):
    r=repo(tmp_path); (r/'a.txt').write_text('x')
    with pytest.raises(ValueError, match='canonical_duplicate_path'):
        create_workspace_binding(r,intended_paths=['a.txt','./a.txt'],intended_commit_title='t')
    with pytest.raises(ValueError, match='path_outside_repository'):
        create_workspace_binding(r,intended_paths=['../x'],intended_commit_title='t')
    with pytest.raises(ValueError, match='git_path_rejected'):
        create_workspace_binding(r,intended_paths=['.git/config'],intended_commit_title='t')
    (r/'b.txt').write_text('unknown')
    with pytest.raises(ValueError, match='unknown_dirty_paths'):
        create_workspace_binding(r,intended_paths=['a.txt'],intended_commit_title='t')
    with pytest.raises(ValueError, match='generated_runtime_path_rejected'):
        create_workspace_binding(r,intended_paths=['sentientos_data/vow/x.json'],intended_commit_title='t')

def test_symlink_deleted_and_commit_verification(tmp_path: Path):
    r=repo(tmp_path); m=tmp_path/'m.json'; m.write_text('{"status":"passed","required_failure_count":0}')
    (r/'link').symlink_to('a.txt'); os.remove(r/'a.txt')
    wb=create_workspace_binding(r,intended_paths=['link'],deleted_paths=['a.txt'],intended_commit_title='change',matrix_json_path=m)
    assert any(f.posture=='symlink' for f in wb.files) and any(f.posture=='deleted' for f in wb.files)
    git(r,'add','-A'); git(r,'commit','-m','change')
    cb=create_commit_binding(r,workspace_binding=wb,matrix_json_path=m)
    ok=verify_commit_matches_workspace(r, wb.to_dict(), cb.to_dict())
    assert ok.status=='landing_evidence_binding_ready'
    git(r,'commit','--allow-empty','-m','later')
    stale=verify_commit_matches_workspace(r, wb.to_dict(), cb.to_dict())
    assert 'current_head_changed_after_validation' in stale.reasons

def test_wrong_title_parent_matrix_and_runtime_root(tmp_path: Path):
    r=repo(tmp_path); m=tmp_path/'m.json'; m.write_text('{}'); (r/'a.txt').write_text('x')
    wb=create_workspace_binding(r,intended_paths=['a.txt'],intended_commit_title='wanted',matrix_json_path=m)
    git(r,'add','.'); git(r,'commit','-m','other')
    cb=create_commit_binding(r,workspace_binding=wb,matrix_json_path=m)
    res=verify_commit_matches_workspace(r, wb.to_dict(), cb.to_dict())
    assert 'commit_title_mismatch' in res.reasons
    m.write_text('{"changed":true}')
    cb2=create_commit_binding(r,workspace_binding=wb,matrix_json_path=m)
    assert 'matrix_digest_mismatch' in verify_commit_matches_workspace(r, wb.to_dict(), cb2.to_dict()).reasons
    with pytest.raises(ValueError, match='runtime_root_inside_workspace'):
        safe_runtime_roots(r, r/'tmp', 'id')

def test_body_binding_and_publication_classification(tmp_path: Path):
    body=tmp_path/'body.md'; body.write_text('### Motivation\n' + 'evidence '*100)
    art=tmp_path/'a.json'; art.write_text('{"ok":true}')
    commit={'head_sha':'h','tree_sha':'t','matrix_digest':'m'}
    side=create_body_binding('title', body, commit, {'artifact':str(art)}).to_dict()
    assert verify_body_binding('title', body, side, {'artifact':str(art)}).status=='pr_body_binding_ready'
    body.write_text(body.read_text()+'x')
    assert 'body_digest_mismatch' in verify_body_binding('title', body, side, {'artifact':str(art)}).reasons
    assert classify_publication_result({'title':'title','body':'...'}, {'title':'title'}).status=='publication_payload_echo_unverified'
    assert classify_publication_result({'pr_number':1,'url':'https://x'}, {}).status=='publication_identifier_observed'
    assert classify_publication_result({'repository':'r','base':'main','head_branch':'b','head_sha':'h'}, {'repository':'r','base':'main','head_branch':'b','head_sha':'h'}).status=='publication_head_binding_observed'
    assert classify_publication_result({'merged':True,'head_sha':'h'}, {'head_sha':'h'}).status=='publication_merge_observed'
    assert classify_publication_result({'head_sha':'bad'}, {'head_sha':'h'}).status=='publication_result_contradicted'
