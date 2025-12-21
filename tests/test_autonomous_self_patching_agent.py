from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from control_plane import RequestType, admit_request
from control_plane.records import AuthorizationError
import task_executor

pytestmark = pytest.mark.no_legacy_skip


def _reload_agent(monkeypatch: pytest.MonkeyPatch, log_path: Path):
    monkeypatch.setenv("SELF_PATCH_LOG", str(log_path))
    import autonomous_self_patching_agent as agent

    return importlib.reload(agent)


def _authority(task_id: str):
    auth = admit_request(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash="intent",
        context_hash="ctx",
        policy_version="wet-run",
    ).record
    provenance = task_executor.AuthorityProvenance(
        authority_source="wet-run",
        authority_scope="self-heal",
        authority_context_id="simulated-node",
        authority_reason="test",
    )
    token = task_executor.AdmissionToken(
        task_id=task_id,
        provenance=provenance,
        request_fingerprint=task_executor.RequestFingerprint("f" * 64),
    )
    return auth, token


def test_apply_requires_authority(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    log_path = tmp_path / "self_patch.jsonl"
    agent = _reload_agent(monkeypatch, log_path)

    with pytest.raises(AuthorizationError):
        agent.apply(1)

    assert not log_path.exists() or log_path.read_text(encoding="utf-8") == ""


def test_apply_with_authority_records(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    log_path = tmp_path / "self_patch.jsonl"
    agent = _reload_agent(monkeypatch, log_path)
    auth, token = _authority("patch-task")

    entry = agent.apply(7, admission_token=token, authorization=auth)

    assert entry["status"] == "applied"
    assert log_path.exists()
    contents = log_path.read_text(encoding="utf-8").splitlines()
    assert any('"patch_id": 7' in line for line in contents)
