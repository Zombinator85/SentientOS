import argparse
import datetime as dt
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

import narrator
try:
    import tts_bridge
except Exception:  # pragma: no cover - optional
    tts_bridge = None


def parse_time(ts: str) -> dt.datetime:
    return dt.datetime.fromisoformat(ts)


def _load_entries(path: Path, start: dt.datetime, end: dt.datetime) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    if not path.exists():
        return entries
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except Exception:
            continue
        ts = data.get('timestamp')
        if not isinstance(ts, str):
            continue
        try:
            t = dt.datetime.fromisoformat(ts.replace('Z', ''))
        except Exception:
            continue
        if start <= t <= end:
            entries.append(data)
    return entries


def load_logs(start: dt.datetime, end: dt.datetime, log_dir: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    mem = _load_entries(log_dir / 'memory.jsonl', start, end)
    refl = _load_entries(log_dir / 'reflection.jsonl', start, end)
    emo = _load_entries(log_dir / 'emotions.jsonl', start, end)
    return mem, refl, emo


def assemble_prompt(start: dt.datetime, end: dt.datetime, mood: str, events: List[Dict[str, Any]], reflections: List[Dict[str, Any]]) -> str:
    lines = [
        f'Time range: {start.isoformat()} to {end.isoformat()}',
        f'System mood: {mood}',
        f'Narration style: {mood}',
        'Events:',
    ]
    for e in events:
        ts = e.get('timestamp', '?')
        txt = str(e.get('text', '')).strip().replace('\n', ' ')
        lines.append(f'- {ts} {txt}')
    if reflections:
        lines.append('Reflections:')
        for r in reflections:
            ts = r.get('timestamp', '?')
            txt = str(r.get('text', '')).strip().replace('\n', ' ')
            lines.append(f'- {ts} {txt}')
    lines.append('Please summarize the system experience in a human-like story.')
    return '\n'.join(lines)


def generate_narrative(start: dt.datetime, end: dt.datetime, mem: List[Dict[str, Any]], refl: List[Dict[str, Any]], emo: List[Dict[str, Any]], dry_run: bool = False) -> Tuple[str, str]:
    mood = narrator.infer_mood(mem + emo)
    prompt = assemble_prompt(start, end, mood, mem, refl)
    narrative = narrator.generate_narrative(prompt, dry_run=dry_run)
    return narrative, mood


def synthesize(text: str, mood: str, path: Path, voice: Optional[str], dry_run: bool = False) -> Optional[str]:
    if tts_bridge is None:
        return None
    return tts_bridge.speak(text, voice=voice, save_path=str(path), emotions={mood: 1.0})


def record_screen(duration: int, video_path: str, dry_run: bool = False) -> None:
    cmd = [
        'ffmpeg', '-y', '-video_size', os.getenv('STORY_RES', '1024x768'),
        '-framerate', '25', '-f', 'x11grab', '-i', os.getenv('DISPLAY', ':0.0'),
        '-t', str(duration), video_path
    ]
    if dry_run:
        Path(video_path).touch()
        print('[Storymaker] DRY RUN record:', ' '.join(cmd))
        return
    try:
        subprocess.run(cmd, check=False)
    except Exception:
        pass


def mux_audio_video(audio_path: str, video_path: str, output_path: str, dry_run: bool = False) -> None:
    cmd = ['ffmpeg', '-y', '-i', video_path, '-i', audio_path, '-c:v', 'copy', '-c:a', 'aac', output_path]
    if dry_run:
        Path(output_path).touch()
        print('[Storymaker] DRY RUN mux:', ' '.join(cmd))
        return
    try:
        subprocess.run(cmd, check=False)
    except Exception:
        pass


def run_pipeline(start: str, end: str, output: str, log_dir: Path, voice: Optional[str] = None, dry_run: bool = False) -> Tuple[str, Optional[str], Optional[str]]:
    start_dt = parse_time(start)
    end_dt = parse_time(end)
    mem, refl, emo = load_logs(start_dt, end_dt, log_dir)
    narrative, mood = generate_narrative(start_dt, end_dt, mem, refl, emo, dry_run=dry_run)
    audio_path = synthesize(narrative, mood, Path(output).with_suffix('.mp3'), voice, dry_run=dry_run)
    if dry_run:
        print(narrative)
        return narrative, audio_path, None
    video_tmp = str(Path(output).with_suffix('.video.mp4'))
    record_screen(int(os.getenv('STORY_DURATION', '5')), video_tmp, dry_run=dry_run)
    if audio_path:
        mux_audio_video(audio_path, video_tmp, output, dry_run=dry_run)
    else:
        os.rename(video_tmp, output)
    return narrative, audio_path, output


def main(argv: List[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description='Generate storybook demo from logs')
    parser.add_argument('--from', dest='start', required=True, help="Start time 'YYYY-MM-DD HH:MM'")
    parser.add_argument('--to', dest='end', required=True, help="End time 'YYYY-MM-DD HH:MM'")
    parser.add_argument('--output', default='demo.mp4')
    parser.add_argument('--log-dir', default='logs')
    parser.add_argument('--voice')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    run_pipeline(args.start, args.end, args.output, Path(args.log_dir), voice=args.voice, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
