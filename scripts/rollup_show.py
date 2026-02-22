from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Show rollup summaries for a pulse stream")
    parser.add_argument("stream", help="Stream name without .jsonl suffix")
    parser.add_argument("--root", default=".", help="Repository root")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    rollup_dir = root / "glow/forge/rollups" / args.stream
    if not rollup_dir.exists():
        print(json.dumps({"stream": args.stream, "rollups": []}, indent=2, sort_keys=True))
        return 0

    rows: list[dict[str, object]] = []
    for path in sorted(rollup_dir.glob("rollup_*.json"), key=lambda item: item.name):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            rows.append({
                "path": str(path.relative_to(root)),
                "rollup_week": payload.get("rollup_week"),
                "row_count": payload.get("row_count"),
                "content_sha256": payload.get("content_sha256"),
            })
    print(json.dumps({"stream": args.stream, "rollups": rows}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
