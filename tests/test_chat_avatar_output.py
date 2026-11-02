from __future__ import annotations

import json
import time
import pytest

from avatar_state import AvatarStateEmitter
from control_plane import Decision, ReasonCode, RequestType
from control_plane.records import AuthorizationRecord
from control_plane.task_admission import AdmissionResponse
from sentientos.chat_avatar_output import ChatAvatarOutputController
from sentientos.control_api import require_authorization_for_request_types
from sentientos.local_model_authority import digest_payload
from speech_emitter import SpeechEmitter

pytestmark = pytest.mark.no_legacy_skip


class _AdmissionStub:
    def __init__(self, decisions: tuple[Decision, ...] = ()) -> None:
        self.decisions = iter(decisions)
        self.calls: list[dict[str, object]] = []

    def __call__(self, **kwargs: object) -> AdmissionResponse:
        request = dict(kwargs)
        self.calls.append(request)
        decision = next(self.decisions, Decision.ALLOW)
        reason = ReasonCode.OK if decision is Decision.ALLOW else ReasonCode.HUMAN_APPROVAL_REQUIRED
        record = AuthorizationRecord.create(
            request_type=request["request_type"],
            requester_id=str(request["requester_id"]),
            intent_hash=str(request["intent_hash"]),
            context_hash=str(request["context_hash"]),
            policy_version=str(request["policy_version"]),
            decision=decision, reason=reason,
            metadata=request.get("metadata"),
        )
        return AdmissionResponse(decision, reason, record)


def _controller(path, admission: _AdmissionStub, clock=lambda: 10.0):
    return ChatAvatarOutputController(
        SpeechEmitter(AvatarStateEmitter(path)), admission_provider=admission,
        monotonic_clock=clock,
    )


def test_chat_avatar_output_requires_session_grant_and_emits_visual_only_state(tmp_path) -> None:
    target = tmp_path / "avatar_state.json"
    admission = _AdmissionStub()
    output = _controller(target, admission)

    assert output.state("session-1")["enabled"] is False
    assert output.publish_response(session_id="session-1", turn_id="turn-1",
        text="answer", output_digest=digest_payload({"text":"answer"})) == {"status": "disabled"}
    assert not target.exists()

    grant = output.set_enabled("session-1", True)
    assert grant["enabled"] is True
    assert output.publish_response(session_id="other-session", turn_id="turn-0",
        text="isolation", output_digest=digest_payload({"text":"isolation"})) == {"status": "disabled"}
    emitted = output.publish_response(session_id="session-1", turn_id="turn-1",
        text="answer", output_digest=digest_payload({"text":"answer"}))
    assert emitted == {"status": "emitted", "phrase_truncated": False}
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["current_phrase"] == "answer"
    assert payload["motion"] == "nod"
    assert payload["speaking"] is False
    assert payload["phrase"]["muted"] is False
    assert payload["viseme_timeline"] == []
    assert payload["metadata"]["output_digest"] == digest_payload({"text":"answer"})
    assert payload["metadata"]["output_mode"] == "chat_response_visual_only"
    assert [call["request_type"] for call in admission.calls] == [
        RequestType.AVATAR_EMISSION, RequestType.AVATAR_EMISSION]
    assert admission.calls[0]["metadata"]["approval_method"] == "local_chat_ui"
    assert admission.calls[1]["metadata"]["approval_scope"] == "chat_response_visual_only"
    other_grant = output.set_enabled("other-session", True)
    assert other_grant["enabled"] is False
    assert other_grant["reason"] == "another_avatar_session_is_active"
    assert json.loads(target.read_text(encoding="utf-8"))["current_phrase"] == "answer"

    assert output.set_enabled("session-1", False)["state_cleared"] is True
    assert output.publish_response(session_id="session-1", turn_id="turn-2",
        text="later", output_digest=digest_payload({"text":"later"})) == {"status": "disabled"}
    cleared = json.loads(target.read_text(encoding="utf-8"))
    assert cleared["current_phrase"] == ""
    assert cleared["speaking"] is False
    assert len(admission.calls) == 3


def test_chat_avatar_output_denial_and_expiry_fail_closed(tmp_path) -> None:
    target = tmp_path / "avatar_state.json"
    denied = _controller(target, _AdmissionStub((Decision.DENY,)))
    result = denied.set_enabled("session-1", True)
    assert result["enabled"] is False
    assert result["reason"] == ReasonCode.HUMAN_APPROVAL_REQUIRED.value
    assert not target.exists()

    now = [0.0]
    expiring = _controller(target, _AdmissionStub(), clock=lambda: now[0])
    assert expiring.set_enabled("session-2", True)["enabled"] is True
    now[0] = expiring.GRANT_SECONDS
    assert expiring.state("session-2")["enabled"] is False
    assert expiring.publish_response(session_id="session-2", turn_id="turn-1",
        text="no", output_digest=digest_payload({"text":"no"})) == {"status": "disabled"}
    assert json.loads(target.read_text(encoding="utf-8"))["current_phrase"] == ""


def test_chat_avatar_output_rechecks_admission_for_each_turn(tmp_path) -> None:
    target = tmp_path / "avatar_state.json"
    output = _controller(target, _AdmissionStub((Decision.ALLOW, Decision.DENY)))
    assert output.set_enabled("session-1", True)["enabled"] is True
    rejected = output.publish_response(session_id="session-1", turn_id="turn-1",
        text="denied answer", output_digest=digest_payload({"text":"denied answer"}))
    assert rejected == {"status": "admission_denied", "reason": ReasonCode.HUMAN_APPROVAL_REQUIRED.value}
    assert not target.exists()
    with pytest.raises(ValueError, match="avatar_output_digest_invalid"):
        output.publish_response(session_id="session-1", turn_id="turn-2",
            text="invalid", output_digest="not-a-digest")
    output.close()


def test_workload_mode_update_is_admitted_and_preserves_current_caption(tmp_path) -> None:
    target = tmp_path / "avatar_state.json"
    admission = _AdmissionStub()
    output = _controller(target, admission)
    assert output.set_enabled("session-1", True)["enabled"] is True
    digest = digest_payload({"text": "answer"})
    assert output.publish_response(session_id="session-1", turn_id="turn-1",
        text="answer", output_digest=digest, workload_mode="normal")["status"] == "emitted"

    assert output.set_workload_mode("session-1", "gaming") == {
        "status": "updated", "workload_mode": "gaming"}
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["current_phrase"] == "answer"
    assert payload["metadata"]["workload_mode"] == "gaming"
    assert payload["metadata"]["output_digest"] == digest
    assert output.set_workload_mode("session-1", "gaming")["status"] == "unchanged"
    assert len(admission.calls) == 3
    assert admission.calls[2]["metadata"]["approval_method"] == "session_grant_workload_sync"
    assert admission.calls[1]["metadata"]["workload_mode"] == "normal"
    with pytest.raises(ValueError, match="avatar_output_workload_mode_invalid"):
        output.set_workload_mode("session-1", "automatic")
    output.close()


def test_denied_workload_mode_update_leaves_avatar_state_unchanged(tmp_path) -> None:
    target = tmp_path / "avatar_state.json"
    output = _controller(target, _AdmissionStub((Decision.ALLOW, Decision.ALLOW, Decision.DENY)))
    assert output.set_enabled("session-1", True)["enabled"] is True
    digest = digest_payload({"text": "answer"})
    assert output.publish_response(session_id="session-1", turn_id="turn-1",
        text="answer", output_digest=digest, workload_mode="normal")["status"] == "emitted"

    result = output.set_workload_mode("session-1", "gaming")
    assert result["status"] == "admission_denied"
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["current_phrase"] == "answer"
    assert payload["metadata"]["workload_mode"] == "normal"
    output.close()


def test_denied_clear_keeps_display_channel_reserved_until_it_is_cleared(tmp_path) -> None:
    target = tmp_path / "avatar_state.json"
    admission = _AdmissionStub((Decision.ALLOW, Decision.ALLOW, Decision.DENY,
                                Decision.DENY, Decision.ALLOW, Decision.ALLOW))
    output = _controller(target, admission)
    assert output.set_enabled("session-1", True)["enabled"] is True
    assert output.publish_response(session_id="session-1", turn_id="turn-1",
        text="visible", output_digest=digest_payload({"text": "visible"}))["status"] == "emitted"

    revoked = output.set_enabled("session-1", False)
    assert revoked["state_cleared"] is False
    assert output.state("session-1")["clear_pending"] is True
    blocked = output.set_enabled("session-2", True)
    assert blocked["enabled"] is False
    assert blocked["reason"] == "previous_avatar_state_clear_denied"
    assert json.loads(target.read_text(encoding="utf-8"))["current_phrase"] == "visible"

    assert output.set_enabled("session-1", True)["enabled"] is True
    assert json.loads(target.read_text(encoding="utf-8"))["current_phrase"] == ""
    output.close()


def test_repeated_enable_is_idempotent_and_shutdown_clears_output(tmp_path) -> None:
    target = tmp_path / "avatar_state.json"
    admission = _AdmissionStub()
    output = _controller(target, admission)
    assert output.set_enabled("session-1", True)["enabled"] is True
    assert output.set_enabled("session-1", True)["enabled"] is True
    assert len(admission.calls) == 1
    output.publish_response(session_id="session-1", turn_id="turn-1",
        text="visible", output_digest=digest_payload({"text": "visible"}))

    output.close()

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["current_phrase"] == ""
    assert payload["speaking"] is False
    assert output.state("session-1")["enabled"] is False


def test_avatar_authorization_accepts_lowercase_contract_name() -> None:
    authorization = AuthorizationRecord.create(
        request_type=RequestType.AVATAR_EMISSION, requester_id="bridge",
        intent_hash="intent", context_hash="context", policy_version="v1-static",
        decision=Decision.ALLOW, reason=ReasonCode.OK,
        metadata={"approved_by": "operator"},
    )
    assert require_authorization_for_request_types(
        authorization, allowed_request_types=("avatar_emission",)) is authorization


def test_speech_timing_updates_only_the_current_granted_turn(tmp_path) -> None:
    target = tmp_path / "avatar_state.json"
    admission = _AdmissionStub()
    output = _controller(target, admission)
    assert output.set_enabled("session-1", True)["enabled"] is True
    output.publish_response(session_id="session-1", turn_id="turn-1", text="Hello friend",
        output_digest=digest_payload({"text": "Hello friend"}))

    started = output.publish_speech_timing({"session_id": "session-1", "turn_id": "turn-1",
        "event": "speech_started", "started_at": time.time(),
        "elapsed_seconds": 0.0})
    word = output.publish_speech_timing({"session_id": "session-1", "turn_id": "turn-1",
        "event": "word_started", "word_index": 1, "char_start": 0,
        "char_length": 5, "elapsed_seconds": 0.12})
    assert started == {"status": "emitted", "speaking": True}
    assert word["status"] == "emitted"
    state = json.loads(target.read_text(encoding="utf-8"))
    timing = state["metadata"]["speech_timing"]
    assert timing["event"] == "word_started"
    assert timing["timing_quality"] == "backend_word_start"
    assert (timing["word_index"], timing["char_start"], timing["char_length"]) == (1, 0, 5)
    assert state["speaking"] is True
    assert output.publish_speech_timing({"session_id": "session-1", "turn_id": "stale",
        "event": "speech_finished"}) == {"status": "stale_or_ungranted"}

    finished = output.publish_speech_timing({"session_id": "session-1", "turn_id": "turn-1",
        "event": "speech_interrupted", "elapsed_seconds": 0.2})
    assert finished == {"status": "emitted", "speaking": False}
    state = json.loads(target.read_text(encoding="utf-8"))
    assert state["speaking"] is False
    assert state["metadata"]["speech_timing"]["event"] == "speech_interrupted"
