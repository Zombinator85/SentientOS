"""Merge resolutions for symbolic conflicts detected by the diff daemon."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    records: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def _write_jsonl(path: Path, records: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def resolve_conflicts(
    conflict_path: Path,
    resolution: str,
    merge_log_path: Path,
    council_queue_path: Path | None = None,
) -> List[Dict[str, Any]]:
    resolution = resolution.lower()
    if resolution not in {"local", "peer", "council"}:
        raise ValueError("Resolution must be one of: local, peer, council")

    conflicts = _load_jsonl(conflict_path)
    merge_records: List[Dict[str, Any]] = []
    council_records: List[Dict[str, Any]] = _load_jsonl(council_queue_path) if council_queue_path else []
    timestamp = datetime.utcnow().isoformat() + "Z"

    for conflict in conflicts:
        decision_record = {
            "symbol_id": conflict.get("symbol_id"),
            "resolution": resolution,
            "resolved_at": timestamp,
        }

        if resolution == "local":
            decision_record["applied_value"] = conflict.get("local")
        elif resolution == "peer":
            decision_record["applied_value"] = conflict.get("remote")
        elif resolution == "council":
            council_records.append(
                {
                    "symbol_id": conflict.get("symbol_id"),
                    "proposed_local": conflict.get("local"),
                    "proposed_remote": conflict.get("remote"),
                    "submitted_at": timestamp,
                    "conflict_type": conflict.get("conflict_type"),
                }
            )

        merge_records.append(decision_record)

    _write_jsonl(merge_log_path, merge_records)
    if council_queue_path:
        _write_jsonl(council_queue_path, council_records)

    return merge_records


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve symbolic conflicts")
    parser.add_argument("conflicts", help="Path to symbolic_conflict.jsonl")
    parser.add_argument("resolution", choices=["local", "peer", "council"], help="Resolution strategy")
    parser.add_argument(
        "--merge-log",
        default=Path("symbolic_merge_log.jsonl"),
        help="Path to write merge decision log",
    )
    parser.add_argument(
        "--council-queue",
        help="Optional council queue file for escalated conflicts",
    )
    args = parser.parse_args()

    merge_log_path = Path(args.merge_log)
    council_path = Path(args.council_queue) if args.council_queue else None

    applied = resolve_conflicts(Path(args.conflicts), args.resolution, merge_log_path, council_path)
    print(f"Applied {len(applied)} resolution(s) using '{args.resolution}' policy.")


if __name__ == "__main__":
    main()
