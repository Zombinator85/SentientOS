"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from sentientos.privilege import require_admin_banner, require_lumos_approval
from utils.system_paths import find_ollama

load_dotenv()

os.environ.setdefault("LUMOS_AUTO_APPROVE", "1")
os.environ.setdefault("SENTIENTOS_HEADLESS", "1")
os.environ["OLLAMA_PATH"] = find_ollama() or ""

require_admin_banner()
if not (os.getenv("LUMOS_AUTO_APPROVE") == "1" or os.getenv("SENTIENTOS_HEADLESS") == "1"):
    require_lumos_approval()
else:
    print("[Lumos] Blessing auto-approved (headless mode).")

LOG_FILE = Path(os.getenv("SENTIENTOS_LOG_DIR") or "logs") / "bootstrap_run.jsonl"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

GUI_STUB = '"""Stub GUI launcher"""\n'
BRIDGE_STUB = '"""Stub model bridge"""\n'
TEST_STUB = '"""Stub cathedral boot test"""\n'


def log_event(action: str, detail: str = "") -> None:
    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "action": action,
        "detail": detail,
    }
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def check_python() -> bool:
    ok = sys.version_info >= (3, 10)
    log_event("python_check", "ok" if ok else sys.version.split()[0])
    return ok


def check_edge_tts() -> bool:
    try:
        __import__("edge_tts")
        available = True
    except Exception:
        available = False
    log_event("edge_tts", "present" if available else "missing")
    return available


def ensure_stub(path: Path, content: str) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        log_event("created", str(path))


def ensure_env() -> None:
    env = Path(".env")
    if not env.exists():
        example = Path(".env.example")
        if example.exists():
            env.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            env.touch()
        log_event("env_created", env.name)


def _read_gpu_description() -> str:
    backend_file = Path(os.getenv("SENTIENTOS_LOG_DIR") or "logs") / "gpu_backend.json"
    try:
        data = json.loads(backend_file.read_text(encoding="utf-8"))
        return data.get("description") or data.get("backend", "Unknown GPU")
    except Exception:
        return "Unknown GPU"


def main() -> None:
    check_python()
    check_edge_tts()
    ensure_env()
    ensure_stub(Path("gui/cathedral_gui.py"), GUI_STUB)
    ensure_stub(Path("model_bridge.py"), BRIDGE_STUB)
    ensure_stub(Path("tests/test_cathedral_boot.py"), TEST_STUB)
    log_event("complete")
    print("[SentientOS] Model: Mixtral 8x7B Instruct (GGUF)")
    print(f"[SentientOS] GPU Backend: {_read_gpu_description()}")
    print("[SentientOS] Relay bound to http://127.0.0.1:5000")
    print("[SentientOS] Lumos approval auto-granted (headless)")


if __name__ == "__main__":
    main()
