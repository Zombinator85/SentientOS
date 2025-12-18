from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, Tuple


def _load_jsonl(path: Path) -> Iterable[dict]:
    if not path.exists():
        return []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def _build_verdict_index(verdicts_path: Path) -> Dict[str, str]:
    verdicts: Dict[str, str] = {}
    for entry in _load_jsonl(verdicts_path):
        proposal_id = entry.get("proposal_id")
        status = entry.get("status")
        if isinstance(proposal_id, str) and isinstance(status, str):
            verdicts[proposal_id] = status
    return verdicts


def _expected_vote(status: str) -> str | None:
    if status == "approved":
        return "approve"
    if status == "rejected":
        return "reject"
    return None


def build_council_dossier(vote_ledger: Path, verdicts_path: Path) -> Tuple[Dict[str, object], str]:
    proposals = list(_load_jsonl(vote_ledger))
    verdict_index = _build_verdict_index(verdicts_path)
    total_proposals = len(proposals)

    agent_stats: Dict[str, dict] = defaultdict(lambda: {
        "votes_cast": 0,
        "proposal_types": defaultdict(int),
        "dissents": 0,
        "symbolic_stance": None,
    })

    for proposal in proposals:
        proposal_id = proposal.get("proposal_id")
        proposal_type = str(proposal.get("proposal_type", "unknown"))
        votes: dict = proposal.get("votes", {}) or {}
        expected = _expected_vote(verdict_index.get(str(proposal_id), ""))
        for agent, decision in votes.items():
            agent_stat = agent_stats[agent]
            agent_stat["votes_cast"] += 1
            agent_stat["proposal_types"][proposal_type] += 1
            if expected and decision != expected:
                agent_stat["dissents"] += 1
            if proposal_type.startswith("symbol"):
                agent_stat["symbolic_stance"] = decision

    summary: Dict[str, object] = {"agents": {}, "total_proposals": total_proposals}
    for agent, stats in agent_stats.items():
        votes_cast = stats["votes_cast"]
        dissents = stats["dissents"]
        participation_rate = votes_cast / total_proposals if total_proposals else 0.0
        dissent_frequency = dissents / votes_cast if votes_cast else 0.0
        summary["agents"][agent] = {
            "votes_cast": votes_cast,
            "participation_rate": round(participation_rate, 3),
            "dissent_frequency": round(dissent_frequency, 3),
            "proposal_types": dict(stats["proposal_types"]),
            "last_symbolic_stance": stats["symbolic_stance"],
        }

    markdown_lines = ["# Governance Council Dossier", "", f"Total proposals: {total_proposals}", ""]
    for agent, stats in summary["agents"].items():
        markdown_lines.append(f"## {agent}")
        markdown_lines.append(f"- Participation: {stats['participation_rate']:.2f}")
        markdown_lines.append(f"- Dissent frequency: {stats['dissent_frequency']:.2f}")
        markdown_lines.append(f"- Last symbolic stance: {stats['last_symbolic_stance']}")
        breakdown = ", ".join(
            f"{ptype}:{count}" for ptype, count in sorted(stats["proposal_types"].items())
        )
        markdown_lines.append(f"- Proposal types: {breakdown if breakdown else 'none'}")
        markdown_lines.append("")

    markdown_snapshot = "\n".join(markdown_lines)
    return summary, markdown_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Governance Council dossier snapshots")
    parser.add_argument(
        "--vote-ledger",
        type=Path,
        default=Path("council") / "vote_ledger.jsonl",
        help="Path to council vote ledger JSONL",
    )
    parser.add_argument(
        "--verdicts",
        type=Path,
        default=Path("council") / "verdicts.jsonl",
        help="Path to council verdicts JSONL",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("council") / "council_dossier.json",
        help="Where to write the dossier summary JSON",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=Path("council") / "council_dossier.md",
        help="Where to write the dashboard markdown snapshot",
    )
    args = parser.parse_args()

    summary, markdown = build_council_dossier(args.vote_ledger, args.verdicts)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(markdown, encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    print("\n" + markdown)


if __name__ == "__main__":
    main()
