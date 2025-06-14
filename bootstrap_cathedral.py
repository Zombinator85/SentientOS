"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

LOG_FILE = Path("logs/bootstrap_run.jsonl")
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


def main() -> None:
    check_python()
    check_edge_tts()
    ensure_env()
    ensure_stub(Path("gui/cathedral_gui.py"), GUI_STUB)
    ensure_stub(Path("model_bridge.py"), BRIDGE_STUB)
    ensure_stub(Path("tests/test_cathedral_boot.py"), TEST_STUB)
    log_event("complete")


if __name__ == "__main__":
    main()
