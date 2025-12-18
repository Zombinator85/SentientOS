from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

from sentientos.council.governance_council import GovernanceCouncil
from sentientos.reflex.reflex_state_index import ReflexStateIndex


@dataclass
class PetitionRecord:
    rule_id: str
    suppressed_at: str
    improvement_trials: int
    reasons: List[str] = field(default_factory=list)
    council_status: str = "pending"

    def to_dict(self) -> Dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "suppressed_at": self.suppressed_at,
            "improvement_trials": self.improvement_trials,
            "reasons": list(self.reasons),
            "council_status": self.council_status,
        }


def _parse_timestamp(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    text = str(raw)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class ReflexPetitioner:
    def __init__(
        self,
        *,
        blacklist_path: Path | str | None = None,
        trials_path: Path | str | None = None,
        petitions_path: Path | str | None = None,
        ttl_seconds: int = 86_400,
        min_valid_trials: int = 3,
        council: Optional[GovernanceCouncil] = None,
        now_fn: Callable[[], datetime] | None = None,
        state_index: ReflexStateIndex | None = None,
    ) -> None:
        self.blacklist_path = Path(blacklist_path or "reflex_blacklist.json")
        self.trials_path = Path(trials_path or "reflections/reflex_trials.jsonl")
        self.petitions_path = Path(petitions_path or "reflections/reinstatement_petition.jsonl")
        self.ttl = timedelta(seconds=int(ttl_seconds))
        self.min_valid_trials = int(min_valid_trials)
        self.council = council or GovernanceCouncil()
        self._now = now_fn or (lambda: datetime.now(timezone.utc))
        self.state_index = state_index

    def _load_blacklist(self) -> dict[str, dict]:
        if not self.blacklist_path.exists():
            return {}
        try:
            return json.loads(self.blacklist_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _save_blacklist(self, payload: dict[str, dict]) -> None:
        self.blacklist_path.parent.mkdir(parents=True, exist_ok=True)
        self.blacklist_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def _load_trials(self) -> list[dict]:
        if not self.trials_path.exists():
            return []
        trials: list[dict] = []
        for line in self.trials_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "rule_id" not in payload:
                continue
            trials.append(payload)
        return trials

    def _eligible_trials(self, rule_id: str, suppressed_at: datetime, trials: Iterable[dict]) -> list[dict]:
        eligible: list[dict] = []
        for trial in trials:
            if str(trial.get("rule_id")) != rule_id:
                continue
            ts = _parse_timestamp(str(trial.get("timestamp")))
            if ts < suppressed_at:
                continue
            eligible.append(trial)
        return eligible

    @staticmethod
    def _is_successful_trial(trial: dict) -> bool:
        status = str(trial.get("status", "")).lower()
        return status and not ("fail" in status or "error" in status)

    def _route_petition(self, rule_id: str, improvement: int, reasons: list[str]) -> str:
        proposal_id = f"reflex-{rule_id}-{int(self._now().timestamp())}"
        summary = (
            f"Reinstate reflex {rule_id}: {improvement} validated trials since suppression."
        )
        vote = self.council.submit_proposal(
            proposal_id=proposal_id,
            proposal_type="reflex_reinstatement",
            origin="ReflexPetitioner",
            summary=summary,
            proposed_by="reflex_petitioner",
        )
        result = self.council.conduct_vote(vote)
        return result.status

    def _append_petition_log(self, records: Iterable[PetitionRecord]) -> None:
        self.petitions_path.parent.mkdir(parents=True, exist_ok=True)
        with self.petitions_path.open("a", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record.to_dict()) + "\n")

    def process_petitions(self) -> dict[str, object]:
        blacklist = self._load_blacklist()
        trials = self._load_trials()
        petitions: list[PetitionRecord] = []
        reinstated: list[str] = []

        if self.state_index is not None:
            for rule_id, entry in blacklist.items():
                self.state_index.mark_suppressed(rule_id, entry.get("reasons", []), str(entry.get("suppressed_at")))

        for rule_id, entry in blacklist.items():
            suppressed_at = _parse_timestamp(entry.get("suppressed_at"))
            ttl_expired = self._now() - suppressed_at >= self.ttl
            if not ttl_expired:
                continue

            eligible_trials = self._eligible_trials(rule_id, suppressed_at, trials)
            successful_trials = [t for t in eligible_trials if self._is_successful_trial(t)]
            improvement = len(successful_trials)
            if improvement <= self.min_valid_trials:
                if self.state_index is not None:
                    self.state_index.mark_petition(rule_id, eligible=False, trials=improvement)
                continue

            status = self._route_petition(rule_id, improvement, entry.get("reasons", []))
            record = PetitionRecord(
                rule_id=rule_id,
                suppressed_at=suppressed_at.isoformat(),
                improvement_trials=improvement,
                reasons=[str(reason) for reason in entry.get("reasons", [])],
                council_status=status,
            )
            petitions.append(record)
            if status == "approved":
                reinstated.append(rule_id)
            if self.state_index is not None:
                self.state_index.mark_petition(rule_id, eligible=True, trials=improvement)

        if reinstated:
            for rule_id in reinstated:
                blacklist.pop(rule_id, None)
                if self.state_index is not None:
                    self.state_index.mark_reinstated(rule_id)
            self._save_blacklist(blacklist)

        if petitions:
            self._append_petition_log(petitions)

        if self.state_index is not None:
            self.state_index.persist()

        return {
            "petitions_triggered": len(petitions),
            "reinstated": reinstated,
            "remaining_blacklisted": sorted(blacklist.keys()),
            "petition_log": str(self.petitions_path),
        }


__all__ = ["ReflexPetitioner", "PetitionRecord"]
