from __future__ import annotations
import os
import time
import json
import argparse
from logging_config import get_log_path
from privilege_lint.color import init, Fore, Style
from sentient_banner import print_banner, print_closing
from sentientos.privilege import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

init()
COLOR_MAP: dict[str, str] = {
    "heartbeat": Fore.YELLOW,
    "openai/gpt-4o": Fore.GREEN,
    "mixtral": Fore.MAGENTA,
    "deepseek-ai/deepseek-r1-distill-llama-70b-free": Fore.CYAN,
}

DEFAULT_FILE = get_log_path("memory.jsonl", "MEMORY_FILE")


from typing import Any, Dict


def detect_color(entry: dict[str, Any]) -> str:
    source = (entry.get("source") or "").lower()
    tags = [t.lower() for t in entry.get("tags", [])]
    if source in COLOR_MAP:
        return str(COLOR_MAP[source])
    for t in tags:
        if t in COLOR_MAP:
            return str(COLOR_MAP[t])
    return str(Fore.WHITE)


def dominant_emotion(entry: dict[str, Any]) -> str | None:
    emotions = entry.get("emotions")
    if isinstance(emotions, dict) and emotions:
        emo, score = max(emotions.items(), key=lambda x: x[1])
        if score > 0:
            return f"{emo}:{score:.2f}"
    return None


def tail_memory(path: str, delay: float = 1.0) -> None:
    """Continuously print new JSON lines from ``path`` with color."""
    print(Fore.BLUE + "[Lumos] Live memory tail started..." + Style.RESET_ALL)
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
                    ts = entry.get("timestamp", "???")
                    src = entry.get("source", "unknown")
                    txt = entry.get("text", "").strip().replace("\n", " ")
                    dom = dominant_emotion(entry)
                    emo_str = f" [{dom}]" if dom else ""
                    print(color + f"[{ts}] ({src}){emo_str} -> {txt[:200]}" + Style.RESET_ALL)
                except Exception as e:  # noqa: BLE001
                    print(Fore.RED + f"[TAIL ERROR] {e}" + Style.RESET_ALL)
    except FileNotFoundError:
        print(Fore.RED + f"[ERROR] memory.jsonl not found: {path}" + Style.RESET_ALL)


def main() -> None:
    # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
    parser = argparse.ArgumentParser(description="Tail memory.jsonl")
    parser.add_argument("--file", default=DEFAULT_FILE, help="Path to JSONL log")
    parser.add_argument("--delay", type=float, default=1.0, help="Polling delay")
    args = parser.parse_args()
    print_banner()
    tail_memory(args.file, delay=args.delay)
    print_closing()


if __name__ == "__main__":
    main()
