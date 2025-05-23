import os
import logging
import tempfile
import requests
import speech_recognition as sr
from dotenv import load_dotenv

from memory_manager import write_mem
from emotion_detector import detect_emotion

load_dotenv()

RELAY_URL = os.getenv("RELAY_URL")
RELAY_SECRET = os.getenv("RELAY_SECRET")
MODEL_SLUG = os.getenv("MODEL_SLUG", "openai/gpt-4o").strip().lower()
MIC_STT = os.getenv("MIC_STT", "google").strip().lower()

logging.basicConfig(level=logging.INFO)

r = sr.Recognizer()
mic = sr.Microphone()


def transcribe(audio: sr.AudioData) -> str:
    if MIC_STT == "sphinx":
        return r.recognize_sphinx(audio)
    return r.recognize_google(audio)


def main() -> None:
    while True:
        with mic as source:
            logging.info("Listening…")
            audio = r.listen(source)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio.get_wav_data())
            tmp_path = tmp.name
        emotion, score = detect_emotion(tmp_path)
        try:
            text = transcribe(audio)
        except Exception as e:
            logging.error(f"STT failed: {e}")
            os.unlink(tmp_path)
            continue
        os.unlink(tmp_path)
        logging.info(f"Heard: {text} [{emotion}:{score:.2f}]")
        write_mem(text, tags=["mic"], source=f"mic:{MODEL_SLUG}", emotion=emotion)
        try:
            res = requests.post(
                RELAY_URL,
                json={"message": text, "model": MODEL_SLUG, "emotion": emotion},
                headers={"X-Relay-Secret": RELAY_SECRET},
                timeout=60,
            )
            reply_chunks = res.json().get("reply_chunks", [])
            for chunk in reply_chunks:
                write_mem(chunk, tags=["mic"], source=f"relay:{MODEL_SLUG}")
                print(chunk)
        except Exception as e:
            logging.error(f"Relay error: {e}")


if __name__ == "__main__":
    main()
