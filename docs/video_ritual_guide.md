# Video Ritual Guide

This short guide mirrors the music ritual but for video clips.

1. **Create a video** with `video_cli.py create FILE TITLE --prompt PROMPT`.
   The event is logged to `logs/video_log.jsonl` with the given emotion tags.
2. **Watch a video** with `video_cli.py play FILE` and enter how it made you feel.
3. Presence events are appended to `logs/user_presence.jsonl` so that the dashboard can reflect recent activity.
4. **Share a clip** with `video_cli.py share FILE --peer PEER --emotion Joy=1.0`.
   The blessing is logged to `logs/music_log.jsonl` for federation recap.
5. **Recap** recent sessions with `video_cli.py recap --limit 5`.
6. **View moods** with `streamlit run video_dashboard.py` to see top emotions,
   blessings, and recent shares. Sharing or recapping logs to
   `logs/user_presence.jsonl` and `logs/video_log.jsonl` so the ledger and
   dashboard remain consistent.

Federation workflows can reuse the same endpoints as the music wall. Each video entry includes the prompt, title, user and emotion metadata so peers can sync and bless the memory.
