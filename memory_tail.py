import os
import time
import json
from datetime import datetime
from colorama import init, Fore, Style

init()

COLOR_MAP = {
    "openai/gpt-4o": Fore.GREEN,
    "mixtral": Fore.MAGENTA,
    "deepseek-ai/deepseek-r1-distill-llama-70b-free": Fore.CYAN,
    "heartbeat": Fore.YELLOW
}

MEMORY_FILE = os.path.join("logs", "memory.jsonl")

def detect_color(entry):
    source = (entry.get("source") or "").lower()
    tags   = [t.lower() for t in entry.get("tags", [])]

    if source in COLOR_MAP:
        return COLOR_MAP[source]
    for t in tags:
        if t in COLOR_MAP:
            return COLOR_MAP[t]
    return Fore.WHITE

def tail_memory(path, delay=2):
    print(Fore.BLUE + "[Lumos] Live memory tail started...\n" + Style.RESET_ALL)
    try:
        with open(path, "r", encoding="utf-8") as f:
            f.seek(0, os.SEEK_END)
            while True:
                line = f.readline()
                if not line:
                    time.sleep(delay)
                    continue
                try:
                    entry = json.loads(line.strip())
                    color = detect_color(entry)
                    ts    = entry.get("timestamp", "???")
                    src   = entry.get("source", "unknown")
                    txt   = entry.get("text", "").strip().replace("\n", " ")

                    print(color + f"[{ts}] ({src}) → {txt[:200]}" + Style.RESET_ALL)

                except Exception as e:
                    print(Fore.RED + f"[TAIL ERROR] {e}" + Style.RESET_ALL)
    except FileNotFoundError:
        print(Fore.RED + f"[ERROR] memory.jsonl not found: {path}" + Style.RESET_ALL)

if __name__ == "__main__":
    tail_memory(MEMORY_FILE)

