from logging_config import get_log_path
import argparse
import json
import time
from pathlib import Path

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover - optional
    requests = None

LEDGER = get_log_path("federation_handshake.jsonl")
LEDGER.parent.mkdir(parents=True, exist_ok=True)


def ping_peer(url: str) -> dict:
    start = time.time()
    status = "unreachable"
    if requests is not None:
        try:
            r = requests.get(url, timeout=5)
            status = str(r.status_code)
        except Exception:
            status = "error"
    elapsed = time.time() - start
    entry = {"timestamp": time.time(), "peer": url, "status": status, "time": elapsed}
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Federation handshake reporter")
    ap.add_argument("peer")
    args = ap.parse_args()
    print(json.dumps(ping_peer(args.peer), indent=2))
