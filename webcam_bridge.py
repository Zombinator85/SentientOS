import os
import time
from dotenv import load_dotenv

try:
    import cv2
    from fer import FER
except Exception as e:  # pragma: no cover
    cv2 = None
    FER = None

from memory_manager import write_mem
from epu import EPU

load_dotenv()

INTERVAL = float(os.getenv("WEBCAM_INTERVAL", "2"))


def main():
    if cv2 is None or FER is None:
        raise RuntimeError("opencv-python and fer are required for webcam bridge")
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise RuntimeError("Webcam not available")
    detector = FER()
    epu = EPU()
    print("[WEB] Webcam bridge started")
    while True:
        ret, frame = cap.read()
        if not ret:
            time.sleep(INTERVAL)
            continue
        result = detector.top_emotion(frame)
        if result:
            label, score = result
        else:
            label, score = "neutral", 1.0
        epu.update_video(label, score)
        write_mem(f"Video emotion: {label} {score:.2f}", tags=["video"], source="webcam")
        print("Fused state:", epu.get_epu_state())
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
