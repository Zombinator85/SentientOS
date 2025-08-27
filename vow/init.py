import json
import threading
import time
from pathlib import Path
from queue import Empty, Queue

MOUNT_POINTS = [Path("/vow"), Path("/glow"), Path("/daemon"), Path("/pulse")]
HEARTBEAT_LOG = Path("/daemon/logs/heartbeat.log")
LEDGER_LOG = Path("/daemon/logs/ledger.jsonl")
SYSTEM_CONTEXT = ""

def ensure_mounts() -> None:
    for path in MOUNT_POINTS:
        path.mkdir(parents=True, exist_ok=True)

def load_model():
    print("Loading GPT-OSS model (placeholder)")
    return object()

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
    return mock_llm(user_input, SYSTEM_CONTEXT)

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
            log.write(json.dumps(entry) + "\n")
            log.flush()
            queue.task_done()
        log.write(json.dumps({"event": "shutdown", "ts": time.strftime('%Y-%m-%d %H:%M:%S')}) + "\n")
        log.flush()

def main() -> None:
    ensure_mounts()
    load_model()
    boot_message()

    stop = threading.Event()
    ledger_queue: Queue = Queue()
    hb_thread = threading.Thread(target=heartbeat, args=(stop,), daemon=True)
    ld_thread = threading.Thread(target=ledger_daemon, args=(stop, ledger_queue), daemon=True)
    hb_thread.start()
    ld_thread.start()

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
        print("Shutting down...")

if __name__ == "__main__":
    main()
