import json
import os
import threading
import time
from collections import OrderedDict
from pathlib import Path
from queue import Empty, Queue

import base64
import hashlib
import math
import psutil
import requests
import shutil
from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

# Glow memory and relay paths
RELAY_LOG = Path("/daemon/logs/relay.jsonl")
GLOW_ARCHIVE = Path("/glow/archive")
GLOW_SUMMARIES = Path("/glow/summaries")
GLOW_DEEP_ARCHIVE = Path("/glow/deep_archive")
GLOW_REF_PATH = Path("/glow/index.json")
GLOW_INDEX_PATH = Path("/glow/embed_index.json")

# In-memory structures for glow retrieval
GLOW_INDEX: dict[str, dict] = {}
GLOW_CACHE: OrderedDict[str, str] = OrderedDict()
EMBED_MODEL = None

MOUNT_POINTS = [Path("/vow"), Path("/glow"), Path("/daemon"), Path("/pulse")]
HEARTBEAT_LOG = Path("/daemon/logs/heartbeat.log")
LEDGER_LOG = Path("/daemon/logs/ledger.jsonl")
LEDGER_SYNC_STATE = Path("/daemon/logs/ledger.sync")
PULSE_FILE = Path("/pulse/system.json")
GLOW_SYNC_STATE = Path("/glow/archive/sync.json")
GLOW_PULL_STATE = Path("/glow/archive/pull.json")
LEDGER_PULL_STATE = Path("/daemon/logs/ledger.pull")
SIGNATURES_LOG = Path("/vow/signatures.jsonl")
KEY_DIR = Path("/vow/keys")
PRIVATE_KEY_FILE = KEY_DIR / "ed25519_private.key"
PUBLIC_KEY_FILE = KEY_DIR / "ed25519_public.key"
REMOTE_PUBLIC_KEY_FILE = KEY_DIR / "remote_public.key"

SIGNING_KEY: SigningKey | None = None
VERIFY_KEY: VerifyKey | None = None
REMOTE_VERIFY_KEY: VerifyKey | None = None
PRUNE_COUNT = 0

SYSTEM_CONTEXT = ""
MODEL = None

MODEL_PATHS = {
    "120b": Path("/models/gpt-oss-120b-quantized"),
    "20b": Path("/models/gpt-oss-20b"),
    "13b": Path("/models/gpt-oss-13b"),
}


def init_keys() -> None:
    """Load or generate the Ed25519 keypair."""
    global SIGNING_KEY, VERIFY_KEY, REMOTE_VERIFY_KEY
    KEY_DIR.mkdir(parents=True, exist_ok=True)
    if PRIVATE_KEY_FILE.exists():
        SIGNING_KEY = SigningKey(PRIVATE_KEY_FILE.read_bytes())
    else:
        SIGNING_KEY = SigningKey.generate()
        PRIVATE_KEY_FILE.write_bytes(SIGNING_KEY.encode())
        PUBLIC_KEY_FILE.write_bytes(SIGNING_KEY.verify_key.encode())
    VERIFY_KEY = SIGNING_KEY.verify_key
    try:
        REMOTE_VERIFY_KEY = VerifyKey(REMOTE_PUBLIC_KEY_FILE.read_bytes())
    except Exception:  # pragma: no cover - best effort
        REMOTE_VERIFY_KEY = None


def sign_entry(entry: dict) -> str:
    """Sign the given entry and record the signature."""
    if SIGNING_KEY is None:
        return ""
    msg = json.dumps(entry, sort_keys=True).encode("utf-8")
    sig = SIGNING_KEY.sign(msg).signature
    sig_b64 = base64.b64encode(sig).decode("ascii")
    SIGNATURES_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(SIGNATURES_LOG, "a", encoding="utf-8") as log:
        log.write(
            json.dumps({"ts": entry.get("ts"), "signature": sig_b64}) + "\n"
        )
    return sig_b64


def verify_entry(entry: dict, signature: str) -> bool:
    """Verify an entry signature using the remote public key."""
    if REMOTE_VERIFY_KEY is None or not signature:
        return False
    try:
        REMOTE_VERIFY_KEY.verify(
            json.dumps(entry, sort_keys=True).encode("utf-8"),
            base64.b64decode(signature),
        )
        return True
    except BadSignatureError:
        return False


def sign_text(text: str) -> str:
    """Sign arbitrary text and return a base64 signature."""
    if SIGNING_KEY is None:
        return ""
    sig = SIGNING_KEY.sign(text.encode("utf-8")).signature
    return base64.b64encode(sig).decode("ascii")


def verify_text(text: str, signature: str) -> bool:
    """Verify text signature using the remote public key."""
    if REMOTE_VERIFY_KEY is None or not signature:
        return False
    try:
        REMOTE_VERIFY_KEY.verify(text.encode("utf-8"), base64.b64decode(signature))
        return True
    except BadSignatureError:
        return False


def write_signed(entry: dict) -> None:
    """Sign and persist a ledger entry."""
    sig = sign_entry(entry)
    entry["signature"] = sig
    entry["verified"] = True
    with open(LEDGER_LOG, "a", encoding="utf-8") as log:
        log.write(json.dumps(entry) + "\n")

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
    GLOW_SUMMARIES.mkdir(parents=True, exist_ok=True)
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

    refs: dict[str, dict] = {}
    if GLOW_REF_PATH.exists():
        try:
            refs = json.loads(GLOW_REF_PATH.read_text(encoding="utf-8"))
        except Exception:  # pragma: no cover - best effort
            refs = {}

    GLOW_INDEX = {}
    # Archived glows via summaries
    for orig, meta in refs.items():
        summary_name = meta.get("summary")
        if not summary_name:
            continue
        path = GLOW_SUMMARIES / summary_name
        try:
            text = path.read_text(encoding="utf-8")
            emb = EMBED_MODEL.encode(text).tolist()
            GLOW_INDEX[orig] = {
                "vector": emb,
                "archived": True,
                "summary": summary_name,
            }
        except Exception:  # pragma: no cover - best effort
            continue

    # Active glows
    for path in sorted(GLOW_ARCHIVE.glob("*.txt")):
        try:
            text = path.read_text(encoding="utf-8")
            emb = EMBED_MODEL.encode(text).tolist()
            GLOW_INDEX[path.name] = {"vector": emb, "archived": False}
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
    for name, meta in GLOW_INDEX.items():
        vec = meta.get("vector")
        if vec:
            scores.append((_cosine(query_vec, vec), name))
    scores.sort(reverse=True)
    top_files = [name for _score, name in scores[:3] if _score > 0]

    force = None
    for token in query.split():
        if token.startswith("archive:"):
            force = token.split(":", 1)[1]

    texts = []
    for name in top_files:
        meta = GLOW_INDEX.get(name, {})
        if force == name and meta.get("archived"):
            path = GLOW_DEEP_ARCHIVE / name
        elif meta.get("archived"):
            path = GLOW_SUMMARIES / meta.get("summary", name)
        else:
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


def summarize_glow(text: str) -> str:
    """Generate a short summary for archived glows."""
    prompt = f"Summarize the following text:\n{text[:4000]}"
    summary, status, _lat = request_relay(prompt, "")
    if summary:
        return summary
    if MODEL is not None:
        try:
            result = MODEL(prompt, max_new_tokens=60)
            return result[0]["generated_text"]
        except Exception:  # pragma: no cover - best effort
            pass
    return text[:200]


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
        entry.setdefault("pruned", False)
        entry.setdefault("summary_refs", [])
        entry["pulse"] = read_pulse_snapshot()
        entry["synced"] = "push_only"
        write_signed(entry)
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
        "pruned": False,
        "summary_refs": [],
        "synced": "push_only",
    }
    write_signed(shutdown_entry)


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


def prune_daemon(
    stop: threading.Event, ledger_queue: Queue, max_age_days: int = 30
) -> None:
    """Summarize and archive old glow files."""
    global PRUNE_COUNT
    while not stop.is_set():
        cutoff = time.time() - max_age_days * 86400
        for path in list(GLOW_ARCHIVE.glob("*.txt")):
            try:
                if path.stat().st_mtime >= cutoff:
                    continue
                text = path.read_text(encoding="utf-8")
                summary = summarize_glow(text)
                GLOW_SUMMARIES.mkdir(parents=True, exist_ok=True)
                summary_name = f"{path.stem}.summary.txt"
                summary_path = GLOW_SUMMARIES / summary_name
                summary_path.write_text(summary, encoding="utf-8")
                sig = sign_text(summary)
                (summary_path.with_suffix(".sig")).write_text(sig, encoding="utf-8")
                checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
                GLOW_DEEP_ARCHIVE.mkdir(parents=True, exist_ok=True)
                dest = GLOW_DEEP_ARCHIVE / path.name
                shutil.move(str(path), dest)
                refs = {}
                if GLOW_REF_PATH.exists():
                    try:
                        refs = json.loads(GLOW_REF_PATH.read_text(encoding="utf-8"))
                    except Exception:  # pragma: no cover - best effort
                        refs = {}
                refs[path.name] = {"summary": summary_name, "checksum": checksum}
                GLOW_REF_PATH.write_text(json.dumps(refs), encoding="utf-8")
                verified = verify_text(summary, sig)
                ledger_queue.put(
                    {
                        "ts": time.strftime('%Y-%m-%d %H:%M:%S'),
                        "event": "pruned",
                        "file": path.name,
                        "summary_file": summary_name,
                        "verified": verified,
                        "relay_used": False,
                        "relay_status": "offline",
                        "latency_ms": 0,
                        "glow_refs": [],
                        "confirmed": True,
                        "pruned": True,
                        "summary_refs": [summary_name],
                        "synced": "push_only",
                    }
                )
                PRUNE_COUNT += 1
            except Exception:  # pragma: no cover - best effort
                continue
        if stop.wait(3600):
            break


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
    to_send: list[str] = []
    for line in lines[last:]:
        try:
            obj = json.loads(line)
            if obj.get("synced") == "push_only":
                to_send.append(line)
        except Exception:  # pragma: no cover - best effort
            continue
    if not to_send:
        LEDGER_SYNC_STATE.write_text(str(len(lines)), encoding="utf-8")
        return True
    payload = "\n".join(to_send)
    try:
        requests.post(
            "http://april-pc.local:5000/sync/ledger",
            data=payload,
            timeout=5,
        )
        for i in range(last, len(lines)):
            try:
                obj = json.loads(lines[i])
                if obj.get("synced") == "push_only":
                    obj["synced"] = "both"
                    lines[i] = json.dumps(obj)
            except Exception:  # pragma: no cover - best effort
                continue
        LEDGER_LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
        LEDGER_SYNC_STATE.write_text(str(len(lines)), encoding="utf-8")
        return True
    except Exception:  # pragma: no cover - best effort
        return False


def pull_sync_glow() -> None:
    """Fetch new glow files from the relay server."""
    last = 0.0
    if GLOW_PULL_STATE.exists():
        try:
            last = float(GLOW_PULL_STATE.read_text(encoding="utf-8"))
        except Exception:  # pragma: no cover - best effort
            last = 0.0
    try:
        resp = requests.get(
            "http://april-pc.local:5000/sync/pull/glow",
            params={"since": last},
            timeout=5,
        )
        data = resp.json()
    except Exception:  # pragma: no cover - best effort
        return
    files = data.get("files", [])
    new_last = last
    GLOW_ARCHIVE.mkdir(parents=True, exist_ok=True)
    GLOW_SUMMARIES.mkdir(parents=True, exist_ok=True)
    for item in files:
        name = item.get("name")
        ts = float(item.get("ts", 0.0))
        content = item.get("content", "")
        signature = item.get("signature", "")
        path = GLOW_ARCHIVE / name
        local_ts = path.stat().st_mtime if path.exists() else 0.0
        if ts >= local_ts and verify_text(content, signature):
            path.write_text(content, encoding="utf-8")
        summary_content = item.get("summary")
        summary_sig = item.get("summary_sig", "")
        if summary_content:
            summary_name = f"{Path(name).stem}.summary.txt"
            summary_path = GLOW_SUMMARIES / summary_name
            if verify_text(summary_content, summary_sig):
                summary_path.write_text(summary_content, encoding="utf-8")
                (summary_path.with_suffix(".sig")).write_text(summary_sig, encoding="utf-8")
                refs = {}
                if GLOW_REF_PATH.exists():
                    try:
                        refs = json.loads(GLOW_REF_PATH.read_text(encoding="utf-8"))
                    except Exception:  # pragma: no cover - best effort
                        refs = {}
                refs[name] = {
                    "summary": summary_name,
                    "checksum": item.get("checksum", ""),
                }
                GLOW_REF_PATH.write_text(json.dumps(refs), encoding="utf-8")
        new_last = max(new_last, ts)
    GLOW_PULL_STATE.write_text(str(new_last), encoding="utf-8")


def pull_sync_ledger(queue: Queue) -> None:
    """Fetch new ledger entries from the relay server."""
    last = ""
    if LEDGER_PULL_STATE.exists():
        last = LEDGER_PULL_STATE.read_text(encoding="utf-8").strip()
    try:
        resp = requests.get(
            "http://april-pc.local:5000/sync/pull/ledger",
            params={"since": last},
            timeout=5,
        )
        data = resp.json()
    except Exception:  # pragma: no cover - best effort
        return
    lines = data.get("lines", [])
    new_last = last
    for line in lines:
        try:
            entry = json.loads(line)
        except Exception:  # pragma: no cover - best effort
            continue
        sig = entry.pop("signature", "")
        verified = verify_entry(entry, sig)
        if not verified:
            queue.put(
                {
                    "event": "integrity_failure",
                    "ts": time.strftime('%Y-%m-%d %H:%M:%S'),
                    "relay_used": False,
                    "relay_status": "offline",
                    "latency_ms": 0,
                    "glow_refs": [],
                    "confirmed": True,
                    "pruned": False,
                    "summary_refs": [],
                    "synced": "push_only",
                }
            )
            continue
        entry["signature"] = sig
        entry["synced"] = "pull_only"
        entry["verified"] = verified
        with open(LEDGER_LOG, "a", encoding="utf-8") as log:
            log.write(json.dumps(entry) + "\n")
        ts = entry.get("ts", "")
        if ts > new_last:
            new_last = ts
    LEDGER_PULL_STATE.write_text(str(new_last), encoding="utf-8")


def sync_once() -> bool:
    glow_ok = sync_glow()
    ledger_ok = sync_ledger()
    return glow_ok and ledger_ok


def sync_daemon(stop: threading.Event) -> None:
    while not stop.is_set():
        sync_once()
        if stop.wait(300):
            break


def pull_sync_daemon(stop: threading.Event, queue: Queue) -> None:
    while not stop.is_set():
        pull_sync_glow()
        pull_sync_ledger(queue)
        if stop.wait(300):
            break

def main() -> None:
    ensure_mounts()
    init_keys()
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
        "pull_sync": {"target": pull_sync_daemon, "args": (stop, ledger_queue)},
        "prune": {"target": prune_daemon, "args": (stop, ledger_queue)},
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
                            "pruned": False,
                            "summary_refs": [],
                            "synced": "push_only",
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
                    "pruned": False,
                    "summary_refs": [],
                    "synced": "push_only",
                }
            )
    finally:
        ledger_queue.join()
        stop.set()
        for info in threads.values():
            info["thread"].join()
        watchdog.join()
        write_signed(
            {
                "event": "prune_report",
                "ts": time.strftime('%Y-%m-%d %H:%M:%S'),
                "count": PRUNE_COUNT,
                "relay_used": False,
                "relay_status": "offline",
                "latency_ms": 0,
                "glow_refs": [],
                "confirmed": True,
                "pruned": False,
                "summary_refs": [],
                "synced": "push_only",
            }
        )
        success = sync_once()
        write_signed(
            {
                "event": "final_sync",
                "ts": time.strftime('%Y-%m-%d %H:%M:%S'),
                "success": success,
                "relay_used": False,
                "relay_status": "offline",
                "latency_ms": 0,
                "glow_refs": [],
                "confirmed": True,
                "pruned": False,
                "summary_refs": [],
                "synced": "push_only",
            }
        )
        sync_once()
        summary = {
            "event": "shutdown_summary",
            "ts": time.strftime('%Y-%m-%d %H:%M:%S'),
            "last_sync_success": success,
            "relay_used": False,
            "relay_status": "offline",
            "latency_ms": 0,
            "glow_refs": [],
            "confirmed": True,
            "pruned": False,
            "summary_refs": [],
            "synced": "push_only",
        }
        write_signed(summary)
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
                        "pruned": False,
                        "summary_refs": [],
                        "synced": "push_only",
                    }
                )
        if stop.wait(5):
            break

if __name__ == "__main__":
    main()
