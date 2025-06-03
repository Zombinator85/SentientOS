import argparse
import json
import time
import subprocess
from pathlib import Path
import zipfile
import tempfile
from typing import Any, List
from flask_stub import Flask, jsonify, request
from admin_utils import require_admin_banner

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.


def run_dashboard(storyboard: str) -> Flask:
    """Return a Flask dashboard app for the storyboard."""
    data = json.loads(Path(storyboard).read_text())
    chapters = data.get("chapters", [])
    state = {"chapters": chapters, "index": 0, "bookmarks": []}
    app = Flask(__name__)

    @app.route("/chapters")
    def _chapters() -> Any:
        args_obj = getattr(request, "args", None)
        user = args_obj.get("user") if args_obj else None
        persona = args_obj.get("persona") if args_obj else None
        filtered = state["chapters"]
        if user:
            filtered = [c for c in filtered if c.get("user") == user]
        if persona:
            filtered = [c for c in filtered if c.get("persona") == persona]
        return jsonify(filtered)

    @app.route("/personas")
    def _personas() -> Any:
        pers = sorted({c.get("persona", "") for c in state["chapters"]})
        return jsonify(pers)

    @app.route("/current")
    def _current() -> Any:
        idx = state["index"]
        if 0 <= idx < len(state["chapters"]):
            return jsonify(state["chapters"][idx])
        return jsonify({})

    @app.route("/jump", methods=["POST"])
    def _jump() -> Any:
        idx = int(request.json.get("index", 0))
        if 0 <= idx < len(state["chapters"]):
            state["index"] = idx
        return jsonify({"ok": True})

    @app.route("/bookmark", methods=["POST"])
    def _bookmark() -> Any:
        state["bookmarks"].append(state["index"])
        return jsonify({"ok": True})

    return app
from flask_stub import Flask, jsonify, request


def _fmt_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02}:{s:02}"


def _trigger_avatar(emotion: str, persona: str, ts: float, cmd: str | None) -> None:
    if cmd:
        full = f"{cmd} --emotion={emotion} --persona={persona} --time={ts}"
        try:
            subprocess.run(full, shell=True, check=False)
        except Exception:
            print(f"[Avatar] {full}")
    else:
        print(f"[Avatar] set_avatar(preset='{emotion}', persona='{persona}')")


def _trigger_sfx(sfx: str | None) -> None:
    if not sfx:
        return
    print(f"[SFX] {sfx}")


def _trigger_gesture(gesture: str | None) -> None:
    if not gesture:
        return
    print(f"[GESTURE] {gesture}")


def _trigger_env(env: str | None) -> None:
    if not env:
        return
    print(f"[ENV] {env}")


def _show_emotion(emotion: str, headless: bool) -> None:
    if headless:
        print(f"Emotion: {emotion}")
    else:
        print(f"[EMOTION] {emotion}")


def print_timeline(storyboard: str) -> None:
    """Print a simple emotion/persona timeline."""
    data = json.loads(Path(storyboard).read_text())
    chapters = data.get("chapters", [])
    for ch in chapters:
        num = ch.get("chapter") or chapters.index(ch) + 1
        mood = ch.get("mood", "neutral")
        persona = ch.get("voice") or ch.get("persona", "")
        ts = _fmt_time(ch.get("t_start", 0))
        mark = "*" if ch.get("highlight") else ""
        print(f"{num:>3} {ts} {mood:<8} {persona} {mark}")


def playback(
    storyboard: str,
    headless: bool = False,
    gui: bool = False,
    audio_only: bool = False,
    avatar_callback: str | None = None,
    show_subtitles: bool = False,
    start_chapter: int = 1,
    enable_gestures: bool = False,
    enable_sfx: bool = False,
    enable_env: bool = False,
    interpolate_voices: bool = False,
    feedback_enabled: bool = False,
    feedback_file: str | None = None,
    dashboard_state: dict | None = None,
    highlights_only: bool = False,
    branch: int | None = None,
) -> None:
    data = json.loads(Path(storyboard).read_text())
    chapters = data.get("chapters", [])
    if branch is not None:
        chapters = [c for c in chapters if c.get("chapter") == branch or c.get("fork_of") == branch]
    if highlights_only:
        chapters = [c for c in chapters if c.get("highlight")]
    total = len(chapters)
    prev_persona = ""
    for ch in chapters[start_chapter - 1 :]:
        num = ch.get("chapter") or chapters.index(ch) + 1
        title = ch.get("title", "")
        emotion = ch.get("mood") or ch.get("emotion", "neutral")
        persona = ch.get("voice") or ch.get("persona", "")
        ts = ch.get("t_start", 0)
        if interpolate_voices and prev_persona and prev_persona != persona:
            print(f"[INTERPOLATE] {prev_persona} -> {persona}")
        _trigger_avatar(emotion, persona, ts, avatar_callback)
        if enable_sfx:
            _trigger_sfx(ch.get("sfx"))
        if enable_gestures:
            _trigger_gesture(ch.get("gesture"))
        if enable_env:
            _trigger_env(ch.get("env"))
        _show_emotion(emotion, headless)
        print(f"Chapter {num}/{total}: {title}")
        duration = max(0.1, ch.get("t_end", 0) - ch.get("t_start", 0))
        if show_subtitles:
            line = ch.get("text", "")
            if headless:
                print(line)
        if not headless and ch.get("audio"):
            print(f"[PLAY] {ch['audio']}")
        if not headless and gui and ch.get("image"):
            print(f"[IMAGE] {ch['image']}")
        start = time.time()
        prev_persona = persona
        if dashboard_state is not None:
            dashboard_state["index"] = num - 1
        while True:
            elapsed = time.time() - start
            pct = min(elapsed / duration, 1.0)
            bar = "#" * int(pct * 20)
            if headless:
                print(
                    f"Chapter {num}/{total} [{bar:<20}] {int(pct*100)}% ({_fmt_time(elapsed)}/{_fmt_time(duration)})",
                    end="\r",
                )
            if pct >= 1.0:
                break
            time.sleep(0.1)
        if headless:
            print()
        if feedback_enabled:
            fb = input("Feedback> ").strip()
            if fb:
                path = Path(feedback_file or storyboard).with_suffix(".feedback.jsonl")
                with open(path, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"chapter": num, "feedback": fb}) + "\n")


def live_playback(
    storyboard: str,
    headless: bool = False,
    gui: bool = False,
    avatar_callback: str | None = None,
    poll: float = 0.5,
    max_chapters: int | None = None,
    **kwargs: Any,
) -> None:
    """Continuously watch a storyboard file and play new chapters."""
    seen = 0
    while True:
        try:
            data = json.loads(Path(storyboard).read_text())
        except Exception:
            time.sleep(poll)
            continue
        chapters = data.get("chapters", [])
        if seen < len(chapters):
            new = {"chapters": chapters[seen:]}
            tmp = Path(storyboard).with_suffix(".live.tmp")
            tmp.write_text(json.dumps(new), encoding="utf-8")
            playback(
                str(tmp),
                headless=headless,
                gui=gui,
                avatar_callback=avatar_callback,
                start_chapter=1,
                **kwargs,
            )
            seen = len(chapters)
            if max_chapters and seen >= max_chapters:
                break
        time.sleep(poll)


def main(argv=None):
    require_admin_banner()
    # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
    parser = argparse.ArgumentParser(description='Replay storyboard')
    parser.add_argument('--storyboard')
    parser.add_argument('--import-demo')
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--gui', action='store_true')
    parser.add_argument('--audio-only', action='store_true')
    parser.add_argument('--avatar-callback')
    parser.add_argument('--show-subtitles', action='store_true')
    parser.add_argument('--chapter', type=int, default=1)
    parser.add_argument('--enable-gestures', action='store_true')
    parser.add_argument('--enable-sfx', action='store_true')
    parser.add_argument('--enable-env', action='store_true')
    parser.add_argument('--interpolate-voices', action='store_true')
    parser.add_argument('--dashboard', action='store_true')
    parser.add_argument('--timeline', action='store_true', help='Print chapter timeline')
    parser.add_argument('--feedback-enabled', action='store_true')
    parser.add_argument('--highlights-only', action='store_true')
    parser.add_argument('--branch', type=int)
    parser.add_argument('--live', action='store_true', help='Watch storyboard for new chapters')
    parser.add_argument('--poll', type=float, default=0.5)
    args = parser.parse_args(argv)
    sb_path = args.storyboard
    if args.import_demo:
        tmp = tempfile.mkdtemp()
        with zipfile.ZipFile(args.import_demo) as zf:
            zf.extractall(tmp)
        sb_path = str(Path(tmp) / 'storyboard.json')
    if not sb_path:
        parser.error('Storyboard required')
    dashboard_state = None
    if args.dashboard:
        app = run_dashboard(sb_path)
        dashboard_state = {"index": 0}
        app.config['dashboard_state'] = dashboard_state
        app.testing = False
        # run in background thread for simplicity
        import threading
        threading.Thread(target=lambda: app.run(port=5001), daemon=True).start()
    play_kwargs = dict(
        headless=args.headless,
        gui=args.gui,
        audio_only=args.audio_only,
        avatar_callback=args.avatar_callback,
        show_subtitles=args.show_subtitles,
        start_chapter=args.chapter,
        enable_gestures=args.enable_gestures,
        enable_sfx=args.enable_sfx,
        enable_env=args.enable_env,
        interpolate_voices=args.interpolate_voices,
        feedback_enabled=args.feedback_enabled,
        dashboard_state=dashboard_state,
        highlights_only=args.highlights_only,
        branch=args.branch,
    )
    if args.timeline:
        print_timeline(sb_path)
        return
    if args.live:
        live_playback(sb_path, poll=args.poll, **play_kwargs)
    else:
        playback(sb_path, **play_kwargs)


if __name__ == '__main__':
    main()
