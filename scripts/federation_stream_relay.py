"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()

import json
import time
import threading
from pathlib import Path

import requests  # type: ignore[import-untyped]
import yaml

CONFIG_PATH = Path("config/federation.yaml")
LOG_PATH = Path("logs/federation_stream.jsonl")

def load_peers(config_path: Path = CONFIG_PATH) -> list[str]:
    """Return list of peer presence URLs from config."""
    if not config_path.exists():
        return []
    try:
        data = yaml.safe_load(config_path.read_text()) or {}
    except Exception:
        return []
    return [p.get("url", "") for p in data.get("peers", []) if p.get("url")]

def relay_peer(url: str, log_path: Path = LOG_PATH) -> None:
    """Subscribe to peer presence stream and append events to log."""
    stream_url = url.rstrip("/") + "/stream"
    while True:
        try:
            with requests.get(stream_url, stream=True, timeout=10) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line or not line.startswith(b"data:"):
                        continue
                    payload = line.split(b":", 1)[1].strip()
                    try:
                        data = json.loads(payload)
                    except Exception:
                        continue
                    data["source"] = url
                    log_path.parent.mkdir(parents=True, exist_ok=True)
                    with log_path.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps(data) + "\n")
        except Exception:
            time.sleep(5)

def main() -> None:
    peers = load_peers()
    threads: list[threading.Thread] = []
    for p in peers:
        t = threading.Thread(target=relay_peer, args=(p,), daemon=True)
        t.start()
        threads.append(t)
    while True:
        time.sleep(60)

if __name__ == "__main__":
    main()
