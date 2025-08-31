#!/usr/bin/env python3
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: add_codex_request.py 'task spec...'")
        return
    task = " ".join(sys.argv[1:]).strip()
    if not task:
        print("Task specification required")
        return
    queue_dir = Path("/glow/codex_requests")
    queue_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    (queue_dir / f"task_{ts}.txt").write_text(task, encoding="utf-8")
    print(f"queued: {task}")


if __name__ == "__main__":
    main()
