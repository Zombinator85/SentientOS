import os
import requests
from emotions import empty_emotion_vector
from mic_bridge import recognize_from_mic
from tts_bridge import speak_async, stop

RELAY_URL = os.getenv("RELAY_URL", "http://localhost:5000/relay")
RELAY_SECRET = os.getenv("RELAY_SECRET", "test-secret")
VOICE_MODEL = os.getenv("VOICE_MODEL", "openai/gpt-4o")


def run_loop():  # pragma: no cover - runs indefinitely
    print("[VOICE LOOP] Starting. Press Ctrl+C to exit.")
    while True:
        result = recognize_from_mic()
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
            reply = " ".join(reply_chunks)
        except Exception as e:
            reply = f"Error contacting relay: {e}"
        t = speak_async(reply, emotions=emotions)
        while t.is_alive():
            intr = recognize_from_mic(save_audio=False)
            if intr.get("message"):
                stop()
                t.join()
                text = intr["message"]
                emotions = intr.get("emotions") or empty_emotion_vector()
                payload = {"message": text, "model": VOICE_MODEL, "emotions": emotions}
                try:
                    resp = requests.post(
                        RELAY_URL,
                        json=payload,
                        headers={"X-Relay-Secret": RELAY_SECRET},
                        timeout=180,
                    )
                    resp.raise_for_status()
                    reply_chunks = resp.json().get("reply_chunks", [])
                    reply = " ".join(reply_chunks)
                except Exception as e:
                    reply = f"Error contacting relay: {e}"
                t = speak_async(reply, emotions=emotions)
        t.join()


if __name__ == "__main__":  # pragma: no cover - manual utility
    run_loop()

