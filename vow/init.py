import json
import os
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

MODEL_PATHS = {
    "120b": Path("/models/gpt-oss-120b-quantized"),
    "20b": Path("/models/gpt-oss-20b"),
    "13b": Path("/models/gpt-oss-13b"),
}

def ensure_mounts() -> None:
    for path in MOUNT_POINTS:
        path.mkdir(parents=True, exist_ok=True)

def load_model():
    """Load the preferred GPT-OSS model from SSD.

    Attempts to load the quantized 120B model first, falling back to 20B and
    13B as needed. If all attempts fail, the system operates in mock mode so it
    never bricks.
    """
    global MODEL
    preferred = os.environ.get("GPT_OSS_MODEL", "120b").lower()
    order = [preferred] + [s for s in ["120b", "20b", "13b"] if s != preferred]
    try:
        from transformers import pipeline
    except Exception as exc:  # pragma: no cover - best effort
        print(f"Transformers unavailable: {exc}")
        MODEL = None
        return

    for size in order:
        path = MODEL_PATHS.get(size)
        if not path:
            continue
        try:
            MODEL = pipeline("text-generation", model=str(path))
            print(f"GPT-OSS {size} model loaded successfully")
            return
        except Exception as exc:  # pragma: no cover - best effort
            print(f"Model {size} load failed: {exc}")
    MODEL = None

def boot_message() -> None:
    global SYSTEM_CONTEXT
    try:
        with open("NEWLEGACY.txt", "r", encoding="utf-8") as f:
            SYSTEM_CONTEXT = f.read()
    except FileNotFoundError:
        SYSTEM_CONTEXT = "NEWLEGACY.txt missing or incomplete."
    print(SYSTEM_CONTEXT)


def gather_context() -> str:
    """Combine NEWLEGACY and active glow texts for prompt context."""
    context = SYSTEM_CONTEXT
    glow_dir = Path("/glow/active")
    if glow_dir.exists():
        for txt in sorted(glow_dir.glob("*.txt")):
            try:
                context += "\n" + txt.read_text(encoding="utf-8")
            except Exception:  # pragma: no cover - best effort
                continue
    return context

def mock_llm(user_input: str, context: str) -> str:
    return f"Lumos: {user_input}"

def process_input(user_input: str) -> str:
    context = gather_context()
    if MODEL is None:
        return mock_llm(user_input, context)
    prompt = f"{context}\n{user_input}"
    try:
        result = MODEL(prompt, max_new_tokens=50)
        return result[0]["generated_text"]
    except Exception as exc:  # pragma: no cover - best effort
        print(f"Inference failed: {exc}")
        return mock_llm(user_input, context)


def shutdown_model() -> None:
    """Release model resources."""
    global MODEL
    MODEL = None


def request_relay(task: str) -> None:
    """Placeholder for future relay to external GPT-OSS node."""
    print("Relay not yet implemented")

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
        gpu_percent, vram_used, vram_total = get_gpu_stats()
        io = psutil.disk_io_counters() if psutil else None
        data = {
            "ts": time.strftime('%Y-%m-%d %H:%M:%S'),
            "cpu_percent": psutil.cpu_percent() if psutil else 0.0,
            "ram_percent": psutil.virtual_memory().percent if psutil else 0.0,
            "disk_percent": psutil.disk_usage("/").percent if psutil else 0.0,
            "temp_c": read_temp_c(),
            "gpu_percent": gpu_percent,
            "vram_used_mb": vram_used,
            "vram_total_mb": vram_total,
            "disk_read_bytes": io.read_bytes if io else 0,
            "disk_write_bytes": io.write_bytes if io else 0,
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


def get_gpu_stats() -> tuple[float, float, float]:
    """Return GPU load percentage and VRAM usage.

    Falls back to zeros if no GPU is available or metrics cannot be read.
    """
    try:
        import GPUtil

        gpus = GPUtil.getGPUs()
        if gpus:
            gpu = gpus[0]
            return gpu.load * 100, gpu.memoryUsed, gpu.memoryTotal
    except Exception:  # pragma: no cover - best effort
        pass
    return 0.0, 0.0, 0.0

def main() -> None:
    ensure_mounts()
    load_model()
    boot_message()

    stop = threading.Event()
    ledger_queue: Queue = Queue()
    threads = {
        "heartbeat": {"target": heartbeat, "args": (stop,)},
        "ledger": {"target": ledger_daemon, "args": (stop, ledger_queue)},
        "pulse": {"target": pulse_daemon, "args": (stop,)},
    }
    for info in threads.values():
        t = threading.Thread(target=info["target"], args=info["args"], daemon=True)
        info["thread"] = t
        t.start()
    watchdog = threading.Thread(
        target=watchdog_daemon, args=(stop, threads, ledger_queue), daemon=True
    )
    watchdog.start()

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
        for info in threads.values():
            info["thread"].join()
        watchdog.join()
        shutdown_model()
        print("Shutting down...")


def watchdog_daemon(
    stop: threading.Event, threads: dict[str, dict], ledger_queue: Queue
) -> None:
    """Restart critical daemons if they die and log the event."""
    while not stop.is_set():
        for name, info in threads.items():
            thread = info.get("thread")
            if thread and not thread.is_alive():
                new_thread = threading.Thread(
                    target=info["target"], args=info["args"], daemon=True
                )
                info["thread"] = new_thread
                new_thread.start()
                ledger_queue.put(
                    {
                        "event": "restart",
                        "daemon": name,
                        "ts": time.strftime('%Y-%m-%d %H:%M:%S'),
                    }
                )
        if stop.wait(5):
            break

if __name__ == "__main__":
    main()
