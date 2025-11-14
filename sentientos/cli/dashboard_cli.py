"""Console dashboard and demo orchestration entrypoint."""

from __future__ import annotations

import argparse
import io
import logging
import sys
import threading
from typing import Callable, Optional, Sequence

from sentientos.dashboard.console import ConsoleDashboard, LogBuffer
from sentientos.dashboard.status_source import make_log_stream_source, make_status_source
from sentientos.experiments import demo_gallery
from sentientos.start import load_config
from sentientos.voice.config import parse_tts_config
from sentientos.voice.tts import TtsEngine


LOGGER = logging.getLogger("sentientos.cli.dashboard")


class _BufferLogHandler(logging.Handler):
    """Logging handler that forwards persona heartbeat lines."""

    def __init__(self, buffer: LogBuffer) -> None:
        super().__init__(level=logging.INFO)
        self._buffer = buffer

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - logging hook
        try:
            message = self.format(record)
        except Exception:
            message = record.getMessage()
        self._buffer.add(message)


def _attach_persona_logger(buffer: LogBuffer) -> Optional[logging.Handler]:
    logger = logging.getLogger("sentientos.persona")
    handler = _BufferLogHandler(buffer)
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logger.addHandler(handler)
    return handler


def _run_demo(
    name: str,
    buffer: LogBuffer,
    speak_callback: Optional[Callable[[str], None]] = None,
) -> Optional[demo_gallery.DemoRun]:
    """Execute a demo and stream results into the dashboard buffer."""

    buffer.add(f"Demo '{name}' starting.")
    if speak_callback:
        try:
            speak_callback(f"Demo {name} starting")
        except Exception:  # pragma: no cover - defensive logging
            LOGGER.exception("Demo speak callback failed (start)")
    try:
        result = demo_gallery.run_demo(name, stream=lambda line: buffer.add(str(line)))
    except Exception as exc:  # pragma: no cover - defensive logging
        buffer.add(f"Demo '{name}' failed: {exc}")
        if speak_callback:
            try:
                speak_callback(f"Demo {name} failed")
            except Exception:  # pragma: no cover - defensive logging
                LOGGER.exception("Demo speak callback failed (error)")
        return None

    outcome = result.result.outcome
    if outcome.lower() == "success":
        buffer.add(f"Demo '{name}' completed successfully.")
        if speak_callback:
            try:
                speak_callback(f"Demo {name} completed successfully")
            except Exception:  # pragma: no cover - defensive logging
                LOGGER.exception("Demo speak callback failed (success)")
    else:
        buffer.add(f"Demo '{name}' completed with outcome: {outcome}")
        if speak_callback:
            try:
                speak_callback(f"Demo {name} completed with outcome {outcome}")
            except Exception:  # pragma: no cover - defensive logging
                LOGGER.exception("Demo speak callback failed (outcome)")
    return result


def _build_dashboard(
    *,
    refresh_interval: float,
    output_stream: Optional[io.TextIOBase] = None,
) -> tuple[ConsoleDashboard, LogBuffer, Optional[Callable[[str], None]]]:
    config = load_config()
    buffer = LogBuffer()
    log_source = make_log_stream_source(buffer)
    status_source = make_status_source(config=config)
    speak_callback: Optional[Callable[[str], None]] = None
    voice_section = config.get("voice")
    if isinstance(voice_section, dict) and voice_section.get("enabled"):
        tts_section = voice_section.get("tts")
        if isinstance(tts_section, dict):
            try:
                tts_config = parse_tts_config(tts_section)
            except Exception as exc:  # pragma: no cover - defensive logging
                LOGGER.warning("Failed to parse TTS config for dashboard: %s", exc)
            else:
                if tts_config.enabled:
                    engine = TtsEngine(tts_config)
                    speak_callback = engine.speak
    dashboard = ConsoleDashboard(
        status_source,
        log_stream_source=log_source,
        refresh_interval=refresh_interval,
        log_buffer=buffer,
        output_stream=output_stream,
    )
    return dashboard, buffer, speak_callback


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="SentientOS console dashboard")
    parser.add_argument(
        "--refresh-interval",
        type=float,
        default=2.0,
        help="Seconds between dashboard refreshes",
    )
    parser.add_argument(
        "--run-demo",
        dest="demo_name",
        help="Run the specified demo from the gallery",
    )
    args = parser.parse_args(argv)

    dashboard, buffer, speak_callback = _build_dashboard(
        refresh_interval=max(0.5, float(args.refresh_interval)),
        output_stream=sys.stdout,
    )

    persona_handler = _attach_persona_logger(buffer)

    demo_thread: Optional[threading.Thread] = None
    if args.demo_name:
        demo_name = args.demo_name

        def _demo_runner() -> None:
            _run_demo(demo_name, buffer, speak_callback)

        demo_thread = threading.Thread(target=_demo_runner, name="SentientOSDemo", daemon=True)
        demo_thread.start()

    try:
        dashboard.run_loop()
    except KeyboardInterrupt:
        dashboard.stop()
    finally:
        if persona_handler:
            logger = logging.getLogger("sentientos.persona")
            logger.removeHandler(persona_handler)
        if demo_thread is not None:
            demo_thread.join(timeout=1.0)
    return 0


if __name__ == "__main__":  # pragma: no cover - module entrypoint
    raise SystemExit(main())
