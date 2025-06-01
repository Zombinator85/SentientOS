from __future__ import annotations

"""Avatar Ritual Artifact Gallery.

Aggregates artifact logs (dreams, gifts, relics, etc.) and allows
filtering and viewing from the command line. Each view is logged for
ritual memory.
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# Log locations
LOG_PATHS = {
    "dream": Path(os.getenv("AVATAR_DREAM_LOG", "logs/avatar_dreams.jsonl")),
    "gift": Path(os.getenv("AVATAR_GIFT_LOG", "logs/avatar_gifts.jsonl")),
    "artifact": Path(os.getenv("AVATAR_ARTIFACT_LOG", "logs/avatar_sanctuary_artifacts.jsonl")),
    "relic": Path("logs/avatar_relics.jsonl"),
    "capsule": Path(os.getenv("AVATAR_FESTIVAL_CAPSULE_LOG", "logs/avatar_festival_capsules.jsonl")),
}

GALLERY_LOG = Path(os.getenv("ARTIFACT_GALLERY_LOG", "logs/artifact_gallery_log.jsonl"))
GALLERY_LOG.parent.mkdir(parents=True, exist_ok=True)


def load_entries(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def gather_artifacts() -> List[Dict[str, Any]]:
    all_entries = []
    for source, path in LOG_PATHS.items():
        for item in load_entries(path):
            item["source"] = source
            all_entries.append(item)
    return all_entries


def filter_artifacts(
    artifacts: List[Dict[str, Any]],
    creator: str | None = None,
    source: str | None = None,
    contains: str | None = None,
) -> List[Dict[str, Any]]:
    out = []
    for art in artifacts:
        if creator and art.get("creator") != creator and art.get("avatar") != creator:
            continue
        if source and art.get("source") != source:
            continue
        if contains:
            text = json.dumps(art, ensure_ascii=False)
            if contains not in text:
                continue
        out.append(art)
    return out


def log_view(filters: Dict[str, Any], count: int) -> None:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "filters": filters,
        "count": count,
    }
    with GALLERY_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="Avatar Ritual Artifact Gallery")
    ap.add_argument("list", nargs="?", help="List artifacts", default="list")
    ap.add_argument("--creator", help="Filter by creator/avatar")
    ap.add_argument("--source", help="Filter by artifact source")
    ap.add_argument("--contains", help="Filter if JSON contains substring")
    args = ap.parse_args()

    arts = gather_artifacts()
    filtered = filter_artifacts(arts, args.creator, args.source, args.contains)
    print(json.dumps(filtered, indent=2))

    log_view({"creator": args.creator, "source": args.source, "contains": args.contains}, len(filtered))


if __name__ == "__main__":
    main()
