from __future__ import annotations

from typing import List

from sentientos.actuators.gui_control import GUIController
from sentientos.actuators.tts_speaker import TTSSpeaker
from sentientos.agents.browser_automator import BrowserAutomator
from sentientos.autonomy.curiosity_loop import ObservationEvent, ObservationRouter
from sentientos.autonomy.runtime import AutonomyRuntime
from sentientos.metrics import MetricsRegistry
from sentientos.perception.asr_listener import ASRListener, CallableASRBackend
from sentientos.perception.screen_ocr import ScreenOCR
from sentientos.config import RuntimeConfig


class RecordingDriver:
    def __init__(self) -> None:
        self.events: List[tuple[str, str]] = []

    def open(self, url: str) -> None:
        self.events.append(("open", url))

    def click(self, selector: str) -> None:
        self.events.append(("click", selector))

    def type(self, selector: str, text: str) -> None:
        self.events.append(("type", f"{selector}:{text}"))


def test_embodied_autonomy_flow(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(tmp_path / "data"))

    metrics = MetricsRegistry()
    config = RuntimeConfig()
    config.audio.enable = True
    config.tts.enable = True
    config.screen.enable = True
    config.gui.enable = True
    config.gui.safety = "permissive"
    config.social.enable = True
    config.social.allow_interactive_web = True
    config.social.domains_allowlist = ("example.com",)
    config.social.daily_action_budget = 3
    config.social.require_quorum_for_post = True
    config.conversation.enable = True
    config.conversation.max_prompts_per_hour = 3

    runtime = AutonomyRuntime(config, metrics=metrics)

    backend = CallableASRBackend("fake", lambda audio, sr: {"text": "hello", "confidence": 0.9})
    runtime.asr = ASRListener(config.audio, backend_factory=lambda _: backend, metrics=metrics)
    runtime.asr._config.enable = True

    screen = ScreenOCR(
        config.screen,
        capture_fn=lambda: {"data": "error dialog", "title": "Dialog"},
        ocr_fn=lambda payload: payload["data"],
        metrics=metrics,
    )
    runtime.screen = screen

    spoken: list[str] = []

    def speak_backend(name: str):
        def inner(text: str) -> None:
            spoken.append(text)

        return inner

    runtime.tts = TTSSpeaker(config.tts, backend_factory=speak_backend, metrics=metrics)

    mouse_events: list[tuple[str, dict]] = []

    def mouse(action: str, payload: dict) -> None:
        mouse_events.append((action, payload))

    runtime.gui = GUIController(config.gui, mouse_driver=mouse, keyboard_driver=lambda a, b: mouse_events.append((a, b)))

    driver = RecordingDriver()
    runtime.social = BrowserAutomator(config.social, driver_factory=lambda: driver, metrics=metrics)

    runtime.conversation._config.enable = True

    samples = [0.2] * 1600
    audio_obs = runtime.asr.process_samples(samples, sample_rate=1600)
    assert audio_obs is not None
    router = ObservationRouter(metrics)
    router.route(ObservationEvent(modality="audio", payload=audio_obs))

    screen_obs = runtime.screen.snapshot()
    assert screen_obs is not None
    router.route(ObservationEvent(modality="screen", payload=screen_obs))

    runtime.tts.enqueue("Greetings")
    runtime.tts.drain()
    assert spoken == ["Greetings"]

    runtime.gui.move(x=5, y=5)
    runtime.gui.type_text("hello")
    runtime.social.open_url("https://example.com/feed")
    runtime.conversation.should_trigger("presence")

    status = runtime.status().modules
    assert "ears" in status and status["ears"]["status"] == "healthy"
    assert "voice" in status
    assert driver.events[0][0] == "open"
    counters = metrics.snapshot()["counters"]
    assert counters["sos_observation_events_total{modality=audio}"] == 1.0
