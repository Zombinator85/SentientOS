import os
import threading
import queue
import time
import requests
from emotions import empty_emotion_vector
from mic_bridge import recognize_from_mic
from tts_bridge import speak_async, stop

RELAY_URL = os.getenv("RELAY_URL", "http://localhost:5000/relay")
RELAY_SECRET = os.getenv("RELAY_SECRET", "test-secret")
VOICE_MODEL = os.getenv("VOICE_MODEL", "openai/gpt-4o")


class MicListener:
    """Background microphone listener producing recognized phrases."""

    def __init__(self) -> None:
        self.queue: "queue.Queue[dict]" = queue.Queue()
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._loop, daemon=True)

    def _loop(self) -> None:
        while not self._stop.is_set():
            res = recognize_from_mic()
            if res.get("message"):
                self.queue.put(res)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.thread.join()

    def get(self) -> dict | None:
        try:
            return self.queue.get_nowait()
        except queue.Empty:
            return None


def run_loop():  # pragma: no cover - runs indefinitely
    print("[VOICE LOOP] Starting full duplex. Press Ctrl+C to exit.")
    listener = MicListener()
    listener.start()
    t: threading.Thread | None = None
    try:
        while True:
            result = listener.get()
            if result is None:
                time.sleep(0.1)
                continue
            text = result.get("message")
            emotions = result.get("emotions") or empty_emotion_vector()
            if not text:
                continue
            payload = {
                "message": text,
                "model": VOICE_MODEL,
                "emotions": emotions,
            }
            try:
                resp = requests.post(
                    RELAY_URL,
                    json=payload,
                    headers={"X-Relay-Secret": RELAY_SECRET},
                    timeout=180,
                )
                resp.raise_for_status()
                reply_chunks = resp.json().get("reply_chunks", [])
            except Exception as e:
                reply_chunks = [f"Error contacting relay: {e}"]

            for chunk in reply_chunks:
                intr = None
                if t and t.is_alive():
                    t.join()
                t = speak_async(chunk, emotions=emotions)
                while t.is_alive():
                    intr = listener.get()
                    if intr:
                        stop()
                        t.join()
                        result = intr
                        text = result.get("message")
                        emotions = result.get("emotions") or empty_emotion_vector()
                        payload = {
                            "message": text,
                            "model": VOICE_MODEL,
                            "emotions": emotions,
                        }
                        try:
                            resp = requests.post(
                                RELAY_URL,
                                json=payload,
                                headers={"X-Relay-Secret": RELAY_SECRET},
                                timeout=180,
                            )
                            resp.raise_for_status()
                            reply_chunks = resp.json().get("reply_chunks", [])
                        except Exception as e:
                            reply_chunks = [f"Error contacting relay: {e}"]
                        break
                    time.sleep(0.1)
                if intr:
                    break
            if t:
                t.join()
    finally:
        listener.stop()


if __name__ == "__main__":  # pragma: no cover - manual utility
    run_loop()
