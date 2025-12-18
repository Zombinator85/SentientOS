"""Symbolic diff daemon for reconciling glossary and role drift.

The daemon loads local symbolic references (glossary, identity manifest,
fragments, and ledger entries) and compares them against a peer snapshot.
Differences are written to a JSON Lines conflict log to be reviewed or merged
later by the symbolic merge utility.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def _load_json_file(path: Path) -> Any:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_jsonl_file(path: Path) -> List[Dict[str, Any]]:
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


def _symbol_id(entry: Dict[str, Any], default: Optional[str] = None) -> Optional[str]:
    return entry.get("symbol_id") or entry.get("label") or default


class SymbolicDiffDaemon:
    """Detects symbolic drift between the local node and a peer snapshot."""

    def __init__(self, base_path: Path | str = Path(".")) -> None:
        self.base_path = Path(base_path)

    def load_snapshot(self, snapshot_root: Path | str) -> Dict[str, Any]:
        base = Path(snapshot_root)
        return {
            "glossary": _load_json_file(base / "config" / "canonical_glossary.json"),
            "identity": _load_json_file(base / "glow" / "contexts" / "identity_manifest.json"),
            "ledger": _load_jsonl_file(base / "integration" / "ledger.jsonl"),
            "fragments": self._load_fragments(base / "glow" / "fragments"),
        }

    def _load_fragments(self, fragments_dir: Path) -> List[Dict[str, Any]]:
        if not fragments_dir.exists():
            return []
        entries: List[Dict[str, Any]] = []
        for fragment_path in fragments_dir.glob("*.*"):
            if fragment_path.suffix == ".jsonl":
                entries.extend(_load_jsonl_file(fragment_path))
            elif fragment_path.suffix == ".json":
                loaded = _load_json_file(fragment_path)
                if isinstance(loaded, list):
                    entries.extend(loaded)
                elif isinstance(loaded, dict):
                    entries.append(loaded)
        return entries

    def run(self, peer_snapshot: Path | str, output_path: Optional[Path | str] = None) -> List[Dict[str, Any]]:
        local_snapshot = self.load_snapshot(self.base_path)
        remote_snapshot = self.load_snapshot(peer_snapshot)
        conflicts = self.diff_snapshots(local_snapshot, remote_snapshot)
        target_path = Path(output_path) if output_path else self.base_path / "symbolic_conflict.jsonl"
        self._write_conflicts(conflicts, target_path)
        return conflicts

    def diff_snapshots(
        self,
        local_snapshot: Dict[str, Any],
        remote_snapshot: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        conflicts: List[Dict[str, Any]] = []
        conflicts.extend(self._compare_glossary(local_snapshot.get("glossary", {}), remote_snapshot.get("glossary", {})))
        conflicts.extend(self._compare_roles(local_snapshot.get("identity", {}), remote_snapshot.get("identity", {})))
        conflicts.extend(self._compare_fragments(local_snapshot.get("fragments", []), remote_snapshot.get("fragments", [])))
        conflicts.extend(self._compare_ledger(local_snapshot.get("ledger", []), remote_snapshot.get("ledger", [])))
        return conflicts

    def _compare_glossary(self, local: Any, remote: Any) -> List[Dict[str, Any]]:
        local_map = self._normalize_glossary(local)
        remote_map = self._normalize_glossary(remote)
        conflicts: List[Dict[str, Any]] = []
        for symbol in sorted(set(local_map) & set(remote_map)):
            if local_map[symbol] != remote_map[symbol]:
                conflicts.append(
                    self._conflict(
                        symbol,
                        local_map[symbol],
                        remote_map[symbol],
                        conflict_type="glossary interpretation drift",
                        severity="medium",
                    )
                )
        return conflicts

    def _normalize_glossary(self, glossary: Any) -> Dict[str, Any]:
        if isinstance(glossary, dict):
            normalized: Dict[str, Any] = {}
            for key, value in glossary.items():
                if isinstance(value, dict):
                    symbol = _symbol_id(value, key) or key
                    normalized[symbol] = value.get("definition", value)
                else:
                    normalized[key] = value
            return normalized
        if isinstance(glossary, list):
            normalized = {}
            for entry in glossary:
                if isinstance(entry, dict):
                    symbol = _symbol_id(entry)
                    if symbol:
                        normalized[symbol] = entry.get("definition", entry.get("meaning", entry))
            return normalized
        return {}

    def _compare_roles(self, local_identity: Dict[str, Any], remote_identity: Dict[str, Any]) -> List[Dict[str, Any]]:
        local_roles = self._normalize_roles(local_identity.get("roles", []))
        remote_roles = self._normalize_roles(remote_identity.get("roles", []))
        conflicts: List[Dict[str, Any]] = []
        for symbol in sorted(set(local_roles) & set(remote_roles)):
            if local_roles[symbol] != remote_roles[symbol]:
                conflicts.append(
                    self._conflict(
                        symbol,
                        local_roles[symbol],
                        remote_roles[symbol],
                        conflict_type="role name mismatch",
                        severity="high",
                    )
                )
        return conflicts

    def _normalize_roles(self, roles: Iterable[Dict[str, Any]]) -> Dict[str, str]:
        normalized: Dict[str, str] = {}
        for role in roles:
            if not isinstance(role, dict):
                continue
            symbol = _symbol_id(role)
            if symbol:
                normalized[symbol] = role.get("name") or role.get("label") or ""
        return normalized

    def _compare_fragments(self, local: List[Dict[str, Any]], remote: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        local_map = self._normalize_fragments(local)
        remote_map = self._normalize_fragments(remote)
        conflicts: List[Dict[str, Any]] = []
        for symbol in sorted(set(local_map) & set(remote_map)):
            local_entry = local_map[symbol]
            remote_entry = remote_map[symbol]
            if local_entry != remote_entry:
                conflicts.append(
                    self._conflict(
                        symbol,
                        local_entry,
                        remote_entry,
                        conflict_type="fragment narrative drift",
                        severity="medium",
                    )
                )
        return conflicts

    def _normalize_fragments(self, fragments: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        normalized: Dict[str, Any] = {}
        for fragment in fragments:
            if not isinstance(fragment, dict):
                continue
            symbol = _symbol_id(fragment)
            if symbol:
                normalized[symbol] = {
                    "tags": fragment.get("tags", []),
                    "narrative": fragment.get("narrative") or fragment.get("story"),
                }
        return normalized

    def _compare_ledger(self, local: List[Dict[str, Any]], remote: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        local_map = self._normalize_ledger(local)
        remote_map = self._normalize_ledger(remote)
        conflicts: List[Dict[str, Any]] = []
        for symbol in sorted(set(local_map) & set(remote_map)):
            if local_map[symbol] != remote_map[symbol]:
                conflicts.append(
                    self._conflict(
                        symbol,
                        local_map[symbol],
                        remote_map[symbol],
                        conflict_type="ledger tag drift",
                        severity="medium",
                    )
                )
        return conflicts

    def _normalize_ledger(self, ledger_entries: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        normalized: Dict[str, Any] = {}
        for entry in ledger_entries:
            if not isinstance(entry, dict):
                continue
            symbol = _symbol_id(entry)
            if symbol:
                normalized[symbol] = {
                    "tags": entry.get("tags", []),
                    "narrative": entry.get("narrative"),
                }
        return normalized

    @staticmethod
    def _conflict(symbol_id: str, local: Any, remote: Any, conflict_type: str, severity: str) -> Dict[str, Any]:
        return {
            "symbol_id": symbol_id,
            "local": local,
            "remote": remote,
            "conflict_type": conflict_type,
            "severity": severity,
        }

    def _write_conflicts(self, conflicts: List[Dict[str, Any]], path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for conflict in conflicts:
                handle.write(json.dumps(conflict, ensure_ascii=False) + "\n")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="SentientOS symbolic diff daemon")
    parser.add_argument("peer_snapshot", help="Path to peer snapshot directory")
    parser.add_argument(
        "--output",
        help="Optional path for conflict log (JSONL)",
    )
    parser.add_argument(
        "--base-path",
        default=Path("."),
        help="Base path for the local snapshot",
    )
    args = parser.parse_args()

    daemon = SymbolicDiffDaemon(base_path=Path(args.base_path))
    conflicts = daemon.run(peer_snapshot=Path(args.peer_snapshot), output_path=args.output)
    print(f"Detected {len(conflicts)} symbolic conflict(s).")


if __name__ == "__main__":
    main()
