import argparse
import json
import time
import subprocess
from pathlib import Path


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


def playback(
    storyboard: str,
    headless: bool = False,
    gui: bool = False,
    audio_only: bool = False,
    avatar_callback: str | None = None,
    show_subtitles: bool = False,
    start_chapter: int = 1,
) -> None:
    data = json.loads(Path(storyboard).read_text())
    chapters = data.get("chapters", [])
    total = len(chapters)
    for ch in chapters[start_chapter - 1 :]:
        num = ch.get("chapter") or chapters.index(ch) + 1
        title = ch.get("title", "")
        emotion = ch.get("mood") or ch.get("emotion", "neutral")
        persona = ch.get("voice") or ch.get("persona", "")
        ts = ch.get("t_start", 0)
        _trigger_avatar(emotion, persona, ts, avatar_callback)
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


def main(argv=None):
    parser = argparse.ArgumentParser(description='Replay storyboard')
    parser.add_argument('--storyboard', required=True)
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--gui', action='store_true')
    parser.add_argument('--audio-only', action='store_true')
    parser.add_argument('--avatar-callback')
    parser.add_argument('--show-subtitles', action='store_true')
    parser.add_argument('--chapter', type=int, default=1)
    args = parser.parse_args(argv)
    playback(
        args.storyboard,
        headless=args.headless,
        gui=args.gui,
        audio_only=args.audio_only,
        avatar_callback=args.avatar_callback,
        show_subtitles=args.show_subtitles,
        start_chapter=args.chapter,
    )


if __name__ == '__main__':
    main()
