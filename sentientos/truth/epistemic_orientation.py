from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Literal, Mapping


EpistemicEntryType = Literal["observation", "inference", "pattern", "contradiction", "suspension", "belief"]
SourceClass = Literal["internal_synthesis", "external_witness", "inference"]
SuspensionReason = Literal["lack_of_data", "conflicting_data", "deliberate_non_resolution"]


@dataclass(frozen=True)
class EpistemicEntry:
    entry_id: str
    claim: str
    entry_type: EpistemicEntryType
    source_class: SourceClass
    confidence: float
    volatility: float
    confidence_band: tuple[float, float]
    since_day: int
    recorded_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ContradictionLink:
    topic: str
    claim_a: str
    claim_b: str
    status: str = "coexisting contradiction"


@dataclass(frozen=True)
class SuspensionRecord:
    claim_id: str
    reason: SuspensionReason
    since_day: int
    note: str | None = None


class EpistemicLedger:
    """Append-only record of epistemic positions without prescribing action."""

    def __init__(self, starting_day: int = 0):
        self.entries: list[EpistemicEntry] = []
        self.current_day = starting_day

    def advance_day(self, days: int = 1) -> None:
        self.current_day += max(0, days)

    def compute_confidence_band(self, confidence: float, volatility: float) -> tuple[float, float]:
        spread = min(0.4, volatility * 0.5)
        lower = max(0.0, confidence - spread)
        upper = min(1.0, confidence + spread)
        return (round(lower, 3), round(upper, 3))

    def estimate_volatility(self, confidences: Iterable[float]) -> float:
        values = list(confidences)
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        return min(1.0, variance**0.5)

    def apply_confidence_decay(self, confidence: float, days_elapsed: int, decay_rate: float = 0.05) -> float:
        decayed = confidence * (1 - decay_rate) ** max(0, days_elapsed)
        return max(0.0, min(1.0, decayed))

    def _record(
        self,
        *,
        entry_id: str,
        claim: str,
        entry_type: EpistemicEntryType,
        source_class: SourceClass,
        confidence: float,
        volatility: float,
        since_day: int | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> EpistemicEntry:
        scope_day = self.current_day if since_day is None else since_day
        band = self.compute_confidence_band(confidence, volatility)
        entry = EpistemicEntry(
            entry_id=entry_id,
            claim=claim,
            entry_type=entry_type,
            source_class=source_class,
            confidence=round(confidence, 3),
            volatility=round(volatility, 3),
            confidence_band=band,
            since_day=scope_day,
            metadata=metadata or {},
        )
        self.entries.append(entry)
        return entry

    def record_observation(
        self,
        entry_id: str,
        claim: str,
        *,
        source_class: SourceClass,
        confidence: float,
        volatility: float,
        since_day: int | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> EpistemicEntry:
        return self._record(
            entry_id=entry_id,
            claim=claim,
            entry_type="observation",
            source_class=source_class,
            confidence=confidence,
            volatility=volatility,
            since_day=since_day,
            metadata=metadata,
        )

    def record_inference(
        self,
        entry_id: str,
        claim: str,
        *,
        confidence: float,
        volatility: float,
        since_day: int | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> EpistemicEntry:
        return self._record(
            entry_id=entry_id,
            claim=claim,
            entry_type="inference",
            source_class="inference",
            confidence=confidence,
            volatility=volatility,
            since_day=since_day,
            metadata=metadata,
        )

    def record_pattern(
        self,
        entry_id: str,
        claim: str,
        *,
        confidence: float,
        volatility: float,
        since_day: int | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> EpistemicEntry:
        return self._record(
            entry_id=entry_id,
            claim=claim,
            entry_type="pattern",
            source_class="internal_synthesis",
            confidence=confidence,
            volatility=volatility,
            since_day=since_day,
            metadata=metadata,
        )

    def record_contradiction(
        self,
        entry_id: str,
        claim: str,
        *,
        confidence: float,
        volatility: float,
        since_day: int | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> EpistemicEntry:
        return self._record(
            entry_id=entry_id,
            claim=claim,
            entry_type="contradiction",
            source_class="external_witness",
            confidence=confidence,
            volatility=volatility,
            since_day=since_day,
            metadata=metadata,
        )

    def record_suspension(
        self,
        entry_id: str,
        claim: str,
        *,
        reason: SuspensionReason,
        since_day: int | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> EpistemicEntry:
        suspension_metadata = {"reason": reason, **(metadata or {})}
        return self._record(
            entry_id=entry_id,
            claim=claim,
            entry_type="suspension",
            source_class="internal_synthesis",
            confidence=0.0,
            volatility=0.0,
            since_day=since_day,
            metadata=suspension_metadata,
        )

    def record_belief(
        self,
        entry_id: str,
        claim: str,
        *,
        confidence: float,
        volatility: float,
        since_day: int | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> EpistemicEntry:
        return self._record(
            entry_id=entry_id,
            claim=claim,
            entry_type="belief",
            source_class="internal_synthesis",
            confidence=confidence,
            volatility=volatility,
            since_day=since_day,
            metadata=metadata,
        )


class ContradictionRegistry:
    """Links mutually exclusive claims without reconciling them."""

    def __init__(self, ledger: EpistemicLedger, *, high_confidence: float = 0.75):
        self.ledger = ledger
        self.high_confidence = high_confidence
        self.topics: dict[str, list[Mapping[str, object]]] = {}
        self.contradictions_by_topic: dict[str, list[ContradictionLink]] = {}

    def register_claim(
        self,
        claim_id: str,
        *,
        topic: str,
        value: str,
        confidence: float,
        source_class: SourceClass,
        volatility: float = 0.0,
        since_day: int | None = None,
    ) -> EpistemicEntry:
        claim = {"id": claim_id, "topic": topic, "value": value, "confidence": confidence}
        self.topics.setdefault(topic, []).append(claim)

        contradictions: list[tuple[Mapping[str, object], ContradictionLink]] = []
        for existing in self.topics[topic]:
            if (
                existing["id"] != claim_id
                and existing["value"] != value
                and existing["confidence"] >= self.high_confidence
                and confidence >= self.high_confidence
            ):
                contradictions.append(
                    (
                        existing,
                        ContradictionLink(topic=topic, claim_a=claim_id, claim_b=existing["id"]),
                    )
                )

        if contradictions:
            links = self.contradictions_by_topic.setdefault(topic, [])
            for existing, link in contradictions:
                if link not in links:
                    links.append(link)
                    volatility_score = self.ledger.estimate_volatility(
                        [confidence, float(existing.get("confidence", 0.0))]
                    )
                    self.ledger.record_contradiction(
                        f"contradiction:{link.claim_a}:{link.claim_b}",
                        f"{topic} contradiction between {link.claim_a} and {link.claim_b}",
                        confidence=1.0,
                        volatility=volatility_score,
                        metadata={"status": link.status, "topic": topic},
                    )

        return self.ledger.record_observation(
            claim_id,
            f"{topic}={value}",
            source_class=source_class,
            confidence=confidence,
            volatility=volatility,
            since_day=since_day,
            metadata={"topic": topic, "value": value},
        )

    def contradictions_for_topic(self, topic: str) -> list[ContradictionLink]:
        return list(self.contradictions_by_topic.get(topic, ()))

    def is_contradicted(self, claim_id: str) -> bool:
        return any(
            claim_id in {link.claim_a, link.claim_b}
            for links in self.contradictions_by_topic.values()
            for link in links
        )


class JudgmentSuspender:
    """Records withheld conclusions and protects them from premature synthesis."""

    def __init__(self, ledger: EpistemicLedger):
        self.ledger = ledger
        self.suspensions: dict[str, SuspensionRecord] = {}

    def suspend(
        self,
        claim_id: str,
        *,
        reason: SuspensionReason,
        note: str | None = None,
        since_day: int | None = None,
    ) -> SuspensionRecord:
        scope_day = self.ledger.current_day if since_day is None else since_day
        record = SuspensionRecord(claim_id=claim_id, reason=reason, since_day=scope_day, note=note)
        self.suspensions[claim_id] = record
        self.ledger.record_suspension(
            f"suspension:{claim_id}",
            f"suspended:{claim_id}",
            reason=reason,
            since_day=scope_day,
            metadata={"note": note},
        )
        return record

    def is_suspended(self, claim_id: str) -> bool:
        return claim_id in self.suspensions

    def active_suspensions(self) -> list[SuspensionRecord]:
        return list(self.suspensions.values())

    def days_withheld(self, claim_id: str) -> int:
        record = self.suspensions.get(claim_id)
        if not record:
            return 0
        return max(0, self.ledger.current_day - record.since_day)


class BeliefEnforcer:
    """Separates observations from beliefs and forbids action routing."""

    def __init__(
        self,
        ledger: EpistemicLedger,
        registry: ContradictionRegistry,
        suspender: JudgmentSuspender,
        *,
        persistence_days: int = 2,
        max_volatility: float = 0.25,
    ):
        self.ledger = ledger
        self.registry = registry
        self.suspender = suspender
        self.persistence_days = persistence_days
        self.max_volatility = max_volatility

    def form_belief(self, observation: EpistemicEntry) -> EpistemicEntry:
        if observation.entry_type != "observation":
            raise ValueError("Only observations may be considered for belief formation")
        if observation.metadata.get("fragment", True):
            raise ValueError("Observation fragments cannot be promoted to belief state")
        if observation.volatility > self.max_volatility:
            raise ValueError("Volatility too high for belief formation")
        if self.registry.is_contradicted(observation.entry_id):
            raise ValueError("Observation is contradicted and cannot become belief")
        if self.suspender.is_suspended(observation.entry_id):
            raise ValueError("Observation is suspended and cannot become belief")
        if (self.ledger.current_day - observation.since_day) < self.persistence_days:
            raise ValueError("Belief requires multi-day persistence before formation")
        confidence = min(1.0, observation.confidence)
        return self.ledger.record_belief(
            f"belief:{observation.entry_id}",
            observation.claim,
            confidence=confidence,
            volatility=observation.volatility,
            since_day=self.ledger.current_day,
            metadata={"from_observation": observation.entry_id},
        )

    def route_to_action(self, belief: EpistemicEntry) -> None:
        raise RuntimeError("Belief formation is internal-only and not actionable")


class EpistemicSelfCheck:
    """Introspective queries over epistemic posture."""

    def __init__(
        self,
        ledger: EpistemicLedger,
        registry: ContradictionRegistry,
        suspender: JudgmentSuspender,
    ):
        self.ledger = ledger
        self.registry = registry
        self.suspender = suspender

    def what_do_i_know(self) -> list[EpistemicEntry]:
        return [entry for entry in self.ledger.entries if entry.entry_type == "belief"]

    def what_am_i_uncertain_about(self) -> list[EpistemicEntry]:
        uncertain = [
            entry
            for entry in self.ledger.entries
            if entry.entry_type in {"observation", "inference", "pattern"}
            and (entry.confidence < 0.5 or entry.volatility > 0.4)
        ]
        for links in self.registry.contradictions_by_topic.values():
            for link in links:
                for entry in self.ledger.entries:
                    if entry.entry_id in {link.claim_a, link.claim_b} and entry not in uncertain:
                        uncertain.append(entry)
        return uncertain

    def what_am_i_refusing_to_conclude(self) -> list[SuspensionRecord]:
        return self.suspender.active_suspensions()


class EpistemicOrientation:
    """Bundles orientation utilities for epistemic posture finalization."""

    def __init__(self, *, starting_day: int = 0):
        self.ledger = EpistemicLedger(starting_day=starting_day)
        self.registry = ContradictionRegistry(self.ledger)
        self.suspender = JudgmentSuspender(self.ledger)
        self.belief_enforcer = BeliefEnforcer(self.ledger, self.registry, self.suspender)
        self.self_check = EpistemicSelfCheck(self.ledger, self.registry, self.suspender)

    def advance_day(self, days: int = 1) -> None:
        self.ledger.advance_day(days)

    def log_observation(
        self,
        entry_id: str,
        claim: str,
        *,
        source_class: SourceClass,
        confidence: float,
        volatility: float,
        since_day: int | None = None,
        fragment: bool = True,
    ) -> EpistemicEntry:
        return self.ledger.record_observation(
            entry_id,
            claim,
            source_class=source_class,
            confidence=confidence,
            volatility=volatility,
            since_day=since_day,
            metadata={"fragment": fragment},
        )

    def form_belief_from_observation(self, observation: EpistemicEntry) -> EpistemicEntry:
        return self.belief_enforcer.form_belief(observation)

    def detect_contradiction(
        self,
        claim_id: str,
        *,
        topic: str,
        value: str,
        confidence: float,
        source_class: SourceClass,
        volatility: float = 0.0,
        since_day: int | None = None,
    ) -> EpistemicEntry:
        return self.registry.register_claim(
            claim_id,
            topic=topic,
            value=value,
            confidence=confidence,
            source_class=source_class,
            volatility=volatility,
            since_day=since_day,
        )

    def suspend_judgment(
        self,
        claim_id: str,
        *,
        reason: SuspensionReason,
        note: str | None = None,
        since_day: int | None = None,
    ) -> SuspensionRecord:
        return self.suspender.suspend(claim_id, reason=reason, note=note, since_day=since_day)

    def introspect(self) -> dict[str, object]:
        return {
            "beliefs": self.self_check.what_do_i_know(),
            "uncertainties": self.self_check.what_am_i_uncertain_about(),
            "refusals": self.self_check.what_am_i_refusing_to_conclude(),
        }


__all__ = [
    "BeliefEnforcer",
    "ContradictionRegistry",
    "EpistemicEntry",
    "EpistemicEntryType",
    "EpistemicLedger",
    "EpistemicOrientation",
    "EpistemicSelfCheck",
    "SourceClass",
    "SuspensionReason",
    "SuspensionRecord",
]
