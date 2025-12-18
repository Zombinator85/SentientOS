from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Mapping

class SymbolLedgerDaemon:
    """Unify symbolic glossary terms across peers into a canonical ledger with justifications and validations."""
    def __init__(self, ledger_path: Path | str | None = None) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        self.ledger_path = Path(ledger_path) if ledger_path else repo_root / "federation" / "symbol_ledger.jsonl"
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self.ledger_path.touch(exist_ok=True)

    def unify_glossaries(self, peer_glossaries: Mapping[str, Dict[str, str]]) -> dict:
        """Compute canonical definitions for terms from multiple peer glossaries and append to ledger if new or changed."""
        # Load last known canonical definitions
        last_canonical: Dict[str, str] = {}
        if self.ledger_path.exists():
            with self.ledger_path.open("r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    term = str(entry.get("term") or "")
                    definition = str(entry.get("definition") or "")
                    if term:
                        # Keep the most recent entry for each term
                        last_canonical[term] = definition

        timestamp = datetime.now(timezone.utc).isoformat()
        new_entries: list[dict] = []
        all_terms = {term for glossary in peer_glossaries.values() for term in glossary}
        for term in sorted(all_terms):
            # Determine canonical definition by consensus
            definitions: Dict[str, int] = {}
            for peer_name, glossary in peer_glossaries.items():
                if term in glossary:
                    def_str = str(glossary[term])
                    definitions[def_str] = definitions.get(def_str, 0) + 1
            if not definitions:
                continue
            # Choose most common definition; tie-break deterministically by lexicographic order
            most_common_def = max(definitions.items(), key=lambda kv: (kv[1], -1 if kv[0] is None else 0, kv[0]))[0]
            count = definitions[most_common_def]
            total_sources = sum(definitions.values())
            if count == total_sources and total_sources > 1:
                justification = f"unanimous consensus from {count} sources"
            elif count > 1:
                justification = f"chosen by majority consensus of {count} out of {total_sources} sources"
            else:
                # Single source provided this term/definition
                source_peer = next((name for name, gloss in peer_glossaries.items() if term in gloss and str(gloss[term]) == most_common_def), None)
                justification = f"adopted from peer '{source_peer}'"
            prev_def = last_canonical.get(term)
            if prev_def is None or str(prev_def) != most_common_def:
                # Create a new ledger entry for this term
                validations: list[dict] = []
                for peer_name, glossary in peer_glossaries.items():
                    if term in glossary:
                        peer_def = str(glossary[term])
                        if peer_def == most_common_def:
                            status = "aligned"
                        else:
                            status = "diverged"
                        entry = {"peer": peer_name, "status": status}
                        if status == "diverged":
                            entry["peer_definition"] = peer_def
                        validations.append(entry)
                    else:
                        validations.append({"peer": peer_name, "status": "missing"})
                ledger_entry = {
                    "timestamp": timestamp,
                    "event": "symbol_ledger",
                    "term": term,
                    "definition": most_common_def,
                    "justification": justification,
                    "validations": validations
                }
                if prev_def is not None:
                    ledger_entry["previous_definition"] = str(prev_def)
                new_entries.append(ledger_entry)
                with self.ledger_path.open("a", encoding="utf-8") as ledger_file:
                    ledger_file.write(json.dumps(ledger_entry, ensure_ascii=False) + "\n")
        return {
            "terms_processed": len(all_terms),
            "new_entries": len(new_entries),
            "entries": new_entries,
            "ledger_path": str(self.ledger_path),
        }
