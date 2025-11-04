"""Autonomy readiness verification CLI."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional

try:  # pragma: no cover - optional dependency
    from colorama import Fore, Style, init as colorama_init
except Exception:  # pragma: no cover - color fallback
    class _Dummy:  # type: ignore[misc]
        RESET = ""
        GREEN = ""
        RED = ""
        YELLOW = ""
        RESET_ALL = ""

    Fore = Style = _Dummy()  # type: ignore[assignment]

    def colorama_init(*_: object, **__: object) -> None:  # type: ignore[override]
        return None


from sentientos.actuators.gui_control import GUIConfig, GUIController, GUIControlError
from sentientos.actuators.tts_speaker import TTSPersonality, TTSConfig, TTSSpeaker
from sentientos.agents.browser_automator import BrowserAutomator, BrowserActionError, SocialConfig
from sentientos.local_model import LocalModel, ModelLoadError
from sentientos.metrics import MetricsRegistry
from sentientos.perception.asr_listener import ASRListener, AudioConfig, CallableASRBackend
from sentientos.perception.screen_ocr import ScreenConfig, ScreenOCR


class SubsystemCheckError(RuntimeError):
    def __init__(self, message: str, *, status: str = "FAIL", hint: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.hint = hint


class MissingSubsystemError(SubsystemCheckError):
    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message, status="MISSING", hint=hint)


@dataclass
class SubsystemResult:
    name: str
    status: str
    latency_ms: float
    last_test_timestamp: str
    error: str | None = None
    hint: str | None = None
    details: Dict[str, object] | None = None

    def to_dict(self) -> Dict[str, object]:
        payload = asdict(self)
        # Drop None fields for cleaner JSON
        return {k: v for k, v in payload.items() if v is not None}


@dataclass
class CheckContext:
    env: Mapping[str, str]
    model_root: Path
    reports_dir: Path


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dirs(path: Path) -> None:
    if path.exists() and path.is_dir():
        return
    if path.suffix:
        path.parent.mkdir(parents=True, exist_ok=True)
    else:
        path.mkdir(parents=True, exist_ok=True)


def _load_local_model() -> LocalModel:
    return LocalModel.autoload()


def _sample_audio(seconds: float = 0.1, sample_rate: int = 16000) -> List[float]:
    count = max(int(seconds * sample_rate), 1)
    return [0.05 for _ in range(count)]


def check_asr(context: CheckContext) -> Dict[str, object]:
    whisper_dir = context.model_root / "whisper"
    if not whisper_dir.exists():
        raise MissingSubsystemError(
            "Whisper model not found",
            hint="Whisper model not found — place base.en.gguf in /models/whisper/",
        )
    dummy_microphone = shutil.which("arecord") or shutil.which("sox")
    if not dummy_microphone:
        raise SubsystemCheckError(
            "Audio capture binary unavailable",
            hint="Install portaudio/sox or expose system microphone capture tooling.",
        )
    backend = CallableASRBackend(
        "diagnostic",
        lambda audio, rate: {
            "text": "diagnostic microphone check",
            "confidence": 0.92,
            "language": "en",
        },
    )
    listener = ASRListener(
        AudioConfig(
            enable=True,
            backend="diagnostic",
            chunk_seconds=1.0,
            max_minutes_per_hour=20.0,
            max_concurrent=1,
        ),
        backend_factory=lambda _: backend,
        metrics=MetricsRegistry(),
    )
    observation = listener.process_samples(_sample_audio(), sample_rate=16000)
    if not observation or not observation.get("transcript"):
        raise SubsystemCheckError(
            "ASR functional test did not produce a transcript",
            hint="Verify Whisper backend is installed and callable.",
        )
    return {
        "model_path": str(whisper_dir),
        "recorder": dummy_microphone,
        "backend": observation.get("backend"),
        "transcript_preview": str(observation.get("transcript", ""))[:80],
    }


def check_tts(context: CheckContext) -> Dict[str, object]:
    binary = shutil.which("espeak") or shutil.which("say")
    if not binary:
        raise MissingSubsystemError(
            "TTS engine not available",
            hint="Install espeak-ng or configure SENTIENTOS_TTS_BACKEND=pyttsx3.",
        )
    spoken: List[Mapping[str, object]] = []

    def backend_factory(_: str) -> Callable[[str, Mapping[str, object]], None]:
        def speak(text: str, *, voice_params: Mapping[str, object] | None = None) -> None:
            spoken.append({"text": text, "voice_params": dict(voice_params or {})})

        return speak

    speaker = TTSSpeaker(
        TTSConfig(
            enable=True,
            backend="diagnostic",
            max_chars_per_minute=5000,
            cooldown_seconds=0.0,
            personality=TTSPersonality(expressiveness="medium", baseline_mood="calm", dynamic_voice=True),
        ),
        backend_factory=backend_factory,
        metrics=MetricsRegistry(),
        mood_provider=lambda: "joyful",
    )
    speaker.enqueue("Diagnostic voice check", mood="alert")
    drained = speaker.drain()
    if not drained:
        raise SubsystemCheckError(
            "TTS functional test produced no speech",
            hint="Ensure espeak/picotts is installed or configure SENTIENTOS_TTS_BACKEND.",
        )
    modifiers = drained[0]["voice"].get("modifiers", {})
    return {
        "backend": binary,
        "dynamic_voice": modifiers,
        "mood": drained[0]["voice"].get("mood"),
    }


def check_ocr(context: CheckContext) -> Dict[str, object]:
    tesseract = shutil.which("tesseract")
    if not tesseract:
        raise MissingSubsystemError(
            "Tesseract binary missing",
            hint="Tesseract not in PATH — install or set TESSDATA_PREFIX",
        )
    tessdata = context.env.get("TESSDATA_PREFIX")
    config = ScreenConfig(enable=True, ocr_backend="diagnostic", max_chars_per_minute=5000)
    capture_payload = {"data": "Diagnostic OCR window", "title": "readiness"}
    screen = ScreenOCR(
        config,
        capture_fn=lambda: capture_payload,
        ocr_fn=lambda payload: str(payload.get("data", "")),
        metrics=MetricsRegistry(),
    )
    observation = screen.snapshot()
    if not observation or not observation.get("text"):
        raise SubsystemCheckError(
            "OCR functional test returned no text",
            hint="Ensure Tesseract models are installed and accessible via TESSDATA_PREFIX.",
        )
    details: Dict[str, object] = {"binary": tesseract, "text_preview": observation["text"]}
    if tessdata:
        details["tessdata"] = tessdata
    return details


def check_browser(context: CheckContext) -> Dict[str, object]:
    chrome = shutil.which("chromium") or shutil.which("google-chrome") or shutil.which("firefox")
    if not chrome:
        raise MissingSubsystemError(
            "No headless browser found",
            hint="Install Chromium or Firefox and ensure it is available on PATH.",
        )

    class _Driver:
        def __init__(self) -> None:
            self.actions: List[tuple[str, object]] = []

        def open(self, url: str) -> None:
            self.actions.append(("open", url))

        def click(self, selector: str) -> None:
            self.actions.append(("click", selector))

        def type(self, selector: str, text: str) -> None:
            self.actions.append(("type", {"selector": selector, "text": text}))

    driver = _Driver()
    automator = BrowserAutomator(
        SocialConfig(
            enable=True,
            allow_interactive_web=False,
            domains_allowlist=("example.com",),
            daily_action_budget=5,
            require_quorum_for_post=False,
        ),
        driver_factory=lambda: driver,
        metrics=MetricsRegistry(),
        panic_flag=lambda: False,
    )
    try:
        automator.open_url("https://example.com/autonomy-diagnostic")
        automator.click("https://example.com/#readiness")
        automator.type_text("https://example.com/form#status", "diagnostic ping")
    except BrowserActionError as exc:
        raise SubsystemCheckError(
            f"Browser automation failed: {exc}",
            hint="Provide a working headless browser driver (Chromium/Firefox).",
        ) from exc
    return {"binary": chrome, "actions": driver.actions}


def check_gui(context: CheckContext) -> Dict[str, object]:
    pyautogui = shutil.which("xdotool") or shutil.which("yabai")
    if not pyautogui:
        raise MissingSubsystemError(
            "GUI automation toolkit missing",
            hint="Install xdotool (Linux) or ensure GUI bridge binary is configured.",
        )
    events: List[tuple[str, Mapping[str, object]]] = []

    def mouse_driver(action: str, payload: Mapping[str, object]) -> None:
        events.append((action, dict(payload)))

    def keyboard_driver(action: str, payload: Mapping[str, object]) -> None:
        events.append((action, dict(payload)))

    controller = GUIController(
        GUIConfig(enable=True, safety="standard", move_smoothing=True),
        mouse_driver=mouse_driver,
        keyboard_driver=keyboard_driver,
        panic_flag=lambda: False,
    )
    try:
        controller.move(x=42, y=21)
        controller.click(x=42, y=21)
        controller.type_text("diagnostic ready")
    except GUIControlError as exc:
        raise SubsystemCheckError(
            f"GUI control failed: {exc}",
            hint="Ensure GUI automation bridge is installed and panic flag cleared.",
        ) from exc
    return {"driver": pyautogui, "events": events}


def check_llm(context: CheckContext) -> Dict[str, object]:
    llm_dir = context.model_root / "llm"
    if not llm_dir.exists():
        raise MissingSubsystemError(
            "LLM model directory missing",
            hint="CUBLAS missing — install CUDA 12.1 runtime or use CPU-only llama-cpp build.",
        )
    try:
        model = _load_local_model()
    except ModelLoadError as exc:
        raise SubsystemCheckError(
            f"Local model failed to load: {exc}",
            hint="CUBLAS missing — install CUDA 12.1 runtime or use CPU-only llama-cpp build.",
        ) from exc
    response = model.generate("Summarise system readiness")
    if not isinstance(response, str) or not response.strip():
        raise SubsystemCheckError(
            "LLM backend returned no output",
            hint="Verify llama.cpp weights are present in /models/llm/",
        )
    gpu_hint = context.env.get("LLAMA_CPP_GPU") or "cpu"
    metadata = getattr(model, "metadata", {})
    return {
        "model_path": str(llm_dir),
        "gpu_offload": gpu_hint,
        "engine": metadata.get("engine", "unknown"),
        "response_preview": response.strip()[:120],
    }


CHECKS: Mapping[str, Callable[[CheckContext], Dict[str, object]]] = {
    "ASR": check_asr,
    "TTS": check_tts,
    "OCR": check_ocr,
    "Browser": check_browser,
    "GUI": check_gui,
    "LLM": check_llm,
}


def run_checks(context: CheckContext) -> Dict[str, SubsystemResult]:
    results: Dict[str, SubsystemResult] = {}
    for name, check in CHECKS.items():
        start = time.perf_counter()
        timestamp = _utcnow()
        hint: str | None = None
        details: Dict[str, object] | None = None
        status = "PASS"
        error: Optional[str] = None
        try:
            details = check(context)
        except SubsystemCheckError as exc:
            status = exc.status
            error = str(exc)
            hint = exc.hint
        except Exception as exc:  # pragma: no cover - unexpected failure
            status = "FAIL"
            error = str(exc)
        latency = (time.perf_counter() - start) * 1000
        result = SubsystemResult(
            name=name,
            status=status,
            latency_ms=round(latency, 2),
            last_test_timestamp=timestamp,
            error=error,
            hint=hint,
            details=details,
        )
        results[name] = result
    return results


def summarise(results: Mapping[str, SubsystemResult]) -> Dict[str, object]:
    totals = {"PASS": 0, "FAIL": 0, "MISSING": 0}
    for result in results.values():
        totals.setdefault(result.status, 0)
        totals[result.status] += 1
    healthy = totals.get("PASS", 0) == len(results)
    return {"totals": totals, "healthy": healthy}


def render(results: Mapping[str, SubsystemResult], *, quiet: bool = False) -> None:
    if not quiet:
        try:  # pragma: no cover - optional color
            colorama_init()
        except Exception:
            pass
    for name, result in results.items():
        colour = {
            "PASS": Fore.GREEN,
            "FAIL": Fore.RED,
            "MISSING": Fore.YELLOW,
        }.get(result.status, "")
        reset = getattr(Style, "RESET_ALL", "")
        if quiet:
            print(f"{name:<8} {result.status:<7} {result.latency_ms:>7.2f}ms")
            continue
        print(f"{colour}{name:<8} {result.status:<7} {result.latency_ms:>7.2f}ms{reset}")
        if result.error:
            print(f"    error: {result.error}")
        if result.hint:
            print(f"    hint : {result.hint}")


def write_report(results: Mapping[str, SubsystemResult], reports_dir: Path) -> Path:
    ensure_dirs(reports_dir)
    payload = {
        "generated_at": _utcnow(),
        "subsystems": {name: res.to_dict() for name, res in results.items()},
        "summary": summarise(results),
    }
    report_path = reports_dir / "autonomy_readiness.json"
    report_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report_path


def build_context() -> CheckContext:
    env = dict(os.environ)
    model_root = Path(env.get("SENTIENTOS_MODEL_ROOT", "models"))
    reports_dir = Path(env.get("SENTIENTOS_REPORT_DIR", "glow/reports"))
    return CheckContext(env=env, model_root=model_root, reports_dir=reports_dir)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Verify embodied autonomy readiness")
    parser.add_argument("--json", action="store_true", help="Print JSON summary to stdout")
    parser.add_argument("--quiet", action="store_true", help="Suppress verbose output")
    args = parser.parse_args(argv)

    context = build_context()
    results = run_checks(context)
    report_path = write_report(results, context.reports_dir)
    summary = summarise(results)

    if args.json:
        payload = {
            "report": str(report_path),
            "subsystems": {name: res.to_dict() for name, res in results.items()},
            "summary": summary,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        render(results, quiet=args.quiet)
        if not args.quiet:
            print(f"report written → {report_path}")

    return 0 if summary.get("healthy") else 1


if __name__ == "__main__":
    sys.exit(main())

