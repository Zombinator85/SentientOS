from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable, Mapping


class VoteJustifier:
    """Attach rationale and precedent references to council votes."""

    def __init__(self, ledger_path: str | Path):
        self.ledger_path = Path(ledger_path)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)

    def record_vote(
        self,
        vote_id: str,
        *,
        agent: str,
        vote: str,
        justification: str,
        precedent_refs: Iterable[str],
        metadata: Mapping[str, object] | None = None,
    ) -> dict:
        entry = {
            "vote_id": vote_id,
            "agent": agent,
            "vote": vote,
            "justification": justification,
            "precedent_refs": list(precedent_refs),
        }
        if metadata:
            entry.update(metadata)
        self._append_jsonl(entry)
        return entry

    def load_votes(self) -> list[dict]:
        votes: list[dict] = []
        if not self.ledger_path.exists():
            return votes
        with self.ledger_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, Mapping):
                    votes.append(dict(parsed))
        return votes

    def render_rationale(self, vote_id: str) -> str:
        relevant = [vote for vote in self.load_votes() if str(vote.get("vote_id")) == str(vote_id)]
        if not relevant:
            return f"No vote found with id {vote_id}."
        lines = [f"# Vote Rationale for {vote_id}", ""]
        for vote in relevant:
            lines.append(f"## Agent: {vote.get('agent')}")
            lines.append(f"Decision: {vote.get('vote')}")
            lines.append("")
            lines.append("Justification:")
            lines.append(vote.get("justification", "<missing>"))
            precedents = vote.get("precedent_refs") or []
            if precedents:
                lines.append("")
                lines.append("Precedent References:")
                for ref in precedents:
                    lines.append(f"- {ref}")
            metadata = {k: v for k, v in vote.items() if k not in {"vote_id", "agent", "vote", "justification", "precedent_refs"}}
            if metadata:
                lines.append("")
                lines.append("Metadata:")
                for key, value in sorted(metadata.items()):
                    lines.append(f"- {key}: {value}")
            lines.append("")
        return "\n".join(lines).strip()

    def _append_jsonl(self, row: Mapping[str, object]) -> None:
        with self.ledger_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render council vote justification")
    parser.add_argument("--vote-id", required=True, help="Vote identifier to render")
    parser.add_argument(
        "--ledger",
        default="council_votes.jsonl",
        help="Path to the council vote ledger (jsonl)",
    )
    args = parser.parse_args()

    justifier = VoteJustifier(args.ledger)
    print(justifier.render_rationale(args.vote_id))


if __name__ == "__main__":
    main()
