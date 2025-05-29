import argparse
import json
import time
from pathlib import Path


def playback(storyboard: str, headless: bool = False, gui: bool = False, audio_only: bool = False) -> None:
    data = json.loads(Path(storyboard).read_text())
    for ch in data.get('chapters', []):
        print(f"Chapter {ch.get('chapter')}: {ch.get('title','')}")
        if not audio_only:
            txt = ch.get('text', '')
            if txt:
                print(txt)
        if not headless and ch.get('audio'):
            print(f"[PLAY] {ch['audio']}")
        if not headless and gui and ch.get('image'):
            print(f"[IMAGE] {ch['image']}")
        time.sleep(0.1)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Replay storyboard')
    parser.add_argument('--storyboard', required=True)
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--gui', action='store_true')
    parser.add_argument('--audio-only', action='store_true')
    args = parser.parse_args(argv)
    playback(args.storyboard, headless=args.headless, gui=args.gui, audio_only=args.audio_only)


if __name__ == '__main__':
    main()
