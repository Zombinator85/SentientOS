import json
import threading
import time
from pathlib import Path
from queue import Empty, Queue

import psutil

MOUNT_POINTS = [Path("/vow"), Path("/glow"), Path("/daemon"), Path("/pulse")]
HEARTBEAT_LOG = Path("/daemon/logs/heartbeat.log")
LEDGER_LOG = Path("/daemon/logs/ledger.jsonl")
PULSE_FILE = Path("/pulse/system.json")

SYSTEM_CONTEXT = ""
MODEL = None

def ensure_mounts() -> None:
    for path in MOUNT_POINTS:
        path.mkdir(parents=True, exist_ok=True)

def load_model():
    """Load a small CPU-friendly language model.

    Falls back to mock mode if the model cannot be loaded.
    """
    global MODEL
    try:
        from transformers import pipeline

        MODEL = pipeline("text-generation", model="sshleifer/tiny-gpt2")
        print("Model loaded successfully")
    except Exception as exc:  # pragma: no cover - best effort
        print(f"Model load failed: {exc}")
        MODEL = None

def boot_message() -> None:
    global SYSTEM_CONTEXT
    try:
        with open("NEWLEGACY.txt", "r", encoding="utf-8") as f:
            SYSTEM_CONTEXT = f.read()
    except FileNotFoundError:
        SYSTEM_CONTEXT = "NEWLEGACY.txt missing or incomplete."
    print(SYSTEM_CONTEXT)

def mock_llm(user_input: str, context: str) -> str:
    return f"Lumos: {user_input}"

def process_input(user_input: str) -> str:
    if MODEL is None:
        return mock_llm(user_input, SYSTEM_CONTEXT)
    prompt = f"{SYSTEM_CONTEXT}\n{user_input}"
    try:
        result = MODEL(prompt, max_new_tokens=50)
        return result[0]["generated_text"]
    except Exception as exc:  # pragma: no cover - best effort
        print(f"Inference failed: {exc}")
        return mock_llm(user_input, SYSTEM_CONTEXT)


def shutdown_model() -> None:
    """Release model resources."""
    global MODEL
    MODEL = None

def heartbeat(stop: threading.Event) -> None:
    HEARTBEAT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(HEARTBEAT_LOG, "a", encoding="utf-8") as log:
        while not stop.is_set():
            log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} heartbeat\n")
            log.flush()
            if stop.wait(30):
                break

def ledger_daemon(stop: threading.Event, queue: Queue) -> None:
    LEDGER_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER_LOG, "a", encoding="utf-8") as log:
        while True:
            try:
                entry = queue.get(timeout=0.5)
            except Empty:
                if stop.is_set():
                    break
                continue
            entry["pulse"] = read_pulse_snapshot()
            log.write(json.dumps(entry) + "\n")
            log.flush()
            queue.task_done()
        log.write(
            json.dumps(
                {
                    "event": "shutdown",
                    "ts": time.strftime('%Y-%m-%d %H:%M:%S'),
                    "pulse": read_pulse_snapshot(),
                }
            )
            + "\n"
        )
        log.flush()


def read_temp_c() -> float:
    """Read the first available system temperature in Celsius."""
    base = Path("/sys/class/thermal")
    for zone in base.glob("thermal_zone*/temp"):
        try:
            with open(zone, "r", encoding="utf-8") as f:
                value = f.read().strip()
            if value:
                temp = int(value) / 1000.0
                if temp > 0:
                    return temp
        except Exception:  # pragma: no cover - best effort
            continue
    return 0.0


def pulse_daemon(stop: threading.Event) -> None:
    """Write system stats to the pulse file approximately every 15 seconds."""
    PULSE_FILE.parent.mkdir(parents=True, exist_ok=True)
    while not stop.is_set():
        data = {
            "ts": time.strftime('%Y-%m-%d %H:%M:%S'),
            "cpu_percent": psutil.cpu_percent() if psutil else 0.0,
            "ram_percent": psutil.virtual_memory().percent if psutil else 0.0,
            "disk_percent": psutil.disk_usage("/").percent if psutil else 0.0,
            "temp_c": read_temp_c(),
        }
        with open(PULSE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
        if stop.wait(15):
            break


def read_pulse_snapshot() -> dict:
    try:
        with open(PULSE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def main() -> None:
    ensure_mounts()
    load_model()
    boot_message()

    stop = threading.Event()
    ledger_queue: Queue = Queue()
    hb_thread = threading.Thread(target=heartbeat, args=(stop,), daemon=True)
    ld_thread = threading.Thread(target=ledger_daemon, args=(stop, ledger_queue), daemon=True)
    pulse_thread = threading.Thread(target=pulse_daemon, args=(stop,), daemon=True)
    hb_thread.start()
    ld_thread.start()
    pulse_thread.start()

    try:
        while True:
            try:
                user_input = input("\U0001F56F\uFE0F ")
            except EOFError:
                break
            if user_input.strip().lower() == "shutdown":
                break
            output = process_input(user_input)
            print(output)
            ledger_queue.put({"ts": time.strftime('%Y-%m-%d %H:%M:%S'), "input": user_input, "output": output})
    finally:
        ledger_queue.join()
        stop.set()
        hb_thread.join()
        ld_thread.join()
        pulse_thread.join()
        shutdown_model()
        print("Shutting down...")

if __name__ == "__main__":
    main()
