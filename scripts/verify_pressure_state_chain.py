from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from scripts.provenance_hash_chain import HASH_ALGO, canonical_json_bytes
except ModuleNotFoundError:  # pragma: no cover
    from provenance_hash_chain import HASH_ALGO, canonical_json_bytes

GENESIS_PREV_STATE_HASH = "GENESIS"


def _compute_snapshot_hash(payload: dict[str, Any], prev_state_hash: str | None) -> str:
    material = {key: value for key, value in payload.items() if key != "state_hash"}
    prev_marker = prev_state_hash or GENESIS_PREV_STATE_HASH
    import hashlib

    digest = hashlib.sha256()
    digest.update(prev_marker.encode("utf-8"))
    digest.update(b"\n")
    digest.update(canonical_json_bytes(material))
    return digest.hexdigest()


def verify_pressure_state_chain(
    state_dir: Path,
    *,
    events_path: Path | None = None,
) -> dict[str, Any]:
    snapshots_dir = state_dir / "snapshots"
    latest_path = state_dir / "latest.json"
    issues: list[str] = []

    if not snapshots_dir.exists():
        issues.append("missing snapshots directory")
        return {"integrity_ok": False, "issues": issues, "snapshot_count": 0}

    snapshot_paths = sorted(path for path in snapshots_dir.glob("*.json") if path.is_file())
    if not snapshot_paths:
        issues.append("no snapshots found")
        return {"integrity_ok": False, "issues": issues, "snapshot_count": 0}

    prev_hash: str | None = None
    observed_hashes: set[str] = set()
    for index, snapshot_path in enumerate(snapshot_paths):
        try:
            payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            issues.append(f"{snapshot_path.name}: invalid json")
            continue
        if not isinstance(payload, dict):
            issues.append(f"{snapshot_path.name}: payload must be object")
            continue

        hash_algo = payload.get("hash_algo")
        if hash_algo != HASH_ALGO:
            issues.append(f"{snapshot_path.name}: hash_algo mismatch ({hash_algo!r})")

        declared_prev = payload.get("prev_state_hash")
        if index == 0:
            if declared_prev != GENESIS_PREV_STATE_HASH:
                issues.append(f"{snapshot_path.name}: first prev_state_hash must be GENESIS")
        elif declared_prev != prev_hash:
            issues.append(
                f"{snapshot_path.name}: prev_state_hash mismatch expected {prev_hash} got {declared_prev}"
            )

        declared_hash = payload.get("state_hash")
        if not isinstance(declared_hash, str) or not declared_hash:
            issues.append(f"{snapshot_path.name}: missing state_hash")
            prev_hash = None
            continue

        expected_hash = _compute_snapshot_hash(payload, None if declared_prev == GENESIS_PREV_STATE_HASH else str(declared_prev))
        if declared_hash != expected_hash:
            issues.append(f"{snapshot_path.name}: state_hash mismatch")

        observed_hashes.add(declared_hash)
        prev_hash = declared_hash

    if latest_path.exists():
        latest = json.loads(latest_path.read_text(encoding="utf-8"))
        if isinstance(latest, dict):
            latest_hash = latest.get("state_hash")
            if snapshot_paths and isinstance(latest_hash, str) and latest_hash != prev_hash:
                issues.append("latest.json state_hash does not match newest snapshot")
        else:
            issues.append("latest.json payload must be object")
    else:
        issues.append("missing latest.json")

    if events_path is not None and events_path.exists():
        for line_no, line in enumerate(events_path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                issues.append(f"events line {line_no}: invalid json")
                continue
            metadata = event.get("metadata") if isinstance(event, dict) else None
            if not isinstance(metadata, dict):
                continue
            if metadata.get("event_type") != "proof_budget_governor":
                continue
            governor = metadata.get("governor")
            if not isinstance(governor, dict):
                issues.append(f"events line {line_no}: missing governor payload")
                continue
            new_hash = governor.get("pressure_state_new_hash")
            skipped = bool(governor.get("state_update_skipped", False))
            if skipped:
                continue
            if isinstance(new_hash, str):
                if new_hash not in observed_hashes:
                    issues.append(f"events line {line_no}: referenced pressure_state_new_hash not found")
            else:
                issues.append(f"events line {line_no}: missing pressure_state_new_hash")

    return {
        "integrity_ok": not issues,
        "issues": issues,
        "snapshot_count": len(snapshot_paths),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify pressure-state hash chain integrity.")
    parser.add_argument("state_dir", type=Path, help="Directory containing latest.json and snapshots/")
    parser.add_argument("--events", type=Path, help="Optional governor JSONL log to cross-check hashes")
    args = parser.parse_args()

    result = verify_pressure_state_chain(args.state_dir, events_path=args.events)
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result["integrity_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
