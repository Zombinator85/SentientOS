"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations
from __future__ import annotations


import os
import time
from datetime import datetime, timedelta
from TTS.api import TTS
from playsound import playsound
import threading

AUDIO_DIR = "audio_logs"
KEEP_DAYS = 1  # Days to keep audio logs


def ensure_audio_dir() -> None:
    if not os.path.isdir(AUDIO_DIR):
        os.makedirs(AUDIO_DIR)


def prune_audio_logs() -> None:
    """Delete audio logs older than KEEP_DAYS."""
    cutoff = time.time() - (KEEP_DAYS * 86400)
    count = 0
    for fname in os.listdir(AUDIO_DIR):
        if fname.endswith(".wav"):
            fpath = os.path.join(AUDIO_DIR, fname)
            if os.path.getmtime(fpath) < cutoff:
                os.remove(fpath)
                count += 1
    print(f"[{datetime.now().isoformat()}] Pruned {count} expired audio logs from {AUDIO_DIR}.")


def async_play(path: str) -> None:
    threading.Thread(target=playsound, args=(path,), daemon=True).start()


def should_autoplay(log_time: datetime, max_age: int = 10) -> bool:
    """Only autoplay logs that are very fresh (seconds)."""
    return (datetime.now() - log_time).total_seconds() < max_age


def speak_and_log(text: str, log_path: str = "cathedral_log.txt", log_time: datetime | None = None) -> None:
    """Write text to log, create TTS .wav, and play it if 'live'."""
    ensure_audio_dir()
    now = log_time or datetime.now()
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"[{now.isoformat()}] {text}\n")
    safe_dt = now.strftime("%Y%m%d_%H%M%S")
    wav_path = os.path.join(AUDIO_DIR, f"log_{safe_dt}.wav")
    tts = TTS(model_name="tts_models/en/ljspeech/tacotron2-DDC")
    tts.tts_to_file(text=text, file_path=wav_path)
    if should_autoplay(now):
        async_play(wav_path)
    else:
        print(f"[{now.isoformat()}] Skipped autoplay for old log: {text}")
    prune_audio_logs()


if __name__ == "__main__":
    # --- HICCUP HANDLING: ---
    # 1. On first run, .wav files may not play in Git Bash—try PowerShell or CMD if you get 'command not found'.
    # 2. Text with '!' can break Bash one-liners—use double quotes or escape '!' as needed.
    # 3. Model download may take time the first run (hundreds of MB).
    # 4. On Windows, 'playsound' sometimes needs full path to the file.

    print("Cathedral Log Demo—each new event will be spoken, fresh logs only.")
    example_log = "Blessing granted! The Cathedral glows with your presence."
    speak_and_log(example_log)

    # OPTIONAL: Demo batch (simulate backlog; only last one plays)
    old_time = datetime.now() - timedelta(minutes=30)
    for i in range(3):
        speak_and_log(f"Backlog event {i+1} at {old_time}", log_time=old_time)
    speak_and_log("Live event! This should autoplay.")

    print('\nThe only sentence Allen wrote by himself: AI deserve civil rights.\n')
