from sentientos.codex_finalize_landing import *

def test_ready_for_pr_metadata():
    req=CodexFinalizeLandingRequest(title='x', intended_commit_title='x', matrix_json_path='/tmp/m.json', focused_test_commands=('t',))
    res=evaluate_finalize_landing(req,(CodexFinalizeLandingCommandResult('focused_tests','t',0),),())
    assert res.decision.status=='ready_for_pr_metadata'

def test_missing_focused_tests_blocks():
    req=CodexFinalizeLandingRequest(title='x', intended_commit_title='x', matrix_json_path='/tmp/m.json')
    res=evaluate_finalize_landing(req,(),())
    assert res.decision.status!='ready_for_pr_metadata'
