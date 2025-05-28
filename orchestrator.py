import os
import json
import time
import datetime
from pathlib import Path
import autonomous_reflector as ar

MEMORY_DIR = Path(os.getenv("MEMORY_DIR", "logs/memory"))
STATE_PATH = MEMORY_DIR / "orchestrator_state.json"
STATE_PATH.parent.mkdir(parents=True, exist_ok=True)


def _load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


class Orchestrator:
    def __init__(self, interval: float = 60.0):
        self.interval = interval
        self.state = _load_state()

    def run_cycle(self) -> None:
        ar.run_once()
        self.state["last_run"] = datetime.datetime.utcnow().isoformat()
        _save_state(self.state)

    def run_forever(self) -> None:
        while True:
            self.run_cycle()
            time.sleep(self.interval)
