"""CLI to exercise text-to-speech playback with avatar/dashboard feedback."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from control_plane import Decision, RequestType, admit_request
from avatar_state import AvatarStateEmitter
from speech_emitter import DEFAULT_BASE_STATE, SpeechEmitter
from speech_log import get_recent_speech
from speech_to_avatar_bridge import SpeechToAvatarBridge


def _load_visemes(source: str | None) -> Any:
    if not source:
        return None
    if source.lower() == "demo":
        return [
            {"time": 0.0, "duration": 0.12, "viseme": "A"},
            {"time": 0.12, "duration": 0.12, "viseme": "B"},
            {"time": 0.24, "duration": 0.12, "viseme": "C"},
        ]
    candidate = Path(source)
    if candidate.exists():
        try:
            return json.loads(candidate.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
    try:
        return json.loads(source)
    except json.JSONDecodeError:
        return None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phrase", nargs="?", default="Hello from SentientOS!", help="text to synthesize")
    parser.add_argument("--visemes", help="Path or JSON payload of viseme timeline (use 'demo' for sample)")
    parser.add_argument("--voice", help="Optional voice name to request from backend")
    parser.add_argument("--mode", help="Runtime mode for avatar forwarding (e.g., LOCAL_OWNER)")
    parser.add_argument("--muted", action="store_true", help="Mute audio playback while still logging state")
    parser.add_argument("--no-avatar", action="store_true", help="Skip avatar_state emission, log only")
    parser.add_argument(
        "--speech-log", type=Path, help="Override speech_log.jsonl destination for test runs"
    )
    parser.add_argument(
        "--state-path", type=Path, help="Override avatar_state.json path for test runs"
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    target_state = args.state_path if args.state_path else None
    emitter = AvatarStateEmitter(target_state)
    bridge = SpeechToAvatarBridge(
        SpeechEmitter(emitter, base_state=dict(DEFAULT_BASE_STATE)),
        log_path=args.speech_log,
    )
    if args.no_avatar:
        bridge.forward_avatar = False

    admission = admit_request(
        request_type=RequestType.SPEECH_TTS,
        requester_id="demo-cli",
        intent_hash=args.phrase,
        context_hash="tts-demo",
        policy_version="v1-static",
        metadata={"approved_by": "demo-operator"},
    )
    if admission.decision is Decision.DENY:
        raise SystemExit(f"Control Plane denied TTS request: {admission.reason.value}")

    viseme_payload = _load_visemes(args.visemes)
    start_payload = bridge.speak_text(
        args.phrase,
        visemes=viseme_payload,
        muted=args.muted,
        mode=args.mode,
        voice=args.voice,
        authorization=admission.record,
    )

    latest = get_recent_speech(log_path=args.speech_log) or {}
    state_path = emitter.target_path if hasattr(emitter, "target_path") else None
    viseme_count = len(start_payload.get("viseme_timeline", [])) if isinstance(start_payload, Mapping) else 0
    print("--- SentientOS TTS Demo ---")
    print(f"Phrase: {args.phrase}")
    print(f"Voice: {args.voice or 'default'} | Mode: {args.mode or 'AUTO'} | Muted: {args.muted}")
    print(f"Avatar forwarding: {'disabled' if args.no_avatar else 'enabled'}")
    print(f"Visemes forwarded: {viseme_count}")
    if state_path:
        print(f"Avatar state file: {state_path}")
    if args.speech_log:
        print(f"Speech log: {args.speech_log}")
    if latest:
        print(f"Last speech entry: {latest}")


if __name__ == "__main__":
    main()

