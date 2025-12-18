from __future__ import annotations

"""Read-only symbol unifier.

The unifier consumes lint feedback, ledger snapshots, hygiene reports, and
concordance signals to emit a canonical symbol map without mutating any source
material. Outputs include JSON-ready dictionaries and Markdown summaries for
human review.
"""

import json
from dataclasses import dataclass
from typing import Iterable, Mapping, MutableMapping, Sequence


@dataclass(frozen=True)
class SymbolSnapshot:
    accepted: tuple[str, ...]
    deprecated: tuple[str, ...]
    tolerated_legacy: tuple[str, ...]

    def to_json(self) -> str:
        return json.dumps(
            {
                "accepted_terms": list(self.accepted),
                "deprecated_terms": list(self.deprecated),
                "tolerated_legacy": list(self.tolerated_legacy),
            },
            indent=2,
            sort_keys=True,
        )

    def to_markdown(self) -> str:
        lines = ["# Canonical Symbol Snapshot", "", "## Accepted", *[f"- {term}" for term in self.accepted], "", "## Deprecated", *[f"- {term}" for term in self.deprecated], "", "## Tolerated Legacy", *[f"- {term}" for term in self.tolerated_legacy]]
        return "\n".join(lines).strip() + "\n"


class SymbolUnifier:
    """Create a canonical symbol view without mutating upstream ledgers."""

    def __init__(self) -> None:
        self._notes: list[str] = []

    def unify(
        self,
        glossary_lint: Sequence[Mapping[str, object]],
        ledger_entries: Sequence[Mapping[str, object]],
        hygiene_report: Mapping[str, object],
        concord_events: Sequence[Mapping[str, object]],
    ) -> dict[str, object]:
        lint_terms = self._collect_terms(glossary_lint)
        ledger_terms = self._collect_ledger_terms(ledger_entries)
        hygiene_terms = set(str(entry.get("term")) for entry in hygiene_report.get("violations", []) if entry.get("term"))
        concord_terms = set(str(entry.get("term")) for entry in concord_events if entry.get("term"))

        accepted = sorted((ledger_terms["accepted"] | concord_terms) - lint_terms["deprecated"] - hygiene_terms)
        deprecated = sorted(lint_terms["deprecated"] | ledger_terms["deprecated"] | hygiene_terms)
        tolerated = sorted(lint_terms["tolerated"] | (ledger_terms["accepted"] & lint_terms["deprecated"]))

        snapshot = SymbolSnapshot(tuple(accepted), tuple(deprecated), tuple(tolerated))
        return {
            "snapshot": snapshot,
            "markdown": snapshot.to_markdown(),
            "json": snapshot.to_json(),
            "notes": list(self._notes),
        }

    def _collect_terms(self, lint_entries: Iterable[Mapping[str, object]]) -> MutableMapping[str, set[str]]:
        accepted: set[str] = set()
        deprecated: set[str] = set()
        tolerated: set[str] = set()
        for entry in lint_entries:
            term = str(entry.get("term") or entry.get("symbol") or "").strip()
            if not term:
                continue
            status = str(entry.get("status") or "accepted").lower()
            if status in {"deprecated", "forbidden"}:
                deprecated.add(term)
            elif status in {"legacy", "tolerated"}:
                tolerated.add(term)
            else:
                accepted.add(term)
        return {"accepted": accepted, "deprecated": deprecated, "tolerated": tolerated}

    def _collect_ledger_terms(self, entries: Iterable[Mapping[str, object]]) -> MutableMapping[str, set[str]]:
        accepted: set[str] = set()
        deprecated: set[str] = set()
        for entry in entries:
            term = str(entry.get("term") or "").strip()
            if not term:
                continue
            if str(entry.get("status")) == "deprecated":
                deprecated.add(term)
            else:
                accepted.add(term)
        return {"accepted": accepted, "deprecated": deprecated}


__all__ = ["SymbolSnapshot", "SymbolUnifier"]
