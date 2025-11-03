"""Backfill semantic embeddings for legacy memory fragments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable, Iterator, List, Mapping

import semantic_embeddings

from sentientos.storage import get_data_root


def _load_fragments(path: Path) -> List[dict]:
    fragments: List[dict] = []
    if not path.exists():
        return fragments
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                fragments.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return fragments


def _batched(indices: List[int], batch_size: int) -> Iterator[List[int]]:
    for start in range(0, len(indices), batch_size):
        yield indices[start : start + batch_size]


def migrate_embeddings(*, dry_run: bool, batch_size: int, report_path: Path | None = None) -> Mapping[str, object]:
    data_root = get_data_root()
    fragments_path = data_root / "glow" / "memory" / "fragments.jsonl"
    fragments = _load_fragments(fragments_path)
    pending = [idx for idx, fragment in enumerate(fragments) if "embedding" not in fragment]
    migrated = 0
    for batch in _batched(pending, batch_size):
        texts = [str(fragments[idx].get("text", "")) for idx in batch]
        embeddings = semantic_embeddings.encode(texts)
        for idx, vector in zip(batch, embeddings):
            fragments[idx]["embedding"] = vector
            migrated += 1
    if not dry_run and migrated:
        fragments_path.parent.mkdir(parents=True, exist_ok=True)
        with fragments_path.open("w", encoding="utf-8") as handle:
            for fragment in fragments:
                handle.write(json.dumps(fragment) + "\n")
    report = {
        "fragments_path": str(fragments_path),
        "total": len(fragments),
        "migrated": migrated,
        "dry_run": dry_run,
        "pending": len(pending),
    }
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill semantic embeddings")
    parser.add_argument("--dry-run", action="store_true", help="Do not persist updates")
    parser.add_argument("--batch-size", type=int, default=32, help="Number of fragments per batch")
    parser.add_argument("--report", type=Path, help="Optional path to write JSON report")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = migrate_embeddings(dry_run=args.dry_run, batch_size=max(1, args.batch_size), report_path=args.report)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

