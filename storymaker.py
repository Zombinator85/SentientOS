import argparse
import datetime as dt
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional
import time
import csv
import zipfile

from dataclasses import dataclass

import narrator
try:
    import tts_bridge
except Exception:  # pragma: no cover - optional
    tts_bridge = None


def parse_time(ts: str) -> dt.datetime:
    return dt.datetime.fromisoformat(ts)


@dataclass
class Chapter:
    start: dt.datetime
    end: dt.datetime
    memory: List[Dict[str, Any]]
    reflection: List[Dict[str, Any]]
    emotions: List[Dict[str, Any]]
    text: str = ""
    mood: str = ""
    audio: Optional[str] = None
    video: Optional[str] = None
    voice: Optional[str] = None
    image: Optional[str] = None
    sfx: Optional[str] = None
    gesture: Optional[str] = None
    env: Optional[str] = None
    t_start: float = 0.0  # relative start time in seconds
    t_end: float = 0.0    # relative end time in seconds
    user: Optional[str] = None
    persona: Optional[str] = None
    fork_of: Optional[int] = None
    branch: Optional[str] = None
    highlight: bool = False


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


def _merge_entries(mem: List[Dict[str, Any]], refl: List[Dict[str, Any]], emo: List[Dict[str, Any]]) -> List[Tuple[dt.datetime, str, Dict[str, Any]]]:
    merged: List[Tuple[dt.datetime, str, Dict[str, Any]]] = []
    for src, lst in [('memory', mem), ('reflection', refl), ('emotion', emo)]:
        for e in lst:
            ts = e.get('timestamp')
            if not isinstance(ts, str):
                continue
            try:
                t = dt.datetime.fromisoformat(ts.replace('Z', ''))
            except Exception:
                continue
            merged.append((t, src, e))
    merged.sort(key=lambda x: x[0])
    return merged


def segment_chapters(mem: List[Dict[str, Any]], refl: List[Dict[str, Any]], emo: List[Dict[str, Any]], gap_minutes: int = 60) -> List[Chapter]:
    entries = _merge_entries(mem, refl, emo)
    chapters: List[Chapter] = []
    cur: List[Tuple[dt.datetime, str, Dict[str, Any]]] = []
    prev_time: Optional[dt.datetime] = None
    for item in entries:
        t, _, _ = item
        if prev_time and (t - prev_time).total_seconds() / 60 > gap_minutes and cur:
            chapters.append(_build_chapter(cur))
            cur = []
        cur.append(item)
        prev_time = t
    if cur:
        chapters.append(_build_chapter(cur))
    return chapters


def _build_chapter(items: List[Tuple[dt.datetime, str, Dict[str, Any]]]) -> Chapter:
    mem = [e for t, s, e in items if s == 'memory']
    refl = [e for t, s, e in items if s == 'reflection']
    emo = [e for t, s, e in items if s == 'emotion']
    start = items[0][0]
    end = items[-1][0]
    return Chapter(start, end, mem, refl, emo)


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


def generate_chapter_narrative(ch: Chapter, dry_run: bool = False) -> Chapter:
    text, mood = generate_narrative(ch.start, ch.end, ch.memory, ch.reflection, ch.emotions, dry_run=dry_run)
    ch.text = text
    ch.mood = mood
    return ch


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


def write_srt(chapters: List[Chapter], path: Path) -> None:
    compute_relative_times(chapters)
    lines: List[str] = []
    idx = 1
    for ch in chapters:
        start = dt.timedelta(seconds=ch.t_start)
        end = dt.timedelta(seconds=ch.t_end)
        lines.append(str(idx))
        lines.append(f"{_fmt_ts(start)} --> {_fmt_ts(end)}")
        lines.append(ch.text)
        lines.append("")
        idx += 1
    path.write_text("\n".join(lines), encoding="utf-8")


def write_transcript(chapters: List[Chapter], path: Path) -> None:
    compute_relative_times(chapters)
    lines = []
    for ch in chapters:
        start = dt.timedelta(seconds=ch.t_start)
        end = dt.timedelta(seconds=ch.t_end)
        lines.append(f"[{_fmt_ts(start)} - {_fmt_ts(end)}] {ch.text}")
    path.write_text("\n".join(lines), encoding="utf-8")


def _fmt_ts(td: dt.timedelta) -> str:
    total_ms = int(td.total_seconds() * 1000)
    hours, rem = divmod(total_ms, 3600 * 1000)
    minutes, rem = divmod(rem, 60 * 1000)
    seconds, ms = divmod(rem, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{ms:03}"


def dominant_emotion(entries: List[Dict[str, Any]]) -> Tuple[str, Optional[float], Optional[float]]:
    scores: Dict[str, float] = {}
    vals: List[float] = []
    ars: List[float] = []
    for e in entries:
        emo = e.get('emotions', {})
        if isinstance(emo, dict) and emo:
            lab = max(emo, key=emo.get)
            scores[lab] = scores.get(lab, 0.0) + float(emo[lab])
        feat = e.get('features') or e.get('emotion_features') or {}
        if isinstance(feat, dict):
            v = feat.get('valence')
            a = feat.get('arousal')
            if isinstance(v, (int, float)):
                vals.append(float(v))
            if isinstance(a, (int, float)):
                ars.append(float(a))
    mood = max(scores, key=scores.get).lower() if scores else 'neutral'
    valence = sum(vals) / len(vals) if vals else None
    arousal = sum(ars) / len(ars) if ars else None
    return mood, arousal, valence


def write_emotion_data(chapters: List[Chapter], overall_mood: str, voice: Optional[str], path: Path) -> None:
    data = {
        'overall': {
            'mood': overall_mood,
            'voice': voice or (getattr(tts_bridge, 'CURRENT_PERSONA', None) if tts_bridge else None),
        },
        'chapters': []
    }
    for i, ch in enumerate(chapters, 1):
        mood, arousal, valence = dominant_emotion(ch.emotions)
        data['chapters'].append({
            'chapter': i,
            'start': ch.start.isoformat(),
            'end': ch.end.isoformat(),
            'voice': ch.voice,
            'mood': mood,
            'arousal': arousal,
            'valence': valence,
        })
    path.write_text(json.dumps(data, indent=2), encoding='utf-8')


def write_sync_metadata(chapters: List[Chapter], path: Path) -> None:
    data = [
        {'chapter': i + 1, 'start': ch.t_start, 'end': ch.t_end}
        for i, ch in enumerate(chapters)
    ]
    path.write_text(json.dumps(data, indent=2), encoding='utf-8')


def generate_scene_image(
    prompt: str,
    out_path: Path,
    dry_run: bool = False,
    image_cmd: Optional[str] = None,
    image_api: Optional[str] = None,
) -> None:
    """Generate a scene illustration using a command, API, or placeholder."""
    if image_cmd:
        cmd = image_cmd.format(prompt=prompt, out=str(out_path))
        if dry_run:
            print("[Storymaker] DRY RUN image cmd:", cmd)
            out_path.write_text("image")
            return
        try:
            subprocess.run(cmd, shell=True, check=False)
            return
        except Exception:
            pass
    if image_api:
        if dry_run:
            print("[Storymaker] DRY RUN image api:", image_api, prompt)
            out_path.write_text("image")
            return
        try:
            import requests  # type: ignore
            resp = requests.post(image_api, json={"prompt": prompt}, timeout=30)
            if resp.status_code == 200:
                out_path.write_bytes(resp.content)
                return
        except Exception:
            pass
    if dry_run:
        out_path.write_text("image")
        return
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (320, 240), color="black")
        d = ImageDraw.Draw(img)
        d.text((10, 10), prompt[:40], fill=(255, 255, 255))
        img.save(out_path)
    except Exception:
        out_path.touch()


def compute_relative_times(chapters: List[Chapter]) -> None:
    t0 = dt.timedelta()
    for ch in chapters:
        duration = dt.timedelta(seconds=len(ch.text.split()) / 2.0)
        ch.t_start = t0.total_seconds()
        ch.t_end = (t0 + duration).total_seconds()
        t0 += duration


def run_pipeline(
    start: str,
    end: str,
    output: str,
    log_dir: Path,
    voice: Optional[str] = None,
    dry_run: bool = False,
    chapters: bool = False,
    subtitle: Optional[str] = None,
    transcript: Optional[str] = None,
    storyboard: Optional[str] = None,
    emotion_data: Optional[str] = None,
    sync_metadata: Optional[str] = None,
    scene_images: bool = False,
    image_cmd: Optional[str] = None,
    image_api: Optional[str] = None,
    user: Optional[str] = None,
    persona: Optional[str] = None,
    fork: Optional[int] = None,
    branch: Optional[str] = None,
    highlight: Optional[List[int]] = None,
) -> Tuple[str, Optional[str], Optional[str]]:
    start_dt = parse_time(start)
    end_dt = parse_time(end)
    mem, refl, emo = load_logs(start_dt, end_dt, log_dir)
    overall_mood = narrator.infer_mood(mem + emo)

    if chapters:
        ch_list = [generate_chapter_narrative(ch, dry_run=dry_run) for ch in segment_chapters(mem, refl, emo)]
        combined = "\n".join(ch.text for ch in ch_list)
        for idx, ch in enumerate(ch_list, 1):
            base = Path(output).with_name(f"{Path(output).stem}_ch{idx}{Path(output).suffix}")
            ch.audio = synthesize(ch.text, ch.mood, base.with_suffix('.mp3'), voice, dry_run=dry_run)
            ch.voice = voice or (getattr(tts_bridge, 'CURRENT_PERSONA', None) if tts_bridge else None)
            ch.user = user
            ch.persona = persona
            if highlight and idx in highlight:
                ch.highlight = True
            if dry_run:
                print(ch.text)
                ch.video = None
            else:
                tmp_vid = str(base.with_suffix('.video.mp4'))
                record_screen(int(os.getenv('STORY_DURATION', '5')), tmp_vid, dry_run=dry_run)
                if ch.audio:
                    mux_audio_video(ch.audio, tmp_vid, str(base), dry_run=dry_run)
                else:
                    os.rename(tmp_vid, base)
                ch.video = str(base)
            if scene_images:
                img_path = base.with_name(f"chapter_{idx}.png")
                generate_scene_image(
                    f"{ch.mood} {ch.memory[0].get('text','') if ch.memory else ''}",
                    img_path,
                    dry_run=dry_run,
                    image_cmd=image_cmd,
                    image_api=image_api,
                )
                ch.image = str(img_path)
        if fork is not None:
            fb = Chapter(start_dt, end_dt, [], [], [], text=branch or "", mood="neutral")
            fb.user = user
            fb.persona = persona
            fb.fork_of = fork
            fb.branch = branch
            if highlight and len(ch_list) + 1 in highlight:
                fb.highlight = True
            ch_list.append(fb)
        compute_relative_times(ch_list)
        if subtitle:
            write_srt(ch_list, Path(subtitle))
        if transcript:
            write_transcript(ch_list, Path(transcript))
        if storyboard:
            data = [{
                'chapter': i + 1,
                'title': (ch.memory[0].get('text', '') if ch.memory else '')[:30],
                'start': ch.start.isoformat(),
                'end': ch.end.isoformat(),
                'audio': ch.audio,
                'video': ch.video,
                'mood': ch.mood,
                't_start': ch.t_start,
                't_end': ch.t_end,
                'image': ch.image,
                'sfx': ch.sfx,
                'gesture': ch.gesture,
                'env': ch.env,
                'user': ch.user,
                'persona': ch.persona,
                'highlight': ch.highlight,
                'fork_of': ch.fork_of,
                'branch': ch.branch,
            } for i, ch in enumerate(ch_list)]
            Path(storyboard).write_text(json.dumps({'chapters': data}, indent=2), encoding='utf-8')
        if emotion_data:
            write_emotion_data(ch_list, overall_mood, voice, Path(emotion_data))
        if sync_metadata:
            write_sync_metadata(ch_list, Path(sync_metadata))
        return combined, None, None if dry_run else output

    narrative, mood = generate_narrative(start_dt, end_dt, mem, refl, emo, dry_run=dry_run)
    audio_path = synthesize(narrative, mood, Path(output).with_suffix('.mp3'), voice, dry_run=dry_run)
    voice_used = voice or (getattr(tts_bridge, 'CURRENT_PERSONA', None) if tts_bridge else None)
    ch_single = Chapter(start_dt, end_dt, mem, refl, emo, text=narrative, mood=mood, audio=audio_path, voice=voice_used)
    ch_single.user = user
    ch_single.persona = persona
    if highlight and 1 in highlight:
        ch_single.highlight = True
    if fork is not None:
        ch_single.fork_of = fork
        ch_single.branch = branch
    compute_relative_times([ch_single])
    if dry_run:
        print(narrative)
        if subtitle:
            write_srt([ch_single], Path(subtitle))
        if transcript:
            write_transcript([ch_single], Path(transcript))
        if emotion_data:
            write_emotion_data([ch_single], mood, voice, Path(emotion_data))
        if sync_metadata:
            write_sync_metadata([ch_single], Path(sync_metadata))
        return narrative, audio_path, None
    video_tmp = str(Path(output).with_suffix('.video.mp4'))
    record_screen(int(os.getenv('STORY_DURATION', '5')), video_tmp, dry_run=dry_run)
    if audio_path:
        mux_audio_video(audio_path, video_tmp, output, dry_run=dry_run)
    else:
        os.rename(video_tmp, output)
    if subtitle:
        write_srt([ch_single], Path(subtitle))
    if transcript:
        write_transcript([ch_single], Path(transcript))
    if emotion_data:
        write_emotion_data([ch_single], mood, voice, Path(emotion_data))
    if sync_metadata:
        write_sync_metadata([ch_single], Path(sync_metadata))
    return narrative, audio_path, output


def export_demo_pack(storyboard_path: str, zip_path: str) -> None:
    """Package storyboard media and metadata into a demo ZIP."""
    sb = Path(storyboard_path)
    if not sb.exists():
        raise FileNotFoundError(storyboard_path)
    data = json.loads(sb.read_text())
    base = sb.parent
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(sb, arcname="storyboard.json")
        for ch in data.get("chapters", []):
            for key in ("audio", "video", "image"):
                fp = ch.get(key)
                if not fp:
                    continue
                path = base / fp if not os.path.isabs(fp) else Path(fp)
                if path.exists():
                    zf.write(path, arcname=path.name)
        for name in ("transcript.txt", "subtitle.srt"):
            p = base / name
            if p.exists():
                zf.write(p, arcname=name)


def compile_diary(start: str, end: str, log_dir: Path, output: str) -> None:
    """Compile a long-form diary from multiple chapters."""
    start_dt = parse_time(start)
    end_dt = parse_time(end)
    mem, refl, emo = load_logs(start_dt, end_dt, log_dir)
    chapters = segment_chapters(mem, refl, emo)
    lines = ["# Cathedral Diary"]
    for i, ch in enumerate(chapters, 1):
        generate_chapter_narrative(ch, dry_run=True)
        lines.append(f"\n## Chapter {i} ({ch.start.date()} - {ch.end.date()})\n")
        lines.append(ch.text)
    Path(output).write_text("\n".join(lines), encoding="utf-8")


def auto_storyboard(log_file: str, output: str) -> None:
    """Generate a simple storyboard from a raw log."""
    chapters = []
    with open(log_file, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            try:
                obj = json.loads(line)
            except Exception:
                continue
            chapters.append({
                "chapter": i,
                "title": str(obj.get("text", ""))[:30],
                "start": obj.get("timestamp"),
                "end": obj.get("timestamp"),
                "text": obj.get("text", ""),
            })
    Path(output).write_text(json.dumps({"chapters": chapters}, indent=2), encoding="utf-8")


def run_live(
    output: str,
    log_dir: Path,
    voice: Optional[str] = None,
    dry_run: bool = False,
    limit: int = 1,
    poll: float = 0.5,
    scene_images: bool = False,
    image_cmd: Optional[str] = None,
    image_api: Optional[str] = None,
    image_prompt_field: Optional[str] = None,
    user: Optional[str] = None,
    persona: Optional[str] = None,
) -> None:
    """Continuously capture new log events and append chapters."""
    sb = Path(output)
    chapters: List[Chapter] = []
    start = dt.datetime.min
    mem: List[Dict[str, Any]] = []
    refl: List[Dict[str, Any]] = []
    emo: List[Dict[str, Any]] = []
    while len(chapters) < limit:
        mem.extend(_load_entries(log_dir / "memory.jsonl", start, dt.datetime.utcnow()))
        refl.extend(_load_entries(log_dir / "reflection.jsonl", start, dt.datetime.utcnow()))
        emo.extend(_load_entries(log_dir / "emotions.jsonl", start, dt.datetime.utcnow()))
        if mem or refl or emo:
            ch = Chapter(start, dt.datetime.utcnow(), mem, refl, emo)
            generate_chapter_narrative(ch, dry_run=dry_run)
            ch.audio = synthesize(
                ch.text,
                ch.mood,
                sb.with_suffix(f".{len(chapters)+1}.mp3"),
                voice,
                dry_run=dry_run,
            )
            ch.voice = voice or (getattr(tts_bridge, "CURRENT_PERSONA", None) if tts_bridge else None)
            ch.user = user
            ch.persona = persona
            if scene_images:
                prompt = ""
                if ch.memory:
                    prompt = ch.memory[0].get(image_prompt_field or "text", "")
                img_path = sb.with_suffix(f".{len(chapters)+1}.png")
                generate_scene_image(prompt, img_path, dry_run=dry_run, image_cmd=image_cmd, image_api=image_api)
                ch.image = str(img_path)
            compute_relative_times([ch])
            chapters.append(ch)
            data = {
                "chapters": [
                    {
                        "chapter": i + 1,
                        "title": (c.memory[0].get("text", "") if c.memory else "")[:30],
                        "start": c.start.isoformat(),
                        "end": c.end.isoformat(),
                        "text": c.text,
                        "mood": c.mood,
                        "audio": c.audio,
                        "image": c.image,
                        "voice": c.voice,
                        "user": c.user,
                        "persona": c.persona,
                        "highlight": c.highlight,
                        "fork_of": c.fork_of,
                        "branch": c.branch,
                        "t_start": c.t_start,
                        "t_end": c.t_end,
                    }
                    for i, c in enumerate(chapters)
                ]
            }
            sb.write_text(json.dumps(data, indent=2), encoding="utf-8")
            mem = []
            refl = []
            emo = []
            start = dt.datetime.utcnow()
        time.sleep(poll)


def export_analytics(start: str, end: str, log_dir: Path, output: str) -> None:
    """Export emotion/persona analytics to a CSV file."""
    start_dt = parse_time(start)
    end_dt = parse_time(end)
    mem, refl, emo = load_logs(start_dt, end_dt, log_dir)
    chapters = segment_chapters(mem, refl, emo)
    compute_relative_times(chapters)
    with open(output, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["chapter", "start", "end", "duration", "mood", "voice"])
        for i, ch in enumerate(chapters, 1):
            mood, _, _ = dominant_emotion(ch.emotions)
            writer.writerow([
                i,
                ch.start.isoformat(),
                ch.end.isoformat(),
                round(ch.t_end - ch.t_start, 2),
                mood,
                ch.voice or "",
            ])


def main(argv: List[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description='Generate storybook demo from logs')
    parser.add_argument('--from', dest='start', required=True, help="Start time 'YYYY-MM-DD HH:MM'")
    parser.add_argument('--to', dest='end', required=True, help="End time 'YYYY-MM-DD HH:MM'")
    parser.add_argument('--output', default='demo.mp4')
    parser.add_argument('--log-dir', default='logs')
    parser.add_argument('--voice')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--chapters', action='store_true', help='Segment story into chapters')
    parser.add_argument('--subtitle')
    parser.add_argument('--transcript')
    parser.add_argument('--storyboard')
    parser.add_argument('--emotion-data')
    parser.add_argument('--sync-metadata')
    parser.add_argument('--scene-images', action='store_true', help='Generate experimental scene images')
    parser.add_argument('--image-cmd')
    parser.add_argument('--image-api')
    parser.add_argument('--image-prompt-field')
    parser.add_argument('--export-demo')
    parser.add_argument('--live', action='store_true', help='Capture logs in real time')
    parser.add_argument('--analytics', action='store_true', help='Export analytics CSV')
    parser.add_argument('--limit', type=int, default=1, help='Live mode chapter limit')
    parser.add_argument('--user')
    parser.add_argument('--persona')
    parser.add_argument('--fork', type=int)
    parser.add_argument('--branch')
    parser.add_argument('--highlight', type=int, action='append')
    parser.add_argument('--diary', action='store_true')
    parser.add_argument('--auto-storyboard', action='store_true')
    parser.add_argument('--log')
    args = parser.parse_args(argv)
    if args.analytics:
        export_analytics(args.start, args.end, Path(args.log_dir), args.output)
        return

    if args.diary:
        compile_diary(args.start, args.end, Path(args.log_dir), args.output)
        return

    if args.auto_storyboard and args.log:
        auto_storyboard(args.log, args.output)
        return

    if args.live:
        run_live(
            args.output,
            Path(args.log_dir),
            voice=args.voice,
            dry_run=args.dry_run,
            limit=args.limit,
            scene_images=args.scene_images,
            image_cmd=args.image_cmd,
            image_api=args.image_api,
            image_prompt_field=args.image_prompt_field,
            user=args.user,
            persona=args.persona,
        )
    else:
        run_pipeline(
            args.start,
            args.end,
            args.output,
            Path(args.log_dir),
            voice=args.voice,
            dry_run=args.dry_run,
            chapters=args.chapters,
            subtitle=args.subtitle,
            transcript=args.transcript,
            storyboard=args.storyboard,
            emotion_data=args.emotion_data,
            sync_metadata=args.sync_metadata,
            scene_images=args.scene_images,
            image_cmd=args.image_cmd,
            image_api=args.image_api,
            user=args.user,
            persona=args.persona,
            fork=args.fork,
            branch=args.branch,
            highlight=args.highlight,
        )
        if args.export_demo and args.storyboard:
            export_demo_pack(args.storyboard, args.export_demo)


if __name__ == '__main__':
    main()
