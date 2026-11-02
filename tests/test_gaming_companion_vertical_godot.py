from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from control_plane import Decision, ReasonCode
from control_plane.records import AuthorizationRecord
from control_plane.task_admission import AdmissionResponse
from sentientos.avatar_renderer_report_ingress import renderer_report_world_state_record
from sentientos.chat_avatar_output import ChatAvatarOutputController
from speech_emitter import SpeechEmitter
from avatar_state import AvatarStateEmitter
from godot_avatar_receiver import AvatarStateForwarder
from tests.test_chat_service_hardened_serving import Inference, service

pytestmark = pytest.mark.no_legacy_skip


def test_fixture_chat_reaches_real_godot_and_returns_unverified_renderer_evidence(tmp_path):
    godot = shutil.which("godot") or shutil.which("godot4")
    if godot is None:
        pytest.skip("Godot is not installed in this validation environment")

    def approve(**kwargs):
        record = AuthorizationRecord.create(
            request_type=kwargs["request_type"], requester_id=kwargs["requester_id"],
            intent_hash=kwargs["intent_hash"], context_hash=kwargs["context_hash"],
            policy_version=kwargs["policy_version"], decision=Decision.ALLOW,
            reason=ReasonCode.OK, metadata=kwargs["metadata"],
        )
        return AdmissionResponse(Decision.ALLOW, ReasonCode.OK, record)

    state_path = tmp_path / "avatar_state.json"
    avatar = ChatAvatarOutputController(
        SpeechEmitter(AvatarStateEmitter(state_path)), admission_provider=approve)
    app = service(tmp_path, Inference(), avatar)
    session_id = app.create_session()
    try:
        app.set_workload_mode("gaming")
        assert app.set_avatar_output_enabled(session_id, True)["enabled"] is True
        reply = app.chat("Quick check-in while I play", session_id=session_id)
        persisted = json.loads(state_path.read_text(encoding="utf-8"))
        assert persisted["current_phrase"] == reply.response
        assert persisted["metadata"]["workload_mode"] == "gaming"

        forwarded = AvatarStateForwarder(state_path)._read_state()
        assert forwarded is not None
        assert forwarded["workload_mode"] == "gaming"
        environment = dict(os.environ)
        environment.update({
            "XDG_CACHE_HOME": str(tmp_path / "cache"),
            "XDG_CONFIG_HOME": str(tmp_path / "config"),
            "XDG_DATA_HOME": str(tmp_path / "data"),
        })
        project = Path(__file__).resolve().parents[1] / "godot_avatar_demo"
        result = subprocess.run(
            [godot, "--headless", "--path", str(project), "--script",
             "res://tests/renderer_report_probe.gd", "--",
             json.dumps(forwarded, separators=(",", ":"), ensure_ascii=False)],
            capture_output=True, text=True, timeout=30, env=environment, check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "godot_renderer_report_probe_passed" in result.stdout
        assert "SCRIPT ERROR" not in result.stdout + result.stderr
        report_line = next(line for line in result.stdout.splitlines()
                           if line.startswith("sentientos_renderer_report_json:"))
        renderer_report = json.loads(report_line.split(":", 1)[1])
        assert renderer_report["session_id"] == session_id
        assert renderer_report["turn_id"] == persisted["metadata"]["turn_id"]
        assert renderer_report["output_digest"] == persisted["metadata"]["output_digest"]
        assert renderer_report["renderer_state"]["applied_render_cap_fps"] == 15

        record = renderer_report_world_state_record(renderer_report)
        assert record["effect_proven"] is False
        assert record["payload"]["observer_issuer_posture"] == "unverified_caller_assertion"
    finally:
        app.close_outputs()

    restarted = service(tmp_path, Inference())
    try:
        restored = restarted.sessions.load(session_id)
        assert restored["turns"][-1]["text"] == reply.response
        assert [turn["role"] for turn in restored["turns"]] == ["user", "assistant"]
    finally:
        restarted.close_outputs()
