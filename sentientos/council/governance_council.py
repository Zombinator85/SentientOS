import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple


@dataclass
class CouncilVote:
    proposal_id: str
    proposal_type: str
    origin: str
    summary: str
    proposed_by: str
    timestamp: str
    votes: Dict[str, str] = field(default_factory=dict)
    quorum_required: int = 3
    status: str = "pending"

    def to_dict(self) -> Dict[str, object]:
        return {
            "proposal_id": self.proposal_id,
            "proposal_type": self.proposal_type,
            "origin": self.origin,
            "summary": self.summary,
            "proposed_by": self.proposed_by,
            "timestamp": self.timestamp,
            "votes": self.votes,
            "quorum_required": self.quorum_required,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, object]) -> "CouncilVote":
        return cls(
            proposal_id=str(payload["proposal_id"]),
            proposal_type=str(payload["proposal_type"]),
            origin=str(payload["origin"]),
            summary=str(payload["summary"]),
            proposed_by=str(payload["proposed_by"]),
            timestamp=str(payload["timestamp"]),
            votes=dict(payload.get("votes", {})),
            quorum_required=int(payload.get("quorum_required", 3)),
            status=str(payload.get("status", "pending")),
        )


class GovernanceCouncil:
    SUPPORTED_TYPES = {
        "doctrine_update",
        "symbol_approval",
        "conflict_resolution",
        "reflex_reinstatement",
    }

    def __init__(
        self,
        ledger_path: Optional[Path] = None,
        verdicts_path: Optional[Path] = None,
        agent_behaviors: Optional[Iterable[Tuple[str, Callable[[CouncilVote], str]]]] = None,
        quorum_required: int = 3,
    ) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        self.ledger_path = ledger_path or repo_root / "council" / "vote_ledger.jsonl"
        self.verdicts_path = verdicts_path or repo_root / "council" / "verdicts.jsonl"
        self.quorum_required = quorum_required

        self.agent_behaviors: List[Tuple[str, Callable[[CouncilVote], str]]] = (
            list(agent_behaviors) if agent_behaviors is not None else self._default_agents()
        )

        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self.ledger_path.touch(exist_ok=True)
        self.verdicts_path.touch(exist_ok=True)

    def _default_agents(self) -> List[Tuple[str, Callable[[CouncilVote], str]]]:
        return [
            ("ArchitectDaemon", self._architect_daemon_vote),
            ("CodexDaemon", self._codex_daemon_vote),
            ("IntegrityDaemon", self._integrity_daemon_vote),
            ("IntegrationMemory", self._integration_memory_vote),
            ("ReflexGuardian", self._reflex_guardian_vote),
        ]

    def submit_proposal(
        self, proposal_id: str, proposal_type: str, origin: str, summary: str, proposed_by: str
    ) -> CouncilVote:
        if proposal_type not in self.SUPPORTED_TYPES:
            raise ValueError(f"Unsupported proposal type: {proposal_type}")

        vote = CouncilVote(
            proposal_id=proposal_id,
            proposal_type=proposal_type,
            origin=origin,
            summary=summary,
            proposed_by=proposed_by,
            timestamp=datetime.utcnow().isoformat() + "Z",
            quorum_required=self.quorum_required,
        )
        return vote

    def conduct_vote(self, vote: CouncilVote) -> CouncilVote:
        for agent_name, behavior in self.agent_behaviors:
            vote.votes[agent_name] = behavior(vote)

        vote.status = self._evaluate_status(vote)
        self._append_to_ledger(vote)

        if vote.status in {"approved", "rejected"}:
            self._append_verdict(vote)

        return vote

    def _evaluate_status(self, vote: CouncilVote) -> str:
        approvals = sum(1 for decision in vote.votes.values() if decision == "approve")
        rejections = sum(1 for decision in vote.votes.values() if decision == "reject")
        if approvals >= vote.quorum_required:
            return "approved"
        if rejections >= vote.quorum_required:
            return "rejected"
        return "no_quorum"

    def _append_to_ledger(self, vote: CouncilVote) -> None:
        with self.ledger_path.open("a", encoding="utf-8") as ledger_file:
            ledger_file.write(json.dumps(vote.to_dict()) + "\n")

    def _append_verdict(self, vote: CouncilVote) -> None:
        verdict_payload = {
            "proposal_id": vote.proposal_id,
            "proposal_type": vote.proposal_type,
            "status": vote.status,
            "votes": vote.votes,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "summary": vote.summary,
        }
        with self.verdicts_path.open("a", encoding="utf-8") as verdicts_file:
            verdicts_file.write(json.dumps(verdict_payload) + "\n")

    def load_vote(self, proposal_id: str) -> Optional[CouncilVote]:
        with self.ledger_path.open("r", encoding="utf-8") as ledger_file:
            for line in ledger_file:
                if not line.strip():
                    continue
                payload = json.loads(line)
                if payload.get("proposal_id") == proposal_id:
                    return CouncilVote.from_dict(payload)
        return None

    @staticmethod
    def _architect_daemon_vote(vote: CouncilVote) -> str:
        if "overreach" in vote.summary.lower():
            return "reject"
        if vote.proposal_type in {"doctrine_update", "conflict_resolution"}:
            return "approve"
        return "approve" if "harmonize" in vote.summary.lower() else "abstain"

    @staticmethod
    def _codex_daemon_vote(vote: CouncilVote) -> str:
        if vote.proposal_type == "symbol_approval":
            return "approve"
        if "forbidden" in vote.summary.lower():
            return "reject"
        return "approve"

    @staticmethod
    def _integrity_daemon_vote(vote: CouncilVote) -> str:
        if "drift" in vote.summary.lower():
            return "reject"
        return "approve" if vote.proposal_type != "reflex_reinstatement" else "abstain"

    @staticmethod
    def _integration_memory_vote(vote: CouncilVote) -> str:
        if "uncertain" in vote.summary.lower():
            return "abstain"
        return "approve"

    @staticmethod
    def _reflex_guardian_vote(vote: CouncilVote) -> str:
        if vote.proposal_type == "reflex_reinstatement":
            return "approve"
        if "conflict" in vote.summary.lower():
            return "reject"
        return "abstain"
