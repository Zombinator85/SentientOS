from __future__ import annotations

import argparse
import json
import platform
import re
import shutil
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sentientos.daemons import pulse_bus

EXTRACTOR_ID = "screen_adapter"
EXTRACTOR_VERSION = "1"
PRIVACY_CHOICES = ("public", "internal", "private", "restricted", "sensitive")

URL_TOKEN_RE = re.compile(r"((?:https?://)?(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}(?:/\S*)?)")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _run_cmd(command: list[str]) -> str | None:
    try:
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    output = completed.stdout.strip()
    return output or None


def _linux_snapshot() -> dict[str, Any]:
    if shutil.which("xdotool") is None:
        return {
            "active_app": None,
            "window_title": None,
            "cursor_position": None,
            "screen_geometry": None,
            "confidence": 0.2,
            "degraded": True,
            "degradation_reason": "xdotool unavailable",
        }

    window_id = _run_cmd(["xdotool", "getactivewindow"])
    window_title = _run_cmd(["xdotool", "getwindowfocus", "getwindowname"])
    app_name = _run_cmd(["xdotool", "getwindowfocus", "getwindowclassname"])
    location = _run_cmd(["xdotool", "getmouselocation", "--shell"])
    geometry = _run_cmd(["xdotool", "getdisplaygeometry"])

    cursor_position = None
    if location:
        values: dict[str, float] = {}
        for line in location.splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key in {"X", "Y"}:
                try:
                    values[key.lower()] = float(value)
                except ValueError:
                    continue
        if values:
            cursor_position = values

    screen_geometry = None
    if geometry:
        parts = geometry.split()
        if len(parts) == 2:
            try:
                screen_geometry = {"width": float(parts[0]), "height": float(parts[1])}
            except ValueError:
                screen_geometry = None

    degraded = window_id is None and app_name is None and window_title is None
    return {
        "active_app": app_name,
        "window_class": app_name,
        "process_name": app_name,
        "window_title": window_title,
        "cursor_position": cursor_position,
        "screen_geometry": screen_geometry,
        "confidence": 0.85 if not degraded else 0.3,
        "degraded": degraded,
        "degradation_reason": "no focused window metadata" if degraded else None,
    }


def _mac_snapshot() -> dict[str, Any]:
    if shutil.which("osascript") is None:
        return {
            "active_app": None,
            "window_title": None,
            "cursor_position": None,
            "screen_geometry": None,
            "confidence": 0.2,
            "degraded": True,
            "degradation_reason": "osascript unavailable",
        }

    app = _run_cmd(["osascript", "-e", 'tell application "System Events" to get name of first process whose frontmost is true'])
    title = _run_cmd(
        [
            "osascript",
            "-e",
            'tell application "System Events" to tell (first process whose frontmost is true) to get value of attribute "AXTitle" of front window',
        ]
    )

    degraded = app is None and title is None
    return {
        "active_app": app,
        "process_name": app,
        "window_title": title,
        "cursor_position": None,
        "screen_geometry": None,
        "confidence": 0.8 if not degraded else 0.3,
        "degraded": degraded,
        "degradation_reason": "no frontmost app/window metadata" if degraded else None,
    }


def _windows_snapshot() -> dict[str, Any]:
    try:
        import win32api  # type: ignore
        import win32gui  # type: ignore
        import win32process  # type: ignore
    except ImportError:
        return {
            "active_app": None,
            "window_title": None,
            "cursor_position": None,
            "screen_geometry": None,
            "confidence": 0.25,
            "degraded": True,
            "degradation_reason": "pywin32 unavailable",
        }

    foreground = win32gui.GetForegroundWindow()
    title = win32gui.GetWindowText(foreground) if foreground else None
    app_name = None
    if foreground:
        try:
            _thread_id, pid = win32process.GetWindowThreadProcessId(foreground)
            app_name = str(pid)
        except Exception:
            app_name = None

    cursor = None
    try:
        x, y = win32api.GetCursorPos()
        cursor = {"x": float(x), "y": float(y)}
    except Exception:
        cursor = None

    degraded = title is None and app_name is None
    return {
        "active_app": app_name,
        "process_name": app_name,
        "window_title": title,
        "cursor_position": cursor,
        "screen_geometry": None,
        "confidence": 0.8 if not degraded else 0.3,
        "degraded": degraded,
        "degradation_reason": "foreground window unavailable" if degraded else None,
    }


def snapshot_screen_context() -> dict[str, Any]:
    system = platform.system().lower()
    if system == "windows":
        return _windows_snapshot()
    if system == "darwin":
        return _mac_snapshot()
    return _linux_snapshot()


def _extract_url_token(window_title: str | None) -> str | None:
    if not window_title:
        return None
    match = URL_TOKEN_RE.search(window_title)
    if not match:
        return None
    token = match.group(1)
    if token.startswith(("http://", "https://")):
        return token
    return f"https://{token}"


def _extract_domain(url_candidate: str | None) -> str | None:
    if not url_candidate:
        return None
    try:
        parsed = urlparse(url_candidate)
    except ValueError:
        return None
    hostname = parsed.hostname
    return hostname.lower() if isinstance(hostname, str) and hostname else None


def _classify_ui_context(active_app: str | None, window_title: str | None) -> dict[str, Any]:
    app = (active_app or "").lower()
    title = window_title or None
    if any(token in app for token in ("chrome", "firefox", "edge", "safari", "browser", "brave")):
        return {"kind": "browser", "doc_title": title}
    if any(token in app for token in ("code", "vim", "emacs", "sublime", "notepad", "pycharm", "idea", "editor")):
        return {"kind": "editor", "doc_title": title}
    if any(token in app for token in ("terminal", "iterm", "powershell", "cmd", "console", "xterm", "gnome-terminal", "kitty")):
        return {"kind": "terminal", "doc_title": title}
    return {"kind": "unknown", "doc_title": title}


def build_perception_payload(
    *,
    privacy_class: str,
    text_excerpt: str | None,
    focused_element_hint: str | None,
    include_domain: bool,
    include_url_full: bool,
    include_text_excerpt: bool,
) -> dict[str, Any]:
    observation = snapshot_screen_context()
    window_title = observation.get("window_title")
    url_candidate = _extract_url_token(window_title if isinstance(window_title, str) else None)
    browser_domain = _extract_domain(url_candidate) if include_domain else None
    url_allowed = include_url_full and privacy_class == "private"
    text_allowed = include_text_excerpt and privacy_class in {"internal", "private"}
    ui_context = _classify_ui_context(
        observation.get("active_app") if isinstance(observation.get("active_app"), str) else None,
        window_title if isinstance(window_title, str) else None,
    )

    redaction_notes: list[str] = []
    if include_url_full and privacy_class != "private":
        redaction_notes.append("browser_url_full omitted: privacy_class must be private")
    if include_text_excerpt and privacy_class not in {"internal", "private"}:
        redaction_notes.append("text_excerpt omitted: requires internal/private privacy_class")
    if include_domain and browser_domain is None:
        redaction_notes.append("browser_domain unavailable from current platform metadata")

    payload: dict[str, Any] = {
        "event_type": "perception.screen",
        "timestamp": _iso_now(),
        "source": "local.screen",
        "extractor_id": EXTRACTOR_ID,
        "extractor_version": EXTRACTOR_VERSION,
        "confidence": float(observation.get("confidence", 0.2)),
        "privacy_class": privacy_class,
        "provenance": {
            "extractor": EXTRACTOR_ID,
            "extractor_version": EXTRACTOR_VERSION,
            "host": socket.gethostname(),
            "platform": platform.platform(),
            "python_version": platform.python_version(),
        },
        "active_app": observation.get("active_app"),
        "window_class": observation.get("window_class"),
        "process_name": observation.get("process_name"),
        "window_title": observation.get("window_title"),
        "browser_domain": browser_domain,
        "browser_url_full": url_candidate if url_allowed else None,
        "focused_element_hint": focused_element_hint,
        "ui_context": ui_context,
        "cursor_position": observation.get("cursor_position"),
        "screen_geometry": observation.get("screen_geometry"),
        "raw_artifact_retained": False,
        "redaction_applied": bool(redaction_notes),
        "redaction_notes": "; ".join(redaction_notes) if redaction_notes else None,
        "degraded": bool(observation.get("degraded", False)),
        "degradation_reason": observation.get("degradation_reason"),
    }
    if text_allowed and text_excerpt:
        payload["text_excerpt"] = text_excerpt[:256]
    return {key: value for key, value in payload.items() if value is not None}


def emit_pulse(payload: dict[str, Any], *, output_log: Path) -> dict[str, Any]:
    event = {
        "timestamp": payload["timestamp"],
        "source_daemon": EXTRACTOR_ID,
        "event_type": "perception.screen",
        "payload": payload,
        "priority": "info",
        "event_origin": "local",
        "context": {"privacy_class": payload["privacy_class"]},
    }
    try:
        published = pulse_bus.publish(event)
        return {"published": True, "event": published}
    except Exception as exc:
        output_log.parent.mkdir(parents=True, exist_ok=True)
        with output_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
        return {
            "published": False,
            "error": str(exc),
            "fallback_log": str(output_log),
            "event": event,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit a perception.screen pulse event from local screen awareness")
    parser.add_argument("--privacy-class", default="internal", choices=PRIVACY_CHOICES)
    parser.add_argument("--text-excerpt", default=None)
    parser.add_argument("--focused-element-hint", default=None)
    parser.add_argument("--include-domain", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--include-url-full", action="store_true", default=False)
    parser.add_argument("--include-text-excerpt", action="store_true", default=False)
    parser.add_argument("--output-log", default="glow/perception/perception_screen_events.jsonl")
    args = parser.parse_args(argv)

    payload = build_perception_payload(
        privacy_class=args.privacy_class,
        text_excerpt=args.text_excerpt,
        focused_element_hint=args.focused_element_hint,
        include_domain=bool(args.include_domain),
        include_url_full=bool(args.include_url_full),
        include_text_excerpt=bool(args.include_text_excerpt),
    )
    result = emit_pulse(payload, output_log=Path(args.output_log))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
