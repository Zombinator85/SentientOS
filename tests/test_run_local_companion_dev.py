from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.no_legacy_skip


def test_screen_ocr_executable_path_is_converted_for_windows_edge():
    from scripts.run_local_companion_dev import _normalize_windows_edge_executable

    conversions = []
    def convert(path):
        conversions.append(path)
        return r"C:\Program Files\Tesseract-OCR\tesseract.exe"

    assert _normalize_windows_edge_executable(
        "/mnt/c/Program Files/Tesseract-OCR/tesseract.exe",
        convert_wsl_path=convert) == r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    assert conversions == [Path("/mnt/c/Program Files/Tesseract-OCR/tesseract.exe")]
    assert _normalize_windows_edge_executable(
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        convert_wsl_path=convert) == r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    assert _normalize_windows_edge_executable(
        "tesseract.exe", convert_wsl_path=convert) == "tesseract.exe"
    with pytest.raises(ValueError, match="screen_observation_ocr_windows_path_required"):
        _normalize_windows_edge_executable(
            "/usr/bin/tesseract", convert_wsl_path=convert)


def test_host_resource_log_exposes_timestamped_cpu_ram_gpu_and_vram():
    from scripts.run_local_companion_dev import _host_resource_log_payload

    evaluation = SimpleNamespace(
        snapshot=SimpleNamespace(
            cpu_utilization_percent=31.5,
            ram_utilization_percent=62.0,
            gpu_utilization_percent=84.0,
            vram_utilization_percent=81.25,
        ),
        epoch=SimpleNamespace(
            observed_at="2026-11-04T18:00:00+00:00",
            collectors_called=4,
            status_counts={"ok": 4},
        ),
        pressure_report=SimpleNamespace(pressure_labels=("nominal",)),
        no_effect_authority=True,
    )

    event = _host_resource_log_payload(evaluation, {
        "evaluation_id": "hre-test",
        "status": "ok",
    })

    assert event == {
        "event": "host_resource_observation",
        "evaluation_id": "hre-test",
        "status": "ok",
        "observed_at": "2026-11-04T18:00:00+00:00",
        "pressure_labels": ["nominal"],
        "collectors_called": 4,
        "collector_status_counts": {"ok": 4},
        "cpu_utilization_percent": 31.5,
        "ram_utilization_percent": 62.0,
        "gpu_utilization_percent": 84.0,
        "vram_utilization_percent": 81.25,
        "gpu_telemetry_available": True,
        "no_effect_authority": True,
        "host_mutation_performed": False,
    }


def test_host_resource_log_marks_missing_gpu_telemetry():
    from scripts.run_local_companion_dev import _host_resource_log_payload

    evaluation = SimpleNamespace(
        snapshot=SimpleNamespace(
            cpu_utilization_percent=None,
            ram_utilization_percent=None,
            gpu_utilization_percent=None,
            vram_utilization_percent=None,
        ),
        epoch=SimpleNamespace(
            observed_at="2026-11-04T18:00:00+00:00",
            collectors_called=3,
            status_counts={"ok": 2, "unavailable": 1},
        ),
        pressure_report=SimpleNamespace(pressure_labels=("telemetry_incomplete",)),
        no_effect_authority=True,
    )

    event = _host_resource_log_payload(evaluation, {
        "evaluation_id": "hre-missing-gpu",
        "status": "degraded",
    })

    assert event["gpu_telemetry_available"] is False
    assert event["cpu_utilization_percent"] is None
    assert event["ram_utilization_percent"] is None
    assert event["gpu_utilization_percent"] is None
    assert event["vram_utilization_percent"] is None
    assert event["host_mutation_performed"] is False


@pytest.mark.parametrize(("samples", "expected"), [
    ((), "deferred"),
    ((80.0,), "available"),
    ((85.0,), "deferred"),
    ((85.0, 83.0), "deferred"),
    ((85.0, 81.9), "available"),
    ((80.0, None), "deferred"),
])
def test_gaming_resource_pressure_guard_uses_fail_closed_hysteresis(samples, expected):
    from scripts.run_local_companion_dev import _GamingResourcePressureGuard

    guard = _GamingResourcePressureGuard()
    assert guard.is_blocked() is True
    state = guard.status()
    for index, sample in enumerate(samples):
        state = guard.observe(sample, f"2026-11-06T09:00:{index:02d}+00:00")
    assert state["admission_status"] == expected
    assert guard.is_blocked() is (expected == "deferred")
    if samples and samples[-1] is None:
        assert state["reason_code"] == "vram_telemetry_unavailable"


def test_gaming_resource_pressure_guard_blocks_after_observation_goes_stale(monkeypatch):
    import scripts.run_local_companion_dev as runner

    guard = runner._GamingResourcePressureGuard()
    guard.observe(80.0, "2026-11-06T09:00:00+00:00")
    observed_at = guard._last_observed_monotonic
    assert observed_at is not None
    monkeypatch.setattr(runner.time, "monotonic", lambda: observed_at + 46.0)

    state = guard.status()

    assert state["admission_status"] == "deferred"
    assert state["reason_code"] == "vram_telemetry_stale"


def test_gaming_resource_observation_releases_residency_when_gate_closes():
    from scripts.run_local_companion_dev import (
        _GamingResourcePressureGuard, _apply_gaming_resource_observation,
    )

    guard = _GamingResourcePressureGuard()
    releases = []
    release = lambda reason: releases.append(reason) or {"status": "released"}
    available = _apply_gaming_resource_observation(
        guard, 80.0, "2026-11-06T09:00:00+00:00", release)
    assert available["admission_status"] == "available"
    assert releases == []

    pressured = _apply_gaming_resource_observation(
        guard, 91.0, "2026-11-06T09:00:15+00:00", release)
    assert pressured["admission_status"] == "deferred"
    assert pressured["residency_release"] == {"status": "released"}
    assert releases == ["vram_pressure_observed"]

    _apply_gaming_resource_observation(
        guard, None, None, release)
    assert releases[-1] == "vram_telemetry_unavailable"


def test_gaming_resource_pressure_guard_rejects_invalid_percentages():
    from scripts.run_local_companion_dev import _GamingResourcePressureGuard

    guard = _GamingResourcePressureGuard()
    for invalid in (-0.1, 100.1, True, float("nan"), "90"):
        state = guard.observe(invalid, "2026-11-06T09:00:00+00:00")
        assert state["admission_status"] == "deferred"
        assert state["reason_code"] == "vram_telemetry_unavailable"


def test_gaming_preload_requires_additional_vram_headroom():
    from scripts.run_local_companion_dev import _GamingResourcePressureGuard

    guard = _GamingResourcePressureGuard()
    available = guard.observe(74.9, "2026-11-06T09:00:00+00:00")
    assert available["admission_status"] == "available"
    assert available["preload_admission_status"] == "available"
    assert available["preload_threshold_percent"] == 75.0

    warm_denied = guard.observe(75.0, "2026-11-06T09:00:15+00:00")
    assert warm_denied["admission_status"] == "available"
    assert warm_denied["preload_admission_status"] == "deferred"
    assert warm_denied["preload_reason_code"] == "preload_vram_headroom_insufficient"


def test_dev_sampler_stays_fresh_and_closes_during_blocked_inference(monkeypatch, tmp_path):
    import threading
    import time
    from datetime import datetime, timezone
    from sentientos.chat_service import DevelopmentLocalChatInference
    from sentientos.governed_local_model_invocation import LocalModelInvocationBudget
    import sentientos.host_resource_runtime as host_runtime
    import scripts.run_local_companion_dev as runner

    class FakeCoordinator:
        def __init__(self, **kwargs):
            self.plan = SimpleNamespace(
                budget=SimpleNamespace(total_deadline_seconds=0.05))
            self.cycles = 0

        def run_cycle(self, *, correlation_id):
            from datetime import datetime, timezone
            self.cycles += 1
            return SimpleNamespace(
                snapshot=SimpleNamespace(vram_utilization_percent=91.0),
                epoch=SimpleNamespace(observed_at=datetime.now(timezone.utc).isoformat()))

    monkeypatch.setattr(host_runtime, "HostResourceRuntimeCoordinator", FakeCoordinator)
    monkeypatch.setattr(host_runtime, "summary_for_evaluation", lambda evaluation: {
        "evaluation_id": "dev-monitor-test", "status": "ok"})
    monkeypatch.setattr(runner, "_host_resource_log_payload", lambda evaluation, report: {
        "event": "host_resource_observation",
        "observed_at": evaluation.epoch.observed_at})
    monkeypatch.setenv("SENTIENTOS_RUNTIME_STATE_ROOT", str(tmp_path / "runtime"))

    entered = threading.Event()
    unblock = threading.Event()
    observations = []
    release_attempts = []
    guard = runner._GamingResourcePressureGuard()

    class FakeInvoker:
        model = SimpleNamespace(active_identity=SimpleNamespace(engine="other"))
        authority_map = None

        def build_request(self, **kwargs):
            return kwargs

        def invoke(self, request, **kwargs):
            entered.set()
            assert unblock.wait(3)
            return SimpleNamespace(status="ok")

        def release_model_residency(self, *, reason_code, cancel_active):
            release_attempts.append((reason_code, cancel_active))
            return {"status": "deferred",
                    "reason_codes": ["active_inference_in_progress"]}

    invoker = FakeInvoker()
    inference = DevelopmentLocalChatInference(invoker)
    # Reproduce the runner's automatic workload mode; no profile transition is
    # needed for this test because the backend invocation itself is the blocker.
    inference._workload_mode = "automatic"

    inference_thread = threading.Thread(target=lambda: inference.generate(
        prompt="[SYSTEM_INSTRUCTION]\nTest [VERIFIED_RUNTIME_CONTEXT] context [SESSION_HISTORY_DATA] history", caller="local-user", correlation_id="blocked-monitor-test",
        budget=LocalModelInvocationBudget(), caller_linkage={}))
    inference_thread.start()
    assert entered.wait(1)

    def observe_vram(utilization, observed_at):
        resource_state = runner._apply_gaming_resource_observation(
            guard, utilization, observed_at,
            lambda reason: invoker.release_model_residency(
                reason_code=reason, cancel_active=False))
        workload_state = inference.reconcile_workload_state()
        resource_state["workload_reconciliation"] = workload_state[
            "workload_reconciliation"]
        observations.append((observed_at, time.monotonic(), resource_state))
        return resource_state

    sampler = None
    sampler = runner._HostResourceSampler(
        interval_seconds=0.01, on_vram_observation=observe_vram)
    try:
        deadline = time.monotonic() + 1.0
        while len(observations) < 3 and time.monotonic() < deadline:
            time.sleep(0.005)
        assert len(observations) >= 3
        # Inference remains blocked while timestamped host observations advance;
        # profile work defers instead of blocking telemetry delivery.
        timestamps = [item[0] for item in observations]
        assert all(isinstance(timestamp, str) and timestamp for timestamp in timestamps)
        assert len(set(timestamps)) == len(timestamps)
        captured_at = [datetime.fromisoformat(timestamp) for timestamp in timestamps]
        now = datetime.now(timezone.utc)
        assert all(-0.05 <= (now - timestamp).total_seconds() <= 0.5
                   for timestamp in captured_at)
        sample_monotonic = [item[1] for item in observations]
        assert all(0.0 < later - earlier <= 0.5
                   for earlier, later in zip(sample_monotonic, sample_monotonic[1:]))
        assert all(item[2]["workload_reconciliation"]["reason_code"]
                   == "inference_in_progress" for item in observations)
        assert all(item[2]["reason_code"] == "vram_pressure"
                   and item[2]["residency_release"]["status"] == "deferred"
                   for item in observations)
        assert len(release_attempts) >= 3
        assert all(reason == "vram_pressure_observed" and cancel_active is False
                   for reason, cancel_active in release_attempts)
        sampler.close()
        assert not sampler._thread.is_alive()
        assert not unblock.is_set()
    finally:
        unblock.set()
        inference_thread.join(timeout=2)
    assert not inference_thread.is_alive()


def test_development_chat_speech_is_opt_in_and_uses_local_controller(
        monkeypatch, tmp_path):
    import sentientos.chat_service as chat_service
    import sentientos.chat_speech_output as chat_speech_output

    constructed = []

    class FakeSpeechOutput:
        def __init__(self, **kwargs):
            constructed.append(kwargs)

        def state(self, session_id):
            return {"configured": True, "backend_available": True,
                    "enabled": False, "scope": "chat_response_local_speech"}

        def close(self):
            pass

    class FakeInvoker:
        class Model:
            active_identity = SimpleNamespace(engine="ollama")

            def is_resident(self):
                return False

        model = Model()

        def release_model_residency(self, **_kwargs):
            return SimpleNamespace(status="released",
                to_dict=lambda: {"status": "released"})

    monkeypatch.setattr(chat_speech_output, "ChatSpeechOutputController",
                        FakeSpeechOutput)
    chat_service.close_production_chat()
    try:
        chat_service.configure_development_chat(
            invoker=FakeInvoker(), data_root=tmp_path / "speech-disabled")
        assert chat_service._get_conversation_service().speech_output_state(
            None)["configured"] is False
        assert constructed == []

        chat_service.configure_development_chat(
            invoker=FakeInvoker(), data_root=tmp_path / "speech-enabled",
            local_speech_output=True)
        state = chat_service._get_conversation_service().speech_output_state(None)
        assert state["configured"] is True
        assert state["backend_available"] is True
        assert state["enabled"] is False
        from fastapi.testclient import TestClient
        from time import monotonic
        with TestClient(chat_service.APP) as client:
            service = chat_service._get_conversation_service()
            inference = service._inference
            assert inference._inference_lock.acquire(blocking=False)
            started = monotonic()
            try:
                busy = client.get("/runtime-status")
            finally:
                inference._inference_lock.release()
            assert busy.status_code == 200
            assert monotonic() - started < 2.0
            assert busy.json()["model_residency"]["status"] == "operation_in_progress"
            assert busy.json()["model_residency"]["loaded"] is None

            runtime = client.get("/runtime-status")
            assert runtime.status_code == 200
            runtime_payload = runtime.json()
            assert {key: value for key, value in runtime_payload.items()
                    if key != "model_residency"} == {
                "status": "running",
                "posture": "development_only",
                "production_serving": False,
                "effective_workload_mode": "normal",
                "screen_observation_configured": False,
                "local_speech_configured": True,
                "local_speech_backend_available": True,
            }
            assert runtime_payload["model_residency"]["status"] == "unloaded"
            assert runtime_payload["model_residency"]["loaded"] is False
            assert isinstance(runtime_payload["model_residency"]["observed_at"], str)
            assert "local model unloaded" in client.get("/").text
        assert len(constructed) == 1
    finally:
        chat_service.close_production_chat()


def test_avatar_nod_expectation_binds_the_authorized_output_command():
    from scripts.run_local_companion_dev import _PreparedAvatarConsequenceEmitter

    class Emitter:
        def __init__(self):
            self.calls = []
        def emit_display_text(self, phrase, *, authorization=None, metadata=None):
            self.calls.append(phrase)
            return {"status": "sent", "renderer_effect_proven": False}

    emitter = Emitter()
    observer = object()
    pointer = {
        "installation_identity": "test-installation",
        "body_identity": "test-avatar",
        "body_generation": 1,
        "manifest_digest": "sha256:" + "a" * 64,
        "artifact_sha256": "sha256:" + "b" * 64,
        "pointer_digest": "sha256:" + "c" * 64,
    }
    adapter = _PreparedAvatarConsequenceEmitter(
        emitter=emitter, pointer=pointer, observer=observer)
    metadata = {
        "session_id": "session-test", "turn_id": "turn-test",
        "output_digest": "sha256:" + "d" * 64,
    }

    assert adapter.emit_display_text(
        "I can help with that.", metadata=metadata)["status"] == "sent"
    staged = adapter._prepared[("session-test", "turn-test")]
    assert staged["expectation"].predicted_observables == {
        "avatar_visible": True, "avatar_motion": "nod"}
    assert staged["dispatch_status"] == "sent"
    assert not any(staged["expectation"].authority.values())
    assert emitter.calls == ["I can help with that."]
