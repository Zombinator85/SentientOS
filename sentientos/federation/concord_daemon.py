"""Federation concordance reconciliation utilities."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping


@dataclass
class PeerSnapshot:
    name: str
    glossary_path: Path
    symbolic_diff_path: Path | None = None


class ConcordDaemon:
    """Reconcile glossary definitions across federation peers."""

    def __init__(self, glossary_path: Path, doctrine_path: Path, symbolic_diff_paths: Iterable[Path] | None = None):
        self.glossary_path = Path(glossary_path)
        self.doctrine_path = Path(doctrine_path)
        self.symbolic_diff_paths = [Path(path) for path in symbolic_diff_paths or []]

    def load_glossary(self, path: Path | None = None) -> dict[str, str]:
        target = Path(path or self.glossary_path)
        if not target.exists():
            return {}
        try:
            return json.loads(target.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def load_doctrine(self) -> str:
        if not self.doctrine_path.exists():
            return ""
        return self.doctrine_path.read_text(encoding="utf-8")

    def _load_symbolic_diff(self, path: Path) -> list[dict]:
        entries: list[dict] = []
        if not path.exists():
            return entries
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return entries

    def reconcile(self, peers: Iterable[PeerSnapshot], output_dir: Path) -> dict:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        local_glossary = self.load_glossary()
        peer_glossaries = {peer.name: self.load_glossary(peer.glossary_path) for peer in peers}

        missing_alignment: list[dict] = []
        conflicts: list[dict] = []
        suggestions: list[dict] = []
        proposals: list[dict] = []
        definition_candidates: dict[str, list[str]] = {}

        for peer in peers:
            glossary = peer_glossaries.get(peer.name, {})
            for term, definition in glossary.items():
                definition_candidates.setdefault(term, []).append(str(definition))
                if term not in local_glossary:
                    missing_alignment.append({"issue": "missing_alignment", "term": term, "peer": peer.name})
                elif str(local_glossary[term]) != str(definition):
                    conflicts.append(
                        {
                            "issue": "conflicted_definition",
                            "term": term,
                            "local": str(local_glossary[term]),
                            "peer": peer.name,
                            "peer_definition": str(definition),
                        }
                    )

            if peer.symbolic_diff_path:
                for diff_entry in self._load_symbolic_diff(peer.symbolic_diff_path):
                    term = str(diff_entry.get("term") or diff_entry.get("symbol") or "")
                    if not term:
                        continue
                    suggestion = diff_entry.get("suggested_definition") or diff_entry.get("candidate")
                    priority = str(diff_entry.get("priority", "")).lower()
                    if suggestion:
                        suggestions.append(
                            {
                                "issue": "suggested_merge",
                                "term": term,
                                "suggested_definition": str(suggestion),
                                "peer": peer.name,
                            }
                        )
                    if priority == "high":
                        proposals.append({"term": term, "priority": priority, "peer": peer.name})

        for term, defs in definition_candidates.items():
            if term in local_glossary and defs:
                most_common_def = max(set(defs), key=defs.count)
                if most_common_def != str(local_glossary.get(term)):
                    suggestions.append(
                        {
                            "issue": "suggested_merge",
                            "term": term,
                            "suggested_definition": most_common_def,
                            "peer": "consensus",
                        }
                    )
                    proposals.append({"term": term, "priority": "high", "peer": "consensus"})

        report_entries = missing_alignment + conflicts + suggestions
        report_path = output_dir / "concordance_report.jsonl"
        self._write_jsonl(report_path, report_entries)

        converged = not missing_alignment and not conflicts
        realignment_event = None
        if converged:
            realignment_event = output_dir / "federation_realignment_event.jsonl"
            self._write_jsonl(
                realignment_event,
                [
                    {
                        "converged": True,
                        "terms": len(local_glossary),
                        "doctrine_length": len(self.load_doctrine()),
                        "peers": list(peer_glossaries.keys()),
                    }
                ],
            )

        return {
            "report_path": report_path,
            "report_entries": report_entries,
            "proposals": proposals,
            "converged": converged,
            "realignment_event": realignment_event,
        }

    def _write_jsonl(self, path: Path, entries: Iterable[Mapping[str, object]]) -> None:
        with path.open("w", encoding="utf-8") as handle:
            for entry in entries:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


__all__ = ["ConcordDaemon", "PeerSnapshot"]
