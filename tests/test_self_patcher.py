"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from importlib import reload

from control_plane import AuthorizationRecord, Decision, ReasonCode, RequestType
import notification
import pytest
import self_patcher
import task_executor


def _auth() -> AuthorizationRecord:
    return AuthorizationRecord(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="tester",
        intent_hash="i",
        context_hash="c",
        policy_version="v1",
        decision=Decision.ALLOW,
        reason=ReasonCode.OK,
        timestamp=0.0,
        metadata=None,
    )


def _token() -> task_executor.AdmissionToken:
    provenance = task_executor.AuthorityProvenance(
        authority_source="tester",
        authority_scope="self-heal",
        authority_context_id="ctx",
        authority_reason="test",
    )
    fingerprint = task_executor.RequestFingerprint("f" * 64)
    return task_executor.AdmissionToken(
        task_id="self-heal-task",
        provenance=provenance,
        request_fingerprint=fingerprint,
    )


def test_apply_requires_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    reload(notification)
    reload(self_patcher)
    with pytest.raises(Exception):
        self_patcher.apply_patch("note", admission_token=None, authorization=None)  # type: ignore[arg-type]


def test_propose_does_not_mutate_memory(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    reload(notification)
    reload(self_patcher)
    patch = self_patcher.propose_patch("note")
    assert patch["status"] == "proposed"
    assert not any(self_patcher.mm.RAW_PATH.glob("*"))


def test_admitted_apply_and_rollback(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    reload(notification)
    reload(self_patcher)
    token = _token()
    auth = _auth()
    applied = self_patcher.apply_patch("note", admission_token=token, authorization=auth)
    patches = self_patcher.list_patches()
    ids = [x["id"] for x in patches]
    assert applied["id"] in ids
    assert applied["status"] == "applied"
    assert applied["request_fingerprint"] == token.request_fingerprint.value
    assert self_patcher.rollback_patch(applied["id"])
    patches = self_patcher.list_patches()
    for p in patches:
        if p["id"] == applied["id"]:
            assert p["rolled_back"]

    import final_approval

    monkeypatch.setattr(final_approval, "request_approval", lambda d: True)
    assert self_patcher.approve_patch(applied["id"])
    patches = self_patcher.list_patches()
    assert any(x["id"] == applied["id"] and x.get("approved") for x in patches)

    events = notification.list_events(3)
    assert any(e["event"] == "patch_rolled_back" for e in events)
    assert any(e["event"] == "patch_approved" for e in events)


def test_reject_patch(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    reload(notification)
    reload(self_patcher)
    token = _token()
    auth = _auth()
    applied = self_patcher.apply_patch("note", admission_token=token, authorization=auth)
    assert self_patcher.reject_patch(applied["id"])
    patches = self_patcher.list_patches()
    assert any(x["id"] == applied["id"] and x.get("rejected") for x in patches)
    events = notification.list_events(2)
    assert any(e["event"] == "patch_rejected" for e in events)


def test_patch_requires_approval(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    reload(notification)
    reload(self_patcher)
    token = _token()
    auth = _auth()
    applied = self_patcher.apply_patch("note", admission_token=token, authorization=auth)
    import final_approval

    monkeypatch.setattr(final_approval, "request_approval", lambda d: False)
    assert not self_patcher.approve_patch(applied["id"])
    patches = self_patcher.list_patches()
    assert not any(x.get("approved") for x in patches if x["id"] == applied["id"])
