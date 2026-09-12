from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from sentientos import maintenance_candidate
from sentientos import maintenance_commit_publication as landing
from sentientos import maintenance_task_authority_lease as authority
from tests.maintenance_commit_publication_fixtures import NOW, setup

pytestmark = pytest.mark.no_legacy_skip
MODE = landing.LOCAL_FAST_FORWARD_MODE


def _local(tmp_path: Path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    repo, worktree, state, lease, validation, policy = setup(tmp_path, MODE)
    subprocess.run(["git", "branch", "-m", "main"], cwd=repo, check=True)
    built = landing.create_commit_and_enqueue(state_root=state, repository_root=repo,
        worktree_root=worktree, lease=lease, validation_result=validation,
        landing_policy=policy, evaluation_time=NOW)
    return repo, worktree, state, lease, validation, policy, built


def _publish(values):
    repo, _, state, lease, _, policy, built = values
    return landing.publish_one_maintenance_request(state_root=state, repository_root=repo,
        lease=lease, landing_policy=policy,
        publication_id=built["publication_request"]["publication_id"], evaluation_time=NOW)


def test_authority_vocabularies_are_exact_and_candidates_are_not_upgraded():
    assert "local_repository_base_advance" in maintenance_candidate.AUTHORITY_CLASSES
    assert maintenance_candidate.AUTHORITY_CLASSES == authority.AUTHORITY_CLASSES
    candidate = maintenance_candidate.adapt_explicit_candidate({"candidate_id":"c", "objective":"x",
        "base_repository_sha":"a"*40, "declared_subject_paths":["sentientos/x.py"],
        "requested_authority_classes":["repository_commit"], "declared_validation_expectations":["pytest"],
        "estimated_file_count":1, "estimated_changed_line_count":1,
        "estimated_implementation_seconds":1, "estimated_validation_seconds":1})
    assert "local_repository_base_advance" not in candidate.requested_authority_classes


def test_local_mode_requires_only_exact_local_authorities(tmp_path):
    values=_local(tmp_path); lease=values[3]
    assert set(lease["authority_classes"]) == {"repository_commit", "local_repository_base_advance"}
    for missing in ("repository_commit", "local_repository_base_advance"):
        altered=dict(lease); altered["authority_classes"]=[a for a in lease["authority_classes"] if a != missing]
        altered["lease_digest"]=authority._seal(altered,"lease_digest")
        with pytest.raises(landing.MaintenanceLandingError, match="missing_authority"):
            landing.build_commit_plan(state_root=values[2],repository_root=values[0],worktree_root=values[1],lease=altered,validation_result=values[4],landing_policy=values[5],evaluation_time=NOW)


def test_real_offline_absorption_updates_exact_main_and_checkout(tmp_path, monkeypatch):
    values=_local(tmp_path); repo, _, _, _, _, _, built=values
    assert not subprocess.run(["git","remote"],cwd=repo,capture_output=True,text=True,check=True).stdout
    original=landing._git
    def guarded(git, root, args, **kwargs):
        assert args[0] not in {"fetch","pull","push","ls-remote"}
        return original(git,root,args,**kwargs)
    monkeypatch.setattr(landing,"_git",guarded)
    monkeypatch.setattr(landing,"_publish_pr",lambda *a,**k: pytest.fail("publication client invoked"))
    result=_publish(values); commit=built["commit_result"]["commit_sha"]
    assert result["terminal_status"] == "publication_succeeded"
    assert result["remote_operations"] == 0 and result["network_performed"] is False
    assert result["runtime_restart_performed"] is result["runtime_adoption_performed"] is False
    assert subprocess.run(["git","rev-parse","HEAD","refs/heads/main"],cwd=repo,text=True,capture_output=True,check=True).stdout.split()==[commit,commit]
    assert (repo/"a.txt").read_text()=="two\n"
    assert not subprocess.run(["git","status","--porcelain"],cwd=repo,text=True,capture_output=True,check=True).stdout
    replay=_publish(values)
    assert replay["publication_result_digest"] == result["publication_result_digest"]


@pytest.mark.parametrize("dirty", ["tracked", "index", "untracked"])
def test_dirty_canonical_checkout_blocks_before_ref_mutation(tmp_path, dirty):
    values=_local(tmp_path); repo=values[0]; parent=values[4]["base_sha"]
    if dirty=="tracked": (repo/"a.txt").write_text("dirty\n")
    elif dirty=="index": (repo/"a.txt").write_text("dirty\n"); subprocess.run(["git","add","a.txt"],cwd=repo,check=True)
    else: (repo/"unknown").write_text("x")
    result=_publish(values)
    assert result["terminal_status"] == "publication_integrity_failed"
    assert subprocess.run(["git","rev-parse","refs/heads/main"],cwd=repo,text=True,capture_output=True,check=True).stdout.strip()==parent


def test_detached_or_wrong_branch_and_moved_base_fail_closed(tmp_path):
    for case in ("detached","other","moved"):
        values=_local(tmp_path/case); repo=values[0]; parent=values[4]["base_sha"]
        if case=="detached": subprocess.run(["git","checkout","--detach",parent],cwd=repo,check=True,capture_output=True)
        elif case=="other": subprocess.run(["git","checkout","-b","other"],cwd=repo,check=True,capture_output=True)
        else:
            subprocess.run(["git","commit","--allow-empty","-m","move"],cwd=repo,check=True,capture_output=True)
        result=_publish(values)
        assert result["terminal_status"] == "publication_integrity_failed"
        if case!="moved": assert subprocess.run(["git","rev-parse","refs/heads/main"],cwd=repo,text=True,capture_output=True,check=True).stdout.strip()==parent
