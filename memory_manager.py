import json
import os
from datetime import datetime

LOG_DIR = os.path.join("logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_PATH = os.path.join(LOG_DIR, "memory.jsonl")

def write_mem(text, tags=None, source="unknown"):
    """Append a memory fragment to logs/memory.jsonl"""
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "text": text,
        "tags": tags or [],
        "source": source,
    }
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry["timestamp"]
