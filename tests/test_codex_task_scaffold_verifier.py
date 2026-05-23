from sentientos.codex_task_scaffold import CodexTaskScaffoldRequest, build_codex_task_scaffold
from sentientos.codex_task_scaffold_verifier import verify_codex_task_scaffold_payload


def test_verifier_accepts_whole_system_payload() -> None:
    req = CodexTaskScaffoldRequest(task_name="x", task_goal="y", subsystem_kind="z", commit_title="[codex:developer] ok")
    payload = build_codex_task_scaffold(req).to_dict()
    verified = verify_codex_task_scaffold_payload(payload)
    assert verified.status == "codex_task_scaffold_verifier_ready"


def test_verifier_flags_missing_contract() -> None:
    req = CodexTaskScaffoldRequest(task_name="x", task_goal="y", subsystem_kind="z", commit_title="bad")
    payload = build_codex_task_scaffold(req).to_dict()
    payload["scaffold"]["final_report_contract"] = []
    verified = verify_codex_task_scaffold_payload(payload)
    assert verified.status == "codex_task_scaffold_verifier_incomplete"
    assert verified.missing_report_contract_items
