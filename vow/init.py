import json
import os
import threading
import time
from collections import OrderedDict
from pathlib import Path
from queue import Empty, Queue

import math
import psutil
import requests

# Glow memory and relay paths
RELAY_LOG = Path("/daemon/logs/relay.jsonl")
GLOW_ARCHIVE = Path("/glow/archive")
GLOW_INDEX_PATH = Path("/glow/index.json")

# In-memory structures for glow retrieval
GLOW_INDEX: dict[str, list[float]] = {}
GLOW_CACHE: OrderedDict[str, str] = OrderedDict()
EMBED_MODEL = None

MOUNT_POINTS = [Path("/vow"), Path("/glow"), Path("/daemon"), Path("/pulse")]
HEARTBEAT_LOG = Path("/daemon/logs/heartbeat.log")
LEDGER_LOG = Path("/daemon/logs/ledger.jsonl")
LEDGER_SYNC_STATE = Path("/daemon/logs/ledger.sync")
PULSE_FILE = Path("/pulse/system.json")
GLOW_SYNC_STATE = Path("/glow/archive/sync.json")

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


def memory_loader() -> None:
    """Build or refresh the glow memory index."""
    global GLOW_INDEX, EMBED_MODEL
    GLOW_ARCHIVE.mkdir(parents=True, exist_ok=True)
    files = sorted(GLOW_ARCHIVE.glob("*.txt"))
    if not files:
        GLOW_INDEX = {}
        GLOW_INDEX_PATH.write_text("{}", encoding="utf-8")
        return
    try:
        from sentence_transformers import SentenceTransformer

        EMBED_MODEL = SentenceTransformer(
            "sentence-transformers/all-MiniLM-L6-v2"  # small model
        )
    except Exception as exc:  # pragma: no cover - best effort
        print(f"Embedding model unavailable: {exc}")
        GLOW_INDEX = {}
        GLOW_INDEX_PATH.write_text("{}", encoding="utf-8")
        return

    GLOW_INDEX = {}
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
            emb = EMBED_MODEL.encode(text).tolist()
            GLOW_INDEX[path.name] = emb
        except Exception:  # pragma: no cover - best effort
            continue
    with open(GLOW_INDEX_PATH, "w", encoding="utf-8") as idx:
        json.dump(GLOW_INDEX, idx)


def _cosine(a: list[float], b: list[float]) -> float:
    denom = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(x * x for x in b))
    if not denom:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / denom


def retrieve_glows(query: str) -> tuple[list[str], list[str]]:
    """Return filenames and texts of top-3 relevant archived glows."""
    if not GLOW_INDEX or EMBED_MODEL is None:
        return [], []
    try:
        query_vec = EMBED_MODEL.encode(query).tolist()
    except Exception:  # pragma: no cover - best effort
        return [], []
    scores = []
    for name, vec in GLOW_INDEX.items():
        scores.append((_cosine(query_vec, vec), name))
    scores.sort(reverse=True)
    top_files = [name for _score, name in scores[:3] if _score > 0]

    texts = []
    for name in top_files:
        path = GLOW_ARCHIVE / name
        if name not in GLOW_CACHE:
            try:
                GLOW_CACHE[name] = path.read_text(encoding="utf-8")
            except Exception:  # pragma: no cover - best effort
                GLOW_CACHE[name] = ""
            if len(GLOW_CACHE) > 10:
                GLOW_CACHE.popitem(last=False)
        texts.append(GLOW_CACHE.get(name, ""))
    return top_files, texts

def mock_llm(user_input: str, context: str) -> str:
    return f"Lumos: {user_input}"


def process_input(user_input: str) -> tuple[str, list[str], bool, str, float]:
    context = gather_context()
    glow_refs, glow_texts = retrieve_glows(user_input)
    if glow_texts:
        context += "\n" + "\n".join(glow_texts)

    relay_output, relay_status, latency_ms = request_relay(user_input, context)
    relay_used = relay_output is not None
    if relay_used:
        return relay_output, glow_refs, relay_used, relay_status, latency_ms

    if MODEL is None:
        return (
            mock_llm(user_input, context),
            glow_refs,
            relay_used,
            relay_status,
            latency_ms,
        )
    prompt = f"{context}\n{user_input}"
    try:
        result = MODEL(prompt, max_new_tokens=50)
        return result[0]["generated_text"], glow_refs, relay_used, relay_status, latency_ms
    except Exception as exc:  # pragma: no cover - best effort
        print(f"Inference failed: {exc}")
        return (
            mock_llm(user_input, context),
            glow_refs,
            relay_used,
            relay_status,
            latency_ms,
        )


def shutdown_model() -> None:
    """Release model resources."""
    global MODEL
    MODEL = None


def request_relay(task: str, context: str) -> tuple[str | None, str, float]:
    """Send task to external node and return (text or None, status, latency)."""
    payload = {"task": task, "context": context}
    RELAY_LOG.parent.mkdir(parents=True, exist_ok=True)
    start = time.time()
    try:
        resp = requests.post(
            "http://april-pc.local:5000/relay", json=payload, timeout=5
        )
        latency_ms = (time.time() - start) * 1000
        data = (
            resp.json()
            if resp.headers.get("content-type", "").startswith("application/json")
            else {"text": resp.text}
        )
        with open(RELAY_LOG, "a", encoding="utf-8") as log:
            log.write(
                json.dumps(
                    {
                        "ts": time.strftime('%Y-%m-%d %H:%M:%S'),
                        "request": payload,
                        "response": data,
                        "latency_ms": latency_ms,
                    }
                )
                + "\n"
            )
        return data.get("output") or data.get("text"), "online", latency_ms
    except Exception:  # pragma: no cover - best effort
        latency_ms = (time.time() - start) * 1000
        with open(RELAY_LOG, "a", encoding="utf-8") as log:
            log.write(
                json.dumps(
                    {
                        "ts": time.strftime('%Y-%m-%d %H:%M:%S'),
                        "event": "relay_failed",
                        "latency_ms": latency_ms,
                    }
                )
                + "\n"
            )
        return None, "offline", latency_ms

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
    while True:
        try:
            entry = queue.get(timeout=0.5)
        except Empty:
            if stop.is_set():
                break
            continue
        entry["pulse"] = read_pulse_snapshot()
        with open(LEDGER_LOG, "a", encoding="utf-8") as log:
            log.write(json.dumps(entry) + "\n")
        queue.task_done()
    shutdown_entry = {
        "event": "shutdown",
        "ts": time.strftime('%Y-%m-%d %H:%M:%S'),
        "pulse": read_pulse_snapshot(),
        "relay_used": False,
        "relay_status": "offline",
        "latency_ms": 0,
        "glow_refs": [],
        "confirmed": True,
        "synced": False,
    }
    with open(LEDGER_LOG, "a", encoding="utf-8") as log:
        log.write(json.dumps(shutdown_entry) + "\n")


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
    prev_net = psutil.net_io_counters() if psutil else None
    last_time = time.time()
    last_ping = 0.0
    relay_latency_ms = 0.0
    relay_status = "offline"
    while not stop.is_set():
        gpu_percent, vram_used, vram_total = get_gpu_stats()
        io = psutil.disk_io_counters() if psutil else None
        net = psutil.net_io_counters() if psutil else None
        now = time.time()
        up_kbps = down_kbps = 0.0
        if net and prev_net:
            interval = now - last_time or 1.0
            up_kbps = (net.bytes_sent - prev_net.bytes_sent) * 8 / 1024 / interval
            down_kbps = (net.bytes_recv - prev_net.bytes_recv) * 8 / 1024 / interval
        prev_net = net
        last_time = now
        if now - last_ping >= 30:
            ping_start = time.time()
            try:
                requests.get("http://april-pc.local:5000/ping", timeout=2)
                relay_status = "online"
                relay_latency_ms = (time.time() - ping_start) * 1000
            except Exception:  # pragma: no cover - best effort
                relay_status = "offline"
                relay_latency_ms = 0.0
            last_ping = now
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
            "net_up_kbps": up_kbps,
            "net_down_kbps": down_kbps,
            "relay_status": relay_status,
            "relay_latency_ms": relay_latency_ms,
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


def sync_glow() -> bool:
    """Upload unsynced glow files to the relay server."""
    synced: list[str] = []
    if GLOW_SYNC_STATE.exists():
        try:
            synced = json.loads(GLOW_SYNC_STATE.read_text(encoding="utf-8"))
        except Exception:  # pragma: no cover - best effort
            synced = []
    changed = False
    GLOW_ARCHIVE.mkdir(parents=True, exist_ok=True)
    for path in sorted(GLOW_ARCHIVE.glob("*.txt")):
        if path.name in synced:
            continue
        try:
            with open(path, "rb") as f:
                files = {"file": (path.name, f, "text/plain")}
                requests.post(
                    "http://april-pc.local:5000/sync/glow",
                    files=files,
                    timeout=5,
                )
            synced.append(path.name)
            changed = True
        except Exception:  # pragma: no cover - best effort
            return False
    if changed:
        GLOW_SYNC_STATE.write_text(json.dumps(synced), encoding="utf-8")
    return True


def sync_ledger() -> bool:
    """Upload unsynced ledger entries and mark them synced locally."""
    if not LEDGER_LOG.exists():
        return True
    lines = LEDGER_LOG.read_text(encoding="utf-8").splitlines()
    last = 0
    if LEDGER_SYNC_STATE.exists():
        try:
            last = int(LEDGER_SYNC_STATE.read_text(encoding="utf-8"))
        except Exception:  # pragma: no cover - best effort
            last = 0
    if last >= len(lines):
        return True
    payload = "\n".join(lines[last:])
    try:
        requests.post(
            "http://april-pc.local:5000/sync/ledger",
            data=payload,
            timeout=5,
        )
        for i in range(last, len(lines)):
            try:
                obj = json.loads(lines[i])
                obj["synced"] = True
                lines[i] = json.dumps(obj)
            except Exception:  # pragma: no cover - best effort
                continue
        LEDGER_LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
        LEDGER_SYNC_STATE.write_text(str(len(lines)), encoding="utf-8")
        return True
    except Exception:  # pragma: no cover - best effort
        return False


def sync_once() -> bool:
    glow_ok = sync_glow()
    ledger_ok = sync_ledger()
    return glow_ok and ledger_ok


def sync_daemon(stop: threading.Event) -> None:
    while not stop.is_set():
        sync_once()
        if stop.wait(300):
            break

def main() -> None:
    ensure_mounts()
    memory_loader()
    load_model()
    boot_message()

    stop = threading.Event()
    ledger_queue: Queue = Queue()
    threads = {
        "heartbeat": {"target": heartbeat, "args": (stop,)},
        "ledger": {"target": ledger_daemon, "args": (stop, ledger_queue)},
        "pulse": {"target": pulse_daemon, "args": (stop,)},
        "sync": {"target": sync_daemon, "args": (stop,)},
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

            confirmed = True
            if any(word in user_input.lower() for word in ["rm", "shutdown", "format"]):
                resp = input("\u26A0\uFE0F Lumos: This action is dangerous. Confirm (yes/no)? ").strip().lower()
                confirmed = resp == "yes"
                if not confirmed:
                    print("Action canceled")
                    ledger_queue.put(
                        {
                            "ts": time.strftime('%Y-%m-%d %H:%M:%S'),
                            "input": user_input,
                            "output": "Action canceled",
                            "relay_used": False,
                            "relay_status": "offline",
                            "latency_ms": 0,
                            "glow_refs": [],
                            "confirmed": False,
                            "synced": False,
                        }
                    )
                    continue

            (
                output,
                glow_refs,
                relay_used,
                relay_status,
                latency_ms,
            ) = process_input(user_input)
            print(output)
            ledger_queue.put(
                {
                    "ts": time.strftime('%Y-%m-%d %H:%M:%S'),
                    "input": user_input,
                    "output": output,
                    "relay_used": relay_used,
                    "relay_status": relay_status,
                    "latency_ms": latency_ms,
                    "glow_refs": glow_refs,
                    "confirmed": confirmed,
                    "synced": False,
                }
            )
    finally:
        ledger_queue.join()
        stop.set()
        for info in threads.values():
            info["thread"].join()
        watchdog.join()
        success = sync_once()
        with open(LEDGER_LOG, "a", encoding="utf-8") as log:
            log.write(
                json.dumps(
                    {
                        "event": "final_sync",
                        "ts": time.strftime('%Y-%m-%d %H:%M:%S'),
                        "success": success,
                        "relay_used": False,
                        "relay_status": "offline",
                        "latency_ms": 0,
                        "glow_refs": [],
                        "confirmed": True,
                        "synced": False,
                    }
                )
                + "\n"
            )
        sync_once()
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
                        "relay_used": False,
                        "relay_status": "offline",
                        "latency_ms": 0,
                        "glow_refs": [],
                        "confirmed": True,
                        "synced": False,
                    }
                )
        if stop.wait(5):
            break

if __name__ == "__main__":
    main()
